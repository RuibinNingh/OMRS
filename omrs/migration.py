import datetime
import json
import os
import re
import shutil

from .common import (
    HISTORY_HEADERS,
    MASTERY_HEADERS,
    SESSIONS_HEADERS,
    config_path,
    extract_category,
    extract_knowledge_tags,
    extract_tag,
    history_path,
    load_csv,
    mastery_path,
    omrs_data_dir,
    parse_yaml_frontmatter,
    questions_root,
    sessions_path,
)
from .ledger import append_commit, has_commits, reserve_operation_id
from .workspace_sync import content_hash, metadata_hash, scan_question_files, update_fingerprints


KNOWN_TEMPLATE_KEYS = ("_omrs_id", "科目", "分类", "难度", "页码", "相关知识点", "tags")


def ensure_ledger_bootstrap(vault: str):
    if has_commits(vault):
        return {"status": "exists"}

    backup_dir = backup_legacy_data(vault)
    questions = []
    changed_paths = []
    existing_mastery = {row.get("UID"): row for row in load_csv(mastery_path(vault), MASTERY_HEADERS)}
    for item in scan_question_files(vault):
        content = item["content"]
        meta = parse_yaml_frontmatter(content)
        uid = item["uid"]
        old = existing_mastery.get(uid, {})
        question_id = meta.get("_omrs_id") or reserve_operation_id(vault)
        normalized, changed = normalize_markdown_template(
            content=content,
            question_id=question_id,
            subject=meta.get("科目") or old.get("Subject") or item["subject"],
            category=extract_category(meta) or old.get("Category") or item["category"],
            difficulty=meta.get("难度") or old.get("Difficulty") or "5",
            page=meta.get("页码", ""),
            related_tags=extract_knowledge_tags(meta) or _split_tags(old.get("Knowledge_Tags", "")),
            current_tag=extract_tag(meta) or old.get("Current_Tag") or "#状态/待攻克",
        )
        if changed:
            _atomic_write_text(item["full_path"], normalized)
            changed_paths.append(item["file_path"])
            content = normalized
            meta = parse_yaml_frontmatter(content)
        q = _question_payload(vault, item, meta, question_id, content)
        questions.append(q)

    mastery_rows = []
    for row in load_csv(mastery_path(vault), MASTERY_HEADERS):
        row = dict(row)
        qid = next((q["question_id"] for q in questions if q["uid"] == row.get("UID")), "")
        row["question_id"] = qid
        mastery_rows.append(row)

    append_commit(vault, "system", "system.genesis", "初始化 Ledger", {
        "schema_version": 1,
        "created_by": "migration",
    })
    append_commit(vault, "migration", "legacy.bootstrap", "迁移旧 CSV 与 Markdown 工作区", {
        "backup_dir": backup_dir,
        "questions": questions,
        "mastery_rows": mastery_rows,
        "session_rows": load_csv(sessions_path(vault), SESSIONS_HEADERS),
        "history_rows": load_csv(history_path(vault), HISTORY_HEADERS),
        "changed_markdown_paths": changed_paths,
        "notes": [
            "旧 history_log.csv 缺少完整来源上下文，迁移后标记为 legacy。",
            "Markdown 正文不进入版本链，Ledger 只恢复结构化状态、算法状态、Session 和统计。",
        ],
    })
    update_fingerprints(vault, questions)
    return {"status": "created", "backup_dir": backup_dir, "questions": len(questions)}


def backup_legacy_data(vault: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(omrs_data_dir(vault), "legacy_backup", stamp)
    os.makedirs(target, exist_ok=True)
    for path in (mastery_path(vault), history_path(vault), sessions_path(vault), config_path(vault)):
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(target, os.path.basename(path)))
    file_list = []
    qroot = questions_root(vault)
    for root, dirs, files in os.walk(qroot):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for fname in files:
            if fname.lower().endswith(".md"):
                file_list.append(os.path.relpath(os.path.join(root, fname), vault))
    with open(os.path.join(target, "markdown_files.json"), "w", encoding="utf-8") as file:
        json.dump(sorted(file_list), file, ensure_ascii=False, indent=2)
    return os.path.relpath(target, vault)


