"""旧推理入口兼容与脱离业务模块后的几何计算一致性。"""
import random
import os
from pathlib import Path
import subprocess
import sys
import unittest

from omrs.inbox import iou as business_iou
from tools.boxdetect import inference, serve, probe
from tools.boxdetect._service import module


class ServiceCompatibilityTests(unittest.TestCase):
    def test_main_control_import_has_no_tool_or_inference_dependency(self):
        source = Path(__file__).resolve().parents[1]
        script = """import importlib.abc, sys
sys.path.insert(0, sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ['tools', 'boxdetect_service', 'onnxruntime', 'numpy', 'torch', 'ultralytics']:
            raise ImportError('主程序不应加载: ' + fullname)
sys.meta_path.insert(0, Block())
import omrs.traincontrol
"""
        env = {key: value for key, value in os.environ.items()
               if key not in ('PYTHONPATH', 'OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL')}
        run = subprocess.run([sys.executable, '-I', '-c', script, str(source)], env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

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
