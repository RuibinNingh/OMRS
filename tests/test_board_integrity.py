"""展示板记录归属、导出内容快照与撤销清单契约。"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from omrs.boards import add_items, boards_path, create_board, get_board, record_printed
from omrs.creation import create_question
from omrs.exporting import _safe_question_path, export_board_html


class BoardIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = self.temp.name
        self.first = create_question(self.vault, subject="数学", category="代数", difficulty=5, question_text="旧题面")
        self.second = create_question(self.vault, subject="数学", category="代数", difficulty=5, question_text="第二题")
        self.board = create_board(self.vault, "甲", [self.first["uid"]])

    def test_add_returns_only_actually_added_uids_without_persisting_response_metadata(self):
        board = add_items(self.vault, self.board["id"], [self.first["uid"], self.second["uid"], self.second["uid"], "不存在"])
        self.assertEqual(board["added"], 1)
        self.assertEqual(board["added_uids"], [self.second["uid"]])
        self.assertEqual(add_items(self.vault, board["id"], [self.second["uid"]])["added_uids"], [])
        raw = json.loads(Path(boards_path(self.vault)).read_text())
        self.assertNotIn("added_uids", raw["boards"][0])

    def test_record_rejects_foreign_board_and_mode_without_writing(self):
        path = Path(boards_path(self.vault))
        before = path.read_bytes()
        for extra in ({"board_id": "BD-another"}, {"mode": "new"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                record_printed(self.vault, self.board["id"], "all", {"pages": 1, **extra})
            self.assertEqual(path.read_bytes(), before)

    def test_record_rejects_foreign_unknown_or_mismatched_items(self):
        path = Path(boards_path(self.vault))
        layouts = [
            {"question_id": self.second["question_id"], "uid": self.second["uid"]},
            {"question_id": "OP-FAKE", "uid": "UID-FAKE"},
            {"question_id": self.first["question_id"], "uid": self.second["uid"]},
        ]
        for item in layouts:
            with self.subTest(item=item):
                before = path.read_bytes()
                layout = {"pages": 1, "items": [{**item, "segments": [{"page": 1, "top": 0, "height": 80}]}]}
                with self.assertRaises(ValueError):
                    record_printed(self.vault, self.board["id"], "all", layout)
                self.assertEqual(path.read_bytes(), before)

    def test_new_record_requires_existing_paper_and_in_bounds_pages(self):
        item = self.board["items"][0]
        base = {"pages": 1, "cursor": {"page": 1, "y": 100},
                "items": [{"question_id": item["question_id"], "uid": item["uid"],
                           "segments": [{"page": 1, "top": 0, "height": 80}]}]}
        with self.assertRaises(ValueError):
            record_printed(self.vault, self.board["id"], "new", base)
        for change in ({"cursor": {"page": 2, "y": 0}},
                       {"items": [{**base["items"][0], "segments": [{"page": 2}]}]},
                       {"answer_pages": [2]}):
            with self.subTest(change=change):
                printed = record_printed(self.vault, self.board["id"], "all", base)
                self.assertEqual(printed["printed_summary"]["pages"], 1)
                with self.assertRaises(ValueError):
                    record_printed(self.vault, self.board["id"], "new", {**base, **change})

    def test_question_paths_cannot_escape_vault_question_directory(self):
        valid = self.board["items"][0].get("file_path") or "错题/数学/代数/Q.md"
        self.assertIsNotNone(_safe_question_path(self.vault, valid))
        self.assertIsNone(_safe_question_path(self.vault, "../outside.md"))
        self.assertIsNone(_safe_question_path(self.vault, "/tmp/outside.md"))

    def test_record_preserves_exported_content_hash_after_markdown_changes(self):
        html = export_board_html(self.vault, self.board["id"]).decode()
        data = json.loads(re.search(r'window\.OMRS_DATA = (\{.*?\});</script>', html, re.S)[1])
        exported = data["questions"][0]
        item = get_board(self.vault, self.board["id"])["items"][0]
        path = Path(self.vault, item["file_path"])
        path.write_text(path.read_text().replace("旧题面", "已修改的新题面"))
        layout = {"board_id": self.board["id"], "mode": "all", "pages": 1,
                  "cursor": {"page": 1, "y": 100}, "items": [{
                      "question_id": exported["question_id"], "uid": exported["uid"], "hash": exported["hash"],
                      "segments": [{"page": 1, "top": 0, "height": 100}]}]}
        board = record_printed(self.vault, self.board["id"], "all", layout)
        self.assertEqual(board["printed"]["items"][0]["hash"], exported["hash"])
        self.assertTrue(board["items"][0]["changed"])
        # 老导出件缺少归属 / 指纹仍兼容，按当时记录的正文回退。
        for key in ("board_id", "mode"):
            layout.pop(key)
        layout["items"][0].pop("hash")
        board = record_printed(self.vault, self.board["id"], "all", layout)
        self.assertFalse(board["items"][0]["changed"])


if __name__ == '__main__':
    unittest.main()
