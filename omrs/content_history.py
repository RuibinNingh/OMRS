"""正文入账：题目 Markdown 的历史版本存进 Ledger 的 blobs 表，commit 只引用哈希。

- record_file_change：写文件后按「元数据变了 → question.metadata_update，只改正文 → question.content_update」
  追加一条 commit，前后两版正文随同一事务进 blobs；
- ensure_content_recorded：写正文前对齐——文件里有未入账的版本（例如 Obsidian 刚改过），先以 self_check 记一笔；
- backfill_missing_content：启动前只补当前缺失的正文 blob，冲突跳过且重复执行不新增提交；
- content_versions / restore_content：列出、取回、还原某题的正文版本（含已删除题目）。
见 AI/ledger.md「正文入账」、AI/data.md。
"""
import json
import os
import sqlite3
from pathlib import Path

from .common import (extract_category, extract_knowledge_tags, extract_labels, extract_tag,
                     parse_yaml_frontmatter)
from .ledger import append_commit, blob_hash, connect, get_blob, has_blob, read_commits, store_blob
from .path_safety import safe_question_path


class ContentConflict(RuntimeError):
    """写入方给的 expected_content_hash 与文件当前正文对不上（HTTP 409）。"""


def projection_row(vault, uid=None, question_id=None, include_archived=False):
    with connect(vault) as db:
        if question_id:
            row = db.execute("SELECT * FROM question_projection WHERE question_id = ?", (question_id,)).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM question_projection WHERE uid = ? AND archived = 0", (uid,)).fetchone()
    if row and (include_archived or not row["archived"]):
        return dict(row)
    return None


def question_file(vault, row):
    return safe_question_path(vault, os.path.abspath(os.path.join(vault, row["file_path"])))


def read_question_file(vault, row):
    with open(question_file(vault, row), "r", encoding="utf-8") as file:
        return file.read()


def atomic_write(path, content):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)


def question_payload(row, content):
    from .workspace_sync import metadata_hash
    meta = parse_yaml_frontmatter(content)
    return {
        "question_id": row["question_id"],
        "uid": row["uid"],
        "file_path": row["file_path"],
        "subject": meta.get("科目", row.get("subject", "")),
        "category": extract_category(meta) or row.get("category", ""),
        "difficulty": meta.get("难度", row.get("difficulty", 5)),
        "current_tag": extract_tag(meta),
        "knowledge_tags": extract_knowledge_tags(meta),
        "labels": extract_labels(meta),
        "metadata": meta,
        "metadata_hash": metadata_hash(meta),
        "content_hash": blob_hash(content),
        "archived": False,
    }


def ensure_content_recorded(vault, row, content):
    """文件当前正文与投影记录的哈希不同时，先把这个未入账的版本记一笔（self_check）。"""
    check_content_reconcile(vault, row, content)
    current = blob_hash(content)
    if current != (row.get("content_hash") or ""):
        append_commit(vault, "self_check", "question.content_update", "写入前发现未入账的正文修改", {
            "question_id": row["question_id"],
            "uid_at_that_time": row["uid"],
            "before_hash": row.get("content_hash") or "",
            "after_hash": current,
        }, blobs=[content])
        row["content_hash"] = current
        refresh_projection(vault)
    elif not has_blob(vault, current):
        store_blob(vault, content)
    return current


def check_content_reconcile(vault, row, content):
    """旧投影正文不可验证时，阻止写入掩盖不可回填的缺口。"""
    if parse_yaml_frontmatter(content).get("_omrs_id") != row["question_id"]:
        raise ContentConflict("题目文件身份与 Ledger 不一致，已拒绝写入")
    current = blob_hash(content)
    expected = row.get("content_hash") or ""
    previous = get_blob(vault, expected)
    if previous is None:
        if current != expected:
            raise ContentConflict("投影旧正文 blob 缺失且文件已改，已暂停该题写入；请先核对备份")
    elif blob_hash(previous) != expected or parse_yaml_frontmatter(previous).get("_omrs_id") != row["question_id"]:
        raise ContentConflict("投影正文 blob 校验失败，已暂停该题写入；请先核对备份")


