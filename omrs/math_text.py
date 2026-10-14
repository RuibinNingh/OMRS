"""将正文里的成对 LaTeX 定界符统一为美元符号，保留公式命令与代码。"""
import re


_TOKEN = re.compile(
    r"(?P<fence>^ {0,3}(?:`{3,}|~{3,})[^\n]*)|(?P<code>`+)"
    r"|(?P<math>(?<![\\$])\${1,2})(?!\$)|(?P<latex>(?<!\\)\\[([])",
    re.MULTILINE,
)


def normalize_math_delimiters(text: str) -> str:
    """只转换同一行的 ``\\(...\\)`` 与可跨行的 ``\\[...\\]``。

    代码、已有美元公式、转义或未配对的定界符保持原样；重复调用结果不变。
    """
    out, position = [], 0
    while match := _TOKEN.search(text, position):
        start, end = match.span()
        out.append(text[position:start])
        token, kind = match.group(), match.lastgroup
        if kind == "fence":
            marker = re.match(r" {0,3}(`+|~+)", token)[1]
            close = re.compile(r"^ {0,3}" + marker[0] + "{" + str(len(marker)) + r",}[\t ]*\r?$", re.MULTILINE)
        elif kind == "code":
            close = re.compile(r"(?<!`)`{" + str(len(token)) + r"}(?!`)")
        elif kind == "math":
            close = re.compile(r"(?<![\\$])" + re.escape(token) + r"(?!\$)")
        else:
            close = re.compile(r"(?<!\\)\\" + (r"\)" if token == r"\(" else r"\]"))
        closing = close.search(text, end)
        if closing and (kind != "latex" or (closing.start() > end and
                        (token != r"\(" or "\n" not in text[end:closing.start()]))):
            body = text[end:closing.start()]
            if kind == "latex":
                delimiter = "$" if token == r"\(" else "$$"
                out.append(delimiter + body + delimiter)
            else:
                out.append(text[start:closing.end()])
            position = closing.end()
        else:
            # 未闭合围栏的余下内容仍是代码；其它未配对标记只保留自身。
            position = len(text) if kind == "fence" else end
            out.append(text[start:position])
    out.append(text[position:])
    return "".join(out)
