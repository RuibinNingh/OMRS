"""收件箱逐卡创建回执：预留 → Ledger 原子事实 → 补齐暂存状态。"""
import base64
import datetime
import hashlib
import json
import os
import re
import sqlite3
import uuid

from . import creation, inbox
from .common import questions_root
from .creation_operation import CreationOperation
from .ledger import connect, reserve_operation_id
from .locking import write_lock
from .migration import ensure_ledger_bootstrap
from .projections import rebuild_projection
from .taxonomy import category_path
from .vault_lifecycle import lease, atomic_json, fsync_dir


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _receipt(vault, op):
    with connect(vault) as db:
        row = db.execute("SELECT result_json FROM op_results WHERE op_id=?", (op["operation_id"],)).fetchone()
        if not row:
            return None
        result = json.loads(row[0])
        commit = db.execute("SELECT commit_type,payload_json FROM commits WHERE commit_id=?", (result.get("commit_id"),)).fetchone()
        identity = json.loads(op["identity_json"])
        if (result.get("digest") != op["digest"] or result.get("question_id") != identity["question_id"]
                or not commit or commit[0] != "question.create"):
            raise inbox.InboxConflict("入库回执与创建身份不匹配，已保留数据", "operation_pending")
        payload = json.loads(commit[1])
        question, stamp = payload.get("question", {}), payload.get("_inbox", {})
        if (stamp.get("operation_id") != op["operation_id"] or stamp.get("digest") != op["digest"]
                or question.get("question_id") != identity["question_id"] or question.get("uid") != identity["uid"]
                or question.get("file_path") != identity["file_path"] or result.get("uid") != identity["uid"]
                or result.get("file_path") != identity["file_path"] or result.get("content_hash") != question.get("content_hash")):
            raise inbox.InboxConflict("创建来源不匹配，已保留数据", "operation_pending")
        return result


def _payload(vault, item, card, form, crops):
    saved = dict(item["cards"].get(str(card), {}))
    saved.update({k: v for k, v in (form or {}).items() if k in ("subject", "category", "difficulty", "tags", "labels", "cause")})
    subject, category = str(saved.get("subject") or "").strip(), str(saved.get("category") or "").strip()
    if not subject or not category:
        raise ValueError("科目和分类是必填项")
    difficulty = int(saved.get("difficulty", 5) or 5)
    if not 1 <= difficulty <= 10:
        raise ValueError("难度必须为1到10")
    labels = saved.get("labels") or []
    tags = saved.get("tags") or []
    if isinstance(tags, str):
        tags = [v.strip() for v in re.split(r"[,，]", tags) if v.strip()]
    for values in (labels, tags):
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError("标记和知识点必须是字符串数组")
    labels, tags = [*dict.fromkeys(labels)], [*dict.fromkeys(tags)]
    regions = [r for r in item["regions"] if r["card"] == card and r["role"] != "ignore"]
    if not any(r["role"] == "question" for r in regions):
        raise ValueError(f"题卡 {card} 没有题目框")
    texts, images, binaries = {"question": [], "answer": []}, {"question": [], "answer": []}, {}
    for region in regions:
        role = region["role"]
        if region["convert"] == "auto":
            raise ValueError(f"区域 {region['id']} 还没决定转文本还是保留图片")
        if region["convert"] == "text":
            if not (region["text"] or "").strip():
                raise ValueError(f"区域 {region['id']} 没有文本")
            texts[role].append(region["text"].strip())
        else:
            encoded = inbox.region_image(vault, item, region, (crops or {}).get(region["id"]))
            if isinstance(encoded, dict) and encoded.get("upload_ref"):
                from .uploads import image_data_url
                encoded = image_data_url(vault, encoded["upload_ref"], purpose="inbox")
            raw = base64.b64decode(encoded.split(",", 1)[-1], validate=True)
            mime, _, _ = inbox.image_size(raw)
            digest = hashlib.sha256(raw).hexdigest()
            binaries[digest] = raw
            images[role].append({"sha256": digest, "mime": mime})
    payload = {"subject": subject, "category": category, "difficulty": difficulty,
               "related_tags": tags, "labels": labels, "cause": str(saved.get("cause") or ""),
               "question_text": "\n\n".join(texts["question"]), "answer_text": "\n\n".join(texts["answer"]),
               "images": images}
    return payload, binaries


