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
# 展示板导出（左题右空 · 支持「只打印新增」）
# --------------------------------------------------------------------------
# 版面与分页全部交给浏览器端模板 board.js（与 A4 引擎同一套测量 / 切片思路）；
# 这里只负责取题、分块、内联图片与颜色，并把版面设置与纸面记录一起交给浏览器。

BOARD_TITLE = "错题集"


def _board_label_ink(color):
    """打印用文字色：同色相压暗到与 18% 淡底达到 WCAG AA 对比度（与 labels.js::lblInk 同算法）。"""
    try:
        value = str(color or "").lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            raise ValueError
        r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        background = tuple(round(component * .18 + 255 * .82) for component in (r, g, b))

        def luminance(rgb):
            values = []
            for component in rgb:
                channel = component / 255
                values.append(channel / 12.92 if channel <= .03928 else ((channel + .055) / 1.055) ** 2.4)
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
            candidate = tuple(round(v * 255) for v in (red, green, blue))
            candidates.append(candidate)
            if contrast(candidate) >= 4.5:
                return "#{:02x}{:02x}{:02x}".format(*candidate)
            lightness += .01
        candidates.append((0, 0, 0))
        best = max(candidates, key=contrast)
        return "#{:02x}{:02x}{:02x}".format(*best)
    except Exception:
        return "#475569"


def _board_label_objects(labels, colors):
    result = []
    for name in labels or []:
        name = str(name or "").strip()
        if not name:
            continue
        color = colors.get(name, "#64748b")
        result.append({"name": name, "color": color, "ink": _board_label_ink(color)})
    return result


def _label_color_map(vault):
    try:
        from .labels import load_labels
        return {
            item["name"]: item.get("color", "#64748b")
            for item in load_labels(vault).get("labels", [])
            if not item.get("archived")
        }
    except Exception:
        return {}


