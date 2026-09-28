"""F / G / C：工具读写、写入来源、按运行撤销与冲突、正文入账与还原。走 AgentRuntime + 假模型之外的直接调用。"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs.actor import agent_actor  # noqa: E402
from omrs.agent.revert import apply_revert, plan_revert  # noqa: E402
from omrs.agent.tools import read, write  # noqa: E402
from omrs.content_history import ContentConflict, content_versions, restore_content  # noqa: E402
from omrs.creation import create_question  # noqa: E402
from omrs.labels import save_label  # noqa: E402
from omrs.ledger import read_commits, verify_ledger  # noqa: E402
from omrs.locking import write_lock  # noqa: E402
from omrs.question_ops import get_question_raw, save_question_markdown  # noqa: E402


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="omrs-at-")
        os.makedirs(os.path.join(self.vault, "错题"))
        for q in ("求 $y=\\sin 2x$ 的最小正周期", "等比数列求和", "已知 $a_{n+1}=2a_n+1$，求通项"):
            create_question(self.vault, "数学", "函数", 5, question_text=q, answer_text="略")
        create_question(self.vault, "数学", "函数", 5, question_text="", answer_text="")  # 纯图片 / 空题
        save_label(self.vault, name="考前必看", color="#dc2626")
        self.ctx = {"vault": self.vault}

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def agent(self, run_id, fn, args, call="c1"):
        with write_lock(), agent_actor("conv", run_id, call) as actor:
            out = fn(self.ctx, args)
        return out, actor.commits

    def test_search_two_char_keyword_and_image_only(self):
        r = read.search_questions(self.ctx, {"keywords": ["周期"]})["result"]
        self.assertEqual([i["uid"] for i in r["items"]], ["函数1"])
        self.assertIn("**周期**", r["items"][0]["snippet"])
        self.assertEqual(r["image_only"], 1)
        r = read.search_questions(self.ctx, {"keywords": ["sin2x"]})["result"]
        self.assertEqual(r["total"], 1)
        q = read.get_question(self.ctx, {"uid": "函数3"})["result"]
        self.assertIn("通项", q["sections"]["题目"])

    def test_labels_are_agent_commits_and_revertible(self):
        out, commits = self.agent("run_a", write.set_question_labels, {"uids": ["函数1", "函数2"], "add": ["考前必看"]})
        self.assertEqual(out["result"]["changed"], ["函数1", "函数2"])
        rows = [c for c in read_commits(self.vault, ascending=True) if c["seq"] in {x["seq"] for x in commits}]
        self.assertTrue(all(c["source"] == "agent" and c["payload"]["_agent"]["run_id"] == "run_a" for c in rows))
        with self.assertRaises(ValueError):
            self.agent("run_a", write.set_question_labels, {"uids": ["函数1"], "add": ["不存在的标记"]})
        plan = plan_revert(self.vault, "run_a")
        self.assertTrue(plan["ok"])
        with write_lock():
            apply_revert(self.vault, "run_a")
        self.assertNotIn("考前必看", get_question_raw(self.vault, "函数1")["markdown"])
        self.assertTrue(plan_revert(self.vault, "run_a")["already"])
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_section_update_history_and_conflict(self):
        out, _ = self.agent("run_b", write.update_question_section, {"uid": "函数2", "section": "错因", "mode": "replace", "content": "公比算错"})
        md = get_question_raw(self.vault, "函数2")["markdown"]
        self.assertIn("## 错因\n公比算错", md)
        versions = content_versions(self.vault, uid="函数2")["versions"]
        self.assertGreaterEqual(len(versions), 2)
        self.assertTrue(all(v["available"] for v in versions))
        # 用户之后又改了同一题：整体撤销被拒绝
        save_question_markdown(self.vault, "函数2", md.replace("公比算错", "公比与首项都算错"))
        plan = plan_revert(self.vault, "run_b")
        self.assertFalse(plan["ok"])
        self.assertTrue(plan["conflicts"])
        # 旧版本仍可还原
        first = versions[0]["hash"]
        restore_content(self.vault, "函数2", first)
        self.assertNotIn("公比", get_question_raw(self.vault, "函数2")["markdown"])
        with self.assertRaises(ContentConflict):
            save_question_markdown(self.vault, "函数2", md, expected_content_hash="0" * 64)

    def test_images_are_kept_on_replace(self):
        new, old = write.replace_section("---\n---\n# 题目\n旧题面\n![[a.png]]\n\n# 答案\n1\n", "题目", "新题面", "replace")
        self.assertIn("新题面", new)
        self.assertIn("![[a.png]]", new)
        self.assertEqual(old, "旧题面\n![[a.png]]")

    def test_create_session_feedback_and_new_question_revert(self):
        out, _ = self.agent("run_c", write.create_review_session, {"items": [{"uid": "函数1", "source": "due"}, {"uid": "函数2", "source": "due"}]})
        sid = out["result"]["session_id"]
        preview = write.feedback_preview(self.ctx, {"session_id": sid, "user_statement": "函数1 错了 3 分", "items": [{"uid": "函数1", "is_correct": False, "sub_score": 3}]})
        self.assertEqual(preview["items"][0]["state"], "真不会")
        self.agent("run_c", write.record_feedback, {"session_id": sid, "user_statement": "函数1 错了 3 分", "items": [{"uid": "函数1", "is_correct": False, "sub_score": 3}]}, call="c2")
        out, _ = self.agent("run_c", write.create_tool, {"subject": "物理", "category": "力学", "question": "单摆周期"}, call="c3")
        self.assertEqual(out["result"]["difficulty"], 5)
        plan = plan_revert(self.vault, "run_c")
        self.assertTrue(plan["ok"], plan)
        with write_lock():
            result = apply_revert(self.vault, "run_c")
        self.assertTrue(result["new_commits"])
        types = {c["commit_type"] for c in read_commits(self.vault, ascending=True) if (c["payload"].get("_revert") or {}).get("run_id") == "run_c"}
        self.assertTrue({"session.retract", "review.retract", "question.archive"} <= types)
        self.assertFalse(os.path.exists(os.path.join(self.vault, out["result"]["path"])))
        self.assertTrue(verify_ledger(self.vault)["valid"])


if __name__ == "__main__":
    unittest.main()
