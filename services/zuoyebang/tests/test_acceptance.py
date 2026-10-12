"""续做验收：真实 HTTP 并发与不可用审计的失败路径。"""
import base64
import http.client
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from .support import HttpCase
from .test_accounts import SYNTHETIC_PROFILE
from .test_search import image_bytes


class AcceptanceTests(HttpCase):
    def test_trusted_proxy_empty_or_duplicate_xff_cannot_become_local(self):
        self.server.config.trusted_proxies = ('127.0.0.1/32',)
        key, _ = self.make_key()
        for values in (('',), ('', '203.0.113.7')):
            with self.subTest(values=values):
                connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
                try:
                    connection.putrequest('GET', '/api/v1/status')
                    connection.putheader('Authorization', 'Bearer ' + key)
                    for value in values:
                        connection.putheader('X-Forwarded-For', value)
                    connection.endheaders()
                    response = connection.getresponse()
                    data = json.loads(response.read())
                    self.assertEqual(response.status, 400, '非法可信转发头被判定为本机请求')
                    self.assertEqual(data['code'], 'proxy_invalid')
                finally:
                    connection.close()

    def test_official_socket_disconnect_is_stable_network_error(self):
        self.login()
        self.assertEqual(self.admin('POST', '/api/admin/profile', {'profile': SYNTHETIC_PROFILE})[0], 200)
        key, _ = self.make_key()
        attempts = []

        class DisconnectedOfficial(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                attempts.append(self.path)
                self.close_connection = True

        upstream = ThreadingHTTPServer(('127.0.0.1', 0), DisconnectedOfficial)
        worker = threading.Thread(target=upstream.serve_forever)
        worker.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        target = f'http://127.0.0.1:{upstream.server_port}/synthetic-disconnect'

        class Boundary:
            def open(self, request, timeout):
                return opener.open(urllib.request.Request(target, data=request.data, headers=dict(request.headers)), timeout=timeout)

        try:
            with patch('zyb_gateway.vendor.direct.urllib.request.build_opener', return_value=Boundary()):
                checks = [
                    self.request('POST', '/api/v1/search', {'image_base64': base64.b64encode(image_bytes()).decode(), 'grade': 0}, {'Authorization': 'Bearer ' + key}),
                    self.admin('POST', '/api/admin/account', {'operation': 'verify'}),
                ]
            for code, data, _heads in checks:
                with self.subTest(response=data):
                    self.assertEqual(code, 502)
                    self.assertEqual(data['code'], 'network')
            self.assertEqual(len(attempts), 2, '网络失败发生了自动重试')
            observations = self.admin('GET', '/api/admin/account')[1]['account']['observations']
            self.assertEqual(observations['account']['state'], 'unknown', '网络失败被误判为凭据失效')
        finally:
            upstream.shutdown()
            upstream.server_close()
            worker.join(3)

    def test_account_check_and_refresh_do_not_restore_cancelled_qr(self):
        self.login()
        self.assertEqual(self.admin('POST', '/api/admin/profile', {'profile': SYNTHETIC_PROFILE})[0], 200)
        from zyb_gateway.vendor.account import AccountClient
        for operation in ('verify', 'refresh'):
            with self.subTest(operation=operation):
                entered = threading.Event()
                release = threading.Event()
                replies = []

                def boundary(action, profile, params=None, **kwargs):
                    if action == 'qr_create':
                        return {'errNo': 0, 'data': {'uuid': 'SYNTHETIC-CANCEL-RACE'}}
                    if action == ('userinfo' if operation == 'verify' else 'relogin'):
                        entered.set()
                        if not release.wait(4):
                            raise AssertionError('测试账号操作未释放')
                    if action == 'relogin':
                        return {'errNo': 0, 'data': {'zybuss': 'SYNTHETIC-REFRESH-RACE'}}
                    return {'errNo': 0, 'data': {'user': {'uid': 42}}}

                with patch.object(AccountClient, 'request', side_effect=boundary):
                    flow = self.admin('POST', '/api/admin/account', {'operation': 'qr_start'})[1]['result']['flow_id']
                    worker = threading.Thread(target=lambda: replies.append(self.admin('POST', '/api/admin/account', {'operation': operation})))
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(2))
                        cancelled = self.admin('POST', '/api/admin/account', {'operation': 'qr_cancel', 'flow_id': flow})
                        self.assertEqual(cancelled[1]['result']['state'], 'cancelled')
                    finally:
                        release.set()
                        worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(replies[0][0], 200)
                current = json.loads((self.cfg.data_dir / 'qr-login.json').read_bytes())
                self.assertEqual(current['state'], 'cancelled', '账号检查/刷新恢复了已取消二维码')
                self.assertNotIn('uuid', current, '已取消二维码重新保存了官方挑战')

    def test_http_overload_audit_failure_returns_stable_503(self):
        acquired = []
        while self.server.http_slots.acquire(blocking=False):
            acquired.append(True)
        try:
            with patch.object(self.server.store, 'audit', side_effect=RuntimeError('SYNTHETIC-PRIVATE-STORAGE-ERROR')):
                code, data, _ = self.request('GET', '/healthz')
            self.assertEqual(code, 503)
            self.assertEqual(data, {'status': 'error', 'msg': '审计存储不可用', 'code': 'audit_unavailable'})
        finally:
            for _ in acquired:
                self.server.http_slots.release()
