import torch
from torch import nn as nn
import torch.nn.functional as F
from torch.optim.lr_scheduler import MultiStepLR
from torch import optim
import numpy as np
from dataLoaders import create_ensemble_loaders
from utils import build_model, json_file_to_pyobj
import argparse
import os
import random
from tqdm import tqdm
import wandb
import ipdb

abs_path = '/home/ferles/medusa/src/'
global_seed = 1
torch.backends.cudnn.deterministic = True
random.seed(global_seed)
np.random.seed(global_seed)
torch.manual_seed(global_seed)
torch.cuda.manual_seed(global_seed)


def train(args):

    json_options = json_file_to_pyobj(args.config)
    training_configurations = json_options.training
    wandb.init(name=training_configurations.checkpoint+'Ensemble')
    device = torch.device(f'cuda:{args.device}')

    dataset = args.dataset.lower()
    pickle_files = [training_configurations.train_pickle, training_configurations.test_pickle]
    train_ind_loaders, train_ood_loaders, val_ind_loaders, val_ood_loaders, test_ind_loaders, test_ood_loaders = create_ensemble_loaders(dataset, num_classes=training_configurations.out_classes, pickle_files=pickle_files)

    criterion = nn.CrossEntropyLoss()
    b = 0.2
    m = 0.4

    epochs = 40
    model = build_model(args).to(device)
    optimizer = optim.SGD(model.parameters(), lr=1.25e-02, momentum=0.9, nesterov=True, weight_decay=1e-4)
    scheduler = MultiStepLR(optimizer, milestones=[10, 20, 30], gamma=0.1)

    best_val_acc = 0

    for index in range(len(train_ind_loaders)):

        train_ind_loader, train_ood_loader = train_ind_loaders[index], train_ood_loaders[index]
        val_ind_loader, _ = train_ind_loaders[index], train_ood_loaders[index]
        test_ind_loader, _ = test_ind_loaders[index], test_ood_loaders[index]

        ood_loader_iter = iter(train_ood_loader)

        for epoch in tqdm(range(epochs)):

            model.train()
            correct, total = 0, 0
            train_loss = 0
            for data in tqdm(train_ind_loader):
                inputs, labels = data
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad()

                outputs = model(inputs)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
                ce_loss = criterion(outputs, labels)

                try:
                    ood_inputs, _ = next(ood_loader_iter)
                except:
                    ood_loader_iter = iter(train_ood_loader)
                    ood_inputs, _ = next(ood_loader_iter)

                ood_inputs = ood_inputs.to(device)
                ood_outputs = model(ood_inputs)
                entropy_input = -torch.mean(torch.sum(F.log_softmax(outputs, dim=1) * F.softmax(outputs, dim=1), dim=1))
                entropy_output = -torch.mean(torch.sum(F.log_softmax(ood_outputs, dim=1) * F.softmax(ood_outputs, dim=1), dim=1))
                margin_loss = b*torch.clamp(m + entropy_input - entropy_output, min=0)

                loss = ce_loss + margin_loss
                train_loss += loss.item()
                loss.backward()
                optimizer.step()

            train_accuracy = correct / total
            wandb.log({'epoch': epoch}, commit=False)
            epoch_train_set_loss = train_loss / train_ind_loader.__len__()

            wandb.log({f'Train Set Loss {index}': epoch_train_set_loss, 'epoch': epoch})
            wandb.log({f'Train Set Accuracy {index}': train_accuracy, 'epoch': epoch})

            with torch.no_grad():

                model.eval()
                correct, total = 0, 0

                for data in val_ind_loader:
                    images, labels = data
                    images = images.to(device)
                    labels = labels.to(device)

                    outputs = model(images)
                    _, predicted = torch.max(outputs.data, 1)
                    total += labels.size(0)
                    correct += (predicted == labels).sum().item()

                val_epoch_accuracy = correct / total
                wandb.log({f'Validation Set Accuracy {index}': val_epoch_accuracy, 'epoch': epoch})

            if val_epoch_accuracy > best_val_acc:
                best_val_acc = val_epoch_accuracy
                if os.path.exists('/raid/ferles/'):
                    torch.save(model.state_dict(), f'/raid/ferles/checkpoints/eb0/{dataset}/{training_configurations.checkpoint}_best_accuracy_ensemble_{index}_sees1.pth')
                else:
                    torch.save(model.state_dict(), f'/home/ferles/checkpoints/eb0/{dataset}/{training_configurations.checkpoint}_best_accuracy_ensemble_{index}_sees1.pth')

                correct, total = 0, 0
                for data in test_ind_loader:
                    images, labels = data
                    images = images.to(device)
                    labels = labels.to(device)

                    outputs = model(images)
                    _, predicted = torch.max(outputs.data, 1)
                    total += labels.size(0)
                    correct += (predicted == labels).sum().item()

                test_epoch_accuracy = correct / total

            wandb.log({f'Test Set Accuracy {index}': test_epoch_accuracy, 'epoch': epoch})

    scheduler.step()


if __name__ == '__main__':

    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0, 1, 2, 3, 4, 5, 6, 7"

    parser = argparse.ArgumentParser(description='DL Dermatology models')

    parser.add_argument('--config', help='Training Configurations', required=True)
    parser.add_argument('--dataset', '--ds', default='cifar10', required=False)
    parser.add_argument('--device', '--dv', type=int, default=0, required=False)

    args = parser.parse_args()
    train(args)

