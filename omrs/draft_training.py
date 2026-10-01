"""草稿来源图的训练框、登记与引用安全清理。"""
import datetime
import hashlib
import json
import os
import sqlite3
import uuid

from .common import load_config, omrs_data_dir
from . import locking
from . import drafts
from .draft_write import _box


def sync_tasks(db, draft_id, force_crop=False):
    """每份草稿的每张来源图有且仅有一个独立训练任务。"""
    now = drafts._now()
    for row in db.execute("SELECT image_sha FROM draft_images WHERE draft_id=? ORDER BY ord", (draft_id,)):
        db.execute("INSERT OR IGNORE INTO training_tasks(id,draft_id,image_sha,status,error,created_at,updated_at,force_crop) "
                   "VALUES(?,?,?,?,?,?,?,?)",
                   (f"dt_{uuid.uuid4().hex[:16]}", draft_id, row["image_sha"], "pending", None, now, now,
                    int(force_crop)))
    obsolete = db.execute("SELECT t.id FROM training_tasks t LEFT JOIN draft_images di ON "
                          "di.draft_id=t.draft_id AND di.image_sha=t.image_sha "
                          "WHERE t.draft_id=? AND di.image_sha IS NULL AND t.status!='registered'", (draft_id,)).fetchall()
    for row in obsolete:
        db.execute("DELETE FROM training_boxes WHERE task_id=?", (row["id"],))
        db.execute("DELETE FROM training_tasks WHERE id=?", (row["id"],))


def _task_status(db, task_id):
    row = db.execute("SELECT status FROM training_tasks WHERE id=?", (task_id,)).fetchone()
    if row["status"] == "registered":
        return "registered"
    if row["status"] == "error":
        return "error"
    has_boxes = db.execute("SELECT 1 FROM training_boxes WHERE task_id=? LIMIT 1", (task_id,)).fetchone()
    return "ready" if has_boxes else "pending"


def _refresh_task(db, task_id):
    status = _task_status(db, task_id)
    db.execute("UPDATE training_tasks SET status=?,error=CASE WHEN ?='error' THEN error ELSE NULL END,updated_at=? WHERE id=?",
               (status, status, drafts._now(), task_id))


def task_view(db, draft_id):
    rows = db.execute("SELECT t.* FROM training_tasks t LEFT JOIN draft_images di ON "
                      "di.draft_id=t.draft_id AND di.image_sha=t.image_sha "
                      "WHERE t.draft_id=? ORDER BY di.ord,t.created_at", (draft_id,)).fetchall()
    out = []
    for row in rows:
        boxes = []
        for b in db.execute("SELECT * FROM training_boxes WHERE task_id=? ORDER BY ord,id", (row["id"],)):
            boxes.append({"id": b["id"], "task_id": row["id"], "section": b["section"],
                          "box": {k: b[k] for k in ("x", "y", "w", "h")},
                          "box_origin": b["box_origin"], "ai_box": drafts._loads(b["ai_box"], None)})
        out.append({"id": row["id"], "image_sha": row["image_sha"], "status": row["status"],
                    "boxes": boxes, "error": row["error"], "force_crop": bool(row["force_crop"])})
    return out


def sync_block_boxes(db, draft_id):
    """正文图片的框自动复制成独立训练标注；转文字后不删除原标注。"""
    sync_tasks(db, draft_id)
    stale = db.execute("SELECT tb.id,tb.task_id,t.image_sha AS task_sha,b.kind,b.image_sha,b.x FROM training_boxes tb "
                       "JOIN training_tasks t ON t.id=tb.task_id LEFT JOIN blocks b ON b.id=tb.source_block_id "
                       "WHERE t.draft_id=? AND tb.source_block_id IS NOT NULL AND "
                       "t.status!='registered' AND t.manual_override=0",
                       (draft_id,)).fetchall()
    for record in stale:
        if record["kind"] is None or (record["kind"] == "image" and
                                      (record["x"] is None or record["image_sha"] != record["task_sha"])):
            db.execute("DELETE FROM training_boxes WHERE id=?", (record["id"],))
            _refresh_task(db, record["task_id"])
    rows = db.execute("SELECT * FROM blocks WHERE draft_id=? AND kind='image' AND x IS NOT NULL "
                      "AND (box_origin IS NULL OR box_origin!='original') ORDER BY ord", (draft_id,))
    for block in rows:
        task = db.execute("SELECT id,status,manual_override FROM training_tasks WHERE draft_id=? AND image_sha=?",
                          (draft_id, block["image_sha"])).fetchone()
        if not task or task["status"] == "registered" or task["manual_override"]:
            continue
        stable_id = "tb_" + hashlib.sha256((task["id"] + ":" + block["id"]).encode()).hexdigest()[:20]
        db.execute("INSERT INTO training_boxes(id,task_id,section,ord,x,y,w,h,box_origin,ai_box,source_block_id) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "section=excluded.section,ord=excluded.ord,x=excluded.x,y=excluded.y,w=excluded.w,h=excluded.h,"
                   "box_origin=excluded.box_origin,ai_box=excluded.ai_box",
                   (stable_id, task["id"], block["section"], block["ord"],
                    block["x"], block["y"], block["w"], block["h"],
                    block["box_origin"] or "manual", block["ai_box"], block["id"]))
        _refresh_task(db, task["id"])


