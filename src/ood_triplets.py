import torch
import torch.nn.functional as F
import numpy as np
from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import confusion_matrix
from torch import nn
from torch.autograd import Variable
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import roc_curve, auc
from utils import build_model_with_checkpoint
from dataLoaders import get_ood_loaders
from tqdm import tqdm
import lib_generation
import argparse
import os
import random
import pickle
import ipdb
from ood import _find_threshold, _get_metrics, _score_npzs, _score_mahalanobis, _predict_mahalanobis, _get_baseline_scores

abs_path = '/home/ferles/Dermatology/medusa/'
global_seed = 1
torch.backends.cudnn.deterministic = True
random.seed(global_seed)
torch.manual_seed(global_seed)
torch.cuda.manual_seed(global_seed)


def _verbose(method, ood_dataset_1, ood_dataset_2, ood_dataset_3, aucs, fprs, accs):

    print('###############################################')
    print()
    print(f"{method} results on {ood_dataset_1} (Out):")
    print()
    print(f'Area Under Receiver Operating Characteristic curve: {aucs[0]}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fprs[0]}')
    print(f'Detection Accuracy: {accs[0]}')
    print('###############################################')
    print()
    print(f"{method} results on {ood_dataset_2} (Out):")
    print()
    print(f'Area Under Receiver Operating Characteristic curve: {aucs[1]}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fprs[1]}')
    print(f'Detection Accuracy: {accs[1]}')
    print('###############################################')
    print()
    print(f"{method} results on {ood_dataset_3} (Out):")
    print()
    print(f'Area Under Receiver Operating Characteristic curve: {aucs[2]}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fprs[2]}')
    print(f'Detection Accuracy: {accs[2]}')
    print('###############################################')
    print()
    print('###############################################')
    print('###############################################')
    print(f"MEAN PERFORMANCE OF {method.upper()}:")
    print(f'Area Under Receiver Operating Characteristic curve: {round(np.mean(aucs), 2)}')
    print(f'False Positive Rate @ 95% True Positive Rate: {round(np.mean(fprs), 2)}')
    print(f'Detection Accuracy: {round(np.mean(accs), 2)}')
    print('###############################################')
    print('###############################################')


def _baseline(model, loaders, device, ind_dataset, val_dataset, ood_dataset_1, ood_dataset_2, ood_dataset_3, monte_carlo_steps=1, exclude_class=None):

    val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader_1, test_ood_loader_2, test_ood_loader_3 = loaders
    model.eval()

    if monte_carlo_steps > 1:
        model._dropout.train()

    val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader = loaders
    val_ind = _get_baseline_scores(model, val_ind_loader, device, monte_carlo_steps)
    val_ood = _get_baseline_scores(model, val_ood_loader, device, monte_carlo_steps)

    if monte_carlo_steps > 1:
        val_ind = val_ind / monte_carlo_steps
        val_ood = val_ood / monte_carlo_steps

    acc, threshold = _find_threshold(val_ind, val_ood)

    test_ind = _get_baseline_scores(model, test_ind_loader, device, monte_carlo_steps)
    test_ood_1 = _get_baseline_scores(model, test_ood_loader_1, device, monte_carlo_steps)
    test_ood_2 = _get_baseline_scores(model, test_ood_loader_2, device, monte_carlo_steps)
    test_ood_3 = _get_baseline_scores(model, test_ood_loader_3, device, monte_carlo_steps)

    if exclude_class is None:
        if monte_carlo_steps == 1:
            ind_savefile_name = f'npzs/baseline_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}.npz'
            ood_savefile_name_1 = f'npzs/baseline_{ood_dataset_1}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_1}.npz'
            ood_savefile_name_2 = f'npzs/baseline_{ood_dataset_2}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_2}.npz'
            ood_savefile_name_3 = f'npzs/baseline_{ood_dataset_3}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_3}.npz'
        else:
            ind_savefile_name = f'npzs/baseline_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_monte_carlo_{monte_carlo_steps}.npz'
            ood_savefile_name_1 = f'npzs/baseline_{ood_dataset_1}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_1}_monte_carlo_{monte_carlo_steps}.npz'
            ood_savefile_name_2 = f'npzs/baseline_{ood_dataset_2}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_2}_monte_carlo_{monte_carlo_steps}.npz'
            ood_savefile_name_3 = f'npzs/baseline_{ood_dataset_3}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_3}_monte_carlo_{monte_carlo_steps}.npz'
    else:
        if monte_carlo_steps == 1:
            ind_savefile_name = f'npzs/baseline_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{exclude_class}.npz'
            ood_savefile_name_1 = f'npzs/baseline_{ood_dataset_1}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_1}_{exclude_class}.npz'
            ood_savefile_name_2 = f'npzs/baseline_{ood_dataset_2}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_2}_{exclude_class}.npz'
            ood_savefile_name_3 = f'npzs/baseline_{ood_dataset_3}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_3}_{exclude_class}.npz'
        else:
            ind_savefile_name = f'npzs/baseline_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_monte_carlo_{monte_carlo_steps}_{exclude_class}.npz'
            ood_savefile_name_1 = f'npzs/baseline_{ood_dataset_1}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_1}_monte_carlo_{monte_carlo_steps}_{exclude_class}.npz'
            ood_savefile_name_2 = f'npzs/baseline_{ood_dataset_2}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_2}_monte_carlo_{monte_carlo_steps}_{exclude_class}.npz'
            ood_savefile_name_3 = f'npzs/baseline_{ood_dataset_3}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset_3}_monte_carlo_{monte_carlo_steps}_{exclude_class}.npz'

    np.savez(ind_savefile_name, test_ind)
    np.savez(ood_savefile_name_1, test_ood_1)
    np.savez(ood_savefile_name_2, test_ood_2)
    np.savez(ood_savefile_name_3, test_ood_3)

    auc_1, fpr_1, acc_1 = _score_npzs(test_ind, test_ood_1, threshold)
    auc_2, fpr_2, acc_2 = _score_npzs(test_ind, test_ood_2, threshold)
    auc_3, fpr_3, acc_3 = _score_npzs(test_ind, test_ood_3, threshold)

    aucs = [auc_1, auc_2, auc_3]
    fprs = [fpr_1, fpr_2, fpr_3]
    accs = [acc_1, acc_2, acc_3]

    print('###############################################')
    print()
    print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name} and out-distribution ood scores to: {ood_savefile_name_1}, {ood_savefile_name_2} and {ood_savefile_name_3}')
    print()
    print('###############################################')
    print()
    print(f"InD dataset: {ind_dataset}")
    print(f"Validation dataset: {val_dataset}")
    if monte_carlo_steps == 1:
        method = f"Baseline"
    else:
        method = f"Baseline results with MC dropout ({monte_carlo_steps} steps)"
    _verbose(method, ood_dataset_1, ood_dataset_2, ood_dataset_3, aucs, fprs, accs)


