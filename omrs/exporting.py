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
import colorsys

from .common import (
    ATTACHMENTS_DIR,
    MASTERY_HEADERS,
    load_csv,
    is_suspended_row,
    mastery_path,
    questions_root,
    split_sections,
    extract_category,
    parse_yaml_frontmatter,
)
from .sessions import get_session


QUESTION_SECTION = "题目"
NOTES_SECTION = "备注"
ANSWER_SECTION = "答案"

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "export_templates")
_KATEX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "vendor", "katex")

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
        if not row or is_suspended_row(row):
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
                "labels": [
                    label.strip()
                    for label in str(row.get("Labels", "") or "").split("|")
                    if label.strip()
                ],
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


def _split_markdown_table_row(line):
    """拆分 Markdown 表格行，支持用反斜杠转义的竖线。"""
    source = (line or "").strip().strip("|")
    cells, current = [], []
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\" and index + 1 < len(source) and source[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def _is_markdown_table_separator(line):
    cells = _split_markdown_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _display_math_delimiter_count(line):
    """统计一行中未转义的 `$$` 分隔符数量。"""
    source = str(line or "")
    count = 0
    index = 0
    while index + 1 < len(source):
        if source[index:index + 2] == "$$" and (index == 0 or source[index - 1] != "\\"):
            count += 1
            index += 2
        else:
            index += 1
    return count


def _find_display_math_end(lines, start):
    """找到从 ``start`` 行开始的跨行 `$$...$$` 结束行。"""
    delimiters = 0
    for index in range(start, len(lines)):
        delimiters += _display_math_delimiter_count(lines[index])
        if delimiters and delimiters % 2 == 0:
            return index
    return None


def _text_to_blocks(vault, text):
    """把一段多行正文转成块列表：每个非空文字行 -> {t:'txt'}，每个嵌入图 -> {t:'img'}。
    细粒度按行成块，既保留原排版语义，也让浏览器端在双栏里填得更紧；跨行 `$$...$$`
    会先合并为一个文字块，确保完整交给 KaTeX。"""
    blocks = []
    lines = (text or "").split("\n")
    index = 0
    while index < len(lines):
        if index + 1 < len(lines) and "|" in lines[index] and _is_markdown_table_separator(lines[index + 1]):
            headers = _split_markdown_table_row(lines[index])
            index += 2
            rows = []
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                cells = _split_markdown_table_row(lines[index])
                rows.append((cells + [""] * len(headers))[:len(headers)])
                index += 1
            blocks.append({"t": "table", "headers": headers, "rows": rows})
            continue
        line = lines[index].rstrip()
        delimiter_count = _display_math_delimiter_count(line)
        if delimiter_count % 2 == 1:
            end = _find_display_math_end(lines, index)
            if end is not None:
                line = "\n".join(lines[index:end + 1]).rstrip()
                index = end + 1
            else:
                index += 1
        else:
            index += 1
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


def _normalize_question_gap_lines(value):
    """将题间空行限制在适合 A4 排版的安全范围内。"""
    try:
        return max(0, min(20, int(value)))
    except (TypeError, ValueError):
        return 0


