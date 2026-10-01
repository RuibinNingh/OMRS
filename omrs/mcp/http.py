"""MCP HTTP 边界：独立凭据、请求体、超时与每个 Key 的资源限制。"""

import asyncio
import json
import time
from collections import deque

from .keys import verify_key

MAX_BODY_BYTES = 72 * 1024 * 1024
REQUEST_BODY_TIMEOUT = 30
REQUESTS_PER_MINUTE = 120
MAX_CONCURRENT_REQUESTS = 4


async def _error(send, status, message):
    body = json.dumps({"error": message}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class MCPRequestGuard:
    """先鉴权，再限流和有界读取；分块请求与 Content-Length 同样受限。"""

    def __init__(self, app, vault, maximum=MAX_BODY_BYTES):
        self.app, self.vault, self.maximum = app, vault, maximum
        self.recent = {}
        self.active = {}

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = list(scope.get("headers") or [])
        auth = [value for key, value in headers if key.lower() == b"authorization"]
        alternate = [value for key, value in headers if key.lower() == b"x-omrs-mcp-key"]
        if len(auth) > 1 or len(alternate) > 1:
            await _error(send, 401, "MCP Key 无效")
            return
        token = None
        if auth and auth[0].lower().startswith(b"bearer "):
            token = auth[0][7:]
        elif not auth and alternate:
            token = alternate[0]
            headers.append((b"authorization", b"Bearer " + token))
        if token is None or len(token) > 512:
            # 让 SDK 保留标准 Bearer challenge 与协议认证错误。
            await self.app(scope, receive, send)
            return
        try:
            identity = await asyncio.to_thread(verify_key, self.vault, token.decode("ascii"))
        except (UnicodeError, OSError, ValueError):
            identity = None
        if not identity:
            await self.app(scope, receive, send)
            return
        key_id = identity["key_id"]
        now = time.monotonic()
        # 状态只留一分钟内的有效 Key，避免不断签发测试 Key 累积内存。
        for stale in list(self.recent):
            queue = self.recent[stale]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if not queue and not self.active.get(stale):
                self.recent.pop(stale, None)
                self.active.pop(stale, None)
        queue = self.recent.setdefault(key_id, deque())
        if len(queue) >= REQUESTS_PER_MINUTE or self.active.get(key_id, 0) >= MAX_CONCURRENT_REQUESTS:
            await _error(send, 429, "MCP 请求过于频繁，请稍后重试")
            return
        queue.append(now)
        self.active[key_id] = self.active.get(key_id, 0) + 1
        try:
            sizes = [value for key, value in headers if key.lower() == b"content-length"]
            if sizes:
                try:
                    size = int(sizes[0])
                except ValueError:
                    size = -1
                if len(sizes) != 1 or size < 0:
                    await _error(send, 400, "Content-Length 不合法")
                    return
                if size > self.maximum:
                    await _error(send, 413, "MCP 请求体超过限制")
                    return
            messages, total = [], 0
            deadline = now + REQUEST_BODY_TIMEOUT
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - time.monotonic()))
                except TimeoutError:
                    await _error(send, 408, "MCP 请求体读取超时")
                    return
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > self.maximum:
                    await _error(send, 413, "MCP 请求体超过限制")
                    return
                messages.append(message)
                if not message.get("more_body", False):
                    break
            position = 0

            async def replay():
                nonlocal position
                if position < len(messages):
                    message = messages[position]
                    position += 1
                    return message
                return await receive()

            forwarded = dict(scope)
            forwarded["headers"] = headers
            await self.app(forwarded, replay, send)
        finally:
            self.active[key_id] -= 1
