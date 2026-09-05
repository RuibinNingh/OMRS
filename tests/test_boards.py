import json
import os
import re
import tempfile
import unittest

from omrs.boards import (
    add_items,
    boards_path,
    board_items_for_export,
    create_board,
    duplicate_board,
    get_board,
    load_boards,
    record_printed,
    reset_printed,
    save_boards,
    update_board,
)
from omrs.creation import create_question
from omrs.exporting import export_board_html
from omrs.question_ops import delete_question, move_question, save_question_markdown, suspend_question, get_question_raw


def embedded_data(payload):
    source = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    match = re.search(r"window\.OMRS_DATA = (\{.*?\});</script>", source, re.DOTALL)
    if not match:
        raise AssertionError("导出 HTML 没有嵌入 OMRS_DATA")
    return json.loads(match.group(1))


def layout_for(uids, pages=1, cursor_y=300.0):
    """模拟浏览器排版结果：每题一段，全部在最后一页。"""
    return {
        "pages": pages,
        "cursor": {"page": pages, "y": cursor_y},
        "items": [{"question_id": qid, "uid": uid, "segments": [{"page": pages, "top": index * 90.0, "height": 80.0}]}
                  for index, (qid, uid) in enumerate(uids)],
        "answer_pages": [],
    }


class BoardTests(unittest.TestCase):
    def test_crud_atomic_backups_and_unknown_print_keys_are_ignored(self):
        with tempfile.TemporaryDirectory() as vault:
            board = create_board(vault, "考前板")
            path = boards_path(vault)
            self.assertTrue(os.path.isfile(path))
            for index in range(4):
                board = update_board(vault, board["id"], note=f"第 {index} 次")
            self.assertTrue(os.path.isfile(f"{path}.bak.1"))
            self.assertTrue(os.path.isfile(f"{path}.bak.3"))

            with open(path, "w", encoding="utf-8") as file:
                json.dump({"version": 1, "boards": [{
                    "id": board["id"], "name": "旧格式板",
                    "print": {"note_ratio": 0.9, "gap_lines": "x", "note_align": "lines", "binding_mm": 22},
                    "last_printed_page": 3,
                }]}, file)
            loaded = load_boards(vault)["boards"][0]
            self.assertEqual(loaded["name"], "旧格式板")
            self.assertNotIn("note_align", loaded["print"])
            self.assertNotIn("last_printed_page", loaded)
            self.assertEqual(loaded["print"]["note_ratio"], 0.55)   # 钳到上限
            self.assertEqual(loaded["print"]["gap_lines"], 2)       # 非法值回默认
            self.assertEqual(loaded["printed"]["pages"], 0)

    def test_question_id_survives_move_and_deleted_question_is_missing(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="题目")
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
            updated = add_items(vault, board["id"], [question["uid"], question["uid"]])
            self.assertEqual(len(updated["items"]), 1)
            self.assertEqual(updated["added"], 0)

    def test_update_items_keeps_added_at_and_extra_gap(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_question(vault, subject="数学", category="代数", difficulty=5)
            second = create_question(vault, subject="数学", category="代数", difficulty=5)
            board = create_board(vault, "排序板", [first["uid"], second["uid"]])
            original = {item["uid"]: item["added_at"] for item in board["items"]}
            reordered = update_board(vault, board["id"], items=[
                {"question_id": board["items"][1]["question_id"], "uid": second["uid"], "extra_gap_lines": 30},
                {"question_id": board["items"][0]["question_id"], "uid": first["uid"]},
            ])
            self.assertEqual([item["uid"] for item in reordered["items"]], [second["uid"], first["uid"]])
            self.assertEqual(reordered["items"][0]["extra_gap_lines"], 24)
            self.assertEqual({item["uid"]: item["added_at"] for item in reordered["items"]}, original)

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
            self.assertEqual([item["uid"] for item in data["questions"]], [second["uid"]])

    def test_printed_record_incremental_export_and_change_detection(self):
        with tempfile.TemporaryDirectory() as vault:
            questions = [
                create_question(vault, subject="数学", category="代数", difficulty=5, question_text=f"题 {i}", answer_text=f"答 {i}")
                for i in range(1, 4)
            ]
            board = create_board(vault, "增量板", [q["uid"] for q in questions[:2]])
            with self.assertRaises(RuntimeError):
                export_board_html(vault, board["id"], mode="new")   # 尚无纸面记录

            ids = [(item["question_id"], item["uid"]) for item in board["items"]]
            board = record_printed(vault, board["id"], "all", layout_for(ids, pages=2, cursor_y=400.0))
            summary = board["printed_summary"]
            self.assertEqual((summary["pages"], summary["count"], summary["new_count"]), (2, 2, 0))
            self.assertTrue(all(item["printed"] for item in board["items"]))
            self.assertEqual(board["items"][0]["printed_page"], 2)

            board = add_items(vault, board["id"], [questions[2]["uid"]])
            self.assertEqual(board["printed_summary"]["new_count"], 1)
            self.assertFalse(board["items"][2]["printed"])

            payload = export_board_html(vault, board["id"], mode="new")
            data = embedded_data(payload)
            self.assertEqual(data["meta"]["mode"], "new")
            self.assertEqual([q["uid"] for q in data["questions"]], [questions[2]["uid"]])
            self.assertEqual(data["questions"][0]["idx"], 3)          # 序号接着纸面继续
            self.assertEqual(data["meta"]["printed"]["cursor"], {"page": 2, "y": 400.0})
            self.assertEqual(data["meta"]["index_start"], 3)
            self.assertIn("<title>错题集</title>", payload.decode("utf-8"))
            self.assertNotIn("增量板", payload.decode("utf-8").split("window.OMRS_DATA")[0])

            # 增量记录：追加新题、推进 cursor，旧题保留
            board = record_printed(vault, board["id"], "new", {
                "pages": 3, "cursor": {"page": 3, "y": 120.0},
                "items": [{"question_id": board["items"][2]["question_id"], "uid": questions[2]["uid"],
                           "segments": [{"page": 2, "top": 400.0, "height": 90.0}, {"page": 3, "top": 0, "height": 40.0}]}],
                "answer_pages": [],
            })
            summary = board["printed_summary"]
            self.assertEqual((summary["pages"], summary["count"], summary["new_count"]), (3, 3, 0))
            self.assertEqual(summary["cursor"], {"page": 3, "y": 120.0})
            self.assertEqual(board["items"][2]["printed_page"], 2)

            # 修改已打印题目正文 → 纸面是旧版
            raw = get_question_raw(vault, questions[0]["uid"])
            save_question_markdown(vault, questions[0]["uid"], raw["markdown"].replace("题 1", "题 1（改）"))
            board = get_board(vault, board["id"])
            self.assertTrue(board["items"][0]["changed"])
            self.assertEqual(board["printed_summary"]["changed_count"], 1)

            # 增量模式：几何沿用纸面记录，答案等显示项跟随当前设置
            update_board(vault, board["id"], print={"note_ratio": 0.5, "answers": "append"})
            board = add_items(vault, board["id"], [])
            data = embedded_data(export_board_html(vault, board["id"], mode="new")) if board["printed_summary"]["new_count"] else None
            self.assertIsNone(data)
            with self.assertRaises(RuntimeError):
                export_board_html(vault, board["id"], mode="new")       # 没有新增题目

            # 复制板不带纸面记录；重置清空
            clone = duplicate_board(vault, board["id"], "副本")
            self.assertEqual(clone["printed_summary"]["pages"], 0)
            self.assertEqual(len(clone["items"]), 3)
            board = reset_printed(vault, board["id"])
            self.assertEqual(board["printed_summary"]["pages"], 0)
            self.assertEqual(board["printed_summary"]["new_count"], 3)

    def test_full_export_data_contract(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(
                vault, subject="物理", category="力学", difficulty=7,
                question_text="题目 $x^2$\n| A | B |\n| --- | --- |\n| 1 | 2 |", answer_text="答案",
            )
            board = create_board(vault, "不应上纸", [question["uid"]])
            detail = get_board(vault, board["id"])
            update_board(
                vault, board["id"],
                items=[{"question_id": detail["items"][0]["question_id"], "uid": question["uid"], "extra_gap_lines": 2}],
                print={"note_ratio": 0.5, "gap_lines": 8, "binding_mm": 25, "answers": "append"},
            )
            payload = export_board_html(vault, board["id"])
            data = embedded_data(payload)
            self.assertEqual(data["meta"]["print"]["note_ratio"], 0.5)
            self.assertEqual(data["meta"]["print"]["binding_mm"], 25)
            self.assertNotIn("binding_marks", data["meta"]["print"])
            self.assertEqual(data["meta"]["mode"], "all")
            self.assertIsNone(data["meta"]["printed"])
            self.assertEqual(data["questions"][0]["extra_gap_lines"], 2)
            self.assertEqual([b["t"] for b in data["questions"][0]["blocks"]], ["txt", "table"])
            self.assertEqual(data["answers"][0]["uid"], question["uid"])
            html = payload.decode("utf-8")
            self.assertIn("<title>错题集</title>", html)
            self.assertIn("katex", html)
            self.assertNotIn("不应上纸", html.split("window.OMRS_DATA")[0])


if __name__ == "__main__":
    unittest.main()