def _board_read_question(vault, item):
    """读取展示板条目对应的题目文件，返回题面 / 答案分节；文件缺失返回 None。"""
    file_path = str(item.get("file_path") or "")
    if not file_path:
        return None
    path = os.path.join(vault, file_path.replace("\\", os.sep).replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
    sections = split_sections(content)
    meta = parse_yaml_frontmatter(content)
    return {
        "uid": item.get("uid", ""),
        "question_id": item.get("question_id", ""),
        "subject": meta.get("科目", item.get("subject", "")),
        "category": extract_category(meta) or item.get("category", ""),
        "difficulty": meta.get("难度", item.get("difficulty", "")),
        "question": sections.get(QUESTION_SECTION, "").strip(),
        "answer": sections.get(ANSWER_SECTION, "").strip(),
        "labels": item.get("labels") or [],
        "extra_gap_lines": int(item.get("extra_gap_lines", 0) or 0),
    }


def build_board_export_data(vault, board_id, mode="all", include_answers=None, overrides=None):
    """组装展示板导出数据（不做分页，分页在浏览器完成）。

    mode="all"  整板从头排版；
    mode="new"  只排尚未进入纸面记录的题目，版面沿用纸面记录里的几何，
                并把 cursor / pages 交给浏览器，让新题接在原纸空白处。
    """
    from .boards import board_items_for_export, normalize_print

    mode = "new" if str(mode or "").lower() == "new" else "all"
    board, items = board_items_for_export(vault, board_id, mode)
    printed = board.get("printed") or {}
    has_paper = int(printed.get("pages", 0) or 0) > 0
    if mode == "new" and not has_paper:
        raise RuntimeError("这个展示板还没有纸面记录，请先「打印全部」并标记为已打印")
    settings = normalize_print({**board.get("print", {}), **(overrides or {})})
    if mode == "new" and has_paper:
        # 纸面几何以已打印的纸为准（栏宽、题间距、装订边），其余显示项跟随当前设置
        paper = normalize_print(printed.get("print") or {})
        for key in ("note_ratio", "gap_lines", "binding_mm"):
            settings[key] = paper[key]
    if include_answers is not None:
        settings["answers"] = "append" if include_answers else "none"

    questions = []
    for item in items:
        question = _board_read_question(vault, item)
        if question:
            questions.append(question)
    if not questions:
        if mode == "new":
            raise RuntimeError("没有新增题目需要打印")
        raise RuntimeError("展示板没有可导出的题目")

    colors = _label_color_map(vault)
    start_index = (len(printed.get("items") or []) + 1) if mode == "new" else 1
    today = datetime.date.today().isoformat()
    data = {
        "meta": {
            "kind": "board",
            "board_id": str(board.get("id") or board_id),
            "board_name": board.get("name", ""),
            "title": BOARD_TITLE,
            "generated": today,
            "mode": mode,
            "print": settings,
            "question_count": len(questions),
            "index_start": start_index,
            "printed": {
                "pages": int(printed.get("pages", 0) or 0),
                "cursor": dict(printed.get("cursor") or {}),
                "answer_pages": list(printed.get("answer_pages") or []),
                "count": len(printed.get("items") or []),
            } if mode == "new" else None,
        },
        "questions": [],
        "answers": [],
    }
    for offset, question in enumerate(questions):
        data["questions"].append({
            "idx": start_index + offset,
            "uid": question["uid"],
            "question_id": question["question_id"],
            "subject": question.get("subject", ""),
            "category": question.get("category", ""),
            "difficulty": question.get("difficulty", ""),
            "labels": _board_label_objects(question.get("labels", []) if settings["show_labels"] else [], colors),
            "blocks": _text_to_blocks(vault, question.get("question", "") or "(无题目内容)"),
            "extra_gap_lines": max(0, min(24, int(question.get("extra_gap_lines", 0) or 0))),
        })
    if settings["answers"] == "append":
        for offset, question in enumerate(questions):
            data["answers"].append({
                "idx": start_index + offset,
                "uid": question["uid"],
                "blocks": _text_to_blocks(vault, question.get("answer", "").strip()),
            })
    return data


_BOARD_BODY = """<div id="bar">
  <strong>OMRS · 错题集打印版</strong>
  <button id="btnPrint" disabled>打印 / 导出 PDF</button>
  <button id="btnDone" class="secondary" title="打印完成后回主程序记录纸面状态">✓ 已打印，记录纸面</button>
  <label><input type="checkbox" id="btnDebug"> 显示切口</label>
  <span class="stat" id="stat">排版中…</span>
</div>
<div id="notice"></div>
<div id="stage"></div>"""


def _build_board_html(data):
    css = _read_template("board.css")
    js = _read_template("board.js")
    katex_css, katex_js = _read_katex_bundle()
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    mode = data.get("meta", {}).get("mode", "all")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="omrs-board-mode" content="{mode}">\n'
        f"<title>{BOARD_TITLE}</title>\n"
        f"<style>\n{katex_css}\n</style>\n"
        f"<style>\n{css}\n</style>\n"
        "</head>\n<body>\n"
        f"{_BOARD_BODY}\n"
        f"<script>\n{katex_js}\n</script>\n"
        f"<script>window.OMRS_DATA = {data_json};</script>\n"
        f"<script>\n{js}\n</script>\n"
        "</body>\n</html>\n"
    )


def export_board_html(vault, board_id, mode="all", include_answers=None, overrides=None):
    """导出展示板为自包含 HTML（bytes）。分页、切片、纸面续排均由浏览器完成。"""
    data = build_board_export_data(vault, board_id, mode=mode, include_answers=include_answers, overrides=overrides)
    return _build_board_html(data).encode("utf-8")


def board_export_filename(board, mode="all"):
    """下载文件名；Content-Disposition 里另有 ASCII 兜底，这里保留中文板名。"""
    name = str((board or {}).get("name") or (board or {}).get("id") or "board")
    suffix = "-新增" if mode == "new" else ""
    return f"OMRS-BD-{name}{suffix}-错题集.html"
