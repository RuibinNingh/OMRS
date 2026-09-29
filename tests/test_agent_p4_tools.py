"""P4 分类与 AI 草稿补丁契约。"""
import json
import os
import tempfile
import unittest
from unittest import mock

from omrs import drafts
from omrs.agent.store import AgentStore
from omrs.agent.tools import build_registry
from omrs.agent.tools import drafts as draft_tools
from omrs.agent.tools import taxonomy as category_tool
from omrs.ai_assist import collect_taxonomy
from omrs.taxonomy import create_category
from omrs import taxonomy as taxonomy_domain
from tests.test_drafts import data_url, make_png


class CategoryToolTests(unittest.TestCase):
    def test_zero_question_cross_subject_idempotent_and_confirm(self):
        with tempfile.TemporaryDirectory() as vault:
            os.makedirs(os.path.join(vault, "错题"))
            self.assertEqual(build_registry().levels()["create_category"], "confirm")
            first = create_category(vault, " 数学  ", " 二次   函数 ")
            self.assertTrue(first["created"])
            self.assertEqual((first["subject"], first["category"]), ("数学", "二次 函数"))
            anchor = os.path.join(vault, "错题", "数学", "二次 函数", "二次 函数.md")
            with open(anchor, "w", encoding="utf-8") as file:
                file.write("用户写的锚点")
            self.assertFalse(create_category(vault, "数学", "二次 函数")["created"])
            with open(anchor, encoding="utf-8") as file:
                self.assertEqual(file.read(), "用户写的锚点")
            create_category(vault, "物理", "二次 函数")
            tax = collect_taxonomy(vault)
            self.assertEqual(tax["categories_by_subject"], {"数学": ["二次 函数"], "物理": ["二次 函数"]})

    def test_unsafe_path_and_partial_failure_not_in_taxonomy(self):
        with tempfile.TemporaryDirectory() as vault:
            os.makedirs(os.path.join(vault, "错题"))
            for bad in ("../外面", ".omrs", "带[括号]", "x\ny"):
                with self.assertRaises(ValueError):
                    create_category(vault, bad, "分类")
            create_category(vault, "数学", "已有")
            with mock.patch("omrs.taxonomy._replace", side_effect=OSError("磁盘故障")):
                # 索引更新失败；新分类不能进入词表。
                with self.assertRaises(OSError):
                    create_category(vault, "数学", "新类")
            self.assertNotIn("新类", collect_taxonomy(vault)["categories_by_subject"]["数学"])
            subject_anchor = os.path.join(vault, "错题", "数学", "数学.md")
            with open(subject_anchor, encoding="utf-8") as file:
                before = file.read()
            create_once = taxonomy_domain._create_once
            def fail_category(path, content):
                if path.endswith("/最终失败/最终失败.md"):
                    raise OSError("模拟锚点写入失败")
                return create_once(path, content)
            with mock.patch.object(taxonomy_domain, "_create_once", side_effect=fail_category):
                with self.assertRaises(OSError):
                    create_category(vault, "数学", "最终失败")
            with open(subject_anchor, encoding="utf-8") as file:
                self.assertEqual(file.read(), before)
            self.assertFalse(os.path.exists(os.path.join(vault, "错题", "数学", "最终失败")))
            self.assertNotIn("最终失败", collect_taxonomy(vault)["categories_by_subject"]["数学"])
            outside = tempfile.mkdtemp()
            try:
                os.symlink(outside, os.path.join(vault, "错题", "物理"))
                with self.assertRaises(ValueError):
                    create_category(vault, "物理", "力学")
            finally:
                os.rmdir(outside)


class DraftPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = self.temp.name
        os.makedirs(os.path.join(self.vault, "错题"))
        store = AgentStore(self.vault)
        self.conv = store.create_conversation("test", "测试")["id"]
        self.ctx = {"vault": self.vault, "conversation_id": self.conv, "run_id": "run-p4", "tool_call_id": "call-p4"}
        self.image = drafts.add_image(self.vault, data_url(make_png(4, 4)), self.conv, "run-p4")
        self.draft = drafts.create_draft(self.vault, {
            "subject": "数学", "category": "函数", "source_images": [self.image["sha256"]],
            "blocks": [{"section": "题目", "kind": "text", "text": "旧题干"},
                       {"section": "题目", "kind": "image", "image_sha": self.image["sha256"], "note": "原图"},
                       {"section": "答案", "kind": "text", "text": "旧答案"}]}, self.ctx)
        self.draft = drafts.set_boxes(self.vault, self.draft["id"], self.draft["revision"], blocks=[{
            "id": self.draft["blocks"][1]["id"], "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "box_origin": "manual"}])

    def tearDown(self):
        self.temp.cleanup()

    def args(self, **changes):
        return {"draft_id": self.draft["id"], "expected_revision": self.draft["revision"], **changes}

    def test_structured_read_and_precise_cas_patch(self):
        self.assertEqual(build_registry().levels()["update_draft"], "rev")
        read = draft_tools.get_draft_tool(self.ctx, {"draft_id": self.draft["id"]})["result"]
        self.assertEqual(read["revision"], self.draft["revision"])
        self.assertIn("note", read)
        self.assertEqual(read["blocks"][1]["image"], self.image["ref"])
        self.assertNotIn(self.image["sha256"], json.dumps(read, ensure_ascii=False))
        ids = [block["block_id"] for block in read["blocks"]]
        result = draft_tools.update_draft_tool(self.ctx, self.args(block_patches=[{"block_id": ids[0], "text": "新题干"}]))
        self.assertTrue(result["wrote"])
        after = drafts.get_draft(self.vault, self.draft["id"])
        self.assertEqual(after["revision"], self.draft["revision"] + 1)
        self.assertEqual([b["id"] for b in after["blocks"]], ids)
        self.assertEqual(after["blocks"][1]["image_sha"], self.image["sha256"])
        self.assertEqual(after["blocks"][1]["box_origin"], "manual")
        self.assertEqual(after["blocks"][1]["box"], {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})
        self.assertEqual(after["blocks"][2]["text"], "旧答案")
        with self.assertRaisesRegex(drafts.DraftError, "草稿已变化"):
            draft_tools.update_draft_tool(self.ctx, self.args(fields={"category": "新类"}))

    def test_manual_edit_is_suggestion_and_invalid_targets_are_atomic(self):
        before = drafts.get_draft(self.vault, self.draft["id"])
        blocks = before["blocks"]
        updated = drafts.update_draft(self.vault, before["id"], before["revision"], {},
                                      [{**b, "text": "人工题干"} if b["id"] == blocks[0]["id"] else b for b in blocks])
        args = {"draft_id": before["id"], "expected_revision": updated["revision"],
                "block_patches": [{"block_id": blocks[0]["id"], "text": "AI 覆盖"}]}
        out = draft_tools.update_draft_tool(self.ctx, args)
        self.assertFalse(out["wrote"])
        self.assertEqual(out["result"]["suggestions"][0]["target"], f"block:{blocks[0]['id']}")
        self.assertEqual(drafts.get_draft(self.vault, before["id"])["blocks"][0]["text"], "人工题干")
        for patch in ({"block_id": "不存在", "text": "坏"},
                      {"block_id": blocks[1]["id"], "text": "替换图片"},
                      {"block_id": blocks[1]["id"], "image_sha": "f" * 64}):
            with self.assertRaises(drafts.DraftError):
                draft_tools.update_draft_tool(self.ctx, {"draft_id": before["id"],
                    "expected_revision": updated["revision"], "block_patches": [patch]})
        with self.assertRaises(drafts.DraftError):
            draft_tools.update_draft_tool(self.ctx, {"draft_id": before["id"],
                "expected_revision": updated["revision"], "fields": {"labels": ["AI 标记"]}})

    def test_manual_field_protected_and_ai_activity_has_revision(self):
        current = drafts.get_draft(self.vault, self.draft["id"])
        updated = drafts.update_draft(self.vault, current["id"], current["revision"],
                                      {"note": "人工备注"}, current["blocks"])
        out = draft_tools.update_draft_tool(self.ctx, {"draft_id": current["id"],
            "expected_revision": updated["revision"], "fields": {"note": "AI 备注"}})
        self.assertFalse(out["wrote"])
        self.assertEqual(out["result"]["suggestions"], [{"target": "field:note", "before": "人工备注", "after": "AI 备注"}])
        self.assertEqual(drafts.get_draft(self.vault, current["id"])["revision"], updated["revision"])
        changed = draft_tools.update_draft_tool(self.ctx, {"draft_id": current["id"],
            "expected_revision": updated["revision"], "fields": {"knowledge_points": ["矩阵运算"]}})
        self.assertTrue(changed["wrote"])
        with open(os.path.join(self.vault, "错题", ".omrs", "drafts", "events.jsonl"), encoding="utf-8") as file:
            event = [json.loads(line) for line in file if '"draft.ai_update"' in line][-1]
        self.assertEqual((event["old_revision"], event["new_revision"], event["run_id"], event["tool_call_id"]),
                         (updated["revision"], updated["revision"] + 1, "run-p4", "call-p4"))

    def test_other_conversation_and_done_rejected(self):
        other = AgentStore(self.vault).create_conversation("other", "另一个")["id"]
        with self.assertRaisesRegex(drafts.DraftError, "本对话"):
            draft_tools.update_draft_tool({**self.ctx, "conversation_id": other}, self.args(fields={"note": "越权"}))
        committed = drafts.commit_draft(self.vault, self.draft["id"], self.draft["revision"])
        with self.assertRaisesRegex(drafts.DraftError, "不能修改"):
            draft_tools.update_draft_tool(self.ctx, {"draft_id": self.draft["id"],
                "expected_revision": committed["draft"]["revision"], "fields": {"note": "越权"}})
