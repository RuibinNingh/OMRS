import base64
import datetime
import hashlib
import json
import os
import re
import sqlite3

from .common import ATTACHMENTS_DIR, questions_root
from .common import extract_labels
from .ledger import append_commit, reserve_operation_id
from .migration import ensure_ledger_bootstrap
from .projections import rebuild_projection
from .workspace_sync import content_hash, metadata_hash, update_fingerprints
from .path_safety import safe_question_directory, safe_question_path


def _next_uid(qroot, category):
    pattern = re.compile(rf"^{re.escape(category)}(\d+)\.md$")
    used = set()
    for root, dirs, files in os.walk(qroot):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for fname in files:
            match = pattern.match(fname)
            if match:
                used.add(int(match.group(1)))
    drafts_db = os.path.join(qroot, ".omrs", "drafts", "drafts.db")
    if os.path.isfile(drafts_db):
        db = sqlite3.connect(f"file:{drafts_db}?mode=ro", uri=True)
        try:
            for (uid,) in db.execute("SELECT uid FROM commit_operations"):
                match = re.fullmatch(rf"{re.escape(category)}(\d+)", uid)
                if match:
                    used.add(int(match.group(1)))
        except sqlite3.OperationalError:
            pass
        finally:
            db.close()
    next_num = 1
    while next_num in used:
        next_num += 1
    return f"{category}{next_num}"


_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
}

# 与 /api/image 与导出读取器（_read_image_info）支持的格式保持一致；
# WebP/BMP/SVG 等即使落盘也无法被图片服务读取，录入时直接拒绝。
_SUPPORTED_IMAGE_MIMES = set(_MIME_EXT)


def _ext_from_mime(mime):
    return _MIME_EXT.get((mime or "").strip().lower(), "png")


def _save_pasted_images(vault, uid, question_id, images, suffix, strict=False, reusable=False,
                        start_index=0):
    """把前端粘贴/选择的图片（data URL 或裸 base64）存到 错题/附件/。

    suffix 用于区分题目图/答案图（'q' / 'a'），文件名形如 `<uid>-q-1.png`，
    可被 `/api/image?name=` 命中，并以 `![[名]]` 嵌入。返回 (文件名列表, 完整路径列表)。
    无效项跳过。
    """
    if not images:
        return [], []
    attach_dir = os.path.join(questions_root(vault), ATTACHMENTS_DIR)
    os.makedirs(attach_dir, exist_ok=True)
    names, paths = [], []
    index = start_index
    for image in images:
        data_url = image.get("data") if isinstance(image, dict) else image
        if not data_url or not isinstance(data_url, str):
            if strict:
                raise ValueError("图片数据缺失")
            continue
        match = re.match(r"^data:([^;,]+);base64,(.*)$", data_url, re.DOTALL)
        if match:
            mime, b64 = match.group(1), match.group(2)
        else:
            mime, b64 = "image/png", data_url
        if (mime or "").strip().lower() not in _SUPPORTED_IMAGE_MIMES:
            raise ValueError(f"不支持的图片格式 {mime or '未知'}（仅支持 PNG/JPEG/GIF）")
        try:
            raw = base64.b64decode(b64, validate=strict)
        except Exception:
            if strict:
                raise ValueError("图片 base64 不合法")
            continue
        if not raw:
            if strict:
                raise ValueError("图片数据为空")
            continue
        index += 1
        ext = _ext_from_mime(mime)
        candidate = index
        short_id = ((question_id or "").replace("OP-", "") if reusable else
                    (question_id or "").replace("OP-", "")[-4:]) or "new"
        name = f"{uid}-{short_id}-{suffix}-{candidate}.{ext}"
        full = os.path.join(attach_dir, name)
        while os.path.exists(full) and not reusable:
            candidate += 1
            name = f"{uid}-{short_id}-{suffix}-{candidate}.{ext}"
            full = os.path.join(attach_dir, name)
        if os.path.exists(full) and reusable:
            with open(full, "rb") as file:
                if file.read() != raw:
                    raise ValueError(f"附件已有不同内容，不能覆盖：{name}")
        else:
            with open(full, "wb") as file:
                file.write(raw)
        names.append(name)
        paths.append(full)
    return names, paths


