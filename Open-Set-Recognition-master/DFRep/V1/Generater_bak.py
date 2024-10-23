import torch
import numpy as np
import torch.nn.functional as F
from random import shuffle
from math import ceil


def generater_input(inputs, targets, args, repeats=4, reduce=16):
    b, c, w, h = inputs.shape
    if b != args.bs:
        return inputs, targets
    g_data = inputs.repeat(repeats, 1, 1, 1)  # repeat examples 3 times [n*sampler, c]
    g_data = g_data[torch.randperm(g_data.size()[0])]
    g_data = g_data.view(-1, b // reduce, c, w, h)
    g_data = g_data.mean(dim=0, keepdim=False)
    g_label = args.train_class_num * torch.ones(b // reduce, dtype=targets.dtype)
    inputs = torch.cat([inputs, g_data], dim=0)
    targets = torch.cat([targets, g_label], dim=0)

    r = torch.randperm(inputs.size()[0])
    inputs = inputs[r]
    targets = targets[r]
    return inputs, targets


def generater_unknown(inputs, targets, args, repeats=4, reduce=16):
    b, c, w, h = inputs.shape

    number = b // reduce if b == args.bs else b

    g_data = inputs.repeat(repeats, 1, 1, 1)  # repeat examples 3 times [n*sampler, c]
    g_data = g_data[torch.randperm(g_data.size()[0])]
    g_data = g_data.view(-1, number, c, w, h)
    g_data = g_data.mean(dim=0, keepdim=False)
    return g_data


def generater_gap(gap, batchsize=32):
    # generated a random gap doesn't require gradient
    b, c = gap.size()
    mem = gap.clone().detach()
    mem = mem.view(-1)
    mem = mem[torch.randperm(mem.size()[0])]
    mem = mem.view([b, c])
    if batchsize < b:
        mem = mem[:batchsize]
    mem = mem.to(gap.device)
    return mem


def generater_gap2(gap):
    # generated a random gap doesn't require gradient
    b, c = gap.size()
    mem = gap.clone().detach()
    mem = mem.view(-1)
    mem = mem[torch.randperm(mem.size()[0])]
    mem = mem.view([b, c])

    mem = mem.to(gap.device)
    # directly passing the gradient.
    generate = gap + mem - gap
    return generate


def generater_gap3(gap, shuffle_rate=2):
    # generated a random gap doesn't require gradient
    b, c = gap.size()
    mem = gap.clone().detach()
    mem = mem.permute(1, 0)  # c,b
    mem = mem.tolist()
    selected_num = max(4, c // shuffle_rate)
    selected_channels = torch.empty(selected_num, dtype=torch.long).random_(c)
    for i in selected_channels:
        m = mem[i]
        shuffle(m)
        mem[i] = m

    mem = torch.Tensor(mem)
    mem = mem.permute(1, 0)
    mem = mem.to(gap.device)
    # directly passing the gradient.
    generate = gap + mem - gap
    return generate


def generater_gap4(gap):
    # generated a random gap doesn't require gradient
    b, c = gap.size()
    mem = gap.clone().detach()
    mem = mem.permute(1, 0)
    rand = torch.rand(c, b)
    rand_perm = rand.argsort(dim=1)
    rand_perm = (torch.arange(0, c) * b).unsqueeze(dim=-1) + rand_perm
    rand_perm = rand_perm.view(-1)
    mem = mem.reshape(-1)
    mem = mem[rand_perm]
    mem = mem.reshape([c, b]).permute(1, 0)
    mem = mem.to(gap.device)
    generate = gap + mem - gap
    return generate


def generater_gap5(gap, ratio=0.7):
    # generated a random gap doesn't require gradient
    b, c = gap.size()
    mem = gap.clone().detach()
    mem = mem.permute(1, 0)
    shuffle_c = int(c*ratio)
    rand_perm = torch.rand(shuffle_c, b)
    rand_perm = rand_perm.argsort(dim=1)
    supp = torch.arange(0, b).unsqueeze(dim=0).expand(c - shuffle_c, b)
    rand_perm = torch.cat([rand_perm,supp],dim=0)
    rand_perm = rand_perm[torch.randperm(c)]
    rand_perm = (torch.arange(0, c) * b).unsqueeze(dim=-1) + rand_perm
    rand_perm = rand_perm.view(-1)
    mem = mem.reshape(-1)
    mem = mem[rand_perm]
    mem = mem.reshape([c, b]).permute(1, 0)
    mem = mem.to(gap.device)
    generate = gap + mem - gap
    return generate


def demo_shuffle():
    b = 5
    c = 10
    gap = torch.arange(1, b + 1, dtype=float).unsqueeze(dim=-1).expand(b, c)
    print(gap)
    gap.requires_grad = True

    generate = generater_gap5(gap)

    print(generate)
    print(generate.requires_grad)

# demo_shuffle()


def CGD_estimator(gap_results):
    "Conditional Gaussian distribution"
    channel_mean = gap_results["channel_mean_all"]  # [class_number, channel]
    channel_std = gap_results["channel_std_all"]  # [class_number, channel]

    channel_mean_mean = channel_mean.mean(dim=0)
    channel_mean_std = channel_mean.std(dim=0)
    channel_std_mean = channel_std.mean(dim=0)
    channel_std_std = channel_std.std(dim=0)

    return {
        "channel_mean": channel_mean,
        "channel_std": channel_std,
        "channel_mean_mean": channel_mean_mean,
        "channel_mean_std": channel_mean_std,
        "channel_std_mean":channel_std_mean,
        "channel_std_std":channel_std_std
    }


def estimator_generator(estimator, gap):
    channel_mean_mean = estimator["channel_mean_mean"]
    channel_mean_std = estimator["channel_mean_std"]
    # channel_std_mean = estimator["channel_std_mean"]
    # channel_std_std = estimator["channel_std_std"]
    # estimator_class = estimator["estimator_class"]
    # estimator_batch = estimator["estimator_batch"]
    channel = channel_mean_mean.size()[0]


    data = torch.randn(gap.size()[0],channel).to(gap.device)
    data = (data - data.mean(dim=0,keepdim=True))/(data.std(dim=0,keepdim=True))
    data = data*channel_mean_std +channel_mean_mean
    data = data.clone().detach()
    # data = gap + data - gap
    return data



def whitennoise_generator(estimator, gap):
    batch_size=gap.size()[0]
    channel_mean = estimator["channel_mean"]
    channel_std = estimator["channel_std"]
    class_num,channel_num= channel_mean.size()


    n = max(ceil(batch_size/class_num),3)
    noise = torch.randn(n,class_num*channel_num).to(gap.device)
    channel_mean = channel_mean.view(-1)
    channel_std = channel_std.view(-1)
    noise = (noise - noise.mean(dim=0,keepdim=True))/(noise.std(dim=0,keepdim=True))
    noise = noise*channel_std +channel_mean

    noise = noise.reshape([n, class_num, channel_num])
    noise = noise.reshape([n*class_num, channel_num])
    noise = noise[torch.randperm(noise.size()[0])]
    noise = noise[0:batch_size]
    generate = 0.5*noise+0.5*gap
    generate = generate.clone().detach()
    # data = gap + data - gap
    return generate


def guassian_generator(estimator, gap):

    channel_mean = estimator["channel_mean"]
    channel_std = estimator["channel_std"]
    channel_mean_mean = estimator["channel_mean_mean"]
    channel_mean_std = estimator["channel_mean_std"]
    channel_std_std = estimator["channel_std_std"]
    class_num, channel_num = channel_mean.size()
    batch_size = gap.size()[0]

    noise = torch.randn(batch_size, channel_num).to(gap.device)
    noise = (noise - noise.mean(dim=0, keepdim=True)) / (noise.std(dim=0, keepdim=True))
    noise = noise * channel_mean_std + channel_mean_mean

    generate = 1.0 * noise + 0.0 * gap
    generate = generate.clone().detach()
    # data = gap + data - gap
    return generate



def demoestimator():
    filepath = "/Users/melody/Downloads/gap.pkl"
    DICT = torch.load(filepath,map_location=torch.device('cpu'))
    estimator = CGD_estimator(DICT)
    guassian_generator(estimator,torch.rand(256,1152))

# demoestimator()

"""--------------------------------------------"""


class CGDestimator():
    def __init__(self, stat):
        super(CGDestimator, self).__init__()
        self.mean = stat["mean"]  # [class_number, channel]
        self.std = stat["std"]

    def generator(self, gap):

        batch_size = gap.shape[0]
        class_num, channel_num = self.mean.size()

        n = max(ceil(batch_size / class_num), 3)

        noise = torch.randn(n, class_num * channel_num).to(gap.device)
        channel_mean = self.mean.view(-1)
        channel_std = self.std.view(-1)
        noise = (noise - noise.mean(dim=0, keepdim=True)) / (noise.std(dim=0, keepdim=True))
        noise = noise * channel_std + channel_mean

        noise = noise.reshape([n, class_num, channel_num])
        noise = noise.reshape([n * class_num, channel_num])
        noise = noise[torch.randperm(noise.size()[0])]
        noise = noise[0:batch_size]
        noise = noise.clone().detach()
        # data = gap + data - gap

        return noise






def channel_swicher(gap,ratio=0.2):
    # generated a random gap doesn't require gradient
    # generated a random gap doesn't require gradient
    b, c = gap.size()
    mem = gap.clone().detach()
    mem = mem.permute(1, 0)
    shuffle_c = int(c * ratio)
    rand_perm = torch.rand(shuffle_c, b)
    rand_perm = rand_perm.argsort(dim=1)
    supp = torch.arange(0, b).unsqueeze(dim=0).expand(c - shuffle_c, b)
    rand_perm = torch.cat([rand_perm, supp], dim=0)
    rand_perm = rand_perm[torch.randperm(c)]
    rand_perm = (torch.arange(0, c) * b).unsqueeze(dim=-1) + rand_perm
    rand_perm = rand_perm.view(-1)
    mem = mem.reshape(-1)
    mem = mem[rand_perm]
    mem = mem.reshape([c, b]).permute(1, 0)
    mem = mem.to(gap.device)
    generate = gap + mem - gap
    return generate

    return generate