def _process(model, images, T, epsilon, device, criterion=nn.CrossEntropyLoss()):

    model.eval()
    if T == 1 and epsilon == 0:
        outputs = model(images.to(device))
        nnOutputs = outputs.detach().cpu().numpy()
    else:
        inputs = Variable(images.to(device), requires_grad=True)
        outputs = model(inputs)
        nnOutputs = outputs.data.cpu()
        nnOutputs = nnOutputs.numpy()
        nnOutputs = nnOutputs - np.max(nnOutputs, axis=1).reshape(nnOutputs.shape[0], 1)
        nnOutputs = np.exp(nnOutputs)/np.sum(np.exp(nnOutputs), axis=1).reshape(nnOutputs.shape[0], 1)
        outputs = outputs / T

        maxIndexTemp = np.argmax(nnOutputs, axis=1)
        labels = Variable(torch.LongTensor([maxIndexTemp]).to(device))
        loss = criterion(outputs, labels[0])
        loss.backward()

        gradient = torch.ge(inputs.grad.data, 0)
        gradient = (gradient.float() - 0.5) * 2

        tempInputs = torch.add(inputs.data,  -epsilon, gradient)
        outputs = model(Variable(tempInputs))
        outputs = outputs / T

        nnOutputs = outputs.data.cpu()
        nnOutputs = nnOutputs.numpy()
        nnOutputs = nnOutputs - np.max(nnOutputs, axis=1).reshape(nnOutputs.shape[0], 1)
        nnOutputs = np.exp(nnOutputs)/np.sum(np.exp(nnOutputs), axis=1).reshape(nnOutputs.shape[0], 1)

    return nnOutputs


def _get_odin_scores(model, loader, T, epsilon, device, score_entropy=False):

    model.eval()

    len_ = 0
    arr = np.zeros(loader.batch_size*loader.__len__())
    for index, data in enumerate(loader):
        images, _ = data
        nnOutputs = _process(model, images, T, epsilon, device=device)
        top_class_probability = np.max(nnOutputs, axis=1)
        if not score_entropy:
            arr[index*loader.batch_size:index*loader.batch_size + top_class_probability.shape[0]] = top_class_probability
        else:
            entropy = -np.sum(np.log(nnOutputs) * nnOutputs, axis=1)
            arr[index*loader.batch_size:index*loader.batch_size + top_class_probability.shape[0]] = top_class_probability - entropy
        len_ += top_class_probability.shape[0]

    return arr[:len_]


