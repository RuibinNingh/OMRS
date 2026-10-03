"""系统运行记录：持久化、筛选分页、脱敏、并发和真实 MCP 领域边界。"""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from omrs import drafts, runtime_records as records
from omrs.creation import create_question
from omrs.ledger import read_commits
from omrs.mcp.keys import create_key
from omrs.projections import ledger_history
from omrs.server import OMRSHandler
try:
    from mcp.server.auth.provider import AccessToken
    from mcp.server.fastmcp.exceptions import ToolError
    from omrs.mcp.server import build_server
except ModuleNotFoundError:
    build_server = None


class RuntimeRecordsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.vault = temp.name

    def call(self, tool="get_overview", key="查询", **args):
        seq = records.begin(self.vault, tool, args, {"key_id": key, "name": key})
        records.finish(self.vault, seq, 12, {"total": 42})
        return seq

    def test_new_install_empty_read_does_not_create_store(self):
        from pathlib import Path
        self.assertEqual(records.list_records(self.vault, {})["summary"]["total"], 0)
        self.assertIsNone(records.detail(self.vault, 1))
        self.assertFalse(Path(records.path(self.vault)).exists())

    def test_persistence_filters_apply_before_pagination_and_statistics_cover_all_matches(self):
        self.call(subject="数学")
        self.call(subject="物理")
        self.call(subject="数学")
        latest = self.call(key="另一密钥", subject="数学")
        options = {"q": "数学", "limit": "1"}
        first = records.list_records(self.vault, options)
        self.assertEqual(first["summary"]["total"], 3)
        self.assertEqual(first["records"][0]["seq"], latest)
        second = records.list_records(self.vault, {**options, "before_seq": first["next_before_seq"]})
        self.assertEqual(second["summary"]["total"], 3)
        self.assertLess(second["records"][0]["seq"], latest)
        self.assertEqual(records.list_records(self.vault, {"key_id": "另一密钥"})["summary"]["total"], 1)
        self.assertEqual(records.list_records(self.vault, {"q": "%"})["summary"]["total"], 0)
        self.assertEqual(records.list_records(self.vault, {"since": "2099-01-01T00:00:00Z"})["summary"]["total"], 0)

    def test_only_whitelisted_summaries_are_stored_including_malicious_labels(self):
        secret, url, text = "omrs_mcp_key_private-secret", "https://example.test/image?signature=private", "机密题目正文"
        seq = records.begin(self.vault, "create_draft", {
            "subject": secret, "category": url, "images": [{"download_url": url, "data_base64": "PRIVATE_IMAGE"}],
            "blocks": [{"text": text}], "client_name": secret, "request_id": secret,
            "unknown": secret, "page": 10**1000}, {"key_id": "id", "name": "Bearer private-token"})
        records.finish(self.vault, seq, 5, {"draft_id": "dr-test", "status": "review", "reused": True,
            "blocks": [{"text": text}], "source_images": [{"download_url": url}]})
        detail = records.detail(self.vault, seq)
        self.assertEqual(detail["arguments"]["images_count"], 1)
        self.assertTrue(detail["result"]["reused"])
        with closing(sqlite3.connect(records.path(self.vault))) as db, db:
            stored = str(db.execute("SELECT * FROM records").fetchall())
        for value in (secret, url, text, "PRIVATE_IMAGE", "private-token", "signature=private"):
            self.assertNotIn(value, stored)

    def test_review_session_summary_keeps_count_and_stable_session_id_only(self):
        seq = records.begin(self.vault, "create_review_session", {
            "request_id": "private-request", "items": [
                {"question_id": "private-question", "source": "due"},
                {"question_id": "another-question", "source": "proficiency"}]})
        records.finish(self.vault, seq, 5, {"session_id": "EXP-test", "reused": True,
            "items": [{"question_id": "private-question", "uid": "private-title"}]})
        detail = records.detail(self.vault, seq)
        self.assertEqual(detail["title"], "创建正式复习计划")
        self.assertEqual(detail["arguments"], {"items_count": 2})
        self.assertEqual(detail["result"], {"session_id": "EXP-test", "reused": True, "items_count": 1})
        self.assertIn("复用已有结果", detail["summary"])
        self.assertNotIn("private", json.dumps(detail))

    def test_restart_marks_only_unfinished_calls_interrupted(self):
        finished = self.call()
        pending = records.begin(self.vault, "create_draft", {})
        self.assertEqual(records.list_records(self.vault, {"status": "running"})["summary"]["total"], 1)
        self.assertEqual(records.recover_interrupted(self.vault), 1)
        self.assertEqual(records.detail(self.vault, pending)["status"], "interrupted")
        self.assertIn("核对目标当前状态", records.detail(self.vault, pending)["summary"])
        self.assertEqual(records.detail(self.vault, finished)["status"], "success")
        self.assertEqual(records.recover_interrupted(self.vault), 0)

    def test_concurrent_call_records_keep_unique_ids_and_terminal_results(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            seqs = list(pool.map(lambda _: self.call(), range(24)))
        self.assertEqual(len(set(seqs)), 24)
        result = records.list_records(self.vault, {})
        self.assertEqual(result["summary"]["success"], 24)
        self.assertEqual(len({row["call_id"] for row in result["records"]}), 24)

    def test_invalid_filters_are_errors_even_when_store_does_not_exist(self):
        for options in ({"limit": 0}, {"before_seq": -1}, {"status": "admin"}, {"since": "2026-01-01"},
                        {"q": "x" * 201}, {"since": "2026-01-02T00:00:00Z", "until": "2026-01-01T00:00:00Z"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                records.list_records(self.vault, options)

    def test_learning_search_and_time_filters_find_matches_beyond_first_page(self):
        create_question(self.vault, "数学", "代数", 5, question_text="求解")
        create_question(self.vault, "物理", "力学", 5, question_text="受力分析")
        result = ledger_history(self.vault, limit=1, summary_only=True, q="代数")
        self.assertEqual(result[0]["payload"]["question"]["subject"], "数学")
        self.assertEqual(ledger_history(self.vault, since="2099-01-01T00:00:00+00:00"), [])

    def test_runtime_routes_use_web_authorization_and_reject_mcp_credentials(self):
        handler = object.__new__(OMRSHandler)
        handler.vault_path, handler.path = self.vault, "/api/runtime/records"
        handler.headers = {"Authorization": "Bearer should-not-authorize-web"}
        responses = []
        handler._json = lambda value, status=200: responses.append((value, status))
        handler.do_GET()
        self.assertEqual(responses[-1][1], 403)
        handler.headers = {}
        handler._authorize = lambda *_: False
        handler.do_GET()
        self.assertEqual(len(responses), 1)
        handler._authorize = lambda *_: True
        handler.do_GET()
        self.assertEqual(responses[-1][1], 200)
        handler.path = "/api/runtime/records/detail?seq=999"
        handler.do_GET()
        self.assertEqual(responses[-1][1], 404)

    def test_store_corruption_reports_failure_but_learning_detail_remains_available(self):
        from pathlib import Path
        from omrs.ledger import append_commit
        commit = append_commit(self.vault, "api", "question.create", "草稿入库", {
            "question": {"uid": "代数1"}, "_draft": {"draft_id": "dr-example"}})
        Path(records.path(self.vault)).write_bytes(b"invalid sqlite")
        handler = object.__new__(OMRSHandler)
        handler.vault_path, handler.headers = self.vault, {}
        handler._authorize = lambda *_: True
        responses = []
        handler._json = lambda value, status=200: responses.append((value, status))
        handler.path = "/api/runtime/records"
        handler.do_GET()
        self.assertEqual(responses[-1][1], 503)
        handler.path = f'/api/history/detail?seq={commit["seq"]}'
        handler.do_GET()
        detail, status = responses[-1]
        self.assertEqual(status, 200)
        self.assertEqual(detail["detail"]["payload"]["question"]["uid"], "代数1")
        self.assertEqual(detail["detail"]["runtime_calls"], [])
        self.assertIn("暂时无法读取", detail["detail"]["runtime_calls_error"])


@unittest.skipUnless(build_server, "可选 MCP SDK 未安装")
class MCPRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.vault = temp.name
        self.key = create_key(self.vault, "外部助手", ["omrs:read", "draft:create"])
        self.token = AccessToken(token=self.key["secret"], client_id=self.key["key_id"], scopes=self.key["scopes"])
        self.server = build_server(self.vault)

    def run_tool(self, name, args):
        async def run():
            with patch("omrs.mcp.server.get_access_token", return_value=self.token):
                return await self.server.call_tool(name, args)
        return asyncio.run(run())

    def test_real_tool_success_and_errors_are_recorded_without_creating_learning_nodes(self):
        self.run_tool("get_overview", {})
        for tool, args, code in (("get_overview", {"extra": self.key["secret"]}, "invalid_arguments"),
                                 ("not-open", {}, "unknown_tool")):
            with self.assertRaises(ToolError):
                self.run_tool(tool, args)
            self.assertEqual(records.list_records(self.vault, {})["records"][0]["error_code"], code)
        self.assertEqual(records.list_records(self.vault, {})["summary"]["total"], 3)
        self.assertEqual(read_commits(self.vault), [])

    def test_image_call_is_identified_without_persisting_raw_or_base64_content(self):
        from tests.test_mcp_protocol import _png
        raw = _png() + b"PRIVATE-MCP-IMAGE-TAIL"
        encoded = base64.b64encode(raw).decode()
        uid = create_question(self.vault, "物理", "图像记录", 5,
                              question_images=["data:image/png;base64," + encoded])["uid"]
        commits = read_commits(self.vault)
        result = self.run_tool("get_question_image", {"uid": uid, "image_index": 0})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, "image")
        self.assertEqual(base64.b64decode(result[0].data), raw)
        latest = records.list_records(self.vault, {})["records"][0]
        self.assertEqual((latest["tool"], latest["title"], latest["status"]),
                         ("get_question_image", "读取题图", "success"))
        detail = records.detail(self.vault, latest["seq"])
        self.assertEqual(detail["arguments"], {"uid": uid, "image_index": 0})
        self.assertEqual(detail["result"], {})
        with closing(sqlite3.connect(records.path(self.vault))) as db, db:
            stored = str(db.execute("SELECT * FROM records").fetchall())
        for private in (encoded, "PRIVATE-MCP-IMAGE-TAIL", self.key["secret"]):
            self.assertNotIn(private, stored)
        self.assertEqual(read_commits(self.vault), commits)
        self.assertEqual(drafts.list_drafts(self.vault, readonly=True), [])

    def test_read_only_key_denial_is_visible_and_cannot_create_draft(self):
        self.key = create_key(self.vault, "仅查询", ["omrs:read"])
        self.token = AccessToken(token=self.key["secret"], client_id=self.key["key_id"], scopes=["omrs:read"])
        with self.assertRaisesRegex(ToolError, "^forbidden:"):
            self.run_tool("create_draft", {})
        row = records.list_records(self.vault, {})["records"][0]
        self.assertEqual((row["key_name"], row["status"], row["error_code"]), ("仅查询", "failure", "forbidden"))
        self.assertEqual(drafts.list_drafts(self.vault), [])

    def test_create_retry_and_human_commit_are_linked_without_changing_original_results(self):
        args = {"subject": "数学", "category": "代数", "request_id": "req-1",
                "blocks": [{"section": "题目", "kind": "text", "text": "求解 1+1"}]}
        self.run_tool("create_draft", args)
        self.run_tool("create_draft", args)
        latest = records.list_records(self.vault, {})["records"][0]
        draft = drafts.get_draft(self.vault, latest["draft_id"])
        self.assertTrue(records.detail(self.vault, latest["seq"])["result"]["reused"])
        drafts.commit_draft(self.vault, draft["id"], draft["revision"])
        detail = records.detail(self.vault, latest["seq"])
        self.assertEqual(detail["draft"]["status"], "done")
        self.assertEqual(len(detail["related_commits"]), 1)
        self.assertEqual(len(records.calls_for_draft(self.vault, draft["id"])), 2)

    def test_storage_failure_does_not_change_tool_result_and_cancellation_is_visible(self):
        with patch("omrs.runtime_records.begin", side_effect=OSError("private storage path")), self.assertLogs("omrs.runtime", level="WARNING") as logged:
            self.run_tool("get_overview", {})
        self.assertNotIn("private storage path", str(logged.output))
        with patch.object(self.server, "_execute_tool", side_effect=asyncio.CancelledError), self.assertRaises(asyncio.CancelledError):
            self.run_tool("get_overview", {})
        self.assertEqual(records.list_records(self.vault, {})["records"][0]["status"], "interrupted")
