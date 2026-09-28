"""草稿内容写入与一次性入库；所有公开入口经 drafts.py 转发。"""
import json
import hashlib
import math
import os
import sqlite3
import uuid

from . import locking
from . import drafts
from . import creation
from .common import questions_root
from .ledger import read_commits, reserve_operation_id
from .projections import rebuild_projection
from .path_safety import safe_question_directory

_FIELDS = {"subject", "category", "difficulty", "knowledge_points", "labels", "cause", "note"}
_BOX_KEYS = {"x", "y", "w", "h"}


def _row(db, draft_id):
    row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        raise drafts.DraftError(f"没有这份草稿：{draft_id}", 404, "not_found")
    return row


def _revision(row, revision):
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise drafts.DraftError("revision 必须是正整数")
    if row["revision"] != revision:
        raise drafts.DraftError("草稿已变化，请重新读取", 409, "revision_conflict", row["revision"])


def _editable(row):
    if row["status"] not in ("cropping", "review"):
        raise drafts.DraftError("这份草稿已结束，不能修改正文", 409, "state_conflict", row["revision"])


def _box(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _BOX_KEYS:
        raise drafts.DraftError("图片框坐标不完整")
    if any(isinstance(value[k], bool) or not isinstance(value[k], (int, float)) or
           not math.isfinite(value[k]) for k in _BOX_KEYS):
        raise drafts.DraftError("图片框坐标必须是有限数值")
    x, y, w, h = (value[k] for k in ("x", "y", "w", "h"))
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x + w <= 1 + 1e-9 and y + h <= 1 + 1e-9):
        raise drafts.DraftError("图片框坐标超出范围")
    return {k: float(value[k]) for k in _BOX_KEYS}


def _fields(row, supplied):
    if not isinstance(supplied, dict) or set(supplied) - _FIELDS:
        raise drafts.DraftError("fields 包含不允许的字段")
    values = {key: row[key] for key in ("subject", "category", "difficulty", "cause", "note")}
    values["knowledge_points"] = drafts._loads(row["knowledge_points"], [])
    values["labels"] = drafts._loads(row["labels"], [])
    values.update(supplied)
    for key in ("subject", "category"):
        if not isinstance(values[key], str) or not values[key].strip():
            raise drafts.DraftError(f"{key} 不能为空")
        values[key] = values[key].strip()
    if isinstance(values["difficulty"], bool) or not isinstance(values["difficulty"], int) or not 1 <= values["difficulty"] <= 10:
        raise drafts.DraftError("difficulty 必须是 1 到 10 的整数")
    for key in ("knowledge_points", "labels"):
        if not isinstance(values[key], list) or any(not isinstance(v, str) for v in values[key]):
            raise drafts.DraftError(f"{key} 必须是字符串数组")
        values[key] = [v.strip() for v in values[key] if v.strip()]
    if len(values["knowledge_points"]) > 8:
        raise drafts.DraftError("知识点最多 8 个")
    for key in ("cause", "note"):
        if not isinstance(values[key], str):
            raise drafts.DraftError(f"{key} 必须是文字")
        values[key] = values[key].strip()
    return values