def _odin(model, loaders, device, ind_dataset, val_dataset, ood_dataset, exclude_class=None):

    model.eval()
    val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader = loaders

    best_auc = 0

    for T in [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]:
        for epsilon in tqdm(np.arange(0, 0.004, 0.004/21, float).tolist()):

            val_ind = _get_odin_scores(model, val_ind_loader, T, epsilon, device=device)
            val_ood = _get_odin_scores(model, val_ood_loader, T, epsilon, device=device)
            auc, _, _ = _score_npzs(val_ind, val_ood, threshold=0)

            if auc > best_auc:
                best_auc = auc
                best_epsilon = epsilon
                best_T = T
                best_val_ind = val_ind
                best_val_ood = val_ood

    print('###############################################')
    print()
    print(f'Selected temperature: {best_T}, selected epsilon: {best_epsilon}')
    print()

    _, threshold = _find_threshold(best_val_ind, best_val_ood)

    ind = _get_odin_scores(model, test_ind_loader, best_T, best_epsilon, device=device)
    ood = _get_odin_scores(model, test_ood_loader, best_T, best_epsilon, device=device)

    if exclude_class is None:
        ind_savefile_name = f'npzs/odin_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_temperature_{best_T}_epsilon{best_epsilon}.npz'
        ood_savefile_name = f'npzs/odin_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_temperature_{best_T}_epsilon{best_epsilon}.npz'
    else:
        ind_savefile_name = f'npzs/odin_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_temperature_{best_T}_epsilon{best_epsilon}_{exclude_class}.npz'
        ood_savefile_name = f'npzs/odin_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_temperature_{best_T}_epsilon{best_epsilon}_{exclude_class}.npz'

    np.savez(ind_savefile_name, ind)
    np.savez(ood_savefile_name, ood)

    auc, fpr, acc = _score_npzs(ind, ood, threshold)

    print('###############################################')
    print()
    print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name} and out-distribution ood scores to: {ood_savefile_name}')
    print()
    print('###############################################')
    print()
    print(f"Odin results on {ind_dataset} (In) vs {ood_dataset} (Out) with Val Set {val_dataset} and chosen T={best_T}, epsilon={best_epsilon}:")
    print(f'Area Under Receiver Operating Characteristic curve: {auc}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fpr}')
    print(f'Detection Accuracy: {acc}')


