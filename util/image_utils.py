import sys
import os

import cv2
import numpy as np


def normalize_image(image, normalize_type='255'):
    """
    Normalize image

    Parameters
    ----------
    image: numpy array
        The image you want to normalize 
    normalize_type: string
        Normalize type should be chosen from the type below.
        - '255': simply dividing by 255.0
        - '127.5': output range : -1 and 1
        - 'ImageNet': normalize by mean and std of ImageNet
        - 'None': no normalization

    Returns
    -------
    normalized_image: numpy array
    """
    if normalize_type == 'None':
        return image
    elif normalize_type == '255':
        return image / 255.0
    elif normalize_type == '127.5':
        return image / 127.5 - 1.0
    elif normalize_type == 'ImageNet':
        print('[FIXME] Not Implemented Error')
        sys.exit(1)


def load_image(
        image_path,
        image_shape,
        rgb=True,
        normalize_type='255',
        gen_input_ailia=False
):
    """
    Loads the image of the given path, performs the necessary preprocessing,
    and returns it.

    Parameters
    ----------
    image_path: string
        The path of image which you want to load.
    image_shape: (int, int)  (height, width)
        Resizes the loaded image to the size required by the model.
    rgb: bool, default=True
        Load as rgb image when True, as gray scale image when False.
    normalize_type: string
        Normalize type should be chosen from the type below.
        - '255': output range: 0 and 1
        - '127.5': output range : -1 and 1
        - 'ImageNet': normalize by mean and std of ImageNet.
        - 'None': no normalization
    gen_input_ailia: bool, default=False
        If True, convert the image to the form corresponding to the ailia.

    Returns
    -------
    image: numpy array
    """
    # rgb == True --> cv2.IMREAD_COLOR
    # rbg == False --> cv2.IMREAD_GRAYSCALE
    if os.path.isfile(image_path):
        image = cv2.imread(image_path, int(rgb))
    else:
        print(f'[ERROR] {image_path} not found.')
        sys.exit()
    if rgb:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = normalize_image(image, normalize_type)
    image = cv2.resize(image, (image_shape[1], image_shape[0]))

    if gen_input_ailia:
        if rgb:
            image = image.transpose((2, 0, 1))  # channel first
            image = image[np.newaxis, :, :, :]  # (batch_size, channel, h, w)
        else:
            image = image[np.newaxis, np.newaxis, :, :]
    return image


def get_image_shape(image_path):
    tmp = cv2.imread(image_path)
    height, width = tmp.shape[0], tmp.shape[1]
    return height, width


# (ref: https://qiita.com/yasudadesu/items/dd3e74dcc7e8f72bc680)
def draw_texts(img, texts, font_scale=0.7, thickness=2):
    h, w, c = img.shape
    offset_x = 10
    initial_y = 0
    dy = int(img.shape[1] / 15)
    color = (0, 0, 0)  # black

    texts = [texts] if type(texts) == str else texts

    for i, text in enumerate(texts):
        offset_y = initial_y + (i+1)*dy
        cv2.putText(img, text, (offset_x, offset_y), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, color, thickness, cv2.LINE_AA)


def draw_result_on_img(img, texts, w_ratio=0.35, h_ratio=0.2, alpha=0.4):
    overlay = img.copy()
    pt1 = (0, 0)
    pt2 = (int(img.shape[1] * w_ratio), int(img.shape[0] * h_ratio))

    mat_color = (200, 200, 200)
    fill = -1
    cv2.rectangle(overlay, pt1, pt2, mat_color, fill)

    mat_img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

    draw_texts(mat_img, texts)
    return mat_img