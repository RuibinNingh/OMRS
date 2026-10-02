"""收件箱（inbox）：上传 → 框选 → 转换 → 提交 的暂存层。

仅依赖标准库。数据全部放在 `错题/.omrs/inbox/`，**不进 Ledger**：
- inbox.db          SQLite：items / regions / cards / jobs
- raw/<sha256>.<ext> 上传原件（按内容哈希命名，重复上传自动合并）
- crops/<region>.png 裁剪产物（由前端 canvas 生成后上传；可重建）
- annotations.jsonl  append-only 标注事件（训练数据的事实源）

坐标一律用归一化 0–1（相对原图宽高）。多模态模型返回的 0–1000（Qwen3-VL）
或绝对像素坐标在 ai_assist.parse_detect_output 里统一换算。

后台 job（detect / extract / classify）只写 inbox.db，自带 _LOCK；
提交（commit_item）在请求线程同步调 creation.create_question，写 Ledger 的路径与
现有录入完全一致。
"""

import base64
import datetime
import hashlib
import io
import json
import os
import re
import sqlite3
import struct
import threading
import uuid
import zipfile

from .common import load_config, omrs_data_dir
from .vault_lifecycle import storage, open_sqlite, task, generation
from .creation import create_question

INBOX_DIR = "inbox"
_LOCK = threading.RLock()

STATUSES = ("pending", "boxed", "ready", "done", "discarded")
ROLES = ("question", "answer", "ignore")
CONVERTS = ("text", "image", "auto")
ORIGINS = ("manual", "ai", "ai_edited")
LAYOUTS = ("zuoyebang", "photo", "plain", "other")
_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}

# 长图切片：高宽比超过 SLICE_MAX_RATIO 就切成若干重叠条带分别送模型
SLICE_MAX_RATIO = 3.0
SLICE_STRIP_RATIO = 2.0
SLICE_OVERLAP = 0.08


# ────────────────────────── 路径 / 时间 / 工具 ──────────────────────────

