"""稳定身份、原子配置与 SQL 投影的行为回归。"""
import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from omrs.common import load_config, save_config, config_path, history_path, mastery_path, sessions_path, load_csv
from omrs.config_repository import initialize, ConfigMirrorConflict
from omrs.data_repository import resolve_question, mastery_rows, history_rows, IdentityConflict
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, read_commits, connect, verify_ledger
from omrs.projections import rebuild_projection, export_legacy_csv
from omrs.projection_runtime import invalidate
from omrs.sessions import create_session_from_selection, get_session, bind_session_entry


def question(qid="Q1", uid="U1"):
    return {"question_id": qid, "uid": uid, "file_path": f"错题/数学/代数/{uid}.md",
            "subject": "数学", "category": "代数", "difficulty": 5,
            "current_tag": "#状态/待攻克", "metadata": {"tags": ["状态/待攻克"]}, "labels": []}


class DataRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.addCleanup(invalidate, self.vault)
        append_commit(self.vault, "test", "question.create", "创建夹具", {"question": question()})
        rebuild_projection(self.vault)

    def feedback(self, **extra):
        return process_feedback(self.vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True, **extra}])[0]

    def test_ordinary_append_does_not_replay_or_delete_whole_tables(self):
        with patch("omrs.projection_runtime.full_project", side_effect=AssertionError("普通追加不得全量重放")):
            result = self.feedback()
        self.assertEqual(result["new_mastery"], float(mastery_rows(self.vault)[0]["Mastery"]))
        self.assertFalse(os.path.exists(history_path(self.vault)))
        export_legacy_csv(self.vault)
        self.assertEqual(len(load_csv(history_path(self.vault))), 1)
        self.assertEqual(len(load_csv(mastery_path(self.vault))), 1)

    def test_startup_scan_uses_sql_and_does_not_create_or_rotate_csv(self):
        from pathlib import Path
        from omrs.indexing import build_index
        vault = os.path.join(self.vault, "startup-vault")
        self.addCleanup(invalidate, vault)
        initialize(vault)
        path = Path(vault, "错题/数学/代数/代数1.md")
        path.parent.mkdir(parents=True)
        path.write_text("---\n_omrs_id: Q-startup\n科目: 数学\n分类: 代数\n难度: 5\n"
                        "tags:\n  - 状态/待攻克\n---\n\n# 题目\n启动扫描题\n", encoding="utf-8")
        rows, scan = build_index(vault, return_scan=True)
        self.assertEqual([row["question_id"] for row in rows], ["Q-startup"])
        self.assertEqual(scan["status"], "ok")
        paths = [Path(factory(vault)) for factory in (mastery_path, history_path, sessions_path)]
        self.assertTrue(all(not csv.exists() for csv in paths))
        from omrs.content_history import backfill_missing_content
        self.assertFalse(backfill_missing_content(vault)["conflicts"])
        import subprocess
        import sys
        environment = dict(os.environ)
        for name in ("OMRS_SYSTEMD_SERVICE", "OMRS_BOXDETECT_CONTROL"):
            environment.pop(name, None)
        exported = subprocess.run([sys.executable, "omrs_engine.py", "--vault", vault, "export-csv"],
                                  env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertIn("已导出", exported.stdout)
        before = [(csv.read_bytes(), csv.stat().st_mtime_ns) for csv in paths]
        path.write_text(path.read_text(encoding="utf-8").replace("难度: 5", "难度: 7"), encoding="utf-8")
        rows = build_index(vault)
        self.assertEqual(int(rows[0]["Difficulty"]), 7)
        self.assertEqual([(csv.read_bytes(), csv.stat().st_mtime_ns) for csv in paths], before)
        self.assertTrue(all(not Path(str(csv) + ".bak.1").exists() for csv in paths))

    def test_archive_and_uid_reuse_preserve_session_original_identity(self):
        session = create_session_from_selection(self.vault, [{"question_id": "Q1"}])
        append_commit(self.vault, "test", "question.archive", "归档", {"question_id": "Q1"})
        append_commit(self.vault, "test", "question.create", "复用显示名", {"question": question("Q2", "U1")})
        rebuild_projection(self.vault)
        current = get_session(self.vault, session["session_id"])
        self.assertEqual(current["entries"][0]["question_id"], "Q1")
        self.assertEqual(current["entries"][0]["availability"], "archived")
        result = process_feedback(self.vault, [{"uid": "U1", "sub_score": 9, "is_correct": True}], session["session_id"])
        self.assertEqual(result[0]["status"], "error")
        with connect(self.vault) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM question_projection").fetchone()[0], 2)
        self.assertEqual(mastery_rows(self.vault)[0]["Attempts"], "0")

    def test_move_old_uid_feedback_resolves_only_bound_session_entry(self):
        session = create_session_from_selection(self.vault, [{"question_id": "Q1"}])
        append_commit(self.vault, "test", "question.move", "移动", {"question_id": "Q1", "to_uid": "U2", "to_path": "错题/数学/几何/U2.md", "to_category": "几何"})
        append_commit(self.vault, "test", "question.create", "复用", {"question": question("Q2", "U1")})
        rebuild_projection(self.vault)
        result = process_feedback(self.vault, [{"uid": "U1", "sub_score": 9, "is_correct": True}], session["session_id"])
        self.assertEqual(result[0]["question_id"], "Q1")
        rows = {r["question_id"]: r for r in mastery_rows(self.vault)}
        self.assertEqual(rows["Q1"]["Attempts"], "1")
        self.assertEqual(rows["Q2"]["Attempts"], "0")
        with self.assertRaises(IdentityConflict):
            process_feedback(self.vault, [{"question_id": "Q1", "uid": "U1", "sub_score": 9, "is_correct": True}], session["session_id"])

    def test_unproven_bootstrap_entry_requires_immutable_manual_binding(self):
        append_commit(self.vault, "test", "legacy.bootstrap", "旧计划", {"session_rows": [{"Session_ID": "S0", "UIDs": '["U1"]', "Status": "active"}]})
        rebuild_projection(self.vault)
        entry = get_session(self.vault, "S0")["entries"][0]
        self.assertEqual(entry["availability"], "unresolved")
        original = read_commits(self.vault)[-1]
        bind_session_entry(self.vault, "S0", entry["entry_id"], "Q1")
        self.assertEqual(get_session(self.vault, "S0")["entries"][0]["question_id"], "Q1")
        self.assertEqual(read_commits(self.vault)[-2]["commit_hash"], original["commit_hash"])
        self.assertEqual(read_commits(self.vault)[-1]["commit_type"], "session.items_bind")

    def test_metadata_does_not_restore_stale_markdown_learning_tag(self):
        self.feedback(); self.feedback()
        after = {**question(), "labels": ["重点"]}
        append_commit(self.vault, "test", "question.metadata_update", "标记", {"question_id": "Q1", "before": question(), "after": after})
        rebuild_projection(self.vault)
        self.assertEqual(mastery_rows(self.vault)[0]["Current_Tag"], "#状态/已击杀")
        result = self.feedback(sub_score=2, is_correct=False)
        self.assertEqual(result["new_mastery"], 0.3)
        self.assertEqual(float(mastery_rows(self.vault)[0]["Mastery"]), result["new_mastery"])
        rebuild_projection(self.vault, force=True)
        self.assertEqual(float(mastery_rows(self.vault)[0]["Mastery"]), 0.3)

    def test_batch_response_matches_sequential_persisted_transition(self):
        result = process_feedback(self.vault, [
            {"question_id": "Q1", "sub_score": 9, "is_correct": True},
            {"question_id": "Q1", "sub_score": 9, "is_correct": True},
            {"question_id": "Q1", "sub_score": 2, "is_correct": False}])
        row = mastery_rows(self.vault)[0]
        self.assertEqual(result[-1]["new_mastery"], float(row["Mastery"]))
        self.assertEqual(result[-1]["new_interval"], int(row["Interval"]))
        self.assertEqual(row["Attempts"], "3")

    def test_timezone_business_date_and_recorded_timestamp_are_distinct(self):
        append_commit(self.vault, "test", "review.batch_submit", "午夜", {"feedbacks": [{"question_id": "Q1", "uid_at_that_time": "U1", "sub_score": 9, "is_correct": True,
            "recorded_at": "2026-10-01T16:15:00+00:00", "occurred_at": "2026-10-02", "review_date": "2026-10-02"}]})
        rebuild_projection(self.vault)
        row = history_rows(self.vault)[0]
        self.assertEqual(row["Date"], "2026-10-02 00:15")
        self.assertEqual(row["recorded_at"], "2026-10-01T16:15:00+00:00")
        self.assertEqual(mastery_rows(self.vault)[0]["Last_Review"], "2026-10-02")

    def test_missing_iana_database_supports_real_feedback_and_shanghai_midnight_history(self):
        from types import SimpleNamespace
        from zoneinfo import ZoneInfoNotFoundError
        from omrs.common import business_time, business_today
        stamp = datetime.datetime(2026, 10, 1, 16, 15, tzinfo=datetime.timezone.utc)
        class FeedbackClock:
            @classmethod
            def now(cls, zone=None):
                return stamp.astimezone(zone) if zone else stamp.replace(tzinfo=None)
        clock = SimpleNamespace(datetime=FeedbackClock, timezone=datetime.timezone)
        with patch("zoneinfo.ZoneInfo", side_effect=ZoneInfoNotFoundError("模拟无 IANA 数据")), patch("omrs.feedback.datetime", clock):
            self.assertEqual(business_today(stamp).isoformat(), "2026-10-02")
            self.assertEqual(business_time(stamp).utcoffset(), datetime.timedelta(hours=8))
            result = self.feedback()
            self.assertEqual(result["status"], "ok")
            row = history_rows(self.vault)[0]
            self.assertEqual(row["Date"], "2026-10-02 00:15")
            self.assertEqual(row["recorded_at"], "2026-10-01T16:15:00+00:00")
            self.assertEqual(mastery_rows(self.vault)[0]["Last_Review"], "2026-10-02")
            rebuild_projection(self.vault, force=True)
            self.assertEqual(history_rows(self.vault)[0], row)

    def test_missing_iana_database_does_not_invent_old_dst_or_other_timezone(self):
        from zoneinfo import ZoneInfoNotFoundError
        from omrs.common import business_time
        old = datetime.datetime(1991, 7, 1, 16, 15, tzinfo=datetime.timezone.utc)
        with patch("zoneinfo.ZoneInfo", side_effect=ZoneInfoNotFoundError("模拟无 IANA 数据")):
            with self.assertRaises(ZoneInfoNotFoundError):
                business_time(old)
            with self.assertRaises(ZoneInfoNotFoundError):
                business_time(old.replace(year=2026), "America/New_York")
            for recorded, zone in ((old.isoformat(), "Asia/Shanghai"), ("2026-10-01T16:15:00+00:00", "America/New_York")):
                append_commit(self.vault, "test", "review.batch_submit", "缺库历史", {"feedbacks": [{
                    "question_id": "Q1", "uid_at_that_time": "U1", "sub_score": 9, "is_correct": True,
                    "recorded_at": recorded, "review_timezone": zone,
                    "review_date": (datetime.date.fromisoformat(recorded[:10]) + datetime.timedelta(days=1)).isoformat()}]})
                rebuild_projection(self.vault)
                latest = history_rows(self.vault)[-1]
                self.assertEqual(latest["recorded_at"], recorded)
                self.assertEqual(latest["Date"], recorded[:10] + " 16:15")
                self.assertNotEqual(latest["review_date"], latest["Date"][:10])

    def test_tuning_recalculates_immediately_and_restore_uses_current_policy(self):
        initialize(self.vault)
        self.feedback(); self.feedback()
        target = read_commits(self.vault)[-1]["seq"]
        hashes = [c["commit_hash"] for c in read_commits(self.vault)]
        result = save_config(self.vault, {"tuning": {"kill_streak": 3}, "ai_api_key": "private"})
        self.assertEqual((result["revision"], result["mirror_pending"]), (2, False))
        self.assertEqual(result["tuning_effective"]["kill_streak"], 3)
        self.assertEqual({k: result["recalculation"][k] for k in ("status", "revision", "questions", "feedbacks")},
                         {"status": "complete", "revision": 2, "questions": 1, "feedbacks": 2})
        self.assertGreaterEqual(result["recalculation"]["seconds"], 0)
        self.assertEqual(result["recalculation"]["policy_hash"], result["policy_hash"])
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(mastery_rows(self.vault)[0]["Current_Tag"], "#状态/待攻克")
        append_commit(self.vault, "test", "state.restore", "还原", {"target_seq": target})
        rebuild_projection(self.vault)
        self.assertEqual(mastery_rows(self.vault)[0]["Current_Tag"], "#状态/待攻克")
        self.assertEqual([c["commit_hash"] for c in read_commits(self.vault)][:len(hashes)], hashes)
        self.assertTrue(verify_ledger(self.vault)["valid"])
        audit = next(c for c in read_commits(self.vault) if c["commit_type"] == "config.tuning_update")
        self.assertNotIn("private", json.dumps(audit["payload"]))

    def test_projection_failure_rolls_back_config_and_learning_state(self):
        initialize(self.vault)
        self.feedback()
        previous = load_config(self.vault)
        row = mastery_rows(self.vault)[0]
        with patch("omrs.projection_runtime.full_project", side_effect=RuntimeError("故障注入")):
            with self.assertRaises(RuntimeError):
                save_config(self.vault, {"tuning": {"kill_streak": 3}})
        self.assertEqual(load_config(self.vault), previous)
        self.assertEqual(mastery_rows(self.vault)[0], row)

    def test_mirror_failure_remains_live_and_restart_conflict_preserves_both(self):
        initialize(self.vault)
        with patch("omrs.config_repository._write_mirror", side_effect=OSError("故障注入")):
            result = save_config(self.vault, {"ai_model": "新模型"})
        self.assertTrue(result["mirror_pending"])
        self.assertEqual(load_config(self.vault)["ai_model"], "新模型")
        with open(config_path(self.vault), "w", encoding="utf-8") as file:
            json.dump({"ai_model": "手改冲突"}, file)
        with self.assertRaises(ConfigMirrorConflict):
            initialize(self.vault)
        self.assertEqual(load_config(self.vault)["ai_model"], "新模型")
        with open(config_path(self.vault), encoding="utf-8") as file:
            self.assertEqual(json.load(file)["ai_model"], "手改冲突")

    def test_missing_mirror_recovers_active_config_instead_of_resetting(self):
        initialize(self.vault)
        save_config(self.vault, {"ai_model": "保留模型"})
        os.unlink(config_path(self.vault))
        initialize(self.vault)
        self.assertEqual(load_config(self.vault)["ai_model"], "保留模型")
        with open(config_path(self.vault), encoding="utf-8") as file:
            self.assertEqual(json.load(file)["ai_model"], "保留模型")

    def test_non_tuning_config_update_audits_keys_without_full_replay(self):
        initialize(self.vault)
        rebuild_projection(self.vault)
        with patch("omrs.projection_runtime.full_project", side_effect=AssertionError("普通配置不得全量重放")):
            save_config(self.vault, {"ai_api_key": "secret"})
            rebuild_projection(self.vault)
        audit = read_commits(self.vault)[-1]
        self.assertEqual(audit["commit_type"], "config.update")
        self.assertEqual(audit["payload"]["changed_keys"], ["ai_api_key"])
        self.assertNotIn("secret", json.dumps(audit["payload"]))

    def test_snapshot_policy_and_head_validation_and_cache_reuse(self):
        self.feedback()
        rebuild_projection(self.vault, force=True)
        invalidate(self.vault)
        with patch("omrs.projection_runtime.full_project", side_effect=AssertionError("有效快照应可重用")):
            rebuild_projection(self.vault)
        with connect(self.vault) as db:
            raw = db.execute("SELECT seq,snapshot_json FROM snapshots ORDER BY seq DESC LIMIT 1").fetchone()
            saved = json.loads(raw["snapshot_json"])
            saved["policy_hash"] = "错误策略"
            db.execute("UPDATE snapshots SET snapshot_json=? WHERE seq=?", (json.dumps(saved), raw["seq"]))
        invalidate(self.vault)
        with patch("omrs.projection_runtime.full_project", wraps=__import__("omrs.projection_runtime", fromlist=["full_project"]).full_project) as full:
            rebuild_projection(self.vault)
            self.assertEqual(full.call_count, 1)
        self.assertEqual(len(history_rows(self.vault)), 1)

    def test_legacy_projection_rewrite_invalidates_checkpoint_without_new_commit(self):
        self.feedback(); self.feedback()
        rebuild_projection(self.vault, force=True)
        hashes = [c["commit_hash"] for c in read_commits(self.vault)]
        with connect(self.vault) as db:
            # 模拟旧投影器的 DELETE + INSERT，链头没有变化，但 SQL 已不再
            # 匹配新投影语义；不能只凭快照头哈希接受这批派生缓存。
            original = dict(db.execute("SELECT * FROM question_projection WHERE question_id='Q1'").fetchone())
            db.execute("DELETE FROM question_projection")
            original["current_tag"] = "#状态/待攻克"
            columns = ",".join(original)
            values = ",".join("?" for _ in original)
            db.execute(f"INSERT INTO question_projection({columns}) VALUES({values})", tuple(original.values()))
            self.assertIsNone(db.execute("SELECT * FROM projection_meta").fetchone())
        invalidate(self.vault)
        state = rebuild_projection(self.vault)
        self.assertEqual(state["questions"]["Q1"]["current_tag"], "#状态/已击杀")
        self.assertEqual(mastery_rows(self.vault)[0]["Current_Tag"], "#状态/已击杀")
        self.assertEqual([c["commit_hash"] for c in read_commits(self.vault)], hashes)

    def test_incremental_and_full_agree_on_deterministic_event_sequence(self):
        import random
        generator = random.Random(20261002)
        for index in range(60):
            if index % 9 == 0:
                append_commit(self.vault, "test", "question.metadata_update", "标记变化", {
                    "question_id": "Q1", "after": {**question(), "labels": [f"标记{index}"]}, "changed_fields": ["labels"]})
                rebuild_projection(self.vault)
            else:
                self.feedback(sub_score=generator.randrange(11), is_correct=generator.choice([True, False]))
            incremental = mastery_rows(self.vault)
            records = history_rows(self.vault)
            rebuild_projection(self.vault, force=True)
            self.assertEqual(mastery_rows(self.vault), incremental)
            self.assertEqual(history_rows(self.vault), records)

    def test_scanner_stop_restart_and_old_generation_cannot_write(self):
        import threading
        import time
        from omrs import workspace_sync
        from omrs.vault_lifecycle import advance_generation, exclusive
        first, second = threading.Event(), threading.Event()
        calls = []
        def scan(vault):
            from omrs.vault_lifecycle import lease
            with lease(vault):
                calls.append(threading.current_thread())
                (first if len(calls) == 1 else second).set()
        self.addCleanup(workspace_sync.stop_workspace_scanner)
        with patch.object(workspace_sync, "scan_workspace", side_effect=scan):
            workspace_sync.start_workspace_scanner(self.vault, 0.02)
            self.assertTrue(first.wait(1))
            old = workspace_sync.start_workspace_scanner._thread
            with exclusive(self.vault):
                workspace_sync.stop_workspace_scanner()
                advance_generation(self.vault)
                workspace_sync.start_workspace_scanner(self.vault, 0.02)
            self.assertTrue(second.wait(1))
            old.join(1)
            self.assertFalse(old.is_alive())
            self.assertIsNot(workspace_sync.start_workspace_scanner._thread, old)

    def test_long_correct_streak_preserves_replay_and_representable_due_date(self):
        results = process_feedback(self.vault, [{"question_id": "Q1", "is_correct": True, "sub_score": 9} for _ in range(100)])
        row = mastery_rows(self.vault)[0]
        self.assertEqual(row["Attempts"], "100")
        self.assertEqual(row["Due_Date"], "9999-12-31")
        self.assertEqual(results[-1]["new_due_date"], row["Due_Date"])
        from omrs.stats import get_stats
        self.assertEqual(get_stats(self.vault)["items"][0]["next_revive_date"], "9999-12-31")
        rebuild_projection(self.vault, force=True)
        self.assertEqual(mastery_rows(self.vault)[0], row)

    def test_tuning_published_snapshot_prevents_replay_on_next_feedback(self):
        initialize(self.vault)
        save_config(self.vault, {"tuning": {"kill_streak": 3}})
        with patch("omrs.projection_runtime.full_project", side_effect=AssertionError("已发布调参不得在普通反馈再次全量重放")):
            self.feedback()

    def test_backfill_more_than_one_batch_uses_same_connection_without_reader_deadlock(self):
        from pathlib import Path
        from omrs.content_history import backfill_missing_content
        from omrs.ledger import append_commit_in_db, blob_hash
        with connect(self.vault) as db:
            db.execute("BEGIN IMMEDIATE")
            for index in range(201):
                qid, uid = f"B{index}", f"回填{index}"
                content = f"---\n_omrs_id: {qid}\n---\n# 题目\n回填夹具\n"
                q = question(qid, uid)
                q["content_hash"] = blob_hash(content)
                path = Path(self.vault) / q["file_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                append_commit_in_db(db, "test", "question.create", "缺失blob合法夹具", {"question": q})
        rebuild_projection(self.vault)
        result = backfill_missing_content(self.vault)
        self.assertEqual(result["count"], 201)
        self.assertEqual(backfill_missing_content(self.vault)["count"], 0)
        with connect(self.vault) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM blobs").fetchone()[0], 201)


if __name__ == "__main__":
    unittest.main()
