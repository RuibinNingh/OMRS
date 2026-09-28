"""正文入账：题目 Markdown 的历史版本存进 Ledger 的 blobs 表，commit 只引用哈希。

- record_file_change：写文件后按「元数据变了 → question.metadata_update，只改正文 → question.content_update」
  追加一条 commit，前后两版正文随同一事务进 blobs；
- ensure_content_recorded：写正文前对齐——文件里有未入账的版本（例如 Obsidian 刚改过），先以 self_check 记一笔；
- ensure_content_snapshot：首次启用时把全部题目的当前正文回填为一条 question.content_snapshot（幂等）；
- content_versions / restore_content：列出、取回、还原某题的正文版本（含已删除题目）。
见 AI/ledger.md「正文入账」、AI/data.md。
"""
import os

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
    current = blob_hash(content)
    if current != (row.get("content_hash") or ""):
        append_commit(vault, "self_check", "question.content_update", "写入前发现未入账的正文修改", {
            "question_id": row["question_id"],
            "uid_at_that_time": row["uid"],
            "before_hash": row.get("content_hash") or "",
            "after_hash": current,
        }, blobs=[content])
        row["content_hash"] = current
    elif not has_blob(vault, current):
        store_blob(vault, content)
    return current


def record_file_change(vault, row, before, after, message, source="api", extra=None):
    from .workspace_sync import metadata_hash
    before_hash, after_hash = blob_hash(before), blob_hash(after)
    if before_hash == after_hash:
        return None
    meta_before, meta_after = parse_yaml_frontmatter(before), parse_yaml_frontmatter(after)
    payload = {"question_id": row["question_id"], "uid_at_that_time": row["uid"],
               "before_hash": before_hash, "after_hash": after_hash, **(extra or {})}
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
    atomic_write(question_file(vault, row), new_content)
    return record_file_change(vault, row, before, new_content, message, source=source, extra=extra)


def refresh_projection(vault):
    from .projections import rebuild_projection
    from .workspace_sync import update_fingerprints
    state = rebuild_projection(vault)
    update_fingerprints(vault, [
        {key: q.get(key) for key in ("question_id", "uid", "file_path", "metadata_hash", "content_hash")}
        for q in state["questions"].values() if not q.get("archived")
    ])
    return state


def ensure_content_snapshot(vault):
    """回填：把现有全部题目的正文放进 blobs，写一条 question.content_snapshot（source=migration）。只执行一次。"""
    from .locking import write_lock
    with write_lock():
        with connect(vault) as db:
            done = db.execute(
                "SELECT 1 FROM commits WHERE commit_type = 'question.content_snapshot' LIMIT 1").fetchone()
            rows = [dict(r) for r in db.execute(
                "SELECT * FROM question_projection WHERE archived = 0").fetchall()]
        if done or not rows:
            return {"status": "skipped", "count": 0}
        items, blobs = [], []
        for row in rows:
            try:
                content = read_question_file(vault, row)
            except (OSError, ValueError):
                continue
            blobs.append(content)
            items.append({"question_id": row["question_id"], "uid": row["uid"], "content_hash": blob_hash(content)})
        append_commit(vault, "migration", "question.content_snapshot", f"回填 {len(items)} 道题的正文",
                      {"items": items}, blobs=blobs)
        return {"status": "ok", "count": len(items)}


def _hashes_in(commit, question_id):
    payload, ctype = commit["payload"] or {}, commit["commit_type"]
    if ctype in ("question.create", "question.create_external"):
        q = payload.get("question") or payload
        return [q.get("content_hash")] if q.get("question_id") == question_id else []
    if ctype == "question.content_snapshot":
        return [i.get("content_hash") for i in payload.get("items", []) if i.get("question_id") == question_id]
    if payload.get("question_id") != question_id:
        return []
    if payload.get("after_hash"):
        return [payload["after_hash"]]
    after = payload.get("after") or {}
    if after.get("content_hash"):
        return [after["content_hash"]]
    if payload.get("content_hash"):
        return [payload["content_hash"]]
    return []


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
            versions.append({"seq": commit["seq"], "commit_id": commit["commit_id"], "created_at": commit["created_at"],
                             "source": commit["source"], "commit_type": commit["commit_type"], "hash": h,
                             "available": has_blob(vault, h)})
    return {"question_id": qid, "uid": row["uid"], "archived": bool(row["archived"]),
            "current_hash": row.get("content_hash") or "", "versions": versions}


def restore_content(vault, uid, content_hash, expected_hash=None):
    row = projection_row(vault, uid=uid)
    if row is None:
        raise RuntimeError(f"UID 不存在：{uid}")
    content = get_blob(vault, content_hash)
    if content is None:
        raise RuntimeError("这个版本的正文不在 Ledger 里")
    commit = write_question(vault, row, content, f"还原题目 {uid} 的正文", expected_hash=expected_hash,
                            extra={"restored_from": content_hash})
    refresh_projection(vault)
    return {"uid": uid, "restored_from": content_hash, "commit_id": commit["commit_id"] if commit else ""}
