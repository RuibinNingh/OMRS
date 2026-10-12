"""标准库 HTTP 服务；管理会话与调用密钥完全隔离。"""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import time
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from . import __version__
from .errors import ApiError
from .security import Auth, csrf_token, request_identity
from .storage import Store
from .accounts import Accounts
from .search import search

EMPTY_ACCOUNT = {'local_session_ready':False, 'has_account_credential':False, 'observations':{'account':{},'signing':{},'events':[]}}
ASSETS={'/':('index.html','text/html; charset=utf-8'),'/assets/panel.js':('panel.js','text/javascript; charset=utf-8'),'/assets/panel.css':('panel.css','text/css; charset=utf-8')}
ROUTES = {*(('GET',p) for p in ASSETS),('POST','/api/admin/credential'),('POST','/api/v1/search'),('GET','/healthz'), ('GET','/api/v1/status'), ('POST','/api/admin/login'), ('POST','/api/admin/logout'), ('GET','/api/admin/session'), ('GET','/api/admin/keys'), ('POST','/api/admin/keys'), ('POST','/api/admin/keys/revoke'), ('POST','/api/admin/profile'), ('GET','/api/admin/history'), ('GET','/api/admin/settings'), ('POST','/api/admin/settings'), ('GET','/api/admin/account'), ('POST','/api/admin/account')}
ACTIONS = {'/api/v1/search':'search','/api/v1/status':'status','/healthz':'health','/api/admin/login':'admin_login','/api/admin/logout':'admin_logout','/api/admin/session':'admin_session','/api/admin/keys':'key_create','/api/admin/keys/revoke':'key_revoke','/api/admin/settings':'settings','/api/admin/history':'history','/api/admin/profile':'profile_import','/api/admin/account':'account','/api/admin/credential':'credential_import'}
def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON field')
        result[key]=value
    return result


SECURITY_HEADERS = {
    'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY',
    'Referrer-Policy':'no-referrer', 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}

