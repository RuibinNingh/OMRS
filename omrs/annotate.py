"""框选标注集（annotate）：独立于收件箱的训练数据标注存储。

只记录「图片 + 题目 / 答案框」，不进 Ledger、不进收件箱、不建题目。数据放在 `错题/.omrs/annotate/`：
- annotate.db          SQLite：images 一张表（框位以 JSON 存在 boxes 列）
- images/<sha256>.<ext> 上传原件，按内容哈希命名 → 重复上传合并

坐标一律归一化 0–1（相对原图宽高），与收件箱导出一致；YOLO 类别号也与收件箱相同
（question=0、answer=1），两份数据集可以直接合并训练。
"""

import datetime
import hashlib
import io
import json
import os
import sqlite3
import threading
import uuid
import zipfile

from .common import omrs_data_dir
from .inbox import image_size

ANNOTATE_DIR = "annotate"
ROLES = ("question", "answer")
STATUSES = ("todo", "done")
CLASS_IDS = {"question": 0, "answer": 1}
MAX_BOXES = 200
MIN_SIDE = 0.002
_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}
_LOCK = threading.RLock()


def annotate_dir(vault):
    path = os.path.join(omrs_data_dir(vault), ANNOTATE_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def images_dir(vault):
    path = os.path.join(annotate_dir(vault), "images")
    os.makedirs(path, exist_ok=True)
    return path


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _new_id():
    return f"AN-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"


def connect(vault):
    db = sqlite3.connect(os.path.join(annotate_dir(vault), "annotate.db"), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, file TEXT, "
        "mime TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, bytes INTEGER NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'todo', boxes TEXT NOT NULL DEFAULT '[]', "
        "uploaded_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    return db


def _image_path(vault, sha256, mime):
    return os.path.join(images_dir(vault), f"{sha256}.{_MIME_EXT.get(mime, 'png')}")


def _loads(text):
    try:
        value = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _row(row):
    return {
        "id": row["id"], "file": row["file"], "width": row["width"], "height": row["height"],
        "bytes": row["bytes"], "status": row["status"], "boxes": _loads(row["boxes"]),
        "uploaded_at": row["uploaded_at"], "updated_at": row["updated_at"],
    }


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("框坐标必须是数字")
    if number != number:  # NaN
        raise ValueError("框坐标必须是数字")
    return number


def clean_boxes(raw):
    """前端框位 → [{role, x, y, w, h}]：角色只收 question / answer，坐标夹到 0–1，过小的框丢弃。"""
    if not isinstance(raw, list):
        raise ValueError("boxes 必须是数组")
    if len(raw) > MAX_BOXES:
        raise ValueError(f"一张图最多 {MAX_BOXES} 个框")
    boxes = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("每个框必须是对象")
        role = entry.get("role")
        if role not in ROLES:
            raise ValueError("框的角色只能是 question 或 answer")
        x, y = _num(entry.get("x")), _num(entry.get("y"))
        # 先按原始坐标算出右下角再夹：伸出图外的部分被裁掉，而不是整体平移
        x0, x1 = (max(0.0, min(1.0, v)) for v in (x, x + _num(entry.get("w"))))
        y0, y1 = (max(0.0, min(1.0, v)) for v in (y, y + _num(entry.get("h"))))
        if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
            continue
        boxes.append({"role": role, "x": round(x0, 6), "y": round(y0, 6),
                      "w": round(x1 - x0, 6), "h": round(y1 - y0, 6)})
    return boxes


# ────────────────────────── 上传 / 查询 / 保存 / 删除 ──────────────────────────

def upload(vault, files):
    """files: [(filename, bytes)] → {images:[新建], duplicates:[{file, id}]}；非图片直接报错，整批不写。"""
    parsed = []
    for filename, data in files:
        if not data:
            continue
        try:
            mime, width, height = image_size(data)
        except ValueError as exc:
            raise ValueError(f"{os.path.basename(filename or 'image')}：{exc}")
        parsed.append((os.path.basename(filename or "image"), data, mime, width, height))
    if not parsed:
        raise ValueError("没有收到图片")
    created, duplicates = [], []
    with _LOCK:
        db = connect(vault)
        try:
            for name, data, mime, width, height in parsed:
                sha = hashlib.sha256(data).hexdigest()
                existing = db.execute("SELECT id FROM images WHERE sha256=?", (sha,)).fetchone()
                if existing:
                    duplicates.append({"file": name, "id": existing["id"]})
                    continue
                path = _image_path(vault, sha, mime)
                if not os.path.exists(path):
                    with open(path, "wb") as handle:
                        handle.write(data)
                image_id, now = _new_id(), _now()
                db.execute(
                    "INSERT INTO images (id, sha256, file, mime, width, height, bytes, status, boxes, uploaded_at, "
                    "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (image_id, sha, name, mime, width, height, len(data), "todo", "[]", now, now))
                created.append(image_id)
            db.commit()
            images = [_row(db.execute("SELECT * FROM images WHERE id=?", (i,)).fetchone()) for i in created]
        finally:
            db.close()
    return {"images": images, "duplicates": duplicates}


def list_images(vault):
    db = connect(vault)
    try:
        rows = db.execute("SELECT * FROM images ORDER BY uploaded_at, rowid").fetchall()
        return [_row(r) for r in rows]
    finally:
        db.close()


def _fetch(db, image_id):
    row = db.execute("SELECT * FROM images WHERE id=?", (str(image_id or ""),)).fetchone()
    if row is None:
        raise ValueError(f"标注图片不存在：{image_id}")
    return row


def raw_file(vault, image_id):
    db = connect(vault)
    try:
        row = _fetch(db, image_id)
    finally:
        db.close()
    path = _image_path(vault, row["sha256"], row["mime"])
    if not os.path.exists(path):
        raise ValueError("原图文件已丢失")
    with open(path, "rb") as handle:
        return row["mime"], handle.read()


def save(vault, image_id, boxes, status=None):
    """整体覆盖一张图的框；status 为 None 时保留原状态。"""
    cleaned = clean_boxes(boxes)
    if status is not None and status not in STATUSES:
        raise ValueError("status 只能是 todo 或 done")
    with _LOCK:
        db = connect(vault)
        try:
            row = _fetch(db, image_id)
            db.execute("UPDATE images SET boxes=?, status=?, updated_at=? WHERE id=?",
                       (json.dumps(cleaned, ensure_ascii=False), status or row["status"], _now(), row["id"]))
            db.commit()
            return _row(_fetch(db, row["id"]))
        finally:
            db.close()


def delete(vault, image_id):
    with _LOCK:
        db = connect(vault)
        try:
            row = _fetch(db, image_id)
            db.execute("DELETE FROM images WHERE id=?", (row["id"],))
            db.commit()
        finally:
            db.close()
        path = _image_path(vault, row["sha256"], row["mime"])
        if os.path.exists(path):
            os.remove(path)
    return {"id": row["id"]}


def stats(vault):
    images = list_images(vault)
    boxes = {role: 0 for role in ROLES}
    for image in images:
        for box in image["boxes"]:
            boxes[box["role"]] = boxes.get(box["role"], 0) + 1
    done = sum(1 for image in images if image["status"] == "done")
    return {"images": len(images), "done": done, "todo": len(images) - done, "boxes": boxes}


# ────────────────────────── 导出 ──────────────────────────

def export(vault, fmt="omrs_jsonl", include_todo=False, fileobj=None):
    """打包已完成（include_todo 时含未完成）的图片与框。fmt: omrs_jsonl | yolo。

    给了 fileobj 就直接写进去（大批量时由服务端写临时文件再流式发送，不在内存里拼整个 zip），返回写入字节数；
    否则返回 zip bytes。原图已是压缩格式，按 ZIP_STORED 存，只压缩文本。
    """
    if fmt not in ("omrs_jsonl", "yolo"):
        raise ValueError("format 只能是 omrs_jsonl 或 yolo")
    db = connect(vault)
    try:
        rows = db.execute("SELECT * FROM images ORDER BY uploaded_at, rowid").fetchall()
    finally:
        db.close()
    buf = fileobj if fileobj is not None else io.BytesIO()
    lines = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            if row["status"] != "done" and not include_todo:
                continue
            path = _image_path(vault, row["sha256"], row["mime"])
            if not os.path.exists(path):
                continue
            name = os.path.basename(path)
            zf.write(path, f"images/{name}", compress_type=zipfile.ZIP_STORED)
            boxes = _loads(row["boxes"])
            lines.append(json.dumps({"id": row["id"], "image": f"images/{name}", "width": row["width"],
                                     "height": row["height"], "status": row["status"], "boxes": boxes},
                                    ensure_ascii=False))
            if fmt == "yolo":
                yolo = [f"{CLASS_IDS[b['role']]} {b['x'] + b['w'] / 2:.6f} {b['y'] + b['h'] / 2:.6f} "
                        f"{b['w']:.6f} {b['h']:.6f}" for b in boxes if b.get("role") in CLASS_IDS]
                zf.writestr(f"labels/{row['sha256']}.txt", "\n".join(yolo) + ("\n" if yolo else ""))
        zf.writestr("labels.jsonl", "\n".join(lines) + ("\n" if lines else ""))
        if fmt == "yolo":
            zf.writestr("classes.txt", "question\nanswer\n")
        zf.writestr("README.txt", "OMRS annotate dataset\n"
                    "labels.jsonl: 每行一张图，boxes 为归一化 [x,y,w,h]（相对原图宽高），role 为 question / answer。\n"
                    "YOLO 类别与收件箱导出相同：0=question，1=answer；两份数据集可直接合并。\n")
    return buf.tell() if fileobj is not None else buf.getvalue()
