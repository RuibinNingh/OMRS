"""旧推理入口兼容与脱离业务模块后的几何计算一致性。"""
import random
import unittest

from omrs.inbox import iou as business_iou
from tools.boxdetect import inference, serve, probe
from tools.boxdetect._service import module


class ServiceCompatibilityTests(unittest.TestCase):
    def test_legacy_interfaces_delegate_to_one_runtime(self):
        self.assertIs(inference.Detector, module('inference').Detector)
        self.assertIs(serve.make_server, module('server').make_server)
        self.assertIs(probe.model_info, module('model').model_info)

    def test_geometry_matches_existing_merge_contract(self):
        rng = random.Random(20261013)
        pairs = [(None, None), ({'x': 0, 'y': 0, 'w': 0, 'h': 0}, {'x': 0, 'y': 0, 'w': 0, 'h': 0})]
        for _ in range(100):
            pairs.append(tuple({key: rng.random() for key in ('x', 'y', 'w', 'h')} for _ in range(2)))
        for a, b in pairs:
            self.assertEqual(inference.iou(a, b), business_iou(a, b))