def _generate_Mahalanobis(model, loaders, device, ind_dataset, val_dataset, ood_dataset, num_classes=10, exclude_class=None, model_type='eb0'):

    model.eval()
    train_ind_loader, val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader = loaders

    temp_x = torch.rand(2, 3, 224, 224).to(device)
    temp_x = Variable(temp_x)
    temp_x = temp_x.to(device)
    if model_type == 'eb0':
        idxs = [0, 2, 4, 7, 10, 14, 15]
        x, features = model.extract_features(temp_x, mode='all')
    else:
        # TODO: In case you wish to evaluate other models, you need to define a proper way to get middle level features
        pass
    features = [features[idx] for idx in idxs] + [x]
    num_output = len(features)
    feature_list = np.empty(num_output)
    count = 0
    for out in features:
        feature_list[count] = out.size(1)
        count += 1

    ipdb.set_trace()
    sample_mean, precision = lib_generation.sample_estimator(model, num_classes, feature_list, train_ind_loader, device=device)

    best_auc = 0
    m_list = [0.0, 0.01, 0.005, 0.002, 0.0014, 0.001, 0.0005]

    best_magnitudes, best_fprs, regressors, thresholds = [], [], [], []
    for magnitude in m_list:
        for i in range(num_output):
            M_val = lib_generation.get_Mahalanobis_score(model, val_ind_loader, num_classes, sample_mean, precision, i, magnitude, device=device)
            M_val = np.asarray(M_val, dtype=np.float32)
            if i == 0:
                Mahalanobis_val_ind = M_val.reshape((M_val.shape[0], -1))
            else:
                Mahalanobis_val_ind = np.concatenate((Mahalanobis_val_ind, M_val.reshape((M_val.shape[0], -1))), axis=1)

        for i in range(num_output):
            M_val_ood = lib_generation.get_Mahalanobis_score(model, val_ood_loader, num_classes, sample_mean, precision, i, magnitude, device=device)
            M_val_ood = np.asarray(M_val_ood, dtype=np.float32)
            if i == 0:
                Mahalanobis_val_ood = M_val_ood.reshape((M_val_ood.shape[0], -1))
            else:
                Mahalanobis_val_ood = np.concatenate((Mahalanobis_val_ood, M_val_ood.reshape((M_val_ood.shape[0], -1))), axis=1)

        Mahalanobis_val_ind = np.asarray(Mahalanobis_val_ind, dtype=np.float32)
        Mahalanobis_val_ood = np.asarray(Mahalanobis_val_ood, dtype=np.float32)

        regressor, auc, threshold = _score_mahalanobis(Mahalanobis_val_ind, Mahalanobis_val_ood)
        with open(f'lr_pickles/logistic_regressor_{exclude_class}_{magnitude}.pickle', 'wb') as lrp:
            pickle.dump(regressor, lrp, protocol=pickle.HIGHEST_PROTOCOL)

        if auc > best_auc:
            best_auc = auc
            best_magnitudes = [magnitude]
            regressors = [regressor]
            thresholds = [threshold]
        elif auc == best_auc:
            best_magnitudes.append(magnitude)
            regressors.append(regressor)
            thresholds.append(threshold)

    print('###############################################')
    print()
    print(f'Selected magnitudes: {best_magnitudes}')
    print(f'Selected thresholds: {thresholds}')
    print()

    aucs, fprs, accs = [], [], []
    for (best_magnitude, regressor, threshold) in zip(best_magnitudes, regressors, thresholds):
        for i in range(num_output):
            M_test = lib_generation.get_Mahalanobis_score(model, test_ind_loader, num_classes, sample_mean, precision, i, best_magnitude, device=device)
            M_test = np.asarray(M_test, dtype=np.float32)
            if i == 0:
                Mahalanobis_test = M_test.reshape((M_test.shape[0], -1))
            else:
                Mahalanobis_test = np.concatenate((Mahalanobis_test, M_test.reshape((M_test.shape[0], -1))), axis=1)

        for i in range(num_output):
            M_ood = lib_generation.get_Mahalanobis_score(model, test_ood_loader, num_classes, sample_mean, precision, i, best_magnitude, device=device)
            M_ood = np.asarray(M_ood, dtype=np.float32)
            if i == 0:
                Mahalanobis_ood = M_ood.reshape((M_ood.shape[0], -1))
            else:
                Mahalanobis_ood = np.concatenate((Mahalanobis_ood, M_ood.reshape((M_ood.shape[0], -1))), axis=1)

        Mahalanobis_test = np.asarray(Mahalanobis_test, dtype=np.float32)
        Mahalanobis_ood = np.asarray(Mahalanobis_ood, dtype=np.float32)

        if exclude_class is None:
            ind_savefile_name = f'npzs/Mahalanobis_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_{best_magnitude}.npz'
            ood_savefile_name = f'npzs/Mahalanobis_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_{best_magnitude}.npz'
        else:
            ind_savefile_name = f'npzs/Mahalanobis_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_{best_magnitude}_{exclude_class}.npz'
            ood_savefile_name = f'npzs/Mahalanobis_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_{best_magnitude}_{exclude_class}.npz'

        np.savez(ind_savefile_name, Mahalanobis_test)
        np.savez(ood_savefile_name, Mahalanobis_ood)
        auc, fpr, acc = _predict_mahalanobis(regressor, Mahalanobis_test, Mahalanobis_ood, threshold)
        aucs.append(auc)
        fprs.append(fpr)
        accs.append(acc)
        print('###############################################')
        print()
        print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name} and out-distribution ood scores to {ood_savefile_name}')
        print()
        print('###############################################')
        print()

    auc = round(np.mean(aucs), 2)
    fpr = round(np.mean(fprs), 2)
    acc = round(np.mean(accs), 2)
    print(f'Mahalanobis results on {ind_dataset} (In) vs {ood_dataset} (Out)  with Val Set {val_dataset}:')
    print(f'Area Under Receiver Operating Characteristic curve: {auc}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fpr}')
    print(f'Detection Accuracy : {acc}')
    print('###############################################')
    print()


