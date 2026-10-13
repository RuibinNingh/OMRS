"""兼容旧候选模型预检命令；实现位于独立检测服务。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.boxdetect._service import module

_probe = module('probe')
model_info = _probe.model_info
Detector = _probe.Detector
main = _probe.main

if __name__ == '__main__':
    main()
