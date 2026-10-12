"""设备会话原子导入；账户网络快照与世代发布；仅保存脱敏观察。"""
from contextlib import contextmanager
import json
import re
import tempfile
import time
from pathlib import Path
from .errors import ApiError
from .storage import atomic_private
from .vendor.account import AccountClient,account_profile
from .vendor.direct import SEARCH_URL, UpstreamError


def validate_profile(profile):
    if not isinstance(profile,dict) or profile.get('url')!=SEARCH_URL:
        raise ApiError('profile_invalid','设备会话必须使用固定官方搜题地址')
    fields,headers=profile.get('fields'),profile.get('headers')
    if not isinstance(fields,dict) or not isinstance(headers,dict) or len(fields)>200 or len(headers)>50:
        raise ApiError('profile_invalid','设备会话缺少合法字段或请求头')
    if any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9_]+',k) or type(v) not in (str,int) or len(str(v))>16384 or '\r' in str(v) or '\n' in str(v) for k,v in fields.items()):
        raise ApiError('profile_invalid','设备字段不合法')
    if not fields.get('cuid') or not fields.get('vc') or not isinstance(profile.get('session_token'),str) or not 1<=len(profile['session_token'])<=8192:
        raise ApiError('profile_invalid','缺少已登记设备标识、版本或签名种子')
    for k,v in headers.items():
        if not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9-]+',k) or not isinstance(v,str) or any(c in v for c in '\r\n') or k.lower() in ('host','authorization','proxy-authorization','content-length','transfer-encoding','connection','upgrade'):
            raise ApiError('profile_invalid','设备请求头不合法')
    if len(json.dumps(profile).encode())>256*1024:
        raise ApiError('profile_invalid','设备会话超过 256 KiB')
    return {'url':profile['url'],'fields':fields,'headers':headers,'session_token':profile['session_token']}


