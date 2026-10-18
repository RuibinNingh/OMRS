"""单监听框选服务：独立管理员面板、调用鉴权与整图历史。"""
import argparse
import hmac
import ipaddress
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .config import Config
from .errors import ApiError
from .security import Auth, csrf_token, request_identity
from .storage import Store, atomic_private, password_hash
from .runtime import Runtime
from .inference import Detector
from .model import ROLES, sha256

MAX_BODY = 22 * 1024 * 1024
ASSETS = {'/':('index.html','text/html; charset=utf-8'),'/assets/panel.js':('panel.js','text/javascript; charset=utf-8'),'/assets/panel.css':('panel.css','text/css; charset=utf-8')}

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON field')
        result[key]=value
    return result


SECURITY_HEADERS = {
    'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY',
    'Referrer-Policy':'no-referrer', 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}

class Handler(BaseHTTPRequestHandler):
    server_version = 'Boxdetect'
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
        value = f'boxdetect_admin={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else self.server.config.session_seconds}'
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
        source,client,peer=request_identity(self.client_address[0],self.headers,self.server.config.trusted_proxies)
        path=self.target_path();runtime=self.server.runtime;store=self.server.store;auth=self.server.auth
        if path=='/healthz' and self.command=='GET': return {'status':'ok','service':'boxdetect'},{}
        if source=='external' and not store.get('allow_external',False): raise ApiError('external_disabled','外部访问尚未开启',403)
        store.rate('peer',peer,240)
        if path in ASSETS and self.command=='GET':
            name,mime=ASSETS[path]
            return (Path(__file__).parent/'assets'/name).read_bytes(),{'Content-Type':mime}
        if path.startswith('/api/admin/'):
            if self.headers.get('Authorization'): raise ApiError('management_key_forbidden','调用Key不能管理框选服务',403)
            if self.command=='POST': self.check_origin()
            if path=='/api/admin/login' and self.command=='POST':
                body=self.read_json(2048);token,expiry=auth.login(body.get('password'),client)
                return {'status':'ok','csrf_token':csrf_token(token),'expires_at':expiry},{'Set-Cookie':self.cookie_header(token)}
            token,expiry=auth.session(self.headers.get('Cookie'))
            supplied=self.headers.get('X-CSRF-Token','')
            if self.command=='POST' and (len(self.headers.get_all('X-CSRF-Token',[]))!=1 or not supplied.isascii() or not hmac.compare_digest(supplied,csrf_token(token))): raise ApiError('csrf_forbidden','管理操作缺少有效CSRF',403)
            if self.command=='GET':
                if path=='/api/admin/session': return {'status':'ok','csrf_token':csrf_token(token),'expires_at':expiry},{}
                if path=='/api/admin/overview': return {'status':'ok',**runtime.status(),**store.stats()},{}
                if path=='/api/admin/keys': return {'status':'ok','keys':auth.list_keys(),**store.stats()},{}
                if path=='/api/admin/models':
                    with store.lock,store.connect() as db: history=[dict(r) for r in db.execute('SELECT * FROM operations ORDER BY time DESC LIMIT 30')]
                    return {'status':'ok','models':runtime.models(),'revision':runtime.revision,'history':history},{}
                if path=='/api/admin/settings': return {'status':'ok','allow_external':store.get('allow_external',False),**runtime.status()},{}
                if path=='/api/admin/history':
                    try:
                        pairs=parse_qs(urlsplit(self.path).query,keep_blank_values=True,max_num_fields=10)
                        if any(len(v)!=1 for v in pairs.values()): raise ValueError()
                        query={k:v[0] for k,v in pairs.items()}
                    except ValueError: raise ApiError('filter_invalid','历史筛选参数不合法')
                    return {'status':'ok',**store.history(query)},{}
                import re
                match=re.fullmatch(r'/api/admin/history/([1-9][0-9]{0,17})(/image)?',path)
                if match:
                    if match[2]:
                        data,mime=store.detail(int(match[1]),image=True);return data,{'Content-Type':mime}
                    return {'status':'ok',**store.detail(int(match[1]))},{}
            elif self.command=='POST':
                body=self.read_json(MAX_BODY if path=='/api/admin/try' else 16384)
                if path=='/api/admin/logout':
                    auth.logout(token);return {'status':'ok'},{'Set-Cookie':self.cookie_header(clear=True)}
                if path=='/api/admin/keys':
                    key,meta=auth.create_key(body.get('name'));return {'status':'ok','key':key,'metadata':meta},{}
                if path=='/api/admin/keys/revoke': auth.revoke_key(body.get('id'));return {'status':'ok'},{}
                if path=='/api/admin/try':
                    value,status=runtime.detect({**body,'source':'test'},'admin',client,peer)
                    return value,{'_status':status}
                if path=='/api/admin/models/apply': return {'status':'ok','operation':runtime.apply(body,'session:'+__import__('hashlib').sha256(token.encode()).hexdigest()[:12]+' @ '+client)},{}
                if path=='/api/admin/settings':
                    if not body or set(body)-{'allow_external','paused','per_key_per_minute','history_retention'}: raise ApiError('settings_invalid','服务设置包含未知字段')
                    for name in ('allow_external','paused'):
                        if name in body and type(body[name]) is not bool: raise ApiError('settings_invalid','开关必须为布尔值')
                    if 'per_key_per_minute' in body and (type(body['per_key_per_minute']) is not int or not 1<=body['per_key_per_minute']<=100): raise ApiError('settings_invalid','每Key每分钟次数须为1到100')
                    if 'history_retention' in body:
                        keep=body['history_retention'];bounds={'days':(1,365),'limit':(1,100000),'detail_bytes':(1,2*1024**3)}
                        if not isinstance(keep,dict) or set(keep)!=set(bounds) or any(type(keep[n]) is not int or not lo<=keep[n]<=hi for n,(lo,hi) in bounds.items()): raise ApiError('settings_invalid','记录保留设置不合法')
                    with store.lock,store.connect() as db:
                        for k,v in body.items(): db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',('retention' if k=='history_retention' else k,json.dumps(v)))
                    return {'status':'ok'},{}
            raise ApiError('not_found','接口不存在',404)
        if path not in ('/health','/detect','/api/v1/status','/api/v1/detect') or (self.command=='GET')!=(path in ('/health','/api/v1/status')): raise ApiError('not_found','接口不存在',404)
        legacy=self.server.config.legacy_loopback and source=='local' and path in ('/health','/detect') and not self.headers.get('Authorization')
        if not legacy:
            if self.headers.get('Origin') is not None: self.check_origin()
            if len(self.headers.get_all('Authorization',[]))!=1: raise ApiError('key_invalid','请提供唯一调用Key',401)
            kid=auth.api_key(self.headers.get('Authorization'))
        else: kid='legacy'
        if self.command=='GET': return ({'file':'model.onnx',**{k:runtime.metadata[k] for k in ('name','sha256','classes','imgsz','conf')}} if path=='/health' else {'status':'ok',**runtime.status()}),{}
        result,status=runtime.detect(self.read_json(MAX_BODY),kid,client,peer,legacy=path=='/detect')
        if not legacy: auth.api_key(self.headers.get('Authorization'))
        return result,{'_status':status}

    def handle_api(self):
        extra={};status=200
        try: result,extra=self.dispatch();status=extra.pop('_status',200)
        except ApiError as exc: result={'status':'error','code':exc.code,'msg':exc.message};status=exc.status
        except (TimeoutError,socket.timeout): result={'status':'error','code':'request_timeout','msg':'请求读取超时'};status=408
        except Exception: result={'status':'error','code':'internal_error','msg':'服务内部错误，请检查私有存储和模型'};status=503
        self.send_json(status,result,extra);self.close_connection=True

    do_GET=handle_api
    do_POST=handle_api
    do_HEAD=handle_api


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            try: request.sendall(b'HTTP/1.0 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError: pass
            self.shutdown_request(request);return
        try: super().process_request(request,address)
        except BaseException: self.slots.release();raise
    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()


def make_server(model_dir,port,*,config=None,data_dir=None,legacy=False):
    config=config or Config(data_dir=Path(data_dir) if data_dir else Path.home()/'.local/share/omrs-boxdetect',port=port,legacy_loopback=legacy)
    store=Store(config)
    runtime=Runtime(model_dir,config,store,Detector)
    cls=Server
    if ':' in config.bind:
        class IPv6Server(Server): address_family=socket.AF_INET6
        cls=IPv6Server
    http=cls((config.bind,config.port),Handler)
    http.config,http.store,http.runtime=config,store,runtime
    http.auth=Auth(store,config);http.slots=threading.BoundedSemaphore(config.http_concurrency)
    number=http.server_port
    http.allowed_hosts={f'127.0.0.1:{number}',f'localhost:{number}',f'[::1]:{number}',*config.allowed_hosts}
    if config.public_origin: http.allowed_hosts.add(urlsplit(config.public_origin).netloc.lower())
    return http


def add_arguments(parser):
    parser.add_argument('--model-dir',default=str(Path.home()/'omrs-train/models/current'))
    parser.add_argument('--port',type=int,default=18765)
    parser.add_argument('--data-dir',default=str(Path.home()/'.local/share/omrs-boxdetect'))
    parser.add_argument('--bind',default='127.0.0.1')
    parser.add_argument('--models-dir')
    parser.add_argument('--public-origin',default='')
    parser.add_argument('--secure-cookie',action='store_true')
    parser.add_argument('--trusted-proxy',action='append',default=['127.0.0.1/32','::1/128'])
    parser.add_argument('--allow-host',action='append',default=[])
    parser.add_argument('--legacy-loopback',action='store_true',help='显式兼容本机旧协议；公网仍须Key')
    parser.add_argument('--allow-external',action='store_true')


def run(args):
    config=Config(data_dir=Path(args.data_dir),port=args.port,bind=args.bind,models_dir=Path(args.models_dir) if args.models_dir else None,
                  public_origin=args.public_origin,secure_cookie=args.secure_cookie,trusted_proxies=tuple(args.trusted_proxy),allowed_hosts=tuple(args.allow_host),legacy_loopback=args.legacy_loopback)
    http=make_server(args.model_dir,args.port,config=config)
    if args.allow_external: http.store.set('allow_external',True)
    print(json.dumps({'host':config.bind,'port':http.server_port,'admin_secret_file':str(http.store.root/'admin-secret.txt')},ensure_ascii=False),flush=True)
    try: http.serve_forever()
    except KeyboardInterrupt: pass
    finally: http.server_close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);add_arguments(parser);run(parser.parse_args(argv))


if __name__=='__main__': main()
