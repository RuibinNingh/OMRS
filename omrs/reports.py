"""AI 分析报告托管。

报告（纯 HTML）存放在 `错题/report/`，元数据索引在 `错题/report/index.json`。
报告由后端同源提供（GET /api/report/view?id=...），因此报告内可用
`<img src="/api/image?name=...">` 直接引用题目图片（见 api.md / data.md）。

对应 API：
  GET  /api/reports          → list_reports()
  POST /api/report/create    → create_report(name, html)
  GET  /api/report/view?id=  → get_report_html(id)
  POST /api/report/delete    → delete_report(id)
"""
from .vault_lifecycle import storage, open_sqlite, lease, task, generation

import datetime
import json
import os
import html as html_lib
import re
import urllib.parse

from .common import questions_root

REPORT_DIR = "report"
_INDEX = "index.json"


@storage
def reports_dir(vault: str) -> str:
    path = os.path.join(questions_root(vault), REPORT_DIR)
    os.makedirs(path, exist_ok=True)
    return path


@storage
def _index_path(vault: str) -> str:
    return os.path.join(reports_dir(vault), _INDEX)


@storage
def _load_index(vault: str) -> list:
    path = _index_path(vault)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except Exception:
        return []


@storage
def _save_index(vault: str, items: list) -> None:
    tmp = _index_path(vault) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, _index_path(vault))


@storage
def list_reports(vault: str) -> list:
    """按创建时间倒序返回元数据列表（过滤掉文件已丢失的条目）。"""
    items = _load_index(vault)
    rdir = reports_dir(vault)
    alive = [it for it in items if os.path.isfile(os.path.join(rdir, it.get("filename", "")))]
    alive.sort(key=lambda it: it.get("created_at", ""), reverse=True)
    return alive


@storage
def create_report(vault: str, name: str, html: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("报告名称不能为空")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("报告内容（HTML）不能为空")

    now = datetime.datetime.now()
    report_id = f"RPT-{now.strftime('%Y%m%d%H%M%S')}"
    # 同秒冲突加后缀
    existing_ids = {it.get("id") for it in _load_index(vault)}
    if report_id in existing_ids:
        suffix = 1
        while f"{report_id}-{suffix}" in existing_ids:
            suffix += 1
        report_id = f"{report_id}-{suffix}"

    filename = f"{report_id}.html"
    payload = html.encode("utf-8")
    path = os.path.join(reports_dir(vault), filename)
    with open(path, "w", encoding="utf-8") as file:
        file.write(html)
        file.flush()
        os.fsync(file.fileno())

    meta = {
        "id": report_id,
        "name": name,
        "filename": filename,
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "size": len(payload),
    }
    items = _load_index(vault)
    items.append(meta)
    _save_index(vault, items)
    return meta


@storage
def get_report_html(vault: str, report_id: str) -> bytes:
    items = _load_index(vault)
    meta = next((it for it in items if it.get("id") == report_id), None)
    if not meta:
        raise ValueError("报告不存在")
    path = os.path.join(reports_dir(vault), meta.get("filename", ""))
    if not os.path.isfile(path):
        raise ValueError("报告文件已丢失")
    with open(path, "rb") as file:
        return file.read()


def signed_report_images(payload: bytes, signer) -> bytes:
    """Sign static OMRS image URLs without changing stored report HTML."""
    source = payload.decode("utf-8", errors="replace")
    image_tag = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
    source_attr = re.compile(r"\bsrc\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)

    def rewrite_tag(match):
        tag = match.group(0)
        attribute = source_attr.search(tag)
        if not attribute:
            return tag
        url = html_lib.unescape(attribute.group(2))
        parsed = urllib.parse.urlsplit(url)
        if parsed.path != "/api/image" or parsed.netloc or parsed.scheme:
            return tag
        name = urllib.parse.parse_qs(parsed.query).get("name", [""])[0]
        if not name:
            return tag
        try:
            session_id, expires, signature = signer(name)
        except ValueError:
            return tag
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query.extend((("grant_session", session_id), ("grant_expires", str(expires)),
                      ("grant_signature", signature)))
        signed = urllib.parse.urlunsplit(("", "", parsed.path, urllib.parse.urlencode(query), parsed.fragment))
        return tag[:attribute.start(2)] + html_lib.escape(signed, quote=True) + tag[attribute.end(2):]

    return image_tag.sub(rewrite_tag, source).encode("utf-8")


@storage
def delete_report(vault: str, report_id: str) -> bool:
    items = _load_index(vault)
    meta = next((it for it in items if it.get("id") == report_id), None)
    if not meta:
        return False
    path = os.path.join(reports_dir(vault), meta.get("filename", ""))
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
    _save_index(vault, [it for it in items if it.get("id") != report_id])
    return True


@storage
def create_mcp_report(vault, name, html, key_id, request_id, authorize=lambda: None):
    """预留稳定编号→原子文件→索引→回执；重试可修复中断的索引登记。"""
    import hashlib
    import sqlite3
    import uuid
    from contextlib import closing
    from . import locking
    from .common import omrs_data_dir
    from .mcp.common import request_identity, RequestError

    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('报告名称必须为 1 到 200 字符')
    if not isinstance(html, str) or not html.strip() or len(html.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('HTML 必须非空且不超过 2 MiB')
    name = name.strip()
    identity, digest = request_identity(key_id, 'create_report', request_id, {'name': name, 'html': html})
    payload = html.encode('utf-8')
    receipt_path = os.path.join(omrs_data_dir(vault), 'mcp_reports.db')
    if os.path.islink(receipt_path):
        raise ValueError('报告回执路径不允许链接')
    with locking.write_lock():
        authorize()
        descriptor = os.open(receipt_path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(receipt_path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute('CREATE TABLE IF NOT EXISTS requests(identity TEXT PRIMARY KEY, digest TEXT NOT NULL, '
                       'meta TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0)')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE identity=?', (identity,)).fetchone()
            reused = row is not None
            if row:
                if row['digest'] != digest:
                    raise RequestError('request_conflict', '同一 request_id 的内容不同')
                meta = json.loads(row['meta'])
                if row['applied']:
                    authorize()
                    return {**meta, 'report_id': meta['id'], 'reused': True}
            else:
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                report_id = 'RPT-MCP-' + uuid.uuid4().hex
                meta = {'id': report_id, 'name': name, 'filename': report_id + '.html', 'created_at': now, 'size': len(payload)}
                db.execute('INSERT INTO requests(identity,digest,meta) VALUES(?,?,?)',
                           (identity, digest, json.dumps(meta, ensure_ascii=False)))
            db.commit()  # 预留编号独立持久化，崩溃重试不能换编号。
            authorize()
            target = os.path.join(reports_dir(vault), meta['filename'])
            if os.path.islink(target):
                raise ValueError('报告文件不允许链接')
            if os.path.exists(target):
                with open(target, 'rb') as source:
                    if hashlib.sha256(source.read()).digest() != hashlib.sha256(payload).digest():
                        raise RequestError('content_conflict', '预留报告的文件内容不一致')
            else:
                tmp = target + '.' + uuid.uuid4().hex + '.tmp'
                try:
                    with open(tmp, 'xb') as output:
                        output.write(payload)
                        output.flush()
                        os.fsync(output.fileno())
                    authorize()
                    os.replace(tmp, target)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
            items = _load_index(vault)
            if not any(item.get('id') == meta['id'] for item in items):
                authorize()
                _save_index(vault, [*items, meta])
            db.execute('UPDATE requests SET applied=1 WHERE identity=?', (identity,))
            db.commit()
            authorize()
            return {**meta, 'report_id': meta['id'], 'reused': reused}
