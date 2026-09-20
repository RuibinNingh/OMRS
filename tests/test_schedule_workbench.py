"""Persistent selection contract and review-source regression coverage."""
import io
import json
import tempfile
import unittest

from omrs.creation import create_question
from omrs.feedback import process_feedback
from omrs.ledger import read_commits
from omrs.question_ops import suspend_question
from omrs.server import OMRSHandler
from omrs.sessions import create_session_from_selection, get_session, list_sessions


class ScheduleWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.questions = [create_question(self.vault, "数学", category, 5,
                                         question_text="求 $1+1$", answer_text="2")
                          for category in ("代数", "几何")]

    def confirm(self, payload):
        handler = object.__new__(OMRSHandler)
        handler.vault_path = self.vault
        handler.path = "/api/confirm-schedule"
        body = json.dumps(payload).encode()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        responses = []
        handler._json = lambda value, status=200: responses.append((value, status))
        handler.do_POST()
        return responses[0]

    def test_single_persistent_plan_is_readable_and_excludes_duplicate(self):
        uid = self.questions[0]["uid"]
        result, status = self.confirm({"selected": [{"uid": uid, "source": "proficiency"}], "persist": True})
        self.assertEqual(status, 200)
        self.assertEqual(result["session_type"], "exp")
        self.assertEqual(result["count"], 1)
        self.assertEqual(list_sessions(self.vault)[0]["pending_uids"], [uid])
        self.assertEqual(get_session(self.vault, result["session_id"])["items"][0]["_source"], "proficiency")
        before = len(read_commits(self.vault))
        duplicate, status = self.confirm({"selected": [{"uid": uid, "source": "due"}], "persist": True})
        self.assertEqual(status, 400)
        self.assertIn("进行中", duplicate["msg"])
        self.assertEqual(len(read_commits(self.vault)), before)

    def test_legacy_single_stays_temporary(self):
        result, status = self.confirm({"selected": [{"uid": self.questions[0]["uid"], "source": "due"}]})
        self.assertEqual(status, 200)
        self.assertEqual(result["session_type"], "tmp")
        self.assertEqual(list_sessions(self.vault), [])

    def test_duplicates_are_saved_once_in_first_seen_order(self):
        first, second = [q["uid"] for q in self.questions]
        selected = [{"uid": first, "source": "proficiency"}, {"uid": first, "source": "due"},
                    {"uid": second, "source": "due"}]
        result, status = self.confirm({"selected": selected, "persist": True})
        self.assertEqual(status, 200)
        self.assertEqual(result["count"], 2)
        session = list_sessions(self.vault)[0]
        self.assertEqual(session["uids"], [first, second])
        self.assertEqual(get_session(self.vault, result["session_id"])["items"][0]["_source"], "proficiency")

    def test_invalid_selections_do_not_write(self):
        uid = self.questions[0]["uid"]
        suspend_question(self.vault, uid)
        before = len(read_commits(self.vault))
        for selected in ([{"uid": uid, "source": "due"}], [{"uid": "missing", "source": "due"}],
                         [{"uid": self.questions[1]["uid"], "source": "smart"}], [None], ["x"], []):
            with self.subTest(selected=selected):
                _, status = self.confirm({"selected": selected, "persist": True})
                self.assertEqual(status, 400)
                self.assertEqual(len(read_commits(self.vault)), before)
                self.assertEqual(list_sessions(self.vault), [])

    def test_source_drives_interval_and_partial_progress(self):
        first, second = [q["uid"] for q in self.questions]
        session = create_session_from_selection(self.vault, [
            {"uid": first, "source": "proficiency"}, {"uid": second, "source": "due"}])
        # At the first correct repetition the normal interval is 6, early review is round(6*.7)=4.
        result = process_feedback(self.vault, [{"uid": first, "sub_score": 5, "is_correct": True}], session["session_id"])
        self.assertEqual(result[0]["new_interval"], 4)
        self.assertEqual(result[0]["source"], "proficiency")
        progress = list_sessions(self.vault)[0]
        self.assertEqual(progress["feedback_count"], 1)
        self.assertEqual(progress["pending_uids"], [second])
        result = process_feedback(self.vault, [{"uid": second, "sub_score": 5, "is_correct": True}], session["session_id"])
        self.assertEqual(result[0]["new_interval"], 6)
        self.assertEqual(list_sessions(self.vault)[0]["status"], "completed")

    def test_persist_flag_requires_boolean(self):
        _, status = self.confirm({"selected": [{"uid": self.questions[0]["uid"]}], "persist": "true"})
        self.assertEqual(status, 400)
        self.assertFalse(list_sessions(self.vault))


if __name__ == '__main__':
    unittest.main()
