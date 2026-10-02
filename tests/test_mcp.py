"""MCP 密钥、能力白名单和外部草稿图片链路。"""

import asyncio
import base64
import hashlib
import os
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

from omrs import drafts
from omrs.mcp.keys import create_key, list_keys, revoke_key, verify_key
try:
    from omrs.mcp.server import _download, build_server
    HAS_MCP_SDK = True
except ModuleNotFoundError as exc:
    if exc.name != "mcp":
        raise
    _download = build_server = None
    HAS_MCP_SDK = False


def png(width=2, height=3):
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class MCPKeyTests(unittest.TestCase):
    def test_secret_only_returned_at_creation_and_revoke_is_immediate(self):
        with tempfile.TemporaryDirectory() as vault:
            made = create_key(vault, "外部助手", ["omrs:read"])
            self.assertTrue(made["secret"].startswith("omrs_mcp_"))
            self.assertNotIn("secret", list_keys(vault)[0])
            self.assertEqual(verify_key(vault, made["secret"])["key_id"], made["key_id"])
            revoke_key(vault, made["key_id"])
            self.assertIsNone(verify_key(vault, made["secret"]))

    def test_expired_and_invalid_scopes_rejected(self):
        with tempfile.TemporaryDirectory() as vault:
            with self.assertRaises(ValueError):
                create_key(vault, "bad", ["omrs:admin"])
            with self.assertRaises(ValueError):
                create_key(vault, "expired", None, "2020-01-01T00:00:00+00:00")


