from __future__ import division,print_function

import argparse
import sys
import time

from tqdm import tqdm_notebook as tqdm
import random
import matplotlib.pyplot as plt
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.nn.init as init
from torch.autograd import Variable, grad
from torchvision import datasets, transforms
from torch.nn.parameter import Parameter
import calculate_log as callog
import warnings
torch.cuda.set_device(5)


def conv3x3(in_planes, out_planes, stride=1):
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)

class BottleneckBlock(nn.Module):
    def __init__(self, in_planes, out_planes, dropRate=0.0):
        super(BottleneckBlock, self).__init__()
        inter_planes = out_planes * 4
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv1 = nn.Conv2d(in_planes, inter_planes, kernel_size=1, stride=1,
                               padding=0, bias=False)
        self.bn2 = nn.BatchNorm2d(inter_planes)
        self.conv2 = nn.Conv2d(inter_planes, out_planes, kernel_size=3, stride=1,
                               padding=1, bias=False)
        self.droprate = dropRate

    def forward(self, x):

        out = self.conv1(self.relu(self.bn1(x)))

        torch_model.record(out)

        if self.droprate > 0:
            out = F.dropout(out, p=self.droprate, inplace=False, training=self.training)

        out = self.conv2(self.relu(self.bn2(out)))
        torch_model.record(out)

        if self.droprate > 0:
            out = F.dropout(out, p=self.droprate, inplace=False, training=self.training)
        return torch.cat([x, out], 1)

class TransitionBlock(nn.Module):
    def __init__(self, in_planes, out_planes, dropRate=0.0):
        super(TransitionBlock, self).__init__()
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv1 = nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=1,
                               padding=0, bias=False)
        self.droprate = dropRate

    def forward(self, x):
        out = self.conv1(self.relu(self.bn1(x)))
        torch_model.record(out)

        if self.droprate > 0:
            out = F.dropout(out, p=self.droprate, inplace=False, training=self.training)
        return F.avg_pool2d(out, 2)

class DenseBlock(nn.Module):
    def __init__(self, nb_layers, in_planes, growth_rate, block, dropRate=0.0):
        super(DenseBlock, self).__init__()
        self.layer = self._make_layer(block, in_planes, growth_rate, nb_layers, dropRate)

    def _make_layer(self, block, in_planes, growth_rate, nb_layers, dropRate):
        layers = []
        for i in range(int(nb_layers)):
            layers.append(block(in_planes+i*growth_rate, growth_rate, dropRate))
        return nn.Sequential(*layers)

    def forward(self, x):
        t = self.layer(x)
        torch_model.record(t)
        return t