def _predict_rotations(model, loader, num_classes, device):

    model.eval()
    uniform = torch.zeros(num_classes)
    for i in range(uniform.size()[0]):
        uniform[i] = 1.0 / uniform.size()[0]

    uniform = uniform.to(device)

    numpy_array_full = np.zeros(loader.batch_size*loader.__len__())
    numpy_array_kl_div = np.zeros(loader.batch_size*loader.__len__())
    numpy_array_rot_score = np.zeros(loader.batch_size*loader.__len__())
    for index, data in tqdm(enumerate(loader)):

        images, _ = data
        images = images.to(device)

        with torch.no_grad():
            outputs = model(images)
            log_softmax_outputs = torch.log_softmax(outputs, 1)
            kl_div = F.kl_div(log_softmax_outputs, uniform)

            # Rotation Loss
            rot_gt = torch.cat((torch.zeros(images.size(0)),
                                torch.ones(images.size(0)),
                                2*torch.ones(images.size(0)),
                                3*torch.ones(images.size(0))), 0).long().to(device)

            rot_images = images.detach().cpu().numpy()
            rot_images = np.concatenate((rot_images, np.rot90(rot_images, 1, axes=(2, 3)),
                                         np.rot90(rot_images, 2, axes=(2, 3)), np.rot90(rot_images, 3, axes=(2, 3))), 0)

            rot_images = torch.FloatTensor(rot_images)
            rot_images = rot_images.to(device)

            rot_preds = model(rot_images, rot=True)
            ce_rot = F.cross_entropy(rot_preds, rot_gt)

            numpy_array_kl_div[index] = kl_div.item()
            numpy_array_rot_score[index] = - 0.25 * ce_rot.item()
            anomaly_score = kl_div.item() - 0.25 * ce_rot.item()
            numpy_array_full[index] = anomaly_score

    return numpy_array_kl_div, numpy_array_rot_score, numpy_array_full


def _rotation(model, loaders, device, ind_dataset, val_dataset, ood_dataset, num_classes, exclude_class=None):

    val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader = loaders

    val_ind_kl_div, val_ind_rot_score, val_ind_full = _predict_rotations(model, val_ind_loader, num_classes, device=device)
    val_ood_kl_div, val_ood_rot_score, val_ood_full = _predict_rotations(model, val_ood_loader, num_classes, device=device)

    _, threshold = _find_threshold(val_ind_full, val_ood_full)

    ind_kl_div, ind_rot_score, ind_full = _predict_rotations(model, test_ind_loader, num_classes, device=device)
    ood_kl_div, ood_rot_score, ood_full = _predict_rotations(model, test_ood_loader, num_classes, device=device)

    if exclude_class is None:
        # ind_savefile_name_kl_div = f'npzs/self_supervision_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_kl_div.npz'
        # ind_savefile_name_rot_score = f'npzs/self_supervision_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_rot_score.npz'
        ind_savefile_name_full = f'npzs/self_supervision_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_full.npz'
        # ood_savefile_name_kl_div = f'npzs/self_supervision_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_kl_div.npz'
        # ood_savefile_name_rot_score = f'npzs/self_supervision_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_rot_score.npz'
        ood_savefile_name_full = f'npzs/self_supervision_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_full.npz'
    else:
        # ind_savefile_name_kl_div = f'npzs/self_supervision_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_kl_div_{exclude_class}.npz'
        # ind_savefile_name_rot_score = f'npzs/self_supervision_{ind_dataset}__ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}rot_score_{exclude_class}.npz'
        ind_savefile_name_full = f'npzs/self_supervision_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}full_{exclude_class}.npz'
        # ood_savefile_name_kl_div = f'npzs/self_supervision_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_kl_div_{exclude_class}.npz'
        # ood_savefile_name_rot_score = f'npzs/self_supervision_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_rot_score_{exclude_class}.npz'
        ood_savefile_name_full = f'npzs/self_supervision_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_full_{exclude_class}.npz'

    auc, fpr, acc = _score_npzs(ind_full, ood_full, threshold)

    # np.savez(ind_savefile_name_kl_div, ind_kl_div)
    # np.savez(ind_savefile_name_rot_score, ind_rot_score)
    np.savez(ind_savefile_name_full, ind_full)
    # np.savez(ood_savefile_name_kl_div, ood_kl_div)
    # np.savez(ood_savefile_name_rot_score, ood_rot_score)
    np.savez(ood_savefile_name_full, ood_full)
    # print('###############################################')
    # print()
    # print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name_kl_div} and out-distribution ood scores to {ood_savefile_name_kl_div}')
    # print()
    # print('###############################################')
    # print()
    # print(f"Self-Supervision results (KL-Divergence) on {ind_dataset} (In) vs {ood_dataset}:")
    # print(f'Area Under Receiver Operating Characteristic curve: {auc_kl_div}')
    # print(f'False Positive Rate @ 95% True Positive Rate: {fpr_kl_div}')
    # print('###############################################')
    # print()
    # print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name_rot_score} and out-distribution ood scores to {ood_savefile_name_rot_score}')
    # print()
    # print('###############################################')
    # print()
    # print(f"Self-Supervision results (Rotation Score) on {ind_dataset} (In) vs {ood_dataset}:")
    # print(f'Area Under Receiver Operating Characteristic curve: {auc_rot_score}')
    # print(f'False Positive Rate @ 95% True Positive Rate: {fpr_rot_score}')
    print('###############################################')
    print()
    print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name_full} and out-distribution ood scores to {ood_savefile_name_full}')
    print()
    print('###############################################')
    print()
    print(f"Self-Supervision results on {ind_dataset} (In) vs {ood_dataset} with Val Set {val_dataset}:")
    print(f'Area Under Receiver Operating Characteristic curve: {auc}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fpr}')
    print(f'OOD Detection Accuracy: {acc}')


