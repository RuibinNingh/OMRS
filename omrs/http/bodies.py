"""旧图片 JSON 流式解析；base64 图片转成上传引用而非累计在 Python 堆中。"""
import base64
import binascii
import io
import json
import re
import tempfile

from ..http_io import BodyError
from ..uploads import stage_file

_END_STRING = re.compile(r'["\\\x00-\x1f]')
_IMAGE_PREFIX = re.compile(r'^data:(image/(?:png|jpeg|gif));base64,')


class _Parser:
    def __init__(self, stream, vault, purpose):
        self.stream, self.vault, self.purpose = stream, vault, purpose
        self.buffer, self.offset = "", 0

    def fill(self):
        if self.offset == len(self.buffer):
            self.buffer = self.stream.read(65536)
            self.offset = 0
        return bool(self.buffer)

    def char(self):
        if not self.fill():
            raise BodyError("JSON 请求体提前结束")
        value = self.buffer[self.offset]
        self.offset += 1
        return value

    def peek(self):
        return self.buffer[self.offset] if self.fill() else ""

    def whitespace(self):
        while self.peek() in (" ", "\t", "\r", "\n"):
            self.offset += 1

    def string(self, images=True):
        if self.char() != '"':
            raise BodyError("JSON 字符串格式错误")
        pieces, prefix, temporary, tail = [], "", None, ""
        finished = False
        try:
            while not finished:
                if not self.fill():
                    raise BodyError("JSON 字符串提前结束")
                end = _END_STRING.search(self.buffer, self.offset)
                stop = end.start() if end else len(self.buffer)
                segment = self.buffer[self.offset:stop]
                self.offset = stop
                if end:
                    marker = self.char()
                    if marker == '"':
                        finished = True
                    elif marker == "\\":
                        escape = self.char()
                        if escape == "u":
                            digits = "".join(self.char() for _ in range(4))
                            try:
                                segment += json.loads('"\\u' + digits + '"')
                            except ValueError as exc:
                                raise BodyError("JSON Unicode 转义不合法") from exc
                        else:
                            escapes = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
                            if escape not in escapes:
                                raise BodyError("JSON 转义不合法")
                            segment += escapes[escape]
                    else:
                        raise BodyError("JSON 字符串含未转义控制字符")
                if temporary is None:
                    pieces.append(segment)
                    if images and len(prefix) < 100:
                        prefix = (prefix + segment)[:100]
                        match = _IMAGE_PREFIX.match(prefix)
                        if match:
                            temporary = tempfile.NamedTemporaryFile("w+b")
                            segment = "".join(pieces)[match.end():]
                            pieces.clear()
                        else:
                            continue
                    else:
                        continue
                tail += segment
                count = (len(tail) // 4) * 4
                if count:
                    temporary.write(base64.b64decode(tail[:count], validate=True))
                    tail = tail[count:]
            if temporary is not None:
                if tail:
                    temporary.write(base64.b64decode(tail, validate=True))
                temporary.flush()
                return {"upload_ref": stage_file(self.vault, temporary.name, mime=match.group(1), purpose=self.purpose)["upload_ref"]}
            # 让标准库合并 UTF-16 成对代理项，保持原 JSON 字符串语义。
            result = "".join(pieces)
            return result.encode("utf-16", "surrogatepass").decode("utf-16")
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise BodyError("图片 base64 或 JSON 字符串不合法") from exc
        finally:
            if temporary is not None:
                temporary.close()

    def value(self, depth=0, image_context=False):
        if depth > 64:
            raise BodyError("JSON 嵌套超过 64 层")
        self.whitespace()
        marker = self.peek()
        if marker == '"':
            return self.string(images=image_context)
        if marker in ('{', '['):
            self.char()
            end = '}' if marker == '{' else ']'
            result = {} if marker == '{' else []
            self.whitespace()
            if self.peek() == end:
                self.char()
                return result
            while True:
                self.whitespace()
                if marker == '{':
                    key = self.string(images=False)
                    self.whitespace()
                    if self.char() != ':':
                        raise BodyError("JSON 对象缺少冒号")
                    result[key] = self.value(depth + 1, image_context or key in ("question_images", "answer_images", "images", "data", "question_image", "answer_image", "image", "crops"))
                else:
                    result.append(self.value(depth + 1, image_context))
                self.whitespace()
                separator = self.char()
                if separator == end:
                    return result
                if separator != ',':
                    raise BodyError("JSON 项之间缺少逗号")
        token = []
        while self.peek() and self.peek() not in ',]} \t\r\n':
            token.append(self.char())
            if len(token) > 128:
                raise BodyError("JSON 数值或常量格式错误")
        try:
            return json.loads("".join(token))
        except ValueError as exc:
            raise BodyError("JSON 数值或常量格式错误") from exc


def parse_images(stream, vault, purpose):
    wrapper = io.TextIOWrapper(stream, encoding="utf-8")
    try:
        parser = _Parser(wrapper, vault, purpose)
        value = parser.value()
        parser.whitespace()
        if parser.peek() or not isinstance(value, dict):
            raise BodyError("请求体必须是单一 JSON 对象")
        return value
    except (UnicodeError, RecursionError) as exc:
        raise BodyError("请求体必须是有效 UTF-8 JSON") from exc
    finally:
        wrapper.detach()
