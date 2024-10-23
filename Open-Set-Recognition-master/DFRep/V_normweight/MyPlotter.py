import torch
import torch.nn as nn
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os
import torch.nn.functional as F
from tqdm import tqdm


def plot_feature(net, args, plotloader, device, dirname, epoch=0, plot_class_num=10, plot_quality=150, testmode=False):
    plot_features = []
    plot_labels = []
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(plotloader):
            inputs, targets = inputs.to(device), targets.to(device)
            out = net(inputs)
            embed_fea = out["embed_fea"]
            # embed_fea = F.normalize(embed_fea, dim=1, p=2)
            try:
                embed_fea = embed_fea.data.cpu().numpy()
                targets = targets.data.cpu().numpy()
            except:
                embed_fea = embed_fea.data.numpy()
                targets = targets.data.numpy()

            plot_features.append(embed_fea)
            plot_labels.append(targets)

    plot_features = np.concatenate(plot_features, 0)
    plot_labels = np.concatenate(plot_labels, 0)

    net_dict = net.state_dict()
    centroids = net_dict['module.centroids'] if isinstance(net, nn.DataParallel) else net_dict['centroids']
    centroids = F.normalize(centroids, dim=1, p=2)
    try:
        centroids = centroids.data.cpu().numpy()
    except:
        centroids = centroids.data.numpy()
    # print(centroids)
    colors = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9']
    for label_idx in range(plot_class_num):
        features = plot_features[plot_labels == label_idx, :]
        plt.scatter(
            features[:, 0],
            features[:, 1],
            c=colors[label_idx],
            s=1,
        )
    plt.scatter(
        centroids[:, 0],
        centroids[:, 1],
        c='black',
        marker="*",
        s=5,
    )

    # plot beam
    for i in range(args.train_class_num):
        xx = centroids[i, 0]
        yy = centroids[i, 1]
        plot_beam(xx, yy, plt, colors[i])


    # currently only support 10 classes, for a good visualization.
    # change plot_class_num would lead to problems.
    legends = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    if testmode:
        legends[plot_class_num] = 'unkown'
    plt.legend(legends[0:plot_class_num] + ['center'], loc='upper right')

    save_name = os.path.join(dirname, 'epoch_' + str(epoch) + '.png')
    plt.savefig(save_name, bbox_inches='tight', dpi=plot_quality)
    plt.close()


def plot_beam(x, y, plt, color):
    x_min, x_max = plt.xlim()
    y_min, y_max = plt.ylim()
    temp_x = x_min if x<0 else x_max
    slope = y/x
    input = np.linspace(0, temp_x, 100)
    output = slope*input
    plt.plot(input, output,c=color)
    plt.xlim(x_min, x_max)
    plt.ylim(y_min, y_max)