def normalize_markdown_template(
    content: str,
    question_id: str,
    subject: str,
    category: str,
    difficulty,
    page="",
    related_tags=None,
    current_tag="#状态/待攻克",
):
    related_tags = related_tags or []
    meta = parse_yaml_frontmatter(content)
    body = content
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
    if match:
        body = content[match.end():]
    tag = (current_tag or "#状态/待攻克").replace("#", "")
    fields = {
        "_omrs_id": question_id,
        "科目": subject or meta.get("科目", ""),
        "分类": f"[[{category}]]" if category and not str(category).startswith("[[") else category,
        "难度": str(difficulty or meta.get("难度") or "5"),
        "页码": str(page or meta.get("页码", "")),
        "相关知识点": related_tags,
        "tags": [tag or "状态/待攻克"],
    }
    # Preserve known existing values unless they were empty and the caller
    # supplied a fallback. _omrs_id is always authoritative.
    if meta.get("相关知识点") and not related_tags:
        fields["相关知识点"] = extract_knowledge_tags(meta)
    if meta.get("tags"):
        tags = meta["tags"] if isinstance(meta["tags"], list) else [meta["tags"]]
        if not any(str(item).startswith("状态/") for item in tags):
            tags.insert(0, "状态/待攻克")
        fields["tags"] = tags
    fm = _format_frontmatter(fields)
    sections = _ensure_sections(body)
    normalized = f"{fm}\n\n{sections}".rstrip() + "\n"
    return normalized, normalized != content


def _format_frontmatter(fields):
    lines = ["---"]
    lines.append(f"_omrs_id: {fields['_omrs_id']}")
    lines.append(f"科目: {fields['科目']}")
    lines.append(f"分类: \"{fields['分类']}\"")
    lines.append(f"难度: {fields['难度']}")
    lines.append(f"页码: {fields['页码']}")
    tags = [tag for tag in fields.get("相关知识点", []) if str(tag).strip()]
    if tags:
        lines.append("相关知识点:")
        for tag in tags:
            clean = str(tag).strip()
            if not clean.startswith("[["):
                clean = f"[[{clean}]]"
            lines.append(f"  - \"{clean}\"")
    else:
        lines.append("相关知识点: []")
    lines.append("tags:")
    for tag in fields.get("tags") or ["状态/待攻克"]:
        lines.append(f"  - {str(tag).replace('#', '')}")
    lines.append("---")
    return "\n".join(lines)


def _ensure_sections(body):
    body = (body or "").strip()
    if not body:
        return "# 题目\n\n# 答案\n\n# 备注\n\n## 错因\n\n## 关联\n"
    required = ["# 题目", "# 答案", "# 备注"]
    for header in required:
        if header not in body:
            body = body.rstrip() + f"\n\n{header}\n"
    if "## 错因" not in body:
        body = body.rstrip() + "\n\n## 错因\n"
    if "## 关联" not in body:
        body = body.rstrip() + "\n\n## 关联\n"
    return body


def _question_payload(vault, item, meta, question_id, content):
    return {
        "question_id": question_id,
        "uid": item["uid"],
        "file_path": item["file_path"],
        "subject": meta.get("科目", item["subject"]),
        "category": extract_category(meta) or item["category"],
        "difficulty": meta.get("难度", "5"),
        "current_tag": extract_tag(meta),
        "knowledge_tags": extract_knowledge_tags(meta),
        "metadata": meta,
        "metadata_hash": metadata_hash(meta),
        "content_hash": content_hash(content),
        "archived": False,
    }


def _split_tags(value):
    return [tag for tag in (value or "").split("|") if tag]


def _atomic_write_text(path, content):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
