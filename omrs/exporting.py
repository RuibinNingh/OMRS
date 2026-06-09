"""错题导出 —— 生成自包含 HTML（A4 打印版 / 屏幕阅读版）。

设计要点：版面与长图切片**全部交给浏览器**完成（浏览器既是排版引擎、又是用户最终查看/
打印的引擎，所见即所打印，无需在 Python 端预测版面，也没有跨渲染器保真度差）。因此本模块：
  - 仍负责：从题库读题、解析 Markdown 分节、抽取图片嵌入、把图片读成 base64 内联；
  - 不再负责：OOXML 生成、OMML 公式、像素级长图切片（这些已下沉到浏览器端模板）。

附带收益：移除了对 Pillow 的依赖，导出回到“纯标准库、零第三方依赖”。
"""

import base64
import datetime
import json
import os
import re
import struct
import urllib.parse

from .common import (
    ATTACHMENTS_DIR,
    MASTERY_HEADERS,
    load_csv,
    mastery_path,
    questions_root,
    split_sections,
)
from .sessions import get_session


QUESTION_SECTION = "题目"
NOTES_SECTION = "备注"
ANSWER_SECTION = "答案"

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "export_templates")

_EMBED_WIKI_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|(\d+))?\]\]")
_EMBED_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# --------------------------------------------------------------------------
# 图片尺寸解析（纯标准库，不依赖 Pillow）+ 查找 + 读取
# --------------------------------------------------------------------------
def _png_size(data):
    if len(data) < 24:
        return None
    return struct.unpack(">II", data[16:24])


