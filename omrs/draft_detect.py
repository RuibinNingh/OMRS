"""草稿来源图的异步自动框选；检测调用不占用全局写锁。"""
import base64
import io
import json
import threading
import uuid

from . import ai_assist, draft_jobs, drafts, inbox, locking
from .common import load_config
from .draft_write import _box, _prepared_before_change, _revision, _row


def _result(sha, status, reason_code=None, reason="", candidates=None, blocks=None, task_id=None):
    return {"sha": sha, "status": status, "reason_code": reason_code, "reason": reason,
            "candidates": candidates or [], "applied_blocks": blocks or [], "training_task_id": task_id}


def _source(db, draft_id, sha):
    return db.execute("SELECT i.* FROM draft_images di JOIN images i ON i.sha256=di.image_sha "
                      "WHERE di.draft_id=? AND di.image_sha=?", (draft_id, sha)).fetchone()


def _guard(db, row, sha):
    """返回不可自动套框的原因；调用前和回写前都须检查。"""
    if row["status"] == "discarded":
        return "state_conflict", "草稿已丢弃，检测结果未应用"
    if not _source(db, row["id"], sha):
        return "source_removed", "来源图已移除，检测结果未应用"
    if not row["sources_complete"]:
        return "unknown_sources", "来源图关联尚未确认，请手动框选"
    shared = db.execute("SELECT COUNT(DISTINCT d.id) FROM draft_images di JOIN drafts d ON d.id=di.draft_id "
                        "WHERE di.image_sha=? AND d.status!='discarded'", (sha,)).fetchone()[0]
    if shared > 1:
        return "shared_image", "这张图被多份草稿共用，请手动框选"
    task = db.execute("SELECT * FROM training_tasks WHERE draft_id=? AND image_sha=?",
                      (row["id"], sha)).fetchone()
    if task and task["status"] == "registered":
        return "registered", "这张图的训练框已登记，不能自动覆盖"
    if task and task["manual_override"]:
        return "manual_box", "这张图已有人工训练框，请手动处理"
    blocks = db.execute("SELECT * FROM blocks WHERE draft_id=? AND kind='image' AND image_sha=?",
                        (row["id"], sha)).fetchall()
    if any(b["x"] is not None and b["box_origin"] in ("manual", "ai_edited") for b in blocks):
        return "manual_box", "这张图已有人工正文框，请手动处理"
    if row["status"] == "done" and blocks:
        return "state_conflict", "已入库草稿的正文不可自动改框"
    if not any(b["x"] is None for b in blocks) and not (task and task["force_crop"]):
        return "no_targets", "没有待自动框选的图片区块或强制训练任务"
    return None, ""


def _snapshot(db, row, sha):
    source = _source(db, row["id"], sha)
    task = db.execute("SELECT id,force_crop FROM training_tasks WHERE draft_id=? AND image_sha=?",
                      (row["id"], sha)).fetchone()
    blocks = db.execute("SELECT id,section,x,y,w,h,box_origin FROM blocks "
                        "WHERE draft_id=? AND kind='image' AND image_sha=? ORDER BY ord,id",
                        (row["id"], sha)).fetchall()
    return {"sha": sha, "width": source["width"], "height": source["height"], "mime": source["mime"],
            "task_id": task["id"] if task else None, "force_crop": bool(task and task["force_crop"]),
            "blocks": [dict(b) for b in blocks]}


def _same_snapshot(db, draft_id, snap):
    current = db.execute("SELECT id,section,x,y,w,h,box_origin FROM blocks "
                         "WHERE draft_id=? AND kind='image' AND image_sha=? ORDER BY ord,id",
                         (draft_id, snap["sha"])).fetchall()
    return [dict(b) for b in current] == snap["blocks"]


