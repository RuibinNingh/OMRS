"""一次击杀、独立复核周期、历史重放与旧快照迁移。"""
import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from omrs import exporting
from omrs.common import DEFAULT_TUNING, business_today, config_path, load_config, save_config
from omrs.config_repository import initialize, normalized_tuning
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.feedback import process_feedback
from omrs.ledger import append_commit, connect, read_commits, verify_ledger
from omrs.projection_runtime import invalidate
from omrs.projections import rebuild_projection, DEFAULT_MASTERY
from omrs.scheduling import generate_recommendations, is_revive_eligible, revive_dormant_days, transition_review
from omrs.stats import get_stats
from omrs.analytics import get_analytics


class ReviewPolicyTests(unittest.TestCase):
    def setUp(self):
        self.q = {"current_tag": "#状态/待攻克"}
        self.m = dict(DEFAULT_MASTERY)
        self.tuning = normalized_tuning({})

    def review(self, day="2026-11-02", score=9, correct=True):
        self.m, self.q["current_tag"], display = transition_review(self.q, self.m,
            {"review_date": day, "sub_score": score, "is_correct": correct}, self.tuning)
        return display

    def test_one_high_correct_kills_but_threshold_and_correctness_are_both_required(self):
        self.review(score=6)
        self.assertEqual(self.m["revive_stage"], 0)
        self.assertLess(self.m["mastery"], 1)
        self.review(score=7, correct=False)
        self.assertEqual(self.m["revive_stage"], 0)
        display = self.review(score=7)
        self.assertEqual((display["label"], display["new_due_date"]), ("已击杀", "2026-11-09"))
        self.assertEqual((self.m["revive_stage"], self.m["kill_count"]), (1, 1))

    def test_ordinary_low_scores_cannot_bypass_kill(self):
        for _ in range(30):
            self.review(score=6)
        self.assertEqual(self.m["mastery"], .95)
        self.assertEqual(self.m["kill_count"], 0)

    def test_due_successes_advance_one_stage_and_repeat_the_maximum(self):
        day = "2026-11-02"
        for count, (stage, interval) in enumerate(zip([1, 2, 3, 4, 5, 5], [7, 21, 60, 120, 180, 180]), 1):
            self.review(day)
            expected = (datetime.date.fromisoformat(day) + datetime.timedelta(days=interval)).isoformat()
            self.assertEqual((self.m["revive_stage"], self.m["interval_days"], self.m["due_date"], self.m["kill_count"]),
                             (stage, interval, expected, count))
            self.assertEqual(self.m["revive_anchor_at"], day)
            day = expected

    def test_same_day_and_early_high_scores_preserve_anchor_due_stage_and_count(self):
        self.review()
        expected = {key: self.m[key] for key in ("revive_stage", "revive_anchor_at", "due_date", "interval_days", "kill_count")}
        for day in ["2026-11-02", "2026-11-02", "2026-11-08"]:
            self.review(day)
            self.assertEqual({key: self.m[key] for key in expected}, expected)
            self.assertEqual(self.m["last_review_at"], day)
        self.review("2026-11-09")
        self.assertEqual(self.m["revive_stage"], 2)

    def test_long_overdue_success_advances_only_one_stage_from_actual_review_day(self):
        self.review()
        self.review("2030-01-01")
        self.assertEqual((self.m["revive_stage"], self.m["due_date"]), (2, "2030-01-22"))

    def test_uncertain_correct_demotes_and_new_kill_restarts_first_stage(self):
        self.review(); self.review("2026-11-09")
        display = self.review("2026-11-10", score=6)
        self.assertEqual((display["label"], self.m["revive_stage"], self.m["due_date"], self.m["repetition"]),
                         ("磨合中", 0, "2026-11-13", 0))
        self.assertEqual(self.q["current_tag"], "#状态/待攻克")
        self.assertEqual(self.m["revive_anchor_at"], "")
        self.assertLess(self.m["mastery"], 1)
        self.review("2026-11-11")
        self.assertEqual((self.m["revive_stage"], self.m["due_date"], self.m["kill_count"]), (1, "2026-11-18", 3))

    def test_wrong_answers_demote_once_and_preserve_cumulative_count(self):
        for score in (2, 9):
            with self.subTest(score=score):
                self.setUp(); self.review()
                self.review("2026-11-03", score=score, correct=False)
                self.assertEqual((self.m["mastery"], self.m["due_date"], self.m["revive_stage"], self.m["kill_count"]),
                                 (.3, "2026-11-04", 0, 1))
                self.review("2026-11-04")
                self.assertEqual((self.m["revive_stage"], self.m["interval_days"]), (1, 7))

    def test_date_limit_does_not_overflow_or_count_same_day_as_new_confirmation(self):
        self.review("9999-12-30")
        self.assertEqual(self.m["due_date"], "9999-12-31")
        self.review("9999-12-31")
        expected = dict(self.m)
        self.review("9999-12-31")
        self.assertEqual((self.m["revive_stage"], self.m["kill_count"]), (expected["revive_stage"], expected["kill_count"]))
        self.assertEqual(self.m["due_date"], "9999-12-31")
        self.review("9999-12-31", score=2, correct=False)
        self.assertEqual(self.m["due_date"], "9999-12-31")

    def test_custom_intervals_and_unknown_legacy_dates(self):
        self.tuning["revive_intervals_days"] = [3, 10, 30, 60, 120]
        self.review()
        self.assertEqual(self.m["due_date"], "2026-11-05")
        self.assertEqual([revive_dormant_days(n) for n in range(1, 6)], [7, 21, 60, 120, 180])
        self.assertTrue(is_revive_eligible(1, "#状态/已击杀", ""))
        self.assertTrue(is_revive_eligible(1, "#状态/已击杀", "无日期"))
        self.assertFalse(is_revive_eligible(.4, "#状态/待攻克", "2000-01-01"))


class ReviveCycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.vault = temporary.name
        self.q = create_question(self.vault, "数学", "代数", 5)
        self.uid = self.q["uid"]
        self.addCleanup(invalidate, self.vault)

    def feed(self, day, score=9, correct=True):
        with patch("omrs.feedback.business_today", return_value=datetime.date.fromisoformat(day)):
            return process_feedback(self.vault, [{"uid": self.uid, "sub_score": score, "is_correct": correct}])[0]

    def row(self):
        return mastery_rows(self.vault)[0]

    def test_actual_due_date_controls_recommendations_despite_later_early_practice(self):
        self.feed("2026-11-02"); self.feed("2026-11-08")
        for day, count in [("2026-11-08", 0), ("2026-11-09", 1)]:
            with patch("omrs.scheduling.business_today", return_value=datetime.date.fromisoformat(day)):
                rec = generate_recommendations(self.vault, 50, 50)
            self.assertEqual(len(rec["due"]), count)
            self.assertEqual(rec["proficiency"], [])
            if count:
                self.assertEqual((rec["due"][0]["revive_stage"], rec["due"][0]["next_revive_date"]), (1, "2026-11-09"))

    def test_feedback_response_incremental_restart_and_full_replay_agree(self):
        self.feed("2026-11-02"); self.feed("2026-11-08")
        result = self.feed("2026-11-09")
        expected = self.row()
        prefix = read_commits(self.vault)
        self.assertEqual((result["revive_stage"], result["new_due_date"]), (2, "2026-11-30"))
        invalidate(self.vault)
        rebuild_projection(self.vault)
        self.assertEqual(self.row(), expected)
        rebuild_projection(self.vault, force=True)
        self.assertEqual(self.row(), expected)
        self.assertEqual(read_commits(self.vault), prefix)
        self.assertTrue(verify_ledger(self.vault)["valid"])

    def test_retract_restore_and_replace_recompute_cycle_without_touching_original_events(self):
        self.feed("2026-11-02")
        self.feed("2026-11-09")
        target = read_commits(self.vault)[-1]["commit_id"]
        self.feed("2026-11-30")
        prefix = read_commits(self.vault)
        payload = {"target_commit_id": target, "target_review_index": 0}
        for kind, stage in [("review.retract", 2), ("review.restore", 3), ("review.replace", 1)]:
            data = {**payload, **({"replacement": {"sub_score": 6}} if kind == "review.replace" else {})}
            append_commit(self.vault, "test", kind, "复核历史修正", data)
            rebuild_projection(self.vault)
            self.assertEqual(int(self.row()["Revive_Stage"]), stage)
            rebuilt = self.row()
            rebuild_projection(self.vault, force=True)
            self.assertEqual(self.row(), rebuilt)
        self.assertEqual(read_commits(self.vault)[:len(prefix)], prefix)

    def test_forecasts_include_sleeping_cycles_and_due_alerts_include_revived_cycles(self):
        self.feed("2026-11-02")
        for day, expected in [("2026-11-02", (0, 0, 1)), ("2026-11-09", (0, 1, 0)), ("2026-11-10", (1, 0, 0))]:
            date = datetime.date.fromisoformat(day)
            with patch("omrs.stats.business_today", return_value=date), patch("omrs.analytics.business_today", return_value=date):
                stats, analytics = get_stats(self.vault), get_analytics(self.vault)
            self.assertEqual((stats["killed"], stats["attacking"]), (1, 0))
            for alerts in [stats["review_alert"], analytics["review_alert"]]:
                self.assertEqual((alerts["overdue"], alerts["due_today"], alerts["due_next_7_days"]), expected)

    def test_tuning_replay_moves_anchor_based_due_without_postponing_to_early_practice(self):
        initialize(self.vault)
        self.feed("2026-11-02"); self.feed("2026-11-05")
        prefix = read_commits(self.vault)
        save_config(self.vault, {"tuning": {"revive_intervals_days": [10, 30, 60, 120, 180]}})
        self.assertEqual((self.row()["Revive_Anchor"], self.row()["Due_Date"]), ("2026-11-02", "2026-11-12"))
        self.assertEqual(read_commits(self.vault)[:len(prefix)], prefix)

    def test_old_projection_columns_are_added_and_old_checkpoints_rebuilt(self):
        self.feed("2026-11-02")
        prefix = read_commits(self.vault)
        with connect(self.vault) as db:
            db.execute("ALTER TABLE mastery_projection DROP COLUMN revive_stage")
            db.execute("ALTER TABLE mastery_projection DROP COLUMN revive_anchor_at")
            db.execute("UPDATE projection_meta SET projector_version='ledger-v3'")
        invalidate(self.vault)
        # 模拟新进程首次打开旧结构。
        with patch("omrs.ledger._INITIALIZED", set()):
            initialize(self.vault)
        self.assertEqual((self.row()["Revive_Stage"], self.row()["Due_Date"]), ("1", "2026-11-09"))
        self.assertEqual(read_commits(self.vault)[:len(prefix)], prefix)

    def test_failed_policy_upgrade_keeps_previous_config_and_projection(self):
        initialize(self.vault)
        self.feed("2026-11-02")
        before, config, commits = self.row(), load_config(self.vault), read_commits(self.vault)
        with connect(self.vault) as db:
            db.execute("UPDATE projection_meta SET projector_version='ledger-v3'")
            db.execute("UPDATE mastery_projection SET mastery=.4,revive_stage=0,revive_anchor_at='',interval_days=6,due_date='2026-11-08'")
        invalidate(self.vault)
        from omrs.projection_runtime import full_project
        def fail_after_replay(*args):
            full_project(*args)
            raise OSError("合成升级重放失败")
        with patch("omrs.projection_runtime.full_project", side_effect=fail_after_replay):
            with self.assertRaisesRegex(OSError, "升级重放失败"):
                initialize(self.vault)
        with connect(self.vault) as db:
            row = db.execute("SELECT mastery,revive_stage,due_date FROM mastery_projection").fetchone()
            self.assertEqual(tuple(row), (.4, 0, "2026-11-08"))
            self.assertEqual(db.execute("SELECT projector_version FROM projection_meta").fetchone()[0], "ledger-v3")
        self.assertEqual(load_config(self.vault), config)
        self.assertEqual(read_commits(self.vault), commits)
        initialize(self.vault)
        self.assertEqual(self.row(), before)


