"""真实 OMRS MCP 链路验收。

这些测试刻意启动 ``omrs_engine.py serve --mcp-port``，使用官方 mcp SDK
作为客户端，再读取同一个临时 Vault。没有 SDK 时整组测试会明确跳过，普通
OMRS 单测不因此增加 MCP 依赖。
"""

import asyncio
import base64
import hashlib
import glob
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from unittest.mock import Mock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
except ImportError:  # pragma: no cover - optional test dependency
    ClientSession = None
    streamable_http_client = None

MCP_AVAILABLE = ClientSession is not None and streamable_http_client is not None

from omrs.common import omrs_data_dir
from omrs.creation import create_question
from omrs import drafts
from omrs.mcp.keys import create_key, revoke_key
from omrs.agent.tools import read as read_tools
from omrs.feedback import process_feedback
from omrs.ledger import read_commits
from omrs.sessions import create_session_from_selection


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _png(width=2, height=2):
    # 生成带颜色条带的 PNG，不需要图像库。
    import struct
    import zlib
    raw = b"".join(b"\x00" + (b"\xff\x00\x00" if y % 2 else b"\x00\xff\x00") * width
                   for y in range(height))
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _jpeg():
    """固定的 3×2 RGB JPEG，不依赖 Pillow。"""
    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
        "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAMDASIAAhEBAxEB/8QAHw"
        "AAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcY"
        "GRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJ"
        "ytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEE"
        "BSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaH"
        "iImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDiKKKK9g8s/9k=")


def _gif():
    # 合法的 1x1 GIF89a 原件。
    return (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00"
            b"\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def _json_result(result):
    """读取 SDK 的结构化 JSON 或 text 内容。"""
    value = getattr(result, "structuredContent", None)
    if value is not None:
        return value
    value = getattr(result, "structured_content", None)
    if value is not None:
        return value
    for item in getattr(result, "content", ()):
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
    return {}


@asynccontextmanager
async def _session(port, secret=None):
    headers = {"Authorization": f"Bearer {secret}"} if secret else None
    async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=False) as client:
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


class MCPServerProcess:
    def __init__(self):
        self.work = tempfile.TemporaryDirectory(prefix="omrs-mcp-protocol-")
        self.vault = os.path.join(self.work.name, "vault")
        os.makedirs(os.path.join(self.vault, "错题"))
        self.web_port, self.mcp_port = _free_port(), _free_port()
        while self.mcp_port == self.web_port:
            self.mcp_port = _free_port()
        create_question(self.vault, "数学", "函数", 5, question_text="求 $f(2)$。", answer_text="答案是 4。")
        create_question(self.vault, "物理", "力学", 5, question_text="求加速度。", answer_text="a=g。")
        self.session_id = create_session_from_selection(self.vault, [
            {"uid": "函数1", "source": "due"}, {"uid": "力学1", "source": "due"}], "")["session_id"]
        process_feedback(self.vault, [{"uid": "函数1", "sub_score": 4, "is_correct": False,
                                      "source": "due", "note": "协议测试练习"}], self.session_id)
        self.process = None
        self.keys = {}

    def start(self):
        env = os.environ.copy()
        env.pop("OMRS_SYSTEMD_SERVICE", None)
        env["PYTHONUNBUFFERED"] = "1"
        log = open(os.path.join(self.work.name, "server.log"), "w", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "omrs_engine.py"), "--vault", self.vault,
             "serve", "-p", str(self.web_port), "--mcp-port", str(self.mcp_port)],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        )
        self._log = log
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.mcp_port}/mcp", timeout=1):
                    break
            except urllib.error.HTTPError:
                # 401/405 等协议层响应说明 Uvicorn 已监听；鉴权在 MCP SDK
                # 初始化时另行验证。
                break
            except OSError:
                if self.process.poll() is not None:
                    raise RuntimeError(open(self._log.name, encoding="utf-8").read())
                time.sleep(.15)
        else:
            raise RuntimeError("MCP 服务未在限时内就绪")
        self.keys["all"] = create_key(self.vault, "integration", ["omrs:read", "draft:create"])
        self.keys["read"] = create_key(self.vault, "readonly", ["omrs:read"])
        expired = create_key(self.vault, "expired", ["omrs:read"])
        path = os.path.join(omrs_data_dir(self.vault), "mcp_keys.json")
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        for row in data["keys"]:
            if row["key_id"] == expired["key_id"]:
                row["expires_at"] = "2020-01-01T00:00:00+00:00"
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        self.keys["expired"] = expired
        return self

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if getattr(self, "_log", None):
            self._log.close()
        self.work.cleanup()


