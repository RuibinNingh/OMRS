"""兼容旧推理导入；计算实现由独立检测服务提供。"""
from tools.boxdetect._service import module

_inference = module('inference')
Detector = _inference.Detector
letterbox_geometry = _inference.letterbox_geometry
restore_box = _inference.restore_box
nms = _inference.nms
iou = _inference.iou
ROLES = _inference.ROLES
