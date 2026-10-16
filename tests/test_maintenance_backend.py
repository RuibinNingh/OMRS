"""全面检查后的数据一致性与 CLI 故障回归；全部使用合成临时 Vault。"""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from omrs import creation, drafts
from omrs.agent.tools import read as read_tools
from omrs.content_history import projection_row
from omrs.data_repository import history_rows
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, connect
from omrs.projections import rebuild_projection
from omrs.question_ops import move_question, save_question_markdown
from omrs.sessions import create_session_from_selection, list_sessions
from omrs.workspace_sync import scan_workspace


class BackendMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="omrs-maintenance-test-")
        self.vault = self.temp.name
        self.addCleanup(self.temp.cleanup)
        read_tools._TEXT_CACHE.clear()
        self.addCleanup(read_tools._TEXT_CACHE.clear)

    def question(self, category="函数", body="合成题面A"):
        return creation.create_question(self.vault, "数学", category, 5, question_text=body)

    def session(self, question):
        return create_session_from_selection(self.vault, [{"question_id": question["question_id"], "source": "due"}])

    def payload(self, question, **extra):
        return {"question_id": question["question_id"], "uid": question["uid"],
                "sub_score": 9, "is_correct": True, **extra}

    def attempts(self, question):
        with connect(self.vault) as db:
            return db.execute("SELECT attempts FROM mastery_projection WHERE question_id=?", (question["question_id"],)).fetchone()[0]

    def review_commit(self):
        with connect(self.vault) as db:
            return db.execute("SELECT commit_id FROM commits WHERE commit_type='review.batch_submit' ORDER BY seq DESC LIMIT 1").fetchone()[0]

    def test_session_retry_reuses_exact_receipt_even_after_history_replace(self):
        question = self.question()
        session = self.session(question)
        first = process_feedback(self.vault, [self.payload(question)], session["session_id"])[0]
        retry = process_feedback(self.vault, [self.payload(question, sub_score=1, is_correct=False)], session["session_id"])[0]
        self.assertEqual(retry, {**first, "reused": True})
        append_commit(self.vault, "test", "review.replace", "人工订正", {
            "target_commit_id": self.review_commit(), "target_review_index": 0,
            "replacement": {"sub_score": 2, "is_correct": False}})
        rebuild_projection(self.vault)
        self.assertEqual(process_feedback(self.vault, [self.payload(question)], session["session_id"])[0], {**first, "reused": True})
        self.assertEqual(self.attempts(question), 1)
        self.assertEqual(len(history_rows(self.vault)), 1)

    def test_session_duplicate_in_batch_and_later_new_item(self):
        first, second = self.question(), self.question()
        session = create_session_from_selection(self.vault, [{"question_id": q["question_id"]} for q in (first, second)])
        result = process_feedback(self.vault, [self.payload(first), self.payload(first), self.payload(second)], session["session_id"])
        self.assertEqual(result[1], {**result[0], "reused": True})
        self.assertEqual([self.attempts(q) for q in (first, second)], [1, 1])
        self.assertEqual(len(history_rows(self.vault)), 2)

    def test_session_invalid_entry_does_not_consume_feedback(self):
        question = self.question()
        session = self.session(question)
        result = process_feedback(self.vault, [self.payload(question, entry_id="other-entry")], session["session_id"])
        self.assertEqual(result[0]["status"], "error")
        self.assertEqual(self.attempts(question), 0)
        self.assertEqual(process_feedback(self.vault, [self.payload(question, entry_id=session["entries"][0]["entry_id"])], session["session_id"])[0]["status"], "ok")

    def test_session_receipt_and_feedback_roll_back_together(self):
        question = self.question()
        session = self.session(question)
        with mock.patch("omrs.projection_runtime.apply_incremental", side_effect=OSError("合成发布失败")):
            with self.assertRaises(OSError):
                process_feedback(self.vault, [self.payload(question)], session["session_id"])
        with connect(self.vault) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM op_results WHERE op_id LIKE 'feedback:session:%'").fetchone()[0], 0)
        result = process_feedback(self.vault, [self.payload(question)], session["session_id"])
        self.assertNotIn("reused", result[0])
        self.assertEqual(self.attempts(question), 1)

    def test_concurrent_session_retries_count_once(self):
        question = self.question()
        session = self.session(question)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: process_feedback(self.vault, [self.payload(question)], session["session_id"]), range(2)))
        self.assertEqual(sum(bool(result[0].get("reused")) for result in results), 1)
        self.assertEqual(self.attempts(question), 1)

    def test_older_retracted_feedback_is_not_resubmitted_without_receipt(self):
        question = self.question()
        session = self.session(question)
        process_feedback(self.vault, [self.payload(question)], session["session_id"])
        target = self.review_commit()
        with connect(self.vault) as db:
            db.execute("DELETE FROM op_results WHERE op_id LIKE 'feedback:session:%'")
        append_commit(self.vault, "test", "review.retract", "撤销原反馈", {
            "target_commit_id": target, "target_review_index": 0})
        rebuild_projection(self.vault)
        result = process_feedback(self.vault, [self.payload(question)], session["session_id"])
        self.assertTrue(result[0]["reused"])
        self.assertEqual(self.attempts(question), 0)
        self.assertEqual(history_rows(self.vault), [])

    def test_independent_instant_practice_still_counts_repeated_answers(self):
        question = self.question()
        for _ in range(2):
            process_feedback(self.vault, [self.payload(question)], "IMM-synthetic")
        self.assertEqual(self.attempts(question), 2)

    def test_cache_tracks_projected_content_across_external_edit_scan_restore(self):
        question = self.question()
        path = Path(self.vault, question["file_path"])
        original = path.read_text(encoding="utf-8")
        original_hash = projection_row(self.vault, uid=question["uid"])["content_hash"]
        path.write_text(original.replace("合成题面A", "合成题面B"), encoding="utf-8")
        read = lambda: read_tools.get_question({"vault": self.vault}, {"uid": question["uid"]})["result"]
        before_scan = read()
        self.assertIn("合成题面A", before_scan["sections"]["题目"])
        self.assertEqual(before_scan["content_hash"], original_hash)
        scan_workspace(self.vault)
        self.assertIn("合成题面B", read()["sections"]["题目"])
        save_question_markdown(self.vault, question["uid"], original)
        restored = read()
        self.assertEqual(restored["content_hash"], original_hash)
        self.assertIn("合成题面A", restored["sections"]["题目"])

    def test_question_note_uses_same_verified_version_as_sections(self):
        question = self.question()
        path = Path(self.vault, question["file_path"])
        original = path.read_text(encoding="utf-8")
        saved = original.replace("# 备注", "# 备注\n\n## 补充备注\n合成备注A\n", 1)
        save_question_markdown(self.vault, question["uid"], saved)
        path.write_text(saved.replace("合成备注A", "外部备注B"), encoding="utf-8")
        result = read_tools.get_question({"vault": self.vault}, {"uid": question["uid"]})["result"]
        self.assertEqual(result["note"], "合成备注A")


    def test_missing_or_corrupt_blob_never_caches_unverified_file(self):
        question = self.question()
        path = Path(self.vault, question["file_path"])
        original = path.read_text(encoding="utf-8")
        key = projection_row(self.vault, uid=question["uid"])["content_hash"]
        with connect(self.vault) as db:
            db.execute("DELETE FROM blobs WHERE hash=?", (key,))
        path.write_text(original.replace("合成题面A", "未扫描正文B"), encoding="utf-8")
        self.assertIsNone(read_tools._content(self.vault, question["uid"])[1])
        self.assertNotIn(key, read_tools._TEXT_CACHE)
        path.write_text(original, encoding="utf-8")
        self.assertIn("合成题面A", read_tools._content(self.vault, question["uid"])[1][0]["题目"])
        read_tools._TEXT_CACHE.clear()
        with connect(self.vault) as db:
            db.execute("INSERT INTO blobs(hash,content,created_at) VALUES(?,?,?)", (key, "损坏正文", "2026-10-16"))
        self.assertIsNone(read_tools._content(self.vault, question["uid"])[1])
        self.assertNotIn(key, read_tools._TEXT_CACHE)

    def test_move_and_create_reject_hidden_taxonomy_without_side_effects(self):
        question = self.question()
        for subject, category in (("数学", ".omrs"), ("数学", ".hidden"), (".hidden", "正常"), ("数学", "[非法]")):
            with self.subTest(subject=subject, category=category):
                with self.assertRaises(ValueError):
                    move_question(self.vault, question["uid"], subject, category)
                with self.assertRaises(ValueError):
                    creation.create_question(self.vault, subject, category, 5)
        self.assertTrue(Path(self.vault, question["file_path"]).is_file())
        self.assertIsNotNone(projection_row(self.vault, uid=question["uid"]))
        moved = move_question(self.vault, question["uid"], " 数学 ", " 合法   分类 ")
        scan_workspace(self.vault)
        self.assertEqual(projection_row(self.vault, uid=moved["uid"])["category"], "合法 分类")

    def test_move_respects_failed_draft_reservation_and_retry_completes(self):
        question = self.question("原分类")
        draft = drafts.create_draft(self.vault, {"subject": "数学", "category": "目标分类", "blocks": [
            {"section": "题目", "kind": "text", "text": "合成草稿"}]})
        with mock.patch("omrs.creation.create_question", side_effect=OSError("合成落盘失败")):
            with self.assertRaises(OSError):
                drafts.commit_draft(self.vault, draft["id"], draft["revision"])
        db = drafts.connect(self.vault)
        try:
            reserved = dict(db.execute("SELECT * FROM commit_operations WHERE draft_id=?", (draft["id"],)).fetchone())
        finally:
            db.close()
        moved = move_question(self.vault, question["uid"], "数学", "目标分类")
        self.assertNotEqual(moved["uid"], reserved["uid"])
        drafts.commit_draft(self.vault, draft["id"], draft["revision"])
        self.assertIsNotNone(projection_row(self.vault, uid=reserved["uid"]))
        scan_workspace(self.vault)
        self.assertIsNotNone(projection_row(self.vault, uid=moved["uid"]))

    def test_concurrent_move_and_create_allocate_different_uids(self):
        question = self.question("原分类")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            moved = pool.submit(move_question, self.vault, question["uid"], "数学", "目标分类")
            created = pool.submit(self.question, "目标分类")
            results = [moved.result(), created.result()]
        self.assertNotEqual(results[0]["uid"], results[1]["uid"])
        scan_workspace(self.vault)
        self.assertTrue(all(projection_row(self.vault, uid=result["uid"]) for result in results))

    def cli(self, *args):
        env = dict(os.environ)
        for name in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"):
            env.pop(name, None)
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "omrs_engine.py"),
                               "--vault", self.vault, *args], cwd=self.vault, env=env,
                              capture_output=True, text=True, timeout=30)

    def test_cli_session_new_empty_and_populated_print_current_schema(self):
        empty = self.cli("sessions", "new")
        self.assertEqual(empty.returncode, 0, empty.stderr)
        self.assertEqual(list_sessions(self.vault), [])
        question = self.question()
        created = self.cli("sessions", "new", "-n", "1")
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn(f"[{question['uid']}] M=", created.stdout)
        self.assertEqual(len(list_sessions(self.vault)), 1)

    def test_cli_invalid_operations_exit_nonzero_and_do_not_write_export(self):
        output = Path(self.vault, "must-not-exist.html")
        for args in (("sessions", "show"), ("sessions", "delete"),
                     ("sessions", "show", "--id", "missing"),
                     ("sessions", "delete", "--id", "missing"),
                     ("export", "--session", "missing", "--uids", "函数1", "-o", str(output))):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, "需要 --id|未找到|只能二选一")
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