def _normalize_a4_two_columns(value):
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _build_export_data(vault, session_id, questions, include_answers, question_gap_lines=0, a4_two_columns=True):
    today = datetime.date.today().isoformat()
    data = {
        "meta": {
            "title": "OMRS 错题复习清单",
            "sub": f"Session: {session_id}    生成日期: {today}    共 {len(questions)} 道题",
            # 供屏幕版「复制作答 JSON」回填，主程序反馈页按此 ID 关联 Session
            "session_id": session_id,
            "question_gap_lines": _normalize_question_gap_lines(question_gap_lines),
            "a4_two_columns": _normalize_a4_two_columns(a4_two_columns),
        },
        "questions": [],
        "feedback": [],
        "answers": [],
    }
    try:
        from .labels import load_labels
        label_colors = {
            item["name"]: item.get("color", "#64748b")
            for item in load_labels(vault).get("labels", [])
            if not item.get("archived")
        }
    except Exception:
        label_colors = {}
    for index, question in enumerate(questions, 1):
        data["questions"].append(
            {
                "idx": index,
                "uid": question["uid"],
                "subject": question.get("subject", ""),
                "category": question.get("category", ""),
                "difficulty": question.get("difficulty", "?"),
                "tags": question.get("tags", ""),
                "labels": _board_label_objects(question.get("labels", []), label_colors),
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


def _font_mime(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".ttf": "font/ttf",
    }.get(ext, "application/octet-stream")


def _read_katex_bundle():
    css_path = os.path.join(_KATEX_DIR, "katex.min.css")
    js_path = os.path.join(_KATEX_DIR, "katex.min.js")
    if not (os.path.isfile(css_path) and os.path.isfile(js_path)):
        return "", ""

    with open(css_path, "r", encoding="utf-8") as file:
        css = file.read()
    with open(js_path, "r", encoding="utf-8") as file:
        js = file.read()

    def inline_font(match):
        font_rel = match.group(1)
        font_path = os.path.normpath(os.path.join(_KATEX_DIR, font_rel.replace("/", os.sep)))
        font_root = os.path.join(_KATEX_DIR, "fonts") + os.sep
        if not (font_path.startswith(font_root) and os.path.isfile(font_path)):
            return match.group(0)
        with open(font_path, "rb") as file:
            encoded = base64.b64encode(file.read()).decode("ascii")
        return f"url(data:{_font_mime(font_path)};base64,{encoded})"

    css = re.sub(r"url\((?:['\"]?)(fonts/[^)'\"]+)(?:['\"]?)\)", inline_font, css)
    js = js.replace("</", "<\\/")
    return css, js


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
      <button class="share" id="copyJsonBtn">📋 复制作答 JSON（导入主程序反馈）</button>
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
    katex_css, katex_js = _read_katex_bundle()
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
        f"<style>\n{katex_css}\n</style>\n"
        f"<style>\n{css}\n</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        f"<script>\n{katex_js}\n</script>\n"
        f"<script>window.OMRS_DATA = {data_json};</script>\n"
        f"<script>\n{js}\n</script>\n"
        "</body>\n</html>\n"
    )


# --------------------------------------------------------------------------
# 对外入口
# --------------------------------------------------------------------------
def export_schedule_html(vault, uids=None, session_id="", include_answers=False, variant="a4", question_gap_lines=0, a4_two_columns=True):
    session_id, questions = _load_export_questions(vault, uids, session_id)
    data = _build_export_data(vault, session_id, questions, include_answers, question_gap_lines, a4_two_columns)
    html_text = _build_html(data, variant)
    return html_text.encode("utf-8"), session_id


def export_schedule_artifact(vault, uids=None, session_id="", export_format="a4", include_answers=False, question_gap_lines=0, a4_two_columns=True):
    """导出错题清单为自包含 HTML。

    export_format: 'a4'（打印版，默认）/ 'screen'（屏幕阅读版）。
    为兼容旧调用，'docx'/'word'/'html'/空 等一律按 A4 处理。
    返回 (bytes, session_id, filename, content_type)。
    """
    fmt = (export_format or "a4").strip().lower()
    variant = "screen" if fmt == "screen" else "a4"
    data, session_id = export_schedule_html(vault, uids, session_id, include_answers, variant, question_gap_lines, a4_two_columns)
    filename = f"OMRS-{session_id}-{variant}.html"
    return data, session_id, filename, "text/html; charset=utf-8"


# --------------------------------------------------------------------------
# 展示板导出
# --------------------------------------------------------------------------

# Board output is intentionally kept as a separate template pair so that the
# browser preview and exported file share exactly the same layout rules.

def _board_label_ink(color):
    # Match labels.js::lblInk(color, "light"): print uses a white paper
    # background, so the same-hue text is lowered until the 18% chip surface
    # reaches WCAG AA contrast.  The stored label color is never changed.
    try:
        value = color.lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            raise ValueError
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        background = tuple(round(component * .18 + 255 * .82) for component in (r, g, b))

        def luminance(rgb):
            values = []
            for component in rgb:
                value = component / 255
                values.append(value / 12.92 if value <= .03928 else ((value + .055) / 1.055) ** 2.4)
            return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]

        def contrast(rgb):
            first, second = luminance(rgb), luminance(background)
            return (max(first, second) + .05) / (min(first, second) + .05)

        hue, _lightness, saturation = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        saturation = max(saturation, .35)
        candidates = []
        lightness = .02
        while lightness <= .58:
            red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
            candidate = tuple(round(value * 255) for value in (red, green, blue))
            candidates.append(candidate)
            if contrast(candidate) >= 4.5:
                return "#{:02x}{:02x}{:02x}".format(*candidate)
            lightness += .01
        candidates.append((0, 0, 0))
        best = max(candidates, key=contrast)
        return "#{:02x}{:02x}{:02x}".format(*best)
    except Exception:
        return "#64748b"


