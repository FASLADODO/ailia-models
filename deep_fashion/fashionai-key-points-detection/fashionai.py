import sys
import time
import argparse

import numpy as np
import cv2
import matplotlib.pyplot as plt

import ailia

# import original modules
sys.path.append('../../util')
from model_utils import check_and_download_models  # noqa: E402
from detector_utils import load_image  # noqa: E402
from webcamera_utils import get_capture  # noqa: E402

from my_utils import decode_np, draw_keypoints

# ======================
# Parameters
# ======================

WEIGHT_DRESS_PATH = './dress_100.onnx'
MODEL_DRESS_PATH = './dress_100.onnx.prototxt'
REMOTE_PATH = \
    'https://storage.googleapis.com/ailia-models/fashionai/'

IMAGE_DRESS_PATH = 'dress.jpg'
SAVE_IMAGE_PATH = 'output.png'

IMAGE_SIZE = 512

MU = 0.65
SIGMA = 0.25
HM_STRIDE = 4

# ======================
# Arguemnt Parser Config
# ======================

parser = argparse.ArgumentParser(
    description='FashionAI model'
)
parser.add_argument(
    '-i', '--input', metavar='IMAGE',
    default='',
    help='The input image path.'
)
parser.add_argument(
    '-v', '--video', metavar='VIDEO',
    default=None,
    help='The input video path. ' +
         'If the VIDEO argument is set to 0, the webcam input will be used.'
)
parser.add_argument(
    '-s', '--savepath', metavar='SAVE_IMAGE_PATH', default=SAVE_IMAGE_PATH,
    help='Save path for the output image.'
)
parser.add_argument(
    '-b', '--benchmark',
    action='store_true',
    help='Running the inference on the same input 5 times ' +
         'to measure execution performance. (Cannot be used in video mode)'
)
parser.add_argument(
    '-t', '--clothing_type', type=str, default='dress',
    choices=('dress',),
    help='clothing type'
)
parser.add_argument(
    '--onnx',
    action='store_true',
    help='execute onnxruntime version.'
)
args = parser.parse_args()


# ======================
# Secondaty Functions
# ======================


def preprocess(img, img_size):
    (img_w, img_h) = img_size
    img = cv2.resize(img, (img_w, img_h), interpolation=cv2.INTER_CUBIC)
    img = np.transpose(img, (2, 0, 1)).astype(np.float32)  # channel, height, width
    img[[0, 2]] = img[[2, 0]]  # BGR -> RGB
    img = img / 255.0
    img = (img - MU) / SIGMA
    pad_imgs = np.zeros([1, 3, IMAGE_SIZE, IMAGE_SIZE], dtype=np.float32)
    pad_imgs[0, :, :img_h, :img_w] = img

    return pad_imgs