@unittest.skipUnless(MCP_AVAILABLE, "可选依赖 mcp 未安装，跳过真实协议验收")
class MCPProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServerProcess()
        try:
            cls.server.start()
        except BaseException:
            cls.server.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_auth_scopes_expiry_and_fixed_tool_whitelist(self):
        async def run():
            with self.assertRaises(Exception):
                async with _session(self.server.mcp_port):
                    pass
            with self.assertRaises(Exception):
                async with _session(self.server.mcp_port, "wrong-key"):
                    pass
            with self.assertRaises(Exception):
                async with _session(self.server.mcp_port, self.server.keys["expired"]["secret"]):
                    pass
            revoked = create_key(self.server.vault, "revoked", ["omrs:read"])
            revoke_key(self.server.vault, revoked["key_id"])
            with self.assertRaises(Exception):
                async with _session(self.server.mcp_port, revoked["secret"]):
                    pass
            async with _session(self.server.mcp_port, self.server.keys["all"]["secret"]) as session:
                tools = await session.list_tools()
                self.assertEqual([tool.name for tool in tools.tools], [
                    "list_taxonomy", "search_questions", "get_question", "get_overview",
                    "get_recommendations", "list_sessions", "get_session", "list_drafts",
                    "get_draft", "create_draft",
                ])
                schema = next(tool.inputSchema for tool in tools.tools if tool.name == "create_draft")
                file_schema = schema["$defs"]["MCPFile"]
                self.assertEqual(file_schema["required"], ["download_url", "file_id"])
                for name in ("download_url", "file_id"):
                    self.assertEqual(file_schema["properties"][name]["type"], "string")
                for name in ("mime_type", "file_name"):
                    value = file_schema["properties"][name]
                    self.assertTrue(value.get("type") == "string" or
                                    any(choice.get("type") == "string" for choice in value.get("anyOf", [])))
                search_schema = next(tool.inputSchema for tool in tools.tools if tool.name == "search_questions")
                self.assertEqual(search_schema["properties"]["page"]["type"], "integer")
                mastery_schema = search_schema["properties"]["mastery_min"]
                self.assertTrue(mastery_schema.get("type") == "number" or
                                any(choice.get("type") == "number" for choice in mastery_schema.get("anyOf", [])))
                denied = await session.call_tool("modify_question", {"uid": "函数1"})
                self.assertTrue(getattr(denied, "isError", getattr(denied, "is_error", False)))
                for forbidden in ("submit_draft", "update_draft", "discard_draft", "record_feedback",
                                  "create_review_session", "set_question_labels", "update_config"):
                    self.assertTrue((await session.call_tool(forbidden, {})).isError)
            async with _session(self.server.mcp_port, self.server.keys["read"]["secret"]) as session:
                denied = await session.call_tool("create_draft", {
                    "subject": "数学", "category": "函数", "request_id": "readonly",
                    "blocks": [{"section": "题目", "kind": "text", "text": "只读"}],
                })
                self.assertTrue(getattr(denied, "isError", getattr(denied, "is_error", False)))
            create_only = create_key(self.server.vault, "create-only", ["draft:create"])
            async with _session(self.server.mcp_port, create_only["secret"]) as session:
                self.assertTrue((await session.call_tool("get_overview", {})).isError)
                text_draft = _json_result(await session.call_tool("create_draft", {
                    "subject": "数学", "category": "纯文字", "request_id": "text-only",
                    "blocks": [{"section": "题目", "kind": "text", "text": "外部对话纯文字题干"}],
                }))
                self.assertEqual(text_draft["status"], "review")
                self.assertEqual(text_draft["source_channel"], "mcp")
                self.assertEqual(text_draft["source_images"], [])
            async with _session(self.server.mcp_port, self.server.keys["all"]["secret"]) as session:
                listed = _json_result(await session.call_tool("list_drafts", {"status": "pending", "source": "mcp"}))
                self.assertTrue(any(item["draft_id"] == text_draft["draft_id"] for item in listed["items"]))
                detail = _json_result(await session.call_tool("get_draft", {"draft_id": text_draft["draft_id"]}))
                self.assertEqual(detail["blocks"][0]["text"], "外部对话纯文字题干")
        asyncio.run(run())

    def test_existing_client_is_rejected_after_key_revocation(self):
        async def run():
            key = create_key(self.server.vault, "revoke-active", ["omrs:read"])
            active_call_completed = False
            with self.assertRaises(Exception):
                async with _session(self.server.mcp_port, key["secret"]) as session:
                    self.assertFalse((await session.call_tool("get_overview", {})).isError)
                    active_call_completed = True
                    revoke_key(self.server.vault, key["key_id"])
                    await session.call_tool("get_overview", {})
            self.assertTrue(active_call_completed)
        asyncio.run(run())

    def test_extra_parameters_and_invalid_draft_do_not_write(self):
        raw = _png(4, 3)
        encoded = {"data_base64": base64.b64encode(raw).decode(), "file_id": "invalid-file",
                   "download_url": "https://example.com/invalid"}
        async def run():
            before = drafts.counts(self.server.vault)
            async with _session(self.server.mcp_port, self.server.keys["all"]["secret"]) as session:
                for name, payload in (("get_overview", {"admin": True}), ("create_draft", {
                    "subject": "数学", "category": "函数", "request_id": "unknown-extra",
                    "uid": "函数1", "status": "done", "blocks": [{"section": "题目", "kind": "text", "text": "越权"}],
                })):
                    denied = await session.call_tool(name, payload)
                    self.assertTrue(denied.isError)
                denied = await session.call_tool("create_draft", {
                    "subject": "", "category": "函数", "request_id": "invalid-subject",
                    "blocks": [{"section": "题目", "kind": "image", "image": 0}], "images": [encoded],
                })
                self.assertTrue(denied.isError)
            self.assertEqual(drafts.counts(self.server.vault), before)
            self.assertFalse(os.path.exists(os.path.join(drafts.images_dir(self.server.vault),
                                                         hashlib.sha256(raw).hexdigest() + ".png")))
        asyncio.run(run())

    def test_query_reuses_assistant_read_semantics(self):
        async def run():
            async with _session(self.server.mcp_port, self.server.keys["all"]["secret"]) as session:
                remote = _json_result(await session.call_tool("search_questions", {"keywords": ["f(2)"]}))
                local = read_tools.search_questions({"vault": self.server.vault}, {"keywords": ["f(2)"]})
                self.assertEqual(remote["total"], local["result"]["total"])
                taxonomy = _json_result(await session.call_tool("list_taxonomy", {}))
                self.assertTrue(any(item["name"] == "数学" for item in taxonomy["subjects"]))
                overview = _json_result(await session.call_tool("get_overview", {}))
                self.assertEqual(overview["total"], local["result"]["in_scope"])
                for name, fn, args in (
                    ("get_question", read_tools.get_question, {"uid": "函数1"}),
                    ("get_recommendations", read_tools.get_recommendations, {"count": 2}),
                    ("list_sessions", read_tools.list_sessions_tool, {}),
                    ("get_session", read_tools.get_session_tool, {"session_id": self.server.session_id}),
                ):
                    remote = _json_result(await session.call_tool(name, args))
                    expected = fn({"vault": self.server.vault}, args)["result"]
                    self.assertEqual(remote, expected)
                question = _json_result(await session.call_tool("get_question", {"uid": "函数1"}))
                self.assertTrue(question["records"])
                self.assertIsNotNone(question["mastery"])
        asyncio.run(run())

    def test_create_original_images_idempotency_and_no_training_side_effect(self):
        images = [_png(), _jpeg() + b"TAIL-DATA", _gif()]
        encoded = [{"data_base64": base64.b64encode(item).decode(), "file_name": f"source-{i}",
                    "file_id": f"file-{i}", "download_url": "https://example.com/image"}
                   for i, item in enumerate(images)]
        payload = {
            "subject": "数学", "category": "MCP 外部题", "request_id": "req-images-1",
            "blocks": [{"section": "题目", "kind": "text", "text": "外部 AI 整理题干"},
                       {"section": "题目", "kind": "image", "image": 0},
                       {"section": "答案", "kind": "image", "image": 1}],
            "images": encoded, "cause": "粗心", "cause_statement": "用户提供的错因原话",
        }
        def formal_snapshot():
            files = {}
            for path in glob.glob(os.path.join(self.server.vault, "错题", "**", "*.md"), recursive=True):
                with open(path, "rb") as stream:
                    files[os.path.relpath(path, self.server.vault)] = hashlib.sha256(stream.read()).hexdigest()
            return files, read_commits(self.server.vault)
        before = formal_snapshot()
        async def run():
            async with _session(self.server.mcp_port, self.server.keys["all"]["secret"]) as session:
                first = _json_result(await session.call_tool("create_draft", payload))
                second = _json_result(await session.call_tool("create_draft", payload))
                self.assertEqual(first["source_channel"], "mcp")
                self.assertEqual(first["status"], "review")
                self.assertFalse(first.get("reused"))
                self.assertTrue(second.get("reused"))
                self.assertEqual(first["difficulty"], 5)
                self.assertEqual(first["blocks"][1]["box"], {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})
                self.assertEqual(len(first["source_images"]), 3)
                self.assertEqual(first["cause_verification"], "client_asserted")
                for raw in images:
                    digest = hashlib.sha256(raw).hexdigest()
                    with open(drafts.image_path(self.server.vault, digest), "rb") as stream:
                        self.assertEqual(stream.read(), raw)
                    # 人工审核区的普通图片接口也必须提供完整原件。
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.server.web_port}/api/drafts/image?sha={digest}",
                                                timeout=5) as response:
                        self.assertEqual(response.read(), raw)
                stored = drafts.get_draft(self.server.vault, first["draft_id"], readonly=True)
                self.assertEqual(stored["training_tasks"], [])
                self.assertEqual(stored["jobs"], [])

                concurrent_payload = {**payload, "request_id": "req-images-concurrent"}
                concurrent = await asyncio.gather(*[
                    session.call_tool("create_draft", concurrent_payload) for _ in range(3)
                ])
                concurrent_values = [_json_result(item) for item in concurrent]
                self.assertEqual(sum(1 for item in concurrent_values if not item.get("reused")), 1)
                self.assertEqual(sum(1 for item in concurrent_values if item.get("reused")), 2)
                changed_file = {**encoded[0], "data_base64": base64.b64encode(_png(3, 4)).decode()}
                conflict = await session.call_tool("create_draft", {**payload, "images": [changed_file, *encoded[1:]]})
                self.assertTrue(conflict.isError)
        asyncio.run(run())
        self.assertEqual(formal_snapshot(), before)

    def test_answer_text_merge_and_whitespace_normalized_retry(self):
        image = {"download_url": "https://example.com/answer", "file_id": "answer-file",
                 "data_base64": base64.b64encode(_png()).decode()}
        payload = {"subject": " 数学 ", "category": " 答案块 ", "request_id": " answer-merge ",
                   "knowledge_points": [" 求值 ", " "], "images": [image], "blocks": [
                       {"section": "题目", "kind": "text", "text": " 题干 "},
                       {"section": "答案", "kind": "text", "text": " 第一步 ", "note": " A "},
                       {"section": "答案", "kind": "text", "text": " 第二步 ", "note": " A "},
                       {"section": "答案", "kind": "image", "image": 0},
                       {"section": "答案", "kind": "text", "text": " 第三步 "},
                       {"section": "答案", "kind": "text", "text": " 第四步 "},
                   ]}
        async def run():
            async with _session(self.server.mcp_port, self.server.keys["all"]["secret"]) as session:
                first = _json_result(await session.call_tool("create_draft", payload))
                self.assertEqual(first["subject"], "数学")
                self.assertEqual(first["category"], "答案块")
                self.assertEqual(first["knowledge_points"], ["求值"])
                self.assertEqual([item["kind"] for item in first["blocks"]], ["text", "text", "image", "text"])
                self.assertEqual(first["blocks"][1]["text"], "第一步\n\n第二步")
                self.assertEqual(first["blocks"][1]["note"], "A")
                self.assertEqual(first["blocks"][3]["text"], "第三步\n\n第四步")
                normalized = {**payload, "subject": "数学", "category": "答案块", "request_id": "answer-merge",
                              "knowledge_points": ["求值"], "blocks": [
                                  {"section": "题目", "kind": "text", "text": "题干"},
                                  {"section": "答案", "kind": "text", "text": "第一步\n\n第二步", "note": "A"},
                                  {"section": "答案", "kind": "image", "image": 0},
                                  {"section": "答案", "kind": "text", "text": "第三步\n\n第四步"},
                              ]}
                second = _json_result(await session.call_tool("create_draft", normalized))
                self.assertTrue(second["reused"])
                self.assertEqual(first["draft_id"], second["draft_id"])
        asyncio.run(run())

    def test_key_management_responses_are_not_cacheable(self):
        base = f"http://127.0.0.1:{self.server.web_port}"
        def request(path, body=None):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as response:
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))
                return json.load(response)
        created = request("/api/mcp/keys", {"name": "cache-test", "scopes": ["omrs:read"]})["key"]
        listed = request("/api/mcp/keys")
        self.assertNotIn(created["secret"], json.dumps(listed))
        request("/api/mcp/keys/revoke", {"key_id": created["key_id"]})

    def test_web_port_rejects_mcp_credentials_and_regular_write(self):
        body = json.dumps({"subject": "数学", "category": "函数", "question": "越权"}).encode()
        credentials = ({"Authorization": f"Bearer {self.server.keys['all']['secret']}"},
                       {"X-OMRS-MCP-Key": self.server.keys["all"]["secret"]})
        for headers in credentials:
            headers = {**headers, "Content-Type": "application/json"}
            for method, path, data in (("GET", "/api/auth/session", None), ("POST", "/api/auth/login", b"{}"),
                                       ("POST", "/api/create", body), ("POST", "/api/drafts/commit", b"{}"),
                                       ("POST", "/api/feedback", b"{}"), ("POST", "/api/mcp/keys", b"{}")):
                request = urllib.request.Request(f"http://127.0.0.1:{self.server.web_port}{path}", data=data,
                                                  method=method, headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 403)

    def test_transport_rejects_untrusted_host_and_origin(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "guard-client", "version": "1"}}}
        async def run():
            async with httpx.AsyncClient(timeout=5) as client:
                for unsafe in ({"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"}):
                    response = await client.post(f"http://127.0.0.1:{self.server.mcp_port}/mcp", json=body,
                                                 headers={"Authorization": f"Bearer {self.server.keys['all']['secret']}",
                                                          "Accept": "application/json, text/event-stream", **unsafe})
                    self.assertIn(response.status_code, (400, 403, 421))
        asyncio.run(run())