def _jpeg_size(data):
    size = len(data)
    index = 2
    while index < size - 9:
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if marker == 0xDA:
            return None
        seg_len = struct.unpack(">H", data[index + 2:index + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if index + 9 <= size:
                height, width = struct.unpack(">HH", data[index + 5:index + 9])
                return (width, height)
        index += 2 + seg_len
    return None


def _gif_size(data):
    if len(data) < 10:
        return None
    return struct.unpack("<HH", data[6:10])


def _read_image_info(path):
    with open(path, "rb") as file:
        data = file.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        wh = _png_size(data)
        if wh:
            return data, wh[0], wh[1], "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        wh = _jpeg_size(data)
        if wh:
            return data, wh[0], wh[1], "jpeg", "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        wh = _gif_size(data)
        if wh:
            return data, wh[0], wh[1], "gif", "image/gif"
    raise ValueError(f"不支持的图片格式: {os.path.basename(path)}")


def _find_image(vault, name):
    if not name:
        return None
    name = name.strip()
    try:
        name = urllib.parse.unquote(name)
    except Exception:
        pass

    if os.path.isabs(name) and os.path.isfile(name):
        return name
    direct = os.path.join(questions_root(vault), ATTACHMENTS_DIR, name)
    if os.path.isfile(direct):
        return direct
    rel = os.path.join(vault, name)
    if os.path.isfile(rel):
        return rel

    attachment_root = os.path.join(questions_root(vault), ATTACHMENTS_DIR)
    basename = os.path.basename(name)
    if os.path.isdir(attachment_root):
        for root, _, files in os.walk(attachment_root):
            if basename in files:
                return os.path.join(root, basename)
    return None


def _extract_embeds(line):
    embeds = []

    def _wiki(match):
        embeds.append((match.group(1), match.group(2)))
        return ""

    def _md(match):
        embeds.append((match.group(2), None))
        return ""

    stripped = _EMBED_WIKI_RE.sub(_wiki, line)
    stripped = _EMBED_MD_RE.sub(_md, stripped)
    return embeds, stripped.strip()


# --------------------------------------------------------------------------
# 题库读取与字段解析（与旧实现一致，未改动）
# --------------------------------------------------------------------------
def _format_export_tags(row):
    tags = []
    seen = set()
    status = (row.get("Current_Tag", "") or "").strip().lstrip("#")
    if status:
        tags.append(status)
        seen.add(status)
    for tag in (row.get("Knowledge_Tags", "") or "").split("|"):
        tag = tag.strip()
        if not tag:
            continue
        display = tag if tag.startswith("知识点/") else f"知识点/{tag}"
        if display in seen:
            continue
        tags.append(display)
        seen.add(display)
    return " · ".join(tags)


def _parse_notes_subsections(notes_text):
    """把 # 备注 段解析为 {错因, 关联} 字典。"""
    if not notes_text:
        return {}
    result = {}
    parts = re.split(r"^##\s+", notes_text, flags=re.MULTILINE)
    for part in parts[1:]:
        lines = part.split("\n", 1)
        key = lines[0].strip()
        value = lines[1].strip() if len(lines) > 1 else ""
        result[key] = value
    return result


def _normalize_export_request(session_id, uids):
    clean_uids = []
    seen = set()
    for uid in uids or []:
        uid = (uid or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        clean_uids.append(uid)
    session_id = session_id or f"TMP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    return session_id, clean_uids


def _load_export_questions(vault, uids=None, session_id=""):
    session = get_session(vault, session_id) if session_id else None
    if session:
        uids = [item["UID"] for item in session["items"]]
    session_id, uids = _normalize_export_request(session_id, uids)
    if not uids:
        raise RuntimeError("export: 既没有有效的 session_id 也没有 uids")

    rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
    row_map = {row["UID"]: row for row in rows}

    questions = []
    for uid in uids:
        row = row_map.get(uid)
        if not row:
            continue
        file_path = os.path.join(vault, row.get("File_Path", ""))
        if not os.path.exists(file_path):
            continue
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        sections = split_sections(content)
        questions.append(
            {
                "uid": uid,
                "subject": row.get("Subject", ""),
                "category": row.get("Category", ""),
                "difficulty": row.get("Difficulty", "?"),
                "tags": _format_export_tags(row),
                "question": sections.get(QUESTION_SECTION, "").strip(),
                "notes": sections.get(NOTES_SECTION, "").strip(),
                "answer": sections.get(ANSWER_SECTION, "").strip(),
            }
        )

    if not questions:
        raise RuntimeError("没有可导出的题目(UID 均未找到或文件缺失)")
    return session_id, questions


# --------------------------------------------------------------------------
# Markdown 正文 -> 结构化内容块（文字 / 内联图片 base64）
# --------------------------------------------------------------------------
def _img_payload(vault, name):
    """查找并把图片读成 {src: data-uri, w, h}；找不到/读失败返回 None。"""
    path = _find_image(vault, name)
    if not path:
        return None
    try:
        data, width, height, _ext, content_type = _read_image_info(path)
    except Exception:
        return None
    b64 = base64.b64encode(data).decode("ascii")
    return {"src": f"data:{content_type};base64,{b64}", "w": width, "h": height}


def _text_to_blocks(vault, text):
    """把一段多行正文转成块列表：每个非空文字行 -> {t:'txt'}，每个嵌入图 -> {t:'img'}。
    细粒度按行成块，既保留原排版语义，也让浏览器端在双栏里填得更紧。"""
    blocks = []
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        embeds, remaining = _extract_embeds(line)
        if remaining:
            blocks.append({"t": "txt", "text": remaining})
        for name, _width in embeds:
            payload = _img_payload(vault, name)
            if payload:
                blocks.append({"t": "img", "img": payload})
            else:
                blocks.append({"t": "txt", "text": f"[图片缺失: {name}]"})
    return blocks


def _build_export_data(vault, session_id, questions, include_answers):
    today = datetime.date.today().isoformat()
    data = {
        "meta": {
            "title": "OMRS 错题复习清单",
            "sub": f"Session: {session_id}    生成日期: {today}    共 {len(questions)} 道题",
        },
        "questions": [],
        "feedback": [],
        "answers": [],
    }
    for index, question in enumerate(questions, 1):
        data["questions"].append(
            {
                "idx": index,
                "uid": question["uid"],
                "subject": question.get("subject", ""),
                "category": question.get("category", ""),
                "difficulty": question.get("difficulty", "?"),
                "tags": question.get("tags", ""),
                "blocks": _text_to_blocks(vault, question.get("question", "") or "(无题目内容)"),
                "notes": _parse_notes_subsections(question.get("notes", "")) or {},
            }
        )
        data["feedback"].append({"uid": question["uid"]})

    if include_answers:
        for index, question in enumerate(questions, 1):
            data["answers"].append(
                {
                    "idx": index,
                    "uid": question["uid"],
                    "blocks": _text_to_blocks(vault, question.get("answer", "").strip()),
                }
            )
    return data


# --------------------------------------------------------------------------
# HTML 组装（读取 export_templates/ 下的 CSS+JS，内联成单文件）
# --------------------------------------------------------------------------
def _read_template(filename):
    with open(os.path.join(_TEMPLATE_DIR, filename), "r", encoding="utf-8") as file:
        return file.read()


_A4_BODY = """<div id="bar">
  <strong>OMRS · A4 打印版</strong>
  <button id="btnPrint">打印 / 导出 PDF</button>
  <label><input type="checkbox" id="btnDebug"> 显示切口</label>
  <span class="stat" id="stat">排版中…</span>
</div>
<div id="stage"></div>"""

_SCREEN_BODY = """<div id="bar">
  <div class="brand">
    <span class="mark">O</span>
    <span class="ttl">错题复习<small id="barSub">加载中…</small></span>
  </div>
  <span class="spacer"></span>
  <div class="ring" title="作答进度">
    <svg width="38" height="38"><circle class="track" cx="19" cy="19" r="16" fill="none" stroke-width="3"></circle><circle class="fill" cx="19" cy="19" r="16" fill="none" stroke-width="3" stroke-linecap="round" stroke-dasharray="100" stroke-dashoffset="100"></circle></svg>
    <span class="pct">0%</span>
  </div>
  <button class="icon-btn" id="progBtn" title="作答情况" aria-label="作答情况">☰</button>
</div>

<div id="stage">
  <div id="track"></div>
</div>

<div id="nav">
  <button class="nbtn" id="prevBtn" title="上一题" aria-label="上一题">‹</button>
  <button class="nbtn" id="nextNavBtn" title="下一题" aria-label="下一题">›</button>
  <span class="mid" id="navMid"></span>
  <button class="next" id="nextBtn"><span>下一题</span><span>→</span></button>
</div>

<div id="sheet">
  <div class="scrim"></div>
  <div class="panel">
    <div class="grip"></div>
    <div class="sh-head">
      <h2>作答情况</h2>
      <span class="sh-close" id="sheetClose" aria-label="关闭">✕</span>
    </div>
    <div class="stats">
      <div class="stat"><div class="v" id="st-done">0</div><div class="k">已作答</div></div>
      <div class="stat g"><div class="v" id="st-right">0</div><div class="k">答对</div></div>
      <div class="stat r"><div class="v" id="st-wrong">0</div><div class="k">答错</div></div>
    </div>
    <div class="subj-break" id="subjBreak"></div>
    <div class="rubric-guide">
      <div class="rg-ttl">评分标准 · 满分 10 分</div>
      <div class="rg-grid">
        <div class="rg-cell ok"><b>答对 · 7–10 分</b><span>思路与过程清晰，真正掌握</span></div>
        <div class="rg-cell warm"><b>答对 · 0–6 分</b><span>答案对但不熟，靠印象或猜中</span></div>
        <div class="rg-cell warm"><b>答错 · 7–10 分</b><span>思路基本对，栽在细节/计算</span></div>
        <div class="rg-cell bad"><b>答错 · 0–6 分</b><span>关键步骤没掌握，需重点重练</span></div>
      </div>
    </div>
    <div class="jump">
      <div class="j-ttl">跳转到题目</div>
      <div class="grid" id="grid"></div>
    </div>
    <div class="sh-actions">
      <button id="jumpFirstUngraded">跳到第一道未判定</button>
      <button class="reset" id="resetBtn">清空记录</button>
    </div>
    <div class="saved-tag" id="savedTag">进度自动保存在本设备</div>
  </div>
</div>

<div id="lightbox"><img alt=""></div>
<div id="toast"></div>"""


def _build_html(data, variant):
    variant = "screen" if variant == "screen" else "a4"
    css = _read_template(f"{variant}.css")
    js = _read_template(f"{variant}.js")
    body = _SCREEN_BODY if variant == "screen" else _A4_BODY
    title = "OMRS 错题本 · 屏幕版" if variant == "screen" else "OMRS 错题本 · A4 打印版"

    data_json = json.dumps(data, ensure_ascii=False)
    data_json = data_json.replace("</", "<\\/")  # 防止 </script> 提前闭合脚本

    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{css}\n</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        f"<script>window.OMRS_DATA = {data_json};</script>\n"
        f"<script>\n{js}\n</script>\n"
        "</body>\n</html>\n"
    )


# --------------------------------------------------------------------------
# 对外入口
# --------------------------------------------------------------------------
def export_schedule_html(vault, uids=None, session_id="", include_answers=False, variant="a4"):
    session_id, questions = _load_export_questions(vault, uids, session_id)
    data = _build_export_data(vault, session_id, questions, include_answers)
    html_text = _build_html(data, variant)
    return html_text.encode("utf-8"), session_id


def export_schedule_artifact(vault, uids=None, session_id="", export_format="a4", include_answers=False):
    """导出错题清单为自包含 HTML。

    export_format: 'a4'（打印版，默认）/ 'screen'（屏幕阅读版）。
    为兼容旧调用，'docx'/'word'/'html'/空 等一律按 A4 处理。
    返回 (bytes, session_id, filename, content_type)。
    """
    fmt = (export_format or "a4").strip().lower()
    variant = "screen" if fmt == "screen" else "a4"
    data, session_id = export_schedule_html(vault, uids, session_id, include_answers, variant)
    filename = f"OMRS-{session_id}-{variant}.html"
    return data, session_id, filename, "text/html; charset=utf-8"