class ReviewCompatibilityTests(unittest.TestCase):
    def test_legacy_killed_question_without_mastery_row_is_pending_confirmation(self):
        with tempfile.TemporaryDirectory() as vault:
            append_commit(vault, "test", "legacy.bootstrap", "无学习快照的旧题", {
                "questions": [{"question_id": "Q1", "uid": "旧题1", "current_tag": "#状态/已击杀"}]})
            rebuild_projection(vault)
            row = mastery_rows(vault)[0]
            self.assertEqual((row["Revive_Stage"], row["Revive_Anchor"], row["Due_Date"]), ("1", "", ""))
            self.assertEqual(len(generate_recommendations(vault)["due"]), 1)

    def test_legacy_snapshot_starts_first_stage_regardless_of_cumulative_kills(self):
        for last in ("2026-10-01", "", "无日期"):
            with self.subTest(last=last), tempfile.TemporaryDirectory() as vault:
                append_commit(vault, "test", "legacy.bootstrap", "旧快照", {
                    "questions": [{"question_id": "Q1", "uid": "旧题1", "current_tag": "#状态/已击杀"}],
                    "mastery_rows": [{"question_id": "Q1", "Mastery": "1", "Kill_Count": "99", "Last_Review": last,
                                      "Due_Date": "2099-01-01"}]})
                prefix = read_commits(vault)
                rebuild_projection(vault)
                row = mastery_rows(vault)[0]
                self.assertEqual((row["Revive_Stage"], row["Kill_Count"]), ("1", "99"))
                self.assertEqual(row["Due_Date"], "2026-10-08" if last == "2026-10-01" else "")
                rec = generate_recommendations(vault, 50, 50)
                self.assertEqual(len(rec["due"]), 1)
                if not row["Due_Date"]:
                    with patch("omrs.feedback.business_today", return_value=datetime.date(2026, 11, 2)):
                        result = process_feedback(vault, [{"question_id": "Q1", "sub_score": 9, "is_correct": True}])[0]
                    self.assertEqual((result["revive_stage"], result["new_due_date"]), (1, "2026-11-09"))
                self.assertEqual(read_commits(vault)[:len(prefix)], prefix)

    def test_legacy_parameters_are_ignored_and_removed_on_save(self):
        with tempfile.TemporaryDirectory() as vault:
            path = Path(config_path(vault))
            path.write_text(json.dumps({"tuning": {"kill_streak": 99, "revive_decay_threshold": .01, "revive_tier_multiplier": 100}}))
            initialize(vault)
            self.assertEqual(normalized_tuning(load_config(vault))["revive_intervals_days"], [7, 21, 60, 120, 180])
            self.assertEqual(load_config(vault)["tuning"], {})
            result = save_config(vault, {"tuning": {"kill_streak": 3, "revive_intervals_days": [3, 10, 30, 60, 120]}})
            self.assertNotIn("kill_streak", result["tuning_effective"])
            self.assertNotIn("kill_streak", json.loads(path.read_text())["tuning"])

    def test_intervals_reject_invalid_shapes_types_and_order_without_changing_active_state(self):
        with tempfile.TemporaryDirectory() as vault:
            initialize(vault)
            before = load_config(vault)
            for value in [[], [1, 2, 3, 4], [1, 2, 3, 4, 4], [0, 2, 3, 4, 5], [True, 2, 3, 4, 5], [1.0, 2, 3, 4, 5], "7,21,60,120,180"]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    save_config(vault, {"tuning": {"revive_intervals_days": value}})
                self.assertEqual(load_config(vault), before)


