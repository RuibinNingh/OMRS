"""在有内存/时间限额的独立进程校验ONNX并完成一次推理。"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from omrs.traincontrol import model_info
from tools.boxdetect.inference import Detector
from PIL import Image

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',required=True);a=p.parse_args()
    folder=Path(a.model_dir);meta=model_info(folder);detector=Detector(folder/'model.onnx',conf=meta['conf'])
    if detector.size!=meta['imgsz']:raise ValueError('ONNX实际输入尺寸与登记不符')
    detector(Image.new('RGB',(640,640),'white'))
    print('模型预检通过')
