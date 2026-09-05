import datetime
import tempfile
import unittest

from omrs.common import MASTERY_HEADERS, load_csv, mastery_path, save_csv
from omrs.creation import create_question
from omrs.scheduling import generate_recommendations
from omrs.server import OMRSHandler
from omrs.sessions import create_session_from_selection


class RecommendationTests(unittest.TestCase):
    def test_negative_counts_return_no_recommendations(self):
        with tempfile.TemporaryDirectory() as vault:
            due = create_question(vault, "数学", "代数", 5)
            future = create_question(vault, "数学", "几何", 5)
            rows = load_csv(mastery_path(vault), MASTERY_HEADERS)
            next(row for row in rows if row["UID"] == future["uid"])["Due_Date"] = (
                datetime.date.today() + datetime.timedelta(days=7)
            ).isoformat()
            save_csv(mastery_path(vault), MASTERY_HEADERS, rows)

            result = generate_recommendations(vault, due_count=-1, prof_count=-1)

        self.assertEqual(result, {"due": [], "proficiency": []})
        self.assertNotEqual(due["uid"], future["uid"])

    def test_bulk_recommendation_endpoint_excludes_active_session_items(self):
        with tempfile.TemporaryDirectory() as vault:
            assigned = create_question(vault, "数学", "代数", 5)
            available = create_question(vault, "数学", "几何", 5)
            create_session_from_selection(vault, [{"uid": assigned["uid"], "source": "due"}])

            handler = object.__new__(OMRSHandler)
            handler.vault_path = vault
            handler.path = "/api/recommend?due_count=1000&prof_count=1000"
            responses = []
            handler._json = responses.append
            handler.do_GET()

        self.assertEqual(responses[0]["status"], "ok")
        returned = {
            item["uid"]
            for bucket in (responses[0]["due"], responses[0]["proficiency"])
            for item in bucket
        }
        self.assertNotIn(assigned["uid"], returned)
        self.assertIn(available["uid"], returned)


if __name__ == "__main__":
    unittest.main()
