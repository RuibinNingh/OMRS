"""普通即时练习的轮次回执：重试、部分成功、并发及事务回滚。"""
import concurrent.futures
import tempfile
import unittest
from unittest.mock import patch

from omrs.creation import create_question
from omrs.data_repository import history_rows
from omrs.feedback import process_feedback
from omrs.ledger import connect
from omrs.question_ops import suspend_question


class InstantFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.vault = self.directory.name
        self.question = create_question(self.vault, "数学", "合成", 5, question_text="合成题目")
        self.round_id = "PR-" + "12" * 16

    def submit(self, rows=None, round_id=None):
        return process_feedback(self.vault, rows if rows is not None else [self.payload()],
                                "IMM-20261024000000", practice_round_id=round_id or self.round_id)

    def payload(self, **values):
        return {"question_id": self.question["question_id"], "sub_score": 8, "is_correct": True, **values}

    def attempts(self):
        with connect(self.vault) as db:
            return db.execute("SELECT attempts FROM mastery_projection WHERE question_id=?",
                              (self.question["question_id"],)).fetchone()[0]

    def test_retry_reuses_accepted_values_and_does_not_kill_question(self):
        first = self.submit()[0]
        second = self.submit([self.payload(sub_score=0, is_correct=False)])[0]
        self.assertEqual(second, {**first, "reused": True})
        self.assertEqual((second["is_correct"], second["sub_score"], second["new_mastery"]), (True, 8, .4))
        self.assertEqual(self.attempts(), 1)
        self.assertEqual(len(history_rows(self.vault)), 1)

    def test_same_second_new_round_can_count_new_answer(self):
        self.submit()
        self.submit(round_id="PR-" + "34" * 16)
        self.assertEqual(self.attempts(), 2)

    def test_duplicate_batch_and_partial_retry(self):
        values = self.payload()
        out = self.submit([values, values, {"question_id": "missing", "sub_score": 8, "is_correct": True}])
        self.assertEqual(out[1], {**out[0], "reused": True})
        self.assertEqual(out[2]["status"], "error")
        self.assertEqual(self.attempts(), 1)
        other = create_question(self.vault, "数学", "合成", 5)
        rows = [values, self.payload(question_id=other["question_id"], sub_score=-1)]
        self.assertEqual(self.submit(rows)[1]["status"], "error")
        rows[1]["sub_score"] = 4
        fixed = self.submit(rows)
        self.assertTrue(fixed[0]["reused"])
        self.assertNotIn("reused", fixed[1])
        self.assertEqual(len(history_rows(self.vault)), 2)

    def test_feedback_and_receipt_roll_back_together(self):
        with patch("omrs.projection_runtime.apply_incremental", side_effect=OSError("合成发布失败")):
            with self.assertRaises(OSError):
                self.submit()
        with connect(self.vault) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM op_results WHERE op_id LIKE 'feedback:instant:%'").fetchone()[0], 0)
        self.assertNotIn("reused", self.submit()[0])
        self.assertEqual(self.attempts(), 1)

    def test_concurrent_retries_count_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.submit(), range(2)))
        self.assertEqual(sum(bool(out[0].get("reused")) for out in results), 1)
        self.assertEqual(self.attempts(), 1)

    def test_suspended_question_still_returns_its_successful_receipt(self):
        first = self.submit()[0]
        suspend_question(self.vault, self.question["uid"], True)
        self.assertEqual(self.submit()[0], {**first, "reused": True})
        self.assertEqual(self.attempts(), 1)

    def test_invalid_round_context_and_missing_stable_identity_do_not_write(self):
        for identity in ("bad", None, 123):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                process_feedback(self.vault, [self.payload()], "IMM-synthetic", practice_round_id=identity)
        with self.assertRaises(ValueError):
            process_feedback(self.vault, [self.payload()], "", practice_round_id=self.round_id)
        out = self.submit([{"uid": self.question["uid"], "sub_score": 8, "is_correct": True}])
        self.assertEqual(out[0]["status"], "error")
        self.assertEqual(self.attempts(), 0)