def _data_url(mime, data):
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _detect_candidates(vault, snap):
    provider = inbox.detect_provider(vault)
    plan = inbox.slice_plan(snap["width"], snap["height"])
    path = drafts.image_path(vault, snap["sha"])
    strips = []
    if len(plan) > 1:
        try:
            from PIL import Image
            with Image.open(path) as image:
                for y0, y1 in plan:
                    buffer = io.BytesIO()
                    image.crop((0, int(y0 * image.height), image.width, int(y1 * image.height))).convert(
                        "RGB").save(buffer, format="JPEG", quality=85)
                    strips.append((y0, y1, _data_url("image/jpeg", buffer.getvalue())))
        except ImportError:
            pass  # Pillow 可选；与收件箱一致，缺失时整图交给提供方。
    if not strips:
        with open(path, "rb") as file:
            strips = [(0.0, 1.0, _data_url(snap["mime"], file.read()))]
    outputs = []
    for y0, y1, image in strips:
        if provider == "local_http":
            boxes = ai_assist.detect_regions_local(load_config(vault).get("inbox_local_detect_url", ""), image,
                                                    layout="other", image_width=snap["width"],
                                                    image_height=round(snap["height"] * (y1 - y0)))
        else:
            boxes = ai_assist.detect_regions(vault, image, layout="other")
        outputs.append({"y0": y0, "y1": y1, "boxes": boxes})
    return _clean_candidates(inbox.merge_strip_boxes(outputs))


def _clean_candidates(boxes):
    cleaned = []
    for candidate in boxes:
        if candidate.get("role") not in ("question", "answer"):
            continue
        box = _box({key: candidate[key] for key in ("x", "y", "w", "h")})
        cleaned.append({"role": candidate["role"], "card": int(candidate.get("card", 1) or 1),
                        **box, "conf": float(candidate.get("conf", 0.5))})
    return cleaned


def _mapping(snap, candidates):
    """只接受一节一框的无歧义映射；其余候选留给人工。"""
    if not candidates:
        return None, "模型没有返回可用框"
    if any(c["card"] != 1 for c in candidates) or len({c["role"] for c in candidates}) != len(candidates):
        return None, "模型返回多题或同一节多个候选框，请人工选择"
    pending = [b for b in snap["blocks"] if b["x"] is None]
    if pending:
        roles = ["question" if b["section"] == "题目" else "answer" for b in pending]
        all_roles = ["question" if b["section"] == "题目" else "answer" for b in snap["blocks"]]
        if len(set(all_roles)) != len(all_roles) or set(roles) != {c["role"] for c in candidates}:
            return None, "候选框与待框选正文块数量或题目/答案分区不匹配"
        return {b["id"]: next(c for c in candidates if c["role"] == role)
                for b, role in zip(pending, roles)}, ""
    if snap["force_crop"]:
        return {"training": candidates}, ""
    return None, "没有待框选目标"


def _active_duplicate(db, draft_id, revision, shas):
    for row in db.execute("SELECT * FROM draft_jobs WHERE draft_id=? AND type='detect' AND revision=? "
                          "AND status IN ('queued','running')", (draft_id, revision)):
        row = draft_jobs._interrupt_orphan(db, row)
        if row["status"] not in ("queued", "running"):
            continue
        existing = {s["sha"] for s in drafts._loads(row["snapshot_json"], [])}
        if existing.intersection(shas):
            if shas <= existing:
                return draft_jobs._job_row(row)
            raise drafts.DraftError("部分来源图已有进行中的检测，请等待后重试", 409,
                                    "operation_pending", revision)
    for row in db.execute("SELECT * FROM draft_jobs WHERE draft_id=? AND type='extract' AND revision=? "
                          "AND status IN ('queued','running')", (draft_id, revision)):
        row = draft_jobs._interrupt_orphan(db, row)
        if row["status"] in ("queued", "running") and shas.intersection(
                snap["image_sha"] for snap in drafts._loads(row["snapshot_json"], [])):
            raise drafts.DraftError("这张图已有进行中的文字提取，请等待后重试", 409,
                                    "operation_pending", revision)
    return None


