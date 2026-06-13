import os
import re

from .common import extract_category, extract_knowledge_tags, extract_tag, parse_yaml_frontmatter, questions_root
from .ledger import append_commit, connect
from .projections import rebuild_projection
from .workspace_sync import content_hash, metadata_hash, scan_workspace, update_fingerprints


def get_question_raw(vault: str, uid: str):
    row = _projection_by_uid(vault, uid)
    if not row:
        raise RuntimeError(f"UID 不存在: {uid}")
    path = os.path.join(vault, row["file_path"])
    with open(path, "r", encoding="utf-8") as file:
        return {
            "uid": uid,
            "question_id": row["question_id"],
            "file_path": row["file_path"],
            "markdown": file.read(),
        }


def save_question_markdown(vault: str, uid: str, markdown: str):
    row = _projection_by_uid(vault, uid)
    if not row:
        raise RuntimeError(f"UID 不存在: {uid}")
    old = get_question_raw(vault, uid)
    old_id = row["question_id"]
    new_meta = parse_yaml_frontmatter(markdown)
    if new_meta.get("_omrs_id") != old_id:
        raise RuntimeError("_omrs_id 是系统内部身份，不能在编辑器中修改")
    path = os.path.join(vault, row["file_path"])
    _atomic_write_text(path, markdown)
    scan_workspace(vault)
    return {"uid": uid, "file_path": row["file_path"], "bytes": len(markdown.encode("utf-8"))}


def move_question(vault: str, uid: str, target_subject: str, target_category: str):
    row = _projection_by_uid(vault, uid)
    if not row:
        raise RuntimeError(f"UID 不存在: {uid}")
    qroot = questions_root(vault)
    target_dir = os.path.join(qroot, target_subject or row["subject"], target_category)
    os.makedirs(target_dir, exist_ok=True)
    target_uid = _next_uid(qroot, target_category)
    target_path = os.path.join(target_dir, f"{target_uid}.md")
    if os.path.exists(target_path):
        raise RuntimeError(f"目标 UID 已存在: {target_uid}")

    source_path = os.path.join(vault, row["file_path"])
    with open(source_path, "r", encoding="utf-8") as file:
        content = file.read()
    content = _replace_frontmatter_field(content, "科目", target_subject or row["subject"])
    content = _replace_frontmatter_field(content, "分类", f'"[[{target_category}]]"')
    tmp = f"{target_path}.tmp"
    _atomic_write_text(tmp, content)
    os.replace(tmp, target_path)
    os.remove(source_path)

    rel = os.path.relpath(target_path, vault)
    meta = parse_yaml_frontmatter(content)
    after = {
        "question_id": row["question_id"],
        "uid": target_uid,
        "file_path": rel,
        "subject": meta.get("科目", target_subject or row["subject"]),
        "category": extract_category(meta) or target_category,
        "difficulty": meta.get("难度", row.get("difficulty", 5)),
        "current_tag": extract_tag(meta),
        "knowledge_tags": extract_knowledge_tags(meta),
        "metadata": meta,
        "metadata_hash": metadata_hash(meta),
        "content_hash": content_hash(content),
        "archived": False,
    }
    append_commit(vault, "api", "question.move", f"迁移题目 {uid} -> {target_uid}", {
        "question_id": row["question_id"],
        "from_uid": uid,
        "to_uid": target_uid,
        "from_path": row["file_path"],
        "to_path": rel,
        "to_category": target_category,
        "after": after,
    })
    state = rebuild_projection(vault)
    update_fingerprints(vault, [
        {
            "question_id": q.get("question_id"),
            "uid": q.get("uid"),
            "file_path": q.get("file_path"),
            "metadata_hash": q.get("metadata_hash"),
            "content_hash": q.get("content_hash"),
        }
        for q in state["questions"].values()
        if not q.get("archived")
    ])
    return {"uid": target_uid, "old_uid": uid, "file_path": rel}


def _projection_by_uid(vault, uid):
    with connect(vault) as db:
        row = db.execute(
            "SELECT * FROM question_projection WHERE uid = ? AND archived = 0",
            (uid,),
        ).fetchone()
    return dict(row) if row else None


def _next_uid(qroot, category):
    pattern = re.compile(rf"^{re.escape(category)}(\d+)\.md$")
    used = set()
    for root, dirs, files in os.walk(qroot):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for fname in files:
            match = pattern.match(fname)
            if match:
                used.add(int(match.group(1)))
    idx = 1
    while idx in used:
        idx += 1
    return f"{category}{idx}"


def _replace_frontmatter_field(content, key, value):
    match = re.match(r"^(---\s*\n)(.*?)(\n---)", content, re.DOTALL)
    if not match:
        return content
    body = match.group(2)
    if re.search(rf"^{re.escape(key)}:", body, re.MULTILINE):
        body = re.sub(rf"^{re.escape(key)}:.*$", f"{key}: {value}", body, flags=re.MULTILINE)
    else:
        body = f"{body}\n{key}: {value}"
    return f"{match.group(1)}{body}{match.group(3)}{content[match.end(3):]}"


def _atomic_write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