def _section_body(text, image_names):
    """把文本与图片嵌入拼成一个 section 的正文。两者皆空时返回空串。"""
    parts = []
    if text and text.strip():
        parts.append(text.strip())
    if image_names:
        parts.append("\n".join(f"![[{name}]]" for name in image_names))
    return "\n\n".join(parts)


def _build_markdown(question_id, subject, category, difficulty, today, related_tags,
                    question_text, answer_text, cause, q_images, a_images, labels=None,
                    ordered_blocks=None):
    related_lines = ["相关知识点: []"]
    if related_tags:
        lines = [f'  - "[[{tag.strip()}]]"' for tag in related_tags if str(tag).strip()]
        if lines:
            related_lines = ["相关知识点:"] + lines
    related_section = "\n".join(related_lines)
    label_values = [str(label).strip() for label in (labels or []) if str(label).strip()]
    label_section = "标记: []"
    if label_values:
        label_section = "标记:\n" + "\n".join(
            f'  - "{label.replace(chr(34), chr(92) + chr(34))}"' for label in label_values
        )

    if ordered_blocks is None:
        question_body = _section_body(question_text, q_images) or "（请在 Obsidian 中编辑此题目内容）"
        answer_body = _section_body(answer_text, a_images)
    else:
        def section_body(section):
            return "\n\n".join((b["text"].strip() if b["kind"] == "text" else f"![[{b['image_name']}]]")
                                for b in ordered_blocks if b["section"] == section)
        question_body = section_body("题目") or "（请在 Obsidian 中编辑此题目内容）"
        answer_body = section_body("答案")

    # 备注区：错因写入 ## 错因（导出 Word 会带上），保留 ## 关联 子标题供 Obsidian 编辑
    cause_clean = cause.strip() if cause else ""
    notes_body = f"## 错因\n{cause_clean}\n\n## 关联"

    return f"""---
_omrs_id: {question_id}
科目: {subject}
分类: "[[{category}]]"
难度: {difficulty}
{related_section}
{label_section}
tags:
  - 状态/待攻克
录入日期: {today}
---

# 题目
{question_body}

# 备注
{notes_body}

# 答案
{answer_body}

# 历史
"""


