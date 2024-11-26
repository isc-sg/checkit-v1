import math
import sys

import numpy as np
import cv2

__version__ = 2.1

def movement(img1, img2):
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    img1 = img1.astype(np.float64)
    img2 = img2.astype(np.float64)
    kernel = cv2.getGaussianKernel(11, 1.5)
    window = np.outer(kernel, kernel.transpose())

    mu1 = cv2.filter2D(img1, -1, window)[32:-32, 32:-32]  # valid
    mu2 = cv2.filter2D(img2, -1, window)[32:-32, 32:-32]
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2
    sigma1_sq = cv2.filter2D(img1 ** 2, -1, window)[32:-32, 32:-32] - mu1_sq
    sigma2_sq = cv2.filter2D(img2 ** 2, -1, window)[32:-32, 32:-32] - mu2_sq
    sigma12 = cv2.filter2D(img1 * img2, -1, window)[32:-32, 32:-32] - mu1_mu2

    movement_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / ((mu1_sq + mu2_sq + c1) *
                                                                (sigma1_sq + sigma2_sq + c2))
    return movement_map.mean()


def calculate_movement(img1, img2):
    if not img1.shape == img2.shape:
        raise ValueError('Input images must have the same dimensions.')
    if img1.ndim == 2:
        return movement(img1, img2)
    elif img1.ndim == 3:
        if img1.shape[2] == 3:
            movements = []
            for i in range(3):
                movements.append(movement(img1, img2))
            return np.array(movements).mean()
        elif img1.shape[2] == 1:
            return movement(np.squeeze(img1), np.squeeze(img2))
    else:
        raise ValueError('Wrong input image dimensions.')