@unittest.skipUnless(MCP_AVAILABLE, "可选依赖 mcp 未安装，跳过 MCP 下载适配验收")
class MCPDownloadAdapterTests(unittest.TestCase):
    def test_invalid_block_is_rejected_before_any_download(self):
        """非法附件引用/未知字段在下载前被 SDK 工具路径拒绝。"""
        from mcp.server.auth.provider import AccessToken
        from omrs.mcp.server import build_server
        with tempfile.TemporaryDirectory(prefix="omrs-mcp-invalid-") as vault:
            manager = build_server(vault)._tool_manager
            key = create_key(vault, "invalid-tool", ["draft:create"])
            token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=key["scopes"])
            payload = {"subject": "数学", "category": "非法块", "request_id": "invalid-block",
                       "images": [{"download_url": "https://example.com/file", "file_id": "file-1"}]}
            async def run():
                with patch("omrs.mcp.server.get_access_token", return_value=token), \
                        patch("omrs.mcp.server._download") as download:
                    for block in ({"section": "题目", "kind": "image", "image": 99},
                                  {"section": "题目", "kind": "text", "text": "题目", "box": {}}):
                        with self.assertRaises(Exception):
                            await manager.call_tool("create_draft", {**payload, "blocks": [block]})
                    download.assert_not_called()
            asyncio.run(run())

    def test_expired_download_url_retry_reuses_saved_draft(self):
        """下载函数使用 mock；SDK 工具校验、草稿事务和原图保存都是真实路径。"""
        from mcp.server.auth.provider import AccessToken
        from omrs.mcp.server import build_server
        with tempfile.TemporaryDirectory(prefix="omrs-mcp-download-") as vault:
            manager = build_server(vault)._tool_manager
            key = create_key(vault, "download-key", ["omrs:read", "draft:create"])
            token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=key["scopes"])
            payload = {"subject": "数学", "category": "下载图片", "request_id": "url-retry",
                       "blocks": [{"section": "题目", "kind": "image", "image": 0}],
                       "images": [{"download_url": "https://example.com/first?temporary=1", "file_id": "stable-file"}]}
            async def run():
                with patch("omrs.mcp.server.get_access_token", return_value=token):
                    with patch("omrs.mcp.server._download", return_value=_png()) as download:
                        first = await manager.call_tool("create_draft", payload)
                        download.assert_called_once()
                    second_payload = {**payload, "images": [
                        {**payload["images"][0], "download_url": "https://example.com/expired?temporary=2"}]}
                    with patch("omrs.mcp.server._download", side_effect=ValueError("已过期")) as download:
                        second = await manager.call_tool("create_draft", second_payload)
                        download.assert_not_called()
                    self.assertEqual(first["draft_id"], second["draft_id"])
                    self.assertTrue(second["reused"])
            asyncio.run(run())

    def test_safe_download_pins_public_address_and_rejects_redirect_and_large_body(self):
        """只 mock DNS/HTTPS，不访问公网或受限网络。"""
        from omrs.mcp.server import MAX_IMAGE_BYTES, _download
        public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        response = Mock(status=200)
        response.getheader.return_value = str(len(_png()))
        response.read1.side_effect = [_png(), b""]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("omrs.mcp.server.socket.getaddrinfo", return_value=public_dns), \
                patch("omrs.mcp.server._PinnedHTTPSConnection", return_value=connection) as factory:
            self.assertEqual(_download("https://example.com/image.png?signature=opaque"), _png())
            factory.assert_called_once_with("example.com", "93.184.216.34", timeout=10)
            response.status = 302
            with self.assertRaisesRegex(ValueError, "重定向"):
                _download("https://example.com/image.png")
            response.status = 200
            response.getheader.return_value = str(MAX_IMAGE_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "8MB"):
                _download("https://example.com/image.png")

        private_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch("omrs.mcp.server.socket.getaddrinfo", return_value=private_dns), \
                patch("omrs.mcp.server._PinnedHTTPSConnection") as factory:
            with self.assertRaisesRegex(ValueError, "受限网络"):
                _download("https://example.com/image.png")
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
