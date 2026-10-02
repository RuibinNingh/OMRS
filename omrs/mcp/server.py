"""OMRS MCP Streamable HTTP 服务。

协议由官方 ``mcp`` SDK 负责；本模块只注册固定工具集合，并把每次调用
转到 OMRS 现有查询和草稿领域函数。API Key 作为 Bearer token 使用，亦
兼容 ``X-OMRS-MCP-Key``，但不会出现在 URL、工具参数或响应中。
"""

import asyncio
import base64
import functools
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
from typing import Annotated, Literal
import urllib.parse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP, Image as MCPImage
from mcp.types import ToolAnnotations
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from jsonschema import Draft202012Validator
from .http import MCPRequestGuard
from .. import locking
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import drafts
from .. import runtime_records
from ..draft_prepare import merge_answer_text_runs
from ..agent.tools import read as read_tools
from ..question_images import read_question_image, validate_original_image
from .keys import verify_key, key_for_id
from .common import RequestError
from . import queries

MAX_IMAGES = 6
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = MAX_IMAGES * MAX_IMAGE_BYTES
MAX_FIELD_CHARS = 20_000
MAX_TOTAL_TEXT_CHARS = 500_000
TOOL_SCOPES = {
    "list_taxonomy": "omrs:read",
    "search_questions": "omrs:read",
    "get_question": "omrs:read",
    "get_question_image": "omrs:read",
    "get_overview": "omrs:read",
    "get_recommendations": "omrs:read",
    "list_sessions": "omrs:read",
    "get_session": "omrs:read",
    "list_drafts": "omrs:read",
    "get_draft": "omrs:read",
    "create_draft": "draft:create",
}

TOOL_SCOPES.update(queries.SCOPES)


class MCPFile(BaseModel):
    """与 ChatGPT fileParams 约定一致的附件对象。

    ``download_url`` 和 ``file_id`` 是平台要求的必填稳定身份；测试客户端
    也可以同时提供 ``data_base64``，但服务端仍会按实际字节重新校验。
    """

    model_config = ConfigDict(extra="forbid")
    download_url: str
    file_id: str
    mime_type: str = ""
    file_name: str = ""
    data_base64: str = ""


class MCPBlock(BaseModel):
    """沿用题目/答案块结构，图片仅可引用完整附件下标。"""

    model_config = ConfigDict(extra="forbid")
    section: Literal["题目", "答案"]
    kind: Literal["text", "image"]
    text: str | None = None
    image: int | str | None = None
    note: str = ""


class MCPTokenVerifier:
    def __init__(self, vault):
        self.vault = vault

    async def verify_token(self, token: str) -> AccessToken | None:
        row = await asyncio.to_thread(verify_key, self.vault, token)
        if not row:
            return None
        return AccessToken(token=token, client_id=row["key_id"], scopes=row["scopes"],
                           subject=row["key_id"])


