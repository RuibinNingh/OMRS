import tempfile
import os
import unittest

from omrs.projections import (_project_state, _content_change_summary, ledger_history,
                              ledger_history_detail, ledger_retraction_state)
from omrs.ledger import append_commit
from omrs.feedback import _question_summary_at_feedback


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

    def test_summary_pagination_keeps_full_chain_retraction_and_lazy_detail(self):
        with tempfile.TemporaryDirectory() as vault:
            append_commit(vault, "system", "system.genesis", "开始", {})
            review = append_commit(vault, "api", "review.batch_submit", "练习", {"feedbacks": [
                {"uid_at_that_time": "U1", "is_correct": False, "sub_score": 3,
                 "subject": "数学", "question_summary": "一次函数求值", "note": "完整详情"}]})
            for index in range(255):
                append_commit(vault, "system", "system.test", f"填充 {index}", {"large": "x" * 300})
            append_commit(vault, "api", "review.retract", "撤销", {
                "target_commit_id": review["commit_id"], "target_review_index": 0})
            first = ledger_history(vault, limit=60, summary_only=True)
            self.assertEqual(len(first), 60)
            self.assertEqual(first[-1]["commit_type"], "review.retract")
            self.assertEqual(ledger_retraction_state(vault)["retracted_reviews"], [f"{review['commit_id']}:0"])
            before = min(row["seq"] for row in first)
            pages = first[:]
            while before > 1:
                page = ledger_history(vault, before_seq=before, limit=60, summary_only=True)
                if not page:
                    break
                self.assertTrue(all(row["seq"] < before for row in page))
                pages = page + pages
                before = min(row["seq"] for row in page)
            self.assertEqual(len(pages), 258)
            slim = next(row for row in pages if row["seq"] == review["seq"])
            self.assertEqual(slim["learning"]["subjects"], {"数学": 1})
            self.assertEqual(slim["learning"]["questions"], ["一次函数求值"])
            self.assertNotIn("note", slim["payload"]["feedbacks"][0])
            self.assertEqual(ledger_history_detail(vault, review["seq"])["payload"]["feedbacks"][0]["note"], "完整详情")

    def test_missing_old_blob_does_not_invent_content_change(self):
        with tempfile.TemporaryDirectory() as vault:
            append_commit(vault, "system", "system.genesis", "开始", {})
            row = append_commit(vault, "self_check", "question.content_update", "正文更新", {
                "uid_at_that_time": "U1", "before_hash": "missing", "after_hash": "missing2"})
            detail = ledger_history_detail(vault, row["seq"])
            self.assertEqual(detail["content_change"], {"available": False, "message": "无可用历史摘要"})

    def test_content_change_ignores_frontmatter_and_names_real_sections(self):
        before = "---\n_omrs_id: Q1\n科目: 数学\n---\n# 题目\n旧题面\n# 答案\n旧答案\n"
        metadata_only = before.replace("科目: 数学", "科目: 物理")
        self.assertEqual(_content_change_summary(before, metadata_only),
                         {"available": False, "sections": [], "message": "无可用历史摘要"})
        mixed = metadata_only.replace("旧题面", "新题面").replace("旧答案", "新答案")
        change = _content_change_summary(before, mixed)
        self.assertEqual([item["section"] for item in change["sections"]], ["题目", "答案"])
        self.assertNotIn("_omrs_id", str(change))

    def test_feedback_summary_keeps_math_and_is_fixed_from_safe_file(self):
        with tempfile.TemporaryDirectory() as vault:
            relative = os.path.join("错题", "数学", "代数", "Q1.md")
            path = os.path.join(vault, relative)
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as file:
                file.write("# 题目\n计算 2 * 3 与 $x_1$。 ![[图1.png]]\n# 答案\n6\n")
            self.assertEqual(_question_summary_at_feedback(vault, {"File_Path": relative}),
                             "计算 2 * 3 与 $x_1$。")
            self.assertEqual(_question_summary_at_feedback(vault, {"File_Path": "../outside.md"}), "")

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

    def test_metadata_update_can_clear_knowledge_tags(self):
        initial = legacy_commit()
        initial["payload"]["questions"][0]["knowledge_tags"] = ["旧知识点"]
        state = self.project(
            [
                initial,
                commit(
                    2,
                    "CMT-000002",
                    "question.metadata_update_external",
                    {"question_id": "Q1", "after": {"question_id": "Q1", "knowledge_tags": []}},
                ),
            ]
        )

        self.assertEqual(state["questions"]["Q1"]["knowledge_tags"], [])


if __name__ == "__main__":
    unittest.main()
