"""诊断日志的提交时机、容量、并发与故障；只使用合成临时 Vault。"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from omrs import log_utils as logs
from omrs.creation import create_question
from omrs.feedback import process_feedback
from omrs.ledger import read_commits
from omrs.llm.compat import resolve_compat
from omrs.llm.openai_compat import OpenAICompatClient
from omrs.log_export import list_logs
from omrs.sessions import create_session_from_selection


class LoggingTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="omrs-diagnostic-test-")
        self.addCleanup(work.cleanup)
        self.vault = work.name
        self.root = Path(self.vault)
        warning = patch.object(logs, "_LAST_WARNING", None)
        warning.start()
        self.addCleanup(warning.stop)

    def entries(self):
        return "".join(path.read_text(encoding="utf-8") for path in (self.root / "logs").glob("*.log"))

    def question(self):
        return create_question(self.vault, "数学", "日志验证", 5, question_text="不应写入诊断的题面")

    def feedback(self, question):
        return {"question_id": question["question_id"], "sub_score": 9, "is_correct": True}

    def test_committed_feedback_is_linked_to_ledger_and_duplicate_retry_does_not_log_again(self):
        question = self.question()
        session = create_session_from_selection(self.vault, [{"question_id": question["question_id"], "source": "due"}])
        payload = self.feedback(question)
        result = process_feedback(self.vault, [payload, payload], session["session_id"])
        self.assertTrue(result[1]["reused"])
        process_feedback(self.vault, [payload], session["session_id"])
        commits = [c for c in read_commits(self.vault) if c["commit_type"] == "review.batch_submit"]
        text = self.entries()
        self.assertEqual(len(commits), 1)
        self.assertEqual(text.count("[FEEDBACK]"), 1)
        for value in (question["question_id"], session["session_id"], commits[0]["commit_id"], "+08:00"):
            self.assertIn(value, text)
        self.assertNotIn("不应写入诊断的题面", text)

    def test_invalid_and_rolled_back_feedback_leave_no_success_diagnostic(self):
        question = self.question()
        self.assertEqual(process_feedback(self.vault, [{**self.feedback(question), "sub_score": 99}])[0]["status"], "error")
        with patch("omrs.projection_runtime.apply_incremental", side_effect=RuntimeError("合成回滚")):
            with self.assertRaisesRegex(RuntimeError, "合成回滚"):
                process_feedback(self.vault, [self.feedback(question)])
        self.assertNotIn("[FEEDBACK]", self.entries())
        self.assertFalse(any(c["commit_type"] == "review.batch_submit" for c in read_commits(self.vault)))

    def test_log_disk_failure_warns_without_changing_committed_feedback(self):
        question = self.question()
        with patch.object(logs, "_directory_lock", side_effect=OSError("不输出此异常原文")), self.assertLogs("omrs.logs") as captured:
            result = process_feedback(self.vault, [self.feedback(question)])
        self.assertEqual(result[0]["status"], "ok")
        self.assertTrue(any(c["commit_type"] == "review.batch_submit" for c in read_commits(self.vault)))
        self.assertNotIn("不输出此异常原文", "".join(captured.output))

    def test_rotation_preserves_whole_utf8_records_and_export_can_find_backups(self):
        path = self.root / "logs/omrs_2026-10-20.log"
        with patch.object(logs, "MAX_LOG_BYTES", 20):
            for index in range(7):
                self.assertTrue(logs.append_log(path, f"中文-{index}\n"))
        files = sorted(path.parent.glob("*.log*"))
        self.assertEqual(len(files), 4)
        self.assertTrue(all(p.stat().st_size <= 20 for p in files))
        retained = [line for p in files for line in p.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(set(retained), {f"中文-{i}" for i in range(7)})
        self.assertEqual(len(list_logs(self.vault)["files"]), 4)

    def test_runtime_retention_only_removes_owned_logs_and_respects_total_capacity(self):
        directory = self.root / "logs"
        directory.mkdir()
        for name in ("omrs_2026-09-19.log", "omrs_2026-10-18.log", "omrs_2026-10-19.log", "custom.log"):
            (directory / name).write_bytes(b"a" * 20)
        (directory / "omrs_2026-99-99.log").write_bytes(b"invalid-date")
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        (directory / "omrs_2020-01-01.log").symlink_to(outside)
        current = directory / "omrs_2026-10-20.log"
        with patch.object(logs, "RUNTIME_MAX_BYTES", 30):
            self.assertTrue(logs.append_log(current, "current\n", runtime_day=dt.date(2026, 10, 20)))
        self.assertFalse((directory / "omrs_2026-09-19.log").exists())
        self.assertFalse((directory / "omrs_2026-10-18.log").exists())
        self.assertTrue((directory / "omrs_2026-10-19.log").exists())
        self.assertTrue((directory / "custom.log").exists())
        self.assertTrue((directory / "omrs_2026-99-99.log").exists())
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_oversized_legacy_file_is_bounded_on_next_write(self):
        path = self.root / "agent.jsonl"
        path.write_bytes(b"old" * 20)
        with patch.object(logs, "MAX_LOG_BYTES", 20):
            self.assertTrue(logs.append_log(path, '{"new":true}\n'))
        self.assertEqual(sum(p.stat().st_size for p in self.root.glob("agent.jsonl*")), 13)

    def test_ai_oversized_record_remains_valid_json_and_disabled_logging_creates_nothing(self):
        path = self.root / "ai/agent-llm.jsonl"
        client = OpenAICompatClient("http://example.invalid", "secret", "test", resolve_compat("custom"))
        client._debug("request", {"large": "x" * 3000})
        self.assertFalse(path.parent.exists())
        client.debug_path = str(path)
        with patch.object(logs, "MAX_LOG_BYTES", 256):
            client._debug("request", {"large": "x" * 3000})
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(record["truncated"])
        self.assertGreater(record["original_bytes"], 256)
        self.assertLessEqual(path.stat().st_size, 256)
        self.assertNotIn("secret", path.read_text(encoding="utf-8"))

    def test_thread_writes_keep_each_record_intact(self):
        path = self.root / "threads.jsonl"
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(lambda i: logs.append_log(path, json.dumps({"id": i, "text": "中文"}) + "\n"), range(80))))
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual({row["id"] for row in rows}, set(range(80)))

    def test_separate_processes_share_rotation_lock_without_losing_records(self):
        script = """import json,sys
