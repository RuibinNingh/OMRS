import csv
import os
import tempfile
import unittest

from omrs.analytics import get_analytics
from omrs.common import HISTORY_HEADERS, MASTERY_HEADERS, history_path, load_csv, mastery_path
from omrs.creation import create_question
from omrs.feedback import process_feedback
from omrs.exporting import export_schedule_artifact
from omrs.ledger import connect, read_commits, verify_ledger
from omrs.question_ops import resume_question, suspend_question
from omrs.scheduling import generate_recommendations, get_items_by_uids, schedule_questions
from omrs.stats import get_stats


class QuestionSuspendTests(unittest.TestCase):
    def make_vault(self):
        vault = tempfile.TemporaryDirectory()
        questions = [
            create_question(vault.name, subject="数学", category="代数", difficulty=5, question_text="题一"),
            create_question(vault.name, subject="数学", category="几何", difficulty=6, question_text="题二"),
            create_question(vault.name, subject="物理", category="力学", difficulty=7, question_text="题三"),
        ]
        return vault, questions

    def test_suspend_keeps_markdown_but_excludes_question_from_active_data(self):
        vault, questions = self.make_vault()
        with vault:
            target = questions[0]
            result = suspend_question(vault.name, target["uid"], reason="暂不复习")

            self.assertEqual(result["uid"], target["uid"])
            self.assertTrue(result["suspended"])
            self.assertTrue(os.path.isfile(os.path.join(vault.name, target["file_path"])))
            with connect(vault.name) as db:
                row = db.execute(
                    "SELECT suspended, archived FROM question_projection WHERE question_id = ?",
                    (target["question_id"],),
                ).fetchone()
            self.assertEqual(row["suspended"], 1)
            self.assertEqual(row["archived"], 0)
            csv_row = next(r for r in load_csv(mastery_path(vault.name), MASTERY_HEADERS) if r["UID"] == target["uid"])
            self.assertEqual(csv_row["Suspended"], "1")
            commits = read_commits(vault.name, ascending=True)
            self.assertEqual(commits[-1]["commit_type"], "question.suspend")
            self.assertTrue(verify_ledger(vault.name)["valid"])

            stats = get_stats(vault.name)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["suspended"], 1)
            self.assertEqual({item["uid"] for item in stats["items"]}, {q["uid"] for q in questions})
            self.assertTrue(next(item for item in stats["items"] if item["uid"] == target["uid"])["suspended"])

            scheduled = schedule_questions(vault.name, count=10)
            self.assertNotIn(target["uid"], {item["UID"] for item in scheduled})
            recommendations = generate_recommendations(vault.name, due_count=10, prof_count=10)
            recommended_uids = {item["uid"] for bucket in recommendations.values() for item in bucket}
            self.assertNotIn(target["uid"], recommended_uids)
            with self.assertRaisesRegex(RuntimeError, "已停用"):
                get_items_by_uids(vault.name, [target["uid"]])
            with self.assertRaisesRegex(RuntimeError, "没有可导出的题目"):
                export_schedule_artifact(vault.name, [target["uid"]], "", "screen")

    def test_suspend_removes_history_from_analytics_but_resume_restores_question(self):
        vault, questions = self.make_vault()
        with vault:
            target = questions[0]
            process_feedback(vault.name, [{"uid": target["uid"], "sub_score": 8, "is_correct": True}])
            before = get_analytics(vault.name)
            self.assertEqual(before["overview"]["total_reviews"], 1)

            suspend_question(vault.name, target["uid"])
            after = get_analytics(vault.name)
            self.assertEqual(after["overview"]["total_reviews"], 0)
            self.assertEqual(after["overview"]["suspended_count"], 1)
            self.assertNotIn(target["uid"], {item["uid"] for item in after["items"]})

            resumed = resume_question(vault.name, target["uid"], reason="恢复复习")
            self.assertFalse(resumed["suspended"])
            stats = get_stats(vault.name)
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["suspended"], 0)
            exported = export_schedule_artifact(vault.name, [target["uid"]], "", "screen")
            self.assertEqual(exported[3], "text/html; charset=utf-8")
            commits = read_commits(vault.name, ascending=True)
            self.assertEqual([c["commit_type"] for c in commits[-2:]], ["question.suspend", "question.resume"])
            self.assertTrue(verify_ledger(vault.name)["valid"])

    def test_feedback_to_suspended_question_is_rejected_without_new_commit(self):
        vault, questions = self.make_vault()
        with vault:
            target = questions[0]
            suspend_question(vault.name, target["uid"])
            before = len(read_commits(vault.name, ascending=True))
            result = process_feedback(
                vault.name,
                [{"uid": target["uid"], "sub_score": 5, "is_correct": False}],
            )
            self.assertEqual(result[0]["status"], "error")
            self.assertIn("停用", result[0]["msg"])
            self.assertEqual(len(read_commits(vault.name, ascending=True)), before)
            self.assertEqual(load_csv(history_path(vault.name), HISTORY_HEADERS), [])

    def test_legacy_csv_without_suspended_column_is_compatible(self):
        vault, questions = self.make_vault()
        with vault:
            rows = load_csv(mastery_path(vault.name), MASTERY_HEADERS)
            with open(mastery_path(vault.name), "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=MASTERY_HEADERS[:-1])
                writer.writeheader()
                writer.writerows({key: row.get(key, "") for key in MASTERY_HEADERS[:-1]} for row in rows)
            stats = get_stats(vault.name)
            self.assertEqual(stats["total"], 3)
            self.assertEqual(stats["suspended"], 0)


if __name__ == "__main__":
    unittest.main()