def _process_gen_odin(model, images, epsilon, criterion=nn.CrossEntropyLoss()):

    model.eval()
    inputs = Variable(images.to(device), requires_grad=True)
    outputs, _, _ = model(inputs)
    nnOutputs = outputs.data.cpu()
    nnOutputs = nnOutputs.numpy()
    nnOutputs = nnOutputs - np.max(nnOutputs, axis=1).reshape(nnOutputs.shape[0], 1)
    nnOutputs = np.exp(nnOutputs)/np.sum(np.exp(nnOutputs), axis=1).reshape(nnOutputs.shape[0], 1)

    maxIndexTemp = np.argmax(nnOutputs, axis=1)
    labels = Variable(torch.LongTensor([maxIndexTemp]).to(device))
    loss = criterion(outputs, labels[0])
    loss.backward()

    gradient = torch.ge(inputs.grad.data, 0)
    gradient = (gradient.float() - 0.5) * 2

    tempInputs = torch.add(inputs.data,  -epsilon, gradient)
    o, h, g = model(Variable(tempInputs))

    return np.max(o.detach().cpu().numpy(), axis=1), np.max(h.detach().cpu().numpy(), axis=1), g.detach().cpu().numpy()


def _process_gen_odin_loader(model, loader, device, epsilon):

    len_ = 0
    max_h = np.zeros(loader.batch_size*loader.__len__())
    for index, data in enumerate(loader):

        images, _ = data
        images = images.to(device)
        o, h, _ = _process_gen_odin(model, images, epsilon)

        max_h[index*loader.batch_size:index*loader.batch_size + o.shape[0]] = h
        len_ += o.shape[0]

    max_h = max_h[:len_]
    return max_h


def _gen_odin_inference(model, loaders, device, ind_dataset, val_dataset, ood_dataset, exclude_class=None):

    model.eval()
    val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader = loaders
    epsilons = [0, 0.0025, 0.005, 0.01, 0.02, 0.04, 0.08]

    best_auc, best_epsilon = 0, 0
    for epsilon in epsilons:

        val_ind_scores = _process_gen_odin_loader(model, val_ind_loader, device, epsilon)
        val_ood_scores = _process_gen_odin_loader(model, val_ood_loader, device, epsilon)

        auc, _, _ = _score_npzs(val_ind_scores, val_ood_scores, threshold=0)
        if auc > best_auc:
            best_auc = auc
            best_epsilon = epsilon
            best_val_ind_scores = val_ind_scores
            best_val_ood_scores = val_ood_scores

    _, threshold = _find_threshold(best_val_ind_scores, best_val_ood_scores)

    test_ind_scores = _process_gen_odin_loader(model, test_ind_loader, device, best_epsilon)
    test_ood_scores = _process_gen_odin_loader(model, test_ood_loader, device, best_epsilon)

    if exclude_class is None:
        max_h_ind_savefile_name = f'npzs/max_h_gen_odin_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}.npz'
        max_h_ood_savefile_name = f'npzs/max_h_gen_odin_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}.npz'
    else:
        max_h_ind_savefile_name = f'npzs/max_h_gen_odin_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_{exclude_class}.npz'
        max_h_ood_savefile_name = f'npzs/max_h_gen_odin_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_{exclude_class}.npz'

    np.savez(max_h_ind_savefile_name, test_ind_scores)
    np.savez(max_h_ood_savefile_name, test_ood_scores)
    auc, fpr, acc = _score_npzs(test_ind_scores, test_ood_scores, threshold)

    print('###############################################')
    print()
    print(f'Succesfully stored in-distribution ood scores for maximum h to {max_h_ind_savefile_name} and out-distribution ood scores to {max_h_ood_savefile_name}')
    print()
    print('###############################################')
    print()
    print(f"Generalized-Odin results (sigmoid) on {ind_dataset} (In) vs {ood_dataset} (Out) with Val Dataset {val_dataset}:")
    print(f'Area Under Receiver Operating Characteristic curve: {auc}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fpr}')
    print(f'Detection Accuracy: {acc}')