class Accounts:
    def __init__(self,store,config):
        self.store,self.config=store,config
        self.path=store.root/'session.json'
        self.flow_path=store.root/'qr-login.json'

    def read_profile(self):
        if self.path.is_symlink():
            raise ApiError('profile_invalid','私有会话不允许符号链接',503)
        try:
            raw=self.path.read_bytes()
        except FileNotFoundError:
            raise ApiError('profile_missing','请先导入已登记设备会话，不能凭空生成设备',503)
        if len(raw)>256*1024:
            raise ApiError('profile_invalid','私有会话超过预算',503)
        try:
            validate_profile(json.loads(raw))
        except (ValueError,TypeError):
            raise ApiError('profile_invalid','私有会话损坏',503)
        return raw

    def status(self):
        with self.store.lock:
            try:
                profile=json.loads(self.read_profile())
            except ApiError as exc:
                if exc.code!='profile_missing':raise
                profile=None
            return {'local_session_ready':profile is not None,'has_account_credential':bool(profile and profile['fields'].get('ZYBUSS')),'observations':self.store.get('observations',{'account':{},'signing':{},'events':[]})}

    def import_profile(self,profile):
        profile=validate_profile(profile)
        with self.store.lock:
            if self.flow_path.is_symlink():
                raise ApiError('profile_invalid','扫码流程不允许符号链接',503)
            atomic_private(self.path,json.dumps(profile,ensure_ascii=False).encode())
            self.flow_path.unlink(missing_ok=True)
            self.store.set('profile_generation',self.store.get('profile_generation',0)+1)
            self.observe('profile_import')
        return self.status()

    def import_credential(self,credential):
        if not isinstance(credential,str) or not 1<=len(credential)<=8192 or any(c in credential for c in ';\r\n\t '):
            raise ApiError('credential_invalid','账号凭据不合法')
        with self.store.lock:
            profile=json.loads(self.read_profile())
            candidate=account_profile(profile,credential)
            return self.import_profile(candidate)

    def observe(self,event,kind='ok',code=None):
        if kind not in {'ok','login_required','signing_session','network','protocol','upstream'}:
            return
        with self.store.lock:
            state=self.store.get('observations',{'account':{},'signing':{},'events':[]})
            now=time.time(); row={'event':event,'kind':kind,'at':now}
            if type(code) is int:row['code']=code
            for name in ('account','signing'):
                part=state[name]
                if event=='profile_import':
                    part.clear();part.update(state='unknown',imported_at=now)
                elif kind=='ok' and event in {'verify','refresh','search','login'}:
                    if part.get('state')=='invalid':row[name+'_recovered']=True
                    part.update(state='valid',last_success_at=now)
                elif kind==('login_required' if name=='account' else 'signing_session'):
                    if part.get('state')!='invalid':
                        part.update(first_invalid_at=now,valid_until_after=part.get('last_success_at'))
                    part['state']='invalid'
            state['events']=(state['events']+[row])[-100:]
            self.store.set('observations',state)

    @contextmanager
    def snapshot(self):
        with self.store.lock:
            raw=self.read_profile()
            generation=self.store.get('profile_generation',0)
            if self.flow_path.is_symlink():
                raise ApiError('profile_invalid','扫码流程不允许符号链接',503)
            flow_raw=self.flow_path.read_bytes() if self.flow_path.exists() else b''
        with tempfile.TemporaryDirectory(prefix='.snapshot-',dir=self.store.root) as tmp:
            path=Path(tmp)/'session.json';atomic_private(path,raw)
            client=AccountClient(path)
            client.timeout=min(self.config.upstream_timeout,30)
            if flow_raw:atomic_private(client.flow_path,flow_raw)
            yield client,raw,generation,flow_raw

    def unchanged(self,raw,generation):
        return self.store.get('profile_generation',0)==generation and self.read_profile()==raw

    def operation(self,operation,flow_id=''):
        methods={'verify':'verify','refresh':'relogin','qr_start':'start_qr','qr_poll':'poll_qr','qr_cancel':'cancel_qr'}
        if not isinstance(operation,str) or operation not in methods:
            raise ApiError('operation_invalid','账号操作不合法')
        if operation in ('qr_poll','qr_cancel') and (not isinstance(flow_id,str) or not re.fullmatch(r'[0-9a-f]{32}',flow_id)):
            raise ApiError('flow_invalid','扫码流程编号不合法')
        with self.snapshot() as (client,raw,generation,flow_raw):
            try:
                method=getattr(client,methods[operation])
                result=method(flow_id) if operation in ('qr_poll','qr_cancel') else method()
            except UpstreamError as exc:
                with self.store.lock:
                    if self.unchanged(raw,generation):self.observe('verify' if operation=='qr_poll' else operation,exc.kind,exc.code)
                raise safe_upstream(exc)
            except (ValueError,KeyError,TypeError,OSError):
                raise ApiError('protocol','官方账号响应或流程不合法',502)
            with self.store.lock:
                if not self.unchanged(raw,generation):
                    raise ApiError('session_changed','设备会话已更换，旧结果未发布',409)
                current_flow=self.flow_path.read_bytes() if self.flow_path.exists() else b''
                if operation.startswith('qr_') and current_flow!=flow_raw:
                    raise ApiError('session_changed','扫码流程已取消或更换，旧结果未发布',409)
                new_raw=client.client.path.read_bytes()
                if new_raw!=raw:
                    validate_profile(json.loads(new_raw))
                    atomic_private(self.path,new_raw)
                    self.store.set('profile_generation',generation+1)
                # 检查/刷新只发布账号；它们携带的旧二维码快照不能恢复已取消或替换的流程。
                if operation.startswith('qr_') and client.flow_path.exists():
                    atomic_private(self.flow_path,client.flow_path.read_bytes())
                if result.get('server_verified'):self.observe('login' if operation=='qr_poll' else operation)
                elif operation in ('qr_start','qr_cancel'):self.observe(operation)
            return result


def safe_upstream(exc):
    errors={
        'network':('无法连接官方服务，请稍后手动重试',502),
        'protocol':('官方响应超过预算或格式已变化',502),
        'signing_session':('签名会话已失效，请导入已更新的设备会话',502),
        'login_required':('官方账号需要重新登录',502),
        'session_changed':('设备会话已更换，请重新操作',409),
    }
    code=exc.kind if exc.kind in errors else 'upstream'
    message,status=errors.get(code,('官方服务返回错误',502))
    return ApiError(code,message,status)
