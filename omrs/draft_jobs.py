"""草稿异步提取作业；模型调用不持全局写锁。"""
from .vault_lifecycle import storage, open_sqlite, lease, task, generation
import base64
import io
import json
import os
import threading
import uuid

from . import drafts, locking
from . import ai_assist
from .draft_write import _box, _revision, _row, _prepared_before_change

_ACTIVE = set()
_ACTIVE_LOCK = threading.Lock()


def _active(job_id):
    with _ACTIVE_LOCK:
        return job_id in _ACTIVE


def _job_row(row):
    return {"id": row["id"], "draft_id": row["draft_id"], "type": row["type"],
            "status": row["status"], "revision": row["revision"], "processed": row["processed"],
            "total": row["total"], "result": drafts._loads(row["result_json"], []),
            "errors": drafts._loads(row["errors_json"], []),
            "done": row["status"] in ("done", "error", "conflict", "interrupted")}


def _interrupt_orphan(db, row):
    if row["status"] in ("queued", "running") and not _active(row["id"]):
        db.execute("UPDATE draft_jobs SET status='interrupted',updated_at=? WHERE id=?",
                   (drafts._now(), row["id"]))
        db.commit()
        row = db.execute("SELECT * FROM draft_jobs WHERE id=?", (row["id"],)).fetchone()
    return row


def jobs_for_draft(db, draft_id):
    rows = db.execute("SELECT * FROM draft_jobs WHERE draft_id=? ORDER BY created_at DESC,rowid DESC LIMIT 10",
                      (draft_id,)).fetchall()
    return [_job_row(row) for row in rows]


@storage
def recover_orphan_jobs(vault, draft_id):
    with lease(vault), locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            rows = db.execute("SELECT * FROM draft_jobs WHERE draft_id=? AND status IN ('queued','running')",
                              (draft_id,)).fetchall()
            for row in rows:
                _interrupt_orphan(db, row)
        finally:
            db.close()


@storage
def get_job(vault, job_id):
    with lease(vault), locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = db.execute("SELECT * FROM draft_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise drafts.DraftError(f"没有这个草稿任务：{job_id}", 404, "not_found")
            return _job_row(_interrupt_orphan(db, row))
        finally:
            db.close()


@storage
def _update(vault, job_id, **fields):
    with lease(vault), locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            if "result" in fields:
                fields["result_json"] = json.dumps(fields.pop("result"), ensure_ascii=False)
            if "errors" in fields:
                fields["errors_json"] = json.dumps(fields.pop("errors"), ensure_ascii=False)
            fields["updated_at"] = drafts._now()
            changes = ",".join(f"{name}=?" for name in fields)
            db.execute(f"UPDATE draft_jobs SET {changes} WHERE id=?", (*fields.values(), job_id))
            db.commit()
        finally:
            db.close()


@storage
def start_extract(vault, draft_id, revision, block_ids, crops=None):
    if not isinstance(block_ids, list) or not block_ids or any(not isinstance(v, str) for v in block_ids):
        raise drafts.DraftError("block_ids 必须是非空块 id 数组")
    if len(set(block_ids)) != len(block_ids):
        raise drafts.DraftError("block_ids 不能重复")
    if crops is None:
        crops = {}
    if not isinstance(crops, dict) or set(crops) - set(block_ids):
        raise drafts.DraftError("crops 只能包含本次目标块")
    for block_id, url in crops.items():
        try:
            drafts._decode_image_data_url(url)
        except ValueError as exc:
            raise drafts.DraftError(f"块 {block_id} 的裁图不合法：{exc}") from exc
    with lease(vault), locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            _revision(row, revision)
            if row["status"] not in ("cropping", "review"):
                raise drafts.DraftError("只有活动草稿可以提取正文", 409, "state_conflict", row["revision"])
            blocks = {b["id"]: b for b in drafts._draft_blocks(db, draft_id)}
            snapshot = []
            for block_id in block_ids:
                block = blocks.get(block_id)
                if not block or block["kind"] != "image" or not block["box"]:
                    raise drafts.DraftError(f"块 {block_id} 不是已框选图片")
                snapshot.append({"id": block_id, "section": block["section"],
                                 "image_sha": block["image_sha"], "box": _box(block["box"])})
            target_shas = {item["image_sha"] for item in snapshot}
            for active in db.execute("SELECT * FROM draft_jobs WHERE draft_id=? AND revision=? "
                                     "AND type IN ('detect','extract') AND status IN ('queued','running')",
                                     (draft_id, revision)):
                active = _interrupt_orphan(db, active)
                if active["status"] not in ("queued", "running"):
                    continue
                prior = drafts._loads(active["snapshot_json"], [])
                prior_shas = {item.get("sha") or item.get("image_sha") for item in prior}
                if target_shas.intersection(prior_shas):
                    raise drafts.DraftError("这张图已有进行中的草稿任务，请等待后重试", 409,
                                            "operation_pending", revision)
            _prepared_before_change(vault, db, row)
            from .draft_training import sync_block_boxes
            sync_block_boxes(db, draft_id)
            job_id = f"dj_{uuid.uuid4().hex[:20]}"
            now = drafts._now()
            db.execute("INSERT INTO draft_jobs(id,draft_id,type,status,revision,snapshot_json,processed,total,"
                       "result_json,errors_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (job_id, draft_id, "extract", "queued", revision,
                        json.dumps(snapshot, ensure_ascii=False), 0, len(snapshot), "[]", "[]", now, now))
            with _ACTIVE_LOCK:
                _ACTIVE.add(job_id)
            db.commit()
        except Exception:
            with _ACTIVE_LOCK:
                _ACTIVE.discard(locals().get("job_id"))
            raise
        finally:
            db.close()
    thread = threading.Thread(target=_run_extract, args=(vault, job_id, revision, snapshot, crops, generation(vault)), daemon=True)
    try:
        thread.start()
    except Exception:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(job_id)
        _update(vault, job_id, status="interrupted")
        raise
    return get_job(vault, job_id)


