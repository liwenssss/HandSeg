import os
import torch
from torch.utils.data import DataLoader
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm

import argparse

import sys
sys.path.append('./dataset')
sys.path.append('./model')

from seg_dataset import HandSegDataset
from FCNet import VGGNet, FCN16s

def save():
    seg_data = HandSegDataset(is_train=False)
    data_loader = DataLoader(seg_data, batch_size=4, shuffle=False, num_workers=4)

    vgg_net = VGGNet(pretrained=True)
    model = FCN16s(pretrained_net=vgg_net, n_class=3)
    model.load_state_dict(torch.load('checkpoints/seg_hand.pth'))
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    model.eval()

    root="./results"
    if not os.path.exists(root):
        os.mkdir(root)

    for step, batch in enumerate(tqdm(data_loader, desc='save results ',
                                      total=len(seg_data) // 4,
                                      initial=0), 0):
        item = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}

        predict = model(item['tmp_depth'].to(device))

        for i in range(predict.shape[0]):
            pre_mask = torch.argmax(predict.cpu(), dim=1)[i].numpy()
            name = item['tmp_depth_dir'][i].split('/')[-1]
            save_path = os.path.join(root, name)
            plt.imsave(save_path, pre_mask)


def show():
    seg_data = HandSegDataset(is_train=True)
    data_loader = DataLoader(seg_data, batch_size=4, shuffle=True)

    vgg_net = VGGNet(pretrained=True)
    model = FCN16s(pretrained_net=vgg_net, n_class=3)
    model.load_state_dict(torch.load('checkpoints/seg_hand.pth'))
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    model.eval()

    for item in data_loader:
        plt.subplot(1, 5, 1)
        plt.axis('off')
        rgb = item['rgb'][0]
        rgb = torch.squeeze(rgb).numpy()
        plt.imshow(rgb / 255)

        plt.subplot(1, 5, 2)
        plt.axis('off')
        depth_im = item['depth_im'][0]
        depth_im = torch.squeeze(depth_im).numpy()
        plt.imshow(depth_im)

        tmp_depth = item['tmp_depth']
        tmp_depth = tmp_depth[0,0,:,:].numpy()
        plt.subplot(1,5,3)
        plt.axis('off')
        plt.imshow(tmp_depth)
        # tmp_depth = torch.squeeze(tmp_depth).numpy()
        # plt.subplot(2,3,3)
        # plt.axis('off')
        # plt.imshow(tmp_depth[0])

        predict = model(item['tmp_depth'].to(device))
        pre_mask = torch.argmax(predict.cpu(), dim=1)[0].numpy()
        # pre_seg = predict[0].permute(1, 2, 0)
        # pre_seg = pre_seg.detach().numpy()
        # pre_mask = np.argmax(pre_seg, -1).astype(np.float32)
        plt.subplot(1,5,4)
        plt.axis('off')
        plt.title('predict label')
        plt.imshow(pre_mask)

        mask_im = torch.squeeze(item['mask_im'][0], dim=0).numpy()
        mask_im = mask_im.astype(np.float32)
        plt.subplot(1, 5, 5)
        plt.axis('off')
        plt.title('gt label')
        plt.imshow(mask_im)
        plt.show()

        break


def fast_hist(a, b, n):
    k = (a >= 0) & (a < n)
    return np.bincount(n * a[k].astype(int) + b[k], minlength=n ** 2).reshape(n, n)

def per_class_iu(hist):
    return np.diag(hist) / (hist.sum(1) + hist.sum(0) - np.diag(hist))

def Iou(input,target,classNum, device):
    '''
    :param input: [b,h,w]
    :param target: [b,h,w]
    :param classNum: scalar
    :return:
    '''
    inputTmp = torch.zeros([input.shape[0],classNum,input.shape[1],input.shape[2]]).to(device)
    targetTmp = torch.zeros([target.shape[0],classNum,target.shape[1],target.shape[2]]).to(device)
    input = input.unsqueeze(1)
    target = target.unsqueeze(1)
    inputOht = inputTmp.scatter_(index=input,dim=1,value=1)
    targetOht = targetTmp.scatter_(index=target,dim=1,value=1)
    batchMious = []
    mul = inputOht * targetOht
    for i in range(input.shape[0]):
        ious = []
        for j in range(classNum):
            intersection = torch.sum(mul[i][j])
            union = torch.sum(inputOht[i][j]) + torch.sum(targetOht[i][j]) - intersection + 1e-6
            iou = intersection / union
            ious.append(iou.cpu().numpy())
        miou = np.mean(ious)
        batchMious.append(miou)
    return np.mean(batchMious)


def eval_mIou(device='cpu', batch_size=4):
    seg_data = HandSegDataset(is_train=False)
    data_loader = DataLoader(seg_data, batch_size=batch_size, shuffle=False, num_workers=4)

    vgg_net = VGGNet(pretrained=True)
    model = FCN16s(pretrained_net=vgg_net, n_class=3)
    model.load_state_dict(torch.load('checkpoints/seg_hand.pth'))
    model.to(device)
    mean_iou = []
    for step, batch in enumerate(tqdm(data_loader, desc='eval miou ',
                                      total=len(seg_data) // batch_size,
                                      initial=0), 0):
        item = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}

        gt_label = item['mask_im'].type(torch.LongTensor).to(device)

        predict = model(item['tmp_depth'])
        pred_label = torch.argmax(predict, dim=1)

        # print(gt_label.shape, pred_label.shape)

        miou = Iou(pred_label, gt_label, classNum=3, device=device)
        mean_iou.append(miou)

    print(np.mean(mean_iou))


if __name__ == '__main__':
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(device)

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', default='save', choices=['show', 'save', 'miou'], type=str)
    args = parser.parse_args()
    if (args.mode == 'show'):
        show()
    if (args.mode == 'save'):
        save()
    if (args.mode == 'miou'):
        eval_mIou(device=device)