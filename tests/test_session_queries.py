"""MCP 与内置助手共用的复习计划查询契约。"""
import datetime
import json
import tempfile
import unittest

from omrs.agent.tools.read import get_recommendations, get_session_tool, list_sessions_tool
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, connect, read_commits
from omrs.projection_runtime import invalidate
from omrs.projections import rebuild_projection
from omrs.sessions import create_session_from_selection, list_sessions


def question(index, uid=None):
    return {"question_id": f"Q{index}", "uid": uid or f"U{index}",
            "file_path": f"错题/数学/代数/{uid or f'U{index}'}.md", "subject": "数学", "category": "代数",
            "difficulty": 5, "current_tag": "#状态/待攻克", "labels": []}


class SessionQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.ctx = {"vault": self.vault}
        self.addCleanup(invalidate, self.vault)

    def bootstrap(self, count=3, sessions=None):
        append_commit(self.vault, "test", "legacy.bootstrap", "查询夹具", {
            "questions": [question(i) for i in range(1, count + 1)], "session_rows": sessions or []})
        rebuild_projection(self.vault)

    def fixture_session(self, sid, indexes, created_at="2026-10-03T10:00:00+00:00"):
        entries = [{"question_id": f"Q{i}", "uid": f"U{i}", "uid_at_creation": f"U{i}",
                    "entry_id": f"{sid}:{n}", "source": "due"} for n, i in enumerate(indexes)]
        append_commit(self.vault, "test", "session.create", "计划夹具", {"session": {
            "session_id": sid, "created_at": created_at, "subject_filter": "数学", "count": len(entries),
            "entries": entries, "items": entries, "status": "active"}})

    def result(self, sid, **args):
        return get_session_tool(self.ctx, {"session_id": sid, **args})["result"]

    def test_list_pages_beyond_twenty_and_uses_deterministic_tie_order(self):
        self.bootstrap(25)
        for i in range(25):
            self.fixture_session(f"S{i:02}", [i + 1])
        rebuild_projection(self.vault)
        first = list_sessions_tool(self.ctx, {})["result"]
        second = list_sessions_tool(self.ctx, {"offset": first["next_offset"]})["result"]
        expected = [f"S{i:02}" for i in range(24, -1, -1)]
        self.assertEqual([s["session_id"] for s in first["sessions"] + second["sessions"]], expected)
        self.assertEqual((first["total"], first["limit"], first["next_offset"]), (25, 20, 20))
        self.assertEqual((second["total"], second["offset"], second["next_offset"]), (25, 20, None))
        self.assertEqual(first["sessions"][0]["availability_counts"],
                         {"active": 1, "suspended": 0, "archived": 0, "unresolved": 0})
        empty = list_sessions_tool(self.ctx, {"offset": 30})["result"]
        self.assertEqual((empty["sessions"], empty["total"], empty["next_offset"]), ([], 25, None))

    def test_detail_defaults_to_hundred_entries_but_progress_covers_whole_plan(self):
        self.bootstrap(105)
        self.fixture_session("BIG", range(1, 106))
        rebuild_projection(self.vault)
        first = self.result("BIG")
        second = self.result("BIG", offset=100)
        self.assertEqual((len(first["entries"]), first["entries_total"], first["next_offset"]), (100, 105, 100))
        self.assertEqual((len(second["entries"]), second["entries_total"], second["next_offset"]), (5, 105, None))
        self.assertEqual(first["pending"], second["pending"])
        self.assertEqual((second["pending_count"], second["count"], second["total_count"]), (105, 105, 105))
        self.assertEqual(second["entries"][0]["entry_id"], "BIG:100")

    def test_partial_feedback_and_completed_state_use_full_progress(self):
        self.bootstrap()
        session = create_session_from_selection(self.vault, [
            {"question_id": "Q1", "source": "proficiency"}, {"question_id": "Q2", "source": "due"}])
        sid = session["session_id"]
        feedback = lambda qid: process_feedback(self.vault, [{"question_id": qid, "sub_score": 5, "is_correct": True}], sid)
        feedback("Q1")
        result = self.result(sid, offset=1, limit=1)
        self.assertEqual((result["status"], result["pending"], result["done"]), ("active", ["U2"], ["U1"]))
        self.assertEqual((result["feedback_count"], result["pending_count"], result["feedback_complete"]), (1, 1, False))
        self.assertEqual(result["entries"][0]["feedback_submitted"], False)
        self.assertEqual(self.result(sid, limit=1)["entries"][0]["source"], "proficiency")
        feedback("Q2")
        completed = self.result(sid)
        self.assertEqual((completed["status"], completed["pending_count"], completed["feedback_complete"]), ("completed", 0, True))
        self.assertTrue(completed["completed_at"])
        rows = list_sessions_tool(self.ctx, {"status": "completed"})["result"]
        self.assertEqual(rows["total"], 1)
        self.assertEqual(rows["sessions"][0]["feedback_count"], 2)
        self.assertEqual(rows["sessions"][0]["subject_filter"], "")
        self.assertEqual(rows["sessions"][0]["pending"], 0)
        self.assertEqual(list_sessions_tool(self.ctx, {"status": "active"})["result"]["total"], 0)

    def test_suspended_only_active_plan_is_visible_without_implying_completion(self):
        self.bootstrap(1)
        self.fixture_session("STOP", [1])
        append_commit(self.vault, "test", "question.suspend", "停用夹具", {"question_id": "Q1"})
        rebuild_projection(self.vault)
        self.assertEqual(list_sessions(self.vault), [])
        self.assertEqual(len(list_sessions(self.vault, include_unavailable=True)), 1)
        result = self.result("STOP")
        self.assertEqual((result["status"], result["count"], result["total_count"]), ("active", 0, 1))
        self.assertEqual((result["pending_count"], result["feedback_count"], result["feedback_complete"]), (0, 0, False))
        self.assertEqual(result["entries"][0]["availability"], "suspended")
        listed = list_sessions_tool(self.ctx, {})["result"]["sessions"][0]
        self.assertEqual((listed["status"], listed["pending"], listed["total_count"]), ("active", 0, 1))
        self.assertFalse(listed["completed_at"])

    def test_archived_suspended_and_unresolved_entries_remain_inspectable(self):
        raw = [{"Session_ID": "MIX", "Created_At": "2026-10-03T10:00:00+00:00", "Subject_Filter": "数学",
                "Count": "4", "Status": "active", "UIDs": json.dumps([
                    {"question_id": "Q1", "uid": "U1", "source": "due"},
                    {"question_id": "Q2", "uid": "U2", "source": "due"},
                    {"question_id": "Q3", "uid": "U3", "source": "proficiency"}, {"uid": "old"}])}]
        self.bootstrap(3, raw)
        append_commit(self.vault, "test", "question.suspend", "停用夹具", {"question_id": "Q1"})
        append_commit(self.vault, "test", "question.archive", "归档夹具", {"question_id": "Q2"})
        rebuild_projection(self.vault)
        result = self.result("MIX")
        self.assertEqual([e["availability"] for e in result["entries"]], ["suspended", "archived", "active", "unresolved"])
        self.assertEqual((result["count"], result["total_count"], result["pending_count"]), (3, 4, 3))
        self.assertEqual(result["availability_counts"], {"active": 1, "suspended": 1, "archived": 1, "unresolved": 1})
        self.assertFalse(result["feedback_complete"])
        self.assertEqual(list_sessions_tool(self.ctx, {})["result"]["sessions"][0]["availability_counts"], result["availability_counts"])

    def test_move_and_reused_uid_keep_original_question_identity(self):
        self.bootstrap(1)
        self.fixture_session("MOVE", [1])
        append_commit(self.vault, "test", "question.move", "改名夹具", {
            "question_id": "Q1", "to_uid": "NEW", "to_path": "错题/数学/几何/NEW.md", "to_category": "几何"})
        append_commit(self.vault, "test", "question.create", "UID 复用夹具", {"question": question(2, "U1")})
        rebuild_projection(self.vault)
        entry = self.result("MOVE")["entries"][0]
        self.assertEqual((entry["question_id"], entry["uid_at_creation"], entry["uid"]), ("Q1", "U1", "NEW"))
        self.assertEqual(self.result("MOVE")["pending"], ["NEW"])
        recommendations = get_recommendations(self.ctx, {"count": 2})["result"]
        self.assertEqual([e["question_id"] for e in recommendations["selection"]], ["Q2"])

    def test_archive_and_reused_uid_do_not_rebind_original_entry(self):
        self.bootstrap(1)
        self.fixture_session("OLD", [1])
        append_commit(self.vault, "test", "question.archive", "归档夹具", {"question_id": "Q1"})
        append_commit(self.vault, "test", "question.create", "UID 复用夹具", {"question": question(2, "U1")})
        rebuild_projection(self.vault)
        entry = self.result("OLD")["entries"][0]
        self.assertEqual((entry["question_id"], entry["uid"], entry["availability"]), ("Q1", "U1", "archived"))
        self.assertEqual(self.result("OLD")["pending_count"], 1)

    def test_recommendations_preserve_counts_sources_and_stable_selection(self):
        self.bootstrap(3)
        today = datetime.date.today()
        with connect(self.vault) as db:
            db.execute("UPDATE mastery_projection SET due_date=? WHERE question_id='Q1'", (today.isoformat(),))
            db.execute("UPDATE mastery_projection SET due_date=? WHERE question_id IN ('Q2','Q3')",
                       ((today + datetime.timedelta(days=30)).isoformat(),))
        before = len(read_commits(self.vault))
        result = get_recommendations(self.ctx, {"count": 2})["result"]
        self.assertEqual((len(result["due"]), len(result["proficiency"]), len(result["selection"])), (1, 1, 2))
        self.assertEqual(result["selection"], [{"question_id": item["question_id"], "uid": item["uid"], "source": item["source"]}
                                               for item in result["due"] + result["proficiency"]])
        for item in result["due"] + result["proficiency"]:
            self.assertTrue(item["question_id"])
            self.assertIn("why", item)
            self.assertIn("mastery", item)
        self.assertEqual(len(read_commits(self.vault)), before)
        session = create_session_from_selection(self.vault, result["selection"])
        self.assertEqual([e["question_id"] for e in session["entries"]], [e["question_id"] for e in result["selection"]])

    def test_queries_do_not_append_ledger_facts(self):
        self.bootstrap(2)
        self.fixture_session("READ", [1])
        rebuild_projection(self.vault)
        before = [(c["seq"], c["commit_hash"]) for c in read_commits(self.vault)]
        self.result("READ")
        list_sessions_tool(self.ctx, {})
        get_recommendations(self.ctx, {"count": 2})
        self.assertEqual([(c["seq"], c["commit_hash"]) for c in read_commits(self.vault)], before)

    def test_strict_pagination_rejects_coercion_and_out_of_range_values(self):
        for fn, base in ((list_sessions_tool, {}), (get_session_tool, {"session_id": "missing"})):
            for field, values in (("offset", (-1, True, 1.5, "1", None)), ("limit", (0, 101, False, 1.5, "20", None))):
                for value in values:
                    with self.subTest(tool=fn.__name__, field=field, value=value):
                        with self.assertRaisesRegex(ValueError, field):
                            fn(self.ctx, {**base, field: value})
        with self.assertRaisesRegex(ValueError, "status"):
            list_sessions_tool(self.ctx, {"status": "pending"})

    def test_missing_or_blank_session_id_reports_readable_error(self):
        self.bootstrap(1)
        with self.assertRaisesRegex(ValueError, "不存在"):
            self.result("missing")
        for value in (None, "", " ", 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "session_id"):
                get_session_tool(self.ctx, {"session_id": value})

    def test_empty_vault_and_out_of_range_detail_page(self):
        listed = list_sessions_tool(self.ctx, {})["result"]
        self.assertEqual((listed["sessions"], listed["total"], listed["next_offset"]), ([], 0, None))
        self.bootstrap(1)
        self.fixture_session("ONE", [1])
        rebuild_projection(self.vault)
        result = self.result("ONE", offset=10)
        self.assertEqual((result["entries"], result["entries_total"], result["next_offset"]), ([], 1, None))
        self.assertEqual((result["pending"], result["pending_count"]), (["U1"], 1))


if __name__ == "__main__":
    unittest.main()
