import json
import os
import re
import tempfile
import unittest

from omrs.boards import (
    boards_path,
    board_items_for_export,
    create_board,
    get_board,
    load_boards,
    save_boards,
    update_board,
)
from omrs.creation import create_question
from omrs.exporting import export_board_html
from omrs.question_ops import delete_question, move_question, suspend_question


def embedded_data(payload):
    source = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    match = re.search(r"window\.OMRS_DATA = (\{.*?\});</script>", source, re.DOTALL)
    if not match:
        raise AssertionError("导出 HTML 没有嵌入 OMRS_DATA")
    return json.loads(match.group(1))


class BoardTests(unittest.TestCase):
    def test_crud_atomic_backups_and_legacy_print_keys_are_ignored(self):
        with tempfile.TemporaryDirectory() as vault:
            board = create_board(vault, "考前板")
            path = boards_path(vault)
            self.assertTrue(os.path.isfile(path))
            for index in range(4):
                board = update_board(vault, board["id"], note=f"第 {index} 次")
            self.assertTrue(os.path.isfile(f"{path}.bak.1"))
            self.assertTrue(os.path.isfile(f"{path}.bak.2"))
            self.assertTrue(os.path.isfile(f"{path}.bak.3"))

            with open(path, "w", encoding="utf-8") as file:
                json.dump({
                    "version": 1,
                    "boards": [{
                        "id": board["id"],
                        "name": "旧格式板",
                        "print": {
                            "note_ratio": 0.42,
                            "gap_lines": 6,
                            "note_align": "lines",
                            "note_min_lines": 4,
                            "note_pattern": "dots",
                        },
                    }],
                }, file)
            loaded = load_boards(vault)["boards"][0]
            self.assertEqual(loaded["name"], "旧格式板")
            self.assertNotIn("note_align", loaded["print"])
            self.assertNotIn("note_min_lines", loaded["print"])
            self.assertNotIn("note_pattern", loaded["print"])

    def test_question_id_survives_move_and_deleted_question_is_missing(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(
                vault, subject="数学", category="代数", difficulty=5,
                question_text="题目",
            )
            board = create_board(vault, "引用板", [question["uid"]])
            moved = move_question(vault, question["uid"], "数学", "几何")
            detail = get_board(vault, board["id"])
            self.assertEqual(detail["items"][0]["question_id"], question["question_id"])
            self.assertEqual(detail["items"][0]["uid"], moved["uid"])
            self.assertFalse(detail["items"][0]["missing"])

            delete_question(vault, moved["uid"])
            detail = get_board(vault, board["id"])
            self.assertTrue(detail["items"][0]["missing"])
            self.assertEqual(board_items_for_export(vault, board["id"])[1], [])

    def test_add_and_create_deduplicate_by_uid_and_question_id(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5)
            board = create_board(vault, "去重板", [question["uid"], question["uid"]])
            self.assertEqual(len(get_board(vault, board["id"])["items"]), 1)

            data = load_boards(vault)
            data["boards"][0]["items"][0]["question_id"] = ""
            save_boards(vault, data)
            updated = __import__("omrs.boards", fromlist=["add_items"]).add_items(
                vault, board["id"], [question["uid"], question["uid"]],
            )
            self.assertEqual(len(updated["items"]), 1)

    def test_suspend_is_kept_on_board_but_skipped_from_export(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="一")
            second = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="二")
            board = create_board(vault, "停用板", [first["uid"], second["uid"]])
            suspend_question(vault, first["uid"])
            detail = get_board(vault, board["id"])
            self.assertEqual(sum(1 for item in detail["items"] if item["suspended"]), 1)
            _, export_items = board_items_for_export(vault, board["id"])
            self.assertEqual([item["uid"] for item in export_items], [second["uid"]])

            data = embedded_data(export_board_html(vault, board["id"]))
            self.assertEqual([item["uid"] for item in data["all_questions"]], [second["uid"]])

    def test_extra_gap_answers_absolute_range_and_paper_title(self):
        with tempfile.TemporaryDirectory() as vault:
            questions = [
                create_question(
                    vault, subject="数学", category="代数", difficulty=5,
                    question_text="\n".join(["长题"] * 45), answer_text=f"答案 {index}",
                )
                for index in range(1, 4)
            ]
            board = create_board(vault, "系统内板名", [question["uid"] for question in questions])
            detail = get_board(vault, board["id"])
            items = detail["items"]
            items[0]["extra_gap_lines"] = 3
            update_board(
                vault, board["id"],
                items=[{
                    key: item.get(key)
                    for key in ("question_id", "uid", "added_at", "extra_gap_lines", "pin")
                } for item in items],
                print={"answers": "append", "gap_lines": 6, "binding_mm": 22, "note_ratio": 0.42},
            )

            payload = export_board_html(vault, board["id"], page_start=2, page_end=3)
            data = embedded_data(payload)
            self.assertEqual(data["page_start"], 2)
            self.assertEqual(data["page_end"], 3)
            self.assertEqual(data["estimated_total_pages"], 4)  # 3 question pages + answer page
            self.assertEqual([page["number"] for page in data["pages"]], [2, 3])
            self.assertEqual(data["all_questions"][0]["extra_gap_px"], 54)
            self.assertTrue(data["include_answers"])
            self.assertIn("<title>错题集</title>", payload.decode("utf-8"))
            self.assertNotIn("系统内板名", payload.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
