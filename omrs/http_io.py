"""HTTP 请求读取：网络等待不持业务写锁，统一期限和错误语义。"""
import io
import json
import socket
import tempfile
import time

MIB = 1024 * 1024
IDLE_TIMEOUT = 15.0
READ_DEADLINE = 30.0
UPLOAD_DEADLINE = 600.0
CHUNK_BYTES = 16 * MIB


class BodyError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def policy(path, content_type="", legacy_mib=128, json_mib=2):
    """传输有界；逻辑多图通过分块上传引用保留完整数量。"""
    media_type = content_type.split(";", 1)[0].strip().lower()
    if path in ("/api/inbox/upload-refs", "/api/annotate/upload-refs"):
        return json_mib * MIB, READ_DEADLINE
    if path.startswith("/api/auth/"):
        return 4096, READ_DEADLINE
    if path.startswith("/api/mcp/"):
        return 16 * 1024, READ_DEADLINE
    if path == "/api/trainpanel/control":
        return 4096, READ_DEADLINE
    if path == "/api/trainpanel/try":
        return 15 * MIB + 65536, UPLOAD_DEADLINE
    if path == "/api/uploads/chunk":
        return CHUNK_BYTES, UPLOAD_DEADLINE
    if path == "/api/entry-background":
        return 201 * MIB, UPLOAD_DEADLINE
    if path.startswith("/api/uploads/"):
        return 16 * 1024, READ_DEADLINE
    if path == "/api/backup/import":
        if "json" in media_type:
            return json_mib * MIB, READ_DEADLINE
        return 8 * 1024 * MIB, UPLOAD_DEADLINE
    if (path in (
            "/api/create", "/api/question/markdown", "/api/ai-recognize", "/api/agent/message")
            or path.startswith(("/api/inbox/", "/api/drafts/", "/api/annotate/"))):
        return legacy_mib * MIB, UPLOAD_DEADLINE
    return json_mib * MIB, READ_DEADLINE


def content_length(handler):
    headers = handler.headers
    values = headers.get_all("Content-Length", []) if hasattr(headers, "get_all") else (
        [headers["Content-Length"]] if "Content-Length" in headers else [])
    if headers.get("Transfer-Encoding"):
        raise BodyError("请求体不支持 Transfer-Encoding，请提供唯一 Content-Length")
    if not values:
        return 0
    if len(values) != 1 or not str(values[0]).isascii() or not str(values[0]).isdecimal():
        raise BodyError("Content-Length 必须是唯一的非负整数")
    return int(values[0])


def receive(handler, path):
    """完整暂存到临时文件；文件由调用方在响应后关闭。"""
    length = content_length(handler)
    from .common import load_config
    config = load_config(handler.vault_path)
    legacy_mib = config.get("http_legacy_upload_mib", 128)
    json_mib = config.get("http_json_mib", 2)
    if type(legacy_mib) is not int or not 2 <= legacy_mib <= 8192:
        raise BodyError("http_legacy_upload_mib 必须是 2 到 8192 的整数")
    if type(json_mib) is not int or not 1 <= json_mib <= 8192:
        raise BodyError("http_json_mib 必须是 1 到 8192 的整数")
    maximum, deadline_seconds = policy(path, handler.headers.get("Content-Type", ""), legacy_mib, json_mib)
    if maximum is not None and length > maximum:
        raise BodyError("请求体超过接口大小限制", 413)
    output = tempfile.TemporaryFile("w+b")
    deadline = time.monotonic() + deadline_seconds
    connection = getattr(handler, "connection", None)
    old_timeout = connection.gettimeout() if connection is not None else None
    try:
        remaining = length
        while remaining:
            left = deadline - time.monotonic()
            if left <= 0:
                raise BodyError("请求体读取超时，请重新上传", 408)
            if connection is not None:
                connection.settimeout(min(IDLE_TIMEOUT, left))
            # read1 不等待凑满 64KiB，避免在有进展的上传上误判无进展。
            reader = getattr(handler.rfile, "read1", handler.rfile.read)
            block = reader(min(65536, remaining))
            if not block:
                raise BodyError("请求体提前结束")
            output.write(block)
            remaining -= len(block)
        output.seek(0)
        return output
    except (socket.timeout, TimeoutError):
        output.close()
        raise BodyError("请求体读取超时，请重新上传", 408) from None
    except BaseException:
        output.close()
        raise
    finally:
        if connection is not None:
            connection.settimeout(old_timeout)


def json_body(handler, body=None):
    if hasattr(handler, "_prepared_json"):
        return handler._prepared_json
    if body is None:
        body = handler.rfile.read(content_length(handler))
    try:
        value = json.loads(body or b"{}")
    except (ValueError, UnicodeError) as exc:
        raise BodyError("请求体必须是有效 UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise BodyError("请求体必须是 JSON 对象")
    return value


class HeadWriter:
    """HEAD 沿同一路由生成响应头，阻止所有正文写出。"""
    def write(self, body):
        return len(body)

    def flush(self):
        pass

    @property
    def closed(self):
        return False
