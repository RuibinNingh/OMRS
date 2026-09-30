"""题目创建时间投影、兼容字段和助手组合检索回归。"""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from omrs.agent.tools import read
from omrs.creation import create_question
from omrs.ledger import connect, ledger_path
from omrs.projections import _project_state
from omrs.stats import get_question_content, get_stats
from omrs.workspace_sync import scan_workspace


def _commit(seq, kind, payload, created_at):
    return {"seq": seq, "commit_id": f"C{seq}", "commit_type": kind, "created_at": created_at,
            "source": "test", "message": kind, "payload": payload}


class CreationMetadataTests(unittest.TestCase):
    def test_old_projection_gets_nullable_created_at_column(self):
        vault = tempfile.mkdtemp(prefix="omrs-created-schema-")
        os.makedirs(os.path.join(vault, "错题"))
        os.makedirs(os.path.dirname(ledger_path(vault)), exist_ok=True)
        db = sqlite3.connect(ledger_path(vault))
        db.execute("CREATE TABLE question_projection (question_id TEXT PRIMARY KEY, uid TEXT UNIQUE NOT NULL, file_path TEXT UNIQUE NOT NULL, subject TEXT NOT NULL, category TEXT NOT NULL, difficulty INTEGER, current_tag TEXT, metadata_json TEXT NOT NULL, metadata_hash TEXT NOT NULL, content_hash TEXT, archived INTEGER NOT NULL DEFAULT 0, suspended INTEGER NOT NULL DEFAULT 0, updated_seq INTEGER NOT NULL)")
        db.commit(); db.close()
        with connect(vault) as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(question_projection)")}
        self.assertIn("created_at", columns)

    def test_create_time_persists_across_move_and_api_fields(self):
        vault = tempfile.mkdtemp(prefix="omrs-created-api-")
        os.makedirs(os.path.join(vault, "错题"))
        question = create_question(vault, "数学", "函数", 5, question_text="题面")
        stats_item = next(item for item in get_stats(vault)["items"] if item["uid"] == question["uid"])
        detail = get_question_content(vault, question["uid"])
        self.assertTrue(stats_item["created_at"])
        self.assertEqual(detail["created_at"], stats_item["created_at"])
        self.assertRegex(detail["entry_date"], r"^\d{4}-\d{2}-\d{2}$")
        before = stats_item["created_at"]
        from omrs.question_ops import move_question
        moved = move_question(vault, question["uid"], "数学", "代数")
        after = next(item for item in get_stats(vault)["items"] if item["uid"] == moved["uid"])["created_at"]
        self.assertEqual(before, after)

    def test_external_create_uses_first_ledger_time(self):
        vault = tempfile.mkdtemp(prefix="omrs-created-external-")
        path = os.path.join(vault, "错题", "数学", "外部题1.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write("---\n_omrs_id: Q-EXT\n科目: 数学\n分类: 函数\n难度: 5\n录入日期: 2026-01-02\n---\n\n# 题目\n外部题\n")
        scan_workspace(vault)
        first = next(item for item in get_stats(vault)["items"] if item["uid"] == "外部题1")
        self.assertTrue(first["created_at"])
        created = first["created_at"]
        scan_workspace(vault)
        second = next(item for item in get_stats(vault)["items"] if item["uid"] == "外部题1")
        self.assertEqual(second["created_at"], created)

    def test_legacy_questions_have_no_precise_time(self):
        state = _project_state(tempfile.mkdtemp(), [_commit(1, "legacy.bootstrap", {
            "questions": [{"question_id": "Q1", "uid": "U1", "file_path": "错题/数学/U1.md",
                            "subject": "数学", "category": "函数", "difficulty": 5}],
            "mastery_rows": [], "session_rows": [], "history_rows": [],
        }, "2026-01-01T00:00:00+00:00")])
        self.assertEqual(state["questions"]["Q1"].get("created_at"), "")

    def test_replayed_duplicate_create_keeps_first_time(self):
        payload = {"question": {"question_id": "Q1", "uid": "U1", "file_path": "错题/数学/U1.md",
                                 "subject": "数学", "category": "函数", "difficulty": 5}}
        state = _project_state(tempfile.mkdtemp(), [
            _commit(1, "question.create", payload, "2026-01-01T00:00:00+00:00"),
            _commit(2, "question.create", payload, "2026-01-02T00:00:00+00:00"),
        ])
        self.assertEqual(state["questions"]["Q1"]["created_at"], "2026-01-01T00:00:00+00:00")

    def test_search_combines_labels_dates_and_three_level_sort_before_page(self):
        items = {
            "A": {"uid": "A", "subject": "数学", "category": "函数", "difficulty": 5, "mastery": .4,
                  "attempts": 1, "labels": ["考前", "易错"], "created_at": "2026-01-03T00:00:00+00:00", "entry_date": "2026-01-03", "suspended": False, "due_date": "", "tag": ""},
            "B": {"uid": "B", "subject": "数学", "category": "函数", "difficulty": 5, "mastery": .4,
                  "attempts": 1, "labels": ["考前"], "created_at": "2026-01-02T00:00:00+00:00", "entry_date": "2026-01-02", "suspended": False, "due_date": "", "tag": ""},
            "C": {"uid": "C", "subject": "数学", "category": "函数", "difficulty": 4, "mastery": .2,
                  "attempts": 1, "labels": ["考前", "易错"], "created_at": "2026-01-01T00:00:00+00:00", "entry_date": "2026-01-01", "suspended": False, "due_date": "", "tag": ""},
        }
        cached = ({"题目": "题面", "答案": "", "错因": ""}, {"题目": "题面", "答案": "", "错因": ""})
        args = {"labels": ["考前", "易错"], "label_match": "all", "created_from": "2026-01-01", "created_to": "2026-01-03",
                "sort": [{"field": "difficulty", "direction": "asc"}, {"field": "created_at", "direction": "desc"}],
                "page_size": 1, "page": 1}
        with mock.patch.object(read, "_items", return_value=items), mock.patch.object(read, "_content", return_value=(None, cached)):
            result = read.search_questions({"vault": "unused"}, args)["result"]
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["uid"], "C")
        self.assertEqual(result["pages"], 2)

    def test_search_rejects_bad_dates_and_duplicate_sort_fields(self):
        with self.assertRaises(ValueError):
            read.search_questions({"vault": "unused"}, {"created_from": "not-a-date"})
        with self.assertRaises(ValueError):
            read.search_questions({"vault": "unused"}, {"sort": [{"field": "uid"}, {"field": "uid"}]})


if __name__ == "__main__":
    unittest.main()