class RestrictedMCP(FastMCP):
    """在 SDK 执行函数前按公开 schema 校验，错误不回显输入或本地堆栈。"""

    def __init__(self, *args, vault, **kwargs):
        self.vault = vault
        super().__init__(*args, **kwargs)

    async def list_tools(self):
        _, row = await asyncio.to_thread(_verified_key, self.vault)
        scopes = set(row["scopes"])
        tools = await super().list_tools()
        # 仅过滤当前请求的描述；全局注册表与 SDK 定义缓存不承担授权。
        return [tool for tool in tools if TOOL_SCOPES.get(tool.name) in scopes]

    async def call_tool(self, name, arguments):
        token = get_access_token()
        identity = await asyncio.to_thread(runtime_records.safely, key_for_id, self.vault, token.client_id) if token else None
        seq = await asyncio.to_thread(runtime_records.safely, runtime_records.begin, self.vault, name, arguments, identity)
        started = time.monotonic()
        result, code = None, "interrupted"
        try:
            result = await self._execute_tool(name, arguments)
            code = ""
            return result
        except ToolError as exc:
            prefix = str(exc).split(":", 1)[0]
            code = prefix if prefix in runtime_records.ERRORS else "internal_error"
            raise
        except Exception:
            code = "internal_error"
            raise
        finally:
            if seq is not None:
                await asyncio.shield(asyncio.to_thread(runtime_records.safely, runtime_records.finish,
                    self.vault, seq, round((time.monotonic() - started) * 1000), result, code))

    async def _execute_tool(self, name, arguments):
        tool = self._tool_manager.get_tool(name)
        if tool is None or name not in TOOL_SCOPES:
            raise ToolError("unknown_tool: 未开放此工具")
        try:
            await asyncio.to_thread(_require, self.vault, TOOL_SCOPES[name])
        except PermissionError:
            raise ToolError("forbidden: MCP Key 无权执行此能力或已失效") from None
        if next(Draft202012Validator(tool.parameters).iter_errors(arguments), None) is not None:
            raise ToolError("invalid_arguments: 参数不符合工具 schema")
        try:
            # JSON Schema 的 integer 接受 1.0；SDK 严格字段还须按参数模型校验，
            # 错误只返回固定说明，不能回显原始参数或 Pydantic 堆栈。
            tool.fn_metadata.arg_model.model_validate(arguments)
        except ValidationError:
            raise ToolError("invalid_arguments: 参数不符合工具 schema") from None
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, PermissionError):
                raise ToolError("forbidden: MCP Key 无权执行此能力或已失效") from None
            if isinstance(cause, locking.WriteLockTimeout):
                raise ToolError("write_busy: 写入繁忙，请稍后重试") from None
            if isinstance(cause, RequestError):
                raise ToolError(f"{cause.code}: {cause}") from None
            if isinstance(cause, ValueError):
                raise ToolError(f"invalid_request: {cause}") from None
            raise ToolError("internal_error: OMRS 执行失败，请稍后重试") from None


def _threaded(fn):
    """一个完整同步领域操作留在同一工作线程，不在事件循环持 RLock。"""
    @functools.wraps(fn)
    async def run(**kwargs):
        return await asyncio.to_thread(fn, **kwargs)
    return run


def _token():
    token = get_access_token()
    if token is None:
        raise PermissionError("MCP Key 无效或已吊销")
    return token


def _verified_key(vault):
    token = _token()
    row = verify_key(vault, token.token)
    if row is None:
        raise PermissionError("MCP Key 无效或已吊销")
    return token, row


def _require(vault, scope):
    token, row = _verified_key(vault)
    if scope not in set(row["scopes"] or []):
        raise PermissionError("MCP Key 没有执行此操作的权限")
    return token


def _read_call(vault, fn, args):
    _require(vault, "omrs:read")
    out = fn({"vault": vault}, args)
    return out.get("result", out)


def _parse_image(value):
    if isinstance(value, MCPFile):
        value = value.model_dump()
    if not isinstance(value, dict):
        raise ValueError("images 每一项必须是文件对象")
    encoded = value.get("data_base64")
    if encoded:
        if not isinstance(encoded, str) or len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 4096):
            raise ValueError("图片 base64 超出大小限制")
        if encoded.startswith("data:"):
            try:
                encoded = encoded.split(",", 1)[1]
            except IndexError as exc:
                raise ValueError("图片 data URL 不合法") from exc
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("图片 base64 不合法") from exc
    else:
        url = value.get("download_url")
        if not isinstance(url, str) or not url:
            raise ValueError("图片文件缺少 data_base64 或 download_url")
        raw = _download(url)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("图片为空或超过 8MB 限制")
    checked = validate_original_image(raw)
    mime, width, height = checked["mime"], checked["width"], checked["height"]
    return {"data": raw, "mime": mime, "width": width, "height": height,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "file_id": str(value.get("file_id") or "").strip(),
            "file_name": str(value.get("file_name") or value.get("name") or "").strip()[:160]}


