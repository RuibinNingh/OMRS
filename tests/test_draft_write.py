"""草稿审核、入库身份与故障恢复。全部测试使用临时 Vault。"""
import concurrent.futures
import http.client
import json
import os
import tempfile
import socketserver
import subprocess
import sys
import threading
import unittest
from unittest import mock

from omrs import drafts
from omrs import draft_write
from omrs import creation
from omrs.common import split_sections
from omrs.ledger import read_commits
from tests.test_drafts import make_png, data_url, QuietHandler


def text_blocks():
    return [{"section": "题目", "kind": "text", "text": "先"},
            {"section": "题目", "kind": "text", "text": "后"},
            {"section": "答案", "kind": "text", "text": "解"}]


class DraftWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.origin = {"conversation_id": "conv", "run_id": "run", "tool_call_id": "call"}

    def create(self, blocks=None, source_images=None):
        data = {"subject": "数学", "category": "函数", "blocks": blocks or text_blocks()}
        if source_images is not None:
            data["source_images"] = source_images
        return drafts.create_draft(self.vault, data, self.origin)

    def commits(self, draft_id):
        return [c for c in read_commits(self.vault) if c["payload"].get("_draft", {}).get("draft_id") == draft_id]

    def test_sources_include_text_only_and_old_unknown_is_not_guessed(self):
        one = drafts.add_image(self.vault, data_url(make_png(4, 4)), "conv", "run")
        two = drafts.add_image(self.vault, data_url(make_png(5, 5)), "conv", "run")
        d = self.create(source_images=[two["sha256"], one["sha256"]])
        self.assertEqual([i["ref"] for i in d["source_images"]], ["IMG-2", "IMG-1"])
        self.assertTrue(d["sources_complete"])
        self.assertEqual(len(d["conversation_images"]), 2)
        old = self.create()
        self.assertFalse(old["sources_complete"])
        self.assertEqual(old["source_images"], [])
        self.assertEqual(len(old["conversation_images"]), 2)
        saved = drafts.update_draft(self.vault, old["id"], 1, {"note": "补备注"},
                                    old["blocks"], source_images=[])
        self.assertFalse(saved["sources_complete"])
        linked = drafts.update_draft(self.vault, old["id"], 2, {}, saved["blocks"],
                                     source_images=[one["sha256"]])
        self.assertTrue(linked["sources_complete"])

    def test_exact_old_source_recovery_from_tool_call(self):
        from omrs.agent.store import AgentStore
        one = drafts.add_image(self.vault, data_url(make_png(4, 4)), "conv", "run")
        two = drafts.add_image(self.vault, data_url(make_png(5, 5)), "conv", "run")
        old = self.create()
        AgentStore(self.vault).save_tool_call("run", "call", "create_draft", "rev",
                                               {"images": ["IMG-2"]}, "done")
        loaded = drafts.get_draft(self.vault, old["id"])
        self.assertTrue(loaded["sources_complete"])
        self.assertEqual([i["sha256"] for i in loaded["source_images"]], [two["sha256"]])
        self.assertNotIn(one["sha256"], [i["sha256"] for i in loaded["source_images"]])

    def test_update_is_atomic_and_revision_protects_content(self):
        d = self.create()
        bad = [{**d["blocks"][0], "text": "已改"}, {**d["blocks"][1], "kind": "image", "image_sha": "missing"}, d["blocks"][2]]
        with self.assertRaises(drafts.DraftError):
            drafts.update_draft(self.vault, d["id"], 1, {"cause": "人工补充"}, bad)
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["cause"], "")
        blocks = [{**b, "text": "更新" if i == 0 else b["text"]} for i, b in enumerate(d["blocks"])]
        updated = drafts.update_draft(self.vault, d["id"], 1, {"cause": "人工补充"}, blocks)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["blocks"][0]["id"], d["blocks"][0]["id"])
        with self.assertRaises(drafts.DraftError) as caught:
            drafts.update_draft(self.vault, d["id"], 1, {}, blocks)
        self.assertEqual((caught.exception.status, caught.exception.current_revision), (409, 2))

    def test_order_and_draft_origin_are_in_persisted_question(self):
        added = drafts.add_image(self.vault, data_url(make_png(4, 4)), "conv", "run")
        d = self.create([{"section": "题目", "kind": "text", "text": "第一段"},
                         {"section": "题目", "kind": "image", "image_sha": added["sha256"]},
                         {"section": "题目", "kind": "text", "text": "第二段"},
                         {"section": "答案", "kind": "text", "text": "结果"}], [added["sha256"]])
        blocks = [{**b, "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "box_origin": "manual"}
                  if b["kind"] == "image" else b for b in d["blocks"]]
        d = drafts.update_draft(self.vault, d["id"], d["revision"], {}, blocks)
        self.assertEqual(d["status"], "review")
        result = drafts.commit_draft(self.vault, d["id"], d["revision"])
        self.assertEqual(result["draft"]["status"], "done")
        path = os.path.join(self.vault, result["result"]["file_path"])
        with open(path, encoding="utf-8") as file:
            body = split_sections(file.read())["题目"]
        self.assertLess(body.index("第一段"), body.index("![["))
        self.assertLess(body.index("![["), body.index("第二段"))
        self.assertEqual(self.commits(d["id"])[0]["payload"]["_draft"],
                         {"draft_id": d["id"], "conversation_id": "conv"})

    def test_concurrent_commit_and_lost_response_reuse_one_ledger_commit(self):
        d = self.create()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(drafts.commit_draft, self.vault, d["id"], 1) for _ in range(2)]
            results = [f.result() for f in futures]
        self.assertEqual(len(self.commits(d["id"])), 1)
        self.assertEqual({r["result"]["question_id"] for r in results},
                         {results[0]["result"]["question_id"]})
        self.assertEqual(sorted(r["reused"] for r in results), [False, True])
        self.assertTrue(drafts.commit_draft(self.vault, d["id"], 1)["reused"])

    def test_archived_question_stays_done_and_is_not_recreated(self):
        from omrs.question_ops import delete_question
        d = self.create()
        result = drafts.commit_draft(self.vault, d["id"], 1)
        self.assertTrue(result["draft"]["question_available"])
        delete_question(self.vault, result["result"]["uid"])
        self.assertFalse(drafts.get_draft(self.vault, d["id"])["question_available"])
        retried = drafts.commit_draft(self.vault, d["id"], 1)
        self.assertTrue(retried["reused"])
        self.assertFalse(retried["draft"]["question_available"])
        self.assertEqual(len(self.commits(d["id"])), 1)

    def test_ledger_after_exception_then_restart_recovers_without_deleting_file(self):
        d = self.create()
        real = creation.append_commit
        def appended_then_lost(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("响应丢失")
        with mock.patch.object(creation, "append_commit", side_effect=appended_then_lost):
            with self.assertRaises(OSError):
                drafts.commit_draft(self.vault, d["id"], 1)
        committed = self.commits(d["id"])
        self.assertEqual(len(committed), 1)
        path = os.path.join(self.vault, committed[0]["payload"]["question"]["file_path"])
        self.assertTrue(os.path.isfile(path))
        # 新 Python 进程模拟服务重启，不依赖进程内锁或缓存。
        output = subprocess.check_output([sys.executable, "-c",
            "import json,sys;from omrs import drafts;print(json.dumps(drafts.commit_draft(sys.argv[1],sys.argv[2],1)))",
            self.vault, d["id"]], cwd=os.getcwd(), text=True)
        result = json.loads(output)
        self.assertTrue(result["reused"])
        self.assertEqual(result["draft"]["status"], "done")
        self.assertEqual(len(self.commits(d["id"])), 1)

    def test_projection_failure_recovers_without_duplicate(self):
        d = self.create()
        with mock.patch.object(creation, "rebuild_projection", side_effect=OSError("投影失败")):
            with self.assertRaises(OSError):
                drafts.commit_draft(self.vault, d["id"], 1)
        self.assertEqual(len(self.commits(d["id"])), 1)
        result = drafts.commit_draft(self.vault, d["id"], 1)
        self.assertTrue(result["reused"])
        self.assertEqual(len(self.commits(d["id"])), 1)

    def test_preledger_failure_then_edit_releases_prepared_identity(self):
        d = self.create()
        with mock.patch.object(creation, "append_commit", side_effect=OSError("Ledger 前失败")):
            with self.assertRaises(OSError):
                drafts.commit_draft(self.vault, d["id"], 1)
        self.assertEqual(self.commits(d["id"]), [])
        edited = drafts.update_draft(self.vault, d["id"], 1, {"cause": "人工编辑"}, d["blocks"])
        self.assertEqual(edited["revision"], 2)
        with drafts.connect(self.vault) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM commit_operations WHERE draft_id=?", (d["id"],)).fetchone())
        result = drafts.commit_draft(self.vault, d["id"], 2)
        self.assertFalse(result["reused"])
        self.assertEqual(len(self.commits(d["id"])), 1)

    def test_postledger_failure_blocks_edit_and_discard_then_recovers(self):
        d = self.create()
        real = creation.append_commit
        def append_then_raise(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("Ledger 后失败")
        with mock.patch.object(creation, "append_commit", side_effect=append_then_raise):
            with self.assertRaises(OSError):
                drafts.commit_draft(self.vault, d["id"], 1)
        with self.assertRaises(drafts.DraftError) as caught:
            drafts.update_draft(self.vault, d["id"], 1, {"cause": "不能覆盖"}, d["blocks"])
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(drafts.get_draft(self.vault, d["id"])["status"], "done")
        with self.assertRaises(drafts.DraftError):
            drafts.discard_draft(self.vault, d["id"], 2)
        self.assertEqual(len(self.commits(d["id"])), 1)

    def test_existing_foreign_question_file_is_never_overwritten(self):
        d = self.create()
        real = creation.create_question
        def preexisting(*args, **kwargs):
            identity = kwargs["reserved_identity"]
            from omrs.migration import ensure_ledger_bootstrap
            ensure_ledger_bootstrap(self.vault)
            root = os.path.join(self.vault, "错题", "数学", "函数")
            os.makedirs(root, exist_ok=True)
            with open(os.path.join(root, identity["uid"] + ".md"), "w", encoding="utf-8") as file:
                file.write("用户题目")
            return real(*args, **kwargs)
        with mock.patch.object(draft_write.creation, "create_question", side_effect=preexisting):
            with self.assertRaisesRegex(ValueError, "不能覆盖"):
                drafts.commit_draft(self.vault, d["id"], 1)
        with open(os.path.join(self.vault, "错题", "数学", "函数", "函数1.md"), encoding="utf-8") as file:
            self.assertEqual(file.read(), "用户题目")
        self.assertEqual(self.commits(d["id"]), [])

    def test_discard_does_not_write_ledger_and_is_repeatable(self):
        d = self.create()
        discarded = drafts.discard_draft(self.vault, d["id"], 1)
        self.assertEqual(discarded["status"], "discarded")
        self.assertEqual(drafts.discard_draft(self.vault, d["id"], 1)["revision"], 2)
        self.assertEqual(self.commits(d["id"]), [])
        with self.assertRaises(drafts.DraftError):
            drafts.update_draft(self.vault, d["id"], 2, {}, d["blocks"])


class DraftHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        os.makedirs(os.path.join(self.vault, "错题"), exist_ok=True)
        QuietHandler.vault_path = self.vault
        self.server = socketserver.TCPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.thread.join, 2)

    def request(self, path, data):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1])
        conn.request("POST", path, json.dumps(data).encode(), {"Content-Type": "application/json"})
        response = conn.getresponse()
        status, payload = response.status, json.loads(response.read())
        conn.close()
        return status, payload

    def test_update_commit_and_structured_conflicts(self):
        d = drafts.create_draft(self.vault, {"subject": "数学", "category": "函数", "blocks": text_blocks()},
                                {"conversation_id": "conv"})
        status, payload = self.request("/api/drafts/update", {
            "id": d["id"], "revision": 1, "fields": {"cause": "人工写的错因"}, "blocks": d["blocks"]})
        self.assertEqual(status, 200)
        self.assertEqual(payload["draft"]["revision"], 2)
        status, payload = self.request("/api/drafts/update", {
            "id": d["id"], "revision": 1, "fields": {}, "blocks": d["blocks"]})
        self.assertEqual(status, 409)
        self.assertEqual((payload["code"], payload["current_revision"]), ("revision_conflict", 2))
        status, payload = self.request("/api/drafts/commit", {"id": d["id"], "revision": 2})
        self.assertEqual(status, 200)
        self.assertEqual(payload["draft"]["status"], "done")
        self.assertTrue({"uid", "question_id", "file_path"} <= set(payload["result"]))
        status, payload = self.request("/api/drafts/commit", {"id": d["id"], "revision": 2})
        self.assertEqual((status, payload["reused"]), (200, True))
        status, payload = self.request("/api/drafts/discard", {"id": d["id"], "revision": 3})
        self.assertEqual((status, payload["code"]), (409, "state_conflict"))

    def test_missing_draft_and_bad_config(self):
        status, payload = self.request("/api/drafts/discard", {"id": "missing", "revision": 1})
        self.assertEqual((status, payload["code"]), (404, "not_found"))
        status, payload = self.request("/api/config", {"draft_mode": "automatic"})
        self.assertEqual(status, 400)
        self.assertIn("draft_mode", payload["msg"])


if __name__ == "__main__":
    unittest.main()
