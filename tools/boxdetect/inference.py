"""固定 YOLOv8 ONNX 文件的预处理与后处理；依赖按需加载。"""
from pathlib import Path
from omrs.inbox import iou
from tools.boxdetect.common import ROLES


def letterbox_geometry(width, height, size):
    scale = min(size / width, size / height)
    nw, nh = round(width * scale), round(height * scale)
    return scale, (size-nw)//2, (size-nh)//2, nw, nh


def restore_box(xywh, width, height, size):
    scale, left, top, _, _ = letterbox_geometry(width, height, size)
    cx, cy, w, h = map(float, xywh)
    x0 = max(0., min(width, (cx-w/2-left)/scale)) / width
    x1 = max(0., min(width, (cx+w/2-left)/scale)) / width
    y0 = max(0., min(height, (cy-h/2-top)/scale)) / height
    y1 = max(0., min(height, (cy+h/2-top)/scale)) / height
    return {'x': x0, 'y': y0, 'w': max(0., x1-x0), 'h': max(0., y1-y0)}


def nms(boxes, threshold=.7):
    result = []
    for box in sorted(boxes, key=lambda b: b['conf'], reverse=True):
        if not any(box['role'] == b['role'] and iou(box, b) > threshold for b in result):
            result.append(box)
    return result


class Detector:
    def __init__(self, model, conf=.25, threads=3):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(Path(model)), sess_options=options, providers=['CPUExecutionProvider'])
        self.input = self.session.get_inputs()[0]
        self.size = int(self.input.shape[-1])
        self.conf = conf

    def __call__(self, image):
        import numpy as np
        from PIL import Image
        _, left, top, nw, nh = letterbox_geometry(image.width, image.height, self.size)
        padded = Image.new('RGB', (self.size, self.size), (114, 114, 114))
        padded.paste(image.convert('RGB').resize((nw, nh), Image.Resampling.BILINEAR), (left, top))
        tensor = np.asarray(padded, dtype=np.float32).transpose(2, 0, 1)[None] / 255.
        prediction = self.session.run(None, {self.input.name: tensor})[0]
        if prediction.ndim != 3 or prediction.shape[1] != 4 + len(ROLES):
            raise ValueError('模型输出不符合 YOLOv8 两类检测契约')
        rows = prediction[0].T
        scores = rows[:, 4:]
        ids = np.argmax(scores, axis=1)
        confidence = np.max(scores, axis=1)
        selected = np.flatnonzero(confidence >= self.conf)
        selected = sorted(selected, key=lambda i: -float(confidence[i]))[:300]
        boxes = []
        for index in selected:
            box = restore_box(rows[index, :4], image.width, image.height, self.size)
            if box['w'] > 0 and box['h'] > 0:
                boxes.append(dict(box, role=ROLES[int(ids[index])], card=1, conf=float(confidence[index])))
        return nms(boxes)
