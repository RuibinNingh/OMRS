"""不可变 MCP 展示板快照：受限原图、原子文件、持久幂等与登录下载。"""
from .vault_lifecycle import storage, open_sqlite, transaction
import base64
import datetime
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from contextlib import closing
from pathlib import Path

from . import boards, exporting, locking
from .common import omrs_data_dir
from .mcp.common import RequestError, request_identity
from .mcp_operations import web_origin
from .question_images import read_question_image, validate_original_image

MAX_BYTES = 64 * 1024 * 1024
TTL = 24 * 60 * 60


@storage
def _directory(vault):
    path = os.path.join(omrs_data_dir(vault), 'mcp_exports')
    if os.path.lexists(path) and (os.path.islink(path) or not os.path.isdir(path)):
        raise ValueError('导出目录不安全')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


@storage
def _connect(vault):
    path = os.path.join(omrs_data_dir(vault), 'mcp_exports.db')
    if os.path.islink(path):
        raise ValueError('导出回执库不允许符号链接')
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    os.chmod(path, 0o600)
    db = open_sqlite(vault, path, timeout=5)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS exports (
            identity TEXT PRIMARY KEY, digest TEXT NOT NULL, export_id TEXT UNIQUE NOT NULL,
            key_id TEXT NOT NULL, board_id TEXT NOT NULL, revision INTEGER NOT NULL,
            mode TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
            size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, filename TEXT NOT NULL
        )''')
        db.execute('CREATE TABLE IF NOT EXISTS contents(export_id TEXT PRIMARY KEY, html BLOB NOT NULL)')
    except BaseException:
        db.close()
        raise
    db.row_factory = sqlite3.Row
    return db


def _stamp(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).isoformat()


def _result(row, web_url, reused=False):
    return {'status': 'exported', 'export_id': row['export_id'], 'board_id': row['board_id'],
            'revision': row['revision'], 'mode': row['mode'], 'filename': row['filename'],
            'size_bytes': row['size_bytes'], 'sha256': row['sha256'],
            'created_at': _stamp(row['created_at']), 'expires_at': _stamp(row['expires_at']),
            'download_url': web_origin(web_url)+'/api/mcp/exports/download?export_id='+row['export_id'], 'reused': reused}


@storage
def _file(vault, export_id):
    if not isinstance(export_id, str) or not re.fullmatch('ex_[0-9a-f]{32}', export_id):
        raise RequestError('not_found', '导出快照不存在')
    return os.path.join(_directory(vault), export_id+'.html')


def _read_file(path, row):
    try:
        expected = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(expected.st_mode) or expected.st_size != row['size_bytes'] or expected.st_size > MAX_BYTES:
            raise ValueError('导出文件不安全或内容已变化')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino):
                raise ValueError('导出文件在读取期间发生变化')
            raw = stream.read(MAX_BYTES+1)
            after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('导出文件在读取期间发生变化')
        if len(raw) != row['size_bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('导出快照校验失败')
        return raw
    except FileNotFoundError:
        raise RequestError('not_found', '导出快照不存在或已清理') from None


@storage
def cleanup(vault, db):
    # 回执保留，过期请求不能换成当前板重新导出。
    for row in db.execute('SELECT export_id FROM exports WHERE expires_at<=?', (time.time(),)):
        path = _file(vault, row['export_id'])
        if os.path.lexists(path):
            os.unlink(path)
    with transaction(db):
        db.execute('DELETE FROM contents WHERE export_id IN (SELECT export_id FROM exports WHERE expires_at<=?)', (time.time(),))
    directory = _directory(vault)
    # 崩溃可能发生在文件原子替换与索引登记之间；只清理超过保留期的孤儿。
    for name in os.listdir(directory):
        if re.fullmatch(r'ex_[0-9a-f]{32}\.html(?:\.[0-9a-f]{32}\.tmp)?', name):
            path = os.path.join(directory, name)
            if time.time()-os.lstat(path).st_mtime > TTL and not db.execute('SELECT 1 FROM exports WHERE export_id=?', (name[:35],)).fetchone():
                os.unlink(path)


@storage
def create(vault, board_id, mode, request_id, key_id, web_url, authorize=lambda: None, expected_revision=None):
    if mode not in ('all', 'new'):
        raise ValueError('mode 必须是 all 或 new')
    if not isinstance(board_id, str) or not board_id.strip() or len(board_id) > 200:
        raise ValueError('board_id 必须是有效板编号')
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 1):
        raise ValueError('expected_revision 必须为正整数')
    payload = {'board_id': board_id, 'mode': mode, 'expected_revision': expected_revision}
    identity, digest = request_identity(key_id, 'export_board', request_id, payload)
    web_origin(web_url)
    with locking.write_lock(), closing(_connect(vault)) as db:
        authorize()
        cleanup(vault, db)
        row = db.execute('SELECT * FROM exports WHERE identity=?', (identity,)).fetchone()
        if row:
            if row['digest'] != digest:
                raise RequestError('request_conflict', '同一 request_id 的内容不同')
            if row['expires_at'] <= time.time():
                raise RequestError('export_expired', '导出快照已到期，请使用新 request_id')
            _recover_file(vault, db, row)
            _read_file(_file(vault, row['export_id']), row)
            authorize()
            return _result(row, web_url, True)
        board = boards.get_board(vault, board_id)
        if not board:
            raise RequestError('not_found', '展示板不存在')
        boards.check_versions(boards.load_boards(vault), board_id, expected_revision)
        names, cache, budget = {}, {}, 0
        def image_loader(uid, name):
            nonlocal budget
            authorize()
            if uid not in names:
                from .agent.tools.read import get_question
                names[uid] = get_question({'vault': vault}, {'uid': uid})['result']['images']
            if name not in names[uid]:
                raise ValueError('导出图片未登记在当前题目中')
            key = (uid, name)
            if key not in cache:
                raw, _ = read_question_image(vault, uid, names[uid].index(name))
                checked = validate_original_image(raw)
                cache[key] = {'src': 'data:'+checked['mime']+';base64,'+base64.b64encode(raw).decode('ascii'),
                              'w': checked['width'], 'h': checked['height']}
            # 相同图片重复嵌入也占输出大小，按每次引用计数。
            budget += len(cache[key]['src'])
            if budget > MAX_BYTES:
                raise RequestError('export_too_large', '导出快照超过64 MiB')
            authorize()
            return cache[key]
        def question_loader(item):
            from .path_safety import safe_question_path
            path = exporting._safe_question_path(vault, item.get('file_path', ''))
            if not path:
                raise ValueError('导出题目路径不安全')
            safe_question_path(vault, path)
            root = os.path.abspath(os.path.join(vault, '错题'))
            current = path
            while current != root:
                if os.path.islink(current):
                    raise ValueError('导出题目路径不允许链接')
                parent = os.path.dirname(current)
                if parent == current:
                    raise ValueError('导出题目路径不安全')
                current = parent
            return exporting._board_read_question(vault, item)
        try:
            data = exporting.build_board_export_data(vault, board_id, mode=mode, image_loader=image_loader, question_loader=question_loader)
        except RuntimeError as exc:
            raise RequestError('invalid_request', str(exc)) from None
        data['meta']['record_paper'] = False
        raw = exporting._build_board_html(data).encode('utf-8')
        if len(raw) > MAX_BYTES:
            raise RequestError('export_too_large', '导出快照超过64 MiB')
        # 先登记完整不可变字节及稳定编号于SQLite，再原子落HTML：崩溃重试可恢复原快照。
        export_id = 'ex_'+uuid.uuid4().hex
        now = time.time()
        row = {'identity': identity, 'digest': digest, 'export_id': export_id, 'key_id': key_id, 'board_id': board_id,
               'revision': board['revision'], 'mode': mode, 'created_at': now, 'expires_at': now+TTL,
               'size_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'filename': re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', exporting.board_export_filename(board, mode))}
        authorize()
        with transaction(db):
            db.execute('INSERT INTO exports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
            db.execute('INSERT INTO contents VALUES(?,?)', (export_id, raw))
        _materialize(vault, row, raw)
        authorize()
        return _result(row, web_url)


@storage
def _materialize(vault, row, raw):
    path = _file(vault, row['export_id'])
    if os.path.lexists(path):
        _read_file(path, row)
        return
    temp = path+'.'+uuid.uuid4().hex+'.tmp'
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


@storage
def download(vault, export_id):
    _file(vault, export_id)
    with locking.write_lock(), closing(_connect(vault)) as db:
        cleanup(vault, db)
        row = db.execute('SELECT * FROM exports WHERE export_id=?', (export_id,)).fetchone()
        if not row:
            raise RequestError('not_found', '导出快照不存在')
        if row['expires_at'] <= time.time():
            raise RequestError('export_expired', '导出快照已到期')
        _recover_file(vault, db, row)
        return _read_file(_file(vault, export_id), row), row['filename']


@storage
def _recover_file(vault, db, row):
    path = _file(vault, row['export_id'])
    if not os.path.lexists(path):
        content = db.execute('SELECT html FROM contents WHERE export_id=?', (row['export_id'],)).fetchone()
        if not content:
            raise RequestError('not_found', '导出快照不存在')
        _materialize(vault, row, bytes(content['html']))