def _ensemble_inference(model_checkpoints, loaders, device, out_classes, ind_dataset, val_dataset, ood_dataset, T=1000, epsilon=0.002, scaling=True):

    val_ind_loader, test_ind_loader, val_ood_loader, test_ood_loader = loaders
    index = 0
    for model_checkpoint in tqdm(model_checkpoints):
        model = build_model_with_checkpoint('eb0', model_checkpoint, device, out_classes=out_classes)
        model.eval()
        if scaling:
            if index == 0:
                val_ind = _get_odin_scores(model, val_ind_loader, T, epsilon, device=device, score_entropy=True)
                val_ood = _get_odin_scores(model, val_ood_loader, T, epsilon, device=device, score_entropy=True)
            else:
                val_ind += _get_odin_scores(model, val_ind_loader, T, epsilon, device=device, score_entropy=True)
                val_ood += _get_odin_scores(model, val_ood_loader, T, epsilon, device=device, score_entropy=True)
        else:
            if index == 0:
                val_ind = _get_odin_scores(model, val_ind_loader, T=1, epsilon=0, device=device, score_entropy=True)
                val_ood = _get_odin_scores(model, val_ood_loader, T=1, epsilon=0, device=device, score_entropy=True)
            else:
                val_ind += _get_odin_scores(model, val_ind_loader, T=1, epsilon=0, device=device, score_entropy=True)
                val_ood += _get_odin_scores(model, val_ood_loader, T=1, epsilon=0, device=device, score_entropy=True)
        index += 1

    val_ind = val_ind / (index-1)
    val_ood = val_ood / (index-1)

    _, threshold = _find_threshold(val_ind, val_ood)

    if scaling:
        ind = _get_odin_scores(model, test_ind_loader, T=T, epsilon=epsilon, device=device, score_entropy=True)
        ood = _get_odin_scores(model, test_ood_loader, T=T, epsilon=epsilon, device=device, score_entropy=True)
    else:
        ind = _get_odin_scores(model, test_ind_loader, T=1, epsilon=0, device=device, score_entropy=True)
        ood = _get_odin_scores(model, test_ood_loader, T=1, epsilon=0, device=device, score_entropy=True)

    ind = ind / (index-1)
    ood = ood / (index-1)

    if scaling:
        ind_savefile_name = f'npzs/ensemble_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_scaling.npz'
        ood_savefile_name = f'npzs/ensemble_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}_scaling.npz'
    else:
        ind_savefile_name = f'npzs/ensemble_{ind_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}.npz'
        ood_savefile_name = f'npzs/ensemble_{ood_dataset}_ind_{ind_dataset}_val_{val_dataset}_ood_{ood_dataset}.npz'

    auc, fpr, acc = _score_npzs(ind, ood, threshold)

    np.savez(ind_savefile_name, ind)
    np.savez(ood_savefile_name, ood)

    print('###############################################')
    print()
    print(f'Succesfully stored in-distribution ood scores to {ind_savefile_name} and out-distribution ood scores to {ood_savefile_name}')
    print()
    print('###############################################')
    print()
    print(f"Self-Ensemble results on {ind_dataset} (In) vs {ood_dataset} (Out) with Val Set {val_dataset}:")
    print(f'Area Under Receiver Operating Characteristic curve: {auc}')
    print(f'False Positive Rate @ 95% True Positive Rate: {fpr}')
    print(f'Detection Accuracy: {acc}')