def create_question(vault, subject, category, difficulty, related_tags=None,
                    question_text="", answer_text="", cause="",
                    question_images=None, answer_images=None, labels=None,
                    ordered_blocks=None, draft_origin=None, reserved_identity=None, actor="api"):
    category_dir, subject, category = safe_question_directory(vault, subject, category)
    if reserved_identity:
        draft_id = (draft_origin or {}).get("draft_id")
        db_path = os.path.join(questions_root(vault), ".omrs", "drafts", "drafts.db")
        op_db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            op = op_db.execute("SELECT uid,question_id,file_path FROM commit_operations WHERE draft_id=?",
                               (draft_id,)).fetchone()
        finally:
            op_db.close()
        expected = (reserved_identity.get("uid"), reserved_identity.get("question_id"),
                    os.path.relpath(os.path.join(category_dir, f"{reserved_identity.get('uid')}.md"), vault))
        if op != expected:
            raise ValueError("草稿入库身份记录不匹配")
    ensure_ledger_bootstrap(vault)
    qroot = questions_root(vault)
    os.makedirs(category_dir, exist_ok=True)

    subject_anchor = os.path.join(qroot, subject, f"{subject}.md")
    safe_question_path(vault, subject_anchor)
    if not os.path.exists(subject_anchor):
        with open(subject_anchor, "w", encoding="utf-8") as file:
            file.write(f"# {subject}\n")

    category_anchor = os.path.join(category_dir, f"{category}.md")
    safe_question_path(vault, category_anchor)
    is_new_category = not os.path.exists(category_anchor)
    if is_new_category:
        with open(category_anchor, "w", encoding="utf-8") as file:
            file.write(f"# {category}\n")
        with open(subject_anchor, "r", encoding="utf-8") as file:
            anchor_content = file.read()
        link = f"[[{category}]]"
        if link not in anchor_content:
            anchor_content = anchor_content.rstrip() + f"\n- {link}\n"
            with open(subject_anchor, "w", encoding="utf-8") as file:
                file.write(anchor_content)

    uid = reserved_identity["uid"] if reserved_identity else _next_uid(qroot, category)
    question_id = reserved_identity["question_id"] if reserved_identity else reserve_operation_id(vault)
    filepath = os.path.join(category_dir, f"{uid}.md")
    safe_question_path(vault, filepath)

    today = reserved_identity.get("today") if reserved_identity else datetime.date.today().isoformat()

    # 先落地图片（命名用 uid + q/a 区分），失败的图片会被跳过
    if ordered_blocks is not None:
        q_names, a_names, q_paths, a_paths, rendered_blocks = [], [], [], [], []
        for block in ordered_blocks:
            if block["kind"] == "text":
                rendered_blocks.append(block)
                continue
            suffix = "q" if block["section"] == "题目" else "a"
            names, paths = _save_pasted_images(vault, uid, question_id, [block["data"]], suffix,
                                               strict=True, reusable=bool(reserved_identity),
                                               start_index=len(q_names if suffix == "q" else a_names))
            (q_names if suffix == "q" else a_names).extend(names)
            (q_paths if suffix == "q" else a_paths).extend(paths)
            rendered_blocks.append({**block, "image_name": names[0]})
    else:
        q_names, q_paths = _save_pasted_images(vault, uid, question_id, question_images, "q")
        a_names, a_paths = _save_pasted_images(vault, uid, question_id, answer_images, "a")
        rendered_blocks = None

    content = _build_markdown(
        question_id, subject, category, difficulty, today, related_tags or [],
        question_text, answer_text, cause, q_names, a_names,
        labels=labels or [], ordered_blocks=rendered_blocks,
    )

    if reserved_identity:
        artifact_hashes = {}
        for path in q_paths + a_paths:
            with open(path, "rb") as file:
                artifact_hashes[os.path.relpath(path, vault)] = hashlib.sha256(file.read()).hexdigest()
        artifact_hashes[os.path.relpath(filepath, vault)] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        op_db = sqlite3.connect(db_path)
        try:
            op_db.execute("UPDATE commit_operations SET artifacts_json=? WHERE draft_id=? AND question_id=?",
                          (json.dumps(artifact_hashes, ensure_ascii=False), draft_id, question_id))
            op_db.commit()
        finally:
            op_db.close()

    if reserved_identity and os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as file:
            if file.read() != content:
                raise ValueError(f"题目文件已有不同内容，不能覆盖：{filepath}")
    else:
        _atomic_write_text(filepath, content)

    try:
        relpath = os.path.relpath(filepath, vault)
        question = {
            "question_id": question_id,
            "uid": uid,
            "file_path": relpath,
            "subject": subject,
            "category": category,
            "difficulty": difficulty,
            "current_tag": "#状态/待攻克",
            "knowledge_tags": related_tags or [],
            "labels": labels or [],
            "metadata": {
                "_omrs_id": question_id,
                "科目": subject,
                "分类": category,
                "难度": str(difficulty),
                "相关知识点": related_tags or [],
                "标记": labels or [],
                "tags": ["状态/待攻克"],
            },
            "metadata_hash": metadata_hash({
                "_omrs_id": question_id,
                "科目": subject,
                "分类": category,
                "难度": str(difficulty),
                "相关知识点": related_tags or [],
                "标记": labels or [],
                "tags": ["状态/待攻克"],
            }),
            "content_hash": content_hash(content),
            "archived": False,
        }
        payload = {"question": question}
        if draft_origin:
            payload["_draft"] = dict(draft_origin)
        append_commit(vault, actor, "question.create", f"创建题目 {uid}", payload, blobs=[content])
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
    except Exception:
        # Ledger 提交失败时，刚写出的 Markdown 可能是正文唯一副本；附件也要随正文保留。
        # 下次扫描可按 _omrs_id 将文件入账，草稿重试仍使用预留身份核对内容。
        raise

    all_images = q_names + a_names
    has_content = bool((question_text and question_text.strip()) or all_images or
                       (rendered_blocks and any(b["kind"] == "text" for b in rendered_blocks))
                       or (answer_text and answer_text.strip()) or (cause and cause.strip()))
    if has_content:
        message = f"已创建 {uid}（含题目内容{'/图片' if all_images else ''}）"
    else:
        message = f"已创建 {uid}，请在 Obsidian 打开编辑题目内容"
    return {
        "uid": uid,
        "question_id": question_id,
        "file_path": relpath,
        "images": all_images,
        "question_images": q_names,
        "answer_images": a_names,
        "message": message,
    }


def _atomic_write_text(path, content):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)