def post_processing(hm_pred, hm_pred2, info):
    keypoints = {
        'blouse': ['neckline_left', 'neckline_right', 'center_front', 'shoulder_left', 'shoulder_right',
                   'armpit_left', 'armpit_right', 'cuff_left_in', 'cuff_left_out', 'cuff_right_in',
                   'cuff_right_out', 'top_hem_left', 'top_hem_right'],
        'outwear': ['neckline_left', 'neckline_right', 'shoulder_left', 'shoulder_right', 'armpit_left',
                    'armpit_right', 'waistline_left', 'waistline_right', 'cuff_left_in', 'cuff_left_out',
                    'cuff_right_in', 'cuff_right_out', 'top_hem_left', 'top_hem_right'],
        'trousers': ['waistband_left', 'waistband_right', 'crotch', 'bottom_left_in', 'bottom_left_out',
                     'bottom_right_in', 'bottom_right_out'],
        'skirt': ['waistband_left', 'waistband_right', 'hemline_left', 'hemline_right'],
        'dress': ['neckline_left', 'neckline_right', 'center_front', 'shoulder_left', 'shoulder_right',
                  'armpit_left', 'armpit_right', 'waistline_left', 'waistline_right', 'cuff_left_in',
                  'cuff_left_out', 'cuff_right_in', 'cuff_right_out', 'hemline_left', 'hemline_right']
    }
    keypoint = keypoints[args.clothing_type]
    conjug = []
    for i, key in enumerate(keypoint):
        if 'left' in key:
            j = keypoint.index(key.replace('left', 'right'))
            conjug.append([i, j])

    a = np.zeros_like(hm_pred2)
    img_w2 = info['img_w2']
    a[:, :, :img_w2 // HM_STRIDE] = np.flip(hm_pred2[:, :, :img_w2 // HM_STRIDE], 2)
    for conj in conjug:
        a[conj] = a[conj[::-1]]
    hm_pred2 = a

    scale = info['scale']
    img_w = info['img_w']
    img_h = info['img_h']
    x, y = decode_np(hm_pred + hm_pred2, scale, HM_STRIDE, (img_w / 2, img_h / 2), method='maxoffset')
    keypoints = np.stack([x, y, np.ones(x.shape)], axis=1).astype(np.int16)

    return keypoints


# ======================
# Main functions
# ======================


def predict(img, net):
    img_flip = cv2.flip(img, 1)

    img_h, img_w, _ = img.shape
    scale = IMAGE_SIZE / max(img_w, img_h)
    img_h2 = int(img_h * scale)
    img_w2 = int(img_w * scale)

    # initial preprocesses
    img = preprocess(img, (img_w2, img_h2))
    img_flip = preprocess(img_flip, (img_w2, img_h2))

    # feedforward
    if not args.onnx:
        output = net.predict({
            'img': img
        })
        output_flip = net.predict({
            'img': img_flip
        })
    else:
        img_name = net.get_inputs()[0].name
        p2_name = net.get_outputs()[0].name
        hm_pred_name = net.get_outputs()[1].name
        output = net.run([p2_name, hm_pred_name],
                         {img_name: img})
        output_flip = net.run([p2_name, hm_pred_name],
                              {img_name: img_flip})

    _, hm_pred = output
    _, hm_pred2 = output_flip

    hm_pred = np.maximum(hm_pred, 0)
    hm_pred2 = np.maximum(hm_pred2, 0)
    hm_pred = hm_pred[0]
    hm_pred2 = hm_pred2[0]

    info = {
        'img_h': img_h,
        'img_w': img_w,
        'img_h2': img_h2,
        'img_w2': img_w2,
        'scale': scale,
    }
    keypoints = post_processing(hm_pred, hm_pred2, info)

    return keypoints


def recognize_from_image(filename, net):
    # prepare input data
    img = load_image(filename)
    print(f'input image shape: {img.shape}')

    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # inference
    print('Start inference...')
    if args.benchmark:
        print('BENCHMARK mode')
        for i in range(5):
            start = int(round(time.time() * 1000))
            keypoints = predict(img, net)
            end = int(round(time.time() * 1000))
            print(f'\tailia processing time {end - start} ms')
    else:
        keypoints = predict(img, net)

    """
    plot result
    """
    res_img = draw_keypoints(img, keypoints)
    cv2.imwrite(args.savepath, res_img)
    print('Script finished successfully.')


def recognize_from_video(video, net):
    capture = get_capture(video)

    while (True):
        ret, frame = capture.read()
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        if not ret:
            continue

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        keypoints = predict(frame, net)
        res_img = draw_keypoints(frame, keypoints)

        # show
        cv2.imshow('frame', res_img)

    capture.release()
    cv2.destroyAllWindows()
    print('Script finished successfully.')


def main():
    dic_model = {
        'dress': (WEIGHT_DRESS_PATH, MODEL_DRESS_PATH, IMAGE_DRESS_PATH),
    }
    weight_path, model_path, img_path = dic_model[args.clothing_type]

    # model files check and download
    check_and_download_models(weight_path, model_path, REMOTE_PATH)

    # load model
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')

    # initialize
    if not args.onnx:
        net = ailia.Net(model_path, weight_path, env_id=env_id)
    else:
        import onnxruntime
        net = onnxruntime.InferenceSession(weight_path)

    if args.video is not None:
        recognize_from_video(args.video, net)
    else:
        recognize_from_image(args.input if args.input else img_path, net)


if __name__ == '__main__':
    main()