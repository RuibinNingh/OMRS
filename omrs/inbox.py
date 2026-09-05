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
  PRIMARY KEY (item_id, card)
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, type TEXT, status TEXT, created_at TEXT, finished_at TEXT,
  processed INTEGER, total INTEGER, result TEXT, errors TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# v1.13：items 追加的列（盲标）。旧库通过 ALTER 补齐，缺省值保持旧行为。
_ITEM_EXTRA_COLUMNS = (("blind", "INTEGER DEFAULT 0"), ("blind_boxes", "TEXT"))


def connect(vault):
    path = os.path.join(inbox_dir(vault), "inbox.db")
    db = sqlite3.connect(path, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(_SCHEMA)
    existing = {row[1] for row in db.execute("PRAGMA table_info(items)")}
    for column, decl in _ITEM_EXTRA_COLUMNS:
        if column not in existing:
            db.execute(f"ALTER TABLE items ADD COLUMN {column} {decl}")
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
        "tags": _loads(row["tags"], []), "cause": row["cause"] or "", "page": row["page"] or "",
        "classified": bool(row["classified"]), "created_uid": row["created_uid"] or "",
    }


def _row_item(db, row, with_children=True):
    item = {
        "id": row["id"], "sha256": row["sha256"], "file": row["file"], "mime": row["mime"],
        "width": row["width"], "height": row["height"], "bytes": row["bytes"],
        "source": row["source"], "uploaded_at": row["uploaded_at"], "status": row["status"],
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

def upload_images(vault, files, source="desktop"):
    """files: [(filename, bytes)]。返回 {items:[...新建或已存在...], duplicates:[...]}。"""
    created, duplicates = [], []
    with _LOCK:
        db = connect(vault)
        try:
            for filename, data in files:
                if not data:
                    continue
                mime, width, height = image_size(data)
                sha = hashlib.sha256(data).hexdigest()
                existing = db.execute("SELECT * FROM items WHERE sha256=?", (sha,)).fetchone()
                if existing:
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


def list_items(vault, status=None, with_children=True):
    db = connect(vault)
    try:
        if status:
            rows = db.execute("SELECT * FROM items WHERE status=? ORDER BY uploaded_at DESC", (status,))
        else:
            rows = db.execute("SELECT * FROM items WHERE status!='discarded' ORDER BY uploaded_at DESC")
        return [_row_item(db, row, with_children) for row in rows.fetchall()]
    finally:
        db.close()


def get_item(vault, item_id):
    db = connect(vault)
    try:
        row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise ValueError(f"收件箱里没有 {item_id}")
        return _row_item(db, row)
    finally:
        db.close()


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


def _write_cards(db, item_id, cards):
    for key, form in (cards or {}).items():
        try:
            card = int(key)
        except (TypeError, ValueError):
            continue
        tags = form.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，]", tags) if t.strip()]
        db.execute(
            "INSERT INTO cards (item_id, card, subject, category, difficulty, tags, cause, page, classified) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(item_id, card) DO UPDATE SET subject=excluded.subject, "
            "category=excluded.category, difficulty=excluded.difficulty, tags=excluded.tags, cause=excluded.cause, "
            "page=excluded.page, classified=excluded.classified",
            (item_id, card, form.get("subject", ""), form.get("category", ""),
             int(form.get("difficulty", 5) or 5), json.dumps(tags, ensure_ascii=False),
             form.get("cause", ""), form.get("page", ""), 1 if form.get("classified") else 0),
        )


