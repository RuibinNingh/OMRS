"""真实 socket/SQLite 测试工具，绝不读取真实凭据。"""
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from zyb_gateway.config import Config
from zyb_gateway.server import create_server

ROOT = Path(__file__).resolve().parents[1]

class HttpCase(unittest.TestCase):
    config_overrides = {}
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'docs', prefix='isolated-test-')
        self.addCleanup(self.temp.cleanup)
        self.cfg = Config(data_dir=Path(self.temp.name) / 'private', port=0, bind='0.0.0.0', **self.config_overrides)
        self.server = create_server(self.cfg)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.password = (self.cfg.data_dir / 'admin-secret.txt').read_text().strip()
        self.cookie = ''
        self.csrf = ''

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None, headers=None, host='127.0.0.1'):
        heads = dict(headers or {})
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
            heads.setdefault('Content-Type', 'application/json')
        connection = http.client.HTTPConnection(host, self.server.server_port, timeout=6)
        connection.request(method, path, body=body, headers=heads)
        response = connection.getresponse()
        raw = response.read()
        result = json.loads(raw) if raw and 'application/json' in response.getheader('Content-Type', '') else raw.decode()
        code, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return code, result, response_headers

    def login(self):
        code, data, heads = self.request('POST', '/api/admin/login', {'password': self.password}, {'Origin': self.base})
        self.assertEqual(code, 200, data)
        self.cookie = heads['Set-Cookie'].split(';')[0]
        self.csrf = data['csrf_token']
        return data, heads

    def admin(self, method, path, body=None, extra=None):
        heads = {'Cookie': self.cookie, 'Origin': self.base, 'X-CSRF-Token': self.csrf}
        heads.update(extra or {})
        return self.request(method, path, body, heads)

    def make_key(self, name='测试调用密钥'):
        if not self.cookie:
            self.login()
        code, data, _ = self.admin('POST', '/api/admin/keys', {'name': name})
        self.assertEqual(code, 200, data)
        return data['key'], data['metadata']['id']

    @staticmethod
    def lan_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('192.0.2.1', 80))
            return s.getsockname()[0]
        finally:
            s.close()