def _bounded_text(value, name, maximum=MAX_FIELD_CHARS):
    if not isinstance(value, str):
        raise ValueError(f"{name} 必须是文字")
    if len(value) > maximum:
        raise ValueError(f"{name} 不能超过 {maximum} 个字符")
    return value


def _validate_read_texts(**values):
    for name, value in values.items():
        if value not in (None, ""):
            _bounded_text(value, name, 200)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """把已检查的公共地址固定到 TLS 连接，避免 DNS 重绑定绕过检查。"""

    def __init__(self, hostname, address, timeout):
        super().__init__(hostname, 443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        sock = socket.create_connection((self._pinned_address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._host)


def _download(url):
    if len(url) > 8192:
        raise ValueError("图片下载地址过长")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("图片下载地址不合法") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("图片地址必须是不带用户信息的 HTTPS URL")
    if port not in (None, 443) or parsed.fragment:
        raise ValueError("图片地址端口不受支持")
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("图片地址无法解析") from exc
    addresses = []
    for item in infos:
        value = item[4][0]
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise ValueError("图片地址指向受限网络，已拒绝下载")
        if value not in addresses:
            addresses.append(value)
    if not addresses:
        raise ValueError("图片地址无法解析")
    connection = _PinnedHTTPSConnection(parsed.hostname, addresses[0], timeout=10)
    try:
        target = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection.request("GET", target, headers={"Accept": "image/png,image/jpeg,image/gif", "Host": parsed.hostname})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ValueError("图片下载不允许重定向")
        if response.status < 200 or response.status >= 300:
            raise ValueError("图片下载失败，请重新提供文件")
        declared = response.getheader("Content-Length")
        if declared:
            if not declared.isdecimal():
                raise ValueError("图片响应大小不合法")
            if int(declared) > MAX_IMAGE_BYTES:
                raise ValueError("图片超过 8MB 限制")
        chunks, total = [], 0
        deadline = time.monotonic() + 30
        while total <= MAX_IMAGE_BYTES:
            if time.monotonic() > deadline:
                raise ValueError("图片下载超时，请重新提供文件")
            chunk = response.read1(min(64 * 1024, MAX_IMAGE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        data = b"".join(chunks)
    except ValueError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise ValueError("图片下载失败，请重新提供文件") from exc
    finally:
        connection.close()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 8MB 限制")
    return data


def _fingerprint(payload, images):
    identity = []
    for item in images:
        identity.append({"file_id": item.get("file_id"), "sha256": item.get("sha256"),
                         "file_name": item.get("file_name")})
    normalized = {"subject": payload["subject"], "category": payload["category"],
                  "knowledge_points": payload.get("knowledge_points") or [],
                  "blocks": payload["blocks"], "cause": payload.get("cause") or "",
                  "cause_statement": payload.get("cause_statement") or "", "images": identity}
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _stable_fingerprint(payload, images):
    """只使用客户端稳定文件身份，不把短期签名 URL 放进幂等摘要。"""
    identity = []
    for value in images:
        item = value.model_dump() if isinstance(value, MCPFile) else value
        identity.append({"file_id": str(item.get("file_id") or ""),
                         "file_name": str(item.get("file_name") or ""),
                         "mime_type": str(item.get("mime_type") or "")})
    normalized = {"subject": payload["subject"], "category": payload["category"],
                  "knowledge_points": payload.get("knowledge_points") or [],
                  "blocks": payload["blocks"], "cause": payload.get("cause") or "",
                  "cause_statement": payload.get("cause_statement") or "", "images": identity}
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _draft_view(draft):
    sources = draft.get("source_images") or []
    by_sha = {item.get("sha256"): item for item in sources}
    source_out = [{key: item.get(key) for key in ("ref", "width", "height", "mime", "bytes")}
                  for item in sources]
    blocks = []
    for block in draft.get("blocks") or []:
        item = {key: block.get(key) for key in ("id", "section", "ord", "kind", "text", "box", "box_origin", "note")}
        if block.get("kind") == "image":
            source = by_sha.get(block.get("image_sha"), {})
            item["image"] = source.get("ref")
        item.pop("image_sha", None)
        blocks.append(item)
    return {"draft_id": draft["id"], "status": draft["status"], "revision": draft["revision"],
            "subject": draft["subject"], "category": draft["category"],
            "knowledge_points": draft.get("knowledge_points") or [], "difficulty": draft.get("difficulty", 5),
            "cause": draft.get("cause") or "", "cause_verification": draft.get("cause_verification"),
            "source_channel": draft.get("source_channel") or "agent", "source_images": source_out,
            "blocks": blocks, "created_at": draft.get("created_at"),
            "updated_at": draft.get("updated_at"), "reused": bool(draft.get("reused"))}


def _create_result(vault, draft):
    """缓存与新建均在封装结果前复查，保留已提交的草稿和原件。"""
    _require(vault, "draft:create")
    return _draft_view(draft)


def build_server(vault, host="127.0.0.1", port=8472, public_url=None):
    """创建带固定工具白名单的 FastMCP 实例。"""
    resource_url = f"http://{host}:{port}/mcp"
    allowed_hosts = [f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]
    allowed_origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    if public_url:
        url = urllib.parse.urlsplit(public_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password or
                url.path != "/mcp" or url.query or url.fragment):
            raise ValueError("MCP 公网地址必须是不含查询参数的 HTTPS /mcp 地址")
        resource_url = public_url
        allowed_hosts.extend([url.netloc, url.hostname + ":443"])
        allowed_origins.append("https://" + url.netloc)
    server = RestrictedMCP(
        "OMRS",
        vault=vault,
        instructions="只读查询 OMRS 学习数据；唯一业务写入是创建待审核草稿。",
        token_verifier=MCPTokenVerifier(vault),
        auth=AuthSettings(issuer_url="https://omrs.invalid", resource_server_url=resource_url),
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                                     allowed_hosts=allowed_hosts, allowed_origins=allowed_origins),
        host=host, port=port, streamable_http_path="/mcp", json_response=True, stateless_http=True,
    )

    def list_taxonomy(subject: str = "", page: Annotated[int, Field(ge=1)] = 1):
        _validate_read_texts(subject=subject)
        return _read_call(vault, read_tools.list_taxonomy, {"subject": subject, "page": page})

    def search_questions(keywords: list[str] | None = None, match: Literal["any", "all"] = "any", subject: str = "", category: str = "", knowledge_point: str = "", labels: list[str] | None = None,
                         label_match: Literal["any", "all"] = "any", status: Literal["", "due", "overdue", "leech", "killed", "suspended", "new", "active"] = "", mastery_min: float | None = None, mastery_max: float | None = None, difficulty_min: float | None = None,
                         difficulty_max: float | None = None, due_range: Literal["", "overdue", "today", "3days", "7days", "future", "not_due"] = "", created_from: str = "", created_to: str = "", sort: list[dict[str, object]] | None = None, page: Annotated[int, Field(ge=1)] = 1,
                         page_size: Annotated[int, Field(ge=1, le=30)] = 20):
        keywords = keywords or []
        labels = labels or []
        if len(keywords) > 8 or len(labels) > 20:
            raise ValueError("keywords 最多 8 项，labels 最多 20 项")
        for value in [*keywords, *labels]:
            _bounded_text(value, "查询条件", 200)
        _validate_read_texts(subject=subject, category=category, knowledge_point=knowledge_point,
                             due_range=due_range, created_from=created_from, created_to=created_to)
        args = {"keywords": keywords, "match": match, "subject": subject, "category": category,
                "knowledge_point": knowledge_point, "labels": labels or [], "label_match": label_match,
                "status": status or None, "mastery_min": mastery_min, "mastery_max": mastery_max,
                "difficulty_min": difficulty_min, "difficulty_max": difficulty_max, "due_range": due_range or None,
                "created_from": created_from, "created_to": created_to, "sort": sort, "page": page,
                "page_size": page_size}
        return _read_call(vault, read_tools.search_questions, args)

    def get_question(uid: str):
        _bounded_text(uid, "uid", 200)
        return _read_call(vault, read_tools.get_question, {"uid": uid})

    def get_question_image(uid: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")],
                           image_index: Annotated[int, Field(ge=0, strict=True)]) -> MCPImage:
        _require(vault, "omrs:read")
        raw, image_format = read_question_image(vault, uid, image_index)
        _require(vault, "omrs:read")
        return MCPImage(data=raw, format=image_format)

    def get_overview(subject: str = ""):
        _validate_read_texts(subject=subject)
        return _read_call(vault, read_tools.get_overview, {"subject": subject})

    def get_recommendations(count: Annotated[int, Field(ge=1, le=30)] = 8, subject: str = "", category: str = "", label: str = ""):
        _validate_read_texts(subject=subject, category=category, label=label)
        return _read_call(vault, read_tools.get_recommendations,
                          {"count": count, "subject": subject, "category": category, "label": label})

    def list_sessions(status: Literal["", "active", "completed"] = ""):
        _validate_read_texts(status=status)
        return _read_call(vault, read_tools.list_sessions_tool, {"status": status or None})

    def get_session(session_id: str):
        _bounded_text(session_id, "session_id", 200)
        return _read_call(vault, read_tools.get_session_tool, {"session_id": session_id})

    def list_drafts(status: Literal["", "pending", "cropping", "review", "done", "discarded"] = "", source: Literal["", "agent", "mcp", "legacy"] = "", limit: Annotated[int, Field(ge=1, le=500)] = 50):
        _require(vault, "omrs:read")
        rows = drafts.list_drafts(vault, status=status or None, limit=limit, readonly=True,
                                  source_channel=source or None)
        return {"total": len(rows), "items": [_draft_view(row) for row in rows]}

    def get_draft(draft_id: str):
        _require(vault, "omrs:read")
        _bounded_text(draft_id, "draft_id", 200)
        return _draft_view(drafts.get_draft(vault, draft_id.strip(), readonly=True))

    def create_draft(subject: str, category: str, blocks: Annotated[list[MCPBlock], Field(min_length=1, max_length=40)], request_id: str,
                     knowledge_points: list[str] | None = None, cause: str = "", cause_statement: str = "",
                     images: Annotated[list[MCPFile], Field(max_length=MAX_IMAGES)] = [], client_name: str = ""):
        token = _require(vault, "draft:create")
        if not isinstance(request_id, str) or not 1 <= len(request_id.strip()) <= 128:
            raise ValueError("request_id 必须是 1 到 128 个字符")
        request_id = request_id.strip()
        if any(ord(ch) < 0x20 or ch in "?#/\\" for ch in request_id):
            raise ValueError("request_id 包含不允许的字符")
        if not isinstance(blocks, list) or not blocks or len(blocks) > 40:
            raise ValueError("blocks 必须是 1 到 40 个块的数组")
        images = images or []
        if not isinstance(images, list) or len(images) > MAX_IMAGES:
            raise ValueError("images 最多 6 张")
        _bounded_text(subject, "subject", 200)
        _bounded_text(category, "category", 200)
        _bounded_text(client_name, "client_name", 80)
        _bounded_text(cause, "cause")
        _bounded_text(cause_statement, "cause_statement")
        if knowledge_points is not None:
            if len(knowledge_points) > 8:
                raise ValueError("knowledge_points 最多 8 项")
            for value in knowledge_points:
                _bounded_text(value, "knowledge_point", 200)
        subject, category = subject.strip(), category.strip()
        knowledge_points = [value.strip() for value in (knowledge_points or []) if value.strip()]
        cause, cause_statement = cause.strip(), cause_statement.strip()
        if not subject or not category:
            raise ValueError("科目和分类不能为空")
        if cause and not cause_statement:
            raise ValueError("提供错因时必须同时提供 cause_statement；外部原话仍需人工核对")
        clean_blocks = []
        total_text_chars = 0
        for index, block in enumerate(blocks):
            if isinstance(block, MCPBlock):
                block = block.model_dump(exclude_none=True)
            if not isinstance(block, dict) or set(block) - {"section", "kind", "text", "image", "note"}:
                raise ValueError(f"第 {index + 1} 块包含不允许的字段")
            section, kind = block.get("section"), block.get("kind")
            if section not in ("题目", "答案") or kind not in ("text", "image"):
                raise ValueError(f"第 {index + 1} 块 section/kind 不合法")
            if kind == "text":
                text = _bounded_text(block.get("text") or "", f"第 {index + 1} 个文字块").strip()
                if not text:
                    raise ValueError(f"第 {index + 1} 个文字块为空")
                note = _bounded_text(block.get("note") or "", f"第 {index + 1} 个说明").strip()
                total_text_chars += len(text) + len(note)
                clean_blocks.append({"section": section, "kind": "text", "text": text,
                                     "note": note})
            else:
                image_index = block.get("image")
                if isinstance(image_index, str) and image_index.startswith("image-"):
                    try:
                        image_index = int(image_index.split("-", 1)[1])
                    except ValueError:
                        image_index = -1
                if isinstance(image_index, bool) or not isinstance(image_index, int) or not 0 <= image_index < len(images):
                    raise ValueError(f"第 {index + 1} 个图片块 image 必须引用 images 下标")
                note = _bounded_text(block.get("note") or "", f"第 {index + 1} 个说明").strip()
                total_text_chars += len(note)
                clean_blocks.append({"section": section, "kind": "image", "image": image_index,
                                     "note": note})
        if total_text_chars > MAX_TOTAL_TEXT_CHARS:
            raise ValueError("草稿文字总量超过限制")
        if not any(item["section"] == "题目" for item in clean_blocks):
            raise ValueError("草稿至少要有一个题目块")
        clean_blocks = merge_answer_text_runs(clean_blocks)
        blocks = clean_blocks
        payload = {"subject": subject, "category": category, "knowledge_points": knowledge_points or [],
                   "blocks": blocks, "cause": cause, "cause_statement": cause_statement}
        stable_hash = _stable_fingerprint(payload, images)
        key_id = token.client_id
        existing = drafts.mcp_request(vault, key_id, request_id)
        inline_images = any(bool((value.model_dump() if isinstance(value, MCPFile) else value).get(name))
                            for value in images for name in ("data_base64",))
        stable_identity = all(
            bool((value.model_dump() if isinstance(value, MCPFile) else value).get("file_id")) and
            bool((value.model_dump() if isinstance(value, MCPFile) else value).get("download_url"))
            for value in images
        )
        if existing and existing.get("stable_hash") == stable_hash and stable_identity and not inline_images:
            draft = drafts.get_draft(vault, existing["draft_id"], readonly=True)
            draft["reused"] = True
            return _create_result(vault, draft)
        prepared_images = [_parse_image(value) for value in images]
        if sum(len(item["data"]) for item in prepared_images) > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("图片总大小超过 48MiB 限制")
        fingerprint = _fingerprint(payload, prepared_images)
        # 已验证的附件下标转成现有领域层的图片 SHA。
        clean_blocks = [{**block, "image_sha": prepared_images[block["image"]]["sha256"]}
                        if block["kind"] == "image" else block for block in clean_blocks]
        # 下载已在锁外完成；幂等复查与原子创建共用领域层全局写锁。
        with locking.write_lock():
            _require(vault, "draft:create")
            existing = drafts.mcp_request(vault, key_id, request_id)
            if existing:
                if (existing.get("stable_hash") == stable_hash and stable_identity and not inline_images) or existing["content_hash"] == fingerprint:
                    draft = drafts.get_draft(vault, existing["draft_id"], readonly=True)
                    draft["reused"] = True
                    return _create_result(vault, draft)
                if existing["content_hash"] != fingerprint:
                    raise ValueError("同一 request_id 的内容不同，请使用新的 request_id")
            _require(vault, "draft:create")
            conversation_id = f"mcp:{key_id}:{request_id}"
            draft = drafts.create_mcp_draft(vault,
                {"subject": subject, "category": category, "knowledge_points": knowledge_points or [],
                 "blocks": clean_blocks, "cause": cause, "cause_statement": cause_statement},
                {"conversation_id": conversation_id, "run_id": None, "tool_call_id": None,
                 "source_channel": "mcp", "source_key_id": key_id, "source_request_id": request_id,
                 "content_hash": fingerprint, "cause_verification": "client_asserted" if cause else "none",
                 "source_client_name": client_name, "stable_hash": stable_hash},
                [item["data"] for item in prepared_images])
            return _create_result(vault, draft)

    read_defs = [
        (list_taxonomy, "list_taxonomy", "列出 OMRS 科目、分类、知识点和标记。"),
        (search_questions, "search_questions", "按现有助手口径筛选、排序和分页查询题目。"),
        (get_question, "get_question", "读取题目正文、练习记录、熟练度和复习状态。"),
        (get_question_image, "get_question_image", "按 get_question.images 的从 0 开始下标读取该题一张完整原图；需要看题图时按需调用。仅返回 PNG/JPEG/GIF 原生图片内容，单张不超过 8 MiB。"),
        (get_overview, "get_overview", "读取题库概况和薄弱分类。"),
        (get_recommendations, "get_recommendations", "读取 OMRS 复习推荐，不创建 Session。"),
        (list_sessions, "list_sessions", "读取最近的复习 Session。"),
        (get_session, "get_session", "读取一个复习 Session 的状态和题目。"),
        (list_drafts, "list_drafts", "读取当前 Vault 的活动草稿；可用 source=mcp 只列本 MCP 来源。"),
        (get_draft, "get_draft", "读取草稿内容和完整来源图片的审核信息。"),
    ]
    for fn, name, description in read_defs:
        server.add_tool(_threaded(fn), name=name, description=description,
                        structured_output=False if fn is get_question_image else None,
                        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                                                    openWorldHint=False))
    server.add_tool(_threaded(create_draft), name="create_draft", description="仅在用户明确要求保存时，创建来源为 MCP 的待审核草稿；不正式入库。images 是完整原图，image 块使用从 0 开始的附件下标，request_id 用于技术重试。",
                    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                                openWorldHint=True), meta={"openai/fileParams": ["images"]})
    queries.register(server, vault, _require, _threaded)
    # FastMCP 默认会忽略函数参数模型中的未知字段；MCP 是权限边界，必须
    # 把拼写错误或试图注入的顶层参数显式拒绝。
    for tool in server._tool_manager.list_tools():
        model = tool.fn_metadata.arg_model
        model.model_config["extra"] = "forbid"
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)
        # 复用助手的输入契约，避免数字/枚举/筛选数量与现有查询语义漂移。
        spec = next((item for item in read_tools.SPECS if item[0] == tool.name), None)
        if spec:
            for name, schema in spec[3].get("properties", {}).items():
                if name in tool.parameters.get("properties", {}):
                    current = tool.parameters["properties"][name]
                    default = current.get("default")
                    current.update(schema)
                    if "enum" in current and default == "":
                        current["enum"] = ["", *current["enum"]]
                    if "anyOf" in current:
                        current.pop("anyOf")
        if tool.name in {"search_questions", "list_taxonomy", "get_question", "get_overview",
                         "get_recommendations", "list_sessions", "get_session"}:
            for schema in tool.parameters["properties"].values():
                if schema.get("type") == "string":
                    schema["maxLength"] = 200
    return server


def build_app(vault, host="127.0.0.1", port=8472, public_url=None):
    server = build_server(vault, host=host, port=port, public_url=public_url)
    return MCPRequestGuard(server.streamable_http_app(), vault)