def _blocks(db, row, supplied, source_shas):
    if not isinstance(supplied, list) or not supplied:
        raise drafts.DraftError("blocks 必须是非空数组")
    existing = {b["id"]: b for b in drafts._draft_blocks(db, row["id"])}
    used = set()
    prepared = []
    for index, raw in enumerate(supplied):
        if not isinstance(raw, dict) or set(raw) - {"id", "section", "kind", "text", "image_sha", "box", "box_origin", "ai_box", "note", "ord"}:
            raise drafts.DraftError(f"第 {index + 1} 块格式不对")
        block_id = raw.get("id") or f"blk_{uuid.uuid4().hex[:10]}"
        if not isinstance(block_id, str) or block_id in used or (raw.get("id") and block_id not in existing):
            raise drafts.DraftError(f"第 {index + 1} 块 id 不合法")
        used.add(block_id)
        section, kind = raw.get("section"), raw.get("kind")
        if section not in drafts.SECTIONS or kind not in drafts.KINDS:
            raise drafts.DraftError(f"第 {index + 1} 块 section 或 kind 不合法")
        note = raw.get("note") or ""
        if not isinstance(note, str):
            raise drafts.DraftError(f"第 {index + 1} 块 note 必须是文字")
        if kind == "text":
            value = raw.get("text")
            if not isinstance(value, str) or not value.strip():
                raise drafts.DraftError(f"第 {index + 1} 块没有有效文字")
            prepared.append((block_id, row["id"], section, index, kind, value.strip(), None,
                             None, None, None, None, None, None, note.strip()))
        else:
            sha = raw.get("image_sha")
            if not isinstance(sha, str) or sha not in source_shas:
                raise drafts.DraftError(f"第 {index + 1} 块图片不在草稿来源中")
            box = _box(raw.get("box"))
            origin = raw.get("box_origin")
            if box and origin not in ("manual", "ai", "ai_edited"):
                raise drafts.DraftError(f"第 {index + 1} 块 box_origin 不合法")
            ai_box = _box(raw.get("ai_box"))
            coords = tuple(box[k] for k in ("x", "y", "w", "h")) if box else (None, None, None, None)
            prepared.append((block_id, row["id"], section, index, kind, None, sha,
                             *coords,
                             origin if box else None, json.dumps(ai_box) if ai_box else None, note.strip()))
    if not any(b[2] == "题目" for b in prepared):
        raise drafts.DraftError("草稿至少要有一个题目块")
    return prepared


def _prepared_before_change(vault, db, row):
    op = db.execute("SELECT * FROM commit_operations WHERE draft_id=?", (row["id"],)).fetchone()
    if op is None:
        return
    if _ledger_result(vault, row["id"]):
        recovered = commit_draft(vault, row["id"], row["revision"])
        raise drafts.DraftError("题目已经入库，请重新读取草稿", 409, "state_conflict",
                                recovered["draft"]["revision"])
    artifacts = drafts._loads(op["artifacts_json"], None)
    if not isinstance(artifacts, dict):
        raise drafts.DraftError("上次入库未完成，请先重试通过以恢复暂存文件", 409,
                                "operation_pending", row["revision"])
    root = os.path.realpath(questions_root(vault))
    files = []
    prefix = f"{op['uid']}-{op['question_id'].replace('OP-', '')}-"
    for relative, expected_hash in artifacts.items():
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise drafts.DraftError("暂存文件记录不完整", 409, "operation_pending", row["revision"])
        path = os.path.realpath(os.path.join(vault, relative))
        if os.path.commonpath((root, path)) != root or not (
            relative == op["file_path"] or os.path.basename(path).startswith(prefix)):
            raise drafts.DraftError("暂存文件路径不安全", 409, "operation_pending", row["revision"])
        if os.path.exists(path):
            with open(path, "rb") as file:
                actual_hash = hashlib.sha256(file.read()).hexdigest()
            if actual_hash != expected_hash:
                raise drafts.DraftError("暂存文件已被修改，不能自动清理", 409,
                                        "operation_pending", row["revision"])
            files.append(path)
    for path in files:
        os.remove(path)
    db.execute("DELETE FROM commit_operations WHERE draft_id=?", (row["id"],))


