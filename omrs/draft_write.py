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
from .common import questions_root, load_config
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
            old_blocks = {b["id"]: b for b in drafts._draft_blocks(db, draft_id)}
            old_fields = {key: row[key] for key in ("subject", "category", "difficulty", "cause", "note")}
            old_fields.update({key: drafts._loads(row[key], []) for key in ("knowledge_points", "labels")})
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
            from .draft_training import sync_block_boxes, sync_tasks
            sync_block_boxes(db, draft_id)
            db.execute("UPDATE drafts SET subject=?,category=?,difficulty=?,knowledge_points=?,labels=?,cause=?,note=?,status=?,revision=revision+1,updated_at=?,sources_complete=? WHERE id=?",
                       (values["subject"], values["category"], values["difficulty"], json.dumps(values["knowledge_points"], ensure_ascii=False),
                        json.dumps(values["labels"], ensure_ascii=False), values["cause"], values["note"], status,
                        drafts._now(), int(bool(row["sources_complete"]) or
                                           (source_images is not None and sources != old_sources)), draft_id))
            db.execute("DELETE FROM blocks WHERE draft_id=?", (draft_id,))
            db.executemany("INSERT INTO blocks(id,draft_id,section,ord,kind,text,image_sha,x,y,w,h,box_origin,ai_box,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", prepared)
            protected = [f"field:{key}" for key, value in values.items() if old_fields[key] != value]
            for b in prepared:
                old = old_blocks.get(b[0])
                if old is None or old["text"] != b[5] or old["note"] != b[13] or old["section"] != b[2] or old["kind"] != b[4]:
                    protected.append(f"block:{b[0]}")
            db.executemany("INSERT OR IGNORE INTO draft_manual_edits(draft_id,target) VALUES(?,?)",
                           [(draft_id, target) for target in protected])
            if source_images is not None:
                db.execute("DELETE FROM draft_images WHERE draft_id=?", (draft_id,))
                db.executemany("INSERT INTO draft_images(draft_id,image_sha,ord) VALUES(?,?,?)",
                               [(draft_id, sha, i) for i, sha in enumerate(sources)])
                for sha in sources:
                    db.execute("UPDATE images SET train=? WHERE sha256=? AND train IS NULL",
                               (int(bool(load_config(vault).get("draft_train_default", False))), sha))
            sync_tasks(db, draft_id)
            sync_block_boxes(db, draft_id)
            db.commit()
        finally:
            db.close()
    drafts._log(vault, "draft.update", {"draft_id": draft_id, "revision": revision + 1, "status": status})
    return drafts.get_draft(vault, draft_id)


_AI_FIELDS = {"subject", "category", "knowledge_points", "cause", "note"}


def patch_draft(vault, draft_id, revision, fields, block_patches, actor):
    """AI 按稳定块 ID 修改文字；保留图片、框位、顺序及训练状态。"""
    if not isinstance(fields, dict) or set(fields) - _AI_FIELDS:
        raise drafts.DraftError("AI 草稿字段不在白名单内")
    if not isinstance(block_patches, list):
        raise drafts.DraftError("block_patches 必须是数组")
    if not fields and not block_patches:
        raise drafts.DraftError("没有草稿修改")
    if not isinstance(actor, dict) or not all(actor.get(k) for k in ("conversation_id", "run_id", "tool_call_id")):
        raise drafts.DraftError("缺少 AI 修改来源")
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            _revision(row, revision)
            _editable(row)
            if row["conversation_id"] != actor["conversation_id"]:
                raise drafts.DraftError("只能修改本对话草稿", 403, "forbidden")
            if db.execute("SELECT 1 FROM commit_operations WHERE draft_id=?", (draft_id,)).fetchone():
                raise drafts.DraftError("草稿正在入库，请先恢复入库结果", 409, "operation_pending", row["revision"])
            values = _fields(row, fields)
            blocks = {b["id"]: b for b in drafts._draft_blocks(db, draft_id)}
            edits, changed, seen = [], {}, set()
            for index, patch in enumerate(block_patches):
                if not isinstance(patch, dict) or set(patch) - {"block_id", "text", "note"}:
                    raise drafts.DraftError(f"第 {index + 1} 个块补丁格式不对")
                block_id = patch.get("block_id")
                if not isinstance(block_id, str) or block_id in seen or block_id not in blocks:
                    raise drafts.DraftError(f"块不存在或重复：{block_id}")
                seen.add(block_id)
                old = blocks[block_id]
                if "text" in patch and old["kind"] != "text":
                    raise drafts.DraftError("图片块只能修改说明，不能改图片或框")
                if "text" in patch and (not isinstance(patch["text"], str) or not patch["text"].strip()):
                    raise drafts.DraftError("文字块内容不能为空")
                if "note" in patch and not isinstance(patch["note"], str):
                    raise drafts.DraftError("图片说明必须是文字")
                new_text = patch["text"].strip() if "text" in patch else old["text"]
                new_note = patch["note"].strip() if "note" in patch else old["note"]
                if new_text != old["text"] or new_note != old["note"]:
                    edits.append((new_text, new_note, block_id, draft_id))
                    changed[f"block:{block_id}"] = {"before": {"text": old["text"], "note": old["note"]},
                                                       "after": {"text": new_text, "note": new_note}}
            for key in fields:
                old = drafts._loads(row[key], []) if key == "knowledge_points" else row[key]
                if values[key] != old:
                    changed[f"field:{key}"] = {"before": old, "after": values[key]}
            statement = row["cause_statement"] or ""
            if "field:cause" in changed:
                statement = actor.get("cause_statement") or ""
                if values["cause"] and not statement:
                    raise drafts.DraftError("AI 修改错因需要用户原话证据")
            if not changed:
                return {"draft": drafts.get_draft(vault, draft_id), "wrote": False, "suggestions": []}
            protected = [target for target in changed if db.execute(
                "SELECT 1 FROM draft_manual_edits WHERE draft_id=? AND target=?", (draft_id, target)).fetchone()]
            if protected:
                return {"draft": drafts.get_draft(vault, draft_id), "wrote": False,
                        "suggestions": [{"target": target, **changed[target]} for target in protected]}
            db.execute("UPDATE drafts SET subject=?,category=?,knowledge_points=?,cause=?,cause_statement=?,note=?,revision=revision+1,updated_at=? WHERE id=?",
                       (values["subject"], values["category"], json.dumps(values["knowledge_points"], ensure_ascii=False),
                        values["cause"], statement, values["note"], drafts._now(), draft_id))
            db.executemany("UPDATE blocks SET text=?,note=? WHERE id=? AND draft_id=?", edits)
            db.commit()
        finally:
            db.close()
    drafts._log(vault, "draft.ai_update", {"draft_id": draft_id, "actor": "agent",
                 "conversation_id": actor["conversation_id"], "run_id": actor["run_id"],
                 "tool_call_id": actor["tool_call_id"], "old_revision": revision,
                 "new_revision": revision + 1, "changes": changed})
    return {"draft": drafts.get_draft(vault, draft_id), "wrote": True, "suggestions": []}


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


