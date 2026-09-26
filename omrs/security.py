"""Remote PIN sessions and narrowly scoped report image grants."""

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import threading
import time

from .common import ATTACHMENTS_DIR, load_config, omrs_data_dir, questions_root

COOKIE_NAME = "omrs_session"
ABSOLUTE_SECONDS = 12 * 3600
DEFAULT_IDLE_MINUTES = 30
_LOCK = threading.RLock()
_SESSIONS = {}
_FAILURES = {}
_SIGNING_KEY = secrets.token_bytes(32)
_LAN_RANGES = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))


def normalize_lan_cidrs(value):
    if isinstance(value, str):
        values = [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = [item.strip() for item in value if item.strip()]
    else:
        raise ValueError("局域网免 PIN 网段必须是 CIDR 列表")
    if len(values) > 8:
        raise ValueError("局域网免 PIN 网段最多 8 个")
    normalized = []
    for item in values:
        try:
            network = ipaddress.ip_network(item, strict=True)
        except ValueError as exc:
            raise ValueError(f"无效的局域网网段: {item}") from exc
        if not any(network.subnet_of(lan) for lan in _LAN_RANGES if network.version == lan.version):
            raise ValueError(f"免 PIN 网段必须在私有局域网地址范围内: {item}")
        normalized.append(str(network))
    return list(dict.fromkeys(normalized))


def direct_lan_exempt(vault, peer, proxy_headers_present=False):
    if proxy_headers_present:
        return False
    try:
        address = ipaddress.ip_address(peer)
        raw = load_config(vault).get("lan_pin_exempt_cidrs", [])
        networks = normalize_lan_cidrs(raw)
        return any(address in ipaddress.ip_network(value) for value in networks)
    except (ValueError, TypeError):
        return False


def _path(vault):
    return os.path.join(omrs_data_dir(vault), "auth.json")


def load_auth(vault):
    try:
        with open(_path(vault), encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def auth_summary(vault):
    data = load_auth(vault)
    return {"pin_configured": bool(data.get("pin_hash")),
            "idle_minutes": int(data.get("idle_minutes", DEFAULT_IDLE_MINUTES))}


def _save(vault, data):
    path = _path(vault)
    tmp = path + ".tmp"
    descriptor = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)


def _idle_minutes(value):
    try:
        number = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("空闲时间必须为 5 到 240 分钟") from exc
    if not 5 <= number <= 240:
        raise ValueError("空闲时间必须为 5 到 240 分钟")
    return number


def set_pin(vault, pin, idle_minutes=DEFAULT_IDLE_MINUTES):
    if not isinstance(pin, str) or not pin.isascii() or not pin.isdigit() or not 4 <= len(pin) <= 12:
        raise ValueError("PIN 必须是 4 到 12 位数字")
    minutes = _idle_minutes(idle_minutes)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 600000)
    _save(vault, {"pin_hash": digest.hex(), "salt": salt.hex(), "idle_minutes": minutes})
    with _LOCK:
        _SESSIONS.clear()
    return auth_summary(vault)


def set_idle_minutes(vault, idle_minutes):
    data = load_auth(vault)
    if not data.get("pin_hash"):
        raise ValueError("请先设置 PIN")
    data["idle_minutes"] = _idle_minutes(idle_minutes)
    _save(vault, data)
    # Sessions stay valid: session_for() re-reads the idle limit on every request.
    return auth_summary(vault)


def disable_pin(vault):
    try:
        os.remove(_path(vault))
    except FileNotFoundError:
        pass
    with _LOCK:
        _SESSIONS.clear()


def verify_pin(vault, pin):
    data = load_auth(vault)
    if not data.get("pin_hash"):
        return False
    try:
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(data["salt"]), 600000)
        return hmac.compare_digest(digest, bytes.fromhex(data["pin_hash"]))
    except (ValueError, KeyError, AttributeError):
        return False


def verify_pin_limited(vault, pin, client_ip):
    """Verify a PIN under the per-IP failed-attempt limit shared with login."""
    now = time.time()
    with _LOCK:
        failures = [stamp for stamp in _FAILURES.get(client_ip, []) if now - stamp < 900]
        if len(failures) >= 5:
            raise ValueError("尝试次数过多，请 15 分钟后重试")
    if not verify_pin(vault, pin):
        with _LOCK:
            _FAILURES[client_ip] = failures + [now]
        return False
    with _LOCK:
        _FAILURES.pop(client_ip, None)
    return True


def login(vault, pin, client_ip):
    if not verify_pin_limited(vault, pin, client_ip):
        raise ValueError("PIN 错误")
    now = time.time()
    token = secrets.token_urlsafe(32)
    session = {"vault": os.path.realpath(vault), "id": secrets.token_hex(16),
               "issued": now, "last_activity": now, "warning_ack": False}
    with _LOCK:
        _SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = session
    return token, session


def session_for(vault, token):
    if not token:
        return None
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _LOCK:
        session = _SESSIONS.get(key)
        if not session:
            return None
        idle = auth_summary(vault)["idle_minutes"] * 60
        if (session["vault"] != os.path.realpath(vault) or
                now - session["issued"] >= ABSOLUTE_SECONDS or
                now - session["last_activity"] >= idle):
            _SESSIONS.pop(key, None)
            return None
        return session


def activity(session):
    with _LOCK:
        session["last_activity"] = time.time()


def logout(token):
    with _LOCK:
        _SESSIONS.pop(hashlib.sha256(token.encode()).hexdigest(), None)


def sign_image(session, name):
    expires = int(session["issued"] + ABSOLUTE_SECONDS)
    message = f'{session["id"]}\0{expires}\0{name}'.encode()
    signature = hmac.new(_SIGNING_KEY, message, hashlib.sha256).hexdigest()
    return session["id"], expires, signature


def report_image_allowed(vault, name):
    if not name or name in {".", ".."} or any(ch in name for ch in ("/", "\\", "\0")):
        return False
    root = os.path.realpath(os.path.join(questions_root(vault), ATTACHMENTS_DIR))
    path = os.path.realpath(os.path.join(root, name))
    return os.path.commonpath((root, path)) == root and os.path.isfile(path)


def valid_image_grant(vault, name, session_id, expires, signature):
    if not report_image_allowed(vault, name):
        return False
    try:
        expiry = int(expires)
    except (ValueError, TypeError):
        return False
    if expiry <= time.time():
        return False
    message = f"{session_id}\0{expiry}\0{name}".encode()
    expected = hmac.new(_SIGNING_KEY, message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        return False
    with _LOCK:
        return any(item["id"] == session_id and item["vault"] == os.path.realpath(vault)
                   and time.time() - item["last_activity"] < auth_summary(vault)["idle_minutes"] * 60
                   for item in _SESSIONS.values())


def is_loopback(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False