def prepare_training_boxes(db, draft_id, training_boxes):
    if not isinstance(training_boxes, list):
        raise drafts.DraftError("training_boxes 必须是数组")
    groups = {}
    for index, raw in enumerate(training_boxes):
        if not isinstance(raw, dict) or set(raw) - {"id", "task_id", "section", "box", "box_origin", "ai_box"}:
            raise drafts.DraftError(f"第 {index + 1} 个训练框格式不对")
        task_id = raw.get("task_id")
        task = db.execute("SELECT * FROM training_tasks WHERE id=? AND draft_id=?", (task_id, draft_id)).fetchone()
        if not task:
            raise drafts.DraftError(f"训练任务不存在：{task_id}", 404, "not_found")
        if task["status"] == "registered":
            raise drafts.DraftError("已登记训练图不可再改框", 409, "state_conflict")
        groups.setdefault(task_id, []).append(raw)
    prepared = {}
    for task_id, entries in groups.items():
        empty = [entry for entry in entries if entry.get("box") is None]
        if empty:
            if len(entries) != 1 or set(empty[0]) != {"task_id", "box"}:
                raise drafts.DraftError("空任务标记不能与有效训练框混用")
            prepared[task_id] = []
            continue
        kept = []
        ids = set()
        existing = {r[0] for r in db.execute("SELECT id FROM training_boxes WHERE task_id=?", (task_id,))}
        for index, entry in enumerate(entries):
            section = entry.get("section")
            if section not in drafts.SECTIONS:
                raise drafts.DraftError("训练框 section 不合法")
            box = _box(entry.get("box"))
            if box is None:
                raise drafts.DraftError("训练框缺少坐标")
            origin = entry.get("box_origin")
            if origin not in ("manual", "ai", "ai_edited"):
                raise drafts.DraftError("训练框 box_origin 不合法")
            ai_box = _box(entry.get("ai_box"))
            box_id = entry.get("id") or f"tb_{uuid.uuid4().hex[:20]}"
            if not isinstance(box_id, str) or box_id in ids or (entry.get("id") and box_id not in existing):
                raise drafts.DraftError("训练框 id 不合法")
            ids.add(box_id)
            kept.append((box_id, task_id, section, index, box["x"], box["y"], box["w"], box["h"],
                         origin, json.dumps(ai_box) if ai_box else None, None))
        prepared[task_id] = kept
    return prepared


def replace_training_boxes(db, prepared):
    for task_id, rows in prepared.items():
        db.execute("DELETE FROM training_boxes WHERE task_id=?", (task_id,))
        db.executemany("INSERT INTO training_boxes(id,task_id,section,ord,x,y,w,h,box_origin,ai_box,source_block_id) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.execute("UPDATE training_tasks SET status=?,error=NULL,manual_override=1,updated_at=? WHERE id=?",
                   ("ready" if rows else "pending", drafts._now(), task_id))
    return tuple(prepared)