def ensure_content_deletable(vault, row, content, record_change=True):
    """删除前保存并核对文件的实际正文；调用方仍须持有写锁。"""
    question_id = parse_yaml_frontmatter(content).get("_omrs_id")
    if question_id != row["question_id"]:
        raise ContentConflict("题目文件身份与 Ledger 不一致，已拒绝删除")
    current = (ensure_content_recorded(vault, row, content) if record_change
               else blob_hash(content))
    if not record_change:
        store_blob(vault, content)
    if get_blob(vault, current) != content:
        raise RuntimeError("正文未能保存到 Ledger，已拒绝删除")
    return current


def record_file_change(vault, row, before, after, message, source="api", extra=None):
    from .workspace_sync import metadata_hash
    from .projections import _content_change_summary
    before_hash, after_hash = blob_hash(before), blob_hash(after)
    if before_hash == after_hash:
        return None
    meta_before, meta_after = parse_yaml_frontmatter(before), parse_yaml_frontmatter(after)
    payload = {"question_id": row["question_id"], "uid_at_that_time": row["uid"],
               "before_hash": before_hash, "after_hash": after_hash,
               "change_summary": _content_change_summary(before, after), **(extra or {})}
    if metadata_hash(meta_before) != metadata_hash(meta_after):
        payload["before"] = question_payload(row, before)
        payload["after"] = question_payload(row, after)
        return append_commit(vault, source, "question.metadata_update", message, payload, blobs=[before, after])
    return append_commit(vault, source, "question.content_update", message, payload, blobs=[before, after])


def write_question(vault, row, new_content, message, expected_hash=None, source="api", extra=None):
    """写前对齐 → 校验 expected_hash → 原子写文件 → 入账。调用方负责之后刷新投影（refresh_projection）。"""
    before = read_question_file(vault, row)
    current = ensure_content_recorded(vault, row, before)
    if expected_hash and expected_hash != current:
        raise ContentConflict("题目正文已被修改，请刷新后重试")
    if parse_yaml_frontmatter(new_content).get("_omrs_id") != row["question_id"]:
        raise ContentConflict("新正文的题目身份与 Ledger 不一致，已拒绝写入")
    atomic_write(question_file(vault, row), new_content)
    try:
        return record_file_change(vault, row, before, new_content, message, source=source, extra=extra)
    except BaseException:
        atomic_write(question_file(vault, row), before)
        raise


def refresh_projection(vault):
    from .projections import rebuild_projection
    from .workspace_sync import update_fingerprints
    state = rebuild_projection(vault)
    update_fingerprints(vault, [
        {key: q.get(key) for key in ("question_id", "uid", "file_path", "metadata_hash", "content_hash")}
        for q in state["questions"].values() if not q.get("archived")
    ])
    return state


def backfill_missing_content(vault):
    """只补当前活动题缺失的 blob；冲突文件跳过，重复执行不写入。"""
    from .locking import write_lock
    with write_lock():
        with connect(vault) as db:
            rows = [dict(r) for r in db.execute(
                "SELECT * FROM question_projection WHERE archived = 0").fetchall()]
            existing = {r["hash"]: r["content"] for r in db.execute("SELECT hash, content FROM blobs")}
        items, blobs, conflicts = [], [], []
        for row in rows:
            expected = row.get("content_hash") or ""
            if expected in existing and blob_hash(existing[expected]) == expected:
                continue
            if expected in existing:
                conflicts.append({"question_id": row["question_id"], "uid": row["uid"],
                                  "reason": "已有 blob 内容与哈希不一致"})
                continue
            try:
                content = read_question_file(vault, row)
            except (OSError, ValueError) as exc:
                conflicts.append({"question_id": row["question_id"], "uid": row["uid"], "reason": str(exc)})
                continue
            if blob_hash(content) != expected or parse_yaml_frontmatter(content).get("_omrs_id") != row["question_id"]:
                conflicts.append({"question_id": row["question_id"], "uid": row["uid"], "reason": "文件哈希或身份与投影不一致"})
                continue
            blobs.append(content)
            items.append({"question_id": row["question_id"], "uid": row["uid"], "content_hash": expected})
        if items:
            append_commit(vault, "migration", "question.content_backfill", f"补齐 {len(items)} 道题的正文",
                          {"items": items}, blobs=blobs)
        return {"status": "conflict" if conflicts else "ok", "count": len(items), "conflicts": conflicts}


