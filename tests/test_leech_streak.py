import tempfile
import unittest

from omrs.analytics import get_analytics
from omrs.creation import create_question
from omrs.feedback import process_feedback
from omrs.question_ops import move_question
from omrs.scheduling import generate_recommendations
from omrs.stats import get_stats


class LeechStreakTests(unittest.TestCase):
    def test_renamed_question_keeps_its_wrong_streak(self):
        with tempfile.TemporaryDirectory() as vault:
            uid = create_question(vault, "数学", "代数", 5)["uid"]
            for _ in range(3):
                process_feedback(vault, [{"uid": uid, "sub_score": 2, "is_correct": False}])
            new_uid = move_question(vault, uid, "数学", "几何")["uid"]

            self.assertNotEqual(new_uid, uid)
            self.assertEqual(get_stats(vault)["items"][0]["wrong_streak"], 3)
            recommendations = generate_recommendations(vault, due_count=10, prof_count=10)
            item = next(item for bucket in recommendations.values() for item in bucket)
            self.assertEqual(item["uid"], new_uid)
            self.assertTrue(item["is_leech"])

    def test_three_recent_wrong_answers_mark_leech_and_correct_resets_it(self):
        with tempfile.TemporaryDirectory() as vault:
            uid = create_question(vault, "数学", "代数", 5)["uid"]

            def snapshot():
                stats = get_stats(vault)
                analytics = get_analytics(vault)
                recommended = generate_recommendations(vault, due_count=10, prof_count=10)
                rec_item = next(
                    item for bucket in recommended.values() for item in bucket
                    if item["uid"] == uid
                )
                return stats, analytics, rec_item

            for count in (1, 2, 3):
                process_feedback(vault, [{"uid": uid, "sub_score": 2, "is_correct": False}])
                stats, analytics, rec_item = snapshot()
                expected = count >= 3
                self.assertEqual(stats["items"][0]["wrong_streak"], count)
                self.assertEqual(stats["items"][0]["is_leech"], expected)
                self.assertEqual(stats["review_alert"]["leech"], int(expected))
                self.assertEqual(analytics["items"][0]["is_leech"], expected)
                self.assertEqual(analytics["overview"]["leech"], int(expected))
                self.assertEqual(rec_item["is_leech"], expected)

            process_feedback(vault, [{"uid": uid, "sub_score": 2, "is_correct": True}])
            stats, analytics, rec_item = snapshot()
            self.assertEqual(stats["items"][0]["fail_count"], 3)
            self.assertEqual(stats["items"][0]["wrong_streak"], 0)
            self.assertFalse(stats["items"][0]["is_leech"])
            self.assertEqual(analytics["weak_spots"]["leeches"], [])
            self.assertFalse(rec_item["is_leech"])

            for _ in range(2):
                process_feedback(vault, [{"uid": uid, "sub_score": 2, "is_correct": False}])
            stats, _, _ = snapshot()
            self.assertEqual(stats["items"][0]["fail_count"], 5)
            self.assertEqual(stats["items"][0]["wrong_streak"], 2)
            self.assertFalse(stats["items"][0]["is_leech"])


if __name__ == "__main__":
    unittest.main()
