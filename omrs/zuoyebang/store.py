"""作业帮独立暂存；短租约、原子发布、私有权限，不保存到源码目录。"""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from ..common import questions_root
from ..vault_lifecycle import atomic_json, lease
from ..locking import write_lock


class ZybError(ValueError):
    def __init__(self, message, code='zuoyebang', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def root(vault):
    path = Path(questions_root(os.path.realpath(vault))) / '.omrs' / 'zuoyebang'
    for parent in reversed([path, *path.parents]):
        if parent == Path(os.path.realpath(vault)) or Path(os.path.realpath(vault)) in parent.parents:
            if parent.is_symlink():
                raise ZybError('作业帮存储目录不允许符号链接')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def location(vault, identity):
    if not isinstance(identity, str) or not re.fullmatch(r'(search|render|job)-[a-f0-9]{32}', identity):
        raise ZybError('作业帮记录编号不合法')
    path = root(vault) / identity
    if path.is_symlink():
        raise ZybError('作业帮记录不允许符号链接')
    return path


def read_json(path, default=None):
    if path.is_symlink():
        raise ZybError('作业帮文件不允许符号链接')
    try:
        return json.loads(path.read_text('utf-8'))
    except FileNotFoundError:
        if default is not None:
            return default
        raise ZybError('作业帮记录不存在', status=404)


def read(vault, identity):
    with lease(vault):
        return read_json(location(vault, identity) / 'record.json')


def save(vault, identity, record):
    with lease(vault), write_lock():
        directory = location(vault, identity)
        directory.mkdir(mode=0o700, exist_ok=True)
        atomic_json(str(directory / 'record.json'), record)


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def profile_bytes(vault):
    path = root(vault) / 'session.json'
    if path.is_symlink():
        raise ZybError('设备会话文件不允许符号链接')
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise ZybError('请先导入已验收的设备会话，再扫码登录作业帮', 'profile_missing', 409)


def observations(vault):
    return read_json(root(vault) / 'observations.json', {'account': {}, 'signing': {}, 'events': []})


def observe(vault, event, kind='ok', code=None):
    """仅白名单元数据；不从上游错误字符串或配置里抄日志。"""
    allowed = {'profile_import', 'login', 'refresh', 'verify', 'search', 'qr_start', 'qr_cancel'}
    kinds = {'ok', 'login_required', 'signing_session', 'network', 'protocol', 'upstream'}
    if event not in allowed or kind not in kinds:
        return
    with lease(vault), write_lock():
        state = observations(vault)
        now = time.time()
        row = {'event': event, 'kind': kind, 'at': now}
        if type(code) is int:
            row['code'] = code
        for name in ('account', 'signing'):
            part = state[name]
            failed = kind == ('login_required' if name == 'account' else 'signing_session')
            success = kind == 'ok' and event in ('login', 'refresh', 'verify', 'search')
            if success:
                if part.get('state') == 'invalid':
                    row[name + '_recovered'] = True
                part.update(state='valid', last_success_at=now)
            elif failed:
                if part.get('state') != 'invalid':
                    part['first_invalid_at'] = now
                    part['valid_until_after'] = part.get('last_success_at')
                part['state'] = 'invalid'
            elif event == 'profile_import':
                part.clear()
                part.update(state='unknown', imported_at=now)
        state['events'].append(row)
        # 完整脱敏事件历史留在日志，界面摘要只保存最新100项。
        state['events'] = state['events'][-100:]
        atomic_json(str(root(vault) / 'observations.json'), state)
        path = root(vault) / 'session-events.jsonl'
        if path.is_symlink():
            raise ZybError('日志文件不允许符号链接')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
