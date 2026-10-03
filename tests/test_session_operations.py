"""MCP 创建复习计划的幂等、身份、授权与事务原子性验收。"""
import concurrent.futures
import datetime
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from omrs import session_operations as operations
from omrs.creation import create_question
from omrs.data_repository import resolve_question
from omrs.errors import RequestError
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, connect, ledger_path, read_commits
from omrs.locking import WriteLockTimeout, write_lock
from omrs.projections import rebuild_projection
from omrs.projection_runtime import invalidate
from omrs.question_ops import delete_question, move_question, suspend_question
from omrs.sessions import delete_session, get_session, list_sessions


class SessionOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.addCleanup(invalidate, self.vault)
        self.questions = [create_question(self.vault, subject, category, 5,
                                         question_text="求 1+1", answer_text="2")
                          for subject, category in (("数学", "代数"), ("数学", "几何"), ("物理", "力学"))]
        self.items = [{"question_id": q["question_id"], "source": "due"} for q in self.questions]

    def create(self, items=None, request_id="request-1", key_id="key-1", validate=lambda: None):
        return operations.create_mcp_session(self.vault, self.items[:1] if items is None else items,
                                             key_id, request_id, validate)

    def counts(self):
        with connect(self.vault) as db:
            return tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                         for table in ("commits", "session_projection", "op_results", "history_projection"))

    def learning(self):
        with connect(self.vault) as db:
            return [tuple(row) for row in db.execute("SELECT * FROM mastery_projection ORDER BY question_id")]

    def assert_error(self, code, fn):
        with self.assertRaises(RequestError) as raised:
            fn()
        self.assertEqual(raised.exception.code, code)

    def test_single_question_is_persistent_without_learning_changes(self):
        before, learning = self.counts(), self.learning()
        result = self.create([{**self.items[0], "source": "proficiency"}])
        self.assertTrue(result["session_id"].startswith("EXP-"))
        self.assertFalse(result["reused"])
        self.assertTrue(result["available"])
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["subject_filter"], "数学")
        self.assertEqual((result["count"], result["pending_count"], result["feedback_count"]), (1, 1, 0))
        self.assertEqual(result["entries"][0]["source"], "proficiency")
        self.assertEqual(result["entries"][0]["question_id"], self.questions[0]["question_id"])
        self.assertEqual(datetime.datetime.fromisoformat(result["created_at"]).utcoffset(), datetime.timedelta())
        self.assertEqual(self.learning(), learning)
        self.assertEqual(self.counts(), (before[0] + 1, 1, 1, before[3]))
        commit = read_commits(self.vault)[-1]
        self.assertEqual((commit["source"], commit["commit_type"]), ("mcp", "session.create"))
        self.assertNotIn("request_id", commit["payload"])
        self.assertEqual(get_session(self.vault, result["session_id"])["pending_count"], 1)

    def test_normalized_retry_ignores_display_uid_and_reuses_before_occupancy(self):
        first = self.create([{**self.items[0], "uid": self.questions[0]["uid"]}])
        before = self.counts()
        retry = self.create([{**self.items[0], "question_id": " " + self.items[0]["question_id"] + " ", "uid": "过期显示编号"}, self.items[0]])
        self.assertEqual(retry["session_id"], first["session_id"])
        self.assertTrue(retry["reused"])
        self.assertEqual(self.counts(), before)

    def test_selection_preserves_first_order_and_sources(self):
        first = {**self.items[1], "source": "proficiency"}
        result = self.create([first, self.items[0], first])
        self.assertEqual(result["count"], 2)
        self.assertEqual([e["question_id"] for e in result["entries"]], [self.items[1]["question_id"], self.items[0]["question_id"]])
        self.assertEqual([e["source"] for e in result["entries"]], ["proficiency", "due"])

    def test_mixed_subjects_have_no_subject_filter(self):
        self.assertEqual(self.create([self.items[0], self.items[2]])["subject_filter"], "")

    def test_changed_payload_and_order_conflict(self):
        self.create(self.items[:2])
        before = self.counts()
        for items in (list(reversed(self.items[:2])), [{**self.items[0], "source": "proficiency"}, self.items[1]], self.items[:1]):
            with self.subTest(items=items):
                self.assert_error("request_conflict", lambda: self.create(items))
                self.assertEqual(self.counts(), before)

    def test_request_identity_is_separate_for_each_key(self):
        first = self.create()
        second = self.create(self.items[1:2], key_id="key-2")
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(self.counts()[2], 2)

    def test_invalid_item_shapes_never_write(self):
        cases = ([], self.items * 34, None, "items", [None], ["question"],
                 [{"question_id": "", "source": "due"}], [{"question_id": " " * 2, "source": "due"}],
                 [{"question_id": "q" * 201, "source": "due"}], [{"question_id": 1, "source": "due"}],
                 [{"question_id": self.items[0]["question_id"]}], [{**self.items[0], "source": "instant"}],
                 [{**self.items[0], "uid": 1}], [{**self.items[0], "extra": "unexpected"}],
                 [self.items[0], {**self.items[0], "source": "proficiency"}])
        before = self.counts()
        for items in cases:
            with self.subTest(items=items):
                self.assert_error("invalid_request", lambda: operations.create_mcp_session(self.vault, items, "key-1", "request-1", lambda: None))
                self.assertEqual(self.counts(), before)

    def test_invalid_request_identity_never_writes(self):
        before = self.counts()
        for request_id in (None, "", "bad/request", "x" * 129):
            with self.subTest(request_id=request_id):
                self.assert_error("invalid_request", lambda: self.create(request_id=request_id))
        self.assert_error("invalid_request", lambda: self.create(key_id=""))
        self.assertEqual(self.counts(), before)

    def test_missing_item_rejects_whole_selection(self):
        before = self.counts()
        self.assert_error("invalid_request", lambda: self.create([self.items[0], {"question_id": "missing", "source": "due"}]))
        self.assertEqual(self.counts(), before)
        self.assertEqual(list_sessions(self.vault), [])

    def test_occupied_item_rejects_whole_selection(self):
        self.create(self.items[1:2])
        before = self.counts()
        self.assert_error("state_conflict", lambda: self.create(self.items[:2], request_id="request-2"))
        self.assertEqual(self.counts(), before)
        self.assertEqual(len(list_sessions(self.vault)), 1)

    def test_archived_and_suspended_selections_are_rejected(self):
        suspend_question(self.vault, self.questions[0]["uid"])
        delete_question(self.vault, self.questions[1]["uid"])
        before = self.counts()
        for item in self.items[:2]:
            self.assert_error("state_conflict", lambda: self.create([item]))
            self.assertEqual(self.counts(), before)

    def test_stable_identity_follows_move_even_when_uid_is_reused(self):
        original = self.questions[0]
        move_question(self.vault, original["uid"], "数学", "新分类")
        replacement = create_question(self.vault, "数学", "代数", 5, question_text="替代题", answer_text="新答案")
        current = resolve_question(self.vault, question_id=original["question_id"])
        result = self.create([{**self.items[0], "uid": replacement["uid"]}])
        self.assertEqual(result["entries"][0]["question_id"], original["question_id"])
        self.assertEqual(result["entries"][0]["uid"], current["uid"])
        self.assertNotEqual(result["entries"][0]["question_id"], replacement["question_id"])
        self.assertEqual(result["entries"][0]["uid_at_creation"], current["uid"])

    def test_retracted_retry_does_not_resurrect_and_reserves_id(self):
        fixed = datetime.datetime(2026, 10, 3, 10, 0, tzinfo=datetime.timezone.utc)
        with patch.object(operations, "_now", return_value=fixed):
            first = self.create()
            delete_session(self.vault, first["session_id"])
            before = self.counts()
            retry = self.create()
            self.assertEqual(self.counts(), before)
            self.assertEqual(retry["session_id"], first["session_id"])
            self.assertEqual(retry["status"], "retracted")
            self.assertFalse(retry["available"])
            self.assertEqual(retry["actionable_pending_count"], 0)
            self.assertIsNone(get_session(self.vault, first["session_id"]))
            second = self.create(request_id="request-2")
            self.assertNotEqual(second["session_id"], first["session_id"])

    def test_restore_keeps_receipt_without_resurrecting_or_recycling_id(self):
        target = read_commits(self.vault)[-1]["seq"]
        fixed = datetime.datetime(2026, 10, 3, 10, 0, tzinfo=datetime.timezone.utc)
        with patch.object(operations, "_now", return_value=fixed):
            first = self.create()
            append_commit(self.vault, "test", "state.restore", "恢复创建前状态", {"target_seq": target})
            rebuild_projection(self.vault)
            before = self.counts()
            retry = self.create()
            self.assertEqual(self.counts(), before)
            self.assertTrue(retry["reused"])
            self.assertEqual(retry["status"], "retracted")
            self.assertFalse(retry["available"])
            second = self.create(request_id="request-2")
            self.assertNotEqual(second["session_id"], first["session_id"])

    def test_retry_reports_current_completion_and_progress(self):
        first = self.create()
        process_feedback(self.vault, [{"question_id": self.items[0]["question_id"], "uid": self.questions[0]["uid"],
                                      "is_correct": True, "sub_score": 8}], first["session_id"])
        before = self.counts()
        retry = self.create()
        self.assertEqual(retry["status"], "completed")
        self.assertEqual((retry["pending_count"], retry["feedback_count"]), (0, 1))
        self.assertTrue(retry["feedback_complete"])
        self.assertTrue(retry["reused"])
        self.assertEqual(self.counts(), before)

    def test_retry_keeps_archived_and_suspended_entry_information(self):
        self.create(self.items[:2])
        delete_question(self.vault, self.questions[0]["uid"])
        suspend_question(self.vault, self.questions[1]["uid"])
        before = self.counts()
        retry = self.create(self.items[:2])
        self.assertEqual([e["availability"] for e in retry["entries"]], ["archived", "suspended"])
        self.assertEqual((retry["total_count"], retry["count"], retry["pending_count"], retry["blocked_count"]), (2, 1, 1, 1))
        self.assertEqual(retry["actionable_pending_count"], 0)
        self.assertEqual(retry["status"], "active")
        self.assertEqual(self.counts(), before)

    def test_initial_permission_rejection_never_writes(self):
        before = self.counts()
        def denied():
            raise PermissionError("密钥已吊销")
        with self.assertRaises(PermissionError):
            self.create(validate=denied)
        self.assertEqual(self.counts(), before)

    def test_permission_is_rechecked_after_waiting_for_common_lock(self):
        allowed, started = [True], threading.Event()
        def validate():
            if not allowed[0]:
                raise PermissionError("密钥已吊销")
        def run():
            started.set()
            return self.create(validate=validate)
        before = self.counts()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with write_lock():
                future = pool.submit(run)
                self.assertTrue(started.wait(5))
                allowed[0] = False
            with self.assertRaises(PermissionError):
                future.result(timeout=10)
        self.assertEqual(self.counts(), before)

    def test_permission_revoked_during_projection_rolls_back(self):
        allowed, before = [True], self.counts()
        original = operations.apply_incremental
        def revoke(*args, **kwargs):
            result = original(*args, **kwargs)
            allowed[0] = False
            return result
        def validate():
            if not allowed[0]:
                raise PermissionError("密钥已吊销")
        with patch.object(operations, "apply_incremental", side_effect=revoke):
            with self.assertRaises(PermissionError):
                self.create(validate=validate)
        rebuild_projection(self.vault)
        self.assertEqual(self.counts(), before)
        self.assertEqual(list_sessions(self.vault), [])

    def test_permission_revoked_after_commit_keeps_legal_session(self):
        def validate():
            with connect(self.vault) as db:
                if db.execute("SELECT 1 FROM op_results WHERE op_id LIKE 'mcp:session:%'").fetchone():
                    raise PermissionError("响应前密钥已吊销")
        with self.assertRaises(PermissionError):
            self.create(validate=validate)
        self.assertEqual(len(list_sessions(self.vault)), 1)
        before = self.counts()
        self.assertTrue(self.create()["reused"])
        self.assertEqual(self.counts(), before)

    def test_projection_failure_rolls_back_fact_receipt_and_cache(self):
        before, learning = self.counts(), self.learning()
        original = operations.apply_incremental
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("投影故障")
        with patch.object(operations, "apply_incremental", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "投影故障"):
                self.create()
        self.assertEqual(self.counts(), before)
        rebuild_projection(self.vault)
        self.assertEqual(list_sessions(self.vault), [])
        self.assertEqual(self.learning(), learning)
        self.assertFalse(self.create()["reused"])

    def test_receipt_insert_failure_rolls_back_fact_and_projection(self):
        with connect(self.vault) as db:
            db.execute("CREATE TRIGGER refuse_receipt BEFORE INSERT ON op_results BEGIN SELECT RAISE(ABORT, '回执故障'); END")
        before = self.counts()
        with self.assertRaises(sqlite3.IntegrityError):
            self.create()
        rebuild_projection(self.vault)
        self.assertEqual(self.counts(), before)
        self.assertEqual(list_sessions(self.vault), [])
        with connect(self.vault) as db:
            db.execute("DROP TRIGGER refuse_receipt")
        self.assertFalse(self.create()["reused"])

    def test_concurrent_same_request_creates_once(self):
        barrier = threading.Barrier(6)
        def run():
            barrier.wait(timeout=10)
            return self.create()
        before = self.counts()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(run) for _ in range(6)]
            results = [f.result(timeout=20) for f in futures]
        self.assertEqual(len({r["session_id"] for r in results}), 1)
        self.assertEqual(sum(not r["reused"] for r in results), 1)
        self.assertEqual(self.counts(), (before[0] + 1, 1, 1, before[3]))

    def test_concurrent_requests_cannot_occupy_same_question(self):
        barrier = threading.Barrier(2)
        def run(request_id):
            barrier.wait(timeout=10)
            try:
                return self.create(request_id=request_id)
            except RequestError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, "request-" + str(i)) for i in range(2)]
            results = [f.result(timeout=20) for f in futures]
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertIn("state_conflict", results)
        self.assertEqual(self.counts()[1:3], (1, 1))

    def test_external_chain_append_retries_before_creating(self):
        original, called = operations.rebuild_projection, [0]
        def changed(vault):
            state = original(vault)
            called[0] += 1
            if called[0] == 1:
                append_commit(vault, "test", "system.note", "模拟另一个进程追加", {})
            return state
        with patch.object(operations, "rebuild_projection", side_effect=changed):
            result = self.create()
        self.assertGreaterEqual(called[0], 2)
        self.assertEqual(result["count"], 1)
        self.assertEqual(self.counts()[1:3], (1, 1))

    def test_external_sqlite_writer_returns_write_busy_without_partial_creation(self):
        before = self.counts()
        original = operations.rebuild_projection
        external = sqlite3.connect(ledger_path(self.vault))
        def locked(vault):
            state = original(vault)
            external.execute("BEGIN IMMEDIATE")
            return state
        def limited(vault):
            db = connect(vault)
            db.execute("PRAGMA busy_timeout=1")
            return db
        try:
            with patch.object(operations, "rebuild_projection", side_effect=locked), patch.object(operations, "connect", side_effect=limited):
                with self.assertRaises(WriteLockTimeout):
                    self.create()
        finally:
            external.rollback()
            external.close()
        self.assertEqual(self.counts(), before)


if __name__ == "__main__":
    unittest.main()