def set_image_training(vault, draft_id, revision, sha, enabled):
    if not isinstance(enabled, bool):
        raise drafts.DraftError("enabled 必须是布尔值")
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            from .draft_write import _row, _revision, _prepared_before_change
            row = _row(db, draft_id)
            _revision(row, revision)
            if row["status"] == "discarded":
                raise drafts.DraftError("已丢弃草稿不能设置训练", 409, "state_conflict", row["revision"])
            source = db.execute("SELECT i.* FROM draft_images di JOIN images i ON i.sha256=di.image_sha "
                                "WHERE di.draft_id=? AND di.image_sha=?", (draft_id, sha)).fetchone()
            if source is None:
                raise drafts.DraftError("图片不是该草稿来源", 400, "invalid")
            if row["source_channel"] == "mcp" and enabled:
                # MCP 草稿创建时不自动建立训练任务；用户在页面明确打开
                # 训练开关时才补建对应任务。
                sync_tasks(db, draft_id)
            if not enabled and db.execute("SELECT 1 FROM training_tasks WHERE image_sha=? AND status='registered' LIMIT 1",
                                          (sha,)).fetchone():
                raise drafts.DraftError("图片已登记，训练开关只读", 409, "state_conflict", row["revision"])
            changed = bool(source["train"]) != enabled
            if changed:
                related = db.execute("SELECT d.* FROM drafts d JOIN draft_images di ON di.draft_id=d.id "
                                     "WHERE di.image_sha=? AND d.status IN ('cropping','review')", (sha,)).fetchall()
                for related_row in related:
                    _prepared_before_change(vault, db, related_row)
                db.execute("UPDATE images SET train=? WHERE sha256=?", (int(enabled), sha))
                db.execute("UPDATE drafts SET revision=revision+1,updated_at=? WHERE id IN "
                           "(SELECT draft_id FROM draft_images WHERE image_sha=?) AND status!='discarded'",
                           (drafts._now(), sha))
            db.commit()
        finally:
            db.close()
    if changed:
        drafts._log(vault, "image.train", {"draft_id": draft_id, "sha256": sha, "enabled": enabled})
    if enabled:
        # 已入库且已有框时可补登记；失败留在任务内，不撤销开关。
        register_ready(vault, draft_id)
    draft = drafts.get_draft(vault, draft_id)
    image = next(item for item in draft["source_images"] if item["sha256"] == sha)
    return {"draft": draft, "image": image}


