import base64
import datetime
import os
import re

from .common import ATTACHMENTS_DIR, questions_root
from .indexing import build_index


def _next_uid(qroot, category):
    pattern = re.compile(rf"^{re.escape(category)}(\d+)\.md$")
    next_num = 1
    for root, dirs, files in os.walk(qroot):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        for fname in files:
            match = pattern.match(fname)
            if match:
                next_num = max(next_num, int(match.group(1)) + 1)
    return f"{category}{next_num}"


_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}


def _ext_from_mime(mime):
    return _MIME_EXT.get((mime or "").strip().lower(), "png")


def _save_pasted_images(vault, uid, images, suffix):
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
    index = 0
    for image in images:
        data_url = image.get("data") if isinstance(image, dict) else image
        if not data_url or not isinstance(data_url, str):
            continue
        match = re.match(r"^data:([^;,]+);base64,(.*)$", data_url, re.DOTALL)
        if match:
            mime, b64 = match.group(1), match.group(2)
        else:
            mime, b64 = "image/png", data_url
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception:
            continue
        if not raw:
            continue
        index += 1
        ext = _ext_from_mime(mime)
        candidate = index
        name = f"{uid}-{suffix}-{candidate}.{ext}"
        full = os.path.join(attach_dir, name)
        while os.path.exists(full):
            candidate += 1
            name = f"{uid}-{suffix}-{candidate}.{ext}"
            full = os.path.join(attach_dir, name)
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


def _build_markdown(subject, category, difficulty, today, note, related_tags,
                    question_text, answer_text, cause, q_images, a_images):
    related_section = ""
    if related_tags:
        lines = "\n".join(
            f'  - "[[{tag.strip()}]]"' for tag in related_tags if str(tag).strip()
        )
        if lines:
            related_section = f"\n相关知识点:\n{lines}"

    page_line = ""
    if note and str(note).strip():
        page_line = f"\n页码: {str(note).strip()}"

    question_body = _section_body(question_text, q_images) or "（请在 Obsidian 中编辑此题目内容）"
    answer_body = _section_body(answer_text, a_images)

    # 备注区：错因写入 ## 错因（导出 Word 会带上），保留 ## 关联 子标题供 Obsidian 编辑
    cause_clean = cause.strip() if cause else ""
    notes_body = f"## 错因\n{cause_clean}\n\n## 关联"

    return f"""---
科目: {subject}
tags:
  - 状态/待攻克
分类: "[[{category}]]"
难度: {difficulty}
录入日期: {today}{page_line}{related_section}
---

# 题目
{question_body}

# 备注
{notes_body}

# 答案
{answer_body}

# 历史
"""


def create_question(vault, subject, category, difficulty, note="", related_tags=None,
                    question_text="", answer_text="", cause="",
                    question_images=None, answer_images=None):
    qroot = questions_root(vault)
    category_dir = os.path.join(qroot, subject, category)
    os.makedirs(category_dir, exist_ok=True)

    subject_anchor = os.path.join(qroot, subject, f"{subject}.md")
    if not os.path.exists(subject_anchor):
        with open(subject_anchor, "w", encoding="utf-8") as file:
            file.write(f"# {subject}\n")

    category_anchor = os.path.join(category_dir, f"{category}.md")
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

    uid = _next_uid(qroot, category)
    filepath = os.path.join(category_dir, f"{uid}.md")

    today = datetime.date.today().isoformat()

    # 先落地图片（命名用 uid + q/a 区分），失败的图片会被跳过
    q_names, q_paths = _save_pasted_images(vault, uid, question_images, "q")
    a_names, a_paths = _save_pasted_images(vault, uid, answer_images, "a")

    content = _build_markdown(
        subject, category, difficulty, today, note, related_tags or [],
        question_text, answer_text, cause, q_names, a_names,
    )

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

    try:
        build_index(vault)
    except Exception:
        # 回滚：删掉本次新建的 md 与刚保存的图片，避免留下半成品
        if os.path.exists(filepath):
            os.remove(filepath)
        for path in q_paths + a_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        raise

    relpath = os.path.relpath(filepath, vault)
    all_images = q_names + a_names
    has_content = bool((question_text and question_text.strip()) or all_images
                       or (answer_text and answer_text.strip()) or (cause and cause.strip()))
    if has_content:
        message = f"已创建 {uid}（含题目内容{'/图片' if all_images else ''}）"
    else:
        message = f"已创建 {uid}，请在 Obsidian 打开编辑题目内容"
    return {
        "uid": uid,
        "file_path": relpath,
        "images": all_images,
        "question_images": q_names,
        "answer_images": a_names,
        "message": message,
    }
