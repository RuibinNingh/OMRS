"""A4 导出的固定中文字体：按内容选择现有 Unicode 分片，只使用标准库。"""

import base64
from functools import lru_cache
from pathlib import Path
import re


FONT_ROOT = Path(__file__).resolve().parents[1] / "assets" / "vendor" / "fonts"
_FAMILIES = (
    ("noto-serif-sc.css", "Noto Serif SC", "OMRS Print Serif", "notoserifsc-OFL.txt"),
    ("fonts.css", "Noto Sans SC", "OMRS Print Sans", "notosanssc-OFL.txt"),
)
_STATIC_TEXT = (
    "OMRS · A4 打印版 打印 / 导出 PDF 显示切口 排版中…页 无切穿 处被迫切穿 "
    "错题复习清单 请在下方空白处作答，做完后再翻到末尾的反馈区核对答案与错因。 "
    "一、题目 二、反馈区 每题下方是答案与错因。 本次未导出答案，只列错因。 "
    "科目 分类 难度 标签 第 题 关联 暂无答案 字体 排版 失败 请重新导出 单栏 "
    "字体与排版尚未准备好，请等待页面排版完成后再打印。 "
    "有内容超出 A4 栏高，请改用单栏或调整超长公式后重新导出。 "
    "内嵌字体无法加载，请重新下载导出文件。 排版未完成 "
)
_FACE_RE = re.compile(r"@font-face\s*\{[^}]+\}")
_FILE_RE = re.compile(r"url\(['\"]?([\w.-]+\.woff2)['\"]?\)")


def _ranges(value):
    """解析 CSS Unicode 范围，支持单点、连续范围与问号通配符。"""
    result = []
    for token in value.split(","):
        token = token.strip().upper().removeprefix("U+")
        if "?" in token:
            lo, hi = token.replace("?", "0"), token.replace("?", "F")
        else:
            lo, _, hi = token.partition("-")
            hi = hi or lo
        result.append((int(lo, 16), int(hi, 16)))
    return tuple(result)


@lru_cache(maxsize=8)
def _faces(path, signature):
    # signature 让开发期间更新样式也能失效；发布目录内的字体资源不可变。
    return tuple(_FACE_RE.findall(Path(path).read_text(encoding="utf-8")))


@lru_cache(maxsize=256)
def _font_uri(path, signature):
    content = Path(path).read_bytes()
    if not content.startswith(b"wOF2"):
        raise ValueError("打印字体不是有效 WOFF2：" + Path(path).name)
    return "data:font/woff2;base64," + base64.b64encode(content).decode("ascii")


def _signature(path):
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _codepoints(data):
    used = set(range(32, 127)) | {ord(char) for char in _STATIC_TEXT}

    def collect(value):
        if isinstance(value, str):
            if not value.startswith("data:"):
                used.update(map(ord, value))
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    collect(data)
    return used


def inline_print_fonts(data):
    """内嵌正文/元信息需要的字体分片和许可；导出后不访问网络或系统 local()。"""
    used = _codepoints(data)
    output = []
    for stylesheet, family, alias, license_name in _FAMILIES:
        source = FONT_ROOT / stylesheet
        license_text = (FONT_ROOT / license_name).read_text(encoding="utf-8")
        output.append("/* " + license_text.replace("*/", "* /") + " */")
        for face in _faces(str(source), _signature(source)):
            family_match = re.search(r"font-family:\s*['\"]([^'\"]+)['\"]", face)
            if not family_match or family_match.group(1) != family:
                continue
            coverage = re.search(r"unicode-range:\s*([^;]+)", face)
            if coverage and not any(lo <= char <= hi for lo, hi in _ranges(coverage.group(1)) for char in used):
                continue
            font_match = _FILE_RE.search(face)
            if not font_match:
                raise ValueError("打印字体缺少本地 WOFF2 来源")
            font = FONT_ROOT / font_match.group(1)
            if font.resolve().parent != FONT_ROOT.resolve():
                raise ValueError("打印字体路径越界")
            uri = _font_uri(str(font), _signature(font))
            face = face.replace(family, alias)
            face = _FILE_RE.sub(lambda match: "url(" + uri + ")", face)
            face = re.sub(r"font-display:\s*\w+", "font-display: block", face)
            output.append(face)
    return "\n".join(output)
