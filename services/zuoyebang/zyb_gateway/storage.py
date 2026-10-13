"""受限 SQLite 与首次管理员初始化。"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import re
from .errors import ApiError


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def atomic_private(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('私有文件不允许符号链接')
    temp = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, config):
        self.config = config
        self.root = Path(config.data_dir)
        if any(parent.is_symlink() for parent in [self.root,*self.root.parents]):
            raise ValueError('私有目录及祖先不允许符号链接')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.path = self.root / 'gateway.sqlite3'
        for name in ('gateway.sqlite3','gateway.sqlite3-journal','gateway.sqlite3-wal','gateway.sqlite3-shm','admin-secret.txt','session.json','qr-login.json'):
            candidate=self.root/name
            if candidate.is_symlink() or (candidate.exists() and candidate.stat().st_nlink!=1):
                raise ValueError('私有文件及 SQLite 旁路文件不允许链接')
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires_at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS login_failures (ip TEXT NOT NULL, time REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS api_keys (id TEXT PRIMARY KEY, name TEXT NOT NULL, digest TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at REAL NOT NULL, last_used_at REAL, revoked_at REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL, method TEXT NOT NULL, action TEXT NOT NULL, path TEXT NOT NULL, source TEXT NOT NULL, client_ip TEXT NOT NULL, peer_ip TEXT NOT NULL, key_id TEXT, result TEXT NOT NULL, http_status INTEGER NOT NULL, latency_ms REAL NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS history_filters ON history (key_id, source, result, id)')
            db.execute('CREATE TABLE IF NOT EXISTS search_details (history_id INTEGER PRIMARY KEY REFERENCES history(id) ON DELETE CASCADE, grade INTEGER, image BLOB, image_meta TEXT, response_json TEXT NOT NULL, stored_bytes INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS rate_events (scope TEXT NOT NULL, identity TEXT NOT NULL, time REAL NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS rate_lookup ON rate_events (scope,identity,time)')
            if db.execute("SELECT 1 FROM settings WHERE name='admin_hash'").fetchone() is None:
                secret_path = self.root / 'admin-secret.txt'
                if secret_path.exists():
                    raise ValueError('已存在初始密码但缺管理员数据库，拒绝覆盖')
                password = secrets.token_urlsafe(36)
                atomic_private(secret_path, (password + '\n').encode())
                db.execute('INSERT INTO settings VALUES (?,?)', ('admin_hash', password_hash(password)))
                db.execute('INSERT INTO settings VALUES (?,?)', ('allow_external', 'false'))
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, name, default=None):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE name=?', (name,)).fetchone()
            return json.loads(row['value']) if row else default

    def set(self, name, value):
        with self.lock, self.connect() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value', (name,json.dumps(value,ensure_ascii=False)))

    def prune_history(self, db):
        db.execute('DELETE FROM history WHERE time < ?', (time.time()-self.config.history_days*86400,))
        db.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)', (self.config.history_limit,))
        total = db.execute('SELECT COALESCE(SUM(stored_bytes),0) FROM search_details').fetchone()[0]
        if total > self.config.history_detail_bytes:
            # 只清理最早的详情，仍保留未到期的请求元数据。
            removing = []
            for detail in db.execute('SELECT history_id,stored_bytes FROM search_details ORDER BY history_id'):
                removing.append((detail['history_id'],))
                total -= detail['stored_bytes']
                if total <= self.config.history_detail_bytes:
                    break
            db.executemany('DELETE FROM search_details WHERE history_id=?', removing)

    def audit(self, row, search_detail=None):
        fields = ('time','method','action','path','source','client_ip','peer_ip','key_id','result','http_status','latency_ms')
        with self.lock, self.connect() as db:
            inserted = db.execute('INSERT INTO history (time,method,action,path,source,client_ip,peer_ip,key_id,result,http_status,latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)', tuple(row[k] for k in fields))
            if search_detail is not None:
                response = json.dumps(search_detail['response'], ensure_ascii=False, separators=(',', ':'), allow_nan=False)
                image = search_detail.get('image')
                image_meta = json.dumps(search_detail.get('image_meta'), ensure_ascii=False, separators=(',', ':'))
                size = len(image or b'') + len(response.encode()) + len(image_meta.encode())
                if size <= self.config.history_detail_bytes:
                    db.execute('INSERT INTO search_details VALUES (?,?,?,?,?,?)', (inserted.lastrowid, search_detail.get('grade'), image, image_meta, response, size))
            self.prune_history(db)

    def history(self, query):
        allowed = {'page','page_size','source','result','key_id','action'}
        if set(query)-allowed or any(len(v)!=1 for v in query.values()):
            raise ApiError('filter_invalid','历史筛选参数不合法')
        def value(name, default=''):
            return query.get(name,[default])[0]
        try:
            page=int(value('page','1')); size=int(value('page_size','30'))
        except (ValueError,TypeError):
            raise ApiError('filter_invalid','页码不合法')
        if not 1<=page<=100000 or not 1<=size<=100:
            raise ApiError('filter_invalid','页码或分页数量超过预算')
        source, result, kid = value('source'), value('result'), value('key_id')
        action = value('action')
        if action not in ('', 'search'):
            raise ApiError('filter_invalid', '记录类型不合法')
        if source not in ('','local','external') or (result and not re.fullmatch(r'[a-z_]{2,40}',result)) or (result and result not in {'ok','error','key_invalid','external_disabled','origin_forbidden','csrf_forbidden','host_forbidden','admin_required','admin_invalid','login_limited','rate_limited','profile_missing','profile_invalid','invalid_name','invalid_key_id','key_missing','filter_invalid','settings_invalid','body_invalid','body_budget','json_invalid','json_required','not_found','request_timeout','internal_error','management_key_forbidden','proxy_invalid','network','protocol','signing_session','login_required','session_changed','upstream','dependency_missing','concurrency_limited','budget_exceeded','response_budget','image_invalid','operation_invalid','credential_invalid','flow_invalid','audit_unavailable','http_invalid','path_invalid'}) or (kid and not re.fullmatch(r'[0-9a-f]{16}',kid)):
            raise ApiError('filter_invalid','来源、结果或密钥筛选不合法')
        # 列名只来自固定白名单，值通过 SQLite 参数绑定。
        clauses=[]; params=[]
        for name,val in [('source',source),('result',result),('key_id',kid),('action',action)]:
            if val:
                if name=='result' and val=='error':
                    clauses.append('http_status>=400')
                else:
                    clauses.append(name+'=?'); params.append(val)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self.lock, self.connect() as db:
            self.prune_history(db)
            total=db.execute('SELECT COUNT(*) FROM history'+where,params).fetchone()[0]
            rows=db.execute('SELECT *,EXISTS(SELECT 1 FROM search_details WHERE history_id=history.id) AS has_detail FROM history'+where+' ORDER BY id DESC LIMIT ? OFFSET ?',[*params,size,(page-1)*size]).fetchall()
        return {'items':[{**dict(row), 'has_detail':bool(row['has_detail'])} for row in rows], 'total':total, 'page':page, 'page_size':size, 'has_more':page*size<total}

    def history_detail(self, history_id):
        with self.lock, self.connect() as db:
            self.prune_history(db)
            row = db.execute('SELECT * FROM history WHERE id=?', (history_id,)).fetchone()
            if row is None:
                raise ApiError('not_found', '该请求记录不存在或已过期', 404)
            detail = db.execute('SELECT grade,image_meta,response_json FROM search_details WHERE history_id=?', (history_id,)).fetchone()
            saved = {'grade':detail['grade'], 'image':json.loads(detail['image_meta']), 'response':json.loads(detail['response_json'])} if detail else None
        return {'item':{**dict(row), 'has_detail':detail is not None}, 'detail':saved}

    def history_image(self, history_id):
        with self.lock, self.connect() as db:
            self.prune_history(db)
            detail = db.execute('SELECT image,image_meta FROM search_details WHERE history_id=?', (history_id,)).fetchone()
            if detail is None or detail['image'] is None:
                raise ApiError('not_found', '该搜题原图未留存或已清理', 404)
        return bytes(detail['image']), json.loads(detail['image_meta'])['content_type']

    def search_budget(self,key_id):
        now=time.time()
        day_start=int(now//86400)*86400
        with self.lock,self.connect() as db:
            minute=db.execute('SELECT COUNT(*) FROM rate_events WHERE scope=? AND identity=? AND time>?',('search',key_id,now-60)).fetchone()[0]
            daily=db.execute('SELECT COUNT(*) FROM rate_events WHERE scope=? AND time>=?',('search',day_start)).fetchone()[0]
            if minute>=self.config.search_per_minute:
                raise ApiError('rate_limited','搜题频率超过每分钟限额',429)
            if daily>=self.config.search_daily_budget:
                raise ApiError('budget_exceeded','今日搜题总预算已用完',429)
            db.execute('INSERT INTO rate_events VALUES (?,?,?)',('search',key_id,now))

    def rate(self, scope, identity, limit, seconds):
        now=time.time()
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM rate_events WHERE time < ?', (now-86400,))
            count=db.execute('SELECT COUNT(*) FROM rate_events WHERE scope=? AND identity=? AND time>?',(scope,identity,now-seconds)).fetchone()[0]
            if count>=limit:
                raise ApiError('rate_limited','请求次数超过限额，请稍后重试',429)
            db.execute('INSERT INTO rate_events VALUES (?,?,?)',(scope,identity,now))
