"""配置发布的真实跨进程镜像、读快照及重算回执原子性。"""
from contextlib import contextmanager, closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from omrs import config_repository as repository
from omrs.common import (MASTERY_HEADERS, config_path, load_config, mastery_path,
                         save_config, save_csv)
from omrs.data_repository import history_rows, mastery_rows
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, connect, ledger_path, read_commits, verify_ledger
from omrs.projection_runtime import invalidate
from omrs.projections import rebuild_projection

ROOT = Path(__file__).resolve().parents[1]

# 独立解释器加载真实配置模块。屏障只控制调用时机，SQL、文件与提交均实际执行。
WORKER = r'''
import json, pathlib, sys, time
from unittest.mock import patch
from omrs import config_repository as repository
directory, vault, job, mode, value = sys.argv[1:]
directory = pathlib.Path(directory)
def wait():
    end = time.monotonic() + 10
    while not (directory / (job + '-resume')).exists():
        if time.monotonic() > end:
            raise RuntimeError('配置发布测试屏障超时')
        time.sleep(.01)
def marker():
    (directory / (job + '-ready')).write_text('1')
if mode in ('pause-finish', 'pause-write', 'pause-publication'):
    name = {'pause-finish':'_finish_mirror', 'pause-write':'_write_mirror',
            'pause-publication':'_publication_status'}[mode]
    original = getattr(repository, name)
    def paused(*args, **kwargs):
        marker(); wait()
        return original(*args, **kwargs)
    with patch.object(repository, name, side_effect=paused):
        result = repository.save(vault, {'ai_model': value})
else:
    marker()
    if mode == 'wait-save':
        wait()
    candidate = {'tuning': {'kill_streak': int(value)}} if mode == 'wait-save' else {'ai_model': value}
    result = repository.save(vault, candidate)
(directory / (job + '-result.json')).write_text(json.dumps(result))
(directory / (job + '-done')).write_text('1')
print(json.dumps(result))
'''


class ConfigPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="omrs-config-publication-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.vault = str(self.directory / "vault")
        self.processes = []
        self.addCleanup(self._stop_processes)
        self.addCleanup(invalidate, self.vault)
        repository.initialize(self.vault)

    def _stop_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
            for stream in (process.stdout, process.stderr):
                if stream:
                    stream.close()

    def _start(self, job, mode, value):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT)
        for key in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"):
            environment.pop(key, None)
        process = subprocess.Popen([sys.executable, "-c", WORKER, str(self.directory),
            self.vault, job, mode, str(value)], cwd=ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def _wait(self, marker):
        target = self.directory / marker
        end = time.monotonic() + 8
        while not target.exists():
            self.assertLess(time.monotonic(), end, "子进程未到达屏障：" + marker)
            time.sleep(.01)

    def _result(self, process, job):
        stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, stderr or stdout)
        return json.loads((self.directory / (job + "-result.json")).read_text())

    def _mirror(self):
        return json.loads(Path(config_path(self.vault)).read_text(encoding="utf-8"))

    def _seed_feedback(self, count=2):
        append_commit(self.vault, "test", "question.create", "原子发布夹具", {"question": {
            "question_id": "Q1", "uid": "函数1", "file_path": "错题/数学/函数/函数1.md",
            "subject": "数学", "category": "函数", "difficulty": 5,
            "current_tag": "#状态/待攻克", "metadata": {"tags": ["状态/待攻克"]}}})
        rebuild_projection(self.vault)
        process_feedback(self.vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True} for _ in range(count)])

    def test_late_old_publisher_cannot_overwrite_newer_process_mirror(self):
        first = self._start("A", "pause-finish", "旧发布者")
        self._wait("A-ready")
        second = self._start("B", "save", "新发布者")
        newest = self._result(second, "B")
        (self.directory / "A-resume").write_text("1")
        late = self._result(first, "A")
        self.assertTrue(late["superseded"])
        self.assertEqual(late["revision"], newest["revision"])
        self.assertEqual(self._mirror()["ai_model"], "新发布者")
        self.assertEqual(load_config(self.vault)["ai_model"], "新发布者")
        repository.initialize(self.vault)
        self.assertEqual(load_config(self.vault)["ai_model"], "新发布者")
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_mirror_write_holds_persistent_transaction_across_processes(self):
        first = self._start("A", "pause-write", "第一发布")
        self._wait("A-ready")
        second = self._start("B", "save", "第二发布")
        self._wait("B-ready")
        # 第三条实际 SQLite 连接拿不到写事务；不是仅依赖进程内 RLock。
        with closing(sqlite3.connect(ledger_path(self.vault), timeout=.05)) as db:
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                db.execute("BEGIN IMMEDIATE")
        self.assertFalse((self.directory / "B-done").exists())
        (self.directory / "A-resume").write_text("1")
        first_result = self._result(first, "A")
        second_result = self._result(second, "B")
        # 镜像事务释放后，B 可以先于 A 读取回执；A 返回较新版本时需明确覆盖。
        self.assertLessEqual(first_result["revision"], second_result["revision"])
        if first_result["revision"] == second_result["revision"]:
            self.assertTrue(first_result["superseded"])
        self.assertEqual(self._mirror()["ai_model"], "第二发布")
        self.assertEqual(load_config(self.vault)["ai_model"], "第二发布")

    def test_later_publication_between_mirror_and_response_returns_consistent_latest_status(self):
        self._seed_feedback()
        first = self._start("A", "pause-publication", "第一配置")
        self._wait("A-ready")
        second = self._start("B", "wait-save", 3)
        self._wait("B-ready")
        (self.directory / "B-resume").write_text("1")
        newest = self._result(second, "B")
        (self.directory / "A-resume").write_text("1")
        late = self._result(first, "A")
        self.assertTrue(late["superseded"])
        self.assertEqual(late["revision"], newest["revision"])
        self.assertEqual(late["tuning_effective"], newest["tuning_effective"])
        self.assertEqual(late["recalculation"], newest["recalculation"])
        self.assertEqual(late["policy_hash"], newest["policy_hash"])
        self.assertEqual(late["revision"], late["recalculation"]["revision"])

    def test_recalculation_receipt_and_projection_roll_back_with_audit_failure(self):
        self._seed_feedback()
        before = {"config": load_config(self.vault), "status": repository.public_status(self.vault),
                  "mastery": mastery_rows(self.vault), "history": history_rows(self.vault),
                  "commits": read_commits(self.vault)}
        with patch.object(repository, "append_commit_in_db", side_effect=RuntimeError("审计提交故障")):
            with self.assertRaisesRegex(RuntimeError, "审计提交故障"):
                save_config(self.vault, {"tuning": {"kill_streak": 3}, "ai_api_key": "合成秘密"})
        after = {"config": load_config(self.vault), "status": repository.public_status(self.vault),
                 "mastery": mastery_rows(self.vault), "history": history_rows(self.vault),
                 "commits": read_commits(self.vault)}
        self.assertEqual(after, before)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_successful_receipt_is_persistent_matches_audit_and_hides_secrets(self):
        self._seed_feedback()
        result = save_config(self.vault, {"tuning": {"kill_streak": 3}, "ai_api_key": "合成秘密"})
        summary = result["recalculation"]
        self.assertEqual((summary["status"], summary["questions"], summary["feedbacks"]), ("complete", 1, 2))
        self.assertEqual(summary["revision"], result["revision"])
        self.assertEqual(summary["policy_hash"], result["policy_hash"])
        self.assertGreaterEqual(summary["seconds"], 0)
        self.assertEqual(mastery_rows(self.vault)[0]["Current_Tag"], "#状态/待攻克")
        audit = read_commits(self.vault)[-1]
        self.assertEqual(audit["payload"]["recalculation"], summary)
        self.assertNotIn("合成秘密", json.dumps(audit, ensure_ascii=False))
        self.assertNotIn("合成秘密", json.dumps(repository.public_status(self.vault), ensure_ascii=False))
        public = repository.public_config(self.vault)
        self.assertNotIn("ai_api_key", public)
        self.assertTrue(public["ai_api_key_configured"])
        self.assertEqual(public["tuning_effective"], result["tuning_effective"])
        self.assertEqual(public["policy_hash"], public["recalculation"]["policy_hash"])
        with connect(self.vault) as db:
            saved = json.loads(db.execute("SELECT value FROM storage_meta WHERE key='config.recalculation'").fetchone()[0])
        self.assertEqual(saved, summary)
        repository.initialize(self.vault)
        self.assertEqual(repository.public_status(self.vault)["recalculation"], summary)
        save_config(self.vault, {"ai_model": "普通配置更新"})
        self.assertEqual(repository.public_status(self.vault)["recalculation"], summary)

    def test_empty_vault_receipt_does_not_block_legacy_bootstrap(self):
        from omrs.indexing import build_index
        self.assertEqual(read_commits(self.vault), [])
        self.assertEqual(repository.public_status(self.vault)["recalculation"]["questions"], 0)
        path = Path(self.vault) / "错题/数学/函数/函数1.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n科目: 数学\n分类: 函数\n难度: 5\ntags:\n  - 状态/待攻克\n---\n# 题目\n迁移合成题\n", encoding="utf-8")
        save_csv(mastery_path(self.vault), MASTERY_HEADERS, [{"UID": "函数1", "File_Path": "错题/数学/函数/函数1.md",
            "Subject": "数学", "Category": "函数", "Difficulty": "5", "Mastery": ".7", "EF": "2.5", "Attempts": "5"}])
        self.assertEqual(len(build_index(self.vault)), 1)
        commits = read_commits(self.vault)
        self.assertEqual([c["commit_type"] for c in commits[:2]], ["system.genesis", "legacy.bootstrap"])
        self.assertEqual(mastery_rows(self.vault)[0]["Attempts"], "5")
        self.assertEqual(float(mastery_rows(self.vault)[0]["Mastery"]), .7)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_pending_third_party_conflict_preserves_file_and_active_copy(self):
        with patch.object(repository, "_write_mirror", side_effect=OSError("镜像磁盘故障")):
            published = save_config(self.vault, {"ai_model": "活动配置"})
        self.assertTrue(published["mirror_pending"])
        original = self._mirror()
        Path(config_path(self.vault)).write_text(json.dumps({**original, "ai_model": "手改配置"}, ensure_ascii=False), encoding="utf-8")
        external = Path(config_path(self.vault)).read_bytes()
        retried = save_config(self.vault, {})
        self.assertTrue(retried["mirror_pending"])
        self.assertTrue(retried["mirror_conflict"])
        self.assertEqual(Path(config_path(self.vault)).read_bytes(), external)

        conflict = Path(config_path(self.vault) + ".active-conflict.json")
        self.assertEqual(json.loads(conflict.read_text(encoding="utf-8"))["ai_model"], "活动配置")
        self.assertEqual(load_config(self.vault)["ai_model"], "活动配置")
        with self.assertRaises(repository.ConfigMirrorConflict):
            repository.initialize(self.vault)
        self.assertEqual(Path(config_path(self.vault)).read_bytes(), external)

    def test_pending_malformed_third_party_json_is_a_conflict_not_a_lost_publication(self):
        with patch.object(repository, "_write_mirror", side_effect=OSError("镜像磁盘故障")):
            published = save_config(self.vault, {"ai_model": "活动配置"})
        self.assertTrue(published["mirror_pending"])
        external = b'{"ai_model": '
        Path(config_path(self.vault)).write_bytes(external)
        retried = save_config(self.vault, {})
        self.assertTrue(retried["mirror_pending"])
        self.assertTrue(retried["mirror_conflict"])
        self.assertEqual(Path(config_path(self.vault)).read_bytes(), external)
        conflict = Path(config_path(self.vault) + ".active-conflict.json")
        self.assertEqual(json.loads(conflict.read_text(encoding="utf-8"))["ai_model"], "活动配置")
        self.assertEqual(load_config(self.vault)["ai_model"], "活动配置")
        with self.assertRaises(repository.ConfigMirrorConflict):
            repository.initialize(self.vault)
        self.assertEqual(Path(config_path(self.vault)).read_bytes(), external)

    def test_projection_reads_active_policy_after_obtaining_its_write_transaction(self):
        from omrs import projection_runtime
        from omrs.common import load_tuning
        self._seed_feedback()
        writer = self._start("B", "wait-save", 3)
        self._wait("B-ready")
        original_connect = projection_runtime.connect
        called = False
        def after_other_publication(vault):
            nonlocal called
            if not called:
                called = True
                (self.directory / "B-resume").write_text("1")
                self._wait("B-done")
            return original_connect(vault)
        # 另一个进程在投影连接建立前提交调参；本请求不得再发布读到的旧策略。
        with patch.object(projection_runtime, "connect", side_effect=after_other_publication):
            state = projection_runtime.project(self.vault)
        self._result(writer, "B")
        self.assertEqual(state["_tuning"], load_tuning(self.vault))
        with connect(self.vault) as db:
            policy = db.execute("SELECT policy_hash FROM projection_meta WHERE id=1").fetchone()[0]
        self.assertEqual(policy, repository.public_status(self.vault)["policy_hash"])
        self.assertEqual(mastery_rows(self.vault)[0]["Current_Tag"], "#状态/待攻克")

    def test_feedback_retries_if_other_process_recalculates_after_state_read(self):
        from omrs import feedback as feedback_module
        self._seed_feedback(1)
        prefix = read_commits(self.vault)
        writer = self._start("B", "wait-save", 3)
        self._wait("B-ready")
        original_connect = feedback_module.connect
        called = False
        def after_other_publication(vault):
            nonlocal called
            if not called:
                called = True
                (self.directory / "B-resume").write_text("1")
                self._wait("B-done")
            return original_connect(vault)
        with patch.object(feedback_module, "connect", side_effect=after_other_publication):
            result = process_feedback(self.vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True}])[0]
        self._result(writer, "B")
        row = mastery_rows(self.vault)[0]
        self.assertEqual(result["new_mastery"], .9)
        self.assertEqual(result["new_mastery"], float(row["Mastery"]))
        self.assertEqual(result["tag"], row["Current_Tag"])
        self.assertEqual(result["new_interval"], int(row["Interval"]))
        self.assertEqual(row["Attempts"], "2")
        self.assertEqual(read_commits(self.vault)[:len(prefix)], prefix)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_feedback_projection_failure_rolls_back_fact_and_invalidates_mutated_cache(self):
        self._seed_feedback(1)
        prefix = read_commits(self.vault)
        before = mastery_rows(self.vault)
        with patch("omrs.projection_runtime._upsert_mastery", side_effect=RuntimeError("反馈投影写入故障")):
            with self.assertRaisesRegex(RuntimeError, "反馈投影写入故障"):
                process_feedback(self.vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True}])
        self.assertEqual(read_commits(self.vault), prefix)
        self.assertEqual(mastery_rows(self.vault), before)
        retried = process_feedback(self.vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True}])[0]
        self.assertEqual(retried["new_mastery"], 1)
        self.assertEqual(mastery_rows(self.vault)[0]["Attempts"], "2")

    def test_retracted_session_feedback_is_rejected_without_a_discarded_fact(self):
        from omrs.sessions import create_session_from_selection, delete_session
        self._seed_feedback(0)
        session = create_session_from_selection(self.vault, [{"question_id": "Q1"}])
        delete_session(self.vault, session["session_id"])
        prefix = read_commits(self.vault)
        with self.assertRaisesRegex(ValueError, "已撤销"):
            process_feedback(self.vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True}], session["session_id"])
        self.assertEqual(read_commits(self.vault), prefix)
        self.assertEqual(mastery_rows(self.vault)[0]["Attempts"], "0")

    def test_public_status_reads_one_snapshot_during_another_process_recalculation(self):
        self._seed_feedback()
        save_config(self.vault, {"tuning": {"kill_streak": 3}})
        before = repository.public_status(self.vault)
        with connect(self.vault) as db:
            db.execute("PRAGMA journal_mode=WAL")
        writer = self._start("B", "wait-save", 4)
        self._wait("B-ready")
        original_connect = repository.connect
        test = self
        class PausedConnection:
            def __init__(self, db):
                self.db = db
            def execute(self, sql, *arguments):
                cursor = self.db.execute(sql, *arguments)
                if sql == "SELECT * FROM active_config WHERE id=1":
                    row = cursor.fetchone()
                    (test.directory / "B-resume").write_text("1")
                    test._wait("B-done")
                    class OneRow:
                        def fetchone(self):
                            return row
                    return OneRow()
                return cursor
        @contextmanager
        def paused_connection(vault):
            with original_connect(vault) as db:
                yield PausedConnection(db)
        with patch.object(repository, "connect", side_effect=paused_connection):
            observed = repository.public_status(self.vault)
        self._result(writer, "B")
        self.assertEqual(observed, before)
        current = repository.public_status(self.vault)
        self.assertGreater(current["revision"], before["revision"])
        self.assertEqual(current["recalculation"]["revision"], current["revision"])
        self.assertEqual(current["policy_hash"], current["recalculation"]["policy_hash"])


if __name__ == "__main__":
    unittest.main()