if __name__ == '__main__':

    import time
    start = time.time()

    parser = argparse.ArgumentParser(description='Out-of-Distribution Detection')

    parser.add_argument('--ood_method', '--m', required=True)
    parser.add_argument('--num_classes', '--nc', type=int, required=True)
    parser.add_argument('--in_distribution_dataset', '--in', required=True)
    parser.add_argument('--val_dataset', '--val', required=True)
    parser.add_argument('--model_checkpoint', '--mc', default=None, required=False)
    parser.add_argument('--model_checkpoints_file', '--mcf', default=None, required=False)
    parser.add_argument('--monte_carlo_steps', '--mcdo', type=int, default=1, required=False)
    parser.add_argument('--batch_size', '--bs', type=int, default=32, required=False)
    parser.add_argument('--device', '--dv', type=int, default=0, required=False)

    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0, 1, 2, 3, 4, 5, 6, 7"

    args = parser.parse_args()
    device = torch.device(f'cuda:{args.device}')

    ood_method = args.ood_method.lower()

    if args.model_checkpoint is None and args.model_checkpoints_file is None:
        raise NotImplementedError('You need to specify either a single or multiple checkpoints')
    elif args.model_checkpoint is not None:
        if ood_method == 'self-supervision' or ood_method == 'selfsupervision' or ood_method =='self_supervision' or ood_method =='rotation':
            model = build_model_with_checkpoint('roteb0', args.model_checkpoint, device=device, out_classes=args.num_classes)
        elif ood_method == 'generalized-odin' or ood_method == 'generalizedodin':
            model = build_model_with_checkpoint('geneb0', args.model_checkpoint, device=device, out_classes=args.num_classes)
        else:
            model = build_model_with_checkpoint('eb0', args.model_checkpoint, device=device, out_classes=args.num_classes)
    else:
        model_checkpoints = []
        for line in open(args.model_checkpoints_file, 'r'):
            model_checkpoints.append(line.split('\n')[0])

    ind_dataset = args.in_distribution_dataset.lower()
    val_dataset = args.val_dataset.lower()
    all_datasets = ['cifar10', 'cifar100', 'svhn', 'stt', 'tinyimagenet']
    all_datasets.remove(ind_dataset)
    all_datasets.remove(val_dataset)
    ood_dataset_1, ood_dataset_2, ood_dataset_3 = all_datasets
    
    loaders = get_ood_loaders(batch_size=args.batch_size, ind_dataset=args.in_distribution_dataset, val_ood_dataset=args.val_dataset, test_ood_dataset=args.out_distribution_dataset)
    if args.val_dataset == 'fgsm':
        if args.fgsm_checkpoint is not None:
            if args.fgsm_classes is None:
                fgsm_classes = args.num_classes
            else:
                fgsm_classes = args.fgsm_classes
            fgsm_model = build_model_with_checkpoint('eb0', args.fgsm_checkpoint, device=device, out_classes=fgsm_classes)
        else:
            from copy import deepcopy
            fgsm_model = deepcopy(model)
        if not os.path.exists(f'{args.val_dataset}_fgsm_loader_{ood_method}.pth'):
            fgsm_loader = _create_fgsm_loader(fgsm_model, loaders[1], device)
            torch.save(fgsm_loader, f'{args.val_dataset}_fgsm_loader_{ood_method}.pth')
        else:
            fgsm_loader = torch.load(f'{args.val_dataset}_fgsm_loader_{ood_method}.pth')
        loaders[-2] = fgsm_loader

    if ood_method == 'baseline':
        method_loaders = loaders[1:]
        _baseline(model, method_loaders, ind_dataset=args.in_distribution_dataset, val_dataset=args.val_dataset, ood_dataset=args.out_distribution_dataset, monte_carlo_steps=args.monte_carlo_steps, exclude_class=args.exclude_class, device=device)
    elif ood_method == 'odin':
        method_loaders = loaders[1:]
        _odin(model, method_loaders, device, ind_dataset=args.in_distribution_dataset, val_dataset=args.val_dataset, ood_dataset=args.out_distribution_dataset, exclude_class=args.exclude_class)
    elif ood_method == 'mahalanobis':
        _generate_Mahalanobis(model, loaders=loaders, ind_dataset=args.in_distribution_dataset, val_dataset=args.val_dataset, ood_dataset=args.out_distribution_dataset, num_classes=args.num_classes, exclude_class=args.exclude_class, device=device)
    elif ood_method == 'self-supervision' or ood_method =='selfsupervision' or ood_method =='self_supervision' or ood_method =='rotation':
        method_loaders = loaders[1:]
        _rotation(model, method_loaders, ind_dataset=args.in_distribution_dataset, val_dataset=args.val_dataset, ood_dataset=args.out_distribution_dataset, num_classes=args.num_classes, exclude_class=args.exclude_class, device=device)
    elif ood_method == 'generalized-odin' or ood_method == 'generalizedodin':
        method_loaders = loaders[1:]
        _gen_odin_inference(model, method_loaders, device, ind_dataset=args.in_distribution_dataset, val_dataset=args.val_dataset, ood_dataset=args.out_distribution_dataset, exclude_class=args.exclude_class)
    elif ood_method == 'ensemble':
        method_loaders = loaders[1:]
        _ensemble_inference(model_checkpoints, method_loaders, device, out_classes=args.num_classes, ind_dataset=args.in_distribution_dataset, val_dataset=args.val_dataset, ood_dataset=args.out_distribution_dataset)
    else:
        raise NotImplementedError('Requested unknown Out-of-Distribution Detection Method')

    end = time.time()
    hours, rem = divmod(end-start, 3600)
    minutes, seconds = divmod(rem, 60)
    print("{:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))