from omrs import log_utils as logs
logs.MAX_LOG_BYTES=1024
for index in range(20):
    assert logs.append_log(sys.argv[1],json.dumps({'worker':sys.argv[2],'i':index})+'\\n')
"""
        path = self.root / "process.jsonl"
        children = [subprocess.Popen([sys.executable, "-c", script, str(path), str(i)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(3)]
        for child in children:
            _, errors = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, errors.decode())
        files = list(self.root.glob("process.jsonl*"))
        rows = [json.loads(line) for p in files for line in p.read_text().splitlines()]
        self.assertEqual({(r["worker"], r["i"]) for r in rows}, {(str(i), j) for i in range(3) for j in range(20)})
        self.assertGreater(len(files), 1)

    def test_symbolic_links_are_not_written_or_followed(self):
        outside = self.root / "outside"
        outside.write_text("unchanged")
        target = self.root / "linked.log"
        target.symlink_to(outside)
        with self.assertLogs("omrs.logs"):
            self.assertFalse(logs.append_log(target, "new\n"))
        self.assertEqual(outside.read_text(), "unchanged")

    def test_write_warning_is_throttled_and_other_vault_is_independent(self):
        with patch.object(logs, "_directory_lock", side_effect=OSError("不回显")), patch.object(logs.time, "monotonic", side_effect=[10, 11, 71]), self.assertLogs("omrs.logs") as captured:
            for _ in range(3):
                self.assertFalse(logs.append_log(self.root / "broken.log", "x"))
        self.assertEqual(len(captured.output), 2)
        with tempfile.TemporaryDirectory() as other:
            self.assertTrue(logs.write_log(self.vault, "FIRST", {}))
            self.assertTrue(logs.write_log(other, "SECOND", {}))
            self.assertNotIn("SECOND", self.entries())
            self.assertIn("SECOND", next((Path(other) / "logs").glob("*.log")).read_text())


if __name__ == "__main__":
    unittest.main()
