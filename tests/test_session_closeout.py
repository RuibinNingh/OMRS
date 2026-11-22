"""单题处置、事务结单及回放，使用独立的合成 Vault。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from omrs.backup_store import create_backup, prepare_import, restore
from omrs.creation import create_question
from omrs.data_repository import IdentityConflict, history_rows, mastery_rows
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, connect, read_commits, verify_ledger
from omrs.projection_runtime import invalidate
from omrs.projections import rebuild_projection
from omrs.session_operations import SessionStateConflict, complete_session, set_entry_skipped, set_session_paused
from omrs.sessions import bind_session_entry, create_session_from_selection, get_session, list_sessions


class SessionCloseoutTests(unittest.TestCase):
    def setUp(self):
        self.vault = self.enterContext(tempfile.TemporaryDirectory())
        self.addCleanup(invalidate, self.vault)
        self.questions = [create_question(self.vault, "数学", category, 5, question_text="求 1+1", answer_text="2")
                          for category in ("代数", "几何", "数论")]
        self.plan = create_session_from_selection(self.vault, [
            {"question_id": question["question_id"], "source": "due"} for question in self.questions])
        self.sid = self.plan["session_id"]

    def current(self):
        return get_session(self.vault, self.sid)

    def payload(self, index, **extra):
        entry = self.plan["entries"][index]
        return {"entry_id": entry["entry_id"], "question_id": entry["question_id"],
                "is_correct": True, "sub_score": 8, **extra}

    def skip(self, index, skipped=True):
        entry = self.plan["entries"][index]
        return set_entry_skipped(self.vault, self.sid, entry["entry_id"], skipped, entry["question_id"])

    def lifecycle(self, index, action):
        append_commit(self.vault, "test", f"question.{action}", "变更合成题",
                      {"question_id": self.questions[index]["question_id"]})
        rebuild_projection(self.vault)

    def finish(self, plan=None):
        return complete_session(self.vault, self.sid, (plan or self.current())["progress"]["signature"])

    def count(self, kind):
        return sum(row["commit_type"] == kind for row in read_commits(self.vault))

    def learning(self):
        return mastery_rows(self.vault), history_rows(self.vault)

    def assert_states(self, *states):
        data = self.current()
        self.assertEqual([entry["feedback_state"] for entry in data["entries"]], list(states))
        progress = data["progress"]
        self.assertEqual(sum(progress[state] for state in ("recorded", "pending", "skipped", "unavailable", "unresolved")),
                         progress["total"])
        return data

    def test_skip_retry_undo_and_occupation_leave_learning_untouched(self):
        before = self.learning()
        self.skip(0)
        self.skip(0)
        self.assertEqual(self.count("session.entry_skip"), 1)
        self.assert_states("skipped", "pending", "pending")
        with self.assertRaisesRegex(ValueError, "进行中"):
            create_session_from_selection(self.vault, [{"question_id": self.questions[0]["question_id"], "source": "due"}])
        self.skip(0, False)
        self.skip(0, False)
        self.assertEqual(self.count("session.entry_skip"), 2)
        self.assert_states("pending", "pending", "pending")
        self.assertEqual(self.learning(), before)
        self.assertEqual(self.count("review.batch_submit"), 0)

    def test_mixed_batch_and_receipt_priority_across_lifecycle_and_completion(self):
        self.skip(0)
        self.lifecycle(1, "suspend")
        results = process_feedback(self.vault, [self.payload(i) for i in range(3)], self.sid)
        self.assertEqual([row["entry_id"] for row in results], [e["entry_id"] for e in self.plan["entries"]])
        self.assertEqual([row["status"] for row in results], ["error", "error", "ok"])
        self.assertIn("跳过", results[0]["msg"])
        self.assertIn("停用", results[1]["msg"])
        open_plan = self.assert_states("skipped", "unavailable", "recorded")
        self.assertTrue(open_plan["progress"]["can_finish"])
        self.lifecycle(2, "archive")
        self.assert_states("skipped", "unavailable", "recorded")
        with self.assertRaises(SessionStateConflict):
            self.skip(2)
        before = self.learning()
        ended = self.finish()
        self.assertEqual(ended["completion"]["counts"],
                         {"recorded": 1, "pending": 0, "unavailable": 1, "skipped": 1, "unresolved": 0, "total": 3})
        self.lifecycle(1, "resume")
        self.lifecycle(2, "restore")
        self.assertEqual(self.current()["completion"], ended["completion"])
        self.assert_states("skipped", "unavailable", "recorded")
        retry = process_feedback(self.vault, [self.payload(2, uid="旧显示编号"), self.payload(1)], self.sid)
        self.assertTrue(retry[0]["reused"])
        self.assertIn("已结束", retry[1]["msg"])
        self.assertEqual(self.finish(open_plan)["completion"], ended["completion"])
        self.assertEqual((self.count("session.complete"), self.count("review.batch_submit")), (1, 1))
        self.assertEqual(self.learning()[1], before[1])

    def test_restore_clears_completion_but_retains_skip_and_historical_event(self):
        self.skip(0)
        self.lifecycle(1, "suspend")
        process_feedback(self.vault, [self.payload(2)], self.sid)
        ended = self.finish()
        self.lifecycle(1, "resume")
        append_commit(self.vault, "test", "session.restore", "显式恢复计划", {"session_id": self.sid})
        rebuild_projection(self.vault, force=True)
        opened = self.assert_states("skipped", "pending", "recorded")
        self.assertEqual((opened["status"], opened["completed_at"], opened["completion"]), ("active", "", None))
        original = next(row["payload"]["completion"] for row in read_commits(self.vault)
                        if row["commit_type"] == "session.complete")
        self.assertEqual(original, ended["completion"])

    def test_history_correction_keeps_original_completion_and_validity_separate(self):
        process_feedback(self.vault, [self.payload(i) for i in range(3)], self.sid)
        closed = self.current()
        self.assertEqual(closed["status"], "completed")
        review = next(row for row in read_commits(self.vault) if row["commit_type"] == "review.batch_submit")
        append_commit(self.vault, "test", "review.retract", "修正原反馈",
                      {"target_commit_id": review["commit_id"], "target_review_index": 1})
        rebuild_projection(self.vault, force=True)
        corrected = self.assert_states("recorded", "recorded", "recorded")
        self.assertFalse(corrected["entries"][1]["feedback_submitted"])
        self.assertEqual(corrected["completion"], closed["completion"])
        self.assertTrue(process_feedback(self.vault, [self.payload(1)], self.sid)[0]["reused"])

    def test_stale_confirmation_after_resume_and_after_pause_cycle(self):
        self.skip(0)
        self.skip(1)
        self.lifecycle(2, "suspend")
        stale = self.current()
        self.lifecycle(2, "resume")
        with self.assertRaises(SessionStateConflict):
            self.finish(stale)
        self.assert_states("skipped", "skipped", "pending")
        self.lifecycle(2, "suspend")
        fresh = self.current()
        set_session_paused(self.vault, self.sid, True)
        with self.assertRaisesRegex(SessionStateConflict, "已暂停"):
            self.finish(fresh)
        with self.assertRaisesRegex(SessionStateConflict, "已暂停"):
            self.skip(0, False)
        set_session_paused(self.vault, self.sid, False)
        with self.assertRaises(SessionStateConflict):
            self.finish(fresh)
        self.assertEqual(self.count("session.complete"), 0)

    def test_unresolved_identity_and_binding_invalidate_older_signature(self):
        append_commit(self.vault, "test", "legacy.bootstrap", "迁移未知身份", {"session_rows": [{
            "Session_ID": "LEGACY", "Status": "active", "Count": "1",
            "UIDs": json.dumps([self.questions[0]["uid"]])}]})
        rebuild_projection(self.vault, force=True)
        self.sid = "LEGACY"
        unresolved = self.assert_states("unresolved")
        with self.assertRaises(SessionStateConflict):
            self.finish(unresolved)
        entry_id = unresolved["entries"][0]["entry_id"]
        result = process_feedback(self.vault, [{**self.payload(0), "entry_id": entry_id}], self.sid)[0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["entry_id"], entry_id)
        self.assertIn("身份待确认", result["msg"])
        with self.assertRaisesRegex(IdentityConflict, "身份"):
            set_entry_skipped(self.vault, self.sid, entry_id, True, self.questions[0]["question_id"])
        skipped = set_entry_skipped(self.vault, self.sid, entry_id, True)
        bind_session_entry(self.vault, self.sid, entry_id, self.questions[0]["question_id"])
        with self.assertRaises(SessionStateConflict):
            self.finish(skipped)
        self.assert_states("skipped")
        set_entry_skipped(self.vault, self.sid, entry_id, False)
        self.assert_states("pending")
        self.assertEqual(len(history_rows(self.vault)), 0)

    def test_all_unavailable_explicit_completion_and_discovery(self):
        for i in range(3):
            self.lifecycle(i, "suspend")
        self.assertEqual(list_sessions(self.vault), [])
        active = list_sessions(self.vault, include_unavailable=True)[0]
        self.assertEqual(active["progress"], self.current()["progress"])
        self.assertTrue(active["progress"]["can_finish"])
        before = self.learning()
        ended = self.finish()
        self.assertEqual(ended["completion"]["counts"]["recorded"], 0)
        self.assertEqual(self.learning(), before)
        self.lifecycle(1, "resume")
        self.assert_states("unavailable", "unavailable", "unavailable")

    def test_final_feedback_and_automatic_completion_roll_back_together(self):
        process_feedback(self.vault, [self.payload(0), self.payload(1)], self.sid)
        before = self.learning()
        with patch("omrs.feedback.publish_completion", side_effect=RuntimeError("模拟结单发布失败")):
            with self.assertRaisesRegex(RuntimeError, "模拟结单"):
                process_feedback(self.vault, [self.payload(2)], self.sid)
        self.assertEqual(self.learning(), before)
        self.assert_states("recorded", "recorded", "pending")
        self.assertEqual(self.count("session.complete"), 0)
        self.assertFalse(process_feedback(self.vault, [self.payload(2)], self.sid)[0].get("reused", False))
        self.assertEqual(self.current()["status"], "completed")
        self.assertEqual(self.count("session.complete"), 1)

    def test_two_processes_close_once(self):
        for index in range(3):
            self.skip(index)
        signature = self.current()["progress"]["signature"]
        script = """import json,sys
