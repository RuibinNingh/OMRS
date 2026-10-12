"""初始化与首个真实 HTTP 纵向切片；测试数据均为隔离临时数据。"""
from contextlib import closing
import sqlite3
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
import urllib.request


class BootstrapTests(unittest.TestCase):
    def test_private_initialization_and_health_contract(self):
        self.assertIsNotNone(importlib.util.find_spec('zyb_gateway'), '独立网关包尚未实现')
        from zyb_gateway.server import create_server
        from zyb_gateway.config import Config
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'docs') as tmp:
            cfg = Config(data_dir=Path(tmp) / 'private', port=0)
            server = create_server(cfg)
            secret_file = cfg.data_dir / 'admin-secret.txt'
            self.assertTrue(secret_file.is_file())
            original = secret_file.read_bytes()
            self.assertGreaterEqual(len(original.strip()), 40)
            self.assertEqual(stat.S_IMODE(secret_file.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(cfg.data_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((cfg.data_dir / 'gateway.sqlite3').stat().st_mode), 0o600)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                with urllib.request.urlopen(base + '/healthz') as response:
                    self.assertEqual(json.load(response), {'service': 'zuoyebang-gateway', 'version': '1.0.0', 'status': 'ok'})
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            again = create_server(Config(data_dir=cfg.data_dir, port=0))
            self.assertEqual(original, secret_file.read_bytes(), '重启不能更换管理员初始密码')
            again.server_close()
            with closing(sqlite3.connect(cfg.data_dir / 'gateway.sqlite3')) as db, db:
                content = '\n'.join(str(row) for row in db.execute('SELECT * FROM settings'))
            self.assertNotIn(original.decode().strip(), content)


if __name__ == '__main__':
    unittest.main()
