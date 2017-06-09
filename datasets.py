import os
import time
import pandas as pd
from torch.utils.data import Dataset, DataLoader
from torchvision.transforms import *
from labels import *
from spectral import *
import numpy as np
from skimage import io
from sklearn.preprocessing import MinMaxScaler
import cv2

mean = [0.31151703, 0.34061992, 0.29885209]
std = [0.16730586, 0.14391145, 0.13747531]


class RandomVerticalFlip(object):
    def __call__(self, img):
        if random.random() < 0.5:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        return img


class RandomTranspose(object):
    def __call__(self, img):
        if random.random() < 0.5:
            img = np.array(img)
            img = img.transpose(1, 0, 2)
            img = Image.fromarray(img)
        return img


class RandomRotate(object):
    def __call__(self, img):
        if random.random() < 0.2:
            img = np.array(img)
            angle = np.random.randint(-45, 45)
            height, width = img.shape[0:2]
            mat = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
            img = cv2.warpAffine(img, mat, (height, width), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            img = Image.fromarray(img)
        return img


def is_image_file(filename):
    return any(filename.endswith(extension) for extension in ['.png', 'jpg', '.jpeg'])


def calc_ndwi(image):
    """
    calculate normalized difference water index
    input image is of the format(NIR, R, G)
    """
    return (image[:, :, 2] - image[:, :, 0]) / (image[:, :, 2] + image[:, :, 0] + 1e-8)


def scale(img):
    rescaleIMG = np.reshape(img, (-1, 1))
    scaler = MinMaxScaler(feature_range=(0, 255))
    rescaleIMG = scaler.fit_transform(rescaleIMG) # .astype(np.float32)
    img_scaled = (np.reshape(rescaleIMG, img.shape))
    return img_scaled


def load_img(filepath):
    """
        This function reads two types of image:
            1. If it is a .jpg, it uses PIL to open and read.
            2. If it is a .tif, it uses tifffile to open it.
    """
    np.seterr(all='warn')

    if is_image_file(filepath):
        image = Image.open(filepath)
        image = image.convert('RGB')
    elif '.tif' in filepath:
        tif_image = io.imread(filepath)
        image = np.empty_like(tif_image).astype(np.int32)
        # RGB image
        rgb = scale(get_rgb(tif_image, (2, 1, 0)))
        # NIR-R-G image
        nrg = get_rgb(tif_image, (3, 2, 1))
        ndwi = calc_ndwi(nrg)
        image[:, :, :3] = rgb
        image[:, :, -1] = ndwi * 255.0
        image = Image.fromarray(image.astype('uint8'))
    else:
        raise OSError('File is not either a .tif file or an image file.')
    return image


def input_transform(crop_size):
    return Compose(
        [
            RandomCrop(crop_size),
            RandomHorizontalFlip(),
            ToTensor(),
        ]
    )


class PlanetDataSet(Dataset):
    def __init__(self, image_dir, label_dir=None, num_labels=17, mode='Train', input_transform=ToTensor(),
                 target_transform=None, tif=False):
        super(PlanetDataSet, self).__init__()
        self.mode = mode
        self.tif = tif
        self.images = []
        suffix = '.jpg' if tif is False else '.tif'
        print('[*]Loading Dataset {}'.format(image_dir))
        t = time.time()
        if mode == 'Train' or mode == 'Validation':
            self.targets = []
            self.labels = pd.read_csv(label_dir)
            image_names = pd.read_csv('../dataset/train.csv' if mode == 'Train' else '../dataset/validation.csv')
            image_names = image_names.as_matrix().flatten()
            self.image_filenames = image_names
            for image in image_names:
                str_target = self.labels.loc[self.labels['image_name'] == image]
                image = os.path.join(image_dir, '{}{}'.format(image, suffix))
                target = np.zeros(num_labels, dtype=np.float32)
                target_index = [label_to_idx[l] for l in str_target['tags'].values[0].split(' ')]
                target[target_index] = 1
                image = load_img(image)
                self.images.append(image)
                self.targets.append(target)
        elif mode == 'Test':
            self.image_filenames = sorted([os.path.join(image_dir, filename) for filename in os.listdir(image_dir)
                                           if is_image_file(filename)])
            for image in self.image_filenames:
                image = load_img(image)
                self.images.append(image)

        print('[*]Dataset loading completed, total time elisped {}'.format(time.time() - t))
        print('[*]Total number of data is {}'.format(len(self)))
        self.input_transform = input_transform
        self.target_transform = target_transform

    def mean_std(self):
        mean = []
        std = []
        images = np.stack([np.asarray(image) for image in self.images]).astype(np.float32)
        for i in range(0, 4 if self.tif else 3):
            images[:, :, :, i] = images[:, :, :, i]/255.
            mean.append(images[:, :, :, i].mean())
            std.append(images[:, :, :, i].std())
        return mean, std

    def __getitem__(self, index):
        if self.mode == 'Test':
            image = load_img(self.image_filenames[index])
            if '.tif' in self.image_filenames[index]:
                im_id = self.image_filenames[index].split('/')[-1].strip('.tif')
            else:
                im_id = self.image_filenames[index].split('/')[-1].strip('.jpg')
            if self.input_transform is not None:
                image = self.input_transform(image)
            return image, im_id
        else:
            image = self.images[index]
            target = self.targets[index]
            if self.input_transform is not None:
                image = self.input_transform(image)
            return image, torch.from_numpy(target)

    def __len__(self):
        return len(self.image_filenames)


def train_tif_loader(batch_size=64, transform=ToTensor()):
    dataset = PlanetDataSet(
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train-tif-v2',
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train.csv',
        mode='Train',
        input_transform=transform,
        tif=True
    )
    return DataLoader(dataset=dataset, batch_size=batch_size, shuffle=True, )


def validation_tif_loader(batch_size=64, transform=ToTensor()):
    dataset = PlanetDataSet(
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train-tif-v2',
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train.csv',
        mode='Validation',
        input_transform=transform,
        tif=True
    )
    return DataLoader(dataset=dataset, batch_size=batch_size, shuffle=True, )


def test_tif_loader(batch_size=64, transform=ToTensor()):
    dataset = PlanetDataSet(
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/test/test-tif',
        mode='Test',
        input_transform=transform,
        tif=True
    )
    return DataLoader(dataset=dataset, batch_size=batch_size, shuffle=True, )


def train_jpg_loader(batch_size=64, transform=ToTensor()):
    dataset = PlanetDataSet(
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train-jpg',
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train.csv',
        mode='Train',
        input_transform=transform
    )
    return DataLoader(dataset=dataset, batch_size=batch_size, shuffle=True, num_workers=3)


def validation_jpg_loader(batch_size=64, transform=ToTensor()):
    dataset = PlanetDataSet(
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train-jpg',
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train.csv',
        mode='Validation',
        input_transform=transform
    )
    return DataLoader(dataset=dataset, batch_size=batch_size, shuffle=False, num_workers=3)


def test_jpg_loader(batch_size=128, transform=ToTensor()):
    dataset = PlanetDataSet(
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/test/test-jpg',
        mode='Test',
        input_transform=transform
    )
    return DataLoader(dataset=dataset, batch_size=batch_size, shuffle=False)


if __name__ == '__main__':
    dd = PlanetDataSet(        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train-jpg',
        '/media/jxu7/BACK-UP/Data/AmazonPlanet/train/train.csv',
        mode='Train')
    print(dd.mean_std())
