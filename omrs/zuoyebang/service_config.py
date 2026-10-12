"""独立作业帮网关配置；与通用配置、旧设备会话隔离。"""
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field

from .. import vault_lifecycle as lifecycle
from ..locking import write_lock
from . import store

DEFAULT_URL = 'http://127.0.0.1:8745'


@dataclass(frozen=True)
class ServiceSnapshot:
    mode: str = 'local'
    base_url: str = DEFAULT_URL
    api_key: str = field(default='', repr=False)
    allow_private_targets: bool = False
    revision: str = ''
    generation: int = 0

    @property
    def api_key_fingerprint(self):
        return hashlib.sha256(self.api_key.encode()).hexdigest()[:12] if self.api_key else ''


def _validate(raw):
    from .targets import parse_target
    if not isinstance(raw, dict) or set(raw) - {'mode', 'base_url', 'api_key', 'allow_private_targets', 'revision'}:
        raise store.ZybError('作业帮私有配置结构不合法', 'service_config')
    value = ServiceSnapshot(**raw)
    parse_target(value.mode, value.base_url, value.allow_private_targets)
    if not isinstance(value.api_key, str) or len(value.api_key) > 4096 or any(
            ord(c) < 33 or ord(c) > 126 for c in value.api_key):
        raise store.ZybError('服务密钥不合法', 'service_config')
    if not isinstance(value.revision, str) or value.revision and not __import__('re').fullmatch(r'[a-f0-9]{32}', value.revision):
        raise store.ZybError('作业帮配置版本不合法', 'service_config')
    return value


def snapshot(vault):
    with lifecycle.lease(vault) as generation:
        path = store.root(vault) / 'service.json'
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as stream:
                if path.is_symlink() or not __import__('stat').S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError()
                raw = stream.read(16 * 1024 + 1)
                if len(raw) > 16 * 1024:
                    raise ValueError()
            value = _validate(json.loads(raw))
        except FileNotFoundError:
            value = ServiceSnapshot()
        except (OSError, ValueError, TypeError):
            raise store.ZybError('作业帮私有配置不可读取，请检查受限文件', 'service_config') from None
        return ServiceSnapshot(**{name: getattr(value, name) for name in (
            'mode', 'base_url', 'api_key', 'allow_private_targets', 'revision')}, generation=generation)


def assert_current(vault, expected):
    with lifecycle.lease(vault, expected.generation):
        if snapshot(vault) != expected:
            raise store.ZybError('作业帮服务配置已切换，旧结果未发布，请重新操作', 'service_changed', 409)


def project(value):
    return {name: getattr(value, name) for name in ('mode', 'base_url', 'allow_private_targets', 'revision')} | {
        'api_key_configured': bool(value.api_key), 'api_key_fingerprint': value.api_key_fingerprint,
        'panel_url': value.base_url.rstrip('/') + '/'}


def public(vault):
    return project(snapshot(vault))


def save(vault, data):
    if not isinstance(data, dict) or set(data) - {'mode', 'base_url', 'api_key', 'allow_private_targets', 'clear_api_key'}:
        raise store.ZybError('作业帮服务配置包含不允许的字段', 'service_config')
    if 'clear_api_key' in data and type(data['clear_api_key']) is not bool or data.get('clear_api_key') and data.get('api_key'):
        raise store.ZybError('清除密钥参数不合法或与新密钥冲突', 'service_config')
    if 'api_key' in data and not isinstance(data['api_key'], str):
        raise store.ZybError('服务密钥必须为字符串', 'service_config')
    with lifecycle.lease(vault), write_lock():
        old = snapshot(vault)
        raw = {name: getattr(old, name) for name in ('mode', 'base_url', 'api_key', 'allow_private_targets')}
        raw.update({key: value for key, value in data.items() if key in raw and (key != 'api_key' or value)})
        if data.get('clear_api_key') is True:
            raw['api_key'] = ''
        raw['base_url'] = raw['base_url'].rstrip('/') if isinstance(raw['base_url'], str) else raw['base_url']
        raw['revision'] = uuid.uuid4().hex
        _validate(raw)
        lifecycle.atomic_json(str(store.root(vault) / 'service.json'), raw)
        return public(vault)