@storage
def _image_for(vault, block, supplied):
    if supplied:
        return supplied
    box = block["box"]
    if all(abs(box[key] - value) < 1e-8 for key, value in {"x": 0, "y": 0, "w": 1, "h": 1}.items()):
        return drafts.image_data_url(vault, block["image_sha"])
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError(f"块 {block['id']} 需要页面裁图；请先在草稿区通过") from exc
    with Image.open(drafts.image_path(vault, block["image_sha"])) as image:
        x, y, w, h = (box[key] for key in ("x", "y", "w", "h"))
        crop = image.crop((round(x * image.width), round(y * image.height),
                           round((x + w) * image.width), round((y + h) * image.height)))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
    raw = buffer.getvalue()
    if len(raw) > drafts._MAX_IMAGE_BYTES:
        raise ValueError(f"块 {block['id']} 的裁图超过 8MB")
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _run_extract(vault, job_id, revision, snapshot, crops, expected_generation=None):
    with task(vault, expected_generation):
        return _run_extract_current(vault, job_id, revision, snapshot, crops)


def _run_extract_current(vault, job_id, revision, snapshot, crops):
    result, errors, successful = [], [], []
    try:
        _update(vault, job_id, status="running")
        for block in snapshot:
            try:
                image = _image_for(vault, block, crops.get(block["id"]))
                role = "question" if block["section"] == "题目" else "answer"
                extracted = ai_assist.extract_region(vault, image, role=role, judge=False)
                text = (extracted.get("text") or "").strip() if isinstance(extracted, dict) else ""
                if not text:
                    raise ValueError("模型没有返回可用文字")
                successful.append((block, text))
                result.append({"block_id": block["id"], "status": "done", "kind": "text"})
            except Exception as exc:
                errors.append({"block_id": block["id"], "error": str(exc)})
            _update(vault, job_id, processed=len(result) + len(errors), result=result, errors=errors)
        with lease(vault), locking.write_lock(), drafts._LOCK:
            db = drafts.connect(vault)
            try:
                row = _row(db, _job_draft_id(db, job_id))
                blocks = {b["id"]: b for b in drafts._draft_blocks(db, row["id"])}
                conflict = row["revision"] != revision or row["status"] not in ("cropping", "review") or any(
                    blocks.get(block["id"]) is None or blocks[block["id"]]["kind"] != "image" or
                    blocks[block["id"]]["image_sha"] != block["image_sha"] or
                    blocks[block["id"]]["box"] != block["box"] for block in snapshot)
                if conflict:
                    db.execute("UPDATE draft_jobs SET status='conflict',result_json=?,errors_json=?,updated_at=? WHERE id=?",
                               (json.dumps(result, ensure_ascii=False), json.dumps(errors, ensure_ascii=False),
                                drafts._now(), job_id))
                else:
                    from .draft_training import sync_block_boxes
                    sync_block_boxes(db, row["id"])
                    for block, text in successful:
                        db.execute("UPDATE blocks SET kind='text',text=?,image_sha=NULL,x=NULL,y=NULL,w=NULL,h=NULL,"
                                   "box_origin=NULL,ai_box=NULL WHERE id=? AND draft_id=?",
                                   (text, block["id"], row["id"]))
                    if successful:
                        missing = db.execute("SELECT 1 FROM blocks WHERE draft_id=? AND kind='image' AND x IS NULL LIMIT 1",
                                             (row["id"],)).fetchone()
                        db.execute("UPDATE drafts SET status=?,revision=revision+1,updated_at=? WHERE id=?",
                                   ("cropping" if missing else "review", drafts._now(), row["id"]))
                    db.execute("UPDATE draft_jobs SET status=?,result_json=?,errors_json=?,updated_at=? WHERE id=?",
                               ("error" if errors else "done", json.dumps(result, ensure_ascii=False),
                                json.dumps(errors, ensure_ascii=False), drafts._now(), job_id))
                db.commit()
            finally:
                db.close()
    except Exception as exc:
        try:
            _update(vault, job_id, status="error", errors=errors + [{"error": str(exc)}])
        except Exception:
            pass
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(job_id)


def _job_draft_id(db, job_id):
    return db.execute("SELECT draft_id FROM draft_jobs WHERE id=?", (job_id,)).fetchone()[0]