class DenseNet3(nn.Module):
    def __init__(self, depth, num_classes, growth_rate=12,
                 reduction=0.5, bottleneck=True, dropRate=0.0):
        super(DenseNet3, self).__init__()

        self.collecting = False

        in_planes = 2 * growth_rate
        n = (depth - 4) / 3
        if bottleneck == True:
            n = n/2
            block = BottleneckBlock
        else:
            block = BasicBlock
        # 1st conv before any dense block
        self.conv1 = nn.Conv2d(3, in_planes, kernel_size=3, stride=1,
                               padding=1, bias=False)
        # 1st block
        self.block1 = DenseBlock(n, in_planes, growth_rate, block, dropRate)
        in_planes = int(in_planes+n*growth_rate)
        self.trans1 = TransitionBlock(in_planes, int(math.floor(in_planes*reduction)), dropRate=dropRate)
        in_planes = int(math.floor(in_planes*reduction))
        # 2nd block
        self.block2 = DenseBlock(n, in_planes, growth_rate, block, dropRate)
        in_planes = int(in_planes+n*growth_rate)
        self.trans2 = TransitionBlock(in_planes, int(math.floor(in_planes*reduction)), dropRate=dropRate)
        in_planes = int(math.floor(in_planes*reduction))
        # 3rd block
        self.block3 = DenseBlock(n, in_planes, growth_rate, block, dropRate)
        in_planes = int(in_planes+n*growth_rate)
        # global average pooling and classifier
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.relu = nn.ReLU(inplace=True)
        self.fc = nn.Linear(in_planes, num_classes)
        self.in_planes = in_planes

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                m.bias.data.zero_()

    def forward(self, x):
        out = self.conv1(x)
        out = self.trans1(self.block1(out))
        out = self.trans2(self.block2(out))
        out = self.block3(out)
        out = self.relu(self.bn1(out))
        out = F.avg_pool2d(out, 8)
        out = out.view(-1, self.in_planes)
        return self.fc(out)

    def load(self, path="densenet_cifar10.pth"):
        tm = torch.load(path,map_location="cpu")
        self.load_state_dict(tm.state_dict(),strict=False)

    def record(self, t):
        if self.collecting:
            self.gram_feats.append(t)

    def gram_feature_list(self,x):
        self.collecting = True
        self.gram_feats = []
        self.forward(x)
        self.collecting = False
        temp = self.gram_feats
        self.gram_feats = []
        return temp

    def get_min_max(self, data, power):
        mins = []
        maxs = []

        for i in range(0,len(data),64):
            batch = data[i:i+64].cuda()
            feat_list = self.gram_feature_list(batch)
            for L,feat_L in enumerate(feat_list):
                if L==len(mins):
                    mins.append([None]*len(power))
                    maxs.append([None]*len(power))

                for p,P in enumerate(power):
                    g_p = G_p(feat_L,P)

                    current_min = g_p.min(dim=0,keepdim=True)[0]
                    current_max = g_p.max(dim=0,keepdim=True)[0]

                    if mins[L][p] is None:
                        mins[L][p] = current_min
                        maxs[L][p] = current_max
                    else:
                        mins[L][p] = torch.min(current_min,mins[L][p])
                        maxs[L][p] = torch.max(current_max,maxs[L][p])

        return mins,maxs

    def get_deviations(self,data,power,mins,maxs):
        deviations = []

        for i in range(0,len(data),64):
            batch = data[i:i+64].cuda()
            feat_list = self.gram_feature_list(batch)
            batch_deviations = []
            for L,feat_L in enumerate(feat_list):
                dev = 0
                for p,P in enumerate(power):
                    g_p = G_p(feat_L,P)

                    dev +=  (F.relu(mins[L][p]-g_p)/torch.abs(mins[L][p]+10**-6)).sum(dim=1,keepdim=True)
                    dev +=  (F.relu(g_p-maxs[L][p])/torch.abs(maxs[L][p]+10**-6)).sum(dim=1,keepdim=True)
                batch_deviations.append(dev.cpu().detach().numpy())
            batch_deviations = np.concatenate(batch_deviations,axis=1)
            deviations.append(batch_deviations)
        deviations = np.concatenate(deviations,axis=0)

        return deviations

start = time.time()
parser = argparse.ArgumentParser(description='Out-of-Distribution Detection')
parser.add_argument('--model_checkpoint', '--mc', required=True)
parser.add_argument('--device', '--dv', type=int, default=0, required=False)

args = parser.parse_args()
device = torch.device(f'cuda:{args.device}')

torch_model = DenseNet3(100, num_classes=10)
torch_model.load()
torch_model.cuda()
torch_model.params = list(torch_model.parameters())
torch_model.eval()
print("Loaded DenseNet")

batch_size = 128
mean = np.array([[125.3/255, 123.0/255, 113.9/255]]).T

std = np.array([[63.0/255, 62.1/255.0, 66.7/255.0]]).T
normalize = transforms.Normalize((125.3/255, 123.0/255, 113.9/255), (63.0/255, 62.1/255.0, 66.7/255.0))

transform_train = transforms.Compose([
    transforms.RandomCrop(32, padding=4),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    normalize

])
transform_test = transforms.Compose([
    transforms.CenterCrop(size=(32, 32)),
    transforms.ToTensor(),
    normalize
])

