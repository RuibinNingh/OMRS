"""MCP 请求边界：真实 Key，流式请求体、超时、并发与限流。

本文件只测试标准库实现的 ASGI guard，无需安装可选 MCP SDK。
"""

import asyncio
import tempfile
import unittest
from unittest.mock import patch

from omrs.mcp.http import MCPRequestGuard
from omrs.mcp.keys import create_key


class MCPHTTPGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="omrs-mcp-http-")
        self.vault = self.temp.name
        self.key = create_key(self.vault, "guard-test", ["omrs:read"])

    def tearDown(self):
        self.temp.cleanup()

    def scope(self, extra=()):
        return {"type": "http", "method": "POST", "path": "/mcp", "headers": [
            (b"authorization", b"Bearer " + self.key["secret"].encode()), *extra]}

    async def request(self, guard, scope=None, messages=None):
        supplied = list(messages or [{"type": "http.request", "body": b"{}", "more_body": False}])
        sent = []
        async def receive():
            return supplied.pop(0) if supplied else {"type": "http.disconnect"}
        async def send(message):
            sent.append(message)
        await guard(scope or self.scope(), receive, send)
        return next(message["status"] for message in sent if message["type"] == "http.response.start")

    def test_chunked_and_declared_large_body_are_rejected_before_app(self):
        called = []
        async def app(*_):
            called.append(True)
        guard = MCPRequestGuard(app, self.vault, maximum=5)
        async def run():
            self.assertEqual(await self.request(guard, self.scope([(b"content-length", b"6")])), 413)
            self.assertEqual(await self.request(guard, messages=[
                {"type": "http.request", "body": b"123", "more_body": True},
                {"type": "http.request", "body": b"456", "more_body": False},
            ]), 413)
            self.assertEqual(await self.request(guard, self.scope([(b"content-length", b"bad")])), 400)
            self.assertEqual(await self.request(guard, self.scope([(b"content-length", b"2"),
                                                                  (b"content-length", b"2")])), 400)
            self.assertEqual(called, [])
            self.assertEqual(guard.active[self.key["key_id"]], 0)
        asyncio.run(run())

    def test_valid_chunked_body_replayed_and_alternate_header_forwarded(self):
        captured = []
        async def app(scope, receive, send):
            body = b""
            while True:
                message = await receive()
                body += message["body"]
                if not message.get("more_body"):
                    break
            captured.append((scope["headers"], body))
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        guard = MCPRequestGuard(app, self.vault, maximum=8)
        scope = {**self.scope(), "headers": [(b"x-omrs-mcp-key", self.key["secret"].encode())]}
        async def run():
            status = await self.request(guard, scope, [
                {"type": "http.request", "body": b"{", "more_body": True},
                {"type": "http.request", "body": b"}", "more_body": False},
            ])
            self.assertEqual(status, 200)
            self.assertEqual(captured[0][1], b"{}")
            self.assertIn((b"authorization", b"Bearer " + self.key["secret"].encode()), captured[0][0])
        asyncio.run(run())

    def test_duplicate_credentials_rejected(self):
        called = []
        async def app(*_):
            called.append(True)
        guard = MCPRequestGuard(app, self.vault)
        async def run():
            self.assertEqual(await self.request(guard, self.scope([(b"authorization", b"Bearer ignored")])), 401)
            scope = {**self.scope(), "headers": [(b"x-omrs-mcp-key", self.key["secret"].encode()),
                                                   (b"x-omrs-mcp-key", self.key["secret"].encode())]}
            self.assertEqual(await self.request(guard, scope), 401)
            self.assertEqual(called, [])
        asyncio.run(run())

    def test_body_timeout_releases_active_slot(self):
        called = []
        async def app(*_):
            called.append(True)
        guard = MCPRequestGuard(app, self.vault)
        async def run():
            sent = []
            gate = asyncio.Event()
            async def receive():
                await gate.wait()
                return {"type": "http.disconnect"}
            async def send(message):
                sent.append(message)
            with patch("omrs.mcp.http.REQUEST_BODY_TIMEOUT", .005):
                await guard(self.scope(), receive, send)
            self.assertEqual(sent[0]["status"], 408)
            self.assertEqual(called, [])
            self.assertEqual(guard.active[self.key["key_id"]], 0)
        asyncio.run(run())

    def test_per_key_rate_limit(self):
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        guard = MCPRequestGuard(app, self.vault)
        async def run():
            with patch("omrs.mcp.http.REQUESTS_PER_MINUTE", 2):
                self.assertEqual(await self.request(guard), 200)
                self.assertEqual(await self.request(guard), 200)
                self.assertEqual(await self.request(guard), 429)
            self.assertEqual(guard.active[self.key["key_id"]], 0)
        asyncio.run(run())

    def test_per_key_concurrency_limit_and_slot_cleanup(self):
        async def run():
            gate, ready = asyncio.Event(), asyncio.Event()
            entered = []
            async def app(scope, receive, send):
                entered.append(True)
                if len(entered) == 2:
                    ready.set()
                await gate.wait()
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ok"})
            guard = MCPRequestGuard(app, self.vault)
            with patch("omrs.mcp.http.MAX_CONCURRENT_REQUESTS", 2):
                first = asyncio.create_task(self.request(guard))
                second = asyncio.create_task(self.request(guard))
                await asyncio.wait_for(ready.wait(), 2)
                self.assertEqual(await self.request(guard), 429)
                gate.set()
                self.assertEqual(await asyncio.gather(first, second), [200, 200])
                self.assertEqual(await self.request(guard), 200)
            self.assertEqual(guard.active[self.key["key_id"]], 0)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
