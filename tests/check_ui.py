"""Front-end UI gate. All production markup and styles are checked without a legacy baseline.

    python3 tests/check_ui.py          # violations cause exit status 1
    python3 tests/check_ui.py --report # counts in the standalone pages and shell

Rules R1–R9 cover token use, safe DOM writes, import direction and file size.
The standalone mobile page and dashboard shell must have zero inline handlers, HTML
assignments, inline styles, literal colors and untokenized font sizes.
"""
import json
import os
from pathlib import Path
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "assets/app"
METRICS = ("handlers", "html_assign", "inline_style", "color_literals", "font_size_literals")
MAX_LINES = {".js": 400, ".mjs": 400, ".css": 300}
MEDIA_OK = {760, 761, 1160, 1161, 1500, 1501}

HANDLER_RE = re.compile(r"(?<![\w.$])on[a-z]{3,}\s*=\s*\\?[\"'`]")
HTML_ASSIGN_RE = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)|insertAdjacentHTML\s*\(")
STYLE_ATTR_RE = re.compile(r"(?<![\w-])style\s*=\s*\\?[\"'`]")
COLOR_RE = re.compile(r"(?<![\w&#-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])|\b(?:rgba?|hsla?)\(")
FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(?!var\(|inherit)[^;\"'}]+")
DECL_RE = re.compile(r"([a-z-]+)\s*:\s*([^;{}]+)")
LENGTH_RE = re.compile(r"(?<![\w-])-?\d*\.?\d+(?:px|rem|em|vh|vw|%)")
TIME_RE = re.compile(r"(?<![\w-])\d*\.?\d+m?s\b|cubic-bezier\(|steps\(")
MEDIA_RE = re.compile(r"@media[^{]*")
IMPORT_RE = re.compile(r"(?:\bimport\s[^'\"]*?from\s*|\bimport\s*\(\s*|\bimport\s+)['\"]([^'\"]+)['\"]")


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def strip_css_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def legacy_files(root):
    out = []
    assets = os.path.join(root, "assets")
    for name in sorted(os.listdir(assets)):
        path = os.path.join(assets, name)
        if os.path.isfile(path) and os.path.splitext(name)[1] in (".js", ".css", ".html"):
            out.append(path)
    html = os.path.join(root, "omrs_dashboard.html")
    if os.path.isfile(html):
        out.append(html)
    return out


def css_values(text):
    """(属性, 值) 列表：只取声明，避开选择器里的 #id。"""
    return DECL_RE.findall(strip_css_comments(text))


def legacy_counts(path):
    text = Path(path).read_text(encoding="utf-8")
    ext = os.path.splitext(path)[1]
    if ext == ".css":
        values = css_values(text)
        return {
            "handlers": 0, "html_assign": 0, "inline_style": 0,
            "color_literals": sum(len(COLOR_RE.findall(v)) for _, v in values),
            "font_size_literals": sum(1 for p, v in values if p == "font-size" and not v.strip().startswith(("var(", "inherit"))),
        }
    return {
        "handlers": len(HANDLER_RE.findall(text)),
        "html_assign": len(HTML_ASSIGN_RE.findall(text)),
        "inline_style": len(STYLE_ATTR_RE.findall(text)),
        "color_literals": len(COLOR_RE.findall(text)),
        "font_size_literals": len(FONT_SIZE_RE.findall(text)),
    }


def measure_legacy(root):
    return {rel(root, p): legacy_counts(p) for p in legacy_files(root)}


def check_legacy(root, current):
    problems = []
    allowed = {"inbox_mobile.html"}
    assets = os.path.join(root, "assets")
    for name in os.listdir(assets):
        path = os.path.join(assets, name)
        if os.path.isfile(path) and name not in allowed:
            problems.append(f"assets/{name}：前端根目录只允许 inbox_mobile.html；代码放 assets/app/")
    for name, counts in current.items():
        for key in METRICS:
            if counts[key]:
                problems.append(f"{name}：{key} {counts[key]}（全仓零容忍）")
    return problems


def layer_of(path):
    """assets/app 下的相对路径 → (层, 页面名)。"""
    parts = path.split("/")
    if len(parts) == 1:
        return "root", None
    if parts[0] == "features" and len(parts) > 2:
        return "features", parts[1]
    return parts[0], None


def import_allowed(src, dst):
    s_layer, s_page = layer_of(src)
    d_layer, d_page = layer_of(dst)
    if s_layer == "root":
        return True
    allowed = {"core": {"core"}, "ui": {"ui", "core"}, "domain": {"domain", "ui", "core"},
               "features": {"features", "domain", "ui", "core"}, "styles": {"styles"}}.get(s_layer, {"core"})
    if d_layer not in allowed:
        return False
    return not (s_layer == "features" and d_layer == "features" and s_page != d_page)


def check_css(name, text, is_tokens):
    problems = []
    for prop, value in css_values(text):
        v = value.strip()
        tag = f"{name}：{prop}: {v[:40]}"
        if not is_tokens:
            if COLOR_RE.search(v) and not prop.startswith("--"):
                problems.append(f"R1 颜色字面量 {tag}")
            if prop in ("font-size", "line-height", "font-weight", "font-family") and not v.startswith(("var(", "inherit")):
                problems.append(f"R2 字体属性不用 token {tag}")
            if re.fullmatch(r"(margin|padding)(-[a-z]+)*|(row-|column-)?gap", prop) and LENGTH_RE.search(re.sub(r"calc\([^)]*var\([^)]*\)[^)]*\)", "", v)):
                problems.append(f"R3 间距字面量 {tag}")
            if prop == "border-radius" and not re.fullmatch(r"(var\(--r-[\w-]+\)|0|50%)(\s+(var\(--r-[\w-]+\)|0))*", v):
                problems.append(f"R4 圆角不用 token {tag}")
            if prop == "box-shadow" and not (v.startswith("var(--elev-") or v == "none" or "var(--focus-ring)" in v):
                problems.append(f"R4 阴影不用 token {tag}")
            if prop == "z-index" and not (v.startswith("var(--z-") or v in ("-1", "0", "1", "2", "auto")):
                problems.append(f"R4 z-index 不用 token {tag}")
            if re.match(r"(transition|animation)", prop) and TIME_RE.search(v):
                problems.append(f"R4 动效时长/缓动字面量 {tag}")
    for media in MEDIA_RE.findall(text):
        widths = {int(w) for w in re.findall(r"(\d+)px", media)}
        if widths - MEDIA_OK:
            problems.append(f"R5 {name}：断点 {sorted(widths - MEDIA_OK)} 不在 760/1160/1500 内")
    return problems


def check_script(name, text, app_rel, root):
    problems = []
    if STYLE_ATTR_RE.search(text):
        problems.append(f"R6 {name}：模板里有 style= 属性")
    if HANDLER_RE.search(text):
        problems.append(f"R6 {name}：模板里有 on*= 行内事件")
    if app_rel != "core/dom.js" and HTML_ASSIGN_RE.search(text):
        problems.append(f"R6 {name}：innerHTML/outerHTML/insertAdjacentHTML 只允许在 core/dom.js")
    if name.endswith((".js", ".mjs")):
        base = os.path.dirname(app_rel)
        for spec in IMPORT_RE.findall(text):
            if not spec.startswith("."):
                continue
            target = os.path.normpath(os.path.join(base, spec)).replace(os.sep, "/")
            if target.startswith(".."):
                problems.append(f"R7 {name}：import 越出 {APP}/（{spec}）")
            elif not import_allowed(app_rel, target):
                problems.append(f"R7 {name}：{layer_of(app_rel)[0]} 不能依赖 {target}")
    return problems


def check_app(root):
    base = os.path.join(root, APP)
    if not os.path.isdir(base):
        return []
    problems = []
    agents = Path(root, "AGENTS.md").read_text(encoding="utf-8") if os.path.isfile(os.path.join(root, "AGENTS.md")) else ""
    feat_dir = os.path.join(base, "features")
    if os.path.isdir(feat_dir):
        for page in sorted(os.listdir(feat_dir)):
            if os.path.isdir(os.path.join(feat_dir, page)) and f"`{APP}/features/{page}/`" not in agents:
                problems.append(f"R9 {APP}/features/{page}/ 没有登记在 AGENTS.md 的代码到文档对应表里")
    for dirpath, _, files in os.walk(base):
        for fname in sorted(files):
            path = os.path.join(dirpath, fname)
            name = rel(root, path)
            app_rel = rel(base, path)
            ext = os.path.splitext(fname)[1]
            if ext not in (".js", ".mjs", ".css", ".html"):
                continue
            text = Path(path).read_text(encoding="utf-8")
            limit = MAX_LINES.get(ext)
            if limit and text.count("\n") > limit:
                problems.append(f"R8 {name}：{text.count(chr(10))} 行，超过 {limit}")
            if ext == ".css":
                problems += check_css(name, text, app_rel == "styles/tokens.css")
            else:
                problems += check_script(name, text, app_rel, root)
    return problems


def main(argv, root=ROOT):
    current = measure_legacy(root)
    if "--update-baseline" in argv:
        print("P8 起没有存量基线；直接修复 check_ui.py 报出的违规")
        return 1
    if "--report" in argv:
        for key in METRICS:
            print(f"{key:20} {sum(c[key] for c in current.values())}")
        return 0
    problems = check_app(root) + check_legacy(root, current)
    for problem in problems:
        print(problem)
    totals = {key: sum(counts[key] for counts in current.values()) for key in METRICS}
    print(f"全仓 UI 计数：{json.dumps(totals, ensure_ascii=False)}；{len(problems)} 处问题")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
