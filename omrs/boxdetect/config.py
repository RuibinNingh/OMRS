"""独立框选服务连接；私有Key不进入通用配置或浏览器。"""
from dataclasses import dataclass,field
from contextlib import contextmanager
import hashlib
import json
import os
import stat
from pathlib import Path
import uuid
from urllib.parse import urlsplit,urlunsplit
from ..common import load_config,questions_root
from .. import vault_lifecycle as lifecycle
from ..locking import write_lock
from .errors import ServiceError
from .targets import parse_target


@dataclass(frozen=True)
class Snapshot:
    mode:str='local'
    base_url:str=''
    api_key:str=field(default='',repr=False)
    allow_private_targets:bool=False
    revision:str=''
    generation:int=0
    configured:bool=False


def location(vault):
    path=Path(questions_root(os.path.realpath(vault)))/'.omrs'/'boxdetect'/'service.json'
    for parent in (path,*path.parents):
        if parent.is_symlink(): raise ServiceError('框选配置目录不允许符号链接')
    return path


def validate(value):
    parse_target(value.mode,value.base_url,value.allow_private_targets)
    if not isinstance(value.api_key,str) or len(value.api_key)>4096 or any(ord(c)<33 or ord(c)>126 for c in value.api_key): raise ServiceError('调用Key格式不合法')
    return value


def snapshot(vault):
    with lifecycle.lease(vault) as generation:
        path=location(vault)
        try:
            fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                    raise ServiceError('框选私有配置必须为普通独立文件','service_config',503)
                raw=stream.read(16385)
        except FileNotFoundError:
            old=load_config(vault).get('inbox_local_detect_url','')
            if not old: return Snapshot(generation=generation)
            try:
                parsed=urlsplit(old)
                base=urlunsplit((parsed.scheme,parsed.netloc,parsed.path.removesuffix('/detect').rstrip('/'),'',''))
                local=parsed.hostname in ('localhost','127.0.0.1','::1')
                return Snapshot(mode='local' if local else 'external',base_url=base,generation=generation)
            except ValueError: return Snapshot(generation=generation)
        try:
            if len(raw)>16384: raise ValueError()
            value=json.loads(raw)
            if not isinstance(value,dict) or set(value)-{'mode','base_url','api_key','allow_private_targets','revision'}: raise ValueError()
            return validate(Snapshot(**value,generation=generation,configured=True))
        except (ValueError,TypeError): raise ServiceError('框选私有配置不可读取，请检查配置文件','service_config',503) from None


def public(vault):
    value=snapshot(vault)
    return {'mode':value.mode,'base_url':value.base_url,'allow_private_targets':value.allow_private_targets,'revision':value.revision,
            'api_key_configured':bool(value.api_key),'api_key_fingerprint':hashlib.sha256(value.api_key.encode()).hexdigest()[:12] if value.api_key else '',
            'panel_url':'/boxdetect/','configured':value.configured,'legacy':bool(value.base_url and not value.configured),
            'provider':load_config(vault).get('inbox_detect_provider','vlm')}


def save(vault,body):
    if not isinstance(body,dict) or set(body)-{'mode','base_url','api_key','allow_private_targets','clear_api_key'}: raise ServiceError('框选连接配置包含未知字段')
    if 'clear_api_key' in body and type(body['clear_api_key']) is not bool or body.get('clear_api_key') and body.get('api_key'): raise ServiceError('清除Key参数不合法或与新Key冲突')
    with _connection_guard(vault),lifecycle.lease(vault),write_lock():
        old=snapshot(vault)
        raw={k:getattr(old,k) for k in ('mode','base_url','api_key','allow_private_targets')}
        raw.update({k:v for k,v in body.items() if k in raw and (k!='api_key' or v)})
        if 'api_key' in body and not isinstance(body['api_key'],str): raise ServiceError('调用Key必须为字符串')
        if body.get('clear_api_key'): raw['api_key']=''
        if isinstance(raw['base_url'],str): raw['base_url']=raw['base_url'].rstrip('/')
        raw['revision']=uuid.uuid4().hex;validate(Snapshot(**raw))
        path=location(vault);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(path.parent,0o700)
        lifecycle.atomic_json(str(path),raw)
        return public(vault)


@contextmanager
def _connection_guard(vault):
    from .. import traincontrol
    try:
        with traincontrol.connection_guard(vault):yield
    except traincontrol.Conflict as exc:
        raise ServiceError(str(exc),'service_busy',409) from None


def assert_current(vault,expected):
    with lifecycle.lease(vault,expected.generation):
        if snapshot(vault)!=expected: raise ServiceError('框选服务配置已切换，旧结果未发布，请重新框选','service_changed',409)
