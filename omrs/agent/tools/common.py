"""工具共用：题目一览（统计快照 + 投影）、到期文字、正文分节与规范化。"""
import datetime
import re
import unicodedata

from ...common import extract_images, parse_date, split_sections
from ...scheduling import is_killed_state

SECTIONS = ("题目", "答案", "错因")


def due_info(item, today=None):
    today = today or datetime.date.today()
    if is_killed_state(item.get("mastery", 0), item.get("tag", "")):
        return "已击杀", None
    d = parse_date(item.get("due_date", ""))
    if not d:
        return "未排期", None
    days = (d - today).days
    text = f"逾期 {-days} 天" if days < 0 else "今天到期" if days == 0 else "明天到期" if days == 1 else f"{days} 天后到期"
    return text, days


def mastery_of(item):
    return None if int(item.get("attempts") or 0) == 0 else round(float(item.get("mastery") or 0), 3)


def cause_of(notes):
    m = re.search(r"^##\s*错因\s*\n(.*?)(?=^##\s|\Z)", notes or "", re.S | re.M)
    return (m.group(1).strip() if m else "")


PLACEHOLDER = "（请在 Obsidian 中编辑此题目内容）"


def sections_of(content):
    parts = split_sections(content)
    question = parts.get("题目", "").strip()
    return {"题目": "" if question == PLACEHOLDER else question, "答案": parts.get("答案", "").strip(),
            "错因": cause_of(parts.get("备注", ""))}


def text_only(value):
    return re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", "", value or "").strip()


def image_names(value):
    return extract_images(value or "")


def norm(value):
    """NFKC、转小写、LaTeX 命令去反斜杠、去空白与花括号和 $，让「sin2x」能命中 \\sin 2x。"""
    value = unicodedata.normalize("NFKC", str(value or "")).lower()
    value = re.sub(r"\\([a-z]+)", r"\1", value)
    return re.sub(r"[\s{}\\$]", "", value)


def snippet(text, keyword, width=80):
    """命中处前后各取一段（不切断 $…$ 公式），命中词用 ** 标出；没命中取开头。"""
    text = re.sub(r"\s+", " ", text_only(text))
    idx = text.lower().find(keyword.lower()) if keyword else -1
    if idx < 0:
        return text[:width] + ("…" if len(text) > width else "")
    a, b = max(0, idx - 18), min(len(text), idx + len(keyword) + 40)
    if text[a:idx].count("$") % 2:
        a = text.rfind("$", 0, idx)
    if text[idx + len(keyword):b].count("$") % 2:
        nxt = text.find("$", idx + len(keyword))
        b = nxt + 1 if nxt >= 0 else len(text)
    hit = text[idx:idx + len(keyword)]
    inside_math = text[:idx].count("$") % 2 == 1
    mark = hit if inside_math else f"**{hit}**"
    return ("…" if a > 0 else "") + text[a:idx] + mark + text[idx + len(keyword):b] + ("…" if b < len(text) else "")
