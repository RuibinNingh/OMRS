import tempfile
import unittest

from omrs.projections import _project_state


def commit(seq, commit_id, commit_type, payload):
    return {
        "seq": seq,
        "commit_id": commit_id,
        "commit_type": commit_type,
        "created_at": f"2026-01-{seq:02d}T00:00:00+00:00",
        "source": "test",
        "message": commit_type,
        "payload": payload,
    }


def legacy_commit(current_tag="#状态/待攻克"):
    return commit(
        1,
        "GENESIS",
        "legacy.bootstrap",
        {
            "questions": [
                {
                    "question_id": "Q1",
                    "uid": "U1",
                    "file_path": "错题/数学/U1.md",
                    "subject": "数学",
                    "category": "代数",
                    "difficulty": 5,
                    "current_tag": current_tag,
                }
            ],
            "mastery_rows": [],
            "session_rows": [
                {
                    "Session_ID": "S1",
                    "Created_At": "2026-01-01",
                    "Subject_Filter": "",
                    "Count": "1",
                    "UIDs": "[\"U1\"]",
                    "Status": "active",
                    "Completed_At": "",
                }
            ],
            "history_rows": [],
        },
    )


def review_batch(seq=2, is_correct=True, score=10, session_id="S1"):
    return commit(
        seq,
        f"CMT-{seq:06d}",
        "review.batch_submit",
        {
            "session_id": session_id,
            "feedbacks": [
                {
                    "question_id": "Q1",
                    "uid_at_that_time": "U1",
                    "session_id": session_id,
                    "source": "due",
                    "is_correct": is_correct,
                    "sub_score": score,
                    "note": "",
                    "occurred_at": "2026-01-02",
                    "recorded_at": "2026-01-02T00:00:00+00:00",
                }
            ],
        },
    )


class HistoryProjectionTests(unittest.TestCase):
    def project(self, commits):
        with tempfile.TemporaryDirectory() as vault:
            return _project_state(vault, commits)

    def test_review_restore_replays_original_feedback(self):
        state = self.project(
            [
                legacy_commit(),
                review_batch(),
                commit(3, "CMT-000003", "review.retract", {"target_commit_id": "CMT-000002", "target_review_index": 0}),
                commit(4, "CMT-000004", "review.restore", {"target_commit_id": "CMT-000002", "target_review_index": 0}),
            ]
        )

        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["Log_ID"], "CMT-000002-001")
        self.assertEqual(state["mastery"]["Q1"]["attempts"], 1)

    def test_session_restore_replays_session_feedback(self):
        state = self.project(
            [
                legacy_commit(),
                review_batch(),
                commit(3, "CMT-000003", "session.retract", {"session_id": "S1"}),
                commit(4, "CMT-000004", "session.restore", {"session_id": "S1"}),
            ]
        )

        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["mastery"]["Q1"]["attempts"], 1)
        self.assertEqual(state["sessions"]["S1"]["Status"], "active")
        self.assertFalse(state["sessions"]["S1"]["_retracted"])

    def test_retract_resets_question_tag_to_baseline(self):
        state = self.project(
            [
                legacy_commit(current_tag="#状态/已击杀"),
                review_batch(is_correct=False, score=2),
                commit(3, "CMT-000003", "review.retract", {"target_commit_id": "CMT-000002", "target_review_index": 0}),
            ]
        )

        self.assertEqual(len(state["history"]), 0)
        self.assertEqual(state["mastery"]["Q1"]["attempts"], 0)
        self.assertEqual(state["questions"]["Q1"]["current_tag"], "#状态/已击杀")

    def test_replace_replays_replacement_payload(self):
        state = self.project(
            [
                legacy_commit(),
                review_batch(is_correct=True, score=10),
                commit(
                    3,
                    "CMT-000003",
                    "review.replace",
                    {
                        "target_commit_id": "CMT-000002",
                        "target_review_index": 0,
                        "replacement": {"sub_score": 2, "is_correct": False, "note": "修正"},
                    },
                ),
            ]
        )

        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["Sub_Score"], "2")
        self.assertEqual(state["history"][0]["Is_Correct"], "0")
        self.assertEqual(state["history"][0]["Note"], "修正")


if __name__ == "__main__":
    unittest.main()
