from omrs.common import business_today
import datetime
import tempfile
import unittest

from omrs import exporting
from omrs.common import load_csv, mastery_path, MASTERY_HEADERS, save_csv
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.ledger import connect
from omrs.feedback import process_feedback
from omrs.projections import rebuild_projection
from omrs.scheduling import (
    generate_recommendations,
    is_revive_eligible,
    revive_dormant_days,
)


def _rows(vault):
    return mastery_rows(vault)


def _set_last_review(vault, uid, days_ago):
    """把某题的 Last_Review / Due_Date 改到 N 天前，模拟时间流逝。

    复燃判定完全基于 Last_Review 与衰减式，不依赖 Ledger 重放，因此这样改
    等价于「那次击杀发生在 N 天前」。Due_Date 一并回拨，否则击杀时的
    SM-2 间隔会把它留在未来，题会落进熟练度列表而不是到期列表。
    """
    target = (business_today() - datetime.timedelta(days=days_ago)).isoformat()
    with connect(vault) as db:
        db.execute("UPDATE mastery_projection SET last_review_at=?,due_date=? WHERE question_id=(SELECT question_id FROM question_projection WHERE uid=? AND archived=0)", (target, target, uid))


def _kill(vault, uid):
    """连续两次高分答对，把题打到「已击杀」。"""
    for _ in range(2):
        process_feedback(vault, [{"uid": uid, "sub_score": 9, "is_correct": True}])


def _row(vault, uid):
    return next(row for row in _rows(vault) if row["UID"] == uid)


def _recommended(vault, uid):
    rec = generate_recommendations(vault, due_count=50, prof_count=50)
    for bucket, source in (("due", "due"), ("proficiency", "proficiency")):
        for item in rec[bucket]:
            if item["uid"] == uid:
                return source, item
    return None, None


class ReviveDormantDaysTests(unittest.TestCase):
    def test_dormancy_is_tiered_by_kill_count(self):
        days = [revive_dormant_days(n, 1.0) for n in (1, 2, 3, 4)]
        # 越熟练（击杀次数越多）休眠越久，且第一档就是「较长周期」
        self.assertEqual(days, sorted(days))
        self.assertEqual(len(set(days)), 4)
        self.assertGreaterEqual(days[0], 45)
        self.assertGreater(days[1], days[0] * 1.5)

    def test_low_mastery_dormancy_is_shorter(self):
        self.assertLess(revive_dormant_days(1, 0.6), revive_dormant_days(1, 1.0))

    def test_unknown_last_review_never_triggers_revive(self):
        # 日期缺失时不应因为「算不出天数」就当作已经休眠够久
        self.assertFalse(is_revive_eligible(1.0, "#状态/已击杀", "", 1))
        self.assertFalse(is_revive_eligible(1.0, "#状态/已击杀", "不是日期", 1))

    def test_non_killed_question_is_never_revived(self):
        self.assertFalse(is_revive_eligible(0.4, "#状态/待攻克", "2000-01-01", 0))


class ReviveCycleTests(unittest.TestCase):
    def test_killed_question_returns_after_dormancy(self):
        with tempfile.TemporaryDirectory() as vault:
            uid = create_question(vault, "数学", "代数", 5)["uid"]
            _kill(vault, uid)
            self.assertEqual(_row(vault, uid)["Current_Tag"], "#状态/已击杀")

            self.assertIsNone(_recommended(vault, uid)[0])

            dormant = revive_dormant_days(1, 1.0)
            _set_last_review(vault, uid, dormant - 1)
            self.assertIsNone(_recommended(vault, uid)[0])

            _set_last_review(vault, uid, dormant)
            source, item = _recommended(vault, uid)
            self.assertEqual(source, "due")
            self.assertTrue(item["is_revived"])
            self.assertEqual(item["kill_count"], 1)
            self.assertEqual(item["dormant_days"], dormant)
            self.assertTrue(item["next_revive_date"])

    def test_second_kill_waits_longer_than_the_first(self):
        with tempfile.TemporaryDirectory() as vault:
            uid = create_question(vault, "数学", "代数", 5)["uid"]
            _kill(vault, uid)
            first_dormant = revive_dormant_days(1, 1.0)
            second_dormant = revive_dormant_days(2, 1.0)

            # 复燃 → 答错降级 → 再次击杀，kill_count 变成 2
            _set_last_review(vault, uid, first_dormant)
            process_feedback(vault, [{"uid": uid, "sub_score": 2, "is_correct": False}])
            _kill(vault, uid)
            row = _row(vault, uid)
            self.assertEqual(row["Current_Tag"], "#状态/已击杀")
            self.assertEqual(int(row["Kill_Count"]), 2)

            # 第一次的周期已过、第二次的还没到 → 仍不出现在推荐里
            _set_last_review(vault, uid, first_dormant + 14)
            self.assertIsNone(_recommended(vault, uid)[0])

            _set_last_review(vault, uid, second_dormant)
            self.assertEqual(_recommended(vault, uid)[0], "due")

    def test_wrong_answer_after_revive_demotes_back_to_attack(self):
        with tempfile.TemporaryDirectory() as vault:
            uid = create_question(vault, "数学", "代数", 5)["uid"]
            _kill(vault, uid)
            _set_last_review(vault, uid, revive_dormant_days(1, 1.0))

            process_feedback(vault, [{"uid": uid, "sub_score": 2, "is_correct": False}])

            row = _row(vault, uid)
            self.assertEqual(row["Current_Tag"], "#状态/待攻克")
            # 降级系数作用于复燃前的熟练度（1.0 → 0.3），不与状态机自身的
            # 低分惩罚连乘
            self.assertAlmostEqual(float(row["Mastery"]), 0.3, places=3)
            self.assertEqual(int(row["Repetition"]), 0)
            self.assertEqual(int(row["Interval"]), 1)
            # 击杀次数不重置，下次复燃周期只会更长
            self.assertEqual(int(row["Kill_Count"]), 1)
            # 已降级 → 立刻回到推荐，且不再是复燃状态
            source, item = _recommended(vault, uid)
            self.assertIsNotNone(source)
            self.assertFalse(item["is_revived"])
            self.assertEqual(item["kill_count"], 1)

    def test_missing_kill_count_column_replays_as_first_kill(self):
        with tempfile.TemporaryDirectory() as vault:
            uid = create_question(vault, "数学", "代数", 5)["uid"]
            _kill(vault, uid)

            rows = _rows(vault)
            for row in rows:
                row.pop("Kill_Count", None)
            save_csv(mastery_path(vault), MASTERY_HEADERS, [{key: row.get(key, "") for key in MASTERY_HEADERS} for row in rows])

            state = rebuild_projection(vault)
            # 老 vault 无该字段：重放不报错，并按第 1 次击杀处理
            self.assertIsInstance(state["mastery"], dict)
            items = generate_recommendations(vault, due_count=50, prof_count=50)
            self.assertIsInstance(items, dict)
            self.assertEqual(
                _recommended(vault, uid)[1]["kill_count"]
                if _recommended(vault, uid)[1] else 0,
                0,
            )


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
