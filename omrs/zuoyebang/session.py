"""私有设备模板与扫码账号；网络操作只使用临时快照，发布时检查世代与指纹。"""
import json
import re
import tempfile
import os
from pathlib import Path
from .. import vault_lifecycle as lifecycle
from ..locking import write_lock
from . import store
from .account import AccountClient
from .direct import SEARCH_URL, UpstreamError


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get('url') != SEARCH_URL:
        raise store.ZybError('设备会话必须使用已验收的作业帮搜题地址')
    fields, headers = profile.get('fields'), profile.get('headers')
    if not isinstance(fields, dict) or not isinstance(headers, dict):
        raise store.ZybError('设备会话缺少 fields 或 headers')
    if not all(isinstance(k, str) and isinstance(v, (str, int)) and not isinstance(v, bool)
               for k, v in fields.items()):
        raise store.ZybError('设备字段必须是字符串或整数')
    if any(not re.fullmatch(r'[A-Za-z0-9_]+', key) for key in fields):
        raise store.ZybError('设备字段名不合法')
    if not fields.get('cuid') or not fields.get('vc') or not profile.get('session_token'):
        raise store.ZybError('设备会话缺少已登记的设备标识、版本或签名种子')
    if not isinstance(profile['session_token'], str) or len(profile['session_token']) > 8192:
        raise store.ZybError('设备会话签名种子不合法')
    for key, value in headers.items():
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9-]+', key) or not isinstance(value, str) or any(c in value for c in '\r\n'):
            raise store.ZybError('设备会话请求头不合法')
        if key.lower() in ('host', 'authorization', 'proxy-authorization', 'content-length', 'transfer-encoding'):
            raise store.ZybError('设备会话包含不允许的请求头')
    return profile


def status(vault):
    with lifecycle.lease(vault):
        try:
            profile = validate_profile(json.loads(store.profile_bytes(vault)))
        except store.ZybError as exc:
            if exc.code != 'profile_missing':
                raise
            profile = None
        return {'local_session_ready': profile is not None,
                'has_account_credential': bool(profile and profile['fields'].get('ZYBUSS')),
                'observations': store.observations(vault)}


def import_profile(vault, profile):
    # 白名单结构完整校验后原子替换，任何验证失败不破坏当前账号。
    validate_profile(profile)
    if len(json.dumps(profile).encode()) > 256 * 1024:
        raise store.ZybError('设备会话文件过大')
    with lifecycle.lease(vault), write_lock():
        lifecycle.atomic_json(str(store.root(vault) / 'session.json'), profile)
        flow = store.root(vault) / 'qr-login.json'
        if flow.is_symlink():
            raise store.ZybError('扫码流程文件不允许符号链接')
        flow.unlink(missing_ok=True)
        store.observe(vault, 'profile_import')
    return status(vault)


def account_operation(vault, operation, flow_id=''):
    methods = {'verify': 'verify', 'refresh': 'relogin', 'qr_start': 'start_qr',
               'qr_poll': 'poll_qr', 'qr_cancel': 'cancel_qr'}
    if operation not in methods:
        raise store.ZybError('账号操作不合法')
    with lifecycle.task(vault):
        with lifecycle.lease(vault):
            raw = store.profile_bytes(vault)
            flow = store.read_json(store.root(vault) / 'qr-login.json', {})
        expected = store.fingerprint(raw)
        with tempfile.TemporaryDirectory(prefix='omrs-zyb-account-') as temp:
            profile = Path(temp) / 'session.json'
            profile.write_bytes(raw)
            os.chmod(profile, 0o600)
            client = AccountClient(profile)
            if flow:
                client.save_flow(flow)
            try:
                method = getattr(client, methods[operation])
                result = method(flow_id) if operation in ('qr_poll', 'qr_cancel') else method()
            except UpstreamError as exc:
                with lifecycle.lease(vault), write_lock():
                    if store.fingerprint(store.profile_bytes(vault)) == expected:
                        store.observe(vault, 'verify' if operation == 'qr_poll' else operation, exc.kind, exc.code)
                raise store.ZybError(str(exc), exc.kind, 502) from exc
            with lifecycle.lease(vault), write_lock():
                if store.fingerprint(store.profile_bytes(vault)) != expected:
                    raise store.ZybError('设备会话已更新，旧账号响应未写入，请重新操作', 'session_changed', 409)
                current_flow = store.read_json(store.root(vault) / 'qr-login.json', {})
                if operation.startswith('qr_') and current_flow != flow:
                    raise store.ZybError('扫码流程已取消或更换，旧响应未写入', 'session_changed', 409)
                next_profile = json.loads(profile.read_bytes())
                if profile.read_bytes() != raw:
                    lifecycle.atomic_json(str(store.root(vault) / 'session.json'), validate_profile(next_profile))
                if client.flow_path.exists():
                    lifecycle.atomic_json(str(store.root(vault) / 'qr-login.json'), json.loads(client.flow_path.read_bytes()))
                if result.get('server_verified'):
                    store.observe(vault, 'login' if operation == 'qr_poll' else operation)
                elif operation in ('qr_start', 'qr_cancel'):
                    store.observe(vault, operation)
            return result