def ensure_content_snapshot(vault):
    """兼容旧调用点；新启动流程只做缺失 blob 的增量回填。"""
    return backfill_missing_content(vault)


def audit_content_coverage(vault):
    """只读盘点当前文件、投影与 blob；不会初始化或迁移 Ledger。"""
    from .ledger import ledger_path
    path = ledger_path(vault)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    db = sqlite3.connect(f"{Path(path).absolute().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        rows = [dict(r) for r in db.execute("SELECT question_id, uid, file_path, content_hash, archived FROM question_projection")]
        blobs = {r["hash"]: r["content"] for r in db.execute("SELECT hash, content FROM blobs")}
        commits = [(r["seq"], r["commit_type"], json.loads(r["payload_json"] or "{}"))
                   for r in db.execute("SELECT seq, commit_type, payload_json FROM commits ORDER BY seq")]
    finally:
        db.close()
    active = [r for r in rows if not r["archived"]]
    missing, conflicts = [], []
    for row in active:
        h = row["content_hash"] or ""
        try:
            content = read_question_file(vault, row)
            actual_hash = blob_hash(content)
            actual_id = parse_yaml_frontmatter(content).get("_omrs_id")
            matches = actual_hash == h and actual_id == row["question_id"]
            if not matches:
                conflicts.append({"question_id": row["question_id"], "uid": row["uid"],
                                  "reason": "文件哈希与投影不一致" if actual_hash != h else "文件身份与投影不一致"})
        except (OSError, ValueError) as exc:
            matches = False
            conflicts.append({"question_id": row["question_id"], "uid": row["uid"], "reason": str(exc)})
        if h and h not in blobs:
            missing.append({"question_id": row["question_id"], "uid": row["uid"], "hash": h,
                            "recoverable_from_current_file": matches})
        elif h and blob_hash(blobs[h]) != h:
            conflicts.append({"question_id": row["question_id"], "uid": row["uid"],
                              "reason": "已有 blob 内容与哈希不一致"})
    snapshot_seq = next((seq for seq, typ, _ in commits if typ == "question.content_snapshot"), None)
    available_hashes = {h for h, content in blobs.items() if blob_hash(content) == h}
    historical = {}
    for seq, typ, payload in commits:
        if typ == "legacy.bootstrap":
            pairs = [(x.get("question_id"), x.get("content_hash")) for x in payload.get("questions", [])]
        elif typ in ("question.content_snapshot", "question.content_backfill"):
            pairs = [(x.get("question_id"), x.get("content_hash")) for x in payload.get("items", [])]
        else:
            question = payload.get("question") or {}
            qid = payload.get("question_id") or question.get("question_id")
            refs = [payload.get("before_hash"), payload.get("after_hash"), payload.get("content_hash"),
                    question.get("content_hash"), (payload.get("before") or {}).get("content_hash"),
                    (payload.get("after") or {}).get("content_hash")]
            pairs = [(qid, h) for h in refs]
        for qid, h in pairs:
            if qid and h and h not in available_hashes:
                historical.setdefault((qid, h), seq)
    current_pairs = {(r["question_id"], r["content_hash"]) for r in active}
    historical_gaps = [{"question_id": qid, "hash": h, "first_referenced_seq": seq,
                        "reason": "blob 缺失" if h not in blobs else "blob 内容与哈希不一致",
                        "before_first_snapshot": bool(snapshot_seq and seq < snapshot_seq)}
                       for (qid, h), seq in historical.items() if (qid, h) not in current_pairs]
    old = sum(gap["before_first_snapshot"] for gap in historical_gaps)
    return {"status": "ok", "active_questions": len(active), "archived_questions": len(rows) - len(active),
            "current_missing_blobs": missing, "file_conflicts": conflicts,
            "historical_missing_blobs": len(historical_gaps), "historical_gaps": historical_gaps,
            "historical_pre_snapshot_missing": old, "snapshot_seq": snapshot_seq}


def _hashes_in(commit, question_id):
    payload, ctype = commit["payload"] or {}, commit["commit_type"]
    if ctype == "legacy.bootstrap":
        return [q.get("content_hash") for q in payload.get("questions", []) if q.get("question_id") == question_id]
    if ctype in ("question.create", "question.create_external"):
        q = payload.get("question") or payload
        return [q.get("content_hash")] if q.get("question_id") == question_id else []
    if ctype in ("question.content_snapshot", "question.content_backfill"):
        return [i.get("content_hash") for i in payload.get("items", []) if i.get("question_id") == question_id]
    if payload.get("question_id") != question_id:
        return []
    return [payload.get("before_hash"), payload.get("after_hash"),
            (payload.get("before") or {}).get("content_hash"),
            (payload.get("after") or {}).get("content_hash"), payload.get("content_hash")]


def content_versions(vault, uid=None, question_id=None):
    row = projection_row(vault, uid=uid, question_id=question_id, include_archived=True)
    if row is None and uid:
        with connect(vault) as db:
            found = db.execute("SELECT * FROM question_projection WHERE uid = ? ORDER BY updated_seq DESC",
                               (uid,)).fetchone()
        row = dict(found) if found else None
    if row is None:
        raise RuntimeError(f"题目不存在：{uid or question_id}")
    qid = row["question_id"]
    versions, seen = [], set()
    for commit in read_commits(vault, ascending=True):
        for h in _hashes_in(commit, qid):
            if not h or h in seen:
                continue
            seen.add(h)
            content = get_blob(vault, h)
            versions.append({"seq": commit["seq"], "commit_id": commit["commit_id"], "created_at": commit["created_at"],
                             "source": commit["source"], "commit_type": commit["commit_type"], "hash": h,
                             "available": content is not None and blob_hash(content) == h
                             and parse_yaml_frontmatter(content).get("_omrs_id") == qid})
    return {"question_id": qid, "uid": row["uid"], "archived": bool(row["archived"]),
            "current_hash": row.get("content_hash") or "", "versions": versions}


def restore_content(vault, uid, content_hash, expected_hash=None):
    row = projection_row(vault, uid=uid)
    if row is None:
        raise RuntimeError(f"UID 不存在：{uid}")
    if content_hash not in {v["hash"] for v in content_versions(vault, question_id=row["question_id"])["versions"]}:
        raise RuntimeError("这个正文版本不属于该题")
    content = get_blob(vault, content_hash)
    if content is None:
        raise RuntimeError("这个版本的正文不在 Ledger 里")
    if blob_hash(content) != content_hash:
        raise RuntimeError("正文 blob 的内容与哈希不一致")
    if parse_yaml_frontmatter(content).get("_omrs_id") != row["question_id"]:
        raise RuntimeError("正文版本中的题目身份不匹配")
    commit = write_question(vault, row, content, f"还原题目 {uid} 的正文", expected_hash=expected_hash,
                            extra={"restored_from": content_hash})
    refresh_projection(vault)
    return {"uid": uid, "restored_from": content_hash, "commit_id": commit["commit_id"] if commit else ""}
