"""在部署者设置的内存／时间限额内校验 ONNX 并完成一次推理。"""
import argparse
from pathlib import Path

from .inference import Detector
from .model import model_info


def add_arguments(parser):
    parser.add_argument('--model-dir', required=True)


def run(args):
    from PIL import Image

    folder = Path(args.model_dir)
    meta = model_info(folder)
    detector = Detector(folder / 'model.onnx', conf=meta['conf'])
    if detector.size != meta['imgsz']:
        raise ValueError('ONNX实际输入尺寸与登记不符')
    detector(Image.new('RGB', (640, 640), 'white'))
    print('模型预检通过')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    run(parser.parse_args(argv))
