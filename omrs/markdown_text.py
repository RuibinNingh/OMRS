"""用于纯文本题面短句的双星号处理，与网页显示共用边界规则。"""

import re
from unicodedata import category


_TOKENS = re.compile(
    r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<suffix>[^\n]*)"
    r"|(?P<opaque>!\[\[[^\]\n]+\]\]|!\[[^\]\n]*\]\([^)\n]+\)"
    r"|\$\$[\s\S]+?\$\$|\$[^$\n]+\$|\\\([^\n]*?\\\)|\\\[[\s\S]*?\\\]"
    r"|(?<!`)(?P<backticks>`+)(?!`)[^\r\n]*?(?<!`)(?P=backticks)(?!`))"
    r"|(?P<newline>\r?\n)|(?P<stars>\*+)",
    re.MULTILINE,
)


def plain_emphasis(text):
    """移除普通文本内成对的双星号，给题目摘要截断前调用。"""
    if "**" not in text:
        return text
    pieces, cursor, start, fence = [], 0, -1, ""
    for match in _TOKENS.finditer(text):
        marker = match["fence"]
        if marker:
            if not fence:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not match["suffix"].strip():
                fence = ""
        if marker or fence or match["newline"] or "\n" in (match["opaque"] or ""):
            start = -1
            continue
        index = match.start()
        if match["stars"] != "**":
            continue
        escape_start = index
        while escape_start and text[escape_start - 1] == "\\":
            escape_start -= 1
        if (index - escape_start) % 2:
            continue
        before = text[index - 1] if index else " "
        after = text[index + 2:index + 3] or " "
        before_space, after_space = before.isspace(), after.isspace()
        before_category, after_category = category(before), category(after)
        opens = not after_space and (after_category[0] not in "PS" or before_space
                                     or before_category[0] in "PS" or after_category in ("Ps", "Pi") or after == "$")
        if start >= 0 and not before_space:
            pieces.extend((text[cursor:start], text[start + 2:index]))
            cursor, start = index + 2, -1
        elif opens:
            start = index
    pieces.append(text[cursor:])
    return "".join(pieces)