train_loader = torch.utils.data.DataLoader(
    datasets.CIFAR10('data', train=True, download=True,
                     transform=transform_train),
    batch_size=batch_size, shuffle=True)
test_loader = torch.utils.data.DataLoader(
    datasets.CIFAR10('data', train=False, transform=transform_test),
    batch_size=batch_size)


data_train = list(torch.utils.data.DataLoader(
    datasets.CIFAR10('data', train=True, download=True,
                     transform=transform_test),
    batch_size=1, shuffle=False))


data = list(torch.utils.data.DataLoader(
    datasets.CIFAR10('data', train=False, download=True,
                     transform=transform_test),
    batch_size=1, shuffle=False))

torch_model.eval()
correct = 0
total = 0
for x,y in test_loader:
    x = x.cuda()
    y = y.numpy()
    correct += (y==np.argmax(torch_model(x).detach().cpu().numpy(),axis=1)).sum()
    total += y.shape[0]
print("Accuracy: ",correct/total)

cifar100 = list(torch.utils.data.DataLoader(
    datasets.CIFAR100('data', train=False, download=True,
                      transform=transform_test),
    batch_size=1, shuffle=False))

svhn = list(torch.utils.data.DataLoader(
    datasets.SVHN('data', split="test", download=True,
                  transform=transform_test),
    batch_size=1, shuffle=True))

train_preds = []
train_confs = []
train_logits = []
for idx in range(0,len(data_train),128):
    batch = torch.squeeze(torch.stack([x[0] for x in data_train[idx:idx+128]]),dim=1).cuda()

    logits = torch_model(batch)
    confs = F.softmax(logits,dim=1).cpu().detach().numpy()
    preds = np.argmax(confs,axis=1)
    logits = (logits.cpu().detach().numpy())

    train_confs.extend(np.max(confs,axis=1))
    train_preds.extend(preds)
    train_logits.extend(logits)
print("Train Preds")

test_preds = []
test_confs = []
test_logits = []

for idx in range(0,len(data),128):
    batch = torch.squeeze(torch.stack([x[0] for x in data[idx:idx+128]]),dim=1).cuda()

    logits = torch_model(batch)
    confs = F.softmax(logits,dim=1).cpu().detach().numpy()
    preds = np.argmax(confs,axis=1)
    logits = (logits.cpu().detach().numpy())

    test_confs.extend(np.max(confs,axis=1))
    test_preds.extend(preds)
    test_logits.extend(logits)
print("Test Preds")

import calculate_log as callog
def detect(all_test_deviations,all_ood_deviations, verbose=True, normalize=True):
    average_results = {}
    for i in range(1,11):
        random.seed(i)

        validation_indices = random.sample(range(len(all_test_deviations)),int(0.1*len(all_test_deviations)))
        test_indices = sorted(list(set(range(len(all_test_deviations)))-set(validation_indices)))

        validation = all_test_deviations[validation_indices]
        test_deviations = all_test_deviations[test_indices]

        t95 = validation.mean(axis=0)+10**-7
        if not normalize:
            t95 = np.ones_like(t95)
        test_deviations = (test_deviations/t95[np.newaxis,:]).sum(axis=1)
        ood_deviations = (all_ood_deviations/t95[np.newaxis,:]).sum(axis=1)

        results = callog.compute_metric(-test_deviations,-ood_deviations)
        for m in results:
            average_results[m] = average_results.get(m,0)+results[m]

    for m in average_results:
        average_results[m] /= i
    if verbose:
        callog.print_results(average_results)
    return average_results


def cpu(ob):
    for i in range(len(ob)):
        for j in range(len(ob[i])):
            ob[i][j] = ob[i][j].cpu()
    return ob

def cuda(ob):
    for i in range(len(ob)):
        for j in range(len(ob[i])):
            ob[i][j] = ob[i][j].cuda()
    return ob