def _board_question(vault, item):
    file_path = str(item.get("file_path") or "")
    if not file_path:
        row = next((r for r in load_csv(mastery_path(vault), MASTERY_HEADERS) if r.get("UID") == item.get("uid")), {})
        file_path = row.get("File_Path", "")
    path = os.path.join(vault, file_path.replace("\\", os.sep).replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
    sections = split_sections(content)
    meta = parse_yaml_frontmatter(content)
    return {
        "uid": item.get("uid", ""),
        "subject": meta.get("科目", item.get("subject", "")),
        "category": extract_category(meta) or item.get("category", ""),
        "difficulty": meta.get("难度", item.get("difficulty", "")),
        "question": sections.get(QUESTION_SECTION, "").strip(),
        "answer": sections.get(ANSWER_SECTION, "").strip(),
        "labels": item.get("labels") or [],
    }


def _board_text_html(text, vault=None):
    """Render board text without dropping tables or image blocks.

    Board pagination treats tables as atomic DOM nodes, just like the A4
    exporter.  Text remains escaped plain HTML; the board template deliberately
    keeps the paper layout small and quiet rather than introducing a second
    Markdown renderer.
    """
    blocks = _text_to_blocks(vault or _BOARD_VAULT, text)
    html = []
    for block in blocks:
        if block.get("t") == "img":
            image = block.get("img") or {}
            html.append(
                f'<img class="bd-img" src="{_escape_html(image.get("src", ""))}" '
                f'alt="{_escape_html(image.get("name", ""))}">'
            )
        elif block.get("t") == "table":
            headers = block.get("headers") or []
            rows = block.get("rows") or []
            head = "".join(f"<th>{_escape_html(cell)}</th>" for cell in headers)
            body = "".join(
                "<tr>" + "".join(f"<td>{_escape_html(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            html.append(
                f'<div class="bd-table-wrap"><table class="bd-table"><thead><tr>{head}</tr>'
                f"<tbody>{body}</tbody></table></div>"
            )
        else:
            html.append(f"<p>{_escape_html(block.get('text', ''))}</p>")
    return "".join(html) or "<p>（无题目内容）</p>"


def _escape_html(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _board_label_html(labels):
    # labels is a list of {name,color} or names. The exporter does not need the
    # label registry to be available: unknown names use the neutral slate color.
    result = []
    for raw in labels or []:
        if isinstance(raw, dict):
            name, color = raw.get("name", ""), raw.get("color", "#64748b")
        else:
            name, color = str(raw), "#64748b"
        if not str(name).strip():
            continue
        rgb = "100,116,139"
        try:
            hex_color = str(color).lstrip("#")
            if len(hex_color) == 3:
                hex_color = "".join(ch * 2 for ch in hex_color)
            if len(hex_color) != 6:
                raise ValueError
            rgb = ",".join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4))
        except Exception:
            pass
        result.append(
            f'<span class="lbl" style="--lrgb:{rgb};--link:{_board_label_ink(str(color))}">'
            f"{_escape_html(name)}</span>"
        )
    return "".join(result)


def _board_text_line_estimate(text, max_chars=31):
    """Estimate rendered board-text height in line units.

    The exporter deliberately does not clip正文.  This estimate is only used to
    choose a page break before the browser renders the fixed A4 sheet; images
    consume a conservative block allowance so they are not silently pushed
    outside the left column.
    """
    lines = 0
    for source in str(text or "").splitlines() or [""]:
        embeds, remaining = _extract_embeds(source)
        if remaining:
            lines += max(1, (len(remaining) + max_chars - 1) // max_chars)
        for _name, _width in embeds:
            lines += 14  # max-height: 240px at roughly 18px text line height
    return max(1, lines)


def _board_label_objects(labels, colors):
    result = []
    for name in labels or []:
        name = str(name or "").strip()
        if not name:
            continue
        color = colors.get(name, "#64748b")
        result.append({
            "name": name,
            "color": color,
            "ink": _board_label_ink(color),
        })
    return result


def export_board_html(vault, board_id, include_answers=None, page_start=1, page_end=None,
                      overrides=None):
    """Export a board as a self-contained A4 HTML document.

    Pagination is calculated for the whole board first.  ``page_start`` and
    ``page_end`` then select already-numbered pages, so printing page 3 alone
    still displays the absolute footer number ``3``.  The board template owns
    the final DOM/CSS and intentionally emits no right-column note element.
    """
    from .boards import board_items_for_export

    board, items = board_items_for_export(vault, board_id)
    settings = {**board.get("print", {}), **(overrides or {})}
    if include_answers is None:
        include_answers = settings.get("answers") == "append"

    global _BOARD_VAULT
    _BOARD_VAULT = vault
    valid_pairs = []
    for item in items:
        question = _board_question(vault, item)
        if question:
            valid_pairs.append((question, item))
    if not valid_pairs:
        raise RuntimeError("展示板没有可导出的题目")

    try:
        from .labels import load_labels
        label_colors = {
            item["name"]: item.get("color", "#64748b")
            for item in load_labels(vault).get("labels", [])
            if not item.get("archived")
        }
    except Exception:
        label_colors = {}

    try:
        ratio = max(.30, min(.55, float(settings.get("note_ratio", .42))))
    except (TypeError, ValueError):
        ratio = .42
    try:
        gap_lines = max(0, min(24, int(settings.get("gap_lines", 6))))
    except (TypeError, ValueError):
        gap_lines = 6
    try:
        binding_mm = max(10, min(40, int(settings.get("binding_mm", 22))))
    except (TypeError, ValueError):
        binding_mm = 22

    # The left content column is about 53 lines high after the fixed header.
    # Keep a small safety margin for font metrics and never cap a long question:
    # a capped estimate would make a long block overflow instead of moving it.
    page_budget = 49
    pages, current, used = [], [], 0
    for index, (question, item) in enumerate(valid_pairs, 1):
        extra = max(0, min(24, int(item.get("extra_gap_lines", 0) or 0)))
        height = _board_text_line_estimate(question.get("question", "")) + 2 + gap_lines + extra
        if current and used + height > page_budget:
            pages.append(current)
            current, used = [], 0
        current.append((index, question, item))
        used += height
    if current:
        pages.append(current)

    answer_page = None
    if include_answers:
        answer_rows = []
        for index, (question, _item) in enumerate(valid_pairs, 1):
            answer_rows.append({
                "index": index,
                "uid": question["uid"],
                "html": _board_text_html(question.get("answer", ""), vault),
            })
        answer_page = {
            "number": len(pages) + 1,
            "binding_px": binding_mm * 3.7795,
            "note_ratio": ratio,
            "answers": answer_rows,
        }

    total_pages = len(pages) + (1 if answer_page else 0)
    try:
        start = max(1, int(page_start or 1))
    except (TypeError, ValueError):
        start = 1
    open_end = page_end in (None, "")
    if open_end:
        end = total_pages
    else:
        try:
            end = int(page_end)
        except (TypeError, ValueError):
            end = total_pages
        if end < start:
            raise ValueError("打印范围起始页不能大于结束页")
        end = min(total_pages, end)
    if start > total_pages or end < start:
        raise RuntimeError("打印范围没有可导出的页")

    all_pages = []
    selected_pages = []
    for page_number, rows in enumerate(pages, 1):
        rendered_questions = []
        for index, question, item in rows:
            labels = _board_label_objects(
                question.get("labels", []) if settings.get("show_labels", True) else [],
                label_colors,
            )
            meta = ""
            if settings.get("show_meta", True):
                meta = (
                    f"{question.get('subject', '')} · {question.get('category', '')} · "
                    f"难度 {question.get('difficulty', '')}"
                )
            rendered_questions.append({
                "index": index,
                "uid": question["uid"],
                "labels": labels,
                "meta": meta,
                "html": _board_text_html(question.get("question", ""), vault),
                "gap_px": gap_lines * 18,
                "extra_gap_px": max(0, min(24, int(item.get("extra_gap_lines", 0) or 0))) * 18,
            })
        rendered_page = {
            "number": page_number,
            "binding_px": binding_mm * 3.7795,
            "note_ratio": ratio,
            "questions": rendered_questions,
        }
        all_pages.append(rendered_page)
        if start <= page_number <= end:
            selected_pages.append(rendered_page)
    if answer_page and start <= answer_page["number"] <= end:
        selected_pages.append(answer_page)

    all_questions = [
        question
        for page in all_pages
        for question in page["questions"]
    ]
    data = {
        "pages": selected_pages,
        # ``all_questions`` lets the browser reflow with real font/image
        # geometry before applying the requested absolute page range.  The
        # legacy ``pages`` field remains for consumers that only inspect the
        # server estimate.
        "all_questions": all_questions,
        "answers": answer_page["answers"] if answer_page else [],
        "binding_px": binding_mm * 3.7795,
        "binding_marks": settings.get("binding_marks", "none")
        if settings.get("binding_marks") in {"none", "3hole", "26hole"}
        else "none",
        "note_ratio": ratio,
        "include_answers": bool(answer_page),
        "board_id": str(board.get("id") or board_id),
        "page_start": start,
        "page_end": end,
        "open_end": open_end,
        "estimated_total_pages": total_pages,
        "estimated_selected_page_count": len(selected_pages),
    }
    css = _read_template("board.css")
    js = _read_template("board.js")
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<meta name=\"omrs-page-count\" content=\"{len(selected_pages)}\">"
        f"<meta name=\"omrs-estimated-page-count\" content=\"{len(selected_pages)}\">"
        f"<meta name=\"omrs-total-page-count\" content=\"{total_pages}\">"
        f"<meta name=\"omrs-page-start\" content=\"{start}\">"
        f"<meta name=\"omrs-page-end\" content=\"{end}\">"
        f"<meta name=\"omrs-open-end\" content=\"{'1' if open_end else '0'}\">"
        "<title>错题集</title><style>" + css + "</style></head><body>"
        '<div class="toolbar">展示板打印预览<button onclick="window.print()">打印 / 导出 PDF</button></div>'
        '<div id="stage"></div>'
        f"<script>window.OMRS_DATA = {data_json};</script>"
        "<script>" + js + "</script></body></html>"
    )
    return html.encode("utf-8")

_BOARD_VAULT = ""
