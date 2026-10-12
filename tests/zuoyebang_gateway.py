"""冻结v1契约的合成网关：真实socket，只替代官方账号/搜题边界。"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tests.zuoyebang_fixtures import candidates

KEY = 'synthetic-gateway-call-key'


class SyntheticGateway:
    def __init__(self, *, framing='length', prefix=''):
        if framing not in ('length', 'close', 'keep-open'):
            raise ValueError('合成网关响应边界不合法')
        self.calls = []
        self.responses = {}
        self.before = None
        self.release = threading.Event()
        self.account = {'local_session_ready': True, 'has_account_credential': True,
                        'observations': {'account': {'state': 'valid'}, 'signing': {'state': 'valid'}, 'events': []}}
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_): pass
            def do_GET(self): self.respond()
            def do_POST(self): self.respond()
            def respond(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                data = json.loads(raw) if raw else None
                route = self.path[len(prefix):] if self.path.startswith(prefix + '/') else self.path
                gateway.calls.append({'method': self.command, 'path': self.path, 'headers': dict(self.headers), 'body': data})
                if gateway.before: gateway.before(self.path)
                headers = {}
                if route == '/healthz':
                    status, body = 200, {'status': 'ok', 'service': 'zuoyebang-gateway', 'version': 'synthetic-v1'}
                elif self.headers.get('Authorization') != 'Bearer ' + KEY:
                    status, body = 401, {'status': 'error', 'code': 'invalid_key', 'msg': '密钥无效'}
                elif route == '/api/v1/status':
                    status, body = 200, {'status': 'ok', 'account': gateway.account, 'panel_url': '/'}
                elif route == '/api/v1/search':
                    assert base64.b64decode(data['image_base64'], validate=True)
                    status, body = 200, {'status': 'ok', 'result': {'data': {'answers': {'mainPageInfo': [json.dumps(candidates())]}}}}
                else:
                    status, body = 404, {'status': 'error', 'code': 'not_found', 'msg': '接口不存在'}
                if self.path in gateway.responses:
                    status, body, headers = gateway.responses[self.path]
                encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
                try:
                    self.send_response(status)
                    for name, value in headers.items(): self.send_header(name, str(value))
                    self.send_header('Content-Type', 'application/json')
                    if framing == 'length' and 'Content-Length' not in headers:
                        self.send_header('Content-Length', str(len(encoded)))
                    if framing != 'length':
                        self.send_header('Connection', 'keep-alive' if framing == 'keep-open' else 'close')
                    self.end_headers()
                    self.wfile.write(encoded)
                    self.wfile.flush()
                    if framing == 'keep-open':
                        # 完整JSON已到达但HTTP正文未结束，必须由客户端截止来收束。
                        gateway.release.wait(2)
                        self.close_connection = True
                except (BrokenPipeError, ConnectionResetError): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f'http://127.0.0.1:{self.server.server_port}' + prefix

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
