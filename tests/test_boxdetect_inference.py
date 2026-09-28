"""ONNX 服务的坐标与 NMS 纯函数不依赖训练框架。"""
import unittest
from tools.boxdetect.inference import letterbox_geometry, restore_box, nms


class InferenceTests(unittest.TestCase):
    def test_portrait_letterbox_restore(self):
        self.assertEqual(letterbox_geometry(100, 200, 640), (3.2, 160, 0, 320, 640))
        self.assertEqual(restore_box([320, 320, 320, 640], 100, 200, 640), {'x':0., 'y':0., 'w':1., 'h':1.})

    def test_landscape_clamps_padding(self):
        box = restore_box([320, 320, 1000, 1000], 200, 100, 640)
        self.assertEqual(box, {'x':0., 'y':0., 'w':1., 'h':1.})

    def test_nms_only_same_class(self):
        box = {'role':'question','x':0,'y':0,'w':.5,'h':.5,'conf':.9}
        result=nms([dict(box,conf=.3),dict(box,role='answer',conf=.8),box])
        self.assertEqual([b['role'] for b in result],['question','answer'])
        self.assertEqual(result[0]['conf'],.9)

    def test_nms_empty(self):
        self.assertEqual(nms([]),[])