class Handler(BaseHTTPRequestHandler):
    server_version = 'ZybGateway'
    sys_version = ''
    def setup(self):
        super().setup()
        self.connection.settimeout(self.server.config.read_timeout)

    def log_message(self, *_args):
        pass

    def send_json(self, status, data, extra=None):
        raw = data if isinstance(data,bytes) else json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        self.send_response(status)
        content_type=(extra or {}).get('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length', str(len(raw)))
        for key, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            if key!='Content-Type':self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (OSError, ConnectionError):
            pass

    def send_error(self, code, message=None, explain=None):
        self.send_json(code, {'status':'error','msg':'HTTP 请求不合法','code':'http_invalid'})

    def read_json(self, limit=256*1024):
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            raise ApiError('body_invalid', '必须提供唯一 Content-Length')
        length_text = self.headers.get('Content-Length', '')
        if not length_text.isdigit() or not 1 <= int(length_text) <= limit:
            raise ApiError('body_budget', '请求正文超过预算或为空')
        if self.headers.get_content_type() != 'application/json':
            raise ApiError('json_required', '请发送 JSON 请求')
        try:
            chunks=[]; remaining=int(length_text)
            deadline=time.monotonic()+self.server.config.read_timeout
            while remaining:
                timeout=deadline-time.monotonic()
                if timeout<=0:raise TimeoutError()
                self.connection.settimeout(timeout)
                part=self.rfile.read1(min(65536,remaining))
                if not part:break
                chunks.append(part);remaining-=len(part)
            raw=b''.join(chunks)
            if len(raw) != int(length_text):
                raise ValueError('truncated')
            body = json.loads(raw, object_pairs_hook=unique_object, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError('nonfinite')))
        except (ValueError, UnicodeError, RecursionError):
            raise ApiError('json_invalid', 'JSON 请求不合法')
        if not isinstance(body, dict):
            raise ApiError('json_invalid', 'JSON 请求必须为对象')
        return body

    def check_host(self):
        if len(self.headers.get_all('Host', [])) != 1:
            raise ApiError('host_forbidden', 'Host 不在可信列表', 403)
        host = self.headers.get('Host','').lower()
        allowed = self.server.allowed_hosts
        if host not in allowed:
            raise ApiError('host_forbidden', 'Host 不在可信列表', 403)
        self.host = host

    def check_origin(self):
        if len(self.headers.get_all('Origin', [])) != 1:
            raise ApiError('origin_forbidden', '写操作必须来自同源面板', 403)
        origin = self.headers.get('Origin','')
        expected = self.server.config.public_origin or ('http://' + self.host)
        if origin != expected:
            raise ApiError('origin_forbidden', '写操作必须来自同源面板', 403)

    def cookie_header(self, token='', clear=False):
        value = f'zyb_admin={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else self.server.config.session_seconds}'
        if self.server.config.secure_cookie:
            value += '; Secure'
        return value

    def target_path(self):
        try:
            target=urlsplit(self.path)
        except ValueError:
            raise ApiError('path_invalid','HTTP 请求路径不合法')
        if target.scheme or target.netloc or target.fragment:
            raise ApiError('path_invalid','请使用不含域名或 fragment 的接口路径')
        return target.path

    def dispatch(self):
        self.check_host()
        self.source, self.client_ip, self.peer_ip = request_identity(self.client_address[0], self.headers, self.server.config.trusted_proxies)
        path = self.target_path()
        if path != '/healthz' and self.source=='external' and not self.server.store.get('allow_external',False):
            raise ApiError('external_disabled','外部访问尚未开启',403)
        if path != '/healthz':
            self.server.store.rate('peer',self.peer_ip,240,60)
        if (self.command,path) not in ROUTES:
            raise ApiError('not_found','接口不存在',404)
        if path in ASSETS:
            name,mime=ASSETS[path]
            return (Path(__file__).parent/'assets'/name).read_bytes(), {'Content-Type':mime}
        auth = self.server.auth
        if path == '/healthz':
            return {'service':'zuoyebang-gateway','version':__version__,'status':'ok'}, {}
        if path.startswith('/api/admin/'):
            if self.headers.get('Authorization'):
                raise ApiError('management_key_forbidden','调用密钥不能管理服务',403)
            if self.command == 'POST':
                self.check_origin()
            if path == '/api/admin/login':
                body = self.read_json(2048)
                token, expiry = auth.login(body.get('password'), self.client_ip)
                return {'status':'ok','csrf_token':csrf_token(token),'expires_at':expiry}, {'Set-Cookie':self.cookie_header(token)}
            token, expiry = auth.session(self.headers.get('Cookie'))
            supplied_csrf=self.headers.get('X-CSRF-Token','')
            if self.command == 'POST' and (len(self.headers.get_all('X-CSRF-Token',[]))!=1 or not supplied_csrf.isascii() or not hmac.compare_digest(supplied_csrf,csrf_token(token))):
                raise ApiError('csrf_forbidden','管理写操作缺少有效 CSRF',403)
            if path == '/api/admin/session':
                return {'status':'ok','csrf_token':csrf_token(token),'expires_at':expiry}, {}
            if path == '/api/admin/logout':
                self.read_json()
                auth.logout(token)
                return {'status':'ok'}, {'Set-Cookie':self.cookie_header(clear=True)}
            if path == '/api/admin/keys' and self.command == 'GET':
                return {'status':'ok','keys':auth.list_keys()}, {}
            if path == '/api/admin/settings' and self.command == 'GET':
                return {'status':'ok','allow_external':self.server.store.get('allow_external',False),'limits':{'api_per_minute':self.server.config.api_per_minute,'search_per_minute':self.server.config.search_per_minute,'search_daily_budget':self.server.config.search_daily_budget,'search_concurrency':self.server.config.search_concurrency}}, {}
            if path == '/api/admin/account' and self.command=='GET':
                return {'status':'ok','account':self.server.accounts.status()}, {}
            if path == '/api/admin/history':
                try:query=parse_qs(urlsplit(self.path).query,keep_blank_values=True,max_num_fields=20)
                except ValueError:raise ApiError('filter_invalid','历史筛选超过参数预算')
                return {'status':'ok',**self.server.store.history(query)}, {}
            body = self.read_json()
            if path == '/api/admin/settings':
                if type(body.get('allow_external')) is not bool or set(body)!={'allow_external'}:
                    raise ApiError('settings_invalid','外部访问开关必须为布尔值')
                self.server.store.set('allow_external',body['allow_external'])
                return {'status':'ok','allow_external':body['allow_external']}, {}
            if path == '/api/admin/keys':
                key, metadata = auth.create_key(body.get('name'))
                return {'status':'ok','key':key,'metadata':metadata}, {}
            if path == '/api/admin/keys/revoke':
                auth.revoke_key(body.get('id'))
                return {'status':'ok'}, {}
            if path == '/api/admin/credential':
                return {'status':'ok','account':self.server.accounts.import_credential(body.get('credential'))}, {}
            if path == '/api/admin/profile':
                return {'status':'ok','account':self.server.accounts.import_profile(body.get('profile'))}, {}
            if path == '/api/admin/account':
                result=self.server.accounts.operation(body.get('operation'),body.get('flow_id',''))
                return {'status':'ok','result':result,'account':self.server.accounts.status()}, {}
            raise ApiError('not_found','接口不存在',404)
        if self.headers.get('Origin') is not None:
            self.check_origin()
        if len(self.headers.get_all('Authorization',[]))!=1:
            raise ApiError('key_invalid','必须提供唯一调用密钥',401)
        self.key_id = auth.api_key(self.headers.get('Authorization'))
        self.server.store.rate('api',self.key_id,self.server.config.api_per_minute,60)
        if path=='/api/v1/search':
            limit=((self.server.config.max_image_bytes+2)//3)*4+1024
            body=self.read_json(limit)
            return {'status':'ok','result':search(self.server,body,self.key_id)}, {}
        return {'status':'ok','account':self.server.accounts.status(),'panel_url':'/'}, {}

    def handle_api(self):
        start=time.monotonic()
        now=time.time()
        self.peer_ip=self.client_address[0]; self.client_ip=self.peer_ip
        self.source='local' if ipaddress.ip_address(self.peer_ip).is_loopback else 'external'
        self.key_id=None
        heads={}; status=200; outcome='ok'
        try:
            result, heads = self.dispatch()
        except ApiError as error:
            status, outcome = error.status,error.code
            result={'status':'error','msg':error.message,'code':error.code}
        except (TimeoutError, socket.timeout):
            status, outcome = 408,'request_timeout'
            result={'status':'error','msg':'读取请求超时','code':outcome}
        except Exception:
            status, outcome = 500,'internal_error'
            result={'status':'error','msg':'服务内部错误','code':outcome}
        try:path=self.target_path()
        except ApiError:path=''
        safe_path=path if any(path==route[1] for route in ROUTES) else '/[unknown]'
        action=ACTIONS.get(path,'unknown')
        if path=='/api/admin/keys' and self.command=='GET':
            action='key_list'
        try:
            self.server.store.audit({'time':now,'method':self.command,'action':action,'path':safe_path,'source':self.source,'client_ip':self.client_ip,'peer_ip':self.peer_ip,'key_id':self.key_id,'result':outcome,'http_status':status,'latency_ms':round((time.monotonic()-start)*1000,3)})
        except Exception:
            # 审计写入失败不得静默宣告成功。
            status=503
            result={'status':'error','msg':'审计存储不可用','code':'audit_unavailable'}
        self.send_json(status,result,heads)
        self.close_connection = True

    do_GET = handle_api
    do_POST = handle_api
    do_PUT = handle_api
    do_PATCH = handle_api
    do_DELETE = handle_api
    do_OPTIONS = handle_api
    do_HEAD = handle_api

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def process_request(self,request,client_address):
        if not self.http_slots.acquire(blocking=False):
            status=429
            result={'status':'error','msg':'HTTP 并发预算已用完','code':'concurrency_limited'}
            try:
                peer=client_address[0]
                try:
                    self.store.audit({'time':time.time(),'method':'UNKNOWN','action':'overload','path':'/[overload]','source':'local' if ipaddress.ip_address(peer).is_loopback else 'external','client_ip':peer,'peer_ip':peer,'key_id':None,'result':'concurrency_limited','http_status':429,'latency_ms':0})
                except Exception:
                    status=503
                    result={'status':'error','msg':'审计存储不可用','code':'audit_unavailable'}
                payload=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
                request.settimeout(1)
                reason='Too Many Requests' if status==429 else 'Service Unavailable'
                request.sendall((f'HTTP/1.0 {status} {reason}\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: '+str(len(payload))+'\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n').encode()+payload)
            except OSError:
                pass
            finally:self.shutdown_request(request)
            return
        try:super().process_request(request,client_address)
        except Exception:
            self.http_slots.release()
            raise

    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.http_slots.release()


class IPv6Server(Server):
    address_family=socket.AF_INET6


def create_server(config):
    store = Store(config)
    cls=IPv6Server if ':' in config.bind else Server
    server = cls((config.bind, config.port), Handler)
    server.store, server.config = store, config
    server.auth = Auth(store, config)
    server.accounts = Accounts(store, config)
    server.search_slots = threading.BoundedSemaphore(config.search_concurrency)
    server.http_slots = threading.BoundedSemaphore(config.http_concurrency)
    port = server.server_port
    server.allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}', *(host.lower() for host in config.allowed_hosts)}
    if port==80:server.allowed_hosts.update({'127.0.0.1','localhost','[::1]'})
    if config.public_origin:server.allowed_hosts.add(urlsplit(config.public_origin).netloc.lower())
    return server
