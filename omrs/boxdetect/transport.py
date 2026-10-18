"""有界固定IP HTTP，代理只转发框选会话，不携带主站凭据。"""
import http.client
import json
import socket
import ssl
import threading
import time
from .targets import parse_target,resolve_target
from .errors import ServiceError

_SLOTS=threading.BoundedSemaphore(12)


def request(config,method,path,body=None,*,headers=None,timeout=120,limit=22*1024**2,authenticated=True):
    target=parse_target(config.mode,config.base_url,config.allow_private_targets)
    if authenticated and not config.api_key: raise ServiceError('请在AI框选服务设置中填写调用Key','service_key',503)
    if not _SLOTS.acquire(blocking=False): raise ServiceError('框选服务连接繁忙，请稍后重试','service_busy',429)
    connection=timer=None;deadline=time.monotonic()+timeout;timed_out=threading.Event()
    try:
        family,address=resolve_target(config.mode,config.base_url,config.allow_private_targets,timeout=min(timeout,3))
        class Pinned(http.client.HTTPConnection):
            def connect(self):
                sock=socket.socket(family,socket.SOCK_STREAM)
                try:
                    sock.settimeout(max(.001,deadline-time.monotonic()));sock.connect(address)
                    sock.settimeout(max(.001,deadline-time.monotonic()))
                    if target.scheme=='https': sock=ssl.create_default_context().wrap_socket(sock,server_hostname=target.hostname)
                    self.sock=sock
                except BaseException: sock.close();raise
        connection=Pinned(target.hostname,target.port or (443 if target.scheme=='https' else 80),timeout=max(.001,deadline-time.monotonic()));connection.connect();sock=connection.sock
        def abort():
            timed_out.set()
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(max(.001,deadline-time.monotonic()),abort);timer.daemon=True;timer.start()
        heads={'Connection':'close','Content-Type':'application/json','Accept':'application/json',**(headers or {})}
        if authenticated:heads['Authorization']='Bearer '+config.api_key
        if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
        connection.request(method,target.path.rstrip('/')+path,body,heads)
        response=connection.getresponse()
        if 300<=response.status<400: raise ServiceError('框选服务重定向被拒绝，请直接填写最终地址','service_redirect',502)
        length=response.getheader('Content-Length')
        if length is not None and (not length.isdecimal() or int(length)>limit):raise ServiceError('框选响应超过预算','service_budget',502)
        if response.getheader('Content-Encoding','identity')!='identity':raise ServiceError('框选响应编码不支持','service_protocol',502)
        raw=bytearray()
        while not response.isclosed():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError()
            sock.settimeout(remaining);part=response.read1(min(65536,limit+1-len(raw)))
            if not part:break
            raw.extend(part)
            if len(raw)>limit:raise ServiceError('框选响应超过预算','service_budget',502)
        if timed_out.is_set() or time.monotonic()>=deadline or (length is not None and len(raw)!=int(length)):raise TimeoutError()
        return response.status,dict(response.getheaders()),bytes(raw)
    except ServiceError:raise
    except (OSError,http.client.HTTPException):raise ServiceError('无法连接框选服务或请求超时，请核对服务状态','service_network',502) from None
    finally:
        if timer:timer.cancel()
        if connection:connection.close()
        _SLOTS.release()


def json_request(config,method,path,body=None,**kwargs):
    status,headers,raw=request(config,method,path,body,**kwargs)
    failures={401:'调用Key无效或已吊销',403:'框选服务拒绝访问，请核对外部访问开关',429:'框选服务繁忙或已达到调用限额',503:'框选服务未就绪或暂停接单',409:'框选任务仍在处理或配置已变化'}
    if status!=200:raise ServiceError(failures.get(status,'框选服务处理失败'), 'service_response',status if status in (409,429,503) else 502)
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or value.get('status')!='ok':raise ValueError()
        return value
    except (ValueError,TypeError):raise ServiceError('框选响应不符合协议','service_protocol',502) from None