def start_detect(vault, draft_id, revision, sha=None):
    if sha is not None and (not isinstance(sha, str) or len(sha) != 64 or
                            any(ch not in "0123456789abcdef" for ch in sha)):
        raise drafts.DraftError("sha 必须是来源图的 SHA256")
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            _revision(row, revision)
            if row["status"] == "discarded":
                raise drafts.DraftError("已丢弃草稿不能自动框选", 409, "state_conflict", revision)
            drafts._source_view(vault, db, row, drafts._draft_blocks(db, draft_id))
            row = _row(db, draft_id)
            shas = [r[0] for r in db.execute("SELECT image_sha FROM draft_images WHERE draft_id=? ORDER BY ord",
                                             (draft_id,))]
            if sha is not None:
                if sha not in shas:
                    raise drafts.DraftError("图片不是该草稿来源")
                shas = [sha]
            duplicate = _active_duplicate(db, draft_id, revision, set(shas))
            if duplicate:
                return duplicate
            if sha is not None and not db.execute("SELECT 1 FROM blocks WHERE draft_id=? AND kind='image'",
                                                 (draft_id,)).fetchone():
                db.execute("UPDATE training_tasks SET force_crop=1 WHERE draft_id=? AND image_sha=? "
                           "AND status!='registered'", (draft_id, sha))
            snapshots = [_snapshot(db, row, item_sha) for item_sha in shas]
            job_id = f"dj_{uuid.uuid4().hex[:20]}"
            now = drafts._now()
            status = "queued" if snapshots else "done"
            db.execute("INSERT INTO draft_jobs(id,draft_id,type,status,revision,snapshot_json,processed,total,"
                       "result_json,errors_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (job_id, draft_id, "detect", status, revision, json.dumps(snapshots, ensure_ascii=False),
                        0, len(snapshots), "[]", "[]", now, now))
            if snapshots:
                with draft_jobs._ACTIVE_LOCK:
                    draft_jobs._ACTIVE.add(job_id)
            db.commit()
        except Exception:
            with draft_jobs._ACTIVE_LOCK:
                draft_jobs._ACTIVE.discard(locals().get("job_id"))
            raise
        finally:
            db.close()
    if snapshots:
        thread = threading.Thread(target=_run_detect, args=(vault, job_id, draft_id, revision, snapshots), daemon=True)
        try:
            thread.start()
        except Exception:
            with draft_jobs._ACTIVE_LOCK:
                draft_jobs._ACTIVE.discard(job_id)
            draft_jobs._update(vault, job_id, status="interrupted")
            raise
    return draft_jobs.get_job(vault, job_id)