def update_item(vault, item_id, data):
    """整体覆盖式更新：regions（列表）、cards（dict）、layout、status。返回更新后的 item。"""
    with _LOCK:
        db = connect(vault)
        try:
            row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise ValueError(f"收件箱里没有 {item_id}")
            if row["status"] == "done":
                raise ValueError("已录入的图片不能再修改")
            before = _row_item(db, row)
            now = _now()
            if "regions" in data and isinstance(data["regions"], list):
                _write_regions(db, item_id, data["regions"], now)
            if "cards" in data and isinstance(data["cards"], dict):
                _write_cards(db, item_id, data["cards"])
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
            db.execute("UPDATE items SET updated_at=? WHERE id=?", (now, item_id))
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
        if r["convert"] == "auto":
            raise ValueError("还有区域没决定「转文本 / 保留图片」")
        if r["convert"] == "text" and not (r["text"] or "").strip():
            raise ValueError("「转文本」区域还没有文本")


def discard_item(vault, item_id):
    with _LOCK:
        db = connect(vault)
        try:
            row = db.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise ValueError(f"收件箱里没有 {item_id}")
            if row["status"] == "done":
                raise ValueError("已录入的图片不能丢弃")
            db.execute("UPDATE items SET status='discarded', updated_at=? WHERE id=?", (_now(), item_id))
            db.commit()
        finally:
            db.close()
    _log(vault, "item.discard", {"item_id": item_id})
    return {"item_id": item_id, "status": "discarded"}


def save_crop(vault, region_id, data_url):
    mime, data = _data_url_bytes(data_url)
    if mime not in _MIME_EXT:
        raise ValueError("裁剪图仅支持 PNG / JPEG / GIF")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", region_id)
    path = os.path.join(crops_dir(vault), f"{safe}.{_MIME_EXT[mime]}")
    with open(path, "wb") as file:
        file.write(data)
    return path