def update_draft(vault, draft_id, revision, fields, blocks, source_images=None):
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            _revision(row, revision)
            _editable(row)
            drafts._source_view(vault, db, row, drafts._draft_blocks(db, draft_id))
            row = _row(db, draft_id)
            values = _fields(row, fields)
            old_sources = [r[0] for r in db.execute(
                "SELECT image_sha FROM draft_images WHERE draft_id=? ORDER BY ord", (draft_id,))]
            if source_images is None:
                sources = old_sources
            else:
                if not isinstance(source_images, list) or any(not isinstance(v, str) for v in source_images):
                    raise drafts.DraftError("source_images 必须是图片 SHA 数组")
                sources = list(dict.fromkeys(source_images))
                for sha in sources:
                    if not db.execute("SELECT 1 FROM conv_images WHERE conversation_id=? AND sha256=?",
                                      (row["conversation_id"], sha)).fetchone():
                        raise drafts.DraftError(f"来源图片不属于本对话：{sha}")
            prepared = _blocks(db, row, blocks, set(sources))
            status = "cropping" if any(b[4] == "image" and b[7] is None for b in prepared) else "review"
            _prepared_before_change(vault, db, row)
            db.execute("UPDATE drafts SET subject=?,category=?,difficulty=?,knowledge_points=?,labels=?,cause=?,note=?,status=?,revision=revision+1,updated_at=?,sources_complete=? WHERE id=?",
                       (values["subject"], values["category"], values["difficulty"], json.dumps(values["knowledge_points"], ensure_ascii=False),
                        json.dumps(values["labels"], ensure_ascii=False), values["cause"], values["note"], status,
                        drafts._now(), int(bool(row["sources_complete"]) or
                                           (source_images is not None and sources != old_sources)), draft_id))
            db.execute("DELETE FROM blocks WHERE draft_id=?", (draft_id,))
            db.executemany("INSERT INTO blocks(id,draft_id,section,ord,kind,text,image_sha,x,y,w,h,box_origin,ai_box,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", prepared)
            if source_images is not None:
                db.execute("DELETE FROM draft_images WHERE draft_id=?", (draft_id,))
                db.executemany("INSERT INTO draft_images(draft_id,image_sha,ord) VALUES(?,?,?)",
                               [(draft_id, sha, i) for i, sha in enumerate(sources)])
            db.commit()
        finally:
            db.close()
    drafts._log(vault, "draft.update", {"draft_id": draft_id, "revision": revision + 1, "status": status})
    return drafts.get_draft(vault, draft_id)


def discard_draft(vault, draft_id, revision):
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            if row["status"] == "discarded":
                return drafts.get_draft(vault, draft_id)
            _revision(row, revision)
            _editable(row)
            _prepared_before_change(vault, db, row)
            db.execute("UPDATE drafts SET status='discarded',revision=revision+1,updated_at=? WHERE id=?",
                       (drafts._now(), draft_id))
            db.commit()
        finally:
            db.close()
    drafts._log(vault, "draft.discard", {"draft_id": draft_id, "revision": revision + 1})
    return drafts.get_draft(vault, draft_id)


def _ledger_result(vault, draft_id):
    for commit in read_commits(vault, ascending=False):
        if commit["commit_type"] != "question.create" or commit["payload"].get("_draft", {}).get("draft_id") != draft_id:
            continue
        q = commit["payload"]["question"]
        return {"uid": q["uid"], "question_id": q["question_id"], "file_path": q["file_path"]}
    return None


def _render_blocks(vault, blocks, crops):
    rendered = []
    if crops is None:
        crops = {}
    if not isinstance(crops, dict) or any(not isinstance(k, str) for k in crops):
        raise drafts.DraftError("crops 必须是块 id 到图片 data URL 的映射")
    image_ids = {b["id"] for b in blocks if b["kind"] == "image"}
    if set(crops) - image_ids:
        raise drafts.DraftError("crops 包含不存在的图片区块")
    for block in blocks:
        if block["kind"] == "text":
            rendered.append({"section": block["section"], "kind": "text", "text": block["text"]})
            continue
        box = _box(block["box"])
        if box is None:
            raise drafts.DraftError(f"图片块 {block['id']} 还未框选", 409, "state_conflict")
        full = all(abs(box[k] - v) < 1e-8 for k, v in {"x": 0, "y": 0, "w": 1, "h": 1}.items())
        if block["id"] in crops:
            image_url = crops[block["id"]]
        elif full:
            image_url = drafts.image_data_url(vault, block["image_sha"])
        else:
            raise drafts.DraftError(f"图片块 {block['id']} 需要裁图数据", 400, "crop_required")
        mime, _width, _height, _data = drafts._decode_image_data_url(image_url)
        if not image_url.startswith(f"data:{mime};base64,"):
            raise drafts.DraftError(f"图片区块 {block['id']} 的声明格式与实际内容不一致")
        rendered.append({"section": block["section"], "kind": "image", "data": image_url, "mime": mime})
    return rendered


