"""复制独立项目后验证命令和导入；不借用主仓库路径或推理依赖。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class IndependenceTests(unittest.TestCase):
    def test_copied_package_imports_without_business_or_training_modules(self):
        source = Path(__file__).resolve().parents[1] / 'boxdetect_service'
        with tempfile.TemporaryDirectory() as temp:
            shutil.copytree(source, Path(temp) / source.name, ignore=shutil.ignore_patterns('__pycache__'))
            env = {key: value for key, value in os.environ.items()
                   if key not in ('PYTHONPATH', 'PYTHONHOME', 'OMRS_SYSTEMD_SERVICE', 'OMRS_BOXDETECT_CONTROL')}
            script = """import sys
import boxdetect_service.server, boxdetect_service.probe
for prefix in ['omrs', 'tools', 'torch', 'ultralytics', 'onnxruntime', 'numpy']:
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules), prefix
"""
            run = subprocess.run([sys.executable, '-c', script], cwd=temp, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            for command in ['serve', 'probe']:
                run = subprocess.run([sys.executable, '-m', 'boxdetect_service', command, '--help'],
                                     cwd=temp, env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn('--model-dir', run.stdout)
