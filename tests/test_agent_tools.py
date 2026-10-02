"""F / G / C：工具读写、写入来源、按运行撤销与冲突、正文入账与还原。走 AgentRuntime + 假模型之外的直接调用。"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from omrs.actor import agent_actor  # noqa: E402
from omrs.agent.revert import apply_revert, plan_revert  # noqa: E402
from omrs.agent.tools import read, write  # noqa: E402
from omrs.content_history import ContentConflict, content_versions, restore_content  # noqa: E402
from omrs.creation import create_question  # noqa: E402
from omrs.common import HISTORY_HEADERS, MASTERY_HEADERS, history_path, load_csv, mastery_path, save_csv  # noqa: E402
from omrs.labels import save_label  # noqa: E402
from omrs.ledger import connect, read_commits, verify_ledger  # noqa: E402
from omrs.locking import write_lock  # noqa: E402
from omrs.question_ops import get_question_raw, save_question_markdown  # noqa: E402
from omrs.stats import get_stats  # noqa: E402


class OverviewDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 20)


class OverviewScopeTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="omrs-overview-")
        self.addCleanup(self.work.cleanup)
        self.vault = self.work.name
        self.ctx = {"vault": self.vault}
        self.ids = {}

    def fixture(self, specs):
        for name, subject, mastery, attempts, due, suspended, wrong in specs:
            question = create_question(self.vault, subject, "概况" + subject, 5, question_text=name)
            self.ids[name] = question
        from omrs.data_repository import mastery_rows
        rows = mastery_rows(self.vault)
        by_uid = {self.ids[spec[0]]["uid"]: spec for spec in specs}
        history = []
        with connect(self.vault) as db:
            for row in rows:
                name, subject, mastery, attempts, due, suspended, wrong = by_uid[row["UID"]]
                row.update(Mastery=str(mastery), Attempts=str(attempts), Due_Date=due,
                           Current_Tag="", Last_Review="2026-09-19", Suspended="1" if suspended == "csv" else "0")
                if suspended:
                    db.execute("UPDATE question_projection SET suspended=1 WHERE uid=?", (row["UID"],))
                for n in range(wrong):
                    # 稳定身份优先：历史 UID 可与当前名称不同。
                    history.append({"UID": "旧名称", "Question_ID": self.ids[name]["question_id"],
                                    "Date": "2026-09-19", "Is_Correct": "0", "Log_ID": f"{name}-{n}"})
        with connect(self.vault) as db:
            for row in rows:
                db.execute("UPDATE mastery_projection SET mastery=?,attempts=?,due_date=?,last_review_at=? WHERE question_id=?", (float(row["Mastery"]), int(row["Attempts"]), row["Due_Date"], row["Last_Review"], row["question_id"]))
                db.execute("UPDATE question_projection SET current_tag=? WHERE question_id=?", (row["Current_Tag"], row["question_id"]))
            for row in history:
                db.execute("INSERT INTO history_projection(log_id,question_id,uid,date,review_date,is_correct,sub_score) VALUES(?,?,?,?,?,?,0)", (row["Log_ID"], row["Question_ID"], row["UID"], row["Date"], row["Date"], int(row["Is_Correct"])))
        clock = patch("omrs.stats.business_today", OverviewDate.today)
        clock.start()
        self.addCleanup(clock.stop)

    def assert_overview(self, subject, counts, summary, weakest, leeches):
        args = {"subject": subject} if subject is not None else {}
        actual = read.get_overview(self.ctx, args)
        self.assertEqual(actual, {"result": {**counts, "weakest": weakest, "leeches": leeches},
                                  "summary": summary})

    def test_all_overview_fields_follow_subject_and_global_counts(self):
        self.fixture([
            ("m-fresh", "数学", 0, 0, "2026-09-20", False, 0),
            ("m-leech", "数学", .4, 3, "2026-09-19", False, 3),
            ("m-killed", "数学", 1, 4, "2026-09-19", False, 0),
            ("m-stop", "数学", .1, 5, "2026-09-19", "csv", 3),
            ("p-leech", "物理", .2, 4, "2026-09-20", False, 4),
            ("p-other", "物理", .8, 1, "无效日期", False, 0),
            ("p-stop", "物理", .7, 1, "", "csv", 0),
            ("b-stop", "生物", .25, 1, "2026-09-19", "projection", 4),
        ])
        math = {"total": 3, "suspended": 1, "overdue": 1, "due_today": 1, "leech": 1,
                "killed": 1, "fresh": 1, "avg_mastery": .467}
        physics = {"total": 2, "suspended": 1, "overdue": 0, "due_today": 1, "leech": 1,
                   "killed": 0, "fresh": 0, "avg_mastery": .5}
        math_weakest = {"path": "数学 / 概况数学", "n": 3, "avg": .7, "due": 2}
        physics_weakest = {"path": "物理 / 概况物理", "n": 2, "avg": .5, "due": 1}
        math_leech = {"uid": self.ids["m-leech"]["uid"], "wrong_streak": 3}
        physics_leech = {"uid": self.ids["p-leech"]["uid"], "wrong_streak": 4}
        self.assert_overview("数学", math, "待复习 2，顽固 1", [math_weakest], [math_leech])
        self.assert_overview("物理", physics, "待复习 1，顽固 1", [physics_weakest], [physics_leech])
        global_counts = {"total": 5, "suspended": 3, "overdue": 1, "due_today": 2, "leech": 2,
                         "killed": 1, "fresh": 1, "avg_mastery": .48}
        for scope in (None, ""):
            self.assert_overview(scope, global_counts, "待复习 3，顽固 2",
                                 [physics_weakest, math_weakest], [physics_leech, math_leech])
        for subject, n, activity in (("数学", 3, 3), ("物理", 2, 4)):
            stats = get_stats(self.vault, subject=subject)
            self.assertEqual(set(stats["subject_dist"]), {subject})
            self.assertEqual(len(stats["scatter_data"]), n)
            self.assertEqual(stats["recent_activity"], {"2026-09-19": activity})
            self.assertEqual(stats["daily_trend"]["2026-09-19"], activity)
        zero = dict.fromkeys(math, 0)
        self.assert_overview("未知科目", zero, "待复习 0，顽固 0", [], [])
        self.assert_overview("生物", {**zero, "suspended": 1}, "待复习 0，顽固 0", [], [])

    def test_empty_vault(self):
        zero = dict.fromkeys(("total", "suspended", "overdue", "due_today", "leech", "killed", "fresh", "avg_mastery"), 0)
        for subject in (None, "", "未知科目"):
            self.assert_overview(subject, zero, "待复习 0，顽固 0", [], [])

    def test_mastery_is_aggregated_before_rounding_and_kill_detection(self):
        self.fixture([
            ("raw-a", "数学", .00049, 1, "", False, 0),
            ("raw-b", "数学", .00049, 1, "", False, 0),
            ("raw-c", "数学", .00149, 1, "", False, 0),
            ("near-kill", "物理", .9996, 1, "2026-09-19", False, 0),
        ])
        math = read.get_overview(self.ctx, {"subject": "数学"})["result"]
        self.assertEqual(math["avg_mastery"], .001)
        self.assertEqual(math["killed"], 0)
        physics = read.get_overview(self.ctx, {"subject": "物理"})["result"]
        self.assertEqual(physics["avg_mastery"], 1)
        self.assertEqual(physics["killed"], 0)
        self.assertEqual(physics["overdue"], 1)


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
        # 录题工具已改为草稿（不写 Ledger）；AI 建新题的撤销路径仍要覆盖（P2 的确认模式会用到）
        out, _ = self.agent("run_c", lambda ctx, args: {"result": create_question(ctx["vault"], "物理", "力学", 5, question_text="单摆周期")},
                            {}, call="c3")
        out["result"]["path"] = out["result"]["file_path"]
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