def commit_draft(vault, draft_id, revision, crops=None, actor="api"):
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            existing = _ledger_result(vault, draft_id)
            if existing:
                # Ledger 是最终事实：先修复投影，再补草稿状态。
                rebuild_projection(vault)
                if row["status"] != "done":
                    db.execute("UPDATE drafts SET status='done',uid=?,question_id=?,revision=revision+1,updated_at=? WHERE id=?",
                               (existing["uid"], existing["question_id"], drafts._now(), draft_id))
                    db.commit()
                db.execute("UPDATE commit_operations SET phase='done',result_json=? WHERE draft_id=?",
                           (json.dumps(existing, ensure_ascii=False), draft_id))
                db.commit()
                return {"draft": drafts.get_draft(vault, draft_id), "result": existing,
                        "reused": True, "training": {"status": "not_requested"}}
            _revision(row, revision)
            if row["status"] != "review":
                raise drafts.DraftError("只有待审核草稿可以入库", 409, "state_conflict", row["revision"])
            blocks = drafts._draft_blocks(db, draft_id)
            rendered = _render_blocks(vault, blocks, crops)
            op = db.execute("SELECT * FROM commit_operations WHERE draft_id=?", (draft_id,)).fetchone()
            if op is None:
                category_dir, _, _ = safe_question_directory(vault, row["subject"], row["category"])
                uid = creation._next_uid(questions_root(vault), row["category"])
                question_id = reserve_operation_id(vault)
                relpath = os.path.relpath(os.path.join(category_dir, f"{uid}.md"), vault)
                prepared_at = drafts._now()
                db.execute("INSERT INTO commit_operations(draft_id,revision,uid,question_id,file_path,phase,actor,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (draft_id, revision, uid, question_id, relpath, "prepared", actor, prepared_at))
                db.commit()
            else:
                if op["revision"] != revision:
                    raise drafts.DraftError("入库操作的草稿版本不一致", 409, "revision_conflict", row["revision"])
                uid, question_id, relpath, actor = op["uid"], op["question_id"], op["file_path"], op["actor"]
                prepared_at = op["created_at"]
            result = creation.create_question(
                vault, row["subject"], row["category"], row["difficulty"], note=row["note"],
                related_tags=drafts._loads(row["knowledge_points"], []), cause=row["cause"],
                labels=drafts._loads(row["labels"], []), ordered_blocks=rendered,
                draft_origin={"draft_id": draft_id, "conversation_id": row["conversation_id"]},
                reserved_identity={"uid": uid, "question_id": question_id, "today": prepared_at[:10]}, actor=actor)
            db.execute("UPDATE drafts SET status='done',uid=?,question_id=?,revision=revision+1,updated_at=? WHERE id=?",
                       (result["uid"], result["question_id"], drafts._now(), draft_id))
            db.execute("UPDATE commit_operations SET phase='done',result_json=? WHERE draft_id=?",
                       (json.dumps(result, ensure_ascii=False), draft_id))
            db.commit()
        finally:
            db.close()
    drafts._log(vault, "draft.commit", {"draft_id": draft_id, "revision": revision + 1,
                                        "uid": result["uid"], "question_id": result["question_id"]})
    return {"draft": drafts.get_draft(vault, draft_id), "result": result,
            "reused": False, "training": {"status": "not_requested"}}