def _run_detect(vault, job_id, draft_id, revision, snapshots):
    proposals, errors = [], []
    try:
        draft_jobs._update(vault, job_id, status="running")
        for snap in snapshots:
            with locking.write_lock(), drafts._LOCK:
                db = drafts.connect(vault)
                try:
                    row = _row(db, draft_id)
                    if row["revision"] != revision:
                        code, reason = "revision_conflict", "草稿在检测前已变化，请重新检测"
                    else:
                        code, reason = _guard(db, row, snap["sha"])
                finally:
                    db.close()
            if code:
                proposals.append(_result(snap["sha"], "conflict" if code == "revision_conflict" else "skipped",
                                         code, reason, task_id=snap["task_id"]))
            else:
                try:
                    candidates = _detect_candidates(vault, snap)
                    mapping, reason = _mapping(snap, candidates)
                    proposals.append(_result(snap["sha"], "applied" if mapping else "suggested",
                                             None if mapping else "ambiguous", reason,
                                             candidates, task_id=snap["task_id"]))
                except Exception as exc:
                    errors.append({"sha": snap["sha"], "error": str(exc)})
                    proposals.append(_result(snap["sha"], "skipped", "provider_error",
                                             str(exc), task_id=snap["task_id"]))
            draft_jobs._update(vault, job_id, processed=len(proposals), errors=errors)
        applied, conflicts = False, any(item["status"] == "conflict" for item in proposals)
        with locking.write_lock(), drafts._LOCK:
            db = drafts.connect(vault)
            try:
                row = _row(db, draft_id)
                if row["revision"] != revision:
                    conflicts = True
                    for item in proposals:
                        if item["status"] == "applied":
                            item.update(status="conflict", reason_code="revision_conflict",
                                        reason="草稿在检测期间已变化，请重新检测")
                else:
                    for snap, item in zip(snapshots, proposals):
                        if item["status"] != "applied":
                            continue
                        code, reason = _guard(db, row, snap["sha"])
                        if code or not _same_snapshot(db, draft_id, snap):
                            item.update(status="conflict", reason_code=code or "snapshot_conflict",
                                        reason=reason or "来源图或正文块在检测期间已变化")
                            conflicts = True
                            continue
                        mapping, _ = _mapping(snap, item["candidates"])
                        if mapping is None:
                            item.update(status="suggested", reason_code="ambiguous", reason="候选映射已失效")
                            continue
                        if not applied and row["status"] != "done":
                            try:
                                _prepared_before_change(vault, db, row)
                            except drafts.DraftError as exc:
                                item.update(status="conflict", reason_code="state_conflict", reason=str(exc))
                                conflicts = True
                                continue
                        if "training" in mapping:
                            db.execute("DELETE FROM training_boxes WHERE task_id=?", (snap["task_id"],))
                            for index, candidate in enumerate(mapping["training"]):
                                rect = _box({key: candidate[key] for key in ("x", "y", "w", "h")})
                                box_id = f"tb_{uuid.uuid5(uuid.NAMESPACE_URL, snap['task_id'] + ':' + str(index)).hex[:20]}"
                                db.execute("INSERT INTO training_boxes(id,task_id,section,ord,x,y,w,h,box_origin,ai_box,source_block_id) "
                                           "VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                                           (box_id, snap["task_id"], "题目" if candidate["role"] == "question" else "答案",
                                            index, rect["x"], rect["y"], rect["w"], rect["h"], "ai",
                                            json.dumps(rect)))
                            db.execute("UPDATE training_tasks SET status='ready',error=NULL,updated_at=? WHERE id=?",
                                       (drafts._now(), snap["task_id"]))
                        else:
                            for block_id, candidate in mapping.items():
                                rect = _box({key: candidate[key] for key in ("x", "y", "w", "h")})
                                db.execute("UPDATE blocks SET x=?,y=?,w=?,h=?,box_origin='ai',ai_box=? "
                                           "WHERE id=? AND draft_id=?", (*rect.values(), json.dumps(rect), block_id, draft_id))
                            from .draft_training import sync_block_boxes
                            sync_block_boxes(db, draft_id)
                            item["applied_blocks"] = list(mapping)
                        applied = True
                    if applied:
                        missing = db.execute("SELECT 1 FROM blocks WHERE draft_id=? AND kind='image' AND x IS NULL LIMIT 1",
                                             (draft_id,)).fetchone()
                        db.execute("UPDATE drafts SET revision=revision+1,updated_at=?,status=CASE WHEN status='done' "
                                   "THEN 'done' ELSE ? END WHERE id=?",
                                   (drafts._now(), "cropping" if missing else "review", draft_id))
                job_status = "conflict" if conflicts else "error" if errors else "done"
                done_training = applied and row["status"] == "done"
                db.execute("UPDATE draft_jobs SET status=?,processed=?,result_json=?,errors_json=?,updated_at=? WHERE id=?",
                           ("running" if done_training else job_status, len(proposals), json.dumps(proposals, ensure_ascii=False),
                            json.dumps(errors, ensure_ascii=False), drafts._now(), job_id))
                db.commit()
            finally:
                db.close()
        if done_training:
            from .draft_training import register_ready
            training = register_ready(vault, draft_id)
            errors.extend({"sha": item["sha"], "error": item["error"]} for item in training["failed"])
            if training["failed"] and job_status != "conflict":
                job_status = "error"
            draft_jobs._update(vault, job_id, status=job_status, errors=errors)
    except Exception as exc:
        try:
            draft_jobs._update(vault, job_id, status="error", errors=errors + [{"error": str(exc)}])
        except Exception:
            pass
    finally:
        with draft_jobs._ACTIVE_LOCK:
            draft_jobs._ACTIVE.discard(job_id)
