"""所有正式创建入口共用历史计划编号，防止技术重试读到其他计划。"""
import datetime
import tempfile
import unittest
from unittest.mock import patch

from omrs.creation import create_question
from omrs.ledger import append_commit, connect, read_commits
from omrs.projection_runtime import invalidate
from omrs.projections import rebuild_projection
from omrs.session_operations import create_mcp_session
from omrs.sessions import _reserved_session_ids, _resolve_session_id, create_session_from_selection, delete_session, get_session


class FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        result = cls(2026, 10, 3, 10, 0, 0)
        return result.replace(tzinfo=tz) if tz else result


class SessionIdReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.addCleanup(invalidate, self.vault)
        self.questions = [create_question(self.vault, "数学", category, 5, question_text="计划编号夹具")
                          for category in ("代数", "几何")]
        self.target_seq = read_commits(self.vault)[-1]["seq"]
        clock = patch("omrs.sessions.datetime.datetime", FixedDateTime)
        clock.start()
        self.addCleanup(clock.stop)
        mcp_clock = patch("omrs.session_operations._now", return_value=FixedDateTime.now(datetime.timezone.utc))
        mcp_clock.start()
        self.addCleanup(mcp_clock.stop)

    def mcp(self):
        return create_mcp_session(self.vault, [{"question_id": self.questions[0]["question_id"], "source": "due"}],
                                  "key", "request", lambda: None)

    def web(self, index):
        return create_session_from_selection(self.vault, [{"question_id": self.questions[index]["question_id"], "source": "due"}])

    def restore(self):
        append_commit(self.vault, "test", "state.restore", "恢复创建计划前状态", {"target_seq": self.target_seq})
        rebuild_projection(self.vault)

    def assert_old_retry_unavailable(self, original, replacement):
        before = len(read_commits(self.vault))
        retry = self.mcp()
        self.assertEqual(retry["session_id"], original["session_id"])
        self.assertNotEqual(retry["session_id"], replacement["session_id"])
        self.assertTrue(retry["reused"])
        self.assertFalse(retry["available"])
        self.assertEqual(retry["status"], "retracted")
        self.assertEqual(retry["actionable_pending_count"], 0)
        self.assertNotIn(self.questions[1]["question_id"], [entry["question_id"] for entry in retry["entries"]])
        self.assertEqual(len(read_commits(self.vault)), before)
        self.assertIsNone(get_session(self.vault, original["session_id"]))

    def test_retracted_mcp_plan_cannot_be_reused_by_same_second_web_creation(self):
        original = self.mcp()
        delete_session(self.vault, original["session_id"])
        replacement = self.web(1)
        self.assertNotEqual(original["session_id"], replacement["session_id"])
        self.assertEqual(replacement["entries"][0]["question_id"], self.questions[1]["question_id"])
        self.assert_old_retry_unavailable(original, replacement)

    def test_restored_mcp_plan_cannot_be_reused_by_same_second_web_creation(self):
        original = self.mcp()
        self.restore()
        with connect(self.vault) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM session_projection WHERE session_id=?", (original["session_id"],)).fetchone())
        replacement = self.web(1)
        self.assertNotEqual(original["session_id"], replacement["session_id"])
        self.assert_old_retry_unavailable(original, replacement)

    def test_retracted_web_plan_keeps_id_reserved(self):
        original = self.web(0)
        delete_session(self.vault, original["session_id"])
        replacement = self.web(1)
        self.assertNotEqual(original["session_id"], replacement["session_id"])
        self.assertIn(original["session_id"], _reserved_session_ids(self.vault))

    def test_restored_web_plan_id_is_reserved_by_creation_fact_without_mcp_receipt(self):
        original = self.web(0)
        self.restore()
        with connect(self.vault) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM session_projection WHERE session_id=?", (original["session_id"],)).fetchone())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM op_results").fetchone()[0], 0)
        replacement = self.web(1)
        self.assertNotEqual(original["session_id"], replacement["session_id"])
        self.assertEqual(_reserved_session_ids(self.vault), {original["session_id"], replacement["session_id"]})

    def test_numeric_fallback_checks_reserved_ids_when_all_letter_suffixes_are_taken(self):
        base = "EXP-20261003100000"
        reserved = {base, *(f"{base}-{chr(ord('A') + index)}" for index in range(26)),
                    f"{base}-0", f"{base}-1", f"{base}-2"}
        original = set(reserved)
        selected = _resolve_session_id(reserved, base)
        self.assertEqual(selected, f"{base}-3")
        self.assertNotIn(selected, reserved)
        self.assertEqual(reserved, original)

    def test_reservation_query_accepts_existing_transaction_and_does_not_write_facts(self):
        original = self.mcp()
        self.restore()
        before = [(commit["seq"], commit["commit_hash"]) for commit in read_commits(self.vault)]
        with connect(self.vault) as db:
            db.execute("BEGIN IMMEDIATE")
            self.assertEqual(_reserved_session_ids(self.vault, db), {original["session_id"]})
        self.assertEqual(_reserved_session_ids(self.vault), {original["session_id"]})
        self.assertEqual([(commit["seq"], commit["commit_hash"]) for commit in read_commits(self.vault)], before)


if __name__ == "__main__":
    unittest.main()