@unittest.skipUnless(HAS_MCP_SDK, "可选 MCP SDK 未安装")
class MCPPolicyTests(unittest.TestCase):
    def test_registry_is_fixed_and_has_file_metadata(self):
        with tempfile.TemporaryDirectory() as vault:
            server = build_server(vault)
            names = [tool.name for tool in server._tool_manager.list_tools()]
            self.assertEqual(names, [
                "list_taxonomy", "search_questions", "get_question", "get_question_image", "get_overview",
                "get_recommendations", "list_sessions", "get_session", "list_drafts",
                "get_draft", "create_draft",
            ])
            create = server._tool_manager.get_tool("create_draft")
            self.assertEqual(create.meta["openai/fileParams"], ["images"])
            from omrs.mcp.server import TOOL_SCOPES
            self.assertEqual(set(TOOL_SCOPES), set(names))
            self.assertEqual({name for name, scope in TOOL_SCOPES.items() if scope == "draft:create"}, {"create_draft"})

    def test_discovery_uses_live_scopes_and_unmapped_tool_is_never_callable(self):
        from mcp.server.auth.provider import AccessToken
        from mcp.server.fastmcp.exceptions import ToolError
        with tempfile.TemporaryDirectory() as vault:
            key = create_key(vault, "当前仅写", ["draft:create"])
            # 旧 token 对象的 scope 不能覆盖磁盘上的当前权限。
            token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=["omrs:read", "draft:create"])
            server = build_server(vault)
            called = []

            def future_tool():
                called.append(True)
                return {"result": "不应执行"}

            server.add_tool(future_tool, name="future_tool")

            async def run():
                with patch("omrs.mcp.server.get_access_token", return_value=token):
                    self.assertEqual([tool.name for tool in await server.list_tools()], ["create_draft"])
                    with self.assertRaisesRegex(ToolError, "^forbidden:"):
                        await server.call_tool("get_overview", {})
                    with self.assertRaisesRegex(ToolError, "^unknown_tool:"):
                        await server.call_tool("future_tool", {})
            asyncio.run(run())
            self.assertEqual(called, [])
            self.assertEqual(len(server._tool_manager.list_tools()), 12)

    def test_ssrf_loopback_and_non_https_are_rejected_before_download(self):
        with self.assertRaises(ValueError):
            _download("http://127.0.0.1/image.png")
        with self.assertRaises(ValueError):
            _download("https://127.0.0.1/image.png")

    def test_image_tool_schema_and_readonly_annotations(self):
        with tempfile.TemporaryDirectory() as vault:
            image = build_server(vault)._tool_manager.get_tool("get_question_image")
            schema = image.parameters
            self.assertEqual(schema["required"], ["uid", "image_index"])
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["properties"]["uid"]["maxLength"], 200)
            self.assertEqual(schema["properties"]["uid"]["pattern"], r"\S")
            self.assertEqual(schema["properties"]["image_index"]["type"], "integer")
            self.assertEqual(schema["properties"]["image_index"]["minimum"], 0)
            self.assertIsNone(image.fn_metadata.output_schema)
            self.assertTrue(image.annotations.readOnlyHint)
            self.assertFalse(image.annotations.destructiveHint)
            self.assertTrue(image.annotations.idempotentHint)
            self.assertFalse(image.annotations.openWorldHint)

    def test_image_invalid_parameters_are_rejected_before_filesystem_reads(self):
        from mcp.server.auth.provider import AccessToken
        from mcp.server.fastmcp.exceptions import ToolError
        with tempfile.TemporaryDirectory() as vault:
            key = create_key(vault, "读图", ["omrs:read"])
            token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=key["scopes"])
            server = build_server(vault)
            invalid = [{}, {"uid": "示例1"}, {"uid": "", "image_index": 0},
                       {"uid": " \t\n\u3000", "image_index": 0},
                       {"uid": "x" * 201, "image_index": 0},
                       {"uid": "示例1", "image_index": 0, "path": "/private"},
                       *({"uid": "示例1", "image_index": value}
                         for value in (-1, True, False, "0", .5, 1.0, None))]

            async def run():
                with patch("omrs.mcp.server.get_access_token", return_value=token), \
                        patch("omrs.mcp.server.read_question_image") as read:
                    for args in invalid:
                        with self.subTest(args=args), self.assertRaisesRegex(ToolError, "^invalid_arguments:"):
                            await server.call_tool("get_question_image", args)
                    read.assert_not_called()
            asyncio.run(run())

    def test_image_rechecks_live_permission_after_actual_read(self):
        from mcp.server.auth.provider import AccessToken
        from mcp.server.fastmcp.exceptions import ToolError
        from omrs.creation import create_question
        from omrs.mcp import keys, server as module
        for mode in ("revoke", "expire", "scope"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as vault:
                raw = png()
                uid = create_question(vault, "物理", "权限读图", 5,
                    question_images=["data:image/png;base64," + base64.b64encode(raw).decode()])["uid"]
                key = create_key(vault, "读图", ["omrs:read"])
                token = AccessToken(token=key["secret"], client_id=key["key_id"], scopes=key["scopes"])
                server = build_server(vault)
                entered, release = threading.Event(), threading.Event()
                original = module.read_question_image

                def paused(*args):
                    image = original(*args)
                    self.assertEqual(image, (raw, "png"))
                    entered.set()
                    if not release.wait(5):
                        raise AssertionError("读图鉴权窗口未释放")
                    return image

                async def run():
                    with patch.object(module, "get_access_token", return_value=token), \
                            patch.object(module, "read_question_image", side_effect=paused), \
                            patch.object(module, "MCPImage") as response:
                        task = asyncio.create_task(server.call_tool("get_question_image",
                                                                    {"uid": uid, "image_index": 0}))
                        try:
                            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                            if mode == "revoke":
                                revoke_key(vault, key["key_id"])
                            else:
                                with keys._key_lock(vault):
                                    data = keys._load(vault)
                                    row = next(row for row in data["keys"] if row["key_id"] == key["key_id"])
                                    if mode == "expire":
                                        row["expires_at"] = "2020-01-01T00:00:00+00:00"
                                    else:
                                        row["scopes"] = ["draft:create"]
                                    keys._save(vault, data)
                        finally:
                            release.set()
                        with self.assertRaisesRegex(ToolError, "^forbidden:"):
                            await asyncio.wait_for(task, 10)
                        response.assert_not_called()
                asyncio.run(run())


class MCPDraftTests(unittest.TestCase):
    def test_raw_image_and_mcp_draft_are_review_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            conversation = "mcp:key:req-1"
            image = drafts.add_mcp_image(vault, raw, conversation, "req-1")
            origin = {"conversation_id": conversation, "source_channel": "mcp", "source_key_id": "key",
                      "source_request_id": "req-1", "content_hash": "digest"}
            data = {"subject": "数学", "category": "外部", "blocks": [
                {"section": "题目", "kind": "image", "image_sha": image["sha256"]},
                {"section": "答案", "kind": "text", "text": "答案"}],
                "source_images": [image["sha256"]]}
            draft = drafts.create_draft(vault, data, origin)
            self.assertEqual(draft["status"], "review")
            self.assertEqual(draft["source_channel"], "mcp")
            self.assertEqual(draft["training_tasks"], [])
            self.assertEqual(draft["blocks"][0]["box"], {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})
            with open(drafts.image_path(vault, image["sha256"]), "rb") as stream:
                self.assertEqual(stream.read(), raw)
            reused = drafts.create_draft(vault, data, origin)
            self.assertTrue(reused["reused"])
            with self.assertRaisesRegex(drafts.DraftError, "内容不同"):
                drafts.create_draft(vault, {**data, "category": "另一个"}, {**origin, "content_hash": "other"})

    def test_mcp_edit_does_not_auto_create_training_task(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = png()
            conversation = "mcp:key:req-edit"
            image = drafts.add_mcp_image(vault, raw, conversation, "req-edit")
            origin = {"conversation_id": conversation, "source_channel": "mcp", "source_key_id": "key",
                      "source_request_id": "req-edit", "content_hash": "digest"}
            data = {"subject": "数学", "category": "外部", "blocks": [
                {"section": "题目", "kind": "image", "image_sha": image["sha256"]}],
                "source_images": [image["sha256"]]}
            draft = drafts.create_draft(vault, data, origin)
            updated = drafts.update_draft(vault, draft["id"], draft["revision"], {}, draft["blocks"])
            self.assertEqual(updated["training_tasks"], [])

    def test_source_filter_is_applied_before_list_limit(self):
        with tempfile.TemporaryDirectory() as vault:
            data = {"subject": "数学", "category": "草稿", "blocks": [
                {"section": "题目", "kind": "text", "text": "待审核"}]}
            mcp = drafts.create_mcp_draft(vault, data, {
                "conversation_id": "mcp:key:older", "source_key_id": "key", "source_request_id": "older"})
            agent = drafts.create_draft(vault, data, {"conversation_id": "agent-newer"})
            db = drafts.connect(vault)
            try:
                db.execute("UPDATE drafts SET created_at=? WHERE id=?", ("2020-01-01", mcp["id"]))
                db.execute("UPDATE drafts SET created_at=? WHERE id=?", ("2021-01-01", agent["id"]))
                db.commit()
            finally:
                db.close()
            rows = drafts.list_drafts(vault, limit=1, readonly=True, source_channel="mcp")
            self.assertEqual([row["id"] for row in rows], [mcp["id"]])

    def test_mcp_image_pixel_limit_is_enforced_before_write(self):
        with tempfile.TemporaryDirectory() as vault:
            raw = bytearray(png())
            raw[16:20] = (100_000).to_bytes(4, "big")
            raw[20:24] = (1_000).to_bytes(4, "big")
            with self.assertRaisesRegex(ValueError, "像素超过"):
                drafts.add_mcp_image(vault, bytes(raw), "mcp:key:req-pixels", "req-pixels")


if __name__ == "__main__":
    unittest.main()
