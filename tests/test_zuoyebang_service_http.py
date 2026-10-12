"""OMRS真实HTTP→合成网关HTTP，鉴权/CSRF/MCP边界与无长期业务锁。"""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from omrs import locking, vault_lifecycle as lifecycle
from omrs.server import OMRSHandler
from omrs.zuoyebang import service_config, store
from tests.zuoyebang_gateway import SyntheticGateway, KEY


class ServiceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='omrs-service-http-')
        self.vault = self.temp.name
        self.gateway = SyntheticGateway().__enter__()
        handler = type('ServiceHandler', (OMRSHandler,), {'vault_path': self.vault, 'log_message': lambda *_: None})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        self.gateway.__exit__(); self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, None if data is None else json.dumps(data), {'Content-Type': 'application/json', **(headers or {})})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_config_save_read_test_and_clear_are_web_only_and_secret_free(self):
        self.assertEqual(self.request('GET', '/api/zuoyebang/service')[0], 200, '尚无服务配置路由')
        status, body = self.request('POST', '/api/zuoyebang/service', {'base_url': self.gateway.url, 'api_key': KEY})
        self.assertEqual(status, 200, body)
        self.assertTrue(body['service']['api_key_configured'])
        self.assertNotIn(KEY, json.dumps(body))
        self.assertEqual(self.gateway.calls, [])
        for path in ('/api/zuoyebang/service', '/api/config'):
            status, body = self.request('GET', path)
            self.assertEqual(status, 200); self.assertNotIn(KEY, json.dumps(body))
        status, tested = self.request('POST', '/api/zuoyebang/service/test', {})
        self.assertEqual(status, 200, tested)
        self.assertTrue(tested['connected']); self.assertTrue(tested['local_session_ready'])
        self.assertEqual([call['path'] for call in self.gateway.calls], ['/api/v1/status'])
        self.assertEqual(self.request('POST', '/api/zuoyebang/service', {'clear_api_key': True})[0], 200)
        self.assertFalse(service_config.snapshot(self.vault).api_key)

    def test_service_routes_keep_csrf_remote_auth_and_mcp_boundary(self):
        paths = ['/api/zuoyebang/service', '/api/zuoyebang/service/test']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.request('POST', path, {}, {'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'})[0], 403)
                self.assertEqual(self.request('POST', path, {}, {'Authorization': 'Bearer synthetic-mcp'})[0], 403)
                self.assertEqual(self.request('POST', path, {}, {'Host': 'remote.example', 'X-Real-IP': '198.51.100.7', 'X-Forwarded-Proto': 'https'})[0], 401)
        self.assertEqual(self.request('GET', '/api/zuoyebang/service', headers={'Authorization': 'Bearer synthetic-mcp'})[0], 403)

    def test_legacy_account_write_is_forbidden_and_points_to_panel(self):
        for path, payload in [('/api/zuoyebang/profile', {'profile': {}}), ('/api/zuoyebang/account', {'operation': 'qr_start'})]:
            with self.subTest(path=path):
                status, body = self.request('POST', path, payload)
                self.assertEqual(status, 409)
                self.assertEqual(body['code'], 'gateway_management')
                self.assertIn('面板', body['msg'])
        self.assertFalse((store.root(self.vault) / 'session.json').exists())
        self.assertEqual(self.gateway.calls, [])

    def test_status_wait_releases_lease_and_write_lock_and_rejects_service_switch(self):
        service_config.save(self.vault, {'base_url': self.gateway.url, 'api_key': KEY})
        entered, release = threading.Event(), threading.Event()
        self.gateway.before = lambda _path: (entered.set(), release.wait(2))
        result = []
        thread = threading.Thread(target=lambda: result.append(self.request('GET', '/api/zuoyebang/status')))
        thread.start()
        try:
            self.assertTrue(entered.wait(1), '状态仍读取OMRS旧设备会话而未连接网关')
            with locking.write_lock(timeout=.2), lifecycle.exclusive(self.vault, timeout=.2): pass
            service_config.save(self.vault, {'base_url': 'http://127.0.0.1:9876'})
        finally:
            release.set(); thread.join(3)
        self.assertEqual(result[0][0], 409, result)
        self.assertEqual(result[0][1]['code'], 'service_changed')

    def test_network_failure_is_not_account_expiry(self):
        service_config.save(self.vault, {'base_url': self.gateway.url, 'api_key': KEY})
        status, body = self.request('GET', '/api/zuoyebang/status')
        self.assertEqual(status, 200); self.assertEqual(body['observations']['account']['state'], 'valid')
        self.gateway.responses['/api/v1/status'] = 502, {'status': 'error', 'msg': KEY}, {}
        status, body = self.request('GET', '/api/zuoyebang/status')
        self.assertEqual(status, 502); self.assertEqual(body['code'], 'gateway_upstream')
        self.assertNotIn(KEY, json.dumps(body)); self.assertNotIn('login_required', json.dumps(body))
