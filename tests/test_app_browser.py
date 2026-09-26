"""把 tests/app/run_browser.py（ui 组件浏览器单测）纳入 unittest。

有 playwright 与 Chromium 时真跑；没有时跳过（完整模式主机上常见），门禁里另有单独的 run_browser.py 一步。
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AppBrowserTests(unittest.TestCase):
    def test_ui_components_pass_in_real_browser(self):
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "app", "run_browser.py")],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode == 2:
            self.skipTest(proc.stdout.strip() or "playwright 不可用")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
