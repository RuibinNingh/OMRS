import tempfile
import unittest

from omrs.common import HISTORY_HEADERS, MASTERY_HEADERS, SESSIONS_HEADERS, history_path, mastery_path, save_csv, sessions_path
from omrs.sessions import get_session, list_sessions, create_session_from_selection
from omrs.feedback import process_feedback
from omrs.ledger import append_commit
from omrs.projections import rebuild_projection
from omrs.common import load_csv


class SessionFeedbackProgressTests(unittest.TestCase):
    def project_fixture(self, vault, count):
        questions = [{"question_id": f"Q{i}", "uid": f"U{i}", "file_path": f"错题/数学/U{i}.md", "subject": "数学", "category": "代数"} for i in range(1, count + 1)]
        sessions = load_csv(sessions_path(vault))
        import json
        for session in sessions:
            entries = json.loads(session["UIDs"])
            session["UIDs"] = json.dumps([{**(item if isinstance(item, dict) else {"uid": item}), "question_id": "Q" + (item["uid"] if isinstance(item, dict) else item)[1:]} for item in entries])
        history = [{**row, "Question_ID": "Q" + row["UID"][1:]} for row in load_csv(history_path(vault))]
        append_commit(vault, "test", "legacy.bootstrap", "迁移合法身份夹具", {"questions": questions, "session_rows": sessions, "history_rows": history})
        rebuild_projection(vault)

    def test_exceptions_require_explicit_closeout_in_either_order(self):
        for event in ("question.suspend", "question.archive"):
            for first in (True, False):
                with self.subTest(event=event, lifecycle_first=first), tempfile.TemporaryDirectory() as vault:
                    self.project_fixture(vault, 2)
                    session = create_session_from_selection(vault, [
                        {"question_id": qid, "source": "due"} for qid in ("Q1", "Q2")])
                    sid = session["session_id"]

                    def change():
                        append_commit(vault, "test", event, "变更题目", {"question_id": "Q1"})
                        rebuild_projection(vault)

                    if first:
                        change()
                    self.assertEqual(process_feedback(vault, [
                        {"question_id": "Q2", "is_correct": True, "sub_score": 8}], sid)[0]["status"], "ok")
                    if not first:
                        change()
                    loaded = get_session(vault, sid)
                    self.assertEqual(loaded["status"], "active")
                    self.assertEqual([e["feedback_state"] for e in loaded["entries"]], ["unavailable", "recorded"])
                    self.assertTrue(loaded["progress"]["can_finish"])
                    self.assertEqual(loaded["progress"], list_sessions(vault)[0]["progress"])

    def test_list_sessions_reports_submitted_and_pending_uids_in_session_order(self):
        with tempfile.TemporaryDirectory() as vault:
            save_csv(
                sessions_path(vault),
                SESSIONS_HEADERS,
                [{
                    "Session_ID": "S1",
                    "Created_At": "2026-08-28T10:00:00",
                    "Subject_Filter": "数学",
                    "Count": "3",
                    "UIDs": '[{"uid":"U1","source":"due"},{"uid":"U2","source":"proficiency"},{"uid":"U3","source":"due"}]',
                    "Status": "active",
                    "Completed_At": "",
                }],
            )
            save_csv(
                history_path(vault),
                HISTORY_HEADERS,
                [
                    {"Log_ID": "L1", "UID": "U2", "Date": "2026-08-28 10:01", "Action": "Feedback", "Sub_Score": "8", "Is_Correct": "1", "Session_ID": "S1", "Note": ""},
                    {"Log_ID": "L2", "UID": "U2", "Date": "2026-08-28 10:02", "Action": "Feedback", "Sub_Score": "9", "Is_Correct": "1", "Session_ID": "S1", "Note": "重复历史不应重复计数"},
                ],
            )

            self.project_fixture(vault, 3)
            session = list_sessions(vault)[0]

        self.assertEqual(session["feedback_uids"], ["U2"])
        self.assertEqual(session["pending_uids"], ["U1", "U3"])
        self.assertEqual(session["feedback_count"], 1)
        self.assertEqual(session["pending_count"], 2)

    def test_get_session_exposes_same_progress_for_direct_detail_load(self):
        with tempfile.TemporaryDirectory() as vault:
            save_csv(
                sessions_path(vault),
                SESSIONS_HEADERS,
                [{
                    "Session_ID": "S1",
                    "Created_At": "2026-08-28T10:00:00",
                    "Subject_Filter": "数学",
                    "Count": "2",
                    "UIDs": '["U1", "U2"]',
                    "Status": "active",
                    "Completed_At": "",
                }],
            )
            save_csv(
                mastery_path(vault),
                MASTERY_HEADERS,
                [
                    {header: ("U1" if header == "UID" else "") for header in MASTERY_HEADERS},
                    {header: ("U2" if header == "UID" else "") for header in MASTERY_HEADERS},
                ],
            )
            save_csv(
                history_path(vault),
                HISTORY_HEADERS,
                [{"Log_ID": "L1", "UID": "U1", "Date": "2026-08-28 10:01", "Action": "Feedback", "Sub_Score": "8", "Is_Correct": "1", "Session_ID": "S1", "Note": ""}],
            )

            self.project_fixture(vault, 2)
            session = get_session(vault, "S1")

        self.assertEqual(session["feedback_uids"], ["U1"])
        self.assertEqual(session["pending_uids"], ["U2"])
        self.assertEqual(session["feedback_count"], 1)
        self.assertEqual(session["pending_count"], 1)


if __name__ == "__main__":
    unittest.main()
