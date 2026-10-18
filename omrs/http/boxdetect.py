"""AI框选配置和同源反代；管理会话与主站凭据隔离。"""
import hashlib
from http.cookies import SimpleCookie
import json
import re
from pathlib import Path
from urllib.parse import urlsplit,urlencode
from ..boxdetect import config,client,transport
from ..boxdetect.errors import ServiceError

PANEL_CSP="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


def public_api(path):
    return path in ('/boxdetect/healthz','/boxdetect/api/v1/status','/boxdetect/api/v1/detect')


def local_control(vault):
    from .. import traincontrol
    try:
        registered=traincontrol.registration(vault);saved=config.snapshot(vault)
        return bool(registered and saved.mode=='local' and saved.base_url==f"http://127.0.0.1:{registered['port']}")
    except (ValueError,OSError):return False


class BoxdetectRoutes:
    def _boxdetect_get(self,path,params):
        try:
            if path=='/api/boxdetect/service':
                self._json({'status':'ok','service':config.public(self.vault_path),'local_control':local_control(self.vault_path)});return
            if path=='/api/boxdetect/status':self._json({'status':'ok',**client.status(self.vault_path)});return
            self._boxdetect_proxy(path,params)
        except ServiceError as error:self._error(error)

    def _boxdetect_post(self,path):
        try:
            if path=='/api/boxdetect/service':
                saved=config.save(self.vault_path,self.services.http_io.json_body(self))
                self._json({'status':'ok','service':saved,'local_control':local_control(self.vault_path)});return
            if path=='/api/boxdetect/control':
                from .. import traincontrol
                body=self.services.http_io.json_body(self)
                if not isinstance(body,dict) or set(body)!={'action'}:raise ServiceError('控制请求只接受action')
                remote,address,_=self._security_context();session=self._active_session
                actor={'auth_mode':'pin_session' if session else 'lan_exempt' if remote else 'local','session_id':session['id'] if session else '', 'client_ip':address}
                try:
                    value=traincontrol.service_command(self.vault_path,body['action'],actor=actor)
                except traincontrol.Conflict as exc:raise ServiceError(str(exc),'busy',409) from None
                except (ValueError,OSError) as exc:raise ServiceError(str(exc),'control_failed',400) from None
                self._json({'status':'ok',**value});return
            if path=='/api/boxdetect/service/test':self._json({'status':'ok',**client.status(self.vault_path)});return
            self._boxdetect_proxy(path,{})
        except ServiceError as error:self._error(error)

    def _boxdetect_proxy(self,path,params):
        if path=='/boxdetect':
            self.send_response(302);self.send_header('Location','/boxdetect/');self.end_headers();return
        tail=path.removeprefix('/boxdetect')
        assets={'/':('index.html','text/html; charset=utf-8'),'/assets/panel.js':('panel.js','text/javascript; charset=utf-8'),'/assets/panel.css':('panel.css','text/css; charset=utf-8')}
        if self.command=='GET' and tail in assets:
            # 外部共享服务不能向OMRS同源页面提供可执行代码。
            name,mime=assets[tail]
            raw=(Path(__file__).resolve().parents[2]/'services/boxdetect/boxdetect_service/assets'/name).read_bytes()
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',PANEL_CSP)
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            self.end_headers();self.wfile.write(raw);return
        allowed={'/','/assets/panel.js','/assets/panel.css','/healthz','/api/v1/status','/api/v1/detect','/api/admin/login','/api/admin/logout','/api/admin/session','/api/admin/overview','/api/admin/keys','/api/admin/keys/revoke','/api/admin/history','/api/admin/models','/api/admin/models/apply','/api/admin/settings','/api/admin/try'}
        if tail not in allowed and not re.fullmatch(r'/api/admin/history/[1-9][0-9]{0,17}(/image)?',tail):raise ServiceError('框选接口不存在','not_found',404)
        saved=config.snapshot(self.vault_path)
        if not saved.base_url:raise ServiceError('请先在设置中填写AI框选服务地址','service_unconfigured',503)
        # 每个代理Cookie绑定配置身份，切换服务后不会向新服务器发送旧管理员令牌。
        binding=hashlib.sha256((saved.mode+'|'+saved.base_url+'|'+saved.revision).encode()).hexdigest()[:24]
        _,address,scheme=self._security_context()
        headers={'X-Forwarded-For':address}
        if public_api(path):
            authorization=self.headers.get_all('Authorization',[])
            if path.endswith('/healthz'):pass
            elif len(authorization)!=1 or not authorization[0].startswith('Bearer '):raise ServiceError('请提供唯一框选调用Key','key_invalid',401)
            else:headers['Authorization']=authorization[0]
        else:
            jar=SimpleCookie()
            try:
                jar.load(self.headers.get('Cookie',''));value=jar['omrs_boxdetect_admin'].value
                prefix,token=value.split('.',1)
                if prefix==binding and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',token):headers['Cookie']='boxdetect_admin='+token
            except (KeyError,ValueError):pass
            csrf=self.headers.get_all('X-CSRF-Token',[])
            if len(csrf)==1 and re.fullmatch(r'[a-f0-9]{64}',csrf[0]):headers['X-CSRF-Token']=csrf[0]
        if self.command=='POST':
            target=urlsplit(saved.base_url);headers['Origin']=target.scheme+'://'+target.netloc
            body=self.services.http_io.json_body(self)
        else:body=None
        suffix=('?'+urlencode(params)) if params else ''
        status,upstream,raw=transport.request(saved,self.command,tail+suffix,body,headers=headers,authenticated=False)
        config.assert_current(self.vault_path,saved)
        mime='application/json; charset=utf-8'
        if tail.endswith('/image') and status==200:
            mime=upstream.get('Content-Type','').split(';',1)[0]
            signatures={'image/png':(b'\x89PNG\r\n\x1a\n',),'image/jpeg':(b'\xff\xd8',),'image/gif':(b'GIF87a',b'GIF89a')}
            if mime not in signatures or not raw.startswith(signatures[mime]):raise ServiceError('原图响应格式不合法','service_protocol',502)
        else:
            try:
                if not isinstance(json.loads(raw),dict):raise ValueError()
            except (ValueError,UnicodeError):raise ServiceError('框选响应不符合JSON协议','service_protocol',502) from None
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',PANEL_CSP)
        if 'Set-Cookie' in upstream and not public_api(path):
            cookie=SimpleCookie();cookie.load(upstream['Set-Cookie'])
            if 'boxdetect_admin' in cookie:
                value=cookie['boxdetect_admin'].value
                if re.fullmatch(r'[A-Za-z0-9_-]{0,128}',value):
                    clear=not value
                    self.send_header('Set-Cookie',f'omrs_boxdetect_admin={binding}.{value}; Path=/boxdetect/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else 3600}'+('; Secure' if scheme=='https' else ''))
        self.end_headers();self.wfile.write(raw)