def register_ready(vault, draft_id):
    """题目先入库；训练逐图独立登记，失败只标任务并供 done 重试。"""
    from . import inbox
    registered, failed, pending = [], [], []
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            draft = db.execute("SELECT status FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if not draft or draft["status"] != "done":
                return {"status": "off", "registered": [], "failed": [], "pending": []}
            rows = db.execute("SELECT t.*,i.train,i.inbox_item_id FROM training_tasks t "
                              "JOIN draft_images di ON di.draft_id=t.draft_id AND di.image_sha=t.image_sha "
                              "JOIN images i ON i.sha256=t.image_sha WHERE t.draft_id=? ORDER BY t.created_at",
                              (draft_id,)).fetchall()
            for task in rows:
                if not task["train"]:
                    continue
                sha = task["image_sha"]
                if task["status"] == "registered":
                    registered.append(sha)
                    continue
                boxes = task_view(db, draft_id)
                selected = next(t["boxes"] for t in boxes if t["id"] == task["id"])
                if not selected:
                    pending.append(sha)
                    continue
                try:
                    path = drafts.image_path(vault, sha)
                    with open(path, "rb") as file:
                        data = file.read()
                    item_id = inbox.register_chat_training(vault, sha, data, draft_id, selected)
                    db.execute("UPDATE images SET inbox_item_id=? WHERE sha256=?", (item_id, sha))
                    db.execute("UPDATE training_tasks SET status='registered',error=NULL,updated_at=? WHERE id=?",
                               (drafts._now(), task["id"]))
                    registered.append(sha)
                except Exception as exc:
                    message = str(exc)
                    db.execute("UPDATE training_tasks SET status='error',error=?,updated_at=? WHERE id=?",
                               (message, drafts._now(), task["id"]))
                    failed.append({"sha": sha, "error": message})
            db.commit()
        finally:
            db.close()
    status = "off" if not (registered or failed or pending) else (
        "complete" if registered and not failed and not pending else
        "partial" if registered else "pending" if pending and not failed else "partial")
    return {"status": status, "registered": registered, "failed": failed, "pending": pending}


def cleanup(vault):
    """仅清理过期丢弃草稿及没有活动引用的原图。"""
    days = load_config(vault).get("draft_discard_keep_days", 7)
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat(timespec="seconds")
    cleaned = {"drafts": 0, "images": 0, "crops": 0}
    retained = {"images": 0}
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            rows = db.execute("SELECT id FROM drafts WHERE status='discarded' AND updated_at<=?", (cutoff,)).fetchall()
            for row in rows:
                draft_id = row["id"]
                if not db.execute("SELECT 1 FROM draft_images WHERE draft_id=?", (draft_id,)).fetchone():
                    continue
                for source in db.execute("SELECT image_sha FROM draft_images WHERE draft_id=?", (draft_id,)):
                    db.execute("INSERT OR IGNORE INTO cleanup_candidates(image_sha,marked_at) VALUES(?,?)",
                               (source["image_sha"], drafts._now()))
                task_ids = [r[0] for r in db.execute("SELECT id FROM training_tasks WHERE draft_id=?", (draft_id,))]
                for task_id in task_ids:
                    db.execute("DELETE FROM training_boxes WHERE task_id=?", (task_id,))
                db.execute("DELETE FROM training_tasks WHERE draft_id=?", (draft_id,))
                db.execute("DELETE FROM draft_images WHERE draft_id=?", (draft_id,))
                db.execute("DELETE FROM blocks WHERE draft_id=?", (draft_id,))
                db.execute("UPDATE drafts SET cleaned_at=? WHERE id=?", (drafts._now(), draft_id))
                cleaned["drafts"] += 1
            candidates = db.execute("SELECT cc.image_sha,i.mime,i.inbox_item_id FROM cleanup_candidates cc "
                                    "LEFT JOIN images i ON i.sha256=cc.image_sha").fetchall()
            agent_db = os.path.join(omrs_data_dir(vault), "agent.db")
            inbox_db = os.path.join(omrs_data_dir(vault), "inbox", "inbox.db")
            training_refs = set()
            training_lookup_failed = False
            if os.path.isfile(inbox_db):
                from . import inbox
                with inbox._LOCK:
                    try:
                        training = sqlite3.connect(f"file:{inbox_db}?mode=ro", uri=True)
                        try:
                            exists = training.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                                      "AND name='chat_training_boxes'").fetchone()
                            if exists:
                                training_refs = {r[0] for r in training.execute(
                                    "SELECT DISTINCT image_sha FROM chat_training_boxes")}
                        finally:
                            training.close()
                    except sqlite3.Error:
                        training_lookup_failed = True
            for image in candidates:
                sha = image["image_sha"]
                if image["mime"] is None:
                    continue
                if db.execute("SELECT 1 FROM draft_images WHERE image_sha=? LIMIT 1", (sha,)).fetchone():
                    retained["images"] += 1
                    continue
                if image["inbox_item_id"] or training_lookup_failed or sha in training_refs:
                    retained["images"] += 1
                    continue
                live_chat = False
                if os.path.isfile(agent_db):
                    agent = sqlite3.connect(f"file:{agent_db}?mode=ro", uri=True)
                    try:
                        convs = [r[0] for r in db.execute(
                            "SELECT conversation_id FROM conv_images WHERE sha256=?", (sha,))]
                        live_chat = any(agent.execute(
                            "SELECT 1 FROM conversations WHERE id=? AND deleted=0", (conv,)).fetchone()
                            for conv in convs)
                    except sqlite3.Error:
                        live_chat = True
                    finally:
                        agent.close()
                else:
                    # 没有对话库时，现存编号也代表潜在引用，宁可保留。
                    live_chat = bool(db.execute("SELECT 1 FROM conv_images WHERE sha256=? LIMIT 1", (sha,)).fetchone())
                if live_chat:
                    retained["images"] += 1
                    continue
                db.execute("DELETE FROM conv_images WHERE sha256=?", (sha,))
                db.execute("DELETE FROM images WHERE sha256=?", (sha,))
            # 先提交引用释放；中断后候选仍在，可下次继续删文件。
            db.commit()
            for image in db.execute("SELECT image_sha FROM cleanup_candidates WHERE image_sha NOT IN "
                                    "(SELECT sha256 FROM images)").fetchall():
                sha = image["image_sha"]
                removed = False
                for ext in set(drafts._MIME_EXT.values()):
                    path = os.path.join(drafts.images_dir(vault), f"{sha}.{ext}")
                    if os.path.isfile(path):
                        os.remove(path)
                        removed = True
                cleaned["images"] += int(removed)
                db.execute("DELETE FROM cleanup_candidates WHERE image_sha=?", (sha,))
            db.commit()
        finally:
            db.close()
    if any(cleaned.values()):
        drafts._log(vault, "draft.cleanup", {"cleaned": cleaned, "retained": retained})
    return {"cleaned": cleaned, "retained": retained}
