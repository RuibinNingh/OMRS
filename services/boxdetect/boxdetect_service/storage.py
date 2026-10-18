"""框选服务私有库：管理员、调用密钥、原图回执与有界保留。"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from .errors import ApiError


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def atomic_private(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('私有文件不能是符号链接')
    temporary = path.with_name('.' + path.name + secrets.token_hex(8))
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Store:
    def __init__(self, config):
        self.config = config
        self.root = Path(config.data_dir)
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('私有目录不能经过符号链接')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.path = self.root / 'boxdetect.sqlite3'
        for name in ('boxdetect.sqlite3', 'boxdetect.sqlite3-journal', 'boxdetect.sqlite3-wal', 'boxdetect.sqlite3-shm', 'admin-secret.txt'):
            p = self.root / name
            if p.is_symlink() or (p.exists() and p.stat().st_nlink != 1):
                raise ValueError('私有文件不能是链接')
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS login_failures(ip TEXT NOT NULL,time REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS api_keys(id TEXT PRIMARY KEY,name TEXT NOT NULL,digest TEXT UNIQUE NOT NULL,prefix TEXT NOT NULL,fingerprint TEXT NOT NULL,created_at REAL NOT NULL,last_used_at REAL,revoked_at REAL);
                CREATE TABLE IF NOT EXISTS rate_events(scope TEXT NOT NULL,identity TEXT NOT NULL,time REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS rate_lookup ON rate_events(scope,identity,time);
                CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL NOT NULL,finished_at REAL,key_id TEXT NOT NULL,request_id TEXT NOT NULL,input_hash TEXT NOT NULL,source TEXT NOT NULL,client_ip TEXT NOT NULL,peer_ip TEXT NOT NULL,state TEXT NOT NULL,http_status INTEGER NOT NULL DEFAULT 202,elapsed_ms INTEGER NOT NULL DEFAULT 0,model TEXT NOT NULL,response TEXT,UNIQUE(key_id,request_id));
                CREATE TABLE IF NOT EXISTS details(request_id INTEGER PRIMARY KEY REFERENCES requests(id) ON DELETE CASCADE,image BLOB,image_meta TEXT NOT NULL,stored_bytes INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,time REAL NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,state TEXT NOT NULL,before_model TEXT,after_model TEXT,error TEXT,body_hash TEXT NOT NULL);
            ''')
            if db.execute("SELECT 1 FROM settings WHERE name='admin_hash'").fetchone() is None:
                if (self.root/'admin-secret.txt').exists():
                    raise ValueError('初始密码已存在但管理员库缺失，拒绝覆盖')
                password = secrets.token_urlsafe(36)
                atomic_private(self.root/'admin-secret.txt', (password+'\n').encode())
                db.execute('INSERT INTO settings VALUES (?,?)', ('admin_hash', password_hash(password)))
            db.execute("UPDATE requests SET state='interrupted',http_status=503,finished_at=?,response=? WHERE state='running'", (time.time(), json.dumps({'status':'error','code':'interrupted','msg':'服务重启，框选已中断，请重新提交'})))
            db.execute("UPDATE operations SET state='interrupted',error='模型操作被进程重启中断，请核对当前模型' WHERE state='running'")
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
            return json.loads(row[0]) if row else default

    def set(self, name, value):
        with self.lock, self.connect() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value', (name,json.dumps(value,ensure_ascii=False)))

    def rate(self, scope, identity, limit, seconds=60):
        now=time.time()
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM rate_events WHERE time<?',(now-86400,))
            count=db.execute('SELECT COUNT(*) FROM rate_events WHERE scope=? AND identity=? AND time>?',(scope,identity,now-seconds)).fetchone()[0]
            if count>=limit:
                raise ApiError('rate_limited','调用频率超过限额，请稍后重试',429)
            db.execute('INSERT INTO rate_events VALUES (?,?,?)',(scope,identity,now))

    def retention(self):
        return self.get('retention', {'days':self.config.history_days,'limit':self.config.history_limit,'detail_bytes':self.config.history_detail_bytes})

    def prune(self, db):
        keep=self.retention()
        db.execute("DELETE FROM requests WHERE state!='running' AND time<?",(time.time()-keep['days']*86400,))
        db.execute("DELETE FROM requests WHERE state!='running' AND id NOT IN (SELECT id FROM requests ORDER BY id DESC LIMIT ?)",(keep['limit'],))
        total=db.execute('SELECT COALESCE(SUM(stored_bytes),0) FROM details').fetchone()[0]
        for row in db.execute('SELECT request_id,stored_bytes FROM details ORDER BY request_id').fetchall():
            if total<=keep['detail_bytes']: break
            db.execute('DELETE FROM details WHERE request_id=?',(row['request_id'],)); total-=row['stored_bytes']

    def begin(self, key_id, request_id, input_hash, source, client_ip, peer_ip, model):
        with self.lock, self.connect() as db:
            row=db.execute('SELECT * FROM requests WHERE key_id=? AND request_id=?',(key_id,request_id)).fetchone()
            if row:
                if row['input_hash']!=input_hash:
                    raise ApiError('request_conflict','相同请求编号不能用于不同图片',409)
                if row['state']=='running':
                    raise ApiError('request_running','该次框选仍在处理中，请稍后按原编号重试',409)
                return row['id'],json.loads(row['response']),row['http_status']
            cursor=db.execute('INSERT INTO requests(time,key_id,request_id,input_hash,source,client_ip,peer_ip,state,model) VALUES (?,?,?,?,?,?,?,\'running\',?)',(time.time(),key_id,request_id,input_hash,source,client_ip,peer_ip,json.dumps(model,ensure_ascii=False)))
            return cursor.lastrowid,None,None

    def image(self, ident, data, meta):
        metadata=json.dumps(meta,ensure_ascii=False)
        with self.lock, self.connect() as db:
            size=len(data)+len(metadata.encode())
            if size<=self.retention()['detail_bytes']:
                db.execute('INSERT INTO details VALUES (?,?,?,?)',(ident,data,metadata,size))
            self.prune(db)

    def finish(self, ident, response, status, elapsed):
        with self.lock, self.connect() as db:
            db.execute('UPDATE requests SET finished_at=?,state=?,http_status=?,elapsed_ms=?,response=? WHERE id=?',(time.time(),'success' if status==200 else 'failure',status,elapsed,json.dumps(response,ensure_ascii=False,allow_nan=False),ident))
            self.prune(db)

    def history(self, query):
        if set(query)-{'page','key_id','state','source','q'}:
            raise ApiError('filter_invalid','历史筛选参数不合法')
        try: page=int(query.get('page','1'))
        except (ValueError,TypeError): raise ApiError('filter_invalid','页码不合法')
        if not 1<=page<=100000: raise ApiError('filter_invalid','页码超过范围')
        clauses=[];values=[]
        for name in ('key_id','state','source'):
            value=query.get(name,'')
            if value:
                if name=='state' and value not in ('running','success','failure','interrupted'): raise ApiError('filter_invalid','结果筛选不合法')
                if name=='source' and value not in ('inbox','draft','test','api','legacy'): raise ApiError('filter_invalid','来源筛选不合法')
                clauses.append('r.'+name+'=?');values.append(value)
        q=query.get('q','')
        if len(q)>100: raise ApiError('filter_invalid','搜索文字过长')
        if q:
            clauses.append('(instr(r.client_ip,?)>0 OR instr(r.request_id,?)>0 OR instr(COALESCE(k.name,\'\'),?)>0)');values.extend([q]*3)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self.lock,self.connect() as db:
            self.prune(db)
            total=db.execute('SELECT COUNT(*) FROM requests r LEFT JOIN api_keys k ON k.id=r.key_id'+where,values).fetchone()[0]
            rows=db.execute('SELECT r.*,k.name AS key_name,EXISTS(SELECT 1 FROM details d WHERE d.request_id=r.id) AS has_image FROM requests r LEFT JOIN api_keys k ON k.id=r.key_id'+where+' ORDER BY r.id DESC LIMIT 20 OFFSET ?',[*values,(page-1)*20]).fetchall()
        items=[]
        for row in rows:
            item=dict(row);item.pop('response');item.pop('input_hash');item['model']=json.loads(item['model']);items.append(item)
        return {'items':items,'total':total,'page':page,'has_more':page*20<total}

    def detail(self, ident, image=False):
        with self.lock,self.connect() as db:
            self.prune(db)
            row=db.execute('SELECT r.*,k.name AS key_name FROM requests r LEFT JOIN api_keys k ON k.id=r.key_id WHERE r.id=?',(ident,)).fetchone()
            if not row: raise ApiError('not_found','记录不存在或已过期',404)
            data=db.execute('SELECT * FROM details WHERE request_id=?',(ident,)).fetchone()
        if image:
            if not data: raise ApiError('not_found','原图未留存或已清理',404)
            return bytes(data['image']),json.loads(data['image_meta'])['content_type']
        item=dict(row);item.pop('input_hash');item['model']=json.loads(item['model']);item['response']=json.loads(item['response']) if item['response'] else None
        return {'item':item,'image':json.loads(data['image_meta']) if data else None}

    def stats(self):
        day=int(time.time()//86400)*86400
        with self.lock,self.connect() as db:
            self.prune(db)
            counts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM requests WHERE time>=? GROUP BY state',(day,))}
            usage=[dict(r) for r in db.execute('SELECT key_id,COUNT(*) calls,SUM(state=\'failure\') failures FROM requests WHERE time>=? GROUP BY key_id',(day,))]
        return {'counts':counts,'key_usage':usage}
