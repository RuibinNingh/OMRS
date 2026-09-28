"""ai-draft P1-3：草稿工具。建草稿（状态推导、图片引用、错因原话校验、不写 Ledger）、查草稿、看图追问、写入预算。"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs import drafts  # noqa: E402
from omrs.agent.loop import AgentLoop  # noqa: E402
from omrs.agent.config import settings, validate_agent_config  # noqa: E402
from omrs.agent.runtime import Hooks, Run  # noqa: E402
from omrs.agent.revert import plan_revert  # noqa: E402
from omrs.agent.store import AgentStore  # noqa: E402
from omrs.agent.tools import Registry, ToolDef, build_registry  # noqa: E402
from omrs.agent.tools import drafts as tools  # noqa: E402
from omrs.creation import create_question  # noqa: E402
from omrs.common import save_config  # noqa: E402
from omrs.ledger import read_commits  # noqa: E402
from tests.test_agent_loop import LIMITS, Stub, reply  # noqa: E402
from tests.test_drafts import data_url, make_png  # noqa: E402

TEXT_ARGS = {"subject": "数学", "category": "函数",
             "blocks": [{"section": "题目", "kind": "text", "text": "求 $y=x^2$ 的最小值"},
                        {"section": "答案", "kind": "text", "text": "0"}]}


class DraftToolsTest(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-dt-")
        os.makedirs(os.path.join(self.vault, "错题"))
        create_question(self.vault, "数学", "函数", 5, question_text="已有题", answer_text="略")
        self.store = AgentStore(self.vault)
        self.conv = self.store.create_conversation("conv_a", "测试")["id"]
        self.ctx = {"vault": self.vault, "conversation_id": self.conv, "run_id": "run_x", "tool_call_id": "c1"}

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def say(self, text):
        self.store.add_message(self.conv, "run_x", {"role": "user", "content": text})

    def img(self, n=1):
        return drafts.add_image(self.vault, data_url(make_png(4 + n, 4)), self.conv, "run_x")["ref"]

    def test_text_draft_is_review_and_writes_no_commit(self):
        before = len(read_commits(self.vault))
        out = tools.create_draft_tool(self.ctx, TEXT_ARGS)
        self.assertTrue(out["wrote"])
        r = out["result"]
        self.assertEqual(r["status"], "review")
        self.assertEqual(r["question_preview"], "求 $y=x^2$ 的最小值")
        self.assertEqual(len(read_commits(self.vault)), before)
        draft = drafts.get_draft(self.vault, r["draft_id"])
        self.assertEqual((draft["run_id"], draft["tool_call_id"], draft["difficulty"]), ("run_x", "c1", 5))
        self.assertEqual(plan_revert(self.vault, "run_x").get("items", []), [])  # 草稿不进按运行撤销

    def test_image_block_is_cropping_and_refs_checked(self):
        ref = self.img()
        args = {**TEXT_ARGS, "images": [ref],
                "blocks": [TEXT_ARGS["blocks"][0], {"section": "答案", "kind": "image", "image": ref, "note": "下半部分"}]}
        r = tools.create_draft_tool(self.ctx, args)["result"]
        self.assertEqual(r["status"], "cropping")
        self.assertEqual(r["blocks"][1], {"section": "答案", "kind": "image", "image": "IMG-1", "note": "下半部分"})
        with self.assertRaisesRegex(ValueError, "不在 images 列表里"):
            tools.create_draft_tool(self.ctx, {**args, "images": []})
        with self.assertRaisesRegex(ValueError, "本对话里没有 IMG-9"):
            tools.create_draft_tool(self.ctx, {**args, "images": ["IMG-9"]})
        other = self.store.create_conversation("conv_b", "别的")["id"]
        with self.assertRaisesRegex(ValueError, "本对话里没有 IMG-1"):
            tools.create_draft_tool({**self.ctx, "conversation_id": other}, args)

    def test_cause_needs_user_statement(self):
        with self.assertRaisesRegex(ValueError, "错因只能用用户说过的话"):
            tools.create_draft_tool(self.ctx, {**TEXT_ARGS, "cause": "粗心"})
        self.say("录一下，错因是 忘了配方 ，下次注意")
        with self.assertRaisesRegex(ValueError, "错因只能用用户说过的话"):
            tools.create_draft_tool(self.ctx, {**TEXT_ARGS, "cause": "粗心", "cause_statement": "我太粗心了"})
        r = tools.create_draft_tool(self.ctx, {**TEXT_ARGS, "cause": "忘了配方", "cause_statement": "忘了 配方"})["result"]
        draft = drafts.get_draft(self.vault, r["draft_id"])
        self.assertEqual((draft["cause"], draft["cause_statement"]), ("忘了配方", "忘了 配方"))
        self.assertEqual(drafts.list_drafts(self.vault).__len__(), 1)  # 失败的两次都没建行

    def test_statement_without_cause_is_dropped(self):
        r = tools.create_draft_tool(self.ctx, {**TEXT_ARGS, "cause_statement": "随便"})["result"]
        self.assertEqual(drafts.get_draft(self.vault, r["draft_id"])["cause_statement"], "")

    def test_list_and_get(self):
        a = tools.create_draft_tool(self.ctx, TEXT_ARGS)["result"]["draft_id"]
        other = self.store.create_conversation("conv_b", "别的")["id"]
        tools.create_draft_tool({**self.ctx, "conversation_id": other}, TEXT_ARGS)
        mine = tools.list_drafts_tool(self.ctx, {})["result"]
        self.assertEqual([d["draft_id"] for d in mine["items"]], [a])
        self.assertEqual(tools.list_drafts_tool(self.ctx, {"all_conversations": True})["result"]["total"], 2)
        got = tools.get_draft_tool(self.ctx, {"draft_id": a})["result"]
        self.assertEqual([b["kind"] for b in got["blocks"]], ["text", "text"])
        with self.assertRaises(ValueError):
            tools.get_draft_tool(self.ctx, {"draft_id": "DR-nope"})

    def test_describe_image(self):
        ref = self.img()
        with mock.patch.object(tools, "ask_image", return_value="分母是 3" + "字" * 3000) as fake:
            r = tools.describe_image_tool(self.ctx, {"image": ref, "question": "分母是多少"})["result"]
        self.assertEqual(r["image"], "IMG-1")
        self.assertTrue(r["answer"].startswith("分母是 3"))
        self.assertIn("已截断", r["answer"])
        self.assertEqual(fake.call_args[0][2], "分母是多少")

    def test_registry(self):
        levels = build_registry().levels()
        self.assertNotIn("create_text_question", levels)
        self.assertNotIn("commit_draft", levels)
        self.assertEqual(build_registry({"draft_mode": "confirm"}).levels()["commit_draft"], "confirm")
        self.assertEqual((levels["create_draft"], levels["describe_image"], levels["list_drafts"]), ("rev", "read", "read"))

    def test_draft_mode_defaults_silent_and_saved_change_is_visible(self):
        self.assertEqual(settings(self.vault)["draft_mode"], "silent")
        self.assertEqual(settings(self.vault)["draft_crop_mode"], "ask")
        self.assertNotIn("commit_draft", build_registry(settings(self.vault)).levels())
        save_config(self.vault, {"draft_mode": "confirm", "draft_crop_mode": "auto", "draft_force_crop": True})
        self.assertEqual(settings(self.vault)["draft_mode"], "confirm")
        self.assertEqual(settings(self.vault)["draft_crop_mode"], "auto")
        self.assertTrue(settings(self.vault)["draft_force_crop"])
        self.assertIn("commit_draft", build_registry(settings(self.vault)).levels())
        with self.assertRaises(ValueError):
            validate_agent_config({"draft_mode": "unexpected"})

    def test_auto_crop_only_registers_one_background_job(self):
        ref = self.img()
        args = {**TEXT_ARGS, "images": [ref]}
        save_config(self.vault, {"draft_crop_mode": "auto"})
        with mock.patch.object(drafts, "start_detect", create=True, return_value={"status": "queued"}) as detect:
            result = tools.create_draft_tool(self.ctx, args)["result"]
        detect.assert_called_once_with(self.vault, result["draft_id"], result["revision"], sha=None)
        self.assertEqual(result["auto_detect"], {"status": "queued", "images": 1})
        self.assertNotIn(drafts.resolve_image(self.vault, self.conv, ref)["sha256"], json.dumps(result))

        for mode in ("ask", "manual"):
            save_config(self.vault, {"draft_crop_mode": mode})
            with mock.patch.object(drafts, "start_detect", create=True) as detect:
                result = tools.create_draft_tool(self.ctx, args)["result"]
            detect.assert_not_called()
            self.assertNotIn("auto_detect", result)

    def test_auto_crop_start_failure_keeps_created_draft_and_hides_details(self):
        ref = self.img()
        sha = drafts.resolve_image(self.vault, self.conv, ref)["sha256"]
        save_config(self.vault, {"draft_crop_mode": "auto"})
        with mock.patch.object(drafts, "start_detect", create=True, side_effect=OSError("/private/images/" + sha)):
            result = tools.create_draft_tool(self.ctx, {**TEXT_ARGS, "images": [ref]})["result"]
        self.assertEqual(result["auto_detect"]["status"], "error")
        self.assertNotIn(sha, json.dumps(result, ensure_ascii=False))
        self.assertIsNotNone(drafts.get_draft(self.vault, result["draft_id"]))

    def test_confirm_preview_and_execute_recheck_current_draft(self):
        draft = {"id": "DR-test", "conversation_id": self.conv, "revision": 3, "status": "review",
                 "subject": "数学", "category": "函数", "difficulty": 5, "blocks": [
                     {"section": "题目", "kind": "text", "text": "求最小值", "note": ""}],
                 "cause": "粗心", "source_images": [{"sha256": "a" * 64}]}
        args = {"draft_id": "DR-test", "revision": 3}
        with mock.patch.object(tools, "settings", return_value={"draft_mode": "confirm"}), \
                mock.patch.object(drafts, "get_draft", return_value=draft), \
                mock.patch.object(drafts, "commit_draft", create=True, return_value={
                    "draft": draft, "result": {"uid": "函数2"}, "reused": False, "training": []}) as commit:
            preview = tools.commit_draft_preview(self.ctx, args)
            self.assertEqual((preview["revision"], preview["blocks"][0]["text"], preview["cause"]),
                             (3, "求最小值", "粗心"))
            self.assertEqual(tools.commit_draft_tool(self.ctx, args)["result"]["uid"], "函数2")
            commit.assert_called_once_with(self.vault, "DR-test", 3)
            for changed in ({"revision": 4}, {"status": "discarded"}, {"conversation_id": "conv_b"}):
                with mock.patch.object(drafts, "get_draft", return_value={**draft, **changed}):
                    with self.assertRaises(ValueError):
                        tools.commit_draft_tool(self.ctx, args)
            self.assertEqual(commit.call_count, 1)
        with mock.patch.object(tools, "settings", return_value={"draft_mode": "silent"}), \
                mock.patch.object(drafts, "get_draft", return_value=draft):
            with self.assertRaisesRegex(ValueError, "方式已改变"):
                tools.commit_draft_tool(self.ctx, args)

    def test_commit_tool_hides_training_sha_and_storage_errors_from_model(self):
        sha = "a" * 64
        path = "/private/vault/错题/.omrs/drafts/images/missing.png"
        draft = {"id": "DR-test", "conversation_id": self.conv, "revision": 3, "status": "review",
                 "subject": "数学", "category": "函数", "difficulty": 5, "blocks": [],
                 "source_images": [{"sha256": sha, "url": "/api/drafts/image?sha=" + sha}]}
        args = {"draft_id": "DR-test", "revision": 3}
        committed = {**draft, "revision": 4, "status": "done"}
        training = {"status": "partial", "registered": [sha],
                    "failed": [{"sha": "b" * 64, "error": path}], "pending": ["c" * 64]}
        with mock.patch.object(tools, "settings", return_value={"draft_mode": "confirm"}), \
                mock.patch.object(drafts, "get_draft", return_value=draft), \
                mock.patch.object(drafts, "commit_draft", return_value={
                    "draft": committed, "result": {"uid": "函数2"}, "reused": False, "training": training}):
            preview = tools.commit_draft_preview(self.ctx, args)
            self.assertEqual(preview["source_images"], draft["source_images"])  # 人看的确认预览保留图 URL
            result = tools.commit_draft_tool(self.ctx, args)["result"]
        self.assertEqual(result["training"], {"status": "partial", "registered": 1, "failed": 1,
                                              "pending": 1, "message": "训练数据登记失败，请在草稿区查看并重试"})
        self.assertNotIn(sha, json.dumps(result, ensure_ascii=False))
        self.assertNotIn(path, json.dumps(result, ensure_ascii=False))

        with mock.patch.object(tools, "settings", return_value={"draft_mode": "confirm"}), \
                mock.patch.object(drafts, "get_draft", side_effect=ValueError("图片文件缺失：" + sha)):
            for action in (tools.commit_draft_preview, tools.commit_draft_tool):
                with self.assertRaisesRegex(ValueError, "无法读取草稿，请在草稿区检查后重试") as caught:
                    action(self.ctx, args)
                self.assertNotIn(sha, str(caught.exception))

        with mock.patch.object(tools, "settings", return_value={"draft_mode": "confirm"}), \
                mock.patch.object(drafts, "get_draft", return_value=draft):
            for error, expected in ((OSError(path), "草稿入库失败"),
                                    (drafts.DraftError(path, 409, "revision_conflict"), "草稿已变化"),
                                    (drafts.DraftError(path, 409, "state_conflict"), "草稿状态已变化")):
                with mock.patch.object(drafts, "commit_draft", side_effect=error):
                    with self.assertRaisesRegex(ValueError, expected) as caught:
                        tools.commit_draft_tool(self.ctx, args)
                    self.assertNotIn(path, str(caught.exception))

    def test_mode_switched_away_and_back_invalidates_old_confirmation(self):
        save_config(self.vault, {"draft_mode": "confirm"})
        run = Run("run_x", self.conv, "faux")
        hooks = Hooks(mock.Mock(vault=self.vault), run, None)
        execute = mock.Mock(return_value={"result": {}})
        tool = ToolDef("commit_draft", "confirm", "", {}, execute, lambda ctx, args: {})
        call = {"id": "call_x", "name": "commit_draft", "args": {"draft_id": "DR-test", "revision": 1}}
        with mock.patch("omrs.agent.runtime.PendingConfirm") as pending:
            pending.return_value.token = "test-token"
            pending.return_value.expires_at = 9999999999
            def toggle(_abort):
                save_config(self.vault, {"draft_mode": "silent"})
                save_config(self.vault, {"draft_mode": "confirm"})
                return "allow"
            pending.return_value.wait.side_effect = toggle
            self.assertIsNone(hooks.before_tool_call(call, tool))
        with self.assertRaisesRegex(ValueError, "配置已变化"):
            hooks.execute(call, tool)
        execute.assert_not_called()


class NoCommitHooks:
    def context_estimate(self, *a):
        return {}

    def before_tool_call(self, call, tool):
        return None

    def execute(self, call, tool):
        return {**tool.run({}, call["args"]), "commits": []}

    def after_tool_call(self, *a):
        pass


class WriteBudgetTest(unittest.TestCase):
    def test_wrote_flag_counts_toward_write_budget(self):
        made = []
        tool = ToolDef("mk", "rev", "", {"type": "object", "properties": {}},
                       lambda ctx, args: made.append(1) or {"result": {"ok": True}, "summary": "", "wrote": True})
        stub = Stub([reply(calls=[("mk", {})] * 3)])
        events = []
        out = AgentLoop(stub, Registry([tool]), NoCommitHooks(), lambda t, d: events.append((t, d)),
                        {**LIMITS, "writes": 2}).run([{"role": "user", "content": "建"}], "sys", take_steering=lambda n: [],
                                                     abort=threading.Event(), on_message=lambda m: None)
        self.assertEqual(out["reason"], "budget")
        self.assertEqual(len(made), 2)
        ends = [d for t, d in events if t == "tool.end" and d.get("status") == "done"]
        self.assertTrue(all(d["wrote"] for d in ends))
        self.assertEqual(json.loads(json.dumps(ends[-1]["budget"]))["writes"], 2)


if __name__ == "__main__":
    unittest.main()
