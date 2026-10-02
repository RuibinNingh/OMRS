"""MCP API Key 的生命周期管理。

密钥只在创建响应中返回一次。持久化文件使用 0600 权限，保存 SHA-256
摘要和非秘密元数据；每次调用都会重新读取并校验状态，所以吊销会立即
使已有 MCP 会话失效。
"""
from ..vault_lifecycle import storage, open_sqlite, lease, task, generation

import datetime
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import threading
import uuid

from ..common import omrs_data_dir

_LOCK = threading.RLock()
_FILENAME = "mcp_keys.json"
_SCOPES = ("omrs:read", "draft:create", "draft:update", "report:create", "board:write", "board:delete")
_DEFAULT_SCOPES = ("omrs:read", "draft:create")


@storage
@contextlib.contextmanager
def _key_lock(vault):
    """串行化 Web 与本机 CLI 的 Key 生命周期，避免吊销被使用时间覆盖。"""
    with _LOCK:
        path = _path(vault) + ".lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


@storage
def _path(vault):
    return os.path.join(omrs_data_dir(vault), _FILENAME)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


@storage
def _load(vault):
    try:
        with open(_path(vault), encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            return {"keys": []}
        # 鉴权文件属于本地可编辑数据；损坏的单条记录不能让整个 MCP
        # 端点抛出 500 或绕过其余有效 Key。
        return {"keys": [row for row in data["keys"] if isinstance(row, dict)]}
    except (OSError, ValueError):
        return {"keys": []}


@storage
def _save(vault, data):
    path = _path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    descriptor = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _scopes(value):
    if value is None:
        return list(_DEFAULT_SCOPES)
    if isinstance(value, str):
        value = [item for item in value.replace(",", " ").split() if item]
    if not isinstance(value, list) or not value or any(item not in _SCOPES for item in value):
        raise ValueError("scope 必须是已登记的 MCP 权限")
    return list(dict.fromkeys(value))


def _public(row):
    return {key: row.get(key) for key in (
        "key_id", "name", "prefix", "scopes", "created_at", "expires_at", "revoked_at", "last_used_at",
    )}


@storage
def create_key(vault, name="", scopes=None, expires_at=None):
    """创建密钥并返回一次性明文 ``secret``。"""
    name = str(name or "").strip()
    if len(name) > 80:
        raise ValueError("密钥名称不能超过 80 个字符")
    scopes = _scopes(scopes)
    if expires_at:
        expires_at = str(expires_at).strip()
        try:
            parsed = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            expires_at = parsed.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()
        except ValueError as exc:
            raise ValueError("expires_at 必须是 ISO-8601 时间") from exc
        if parsed <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("expires_at 必须晚于当前时间")
    key_id = "mcp_" + uuid.uuid4().hex[:16]
    secret = "omrs_mcp_" + key_id + "_" + secrets.token_urlsafe(32)
    row = {"key_id": key_id, "name": name or key_id, "prefix": secret[:18],
           "secret_sha256": hashlib.sha256(secret.encode()).hexdigest(), "scopes": scopes,
           "created_at": _now(), "expires_at": expires_at, "revoked_at": None, "last_used_at": None}
    with _key_lock(vault):
        data = _load(vault)
        data["keys"].append(row)
        _save(vault, data)
    return {**_public(row), "secret": secret}


@storage
def list_keys(vault):
    with _key_lock(vault):
        return [_public(row) for row in _load(vault)["keys"] if isinstance(row, dict)]


@storage
def revoke_key(vault, key_id):
    key_id = str(key_id or "").strip()
    with _key_lock(vault):
        data = _load(vault)
        for row in data["keys"]:
            if row.get("key_id") == key_id:
                if not row.get("revoked_at"):
                    row["revoked_at"] = _now()
                    _save(vault, data)
                return _public(row)
    raise ValueError("MCP Key 不存在")


@storage
def verify_key(vault, secret):
    """校验密钥并返回公开身份；失败统一返回 ``None``。"""
    if not isinstance(secret, str) or not secret or len(secret) > 512:
        return None
    digest = hashlib.sha256(secret.encode()).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc)
    with _key_lock(vault):
        data = _load(vault)
        for row in data["keys"]:
            stored = str(row.get("secret_sha256") or "")
            if len(stored) != 64 or any(ch not in "0123456789abcdef" for ch in stored):
                continue
            if not hmac.compare_digest(stored, digest):
                continue
            key_id = row.get("key_id")
            if (not isinstance(key_id, str) or len(key_id) != 20 or not key_id.startswith("mcp_") or
                    any(ch not in "0123456789abcdef" for ch in key_id[4:])):
                return None
            if row.get("revoked_at"):
                return None
            scopes = row.get("scopes")
            if not isinstance(scopes, list) or not scopes or any(value not in _SCOPES for value in scopes):
                return None
            expiry = row.get("expires_at")
            if expiry:
                try:
                    parsed = datetime.datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                    if parsed <= now:
                        return None
                except ValueError:
                    return None
            used_at = _now()
            if row.get("last_used_at") != used_at:
                row["last_used_at"] = used_at
                _save(vault, data)
            return _public(row)
    return None


@storage
def key_for_id(vault, key_id):
    with _key_lock(vault):
        for row in _load(vault)["keys"]:
            if row.get("key_id") == key_id:
                return _public(row)
    return None


@storage
def active_key(vault, key_id):
    """网页确认只凭稳定编号重新鉴权，不存储或恢复明文凭据。"""
    return _active(key_for_id(vault, key_id))


def _active(row):
    if not row or row.get('revoked_at'):
        return None
    scopes = row.get('scopes')
    if not isinstance(scopes, list) or not scopes or any(scope not in _SCOPES for scope in scopes):
        return None
    if row.get('expires_at'):
        try:
            expiry = datetime.datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
            expiry = expiry.replace(tzinfo=datetime.timezone.utc) if expiry.tzinfo is None else expiry
            if expiry <= datetime.datetime.now(datetime.timezone.utc):
                return None
        except (ValueError, TypeError):
            return None
    return row


@storage
def update_scopes(vault, key_id, scopes):
    """只编辑有效密钥的权限，吊销和到期均不可复活。"""
    scopes = _scopes(scopes)
    with _key_lock(vault):
        data = _load(vault)
        row = next((item for item in data['keys'] if item.get('key_id') == key_id), None)
        if not _active(row):
            raise ValueError('密钥不存在、已吊销或已到期，不能编辑权限')
        row['scopes'] = scopes
        _save(vault, data)
        return _public(row)