def _crop_data_url(vault, region_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", region_id)
    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg"), ("gif", "image/gif")):
        path = os.path.join(crops_dir(vault), f"{safe}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as file:
                return _to_data_url(mime, file.read())
    return None


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


def start_job(vault, job_type, payload):
    if job_type not in JOB_TYPES:
        raise ValueError(f"未知任务类型：{job_type}")
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    units = _job_units(job_type, payload)
    if not units:
        raise ValueError("任务没有可处理的内容")
    _job_update(vault, job_id, type=job_type, status="running", created_at=_now(), finished_at=None,
                processed=0, total=len(units), result=[], errors=[], done=False)
    thread = threading.Thread(target=_run_job, args=(vault, job_id, job_type, units), daemon=True)
    thread.start()
    return get_job(vault, job_id)


def _job_units(job_type, payload):
    if job_type in ("detect", "auto"):
        return [u for u in (payload.get("items") or []) if isinstance(u, dict) and u.get("item_id")]
    if job_type == "extract":
        return [u for u in (payload.get("regions") or []) if isinstance(u, dict) and u.get("region_id")]
    return [u for u in (payload.get("cards") or []) if isinstance(u, dict) and u.get("item_id")]


def _run_job(vault, job_id, job_type, units):
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

PROVIDERS = ("vlm", "template", "local_http")

# 没有可参考的同版式样本时，作业帮截图的默认模板（单位：图片宽度的倍数；题目框按像素锚定顶部，
# 答案框从「答案」标题附近起一直到底）。有人工样本后模板会自动改为沿用最近一张的框位。
_TEMPLATE_DEFAULTS = {
    "zuoyebang": [
        {"role": "question", "x": 0.03, "y_w": 0.20, "h_w": 0.75, "w": 0.94},
        {"role": "answer", "x": 0.03, "y_w": 1.30, "h_w": None, "w": 0.94},
    ],
    "plain": [{"role": "question", "x": 0.0, "y_w": 0.0, "h_w": None, "w": 1.0}],
}


def _template_reference(db, item):
    """最近一张同版式、已就绪/已录入、带人工确认框的图，作为模板来源。"""
    rows = db.execute(
        "SELECT * FROM items WHERE layout=? AND id!=? AND status IN ('ready','done') ORDER BY updated_at DESC LIMIT 20",
        (item["layout"] or "other", item["id"])).fetchall()
    for row in rows:
        ref = _row_item(db, row)
        if any(r["origin"] in ("manual", "ai_edited") for r in ref["regions"]) and \
                any(r["role"] == "question" for r in ref["regions"]):
            return ref
    return None


def template_boxes(item, reference=None):
    """版式模板框选（零联网）。有 reference 时沿用其框位：横向照搬；y<0.35 的框（题目）按像素锚定顶部，
    其余（答案）按比例并延伸到底。没有 reference 时按 _TEMPLATE_DEFAULTS 用宽度倍数给初值。"""
    width, height = float(item["width"] or 1), float(item["height"] or 1)
    boxes = []
    if reference:
        rw, rh = float(reference["width"] or 1), float(reference["height"] or 1)
        for r in reference["regions"]:
            if r["role"] == "ignore":
                continue
            anchored = r["y"] < 0.35
            y = min(0.95, r["y"] * rh / height) if anchored else r["y"]
            h = min(1.0 - y, r["h"] * rh / height) if anchored else (1.0 - y if r["role"] == "answer" else min(1.0 - y, r["h"]))
            boxes.append({"role": r["role"], "card": r["card"], "x": r["x"], "y": y, "w": r["w"], "h": h, "conf": 0.6})
        return [b for b in boxes if b["w"] > 0 and b["h"] > 0]
    for t in _TEMPLATE_DEFAULTS.get(item["layout"] or "", []):
        y = min(0.95, t["y_w"] * width / height)
        h = (1.0 - y) if t["h_w"] is None else min(1.0 - y, t["h_w"] * width / height)
        if h > 0:
            boxes.append({"role": t["role"], "card": 1, "x": t["x"], "y": y, "w": t["w"], "h": h, "conf": 0.4})
    return boxes


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
    if provider == "template":
        db = connect(vault)
        try:
            ref = _template_reference(db, item)
        finally:
            db.close()
        boxes = template_boxes(item, ref)
        if not boxes:
            raise ValueError(f"版式「{item['layout'] or 'other'}」没有模板，也没有可沿用的同版式样本")
        return boxes, 0
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
    if item["status"] == "done":
        raise ValueError("已录入的图片不再框选")
    provider = unit.get("provider") or load_config(vault).get("inbox_detect_provider") or "vlm"
    if provider not in PROVIDERS:
        raise ValueError(f"未知框选提供方：{provider}")
    boxes, strips_n = _detect_with_provider(vault, ai, item, unit, provider)
    summary = [{k: b[k] for k in ("role", "card", "x", "y", "w", "h", "conf")} for b in boxes]
    blind = _should_blind(vault, unit)
    if blind:
        # 不展示 AI 框：只存到 blind_boxes，等人工画完、标记就绪时成对写进 item.ready 事件
        with _LOCK:
            db = connect(vault)
            try:
                db.execute("UPDATE items SET blind=1, blind_boxes=?, updated_at=? WHERE id=?",
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
    if not unit.get("replace") and item["regions"]:
        # 已有人工框时不覆盖，只把 AI 框补在后面
        regions = item["regions"] + regions
    updated = update_item(vault, item["id"], {"regions": regions})
    _log(vault, "ai.detect", {"item_id": item["id"], "provider": provider, "strips": strips_n, "boxes": summary})
    result = {"item_id": item["id"], "provider": provider, "blind": False, "boxes": len(boxes),
              "regions": updated["regions"]}
    auto = _auto_policy(vault, ai, updated, boxes)
    if auto:
        result["auto"] = auto
    return result


def _auto_policy(vault, ai, item, boxes):
    """置信度 ≥ inbox_auto_ready_conf 时自动转文本（auto 判断）并置就绪。返回 None 表示未触发。
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
            _run_extract(vault, ai, {"region_id": r["id"]})
            outcome["extracted"] += 1
        except Exception as exc:  # noqa: BLE001
            outcome["reason"] = f"自动转文本失败：{exc}"
            _log(vault, "item.auto", {"item_id": item["id"], **outcome})
            return outcome
    try:
        update_item(vault, item["id"], {"status": "ready"})
        outcome["ready"] = True
    except Exception as exc:  # noqa: BLE001
        outcome["reason"] = f"未能自动置就绪：{exc}"
    _log(vault, "item.auto", {"item_id": item["id"], **outcome})
    return outcome


def _run_auto(vault, ai, unit):
    """无人值守：服务端切片 → detect（配置的提供方）→ 自动策略。前端不在环，需 Pillow 或整图即题目。"""
    return _run_detect(vault, ai, {"item_id": unit["item_id"], "provider": unit.get("provider"),
                                   "replace": unit.get("replace", False)})


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
    image = region_image(vault, item, region, unit.get("crop"))
    mode = region["convert"]
    result = ai.extract_region(vault, image, role=region["role"], judge=(mode == "auto"))
    regions = item["regions"]
    for r in regions:
        if r["id"] == region_id:
            r["judge"] = {"ok": bool(result.get("convertible", True)), "reason": result.get("reason", "")}
            if mode == "auto":
                r["convert"] = "text" if result.get("convertible", True) else "image"
            if r["convert"] == "text":
                r["text"] = result.get("text", "")
                r["text_status"] = "done" if (r["text"] or "").strip() else "error"
            else:
                r["text_status"] = "none"
    update_item(vault, item["id"], {"regions": regions})
    _log(vault, "ai.extract", {"item_id": item["id"], "region_id": region_id, "role": region["role"],
                               "convert_before": mode, "judge": result.get("convertible", True),
                               "reason": result.get("reason", ""), "chars": len(result.get("text") or "")})
    return {"region_id": region_id, "convert": [r["convert"] for r in regions if r["id"] == region_id][0],
            "judge": result.get("convertible", True), "reason": result.get("reason", ""),
            "text": result.get("text", "")}


def _run_classify(vault, ai, unit):
    item = get_item(vault, unit["item_id"])
    card = int(unit.get("card", 1) or 1)
    question = next((r for r in item["regions"] if r["card"] == card and r["role"] == "question"), None)
    if not question:
        raise ValueError(f"题卡 {card} 没有题目框")
    image = region_image(vault, item, question, unit.get("crop"))
    form = item["cards"].get(str(card), {"subject": "", "category": "", "difficulty": 5, "tags": [], "cause": "", "page": ""})
    result = ai.classify_question(vault, image, hint_subject=form.get("subject", ""), hint_category=form.get("category", ""))
    merged = dict(form)
    if not merged.get("subject") and result.get("subject"):
        merged["subject"] = result["subject"]
    if not merged.get("category") and result.get("category"):
        merged["category"] = result["category"]
    merged["difficulty"] = result.get("difficulty", merged.get("difficulty", 5))
    tags = list(merged.get("tags") or [])
    for tag in result.get("knowledge_tags") or []:
        if tag not in tags:
            tags.append(tag)
    merged["tags"] = tags
    merged["classified"] = True
    update_item(vault, item["id"], {"cards": {str(card): merged}})
    return {"item_id": item["id"], "card": card, "form": merged}


# ────────────────────────── 提交（写题库） ──────────────────────────

def commit_item(vault, item_id, card=1, form=None, crops=None):
    """把一张题卡写成题目：文本区拼进正文，图片区裁图嵌入。成功后 item → done。"""
    item = get_item(vault, item_id)
    if item["status"] == "done":
        raise ValueError("这张图已经录入过了")
    card = int(card or 1)
    regions = [r for r in item["regions"] if r["card"] == card and r["role"] != "ignore"]
    if not any(r["role"] == "question" for r in regions):
        raise ValueError(f"题卡 {card} 没有题目框")
    saved = dict(item["cards"].get(str(card), {}))
    saved.update({k: v for k, v in (form or {}).items() if k in ("subject", "category", "difficulty", "tags", "labels", "cause", "page")})
    subject = str(saved.get("subject") or "").strip()
    category = str(saved.get("category") or "").strip()
    if not subject or not category:
        raise ValueError("科目和分类是必填项")
    tags = saved.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,，]", tags) if t.strip()]
    labels = saved.get("labels") or []
    if isinstance(labels, str):
        labels = [t.strip() for t in re.split(r"[,，]", labels) if t.strip()]
    crops = crops or {}

    texts = {"question": [], "answer": []}
    images = {"question": [], "answer": []}
    for r in regions:
        if r["convert"] == "auto":
            raise ValueError(f"区域 {r['id']} 还没决定转文本还是保留图片")
        if r["convert"] == "text":
            if not (r["text"] or "").strip():
                raise ValueError(f"区域 {r['id']} 选择了转文本但没有文本")
            texts[r["role"]].append(r["text"].strip())
        else:
            images[r["role"]].append({"data": region_image(vault, item, r, crops.get(r["id"]))})

    result = create_question(
        vault, subject=subject, category=category,
        difficulty=int(saved.get("difficulty", 5) or 5), note=str(saved.get("page") or ""),
        related_tags=tags, labels=labels, question_text="\n\n".join(texts["question"]),
        answer_text="\n\n".join(texts["answer"]), cause=str(saved.get("cause") or ""),
        question_images=images["question"], answer_images=images["answer"],
    )

    with _LOCK:
        db = connect(vault)
        try:
            _write_cards(db, item_id, {str(card): {**saved, "tags": tags, "labels": labels, "classified": saved.get("classified", False)}})
            db.execute("UPDATE cards SET created_uid=?, created_question_id=? WHERE item_id=? AND card=?",
                       (result["uid"], result["question_id"], item_id, card))
            all_cards = sorted({r["card"] for r in item["regions"] if r["role"] != "ignore"})
            done_cards = {row["card"] for row in db.execute(
                "SELECT card FROM cards WHERE item_id=? AND created_uid IS NOT NULL AND created_uid!=''", (item_id,))}
            if set(all_cards) <= done_cards:
                db.execute("UPDATE items SET status='done', link_uid=?, link_question_id=?, updated_at=? WHERE id=?",
                           (result["uid"], result["question_id"], _now(), item_id))
            db.commit()
        finally:
            db.close()
    _log(vault, "item.commit", {"item_id": item_id, "card": card, "uid": result["uid"],
                                "question_id": result["question_id"], "layout": item["layout"],
                                "regions": _region_summary(regions)})
    return {**result, "item_id": item_id, "card": card}


# ────────────────────────── 数据集 ──────────────────────────

def dataset_stats(vault):
    items = list_items(vault)
    db = connect(vault)
    try:
        done_rows = db.execute("SELECT * FROM items WHERE status='done'").fetchall()
        items += [_row_item(db, r) for r in done_rows if r["id"] not in {i["id"] for i in items}]
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
    return {
        "images": len(items), "done": finished,
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
                              "AND updated_at<=?", (cutoff,)).fetchall()
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


def cleanup_expired(vault):
    """上传时顺手跑一次超期清理（只删原图，很便宜）；任何异常都吞掉，不影响上传。"""
    try:
        return cleanup(vault)
    except Exception:  # noqa: BLE001
        return None


def export_dataset(vault, fmt="omrs_jsonl", include_raw=True):
    """打包 labels + 原图。fmt: omrs_jsonl | yolo。返回 zip bytes。"""
    db = connect(vault)
    try:
        rows = db.execute("SELECT * FROM items WHERE status!='discarded' ORDER BY uploaded_at").fetchall()
        items = [_row_item(db, r) for r in rows]
        rows_by_id = {r["id"]: r for r in rows}
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
                      "source": item["source"], "regions": _region_summary(item["regions"])}
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