def _frozen_dir(vault, operation_id, create=False):
    if not re.fullmatch(r"inbox-[a-f0-9]{32}", operation_id):
        raise inbox.InboxConflict("预留操作编号不合法", "operation_pending")
    path = os.path.join(inbox.inbox_dir(vault), "operations", operation_id)
    root = os.path.realpath(questions_root(vault))
    if os.path.commonpath((root, os.path.realpath(path))) != root:
        raise inbox.InboxConflict("预留目录越界", "operation_pending")
    cursor = path
    while os.path.abspath(cursor) != os.path.abspath(vault):
        if os.path.islink(cursor):
            raise inbox.InboxConflict("预留目录不能包含链接", "operation_pending")
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent
    if create:
        os.makedirs(path, exist_ok=True)
        fsync_dir(os.path.dirname(path))
        fsync_dir(inbox.inbox_dir(vault))
    return path


def _freeze(vault, operation_id, binaries):
    directory = _frozen_dir(vault, operation_id, create=True)
    for digest, raw in binaries.items():
        path = os.path.join(directory, digest)
        if os.path.islink(path):
            raise inbox.InboxConflict("预留图片不能是链接", "operation_pending")
        if os.path.exists(path):
            with open(path, "rb") as file:
                if hashlib.sha256(file.read()).hexdigest() != digest:
                    raise inbox.InboxConflict("预留图片已被修改，不能覆盖", "operation_pending")
            continue
        temporary = path + "." + uuid.uuid4().hex + ".tmp"
        with open(temporary, "xb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        fsync_dir(directory)


def _finish(vault, op, result):
    payload = json.loads(op["payload_json"])
    with inbox.connect(vault) as db:
        row = db.execute("SELECT * FROM items WHERE id=?", (op["item_id"],)).fetchone()
        if not row or row["reset_epoch"] != op["reset_epoch"]:
            raise inbox.InboxConflict("图片代次已变化，不能补入旧回执", "reset_conflict")
        saved = {k: payload[k] for k in ("subject", "category", "difficulty", "labels", "cause")}
        saved["tags"] = payload["related_tags"]
        inbox._write_cards(db, op["item_id"], {str(op["card"]): saved})
        already = db.execute("SELECT created_question_id FROM cards WHERE item_id=? AND card=?", (op["item_id"], op["card"])).fetchone()[0]
        db.execute("UPDATE cards SET created_uid=?,created_question_id=? WHERE item_id=? AND card=?",
                   (result["uid"], result["question_id"], op["item_id"], op["card"]))
        missing = db.execute("SELECT 1 FROM regions r WHERE r.item_id=? AND r.role!='ignore' AND NOT EXISTS "
                             "(SELECT 1 FROM cards c WHERE c.item_id=r.item_id AND c.card=r.card AND c.created_question_id!='') LIMIT 1",
                             (op["item_id"],)).fetchone()
        if not missing:
            db.execute("UPDATE items SET status='done',link_uid=?,link_question_id=? WHERE id=?", (result["uid"], result["question_id"], op["item_id"]))
        if not already:
            db.execute("UPDATE items SET revision=revision+1,updated_at=? WHERE id=?", (inbox._now(), op["item_id"]))
        db.execute("UPDATE commit_operations SET phase='applied',result_json=? WHERE operation_id=?", (_json(result), op["operation_id"]))
    return {**result, "item_id": op["item_id"], "card": op["card"]}


def _execute(vault, op):
    result = _receipt(vault, op)
    if result:
        rebuild_projection(vault)
        return {**_finish(vault, op, result), "reused": True}
    payload, identity = json.loads(op["payload_json"]), json.loads(op["identity_json"])
    images = {}
    for role, entries in payload["images"].items():
        images[role] = []
        for entry in entries:
            path = os.path.join(_frozen_dir(vault, op["operation_id"]), entry["sha256"])
            if os.path.islink(path):
                raise inbox.InboxConflict("预留图片不能是链接", "operation_pending")
            try:
                with open(path, "rb") as file:
                    raw = file.read()
            except OSError as exc:
                raise inbox.InboxConflict("预留图片未完整写入，请用原内容重试", "operation_pending") from exc
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise inbox.InboxConflict("预留图片内容冲突，已保留", "operation_pending")
            images[role].append({"data": raw})
    def validate(current_vault):
        with inbox.connect(current_vault) as db:
            current = db.execute("SELECT identity_json,digest FROM commit_operations WHERE operation_id=?", (op["operation_id"],)).fetchone()
            if not current or current[0] != op["identity_json"] or current[1] != op["digest"]:
                raise inbox.InboxConflict("创建预留已变化", "operation_pending")
        artifacts = json.loads(op["artifacts_json"])
        for relative, expected_hash in artifacts.items():
            path = os.path.realpath(os.path.join(current_vault, relative))
            if os.path.commonpath((path, os.path.realpath(questions_root(current_vault)))) != os.path.realpath(questions_root(current_vault)):
                raise inbox.InboxConflict("预留产物路径越界", "operation_pending")
            if os.path.exists(path):
                with open(path, "rb") as file:
                    if hashlib.sha256(file.read()).hexdigest() != expected_hash:
                        raise inbox.InboxConflict("预留产物被修改，已保留", "operation_pending")
    def save_artifacts(current_vault, artifacts):
        with inbox.connect(current_vault) as db:
            db.execute("UPDATE commit_operations SET artifacts_json=? WHERE operation_id=?", (_json(artifacts), op["operation_id"]))
    operation = CreationOperation(identity, {"item_id": op["item_id"], "reset_epoch": op["reset_epoch"], "card": op["card"]},
                                  op["operation_id"], op["digest"], validate, save_artifacts)
    values = {k: v for k, v in payload.items() if k != "images"}
    result = creation.create_question(vault, **values, question_images=images["question"], answer_images=images["answer"], operation=operation)
    return {**_finish(vault, op, result), "reused": False}


def commit_item(vault, item_id, card=1, form=None, crops=None, expected_revision=None, reset_epoch=None, require_version=False):
    with lease(vault), write_lock(), inbox._LOCK:
        item = inbox.get_item(vault, item_id)
        if not item:
            raise ValueError(f"收件箱里没有 {item_id}")
        if require_version and (type(expected_revision) is not int or type(reset_epoch) is not int):
            raise inbox.InboxConflict("缺少修订号或代次，请刷新", "revision_required")
        if reset_epoch is not None and reset_epoch != item["reset_epoch"]:
            raise inbox.InboxConflict("图片已重置", "reset_conflict")
        card = int(card or 1)
        payload, binaries = _payload(vault, item, card, form, crops)
        digest = hashlib.sha256(_json(payload).encode()).hexdigest()
        with inbox.connect(vault) as db:
            op = db.execute("SELECT * FROM commit_operations WHERE item_id=? AND reset_epoch=? AND card=?", (item_id, item["reset_epoch"], card)).fetchone()
            if op:
                op = dict(op)
                if op["digest"] != digest or op["phase"] == "cancelled":
                    raise inbox.InboxConflict("此卡已提交不同内容，不能再次创建", "request_conflict")
            else:
                if item["training_only"] or item["status"] in {"done", "discarded"}:
                    raise ValueError("这张图已经结束或为训练专用，不能录入题库")
                row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
                inbox._check_write(row, expected_revision, reset_epoch, require_version)
                prior = db.execute("SELECT created_question_id,created_uid FROM cards WHERE item_id=? AND card=?", (item_id, card)).fetchone()
                if prior and (prior[0] or prior[1]):
                    # 旧版本已创建但无完整内容回执：保留原身份，禁止新建。
                    if not prior[0]:
                        raise inbox.InboxConflict("旧题卡只保存UID，无法证明创建身份，请核对历史后处理；未创建新题", "identity_unresolved")
                    return {"uid": prior[1], "question_id": prior[0], "item_id": item_id, "card": card, "reused": True}
                ensure_ledger_bootstrap(vault)
                directory, _, category = category_path(vault, payload["subject"], payload["category"])
                uid = creation._next_uid(questions_root(vault), category)
                identity = {"uid": uid, "question_id": reserve_operation_id(vault),
                            "file_path": os.path.relpath(os.path.join(directory, uid + ".md"), vault), "today": datetime.date.today().isoformat()}
                op = {"operation_id": "inbox-" + uuid.uuid4().hex, "item_id": item_id, "reset_epoch": item["reset_epoch"],
                      "card": card, "revision": item["revision"], "digest": digest, "identity_json": _json(identity),
                      "payload_json": _json(payload), "artifacts_json": "{}", "phase": "prepared"}
                db.execute("INSERT INTO commit_operations(operation_id,item_id,reset_epoch,card,revision,digest,identity_json,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                           tuple(op[k] for k in ("operation_id", "item_id", "reset_epoch", "card", "revision", "digest", "identity_json", "payload_json")))
        _freeze(vault, op["operation_id"], binaries)
        result = _execute(vault, op)
        inbox._log(vault, "item.commit", {"item_id": item_id, "card": card, "question_id": result["question_id"], "uid": result["uid"], "reused": result["reused"]})
        return result


def pending_question_ids(vault):
    path = os.path.join(questions_root(vault), ".omrs", "inbox", "inbox.db")
    if not os.path.isfile(path):
        return set()
    with lease(vault):
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            try:
                return {json.loads(row[0])["question_id"] for row in db.execute("SELECT identity_json FROM commit_operations WHERE phase='prepared'")}
            except sqlite3.OperationalError:
                return set()
        finally:
            db.close()


def recover_pending(vault):
    path = os.path.join(questions_root(vault), ".omrs", "inbox", "inbox.db")
    if not os.path.isfile(path):
        return {"recovered": 0, "awaiting_images": []}
    recovered, awaiting = 0, []
    with lease(vault), write_lock(), inbox._LOCK:
        with inbox.connect(vault) as db:
            ops = [dict(row) for row in db.execute("SELECT * FROM commit_operations WHERE phase='prepared'")]
        for op in ops:
            payload = json.loads(op["payload_json"])
            missing = any(not os.path.isfile(os.path.join(_frozen_dir(vault, op["operation_id"]), entry["sha256"]))
                          for values in payload["images"].values() for entry in values)
            if missing and _receipt(vault, op) is None:
                # 身份与摘要已经预留，但尚无创建事实；等待原裁图重传，扫描跳过预留身份。
                for relative, expected in json.loads(op["artifacts_json"]).items():
                    candidate = os.path.realpath(os.path.join(vault, relative))
                    if os.path.commonpath((candidate, os.path.realpath(questions_root(vault)))) != os.path.realpath(questions_root(vault)):
                        raise inbox.InboxConflict("预留产物路径越界", "operation_pending")
                    if os.path.exists(candidate):
                        with open(candidate, "rb") as file:
                            if hashlib.sha256(file.read()).hexdigest() != expected:
                                raise inbox.InboxConflict("预留产物被修改，已保留", "operation_pending")
                awaiting.append({"item_id": op["item_id"], "card": op["card"]})
                continue
            _execute(vault, op)
            recovered += 1
    return {"recovered": recovered, "awaiting_images": awaiting}
