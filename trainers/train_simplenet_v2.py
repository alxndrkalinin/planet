from torch.nn import *
from util import *
from torch import optim
from planet_models.simplenet_v2 import SimpleNetV2
from PIL import Image
import random
from planet_models.simplenet_v3 import SimpleNetV3
from datasets import *
import torch


name = 'simplenet_v3.1'
is_cuda_availible = torch.cuda.is_available()


class RandomVerticalFLip(object):
    def __call__(self, img):
        if random.random() < 0.5:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return img


def adjust_lr(optimizer, rate):
    for param_group in optimizer.param_groups:
        if param_group['lr'] >= 1e-5:
            param_group['lr'] = param_group['lr'] * rate


def train_simplenet_v2_forest(epoch=50):
    # try SGD instead of ADAM
    criterion = MultiLabelSoftMarginLoss()
    net = SimpleNetV3()
    logger = Logger('../log/', name)
    optimizer = optim.Adam(lr=5e-4, params=net.parameters())
    net.cuda()
    net = torch.nn.DataParallel(net, device_ids=[0, 1])
    # resnet.load_state_dict(torch.load('../models/simplenet_v3.pth'))
    train_data_set = train_jpg_loader(256, transform=Compose(
        [

            Scale(77),
            RandomHorizontalFlip(),
            RandomVerticalFLip(),
            RandomCrop(72),
            ToTensor(),
            Normalize(mean, std)
        ]
    ))
    validation_data_set = validation_jpg_loader(64, transform=Compose(
        [
            Scale(72),
            ToTensor(),
            Normalize(mean, std)
         ]
    ))
    best_loss = np.inf
    patience = 0
    for i in range(epoch):
        # training
        training_loss = 0.0
        for batch_index, (target_x, target_y) in enumerate(train_data_set):
            if is_cuda_availible:
                target_x, target_y = target_x.cuda(), target_y.cuda()
            net.train()
            target_x, target_y = Variable(target_x), Variable(target_y)
            optimizer.zero_grad()
            output = net(target_x)
            loss = criterion(output, target_y)
            training_loss += loss.data[0]
            loss.backward()
            optimizer.step()
            if batch_index % 50 == 0:
                print('Training loss is {}'.format(loss.data[0]))
        print('Finished epoch {}'.format(i))
        training_loss /= batch_index
        # evaluating
        val_loss = 0.0
        net.eval()
        preds = []
        targets = []
        for batch_index, (val_x, val_y) in enumerate(validation_data_set):
            if is_cuda_availible:
                val_y = val_y.cuda()
            val_y = Variable(val_y, volatile=True)
            val_output = evaluate(net, val_x)
            val_loss += criterion(val_output, val_y)
            val_output = F.sigmoid(val_output)
            binary_y = val_output.data.cpu().numpy()
            binary_y[binary_y > 0.2] = 1
            binary_y[binary_y <= 0.2] = 0
            preds.append(binary_y)
            targets.append(val_y.data.cpu().numpy())
        targets = np.concatenate(targets)
        preds = np.concatenate(preds)
        f2_scores = f2_score(targets, preds)
        val_loss = val_loss.data[0]/batch_index
        if best_loss > val_loss:
            print('Saving model...')
            best_loss = val_loss
            torch.save(net.state_dict(), '../models/{}.pth'.format(name))
            patience = 0
        else:
            adjust_lr(optimizer, 0.8)
            patience += 1
            print('Patience: {}'.format(patience))
            print('Best loss {}, previous loss {}'.format(best_loss, val_loss))

        print('Evaluation loss is {}, Training loss is {}'.format(val_loss, training_loss))
        print('F2 Score is %s' % (f2_scores))

        if patience >= 20:
            print('Early stopping!')
            break

        logger.add_record('train_loss', loss.data[0])
        logger.add_record('evaluation_loss', val_loss)
        logger.add_record('f2_score', f2_scores)
    logger.save()
    logger.save_plot()


if __name__ == '__main__':
    train_simplenet_v2_forest(epoch=500)

