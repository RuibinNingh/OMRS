"""独立管理员鉴权、API 密钥摘要与同源保护。"""
import hashlib
import hmac
import ipaddress
from http.cookies import SimpleCookie
import secrets
import time
from .errors import ApiError
from .storage import password_hash


def request_identity(peer, headers, trusted_proxies):
    def address(value):
        addr = ipaddress.ip_address(value)
        return addr.ipv4_mapped if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped else addr
    peer_ip = address(peer)
    networks = [ipaddress.ip_network(net, strict=True) for net in trusted_proxies]
    def trusted(addr):
        return any(addr in net for net in networks)
    client = peer_ip
    if trusted(peer_ip) and headers.get('X-Forwarded-For') is not None:
        try:
            raw = headers.get('X-Forwarded-For')
            if len(raw)>1024 or len(headers.get_all('X-Forwarded-For', []))!=1:
                raise ValueError('multiple')
            chain = [address(part.strip()) for part in raw.split(',')]
            if not 1<=len(chain)<=16:
                raise ValueError('chain')
            for entry in reversed(chain):
                if not trusted(client):
                    break
                client = entry
        except ValueError:
            raise ApiError('proxy_invalid','可信代理的转发 IP 不合法')
    # 即使可信远端代理声称 127.0.0.1，socket 外部来源仍然是 external。
    source = 'local' if peer_ip.is_loopback and client.is_loopback else 'external'
    return source,str(client),str(peer_ip)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token):
    return digest('csrf:' + token)


class Auth:
    def __init__(self, store, config):
        self.store, self.config = store, config

    def login(self, password, ip):
        now = time.time()
        with self.store.lock, self.store.connect() as db:
            db.execute('DELETE FROM login_failures WHERE time < ?', (now - self.config.login_window,))
            count = db.execute('SELECT COUNT(*) FROM login_failures WHERE ip=?', (ip,)).fetchone()[0]
            global_count = db.execute('SELECT COUNT(*) FROM login_failures').fetchone()[0]
            if count >= self.config.login_failures or global_count >= 50:
                raise ApiError('login_limited', '登录失败次数过多，请稍后重试', 429)
            row = db.execute("SELECT value FROM settings WHERE name='admin_hash'").fetchone()
            stored = row[0]
            if not isinstance(password, str) or not 8 <= len(password) <= 256:
                candidate = ''
            else:
                candidate = password_hash(password, stored.split(':')[0])
            if not hmac.compare_digest(stored, candidate):
                db.execute('INSERT INTO login_failures VALUES (?,?)', (ip, now))
                # 失败记录必须提交，不能被异常回滚。
                db.commit()
                raise ApiError('admin_invalid', '管理员认证失败', 401)
            db.execute('DELETE FROM login_failures WHERE ip=?', (ip,))
            db.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
            token = secrets.token_urlsafe(32)
            expiry = now + self.config.session_seconds
            db.execute('INSERT INTO sessions VALUES (?,?)', (digest(token), expiry))
        return token, expiry

    def session(self, cookie):
        try:
            cookies = SimpleCookie()
            cookies.load(cookie or '')
            token = cookies['zyb_admin'].value
        except (KeyError, ValueError):
            raise ApiError('admin_required', '请先登录管理面板', 401)
        if len(token) > 128:
            raise ApiError('admin_required', '请先登录管理面板', 401)
        with self.store.lock, self.store.connect() as db:
            row = db.execute('SELECT expires_at FROM sessions WHERE digest=? AND expires_at>?', (digest(token), time.time())).fetchone()
        if not row:
            raise ApiError('admin_required', '管理会话已过期，请重新登录', 401)
        return token, row[0]

    def logout(self, token):
        with self.store.lock, self.store.connect() as db:
            db.execute('DELETE FROM sessions WHERE digest=?', (digest(token),))

    @staticmethod
    def key_metadata(row):
        return {**{key:row[key] for key in ('id','name','prefix','fingerprint','created_at','last_used_at','revoked_at')}, 'state':'revoked' if row['revoked_at'] else 'active'}

    def create_key(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c)<32 for c in name):
            raise ApiError('invalid_name', '密钥名称须为 1 至 80 个字符')
        key = 'zyb_' + secrets.token_urlsafe(32)
        kid = secrets.token_hex(8)
        fingerprint = digest(key)[:12]
        with self.store.lock, self.store.connect() as db:
            db.execute('INSERT INTO api_keys VALUES (?,?,?,?,?,?,NULL,NULL)', (kid, name.strip(), digest(key), key[:10], fingerprint, time.time()))
            row = db.execute('SELECT * FROM api_keys WHERE id=?', (kid,)).fetchone()
        return key, self.key_metadata(row)

    def list_keys(self):
        with self.store.lock, self.store.connect() as db:
            return [self.key_metadata(row) for row in db.execute('SELECT * FROM api_keys ORDER BY created_at DESC')]

    def revoke_key(self, kid):
        if not isinstance(kid, str) or len(kid) != 16:
            raise ApiError('invalid_key_id', '密钥编号不合法')
        with self.store.lock, self.store.connect() as db:
            changed = db.execute('UPDATE api_keys SET revoked_at=COALESCE(revoked_at,?) WHERE id=?', (time.time(), kid)).rowcount
        if not changed:
            raise ApiError('key_missing', '密钥不存在', 404)

    def api_key(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer ') or len(authorization)>128:
            raise ApiError('key_invalid', '调用密钥无效或已吊销', 401)
        key = authorization[7:]
        with self.store.lock, self.store.connect() as db:
            row = db.execute('SELECT * FROM api_keys WHERE digest=? AND revoked_at IS NULL', (digest(key),)).fetchone()
            if row:
                db.execute('UPDATE api_keys SET last_used_at=? WHERE id=?', (time.time(), row['id']))
        if not row:
            raise ApiError('key_invalid', '调用密钥无效或已吊销', 401)
        return row['id']
