"""旧工具入口定位同仓独立服务；不用于主应用的进程导入。"""
import importlib
from pathlib import Path
import sys


def module(name):
    source = Path(__file__).resolve().parents[2] / 'services' / 'boxdetect'
    if not source.is_dir():
        raise ImportError('缺少 services/boxdetect，请使用包含独立检测服务的完整源码包')
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return importlib.import_module('boxdetect_service.' + name)