def set_boxes(vault, draft_id, revision, blocks=None, training_boxes=None):
    if blocks is None and training_boxes is None:
        raise drafts.DraftError("至少提交一种框选改动")
    if blocks is not None and not isinstance(blocks, list):
        raise drafts.DraftError("blocks 必须是数组")
    with locking.write_lock(), drafts._LOCK:
        db = drafts.connect(vault)
        try:
            row = _row(db, draft_id)
            _revision(row, revision)
            if row["status"] == "discarded" or (row["status"] == "done" and blocks is not None):
                raise drafts.DraftError("草稿状态不允许修改正文框", 409, "state_conflict", row["revision"])
            seen, prepared = set(), []
            for index, raw in enumerate(blocks or []):
                if not isinstance(raw, dict) or set(raw) - {"id", "box", "box_origin", "ai_box"}:
                    raise drafts.DraftError(f"第 {index + 1} 个正文框格式不对")
                block_id = raw.get("id")
                block = db.execute("SELECT * FROM blocks WHERE id=? AND draft_id=?", (block_id, draft_id)).fetchone()
                if not block or block["kind"] != "image" or block_id in seen:
                    raise drafts.DraftError(f"图片块不存在或重复：{block_id}")
                seen.add(block_id)
                box = _box(raw.get("box"))
                origin = raw.get("box_origin")
                if box and origin not in ("manual", "ai", "ai_edited"):
                    raise drafts.DraftError("box_origin 不合法")
                ai_box = _box(raw.get("ai_box"))
                prepared.append((block_id, box, origin if box else None, ai_box))
            from .draft_training import prepare_training_boxes, replace_training_boxes, sync_block_boxes
            training_prepared = prepare_training_boxes(db, draft_id, training_boxes) if training_boxes is not None else {}
            if row["status"] in ("cropping", "review") and (prepared or training_prepared):
                _prepared_before_change(vault, db, row)
            for block_id, box, origin, ai_box in prepared:
                coords = tuple(box[k] for k in ("x", "y", "w", "h")) if box else (None,) * 4
                db.execute("UPDATE blocks SET x=?,y=?,w=?,h=?,box_origin=?,ai_box=? WHERE id=?",
                           (*coords, origin, json.dumps(ai_box) if ai_box else None, block_id))
            sync_block_boxes(db, draft_id)
            selected_tasks = replace_training_boxes(db, training_prepared)
            changed = bool(prepared or selected_tasks)
            if changed:
                missing = db.execute("SELECT 1 FROM blocks WHERE draft_id=? AND kind='image' AND x IS NULL LIMIT 1",
                                     (draft_id,)).fetchone()
                status = "cropping" if missing else "review"
                db.execute("UPDATE drafts SET status=CASE WHEN status='done' THEN 'done' ELSE ? END,"
                           "revision=revision+1,updated_at=? WHERE id=?", (status, drafts._now(), draft_id))
            db.commit()
        finally:
            db.close()
    if changed:
        drafts._log(vault, "draft.crop", {"draft_id": draft_id, "revision": revision + 1,
                                           "blocks": len(prepared), "training_tasks": len(selected_tasks)})
    if changed and row["status"] == "done":
        from .draft_training import register_ready
        register_ready(vault, draft_id)
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
            try:
                from .draft_jobs import _image_for
                image_url = _image_for(vault, block, None)
            except ValueError as exc:
                raise drafts.DraftError(f"图片块 {block['id']} 需要裁图数据：{exc}", 400, "crop_required") from exc
        try:
            mime, _width, _height, _data = drafts._decode_image_data_url(image_url)
        except ValueError as exc:
            raise drafts.DraftError(f"图片块 {block['id']} 的裁图不合法：{exc}") from exc
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
                vault, row["subject"], row["category"], row["difficulty"],
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