class Detector:
    def __init__(self):
        self.all_test_deviations = None
        self.mins = {}
        self.maxs = {}
        self.classes = range(10)

    def compute_minmaxs(self,data_train,POWERS=[10]):
        for PRED in tqdm(self.classes):
            train_indices = np.where(np.array(train_preds)==PRED)[0]
            train_PRED = torch.squeeze(torch.stack([data_train[i][0] for i in train_indices]),dim=1)
            mins,maxs = torch_model.get_min_max(train_PRED,power=POWERS)
            self.mins[PRED] = cpu(mins)
            self.maxs[PRED] = cpu(maxs)
            torch.cuda.empty_cache()

    def compute_test_deviations(self,POWERS=[10]):
        all_test_deviations = None
        for PRED in tqdm(self.classes):
            test_indices = np.where(np.array(test_preds)==PRED)[0]
            test_PRED = torch.squeeze(torch.stack([data[i][0] for i in test_indices]),dim=1)
            test_confs_PRED = np.array([test_confs[i] for i in test_indices])
            mins = cuda(self.mins[PRED])
            maxs = cuda(self.maxs[PRED])
            test_deviations = torch_model.get_deviations(test_PRED,power=POWERS,mins=mins,maxs=maxs)/test_confs_PRED[:,np.newaxis]
            cpu(mins)
            cpu(maxs)
            if all_test_deviations is None:
                all_test_deviations = test_deviations
            else:
                all_test_deviations = np.concatenate([all_test_deviations,test_deviations],axis=0)
            torch.cuda.empty_cache()
        self.all_test_deviations = all_test_deviations

    def compute_ood_deviations(self,ood,POWERS=[10]):
        ood_preds = []
        ood_confs = []

        for idx in range(0,len(ood),128):
            batch = torch.squeeze(torch.stack([x[0] for x in ood[idx:idx+128]]),dim=1).cuda()
            logits = torch_model(batch)
            confs = F.softmax(logits,dim=1).cpu().detach().numpy()
            preds = np.argmax(confs,axis=1)

            ood_confs.extend(np.max(confs,axis=1))
            ood_preds.extend(preds)
            torch.cuda.empty_cache()
        print("Done")

        all_ood_deviations = None
        for PRED in tqdm(self.classes):
            ood_indices = np.where(np.array(ood_preds)==PRED)[0]
            if len(ood_indices)==0:
                continue
            ood_PRED = torch.squeeze(torch.stack([ood[i][0] for i in ood_indices]),dim=1)
            ood_confs_PRED =  np.array([ood_confs[i] for i in ood_indices])
            mins = cuda(self.mins[PRED])
            maxs = cuda(self.maxs[PRED])
            ood_deviations = torch_model.get_deviations(ood_PRED,power=POWERS,mins=mins,maxs=maxs)/ood_confs_PRED[:,np.newaxis]
            cpu(self.mins[PRED])
            cpu(self.maxs[PRED])
            if all_ood_deviations is None:
                all_ood_deviations = ood_deviations
            else:
                all_ood_deviations = np.concatenate([all_ood_deviations,ood_deviations],axis=0)
            torch.cuda.empty_cache()
        average_results = detect(self.all_test_deviations,all_ood_deviations)
        return average_results, self.all_test_deviations, all_ood_deviations

def G_p(ob, p):
    temp = ob.detach()

    temp = temp**p
    temp = temp.reshape(temp.shape[0],temp.shape[1],-1)
    temp = ((torch.matmul(temp,temp.transpose(dim0=2,dim1=1)))).sum(dim=2)
    temp = (temp.sign()*torch.abs(temp)**(1/p)).reshape(temp.shape[0],-1)

    return temp

detector = Detector()
detector.compute_minmaxs(data_train,POWERS=range(1,11))

detector.compute_test_deviations(POWERS=range(1,11))

print("SVHN")
svhn_results = detector.compute_ood_deviations(svhn,POWERS=range(1,11))
print("CIFAR-100")
c100_results = detector.compute_ood_deviations(cifar100,POWERS=range(1,11))