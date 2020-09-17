import sys
import time
import argparse
from collections import OrderedDict

import numpy as np
import cv2
from PIL import Image

import ailia

# import original modules
sys.path.append('../util')
from utils import check_file_existance  # noqa: E402
from model_utils import check_and_download_models  # noqa: E402
from detector_utils import plot_results, load_image  # noqa: E402C

# ======================
# Parameters
# ======================

REMOTE_PATH = 'https://storage.googleapis.com/ailia-models/clothing-detection/'

DATASETS_MODEL_PATH = OrderedDict([
    ('modanet', ['yolov3-modanet.opt.onnx', 'yolov3-modanet.opt.onnx.prototxt']),
    ('df2', ['yolov3-df2.opt.onnx', 'yolov3-df2.opt.onnx.prototxt'])
])

IMAGE_PATH = 'input.jpg'
SAVE_IMAGE_PATH = 'output.png'

DATASETS_CATEGORY = {
    'modanet': [
        "bag", "belt", "boots", "footwear", "outer", "dress", "sunglasses",
        "pants", "top", "shorts", "skirt", "headwear", "scarf/tie"
    ],
    'df2': [
        "short sleeve top", "long sleeve top", "short sleeve outwear", "long sleeve outwear",
        "vest", "sling", "shorts", "trousers", "skirt", "short sleeve dress",
        "long sleeve dress", "vest dress", "sling dress"
    ]
}
THRESHOLD = 0.39
IOU = 0.4
DETECTION_WIDTH = 416

# ======================
# Arguemnt Parser Config
# ======================
parser = argparse.ArgumentParser(
    description='Clothing detection model'
)
parser.add_argument(
    '-i', '--input', metavar='IMAGE',
    default=IMAGE_PATH,
    help='The input image path.'
)
parser.add_argument(
    '-d', '--dataset', metavar='TYPE', choices=DATASETS_MODEL_PATH,
    default=list(DATASETS_MODEL_PATH.keys())[0],
    help='Type of dataset to train the model. Allowed values are {}.'.format(', '.join(DATASETS_MODEL_PATH))
)
parser.add_argument(
    '-v', '--video', metavar='VIDEO',
    default=None,
    help='The input video path. ' +
         'If the VIDEO argument is set to 0, the webcam input will be used.'
)
parser.add_argument(
    '-s', '--savepath', metavar='SAVE_IMAGE_PATH',
    default=SAVE_IMAGE_PATH,
    help='Save path for the output image.'
)
parser.add_argument(
    '-b', '--benchmark',
    action='store_true',
    help='Running the inference on the same input 5 times ' +
         'to measure execution performance. (Cannot be used in video mode)'
)
parser.add_argument(
    '-dw', '--detection_width',
    default=DETECTION_WIDTH,
    help='The detection width and height for yolo. (default: 416)'
)
args = parser.parse_args()

weight_path, model_path = DATASETS_MODEL_PATH[args.dataset]
category = DATASETS_CATEGORY[args.dataset]


# ======================
# Secondaty Functions
# ======================

def letterbox_image(image, size):
    '''resize image with unchanged aspect ratio using padding'''
    iw, ih = image.size
    w, h = size
    scale = min(w / iw, h / ih)
    nw = int(iw * scale)
    nh = int(ih * scale)

    image = image.resize((nw, nh), Image.BICUBIC)
    new_image = Image.new('RGB', size, (128, 128, 128))
    new_image.paste(image, ((w - nw) // 2, (h - nh) // 2))
    return new_image


def preprocess(img, resize):
    image = Image.fromarray(img)
    boxed_image = letterbox_image(image, (resize, resize))
    image_data = np.array(boxed_image, dtype='float32')
    image_data /= 255.
    image_data = np.expand_dims(image_data, 0)  # Add batch dimension.
    image_data = np.transpose(image_data, [0, 3, 1, 2])
    return image_data


def post_processing(img_shape, all_boxes, all_scores, indices):
    indices = indices.astype(np.int)

    bboxes = []
    for idx_ in indices[0]:
        cls_ind = idx_[1]
        score = all_scores[tuple(idx_)]

        idx_1 = (idx_[0], idx_[2])
        box = all_boxes[idx_1]
        y, x, y2, x2 = box
        w = (x2 - x) / img_shape[1]
        h = (y2 - y) / img_shape[0]
        x /= img_shape[1]
        y /= img_shape[0]

        r = ailia.DetectorObject(
            category=cls_ind, prob=score,
            x=x, y=y, w=w, h=h,
        )
        bboxes.append(r)

    return bboxes


# ======================
# Main functions
# ======================


def detect_objects(img, detector):
    img_shape = img.shape[:2]

    # initial preprocesses
    img = preprocess(img, resize=args.detection_width)

    # feedforward
    all_boxes, all_scores, indices = detector.predict({
        'input_1': img,
        'image_shape': np.array([img_shape], np.float32),
        'layer.score_threshold': np.array([THRESHOLD], np.float32),
        'iou_threshold': np.array([IOU], np.float32),
    })

    # post processes
    detect_object = post_processing(img_shape, all_boxes, all_scores, indices)

    return detect_object


def recognize_from_image(filename, detector):
    # prepare input data
    img = load_image(filename)
    print(f'input image shape: {img.shape}')

    x = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

    # inferece
    print('Start inference...')
    if args.benchmark:
        print('BENCHMARK mode')
        for i in range(5):
            start = int(round(time.time() * 1000))
            detect_object = detect_objects(x, detector)
            end = int(round(time.time() * 1000))
            print(f'\tailia processing time {end - start} ms')
    else:
        detect_object = detect_objects(x, detector)

    # plot result
    res_img = plot_results(detect_object, img, category)
    cv2.imwrite(args.savepath, res_img)
    print('Script finished successfully.')


def recognize_from_video(video, detector):
    if video == '0':
        print('[INFO] Webcam mode is activated')
        capture = cv2.VideoCapture(0)
        if not capture.isOpened():
            print("[ERROR] webcamera not found")
            sys.exit(1)
    else:
        if check_file_existance(args.video):
            capture = cv2.VideoCapture(args.video)

    while True:
        ret, frame = capture.read()
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        if not ret:
            continue

        x = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        detect_object = detect_objects(x, detector)
        res_img = plot_results(detect_object, frame, category)
        cv2.imshow('frame', res_img)

    capture.release()
    cv2.destroyAllWindows()
    print('Script finished successfully.')


def main():
    # model files check and download
    check_and_download_models(weight_path, model_path, REMOTE_PATH)

    # load model
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')

    # initialize
    detector = ailia.Net(model_path, weight_path, env_id=env_id)
    id_image_shape = detector.find_blob_index_by_name("image_shape")
    detector.set_input_shape((1, 3, args.detection_width, args.detection_width))
    detector.set_input_blob_shape((1, 2), id_image_shape)

    if args.video is not None:
        # video mode
        recognize_from_video(args.video, detector)
    else:
        # image mode
        recognize_from_image(args.input, detector)


if __name__ == '__main__':
    main()