class ReviveExportTests(unittest.TestCase):
    def _vault_with_notes(self):
        vault = tempfile.TemporaryDirectory()
        uid = create_question(
            vault.name, "数学", "代数", 5,
            question_text="求 $x^2-1=0$ 的解。",
            answer_text="$x=\\pm 1$",
            cause="漏了负根，符号没考虑。",
        )["uid"]
        return vault, uid

    def test_error_reason_leaves_the_question_area(self):
        vault, uid = self._vault_with_notes()
        with vault:
            _, questions = exporting._load_export_questions(vault.name, [uid])
            for include in (False, True):
                data = exporting._build_export_data(vault.name, "TMP-1", questions, include)
                question = data["questions"][0]
                self.assertNotIn("错因", question["notes"])
                self.assertNotIn("feedback", data)
                self.assertEqual(len(data["answers"]), 1)
                self.assertIn("错因", data["answers"][0]["notes"])
                self.assertEqual(
                    bool(data["answers"][0]["blocks"]), include,
                    "错因跟随答案段；不勾选答案时不应输出答案正文",
                )

    def test_error_reason_survives_in_answer_notes(self):
        vault, uid = self._vault_with_notes()
        with vault:
            _, questions = exporting._load_export_questions(vault.name, [uid])
            data = exporting._build_export_data(vault.name, "TMP-1", questions, True)
            self.assertIn("负根", data["answers"][0]["notes"]["错因"])
            self.assertEqual(data["answers"][0]["idx"], 1)

    def test_a4_template_drops_the_checkbox_sheet(self):
        with open("omrs/export_templates/a4.js", "r", encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("反馈勾选表", source)
        self.assertNotIn("fb-row", source)
        # 错因只在反馈区输出
        self.assertEqual(source.count('noteBlock("错因"'), 1)

    def test_board_export_carries_notes_to_the_answer_page(self):
        vault, uid = self._vault_with_notes()
        with vault:
            from omrs import boards
            board = boards.create_board(vault.name, "测试板", [uid])
            board_id = board["id"] if isinstance(board, dict) else board
            data = exporting.build_board_export_data(
                vault.name, board_id, include_answers=True,
            )
            self.assertNotIn("错因", data["questions"][0]["notes"])
            self.assertIn("错因", data["answers"][0]["notes"])


if __name__ == "__main__":
    unittest.main()
