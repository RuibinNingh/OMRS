import csv
import os
import tempfile
import unittest

from omrs.common import MASTERY_HEADERS, load_csv, mastery_path
from omrs.creation import create_question
from omrs.analytics import get_analytics
from omrs.feedback import process_feedback
from omrs.labels import (
    label_priority_bonus,
    load_labels,
    merge_labels,
    save_label,
)
from omrs.ledger import connect, read_commits
from omrs.question_ops import set_question_labels
from omrs.scheduling import compute_priority
from omrs.stats import get_stats


class LabelTests(unittest.TestCase):
    def test_labels_json_yaml_projection_and_idempotent_clear(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(
                vault, subject="数学", category="代数", difficulty=5,
                question_text="题目",
            )
            saved = save_label(vault, name="考前必看", color="#dc2626")
            self.assertEqual(load_labels(vault)["labels"][0]["name"], "考前必看")

            first = set_question_labels(vault, question["uid"], ["考前必看"])
            self.assertTrue(first["changed"])
            commits_after_set = len(read_commits(vault, ascending=True))
            repeated = set_question_labels(vault, question["uid"], ["考前必看"])
            self.assertFalse(repeated["changed"])
            self.assertEqual(len(read_commits(vault, ascending=True)), commits_after_set)

            markdown_path = os.path.join(vault, question["file_path"])
            with open(markdown_path, "r", encoding="utf-8") as file:
                markdown = file.read()
            self.assertIn("标记:\n  - \"考前必看\"", markdown)

            with connect(vault) as db:
                projected = db.execute(
                    "SELECT label FROM question_labels WHERE question_id = ?",
                    (question["question_id"],),
                ).fetchall()
            self.assertEqual([row["label"] for row in projected], ["考前必看"])
            stats_item = next(item for item in get_stats(vault)["items"] if item["uid"] == question["uid"])
            self.assertEqual(stats_item["labels"], ["考前必看"])

            cleared = set_question_labels(vault, question["uid"], [])
            self.assertTrue(cleared["changed"])
            with open(markdown_path, "r", encoding="utf-8") as file:
                markdown = file.read()
            self.assertIn("标记: []", markdown)
            with connect(vault) as db:
                count = db.execute(
                    "SELECT COUNT(*) AS n FROM question_labels WHERE question_id = ?",
                    (question["question_id"],),
                ).fetchone()["n"]
            self.assertEqual(count, 0)
            self.assertEqual(
                next(item for item in get_stats(vault)["items"] if item["uid"] == question["uid"])["labels"],
                [],
            )
            self.assertEqual(saved["count"], 0)

    def test_legacy_csv_without_labels_column_is_compatible(self):
        with tempfile.TemporaryDirectory() as vault:
            create_question(vault, subject="数学", category="代数", difficulty=5)
            rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
            headers = [header for header in MASTERY_HEADERS if header != "Labels"]
            with open(mastery_path(vault), "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=headers)
                writer.writeheader()
                writer.writerows({key: row.get(key, "") for key in headers} for row in rows)

            stats = get_stats(vault)
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["items"][0]["labels"], [])

    def test_rename_delete_and_merge_cascade_yaml_references(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_question(vault, subject="数学", category="代数", difficulty=5)
            second = create_question(vault, subject="数学", category="代数", difficulty=5)
            source = save_label(vault, name="计算失误", color="#dc2626")
            target = save_label(vault, name="压轴", color="#2563eb")
            set_question_labels(vault, first["uid"], ["计算失误"])
            set_question_labels(vault, second["uid"], ["计算失误", "压轴"])

            renamed = save_label(
                vault, value=source["id"], name="粗心", color="#ea580c",
            )
            self.assertEqual(renamed["affected"], 2)
            self.assertEqual(
                next(item for item in get_stats(vault)["items"] if item["uid"] == first["uid"])["labels"],
                ["粗心"],
            )

            merged = merge_labels(vault, "粗心", target["id"])
            self.assertEqual(merged["affected"], 2)
            self.assertNotIn("粗心", [item["name"] for item in load_labels(vault)["labels"]])
            self.assertEqual(
                next(item for item in get_stats(vault)["items"] if item["uid"] == first["uid"])["labels"],
                ["压轴"],
            )
            self.assertEqual(
                next(item for item in get_stats(vault)["items"] if item["uid"] == second["uid"])["labels"],
                ["压轴"],
            )

            deleted = __import__("omrs.labels", fromlist=["delete_label"]).delete_label(
                vault, target["id"], detach=True,
            )
            self.assertEqual(deleted["affected"], 2)
            self.assertEqual(
                [item for item in get_stats(vault)["items"] if item["labels"]],
                [],
            )

    def test_label_priority_bonus_is_capped_and_default_zero(self):
        self.assertEqual(label_priority_bonus(["A", "B"], {"A": 0.7, "B": 0.6}, cap=1.0), 1.0)
        self.assertEqual(label_priority_bonus(["A"], {"A": -1}, cap=1.0), 0.0)
        base = compute_priority(
            0.5, 2.5, 0, "#状态/待攻克", 0.5,
        )
        boosted = compute_priority(
            0.5, 2.5, 0, "#状态/待攻克", 0.5,
            labels=["考前必看"], label_bonuses={"考前必看": 0.3},
        )
        self.assertAlmostEqual(boosted - base, 0.3)

    def test_analytics_reports_accuracy_and_average_score_by_label(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_question(vault, subject="数学", category="代数", difficulty=5)
            second = create_question(vault, subject="数学", category="代数", difficulty=5)
            save_label(vault, name="计算失误")
            save_label(vault, name="压轴")
            set_question_labels(vault, first["uid"], ["计算失误"])
            set_question_labels(vault, second["uid"], ["计算失误", "压轴"])
            process_feedback(vault, [{
                "uid": first["uid"], "sub_score": 8, "is_correct": True,
            }])
            process_feedback(vault, [{
                "uid": second["uid"], "sub_score": 4, "is_correct": False,
            }])

            by_label = {
                item["label"]: item for item in get_analytics(vault)["accuracy"]["by_label"]
            }
            self.assertEqual(by_label["计算失误"]["questions"], 2)
            self.assertEqual(by_label["计算失误"]["reviews"], 2)
            self.assertEqual(by_label["计算失误"]["correct"], 1)
            self.assertEqual(by_label["计算失误"]["accuracy"], 0.5)
            self.assertEqual(by_label["计算失误"]["avg_score"], 6.0)
            self.assertEqual(by_label["压轴"]["questions"], 1)
            self.assertEqual(by_label["压轴"]["reviews"], 1)
            self.assertEqual(by_label["压轴"]["correct"], 0)
            self.assertEqual(by_label["压轴"]["avg_score"], 4.0)


if __name__ == "__main__":
    unittest.main()