from omrs.session_operations import complete_session
plan = complete_session(*sys.argv[1:])
print(json.dumps(plan['completion']))
"""
        barrier = Barrier(2)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("OMRS_SYSTEMD_SERVICE", None)

        def request():
            barrier.wait(timeout=10)
            return json.loads(subprocess.check_output(
                [sys.executable, "-c", script, self.vault, self.sid, signature], env=env, timeout=20))

        with ThreadPoolExecutor(2) as pool:
            first, second = [pool.submit(request) for _ in range(2)]
            self.assertEqual(first.result(), second.result())
        self.assertEqual(self.count("session.complete"), 1)

    def test_incremental_full_replay_restart_and_backup_restore(self):
        self.skip(0)
        self.lifecycle(1, "suspend")
        process_feedback(self.vault, [self.payload(2)], self.sid)
        ended = self.finish()
        incremental = (ended["progress"], ended["completion"])
        with connect(self.vault) as db:
            self.assertEqual(json.loads(db.execute("SELECT closeout_json FROM session_projection").fetchone()[0])["completion"],
                             ended["completion"])
        invalidate(self.vault)
        rebuild_projection(self.vault, force=True)
        self.assertEqual((self.current()["progress"], self.current()["completion"]), incremental)
        script = """import json,sys
from omrs.config_repository import initialize
from omrs.sessions import get_session
initialize(sys.argv[1])
s = get_session(*sys.argv[1:])
print(json.dumps([s['progress'], s['completion']]))
"""
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("OMRS_SYSTEMD_SERVICE", None)
        restarted = subprocess.check_output([sys.executable, "-c", script, self.vault, self.sid], env=env, timeout=20)
        self.assertEqual(tuple(json.loads(restarted)), incremental)
        archive, _, _, _ = create_backup(self.vault)
        self.addCleanup(Path(archive).unlink)
        destination = self.enterContext(tempfile.TemporaryDirectory())
        candidate = prepare_import(destination, archive)
        self.assertTrue(candidate["preview"]["manifest_verified"])
        self.assertTrue(restore(destination, candidate["restore_id"], confirm=True)["restored"])
        self.assertEqual(get_session(destination, self.sid)["completion"], ended["completion"])
        self.assertEqual(history_rows(destination), history_rows(self.vault))
        self.assertTrue(verify_ledger(destination)["valid"])
        self.assertEqual(read_commits(destination), read_commits(self.vault))

    def test_old_completion_replays_without_inventing_dispositions(self):
        append_commit(self.vault, "test", "session.complete", "旧版完成事件",
                      {"session_id": self.sid, "completed_at": "2026-09-18T01:02:03Z"})
        rebuild_projection(self.vault, force=True)
        plan = self.current()
        self.assertEqual((plan["status"], plan["completed_at"], plan["completion"]),
                         ("completed", "2026-09-18T01:02:03Z", None))
        self.assertFalse(plan["progress"]["can_finish"])
        self.assertEqual(history_rows(self.vault), [])


if __name__ == "__main__":
    unittest.main()