def inbox_dir(vault):
    path = os.path.join(omrs_data_dir(vault), INBOX_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def raw_dir(vault):
    path = os.path.join(inbox_dir(vault), "raw")
    os.makedirs(path, exist_ok=True)
    return path


def crops_dir(vault):
    path = os.path.join(inbox_dir(vault), "crops")
    os.makedirs(path, exist_ok=True)
    return path


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _new_item_id():
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return f"IB-{stamp}-{uuid.uuid4().hex[:6]}"


def _loads(text, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def image_size(data):
    """从 PNG / JPEG / GIF 字节读取 (mime, width, height)。不依赖 Pillow。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "image/png", width, height
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return "image/gif", width, height
    if data[:2] == b"\xff\xd8":
        pos = 2
        size = len(data)
        while pos + 9 < size:
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                return "image/jpeg", width, height
            pos += 2 + length
        raise ValueError("JPEG 缺少尺寸信息")
    raise ValueError("不支持的图片格式（仅支持 PNG / JPEG / GIF）")


def _data_url_bytes(data_url):
    """data URL 或裸 base64 → (mime, bytes)。"""
    if not isinstance(data_url, str) or not data_url:
        raise ValueError("缺少图片数据")
    match = re.match(r"^data:([^;,]+);base64,(.*)$", data_url, re.DOTALL)
    if match:
        return match.group(1).strip().lower(), base64.b64decode(match.group(2))
    return "image/png", base64.b64decode(data_url)


def _to_data_url(mime, data):
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _clamp01(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))


def _clean_region(raw, index):
    role = raw.get("role") if raw.get("role") in ROLES else "question"
    convert = raw.get("convert") if raw.get("convert") in CONVERTS else "auto"
    origin = raw.get("origin") if raw.get("origin") in ORIGINS else "manual"
    x, y = _clamp01(raw.get("x", 0)), _clamp01(raw.get("y", 0))
    w = max(0.0, min(1.0 - x, _clamp01(raw.get("w", 0))))
    h = max(0.0, min(1.0 - y, _clamp01(raw.get("h", 0))))
    if w <= 0 or h <= 0:
        raise ValueError("区域宽高必须大于 0")
    ai_box = raw.get("ai_box") if isinstance(raw.get("ai_box"), dict) else None
    judge = raw.get("judge") if isinstance(raw.get("judge"), dict) else None
    try:
        card = max(1, int(raw.get("card", 1)))
    except (TypeError, ValueError):
        card = 1
    return {
        "id": str(raw.get("id") or f"r_{uuid.uuid4().hex[:8]}"),
        "card": card,
        "ord": index,
        "role": role,
        "x": x, "y": y, "w": w, "h": h,
        "origin": origin,
        "conf": float(raw["conf"]) if raw.get("conf") not in (None, "") else None,
        "ai_box": ai_box,
        "convert": convert,
        "text": raw.get("text") if isinstance(raw.get("text"), str) else None,
        "text_status": str(raw.get("text_status") or "none"),
        "judge": judge,
        "judge_overridden": bool(raw.get("judge_overridden")),
    }


def iou(a, b):
    if not a or not b:
        return 0.0
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


# ────────────────────────── 存储 ──────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, sha256 TEXT UNIQUE, file TEXT, mime TEXT, width INTEGER, height INTEGER,
  bytes INTEGER, source TEXT, uploaded_at TEXT, status TEXT, layout TEXT,
  link_uid TEXT, link_question_id TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS regions (
  id TEXT PRIMARY KEY, item_id TEXT, card INTEGER, ord INTEGER, role TEXT,
  x REAL, y REAL, w REAL, h REAL, origin TEXT, conf REAL, ai_box TEXT,
  convert TEXT, text TEXT, text_status TEXT, judge TEXT, judge_overridden INTEGER, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS regions_item ON regions(item_id);
CREATE TABLE IF NOT EXISTS cards (
  item_id TEXT, card INTEGER, subject TEXT, category TEXT, difficulty INTEGER, tags TEXT,
  cause TEXT, page TEXT, classified INTEGER, created_uid TEXT, created_question_id TEXT,
  manual_fields TEXT NOT NULL DEFAULT '{}', field_sources TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (item_id, card)
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, type TEXT, status TEXT, created_at TEXT, finished_at TEXT,
  processed INTEGER, total INTEGER, result TEXT, errors TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS chat_training_boxes (
  id TEXT PRIMARY KEY,item_id TEXT NOT NULL,draft_id TEXT NOT NULL,image_sha TEXT NOT NULL,
  section TEXT NOT NULL,ord INTEGER NOT NULL,x REAL NOT NULL,y REAL NOT NULL,w REAL NOT NULL,h REAL NOT NULL,
  origin TEXT NOT NULL,ai_box TEXT
);
CREATE INDEX IF NOT EXISTS chat_training_item ON chat_training_boxes(item_id);
"""

# items 扩展列：盲标、训练专用图与重置代次。旧库通过 ALTER 补齐。
_ITEM_EXTRA_COLUMNS = (("blind", "INTEGER DEFAULT 0"), ("blind_boxes", "TEXT"),
                       ("training_only", "INTEGER NOT NULL DEFAULT 0"),
                       ("reset_epoch", "INTEGER NOT NULL DEFAULT 0"),
                       ("revision", "INTEGER NOT NULL DEFAULT 0"))


class InboxConflict(ValueError):
    """图片已被其他操作修改；调用方须重新读取后明确处理本地编辑。"""

    def __init__(self, message, code="revision_conflict", current_revision=None):
        super().__init__(message)
        self.code = code
        self.current_revision = current_revision


def _check_write(row, expected_revision=None, reset_epoch=None, require_version=False):
    if require_version and (type(expected_revision) is not int or type(reset_epoch) is not int):
        raise InboxConflict("缺少图片修订号或重置代次，请刷新页面后重试", "revision_required", row["revision"])
    if reset_epoch is not None and (type(reset_epoch) is not int or reset_epoch != row["reset_epoch"]):
        raise InboxConflict("图片已重置，请重新读取后再保存", "reset_conflict", row["revision"])
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision != row["revision"]):
        raise InboxConflict("图片已在其他位置修改，请核对后重新保存", "revision_conflict", row["revision"])


@storage
def connect(vault):
    path = os.path.join(inbox_dir(vault), "inbox.db")
    db = open_sqlite(vault, path, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(_SCHEMA)
    existing = {row[1] for row in db.execute("PRAGMA table_info(items)")}
    for column, decl in _ITEM_EXTRA_COLUMNS:
        if column not in existing:
            db.execute(f"ALTER TABLE items ADD COLUMN {column} {decl}")
    card_columns = {row[1] for row in db.execute("PRAGMA table_info(cards)")}
    for column in ("manual_fields", "field_sources"):
        if column not in card_columns:
            db.execute(f"ALTER TABLE cards ADD COLUMN {column} TEXT NOT NULL DEFAULT '{{}}'")
    if "labels" not in card_columns:
        db.execute("ALTER TABLE cards ADD COLUMN labels TEXT NOT NULL DEFAULT '[]'")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS commit_operations (
            operation_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, reset_epoch INTEGER NOT NULL,
            card INTEGER NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL,
            identity_json TEXT NOT NULL, payload_json TEXT NOT NULL,
            artifacts_json TEXT NOT NULL DEFAULT '{}', phase TEXT NOT NULL DEFAULT 'prepared',
            result_json TEXT, UNIQUE(item_id, reset_epoch, card)
        );
    """)
    db.commit()
    return db


def _meta_get(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(db, key, value):
    db.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))


def _meta_incr(db, key, delta=1):
    value = int(_meta_get(db, key, 0) or 0) + int(delta)
    _meta_set(db, key, value)
    return value


@storage
def _log(vault, event, payload):
    """append-only 标注事件流。"""
    record = {"ts": _now(), "event": event, **payload}
    path = os.path.join(inbox_dir(vault), "annotations.jsonl")
    with _LOCK:
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _row_region(row):
    return {
        "id": row["id"], "card": row["card"], "ord": row["ord"], "role": row["role"],
        "x": row["x"], "y": row["y"], "w": row["w"], "h": row["h"],
        "origin": row["origin"], "conf": row["conf"], "ai_box": _loads(row["ai_box"], None),
        "convert": row["convert"], "text": row["text"], "text_status": row["text_status"] or "none",
        "judge": _loads(row["judge"], None), "judge_overridden": bool(row["judge_overridden"]),
    }


def _row_card(row):
    return {
        "card": row["card"], "subject": row["subject"] or "", "category": row["category"] or "",
        "difficulty": row["difficulty"] if row["difficulty"] is not None else 5,
        "tags": _loads(row["tags"], []), "labels": _loads(row["labels"], []), "cause": row["cause"] or "",
        "classified": bool(row["classified"]), "created_uid": row["created_uid"] or "",
        "created_question_id": row["created_question_id"] or "",
        "manual_fields": _loads(row["manual_fields"], {}),
        "field_sources": _loads(row["field_sources"], {}),
    }


def _row_item(db, row, with_children=True):
    item = {
        "id": row["id"], "sha256": row["sha256"], "file": row["file"], "mime": row["mime"],
        "width": row["width"], "height": row["height"], "bytes": row["bytes"],
        "source": row["source"], "uploaded_at": row["uploaded_at"], "status": row["status"],
        "training_only": bool(row["training_only"]),
        "reset_epoch": row["reset_epoch"],
        "revision": row["revision"],
        "layout": row["layout"], "updated_at": row["updated_at"],
        "link": {"uid": row["link_uid"], "question_id": row["link_question_id"]} if row["link_uid"] else None,
        # 盲标：AI 框已跑但不展示给标注者；blind_boxes 只在事件与数据集导出里出现，不进 item 响应
        "blind": bool(row["blind"]) if "blind" in row.keys() else False,
    }
    if with_children:
        item["regions"] = [
            _row_region(r) for r in db.execute(
                "SELECT * FROM regions WHERE item_id=? ORDER BY card, ord", (row["id"],))
        ]
        item["cards"] = {
            str(c["card"]): _row_card(c)
            for c in db.execute("SELECT * FROM cards WHERE item_id=? ORDER BY card", (row["id"],))
        }
    return item


def _raw_path(vault, sha256, mime):
    return os.path.join(raw_dir(vault), f"{sha256}.{_MIME_EXT.get(mime, 'png')}")


# ────────────────────────── 上传 / 查询 / 更新 ──────────────────────────

@storage
def upload_images(vault, files, source="desktop"):
    """files: [(filename, bytes)]。返回 {items:[...新建或已存在...], duplicates:[...]}。"""
    created, duplicates = [], []
    with _LOCK:
        db = connect(vault)
        try:
            for filename, data in files:
                if isinstance(data, dict) and data.get("upload_ref"):
                    from .uploads import resolve, read
                    resolve(vault, data["upload_ref"], purpose="inbox")
                    data = read(vault, data["upload_ref"])
                if not data:
                    continue
                mime, width, height = image_size(data)
                sha = hashlib.sha256(data).hexdigest()
                existing = db.execute("SELECT * FROM items WHERE sha256=?", (sha,)).fetchone()
                if existing:
                    if existing["training_only"]:
                        db.execute("UPDATE items SET training_only=0,status='pending',layout='zuoyebang',"
                                   "source=?,file=?,updated_at=? WHERE id=?",
                                   (source, os.path.basename(filename or "image"), _now(), existing["id"]))
                        created.append(existing["id"])
                    else:
                        duplicates.append({"file": filename, "item_id": existing["id"]})
                    continue
                path = _raw_path(vault, sha, mime)
                if not os.path.exists(path):
                    with open(path, "wb") as file:
                        file.write(data)
                item_id = _new_item_id()
                now = _now()
                db.execute(
                    "INSERT INTO items (id, sha256, file, mime, width, height, bytes, source, uploaded_at, "
                    "status, layout, link_uid, link_question_id, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item_id, sha, os.path.basename(filename or "image"), mime, width, height,
                     len(data), source, now, "pending", "zuoyebang", None, None, now),
                )
                created.append(item_id)
            db.commit()
            items = [_row_item(db, db.execute("SELECT * FROM items WHERE id=?", (i,)).fetchone())
                     for i in created]
        finally:
            db.close()
    for item in items:
        _log(vault, "item.upload", {"item_id": item["id"], "file": item["file"], "source": source,
                                    "width": item["width"], "height": item["height"]})
    result = {"items": items, "duplicates": duplicates}
    if items and load_config(vault).get("inbox_auto_on_upload"):
        # 无人值守：上传即排队 auto job（detect → 自动策略），失败只记录不影响上传
        try:
            result["job"] = start_job(vault, "auto", {"items": [{"item_id": i["id"]} for i in items]})
        except Exception as exc:  # noqa: BLE001
            result["job_error"] = str(exc)
    cleanup_expired(vault)
    return result


@storage
def list_items(vault, status=None, with_children=True):
    db = connect(vault)
    try:
        if status:
            rows = db.execute("SELECT * FROM items WHERE status=? AND training_only=0 ORDER BY uploaded_at DESC", (status,))
        else:
            rows = db.execute("SELECT * FROM items WHERE status!='discarded' AND training_only=0 ORDER BY uploaded_at DESC")
        return [_row_item(db, row, with_children) for row in rows.fetchall()]
    finally:
        db.close()


@storage
def get_item(vault, item_id):
    db = connect(vault)
    try:
        row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise ValueError(f"收件箱里没有 {item_id}")
        return _row_item(db, row)
    finally:
        db.close()


@storage
def raw_file(vault, item_id):
    item = get_item(vault, item_id)
    path = _raw_path(vault, item["sha256"], item["mime"])
    if not item["file"] or not os.path.exists(path):
        raise ValueError("原图文件不存在（可能已被清理）")
    with open(path, "rb") as file:
        return item["mime"], file.read()


def _write_regions(db, item_id, regions, now):
    db.execute("DELETE FROM regions WHERE item_id=?", (item_id,))
    for index, raw in enumerate(regions):
        r = _clean_region(raw, index)
        db.execute(
            "INSERT INTO regions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], item_id, r["card"], r["ord"], r["role"], r["x"], r["y"], r["w"], r["h"],
             r["origin"], r["conf"], json.dumps(r["ai_box"]) if r["ai_box"] else None,
             r["convert"], r["text"], r["text_status"], json.dumps(r["judge"], ensure_ascii=False) if r["judge"] else None,
             1 if r["judge_overridden"] else 0, now),
        )


def _write_cards(db, item_id, cards, ai=False):
    for key, form in (cards or {}).items():
        try:
            card = int(key)
        except (TypeError, ValueError):
            continue
        previous = db.execute("SELECT * FROM cards WHERE item_id=? AND card=?", (item_id, card)).fetchone()
        # 单字段保存与AI补全都保留未提交的字段，显式空数组仍用于清空。
        if previous:
            form = {**_row_card(previous), **form}
        tags = form.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，]", tags) if t.strip()]
        labels = form.get("labels", _loads(previous["labels"], []) if previous else [])
        if not isinstance(labels, list) or any(not isinstance(v, str) for v in labels):
            raise ValueError("标记必须是字符串数组")
        labels = list(dict.fromkeys(v.strip() for v in labels if v.strip()))
        if ai and previous and "labels" not in form:
            labels = _loads(previous["labels"], [])
        manual = dict(_loads(previous["manual_fields"], {}) if previous else {})
        manual.update(form.get("manual_fields") or {})
        sources = dict(_loads(previous["field_sources"], {}) if previous else {})
        sources.update(form.get("field_sources") or {})
        if not ai:
            for name, column, value, default in (
                ("subject", "subject", form.get("subject", ""), ""),
                ("category", "category", form.get("category", ""), ""),
                ("difficulty", "difficulty", int(form.get("difficulty", 5) or 5), 5),
                ("tags", "tags", tags, []),
                ("labels", "labels", labels, []),
                ("cause", "cause", form.get("cause", ""), ""),
            ):
                old = (_loads(previous[column], []) if name in {"tags", "labels"} else previous[column]) if previous else default
                if value != old:
                    manual[name] = True
                    sources.pop(name, None)
        db.execute(
            "INSERT INTO cards (item_id, card, subject, category, difficulty, tags, labels, cause, page, classified, manual_fields, field_sources) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(item_id, card) DO UPDATE SET subject=excluded.subject, "
            "category=excluded.category, difficulty=excluded.difficulty, tags=excluded.tags, labels=excluded.labels, cause=excluded.cause, "
            "page=excluded.page, classified=excluded.classified, manual_fields=excluded.manual_fields, field_sources=excluded.field_sources",
            (item_id, card, form.get("subject", ""), form.get("category", ""),
             int(form.get("difficulty", 5) or 5), json.dumps(tags, ensure_ascii=False), json.dumps(labels, ensure_ascii=False),
             form.get("cause", ""), "", 1 if form.get("classified") else 0,
             json.dumps(manual, ensure_ascii=False), json.dumps(sources, ensure_ascii=False)),
        )


@storage
def update_item(vault, item_id, data, require_epoch=False, require_version=False, _ai=False):
    """只修改明确提交的字段；regions 明确传入时整体替换。"""
    with _LOCK:
        db = connect(vault)
        try:
            row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise ValueError(f"收件箱里没有 {item_id}")
            if row["training_only"]:
                raise ValueError("训练专用图片不能进入普通处理流程")
            if row["status"] in ("done", "discarded"):
                raise ValueError("已结束的图片不能再修改")
            if require_epoch and row["reset_epoch"] and "reset_epoch" not in data:
                raise InboxConflict("图片已重置，请重新读取后再保存", "reset_conflict", row["revision"])
            _check_write(row, data.get("expected_revision"), data.get("reset_epoch"), require_version)
            before = _row_item(db, row)
            now = _now()
            if "regions" in data and isinstance(data["regions"], list):
                _write_regions(db, item_id, data["regions"], now)
            if "cards" in data and isinstance(data["cards"], dict):
                _write_cards(db, item_id, data["cards"], ai=_ai)
            layout = data.get("layout")
            if layout in LAYOUTS:
                db.execute("UPDATE items SET layout=? WHERE id=?", (layout, item_id))
            status = data.get("status")
            count = db.execute("SELECT COUNT(*) FROM regions WHERE item_id=?", (item_id,)).fetchone()[0]
            if status in ("pending", "boxed", "ready"):
                if status == "ready":
                    _assert_ready(db, item_id)
                db.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
            elif status is None and "regions" in data:
                current = db.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()[0]
                if current in ("pending", "boxed"):
                    db.execute("UPDATE items SET status=? WHERE id=?",
                               ("boxed" if count else "pending", item_id))
            db.execute("UPDATE items SET revision=revision+1, updated_at=? WHERE id=?", (now, item_id))
            after = _row_item(db, db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())
            if "regions" in data:
                # 被删掉的 AI 原框 = 拒绝；增量计数，避免统计时全量扫 annotations.jsonl
                before_ai = {r["id"] for r in before["regions"] if r["origin"] == "ai"}
                after_ids = {r["id"] for r in after["regions"]}
                if before_ai - after_ids:
                    _meta_incr(db, "rejected_ai_boxes", len(before_ai - after_ids))
            blind_boxes = None
            if status == "ready" and after.get("blind"):
                blind_boxes = _loads(db.execute("SELECT blind_boxes FROM items WHERE id=?", (item_id,)).fetchone()[0], None)
            db.commit()
        finally:
            db.close()
    if "regions" in data:
        _log(vault, "regions.update", {"item_id": item_id, "layout": after["layout"],
                                       "width": after["width"], "height": after["height"],
                                       "before": _region_summary(before["regions"]),
                                       "after": _region_summary(after["regions"])})
    if status == "ready":
        payload = {"item_id": item_id, "regions": _region_summary(after["regions"])}
        if after.get("blind"):
            # 盲标：把人工最终框与当时藏起来的 AI 框成对写进事件，作干净评估集
            payload.update({"blind": True, "ai_boxes": blind_boxes or [],
                            "blind_eval": blind_eval(after["regions"], blind_boxes or [])})
        _log(vault, "item.ready", payload)
    return after


@storage
def reset_item(vault, item_id, expected_revision=None, reset_epoch=None, require_version=False):
    """原子清空当前截图的处理进度；原图和上传信息保留。"""
    with _LOCK:
        db = connect(vault)
        try:
            row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise ValueError(f"收件箱里没有 {item_id}")
            if row["training_only"] or row["status"] in ("done", "discarded"):
                raise ValueError("这张图片不能重置")
            _check_write(row, expected_revision, reset_epoch, require_version)
            committed = db.execute("SELECT 1 FROM cards WHERE item_id=? AND created_uid IS NOT NULL "
                                   "AND created_uid!='' LIMIT 1", (item_id,)).fetchone()
            if committed:
                raise ValueError("这张图片已有题卡录入题库，不能重置")
            pending = db.execute("SELECT 1 FROM commit_operations WHERE item_id=? AND reset_epoch=? AND phase!='cancelled' LIMIT 1",
                                 (item_id, row["reset_epoch"])).fetchone()
            if pending:
                raise InboxConflict("此图片有入库预留，请先用原内容完成重试，不能重置", "operation_pending")
            before = _row_item(db, row)
            region_ids = [region["id"] for region in before["regions"]]
            db.execute("DELETE FROM regions WHERE item_id=?", (item_id,))
            db.execute("DELETE FROM cards WHERE item_id=?", (item_id,))
            db.execute("UPDATE items SET status='pending', layout='zuoyebang', blind=0, blind_boxes=NULL, "
                       "reset_epoch=reset_epoch+1, revision=revision+1, updated_at=? WHERE id=?", (_now(), item_id))
            after = _row_item(db, db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())
            db.commit()
        finally:
            db.close()
    for region_id in region_ids:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", region_id)
        for ext in _MIME_EXT.values():
            try:
                os.remove(os.path.join(crops_dir(vault), f"{safe}.{ext}"))
            except OSError:
                pass
    _log(vault, "item.reset", {"item_id": item_id, "before": _region_summary(before["regions"]),
                                "reset_epoch": after["reset_epoch"]})
    return after


def _region_summary(regions):
    return [
        {k: r.get(k) for k in ("id", "card", "role", "x", "y", "w", "h", "origin", "conf", "ai_box",
                                "convert", "judge", "judge_overridden")}
        for r in regions
    ]


def _assert_ready(db, item_id):
    regions = [_row_region(r) for r in db.execute("SELECT * FROM regions WHERE item_id=?", (item_id,))]
    if not any(r["role"] == "question" for r in regions):
        raise ValueError("至少要有一个题目框")
    for r in regions:
        if r["role"] == "ignore":
            continue
        if r["text_status"] in ("running", "stale", "error"):
            raise ValueError("还有区域正在提取、提取失败或框位已变，请重新提取后审核")
        if r["convert"] == "auto":
            raise ValueError("还有区域未提取，请先一键提取后审核")
        if r["convert"] == "text" and not (r["text"] or "").strip():
            raise ValueError("「转文本」区域还没有文本")


def discard_item(vault, item_id, expected_revision=None, reset_epoch=None, require_version=False):
    return discard_items(vault, [{"id": item_id, "expected_revision": expected_revision,
                                  "reset_epoch": reset_epoch}], require_version=require_version)[0]


@storage
def discard_items(vault, entries, require_version=False):
    """批量丢弃先核对全部版本，再在一个事务内修改；冲突时整批不动。"""
    if not entries or not isinstance(entries, list):
        raise ValueError("没有要丢弃的图片")
    with _LOCK:
        db = connect(vault)
        try:
            checked = []
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("丢弃项必须是对象")
                item_id = entry.get("id")
                if item_id in checked:
                    raise ValueError("丢弃列表中有重复图片")
                row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
                if not row:
                    raise ValueError(f"收件箱里没有 {item_id}")
                if row["status"] in ("done", "discarded"):
                    raise ValueError("已结束的图片不能丢弃")
                _check_write(row, entry.get("expected_revision"), entry.get("reset_epoch"), require_version)
                checked.append(item_id)
            for item_id in checked:
                db.execute("UPDATE items SET status='discarded', revision=revision+1, updated_at=? WHERE id=?", (_now(), item_id))
            db.commit()
        finally:
            db.close()
    for item_id in checked:
        _log(vault, "item.discard", {"item_id": item_id})
    return [{"item_id": item_id, "status": "discarded"} for item_id in checked]


@storage
def save_crop(vault, region_id, data_url):
    if isinstance(data_url, dict) and data_url.get("upload_ref"):
        from .uploads import image_data_url
        data_url = image_data_url(vault, data_url["upload_ref"], purpose="inbox")
    mime, data = _data_url_bytes(data_url)
    if mime not in _MIME_EXT:
        raise ValueError("裁剪图仅支持 PNG / JPEG / GIF")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", region_id)
    path = os.path.join(crops_dir(vault), f"{safe}.{_MIME_EXT[mime]}")
    with open(path, "wb") as file:
        file.write(data)
    return path


@storage
def _crop_data_url(vault, region_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", region_id)
    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg"), ("gif", "image/gif")):
        path = os.path.join(crops_dir(vault), f"{safe}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as file:
                return _to_data_url(mime, file.read())
    return None


@storage
def _pillow_crop(vault, item, region):
    """有 Pillow 时服务端裁图；没有则返回 None。"""
    try:
        from PIL import Image  # noqa: WPS433 - 可选依赖
    except Exception:
        return None
    path = _raw_path(vault, item["sha256"], item["mime"])
    with Image.open(path) as im:
        w, h = im.size
        box = (int(region["x"] * w), int(region["y"] * h),
               int((region["x"] + region["w"]) * w), int((region["y"] + region["h"]) * h))
        buf = io.BytesIO()
        im.crop(box).convert("RGB").save(buf, format="PNG")
    return _to_data_url("image/png", buf.getvalue())


@storage
def region_image(vault, item, region, supplied=None):
    """按优先级取区域图：本次请求附带的裁图 → crops/ 缓存 → Pillow 服务端裁 → 整图（框覆盖全图时）。"""
    if supplied:
        save_crop(vault, region["id"], supplied)
        return supplied
    cached = _crop_data_url(vault, region["id"])
    if cached:
        return cached
    if region["x"] <= 0.005 and region["y"] <= 0.005 and region["w"] >= 0.99 and region["h"] >= 0.99:
        mime, data = raw_file(vault, item["id"])
        return _to_data_url(mime, data)
    cropped = _pillow_crop(vault, item, region)
    if cropped:
        save_crop(vault, region["id"], cropped)
        return cropped
    raise ValueError(f"区域 {region['id']} 缺少裁剪图：请由前端附带 crops，或安装 Pillow 以便服务端裁图")


# ────────────────────────── 长图切片 / 框合并（纯函数，可测） ──────────────────────────

def slice_plan(width, height, max_ratio=SLICE_MAX_RATIO, strip_ratio=SLICE_STRIP_RATIO, overlap=SLICE_OVERLAP):
    """返回 [(y0, y1)] 归一化条带。高宽比不超过 max_ratio 时返回整图 [(0,1)]。"""
    if not width or not height or height / width <= max_ratio:
        return [(0.0, 1.0)]
    strip = (width * strip_ratio) / height  # 每条带占整图高度的比例
    step = strip * (1.0 - overlap)
    plan, y = [], 0.0
    while True:
        y1 = min(1.0, y + strip)
        plan.append((round(y, 4), round(y1, 4)))
        if y1 >= 1.0:
            break
        y += step
    # 末尾只剩一小条时并入上一条，避免送一个几乎没内容的碎片
    if len(plan) > 1 and (plan[-1][1] - plan[-1][0]) < 0.5 * strip:
        plan[-2] = (plan[-2][0], 1.0)
        plan.pop()
    return plan


def merge_strip_boxes(strips, min_iou=0.4):
    """strips: [{"y0","y1","boxes":[{role,card,x,y,w,h,conf}]}]，boxes 坐标相对条带。
    映射回整图后，把**不同条带**里同角色、上下相接/重叠且水平重叠的框合并为并集
    （同一条带内的两个框永远不合并，保证一张拍照里的两道题不会被粘成一道）。"""
    mapped = []
    for index, strip in enumerate(strips):
        y0, y1 = float(strip["y0"]), float(strip["y1"])
        span = max(1e-6, y1 - y0)
        for box in strip.get("boxes") or []:
            mapped.append({
                "role": box.get("role", "question"), "card": int(box.get("card", 1) or 1),
                "x": _clamp01(box["x"]), "y": _clamp01(y0 + _clamp01(box["y"]) * span),
                "w": _clamp01(box["w"]), "h": _clamp01(_clamp01(box["h"]) * span),
                "conf": float(box.get("conf", 0.5) or 0.5), "_strips": {index},
            })
    merged = []
    for box in sorted(mapped, key=lambda b: b["y"]):
        target = None
        for cand in merged:
            if cand["role"] != box["role"] or box["_strips"] & cand["_strips"]:
                continue
            h_overlap = min(cand["x"] + cand["w"], box["x"] + box["w"]) - max(cand["x"], box["x"])
            v_gap = box["y"] - (cand["y"] + cand["h"])
            if iou(cand, box) >= min_iou or (h_overlap > 0.5 * min(cand["w"], box["w"]) and v_gap < 0.02):
                target = cand
                break
        if target is None:
            merged.append(dict(box))
            continue
        x1, y1 = min(target["x"], box["x"]), min(target["y"], box["y"])
        x2 = max(target["x"] + target["w"], box["x"] + box["w"])
        y2 = max(target["y"] + target["h"], box["y"] + box["h"])
        target.update({"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "conf": min(target["conf"], box["conf"]),
                       "_strips": target["_strips"] | box["_strips"]})
    for box in merged:
        box.pop("_strips", None)
        box["card"] = box.get("card") or 1
    return merged


# ────────────────────────── 后台任务 ──────────────────────────

_JOBS = {}


@storage
def _job_update(vault, job_id, **fields):
    with _LOCK:
        job = _JOBS.setdefault(job_id, {"id": job_id})
        job.update(fields)
        db = connect(vault)
        try:
            db.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                (job_id, job.get("type"), job.get("status"), job.get("created_at"), job.get("finished_at"),
                 job.get("processed", 0), job.get("total", 0),
                 json.dumps(job.get("result", []), ensure_ascii=False),
                 json.dumps(job.get("errors", []), ensure_ascii=False)),
            )
            db.commit()
        finally:
            db.close()
        return dict(job)


@storage
def get_job(vault, job_id):
    with _LOCK:
        if job_id in _JOBS:
            return dict(_JOBS[job_id])
    db = connect(vault)
    try:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError(f"任务不存在：{job_id}")
        return {"id": row["id"], "type": row["type"], "status": row["status"], "created_at": row["created_at"],
                "finished_at": row["finished_at"], "processed": row["processed"], "total": row["total"],
                "result": _loads(row["result"], []), "errors": _loads(row["errors"], []),
                "done": row["status"] in ("done", "error")}
    finally:
        db.close()


JOB_TYPES = ("detect", "extract", "classify", "auto")


@storage
def start_job(vault, job_type, payload):
    if job_type not in JOB_TYPES:
        raise ValueError(f"未知任务类型：{job_type}")
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    units = _job_units(job_type, payload)
    if not units:
        raise ValueError("任务没有可处理的内容")
    if job_type in ("detect", "auto", "classify"):
        for unit in units:
            unit.setdefault("reset_epoch", get_item(vault, unit["item_id"])["reset_epoch"])
    _job_update(vault, job_id, type=job_type, status="running", created_at=_now(), finished_at=None,
                processed=0, total=len(units), result=[], errors=[], done=False)
    thread = threading.Thread(target=_run_job, args=(vault, job_id, job_type, units, generation(vault)), daemon=True)
    thread.start()
    return get_job(vault, job_id)


def _job_units(job_type, payload):
    if job_type in ("detect", "auto"):
        return [u for u in (payload.get("items") or []) if isinstance(u, dict) and u.get("item_id")]
    if job_type == "extract":
        return [u for u in (payload.get("regions") or []) if isinstance(u, dict) and u.get("region_id")]
    return [u for u in (payload.get("cards") or []) if isinstance(u, dict) and u.get("item_id")]


def _run_job(vault, job_id, job_type, units, started_generation=None):
    try:
        with task(vault, started_generation):
            _run_job_current(vault, job_id, job_type, units)
    except Exception as exc:
        from .vault_lifecycle import VaultChanged
        if not isinstance(exc, VaultChanged):
            raise
        # 恢复后旧任务不能在新库登记终态；新库恢复入口负责 interrupted。


def _run_job_current(vault, job_id, job_type, units):
    from . import ai_assist  # 延迟导入，避免循环
    results, errors = [], []
    for index, unit in enumerate(units):
        try:
            if job_type == "detect":
                results.append(_run_detect(vault, ai_assist, unit))
            elif job_type == "auto":
                results.append(_run_auto(vault, ai_assist, unit))
            elif job_type == "extract":
                results.append(_run_extract(vault, ai_assist, unit))
            else:
                results.append(_run_classify(vault, ai_assist, unit))
        except Exception as exc:  # noqa: BLE001 - 单个单元失败不影响其他
            errors.append({"unit": {k: v for k, v in unit.items() if k not in ("crop", "strips")}, "msg": str(exc)})
        _job_update(vault, job_id, processed=index + 1, result=results, errors=errors)
    _job_update(vault, job_id, status="done", done=True, finished_at=_now(), result=results, errors=errors)


# ────────────────────────── 框选提供方 ──────────────────────────

PROVIDERS = ("vlm", "local_http")


def detect_provider(vault, requested=None):
    """读取框选提供方；旧配置 template 在升级后按默认多模态模型处理。"""
    provider = requested or load_config(vault).get("inbox_detect_provider") or "vlm"
    if not requested and provider == "template":
        provider = "vlm"
    if provider not in PROVIDERS:
        raise ValueError(f"未知框选提供方：{provider}")
    return provider


def _pillow_strips(vault, item):
    """有 Pillow 时按 slice_plan 在服务端切条带（JPEG）；没有则返回 None。"""
    try:
        from PIL import Image  # noqa: WPS433
    except Exception:
        return None
    plan = slice_plan(item["width"], item["height"])
    path = _raw_path(vault, item["sha256"], item["mime"])
    strips = []
    with Image.open(path) as im:
        w, h = im.size
        for y0, y1 in plan:
            buf = io.BytesIO()
            im.crop((0, int(y0 * h), w, int(y1 * h))).convert("RGB").save(buf, format="JPEG", quality=85)
            strips.append({"y0": y0, "y1": y1, "data": _to_data_url("image/jpeg", buf.getvalue())})
    return strips


def _detect_with_provider(vault, ai, item, unit, provider):
    """按提供方取框。返回 (boxes, strips_count)。boxes 为整图归一化坐标。"""
    strips = unit.get("strips")
    if not strips:
        strips = _pillow_strips(vault, item)
    if not strips:
        # 前端没切片且无 Pillow：整图送模型（长图会被模型端压缩，精度下降）
        mime, data = raw_file(vault, item["id"])
        strips = [{"y0": 0.0, "y1": 1.0, "data": _to_data_url(mime, data)}]
    outputs = []
    for strip in strips:
        if provider == "local_http":
            span = float(strip["y1"]) - float(strip["y0"])
            boxes = ai.detect_regions_local(load_config(vault).get("inbox_local_detect_url", ""), strip["data"],
                                            layout=item.get("layout") or "other", image_width=item["width"],
                                            image_height=int(round(item["height"] * span)))
        else:
            boxes = ai.detect_regions(vault, strip["data"], layout=item.get("layout") or "other")
        outputs.append({"y0": strip["y0"], "y1": strip["y1"], "boxes": boxes})
    return merge_strip_boxes(outputs), len(strips)


def _should_blind(vault, unit):
    """盲标：单元里显式 blind，或按配置每 N 张一次（计数器存 meta）。"""
    if unit.get("blind") is not None:
        return bool(unit.get("blind"))
    try:
        every = int(load_config(vault).get("inbox_blind_every") or 0)
    except (TypeError, ValueError):
        every = 0
    if every <= 0:
        return False
    with _LOCK:
        db = connect(vault)
        try:
            count = _meta_incr(db, "detect_counter")
            db.commit()
        finally:
            db.close()
    return count % every == 0


def blind_eval(regions, ai_boxes):
    """盲标评估：对每个 AI 框找同角色 IoU 最高的人工最终框。返回 {pairs:[{role, iou}], mean_iou, matched, total}。"""
    pairs = []
    for b in ai_boxes or []:
        best = 0.0
        for r in regions:
            if r["role"] == b.get("role"):
                best = max(best, iou(r, b))
        pairs.append({"role": b.get("role"), "iou": round(best, 3)})
    matched = sum(1 for p in pairs if p["iou"] >= 0.5)
    return {"pairs": pairs, "total": len(pairs), "matched": matched,
            "mean_iou": round(sum(p["iou"] for p in pairs) / len(pairs), 3) if pairs else None}


def _run_detect(vault, ai, unit):
    item = get_item(vault, unit["item_id"])
    epoch = unit.get("reset_epoch", item["reset_epoch"])
    if item["reset_epoch"] != epoch:
        raise ValueError("图片已重置，旧框选任务已失效")
    if item["status"] in ("done", "discarded"):
        raise ValueError("已结束的图片不再框选")
    provider = detect_provider(vault, unit.get("provider"))
    boxes, strips_n = _detect_with_provider(vault, ai, item, unit, provider)
    summary = [{k: b[k] for k in ("role", "card", "x", "y", "w", "h", "conf")} for b in boxes]
    blind = _should_blind(vault, unit)
    if blind:
        # 不展示 AI 框：只存到 blind_boxes，等人工画完、标记就绪时成对写进 item.ready 事件
        with _LOCK:
            db = connect(vault)
            try:
                fresh = db.execute("SELECT reset_epoch, revision, status FROM items WHERE id=?", (item["id"],)).fetchone()
                if not fresh or fresh["reset_epoch"] != epoch or fresh["status"] not in ("pending", "boxed"):
                    raise ValueError("图片已重置或结束，旧框选任务已失效")
                if fresh["revision"] != item["revision"]:
                    raise InboxConflict("框选期间图片已修改，旧检测结果未写入", current_revision=fresh["revision"])
                db.execute("UPDATE items SET blind=1, blind_boxes=?, revision=revision+1, updated_at=? WHERE id=?",
                           (json.dumps(summary, ensure_ascii=False), _now(), item["id"]))
                db.commit()
            finally:
                db.close()
        _log(vault, "ai.detect", {"item_id": item["id"], "provider": provider, "strips": strips_n,
                                  "blind": True, "boxes": summary})
        return {"item_id": item["id"], "provider": provider, "blind": True, "boxes": 0, "hidden": len(boxes),
                "regions": item["regions"]}
    regions = [
        {"card": b["card"], "role": b["role"], "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"],
         "origin": "ai", "conf": round(b["conf"], 3),
         "ai_box": {"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]}, "convert": "auto"}
        for b in boxes
    ]
    with _LOCK:
        fresh = get_item(vault, item["id"])
        if fresh["reset_epoch"] != epoch or fresh["status"] not in ("pending", "boxed"):
            raise ValueError("图片已重置或结束，旧框选任务已失效")
        if fresh["revision"] != item["revision"]:
            raise InboxConflict("框选期间图片已修改，旧检测结果未写入", current_revision=fresh["revision"])
        if not unit.get("replace"):
            # 模型调用期间可能新增人工框，只在最新区域后追加 AI 框。
            regions = fresh["regions"] + regions
        updated = update_item(vault, item["id"], {"regions": regions, "reset_epoch": epoch,
                                                   "expected_revision": fresh["revision"]})
    _log(vault, "ai.detect", {"item_id": item["id"], "provider": provider, "strips": strips_n, "boxes": summary})
    result = {"item_id": item["id"], "provider": provider, "blind": False, "boxes": len(boxes),
              "regions": updated["regions"]}
    auto = _auto_policy(vault, ai, updated, boxes)
    if auto:
        result["auto"] = auto
    return result


def _auto_policy(vault, ai, item, boxes):
    """置信度 ≥ inbox_auto_ready_conf 时自动提取并判断，保留人工审核。返回 None 表示未触发。
    转文本需要裁图：服务端有 Pillow 或框覆盖全图；否则中止并记录原因。"""
    try:
        threshold = float(load_config(vault).get("inbox_auto_ready_conf") or 0)
    except (TypeError, ValueError):
        threshold = 0.0
    if threshold <= 0 or not boxes:
        return None
    if item["status"] not in ("pending", "boxed"):
        return None
    if not any(b["role"] == "question" for b in boxes) or min(b["conf"] for b in boxes) < threshold:
        return {"triggered": False, "reason": f"置信度未达到 {threshold}"}
    if any(r["origin"] != "ai" for r in item["regions"]):
        return {"triggered": False, "reason": "已有人工框，不自动处理"}
    outcome = {"triggered": True, "extracted": 0, "ready": False}
    for r in item["regions"]:
        if r["role"] == "ignore" or r["convert"] == "image" or (r["convert"] == "text" and r["text"]):
            continue
        try:
            _run_extract(vault, ai, {"region_id": r["id"], "reset_epoch": item["reset_epoch"]})
            outcome["extracted"] += 1
        except Exception as exc:  # noqa: BLE001
            outcome["reason"] = f"自动转文本失败：{exc}"
            _log(vault, "item.auto", {"item_id": item["id"], **outcome})
            return outcome
    outcome["reason"] = "提取完成，待人工审核"
    _log(vault, "item.auto", {"item_id": item["id"], **outcome})
    return outcome


def _run_auto(vault, ai, unit):
    """无人值守：服务端切片 → detect（配置的提供方）→ 自动策略。前端不在环，需 Pillow 或整图即题目。"""
    detect_unit = {"item_id": unit["item_id"], "provider": unit.get("provider"),
                   "replace": unit.get("replace", False)}
    if "reset_epoch" in unit:
        detect_unit["reset_epoch"] = unit["reset_epoch"]
    return _run_detect(vault, ai, detect_unit)


def _run_extract(vault, ai, unit):
    region_id = unit["region_id"]
    db = connect(vault)
    try:
        row = db.execute("SELECT * FROM regions WHERE id=?", (region_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise ValueError(f"区域不存在：{region_id}")
    region = _row_region(row)
    item = get_item(vault, row["item_id"])
    epoch = unit.get("reset_epoch", item["reset_epoch"])
    if item["reset_epoch"] != epoch:
        raise ValueError("图片已重置，旧提取任务已失效")
    if item["status"] in ("done", "discarded"):
        raise ValueError("图片已结束，旧提取任务已失效")
    image = region_image(vault, item, region, unit.get("crop"))
    mode = region["convert"]
    # 模型调用不占写锁；写回时核对该区域，避免覆盖其它框或已经修改的内容。
    signature = lambda r: tuple(r.get(k) for k in
                               ("role", "x", "y", "w", "h", "convert", "text", "judge", "text_status"))
    def apply_result(result=None):
        with _LOCK:
            fresh = get_item(vault, item["id"])
            if fresh["reset_epoch"] != epoch:
                raise ValueError("图片已重置，旧提取任务已失效")
            if fresh["status"] in ("done", "discarded"):
                raise ValueError("图片已录入或丢弃，不能写入提取结果")
            target = next((r for r in fresh["regions"] if r["id"] == region_id), None)
            if not target or signature(target) != signature(region):
                raise ValueError("区域已修改，请重新提取")
            if result is None:
                target["text_status"] = "error"
            else:
                ok = result["convertible"]
                target["judge"] = {"ok": ok, "reason": result.get("reason", "")}
                target["judge_overridden"] = False
                target["convert"] = "text" if ok else "image"
                # 不可转时不把局部识别文字当成完整题面；旧文本留存，人工仍可切回。
                if ok:
                    target["text"] = result["text"]
                target["text_status"] = "done" if ok else "none"
            update_item(vault, item["id"], {"regions": fresh["regions"], "status": "boxed",
                                                   "reset_epoch": epoch, "expected_revision": fresh["revision"]})
            return target
    try:
        result = ai.extract_region(vault, image, role=region["role"], judge=True)
        if not isinstance(result.get("convertible"), bool):
            raise ValueError("模型未返回有效的可提取判断，请重试")
        if result["convertible"] and not (result.get("text") or "").strip():
            raise ValueError("模型未返回文本，请重试")
    except Exception:
        apply_result()
        raise
    target = apply_result(result)
    _log(vault, "ai.extract", {"item_id": item["id"], "region_id": region_id, "role": region["role"],
                               "convert_before": mode, "judge": result["convertible"],
                               "reason": result.get("reason", ""), "chars": len(result.get("text") or "")})
    return {"region_id": region_id, "convert": target["convert"],
            "judge": result["convertible"], "reason": result.get("reason", ""),
            "text": target["text"]}


def _run_classify(vault, ai, unit):
    item = get_item(vault, unit["item_id"])
    epoch = unit.get("reset_epoch", item["reset_epoch"])
    if item["reset_epoch"] != epoch:
        raise ValueError("图片已重置，旧分类任务已失效")
    if item["status"] in ("done", "discarded"):
        raise ValueError("图片已结束，旧分类任务已失效")
    card = int(unit.get("card", 1) or 1)
    question = next((r for r in item["regions"] if r["card"] == card and r["role"] == "question"), None)
    if not question:
        raise ValueError(f"题卡 {card} 没有题目框")
    image = region_image(vault, item, question, unit.get("crop"))
    form = item["cards"].get(str(card), {"subject": "", "category": "", "difficulty": 5, "tags": [], "cause": ""})
    result = ai.classify_question(vault, image, hint_subject=form.get("subject", ""), hint_category=form.get("category", ""))
    with _LOCK:
        fresh = get_item(vault, item["id"])
        if fresh["reset_epoch"] != epoch or fresh["status"] in ("done", "discarded"):
            raise ValueError("图片已重置或结束，旧分类任务已失效")
        if fresh["revision"] != item["revision"]:
            raise InboxConflict("分类期间图片已修改，旧分类结果未写入", current_revision=fresh["revision"])
        if not any(r["id"] == question["id"] and r["role"] == "question" for r in fresh["regions"]):
            raise ValueError("题目框已修改，旧分类结果已失效")
        merged = dict(fresh["cards"].get(str(card), form))
        manual = merged.get("manual_fields") or {}
        sources = dict(merged.get("field_sources") or {})
        provenance = {"kind": "ai", "image_sha": fresh["sha256"], "region_id": question["id"],
                      "source_revision": item["revision"]}
        if not manual.get("subject") and not merged.get("subject") and result.get("subject"):
            merged["subject"] = result["subject"]
            sources["subject"] = provenance
        if not manual.get("category") and not merged.get("category") and result.get("category"):
            merged["category"] = result["category"]
            sources["category"] = provenance
        if not manual.get("difficulty") and merged.get("difficulty", 5) == 5:
            merged["difficulty"] = result.get("difficulty", merged.get("difficulty", 5))
            sources["difficulty"] = provenance
        tags = list(merged.get("tags") or [])
        if not manual.get("tags"):
            for tag in result.get("knowledge_tags") or []:
                if tag not in tags:
                    tags.append(tag)
            sources["tags"] = provenance
        merged["tags"] = tags
        merged["field_sources"] = sources
        merged["classified"] = True
        update_item(vault, item["id"], {"cards": {str(card): merged}, "reset_epoch": epoch,
                                               "expected_revision": fresh["revision"]}, _ai=True)
    return {"item_id": item["id"], "card": card, "form": merged}


# ────────────────────────── 提交（写题库） ──────────────────────────

def commit_item(vault, item_id, card=1, form=None, crops=None,
                expected_revision=None, reset_epoch=None, require_version=False):
    from .inbox_commit import commit_item as commit
    return commit(vault, item_id, card, form, crops, expected_revision, reset_epoch, require_version)


# ────────────────────────── 数据集 ──────────────────────────

@storage
def register_chat_training(vault, sha, data, draft_id, boxes):
    """按图哈希登记聊天训练标注，不经过上传队列与自动 detect。"""
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("训练原图 SHA 与内容不符")
    mime, width, height = image_size(data)
    if not boxes:
        raise ValueError("训练图没有有效框")
    with _LOCK:
        db = connect(vault)
        try:
            item = db.execute("SELECT * FROM items WHERE sha256=?", (sha,)).fetchone()
            if item:
                item_id = item["id"]
            else:
                item_id = _new_item_id()
                now = _now()
                db.execute("INSERT INTO items(id,sha256,file,mime,width,height,bytes,source,uploaded_at,"
                           "status,layout,link_uid,link_question_id,updated_at,training_only) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (item_id, sha, f"{sha}.{_MIME_EXT.get(mime, 'png')}", mime, width, height,
                            len(data), "chat", now, "ready", "other", None, None, now, 1))
            raw_path = _raw_path(vault, sha, mime)
            if not os.path.exists(raw_path):
                with open(raw_path, "wb") as file:
                    file.write(data)
            # 草稿库登记状态可能在收件箱事务提交后才失败；重试以本次完整框集覆盖旧关联。
            db.execute("DELETE FROM chat_training_boxes WHERE draft_id=? AND image_sha=?", (draft_id, sha))
            for order, box in enumerate(boxes):
                rect = box["box"]
                ident = "ct_" + hashlib.sha256((draft_id + ":" + box["id"]).encode()).hexdigest()[:24]
                db.execute("INSERT INTO chat_training_boxes(id,item_id,draft_id,image_sha,section,ord,x,y,w,h,origin,ai_box) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "section=excluded.section,ord=excluded.ord,x=excluded.x,y=excluded.y,w=excluded.w,h=excluded.h,"
                           "origin=excluded.origin,ai_box=excluded.ai_box",
                           (ident, item_id, draft_id, sha, box["section"], order,
                            rect["x"], rect["y"], rect["w"], rect["h"], box["box_origin"],
                            json.dumps(box.get("ai_box"), ensure_ascii=False)))
            db.commit()
        finally:
            db.close()
    _log(vault, "image.train", {"item_id": item_id, "sha256": sha, "draft_id": draft_id,
                               "boxes": len(boxes)})
    return item_id


def _dataset_items(db):
    rows = db.execute("SELECT * FROM items WHERE status!='discarded' OR id IN "
                      "(SELECT DISTINCT item_id FROM chat_training_boxes) ORDER BY uploaded_at").fetchall()
    items = []
    for row in rows:
        item = _row_item(db, row)
        chat_rows = db.execute("SELECT * FROM chat_training_boxes WHERE item_id=? ORDER BY draft_id,ord,id",
                               (row["id"],)).fetchall()
        item["chat_annotations"] = [{"draft_id": r["draft_id"], "id": r["id"]} for r in chat_rows]
        for r in chat_rows:
            item["regions"].append({"id": r["id"], "card": 1, "ord": r["ord"],
                                    "role": "question" if r["section"] == "题目" else "answer",
                                    "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"],
                                    "origin": r["origin"], "conf": None,
                                    "ai_box": _loads(r["ai_box"], None), "convert": "image",
                                    "text": None, "text_status": "none", "judge": None,
                                    "judge_overridden": False, "source": "chat", "draft_id": r["draft_id"]})
        items.append(item)
    return items, {r["id"]: r for r in rows}

@storage
def dataset_stats(vault):
    db = connect(vault)
    try:
        items, _rows_by_id = _dataset_items(db)
    finally:
        db.close()
    regions = [r for i in items for r in i["regions"]]
    by_role = {role: sum(1 for r in regions if r["role"] == role) for role in ROLES}
    by_layout = {}
    for i in items:
        by_layout[i["layout"] or "other"] = by_layout.get(i["layout"] or "other", 0) + 1
    ai_regions = [r for r in regions if r["origin"] in ("ai", "ai_edited")]
    adopted = sum(1 for r in ai_regions if r["origin"] == "ai")
    edited = [r for r in ai_regions if r["origin"] == "ai_edited"]
    ious = [iou(r, r["ai_box"]) for r in edited if r.get("ai_box")]
    rejected = _rejected_count(vault)
    blind = _blind_stats(vault)
    decided = [r for r in regions if r["role"] != "ignore" and r["convert"] in ("text", "image")]
    judged = [r for r in decided if r.get("judge")]
    agree = sum(1 for r in judged if (r["judge"].get("ok") and r["convert"] == "text")
                or (not r["judge"].get("ok") and r["convert"] == "image"))
    finished = sum(1 for i in items if i["status"] == "done")
    chat_images = sum(1 for i in items if i["chat_annotations"])
    chat_boxes = sum(len(i["chat_annotations"]) for i in items)
    return {
        "images": len(items), "done": finished,
        "chat": {"images": chat_images, "boxes": chat_boxes},
        "boxes": {"total": len(regions), **by_role},
        "layouts": by_layout,
        "ai": {"suggested": len(ai_regions) + rejected, "adopted": adopted, "edited": len(edited), "rejected": rejected,
               "adoption_rate": round(adopted / (len(ai_regions) + rejected), 3) if (ai_regions or rejected) else None,
               "mean_iou_edited": round(sum(ious) / len(ious), 3) if ious else None},
        "convert": {"text": sum(1 for r in decided if r["convert"] == "text"),
                    "image": sum(1 for r in decided if r["convert"] == "image"),
                    "judged": len(judged), "agree": agree,
                    "agreement_rate": round(agree / len(judged), 3) if judged else None},
        "blind": blind,
        "storage": storage_stats(vault),
    }


@storage
def _rejected_count(vault):
    """拒绝的 AI 框数：meta 里增量维护；老库第一次从 annotations.jsonl 回填一次。"""
    with _LOCK:
        db = connect(vault)
        try:
            value = _meta_get(db, "rejected_ai_boxes")
            if value is not None:
                return int(value)
            rejected = 0
            path = os.path.join(inbox_dir(vault), "annotations.jsonl")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as file:
                    for line in file:
                        rec = _loads(line, {})
                        if rec.get("event") == "regions.update":
                            before_ai = {r["id"] for r in rec.get("before", []) if r.get("origin") == "ai"}
                            after_ids = {r["id"] for r in rec.get("after", [])}
                            rejected += len(before_ai - after_ids)
            _meta_set(db, "rejected_ai_boxes", rejected)
            db.commit()
            return rejected
        finally:
            db.close()


@storage
def _blind_stats(vault):
    """盲标评估集：已就绪/已录入的盲标图，人工最终框 vs 当时隐藏的 AI 框。"""
    db = connect(vault)
    try:
        rows = db.execute("SELECT * FROM items WHERE blind=1 AND status!='discarded'").fetchall()
        pending = 0
        evals = []
        for row in rows:
            if row["status"] not in ("ready", "done"):
                pending += 1
                continue
            item = _row_item(db, row)
            evals.append(blind_eval(item["regions"], _loads(row["blind_boxes"], []) or []))
    finally:
        db.close()
    ious = [p["iou"] for e in evals for p in e["pairs"]]
    return {"images": len(rows), "evaluated": len(evals), "pending": pending,
            "ai_boxes": len(ious), "matched": sum(1 for v in ious if v >= 0.5),
            "mean_iou": round(sum(ious) / len(ious), 3) if ious else None}


# ────────────────────────── 清理 ──────────────────────────

@storage
def storage_stats(vault):
    def _size(path):
        total = 0
        if os.path.isdir(path):
            for name in os.listdir(path):
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    total += os.path.getsize(full)
        return total
    db = connect(vault)
    try:
        discarded = db.execute("SELECT COUNT(*) FROM items WHERE status='discarded' AND file IS NOT NULL").fetchone()[0]
    finally:
        db.close()
    return {"raw_bytes": _size(raw_dir(vault)), "crops_bytes": _size(crops_dir(vault)), "discarded": discarded}


@storage
def cleanup(vault, discarded_days=None, crops=False):
    """删除超期（默认 inbox_discard_keep_days 天）的已丢弃原图；crops=True 时清空裁剪缓存。
    丢弃项的行保留（file 置空）以便事件回溯；被未丢弃项共享的原图（同 sha256 不可能，主键唯一）无需考虑。"""
    if discarded_days is None:
        try:
            discarded_days = int(load_config(vault).get("inbox_discard_keep_days") or 7)
        except (TypeError, ValueError):
            discarded_days = 7
    removed_raw, removed_bytes = 0, 0
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max(0, discarded_days))).isoformat(timespec="seconds")
    with _LOCK:
        db = connect(vault)
        try:
            rows = db.execute("SELECT id, sha256, mime FROM items WHERE status='discarded' AND file IS NOT NULL "
                              "AND updated_at<=? AND id NOT IN (SELECT DISTINCT item_id FROM chat_training_boxes)",
                              (cutoff,)).fetchall()
            for row in rows:
                path = _raw_path(vault, row["sha256"], row["mime"])
                if os.path.exists(path):
                    removed_bytes += os.path.getsize(path)
                    os.remove(path)
                    removed_raw += 1
                db.execute("UPDATE items SET file=NULL WHERE id=?", (row["id"],))
            db.commit()
        finally:
            db.close()
    removed_crops = 0
    if crops:
        folder = crops_dir(vault)
        for name in os.listdir(folder):
            full = os.path.join(folder, name)
            if os.path.isfile(full):
                os.remove(full)
                removed_crops += 1
    if removed_raw or removed_crops:
        _log(vault, "inbox.cleanup", {"discarded_days": discarded_days, "raw": removed_raw,
                                      "raw_bytes": removed_bytes, "crops": removed_crops})
    return {"raw": removed_raw, "raw_bytes": removed_bytes, "crops": removed_crops, "discarded_days": discarded_days}


@storage
def cleanup_expired(vault):
    """上传时顺手跑一次超期清理（只删原图，很便宜）；任何异常都吞掉，不影响上传。"""
    try:
        return cleanup(vault)
    except Exception:  # noqa: BLE001
        return None


@storage
def export_dataset(vault, fmt="omrs_jsonl", include_raw=True):
    """打包 labels + 原图。fmt: omrs_jsonl | yolo。返回 zip bytes。"""
    db = connect(vault)
    try:
        items, rows_by_id = _dataset_items(db)
    finally:
        db.close()
    buf = io.BytesIO()
    class_ids = {"question": 0, "answer": 1}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        lines = []
        for item in items:
            raw_name = f"{item['sha256']}.{_MIME_EXT.get(item['mime'], 'png')}"
            if include_raw:
                path = _raw_path(vault, item["sha256"], item["mime"])
                if os.path.exists(path):
                    zf.write(path, f"images/{raw_name}")
            record = {"item_id": item["id"], "image": f"images/{raw_name}", "width": item["width"],
                      "height": item["height"], "layout": item["layout"], "status": item["status"],
                      "source": item["source"], "training_only": item["training_only"],
                      "chat_annotations": item["chat_annotations"],
                      "regions": _region_summary(item["regions"])}
            if item.get("blind"):
                record["blind"] = True
                record["blind_ai_boxes"] = _loads(rows_by_id[item["id"]]["blind_boxes"], [])
            lines.append(json.dumps(record, ensure_ascii=False))
            if fmt == "yolo":
                yolo = []
                for r in item["regions"]:
                    if r["role"] not in class_ids:
                        continue
                    yolo.append(f"{class_ids[r['role']]} {r['x'] + r['w'] / 2:.6f} {r['y'] + r['h'] / 2:.6f} {r['w']:.6f} {r['h']:.6f}")
                zf.writestr(f"labels/{item['sha256']}.txt", "\n".join(yolo) + ("\n" if yolo else ""))
        zf.writestr("labels.jsonl", "\n".join(lines) + ("\n" if lines else ""))
        if fmt == "yolo":
            zf.writestr("classes.txt", "question\nanswer\n")
        ann = os.path.join(inbox_dir(vault), "annotations.jsonl")
        if os.path.exists(ann):
            zf.write(ann, "annotations.jsonl")
        zf.writestr("README.txt", "OMRS inbox dataset\nlabels.jsonl: 每行一张图，regions 为归一化 [x,y,w,h]（相对原图宽高）。\n"
                                  "origin=ai_edited 的区域带 ai_box（模型原框），可算 IoU。\nannotations.jsonl: 全部人工/AI 事件。\n")
    return buf.getvalue()
