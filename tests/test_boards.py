import json
import os
import re
import tempfile
import unittest

from omrs.boards import (
    BOARDS_VERSION,
    MAX_GAP_LINES,
    add_items,
    boards_path,
    board_items_for_export,
    create_board,
    create_folder,
    delete_folder,
    duplicate_board,
    effective_gap_lines,
    list_boards,
    list_folders,
    move_board,
    get_board,
    load_boards,
    printed_history_path,
    read_printed_history,
    record_printed,
    reset_printed,
    save_boards,
    update_board,
    update_folder,
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
    def test_new_board_uses_equal_question_and_note_columns_by_default(self):
        with tempfile.TemporaryDirectory() as vault:
            board = create_board(vault, "对半板")
            self.assertEqual(board["print"]["note_ratio"], 0.5)

    def test_locked_layout_change_clears_printed_state(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="题目")
            board = create_board(vault, "锁定板", [question["uid"]])
            item = board["items"][0]
            board = record_printed(vault, board["id"], "all", layout_for([(item["question_id"], item["uid"])], pages=1))
            self.assertEqual(board["printed_summary"]["pages"], 1)
            board = update_board(vault, board["id"], print={"locked": True})
            self.assertTrue(board["print"]["locked"])
            self.assertEqual(board["printed_summary"]["pages"], 1)
            board = update_board(vault, board["id"], print={"gap_lines": 8})
            self.assertEqual(board["printed_summary"]["pages"], 0)
            self.assertEqual(board["printed_summary"]["new_count"], 1)

    def test_locked_item_reorder_clears_printed_state(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="一")
            second = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="二")
            board = create_board(vault, "锁定排序", [first["uid"], second["uid"]])
            ids = [(item["question_id"], item["uid"]) for item in board["items"]]
            board = record_printed(vault, board["id"], "all", layout_for(ids))
            board = update_board(vault, board["id"], print={"locked": True})
            reordered = list(reversed(board["items"]))
            board = update_board(vault, board["id"], items=reordered)
            self.assertEqual(board["printed_summary"]["pages"], 0)

    def test_locked_reset_keeps_printed_history_for_layout_and_item_changes(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="一")
            second = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="二")
            board = create_board(vault, "锁定历史", [first["uid"]])
            item = board["items"][0]
            record_printed(vault, board["id"], "all", layout_for([(item["question_id"], item["uid"])]))
            update_board(vault, board["id"], print={"locked": True})
            update_board(vault, board["id"], print={"gap_lines": 6})
            rows = read_printed_history(vault)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event"], "reset")
            self.assertEqual(rows[0]["count"], 1)

            board = record_printed(vault, board["id"], "all", layout_for([(item["question_id"], item["uid"])]))
            add_items(vault, board["id"], [second["uid"]])
            rows = read_printed_history(vault)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["event"], "reset")
            self.assertEqual(rows[0]["count"], 1)

    def test_unlock_and_change_still_resets_stale_paper_in_one_request(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="题目")
            board = create_board(vault, "解锁改版", [question["uid"]])
            item = board["items"][0]
            record_printed(vault, board["id"], "all", layout_for([(item["question_id"], item["uid"])]))
            update_board(vault, board["id"], print={"locked": True})
            updated = update_board(vault, board["id"], print={"locked": False, "gap_lines": 9})
            self.assertFalse(updated["print"]["locked"])
            self.assertEqual(updated["print"]["gap_lines"], 9)
            self.assertEqual(updated["printed_summary"]["pages"], 0)

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
            self.assertNotIn("binding_mm", loaded["print"])
            self.assertEqual(loaded["name"], "旧格式板")
            self.assertNotIn("note_align", loaded["print"])
            self.assertNotIn("last_printed_page", loaded)
            self.assertEqual(loaded["print"]["note_ratio"], 0.55)   # 钳到上限
            self.assertEqual(loaded["print"]["gap_lines"], 2)       # 非法值回默认
            self.assertEqual(loaded["printed"]["pages"], 0)

            updated = update_board(vault, board["id"], print={"note_ratio": 0.42})
            self.assertEqual(updated["print"]["note_ratio"], 0.42)  # 已保存的自定义比例不迁移

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

    def test_update_items_keeps_added_at_and_folds_legacy_extra_gap(self):
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
            # v2 客户端仍传 extra_gap_lines：先夹到 24，再按「全局 2 + 额外 24」折算成绝对 26 行
            self.assertEqual(reordered["items"][0]["gap_lines"], 26)
            self.assertEqual(reordered["items"][0]["extra_gap_lines"], 0)
            self.assertEqual(reordered["items"][0]["effective_gap_lines"], 26)
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
            self.assertNotIn("binding_mm", data["meta"]["print"])
            self.assertNotIn("binding_marks", data["meta"]["print"])
            self.assertEqual(data["meta"]["mode"], "all")
            self.assertIsNone(data["meta"]["printed"])
            self.assertEqual(data["questions"][0]["gap_lines"], 10)   # 全局 8 + v2 额外 2，折算成绝对值
            self.assertNotIn("extra_gap_lines", data["questions"][0])
            self.assertEqual([b["t"] for b in data["questions"][0]["blocks"]], ["txt", "table"])
            self.assertEqual(data["answers"][0]["uid"], question["uid"])
            html = payload.decode("utf-8")
            self.assertIn("<title>错题集</title>", html)
            self.assertIn("katex", html)
            self.assertNotIn("不应上纸", html.split("window.OMRS_DATA")[0])


if __name__ == "__main__":
    unittest.main()


class BoardFolderTests(unittest.TestCase):
    def test_v1_file_migrates_to_current_version_with_every_board_unfiled(self):
        with tempfile.TemporaryDirectory() as vault:
            board = create_board(vault, "老板子")
            with open(boards_path(vault), "w", encoding="utf-8") as file:
                json.dump({"version": 1, "boards": [{"id": board["id"], "name": "老板子"}]}, file)
            data = load_boards(vault)
            self.assertEqual(data["version"], BOARDS_VERSION)
            self.assertEqual(data["folders"], [])
            self.assertEqual(data["boards"][0]["folder_id"], "")
            self.assertEqual(data["boards"][0]["order"], 0)

    def test_dangling_folder_id_falls_back_to_unfiled_without_dropping_the_board(self):
        with tempfile.TemporaryDirectory() as vault:
            folder = create_folder(vault, "高三上")
            board = create_board(vault, "板", folder_id=folder["id"])
            delete_folder(vault, folder["id"])                       # 默认保留板
            self.assertEqual(list_folders(vault), [])
            self.assertEqual(len(list_boards(vault)), 1)

            path = boards_path(vault)
            with open(path, encoding="utf-8") as file:
                raw = json.load(file)
            raw["boards"][0]["folder_id"] = "BF-不存在"
            with open(path, "w", encoding="utf-8") as file:
                json.dump(raw, file, ensure_ascii=False)
            reloaded = load_boards(vault)["boards"]
            self.assertEqual(len(reloaded), 1)                       # 不报错、不丢板
            self.assertEqual(reloaded[0]["folder_id"], "")
            self.assertEqual(reloaded[0]["id"], board["id"])

    def test_folder_crud_reorders_and_clamps_names(self):
        with tempfile.TemporaryDirectory() as vault:
            first = create_folder(vault, "  期中  考试 ")
            self.assertEqual(first["name"], "期中 考试")             # 折叠空白
            second = create_folder(vault, "已归档")
            self.assertEqual([f["order"] for f in list_folders(vault)], [0, 1])
            update_folder(vault, second["id"], order=0)
            self.assertEqual([f["name"] for f in list_folders(vault)], ["已归档", "期中 考试"])
            update_folder(vault, second["id"], name="归档区")
            self.assertEqual(list_folders(vault)[0]["name"], "归档区")
            with self.assertRaises(ValueError):
                create_folder(vault, "   ")
            with self.assertRaises(ValueError):
                update_folder(vault, "BF-不存在", name="x")

    def test_delete_folder_keeps_or_drops_the_boards_inside(self):
        with tempfile.TemporaryDirectory() as vault:
            folder = create_folder(vault, "组")
            create_board(vault, "A", folder_id=folder["id"])
            create_board(vault, "B", folder_id=folder["id"])
            result = delete_folder(vault, folder["id"])              # keep_boards 默认 True
            self.assertEqual(result["boards_kept"], 2)
            self.assertEqual(sorted(b["name"] for b in list_boards(vault)), ["A", "B"])
            self.assertTrue(all(b["folder_id"] == "" for b in list_boards(vault)))

            other = create_folder(vault, "临时组")
            create_board(vault, "C", folder_id=other["id"])
            dropped = delete_folder(vault, other["id"], keep_boards=False)
            self.assertEqual(dropped["boards_deleted"], 1)
            self.assertEqual(sorted(b["name"] for b in list_boards(vault)), ["A", "B"])

    def test_move_board_across_and_within_groups_renumbers_order(self):
        with tempfile.TemporaryDirectory() as vault:
            folder = create_folder(vault, "组")
            a = create_board(vault, "A", folder_id=folder["id"])
            b = create_board(vault, "B", folder_id=folder["id"])
            c = create_board(vault, "C")                              # 未归档
            inside = lambda fid: [x["name"] for x in list_boards(vault) if x["folder_id"] == fid]
            self.assertEqual(inside(folder["id"]), ["A", "B"])

            move_board(vault, b["id"], folder["id"], 0)               # 组内前移
            self.assertEqual(inside(folder["id"]), ["B", "A"])
            move_board(vault, c["id"], folder["id"], 1)               # 跨组插到中间
            self.assertEqual(inside(folder["id"]), ["B", "C", "A"])
            self.assertEqual(inside(""), [])
            move_board(vault, c["id"], "")                            # 移回未归档
            self.assertEqual(inside(folder["id"]), ["B", "A"])
            self.assertEqual(inside(""), ["C"])
            self.assertEqual([x["order"] for x in list_boards(vault) if x["folder_id"] == folder["id"]], [0, 1])
            # 越界 index 收敛到组尾，不抛错
            move_board(vault, a["id"], folder["id"], 99)
            self.assertEqual(inside(folder["id"]), ["B", "A"])

    def test_created_and_duplicated_boards_land_in_the_right_folder(self):
        with tempfile.TemporaryDirectory() as vault:
            folder = create_folder(vault, "组")
            a = create_board(vault, "A", folder_id=folder["id"])
            create_board(vault, "B", folder_id=folder["id"])
            clone = duplicate_board(vault, a["id"], "A 副本")
            self.assertEqual(clone["folder_id"], folder["id"])
            # 副本紧跟源板，不掉到组尾（同秒操作的 updated_at 会撞在一起，靠显式重编号）
            self.assertEqual([x["name"] for x in list_boards(vault)], ["A", "A 副本", "B"])
            # 未知 folder_id 静默落到未归档
            self.assertEqual(create_board(vault, "C", folder_id="BF-不存在")["folder_id"], "")
            update_board(vault, a["id"], folder_id="BF-也不存在")
            self.assertEqual(get_board(vault, a["id"])["folder_id"], "")

    def test_list_boards_exposes_uids_for_the_picker_row_state(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="题")
            board = create_board(vault, "板", [question["uid"]])
            row = next(x for x in list_boards(vault) if x["id"] == board["id"])
            self.assertEqual(row["uids"], [question["uid"]])


class BoardGapMigrationTests(unittest.TestCase):
    """v2（全局 + extra_gap_lines）→ v3（每题绝对 gap_lines）的迁移等值与幂等。"""

    def _write_v2(self, vault, board_id, global_gap, extras):
        with open(boards_path(vault), "w", encoding="utf-8") as file:
            json.dump({"version": 2, "folders": [], "boards": [{
                "id": board_id, "name": "v2 板",
                "print": {"note_ratio": 0.42, "gap_lines": global_gap, "binding_mm": 22},
                "items": [{"question_id": f"OP-{i:06d}", "uid": f"题{i}", "extra_gap_lines": extra}
                          for i, extra in enumerate(extras)],
            }]}, file, ensure_ascii=False)

    def test_v2_extra_gap_migrates_to_equal_absolute_gap_per_item(self):
        with tempfile.TemporaryDirectory() as vault:
            board = create_board(vault, "占位")
            self._write_v2(vault, board["id"], 3, [0, 1, 5, 24, 99])
            items = load_boards(vault)["boards"][0]["items"]
            settings = load_boards(vault)["boards"][0]["print"]
            # extra=0 不折算（保持继承 None）；其余 = 全局 3 + 夹到 24 的 extra
            self.assertEqual([item["gap_lines"] for item in items], [None, 4, 8, 27, 27])
            # 「有效留白」与迁移前 v2 语义（全局 + extra）逐题等值 —— 纸面像素不变
            v2_effective = [3 + min(24, extra) for extra in [0, 1, 5, 24, 99]]
            self.assertEqual([effective_gap_lines(item, settings) for item in items], v2_effective)
            self.assertTrue(all(item["extra_gap_lines"] == 0 for item in items))

    def test_second_normalization_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as vault:
            board = create_board(vault, "占位")
            self._write_v2(vault, board["id"], 3, [0, 2, 24])
            once = load_boards(vault)
            self.assertEqual(once["version"], BOARDS_VERSION)
            save_boards(vault, once)                       # 写回 v3
            twice = load_boards(vault)
            self.assertEqual(twice["boards"][0]["items"], once["boards"][0]["items"])
            save_boards(vault, twice)                      # 再存一次
            self.assertEqual(load_boards(vault)["boards"][0]["items"], once["boards"][0]["items"])

    def test_absolute_gap_is_clamped_and_null_means_inherit(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5)
            board = create_board(vault, "留白板", [question["uid"]])
            qid = board["items"][0]["question_id"]
            for sent, expected in [(None, None), (0, 0), (7, 7), (99, MAX_GAP_LINES), ("x", None)]:
                result = update_board(vault, board["id"], items=[
                    {"question_id": qid, "uid": question["uid"], "gap_lines": sent}])
                self.assertEqual(result["items"][0]["gap_lines"], expected, sent)
            # None → 有效值跟随全局
            update_board(vault, board["id"], print={"gap_lines": 6})
            detail = get_board(vault, board["id"])
            self.assertIsNone(detail["items"][0]["gap_lines"])
            self.assertEqual(detail["items"][0]["effective_gap_lines"], 6)

    def test_items_and_print_in_one_update_fold_with_the_requested_global_gap(self):
        """同一请求同时提交 items + print：v2 折算必须用**本次请求后**的全局留白。"""
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5)
            board = create_board(vault, "同帧板", [question["uid"]])       # 全局默认 2
            qid = board["items"][0]["question_id"]
            result = update_board(
                vault, board["id"],
                items=[{"question_id": qid, "uid": question["uid"], "extra_gap_lines": 4}],
                print={"gap_lines": 10},
            )
            self.assertEqual(result["print"]["gap_lines"], 10)
            self.assertEqual(result["items"][0]["gap_lines"], 14)          # 10 + 4，不是旧值 2 + 4
            self.assertEqual(result["items"][0]["effective_gap_lines"], 14)


class BoardPrintedHistoryTests(unittest.TestCase):
    """boards_printed_history.jsonl：只增不改的纸面事件流。"""

    def _board_with_paper(self, vault, name="历史板"):
        questions = [create_question(vault, subject="数学", category="代数", difficulty=5,
                                     question_text=f"题 {i}") for i in range(2)]
        board = create_board(vault, name, [q["uid"] for q in questions])
        ids = [(item["question_id"], item["uid"]) for item in board["items"]]
        return record_printed(vault, board["id"], "all", layout_for(ids, pages=2)), questions

    def test_missing_history_file_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as vault:
            self.assertFalse(os.path.isfile(printed_history_path(vault)))
            self.assertEqual(read_printed_history(vault), [])

    def test_first_record_writes_nothing_and_later_records_append_the_previous_paper(self):
        with tempfile.TemporaryDirectory() as vault:
            board, questions = self._board_with_paper(vault)
            # 第一次记录时旧纸面是空的（pages=0），没有可留存的历史
            self.assertEqual(read_printed_history(vault), [])

            extra = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="新")
            board = add_items(vault, board["id"], [extra["uid"]])
            ids = [(item["question_id"], item["uid"]) for item in board["items"]]
            record_printed(vault, board["id"], "all", layout_for(ids, pages=3))
            rows = read_printed_history(vault)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event"], "record")
            self.assertEqual(rows[0]["mode"], "all")
            self.assertEqual((rows[0]["pages"], rows[0]["count"]), (2, 2))    # 留存的是**被替换掉**的那份
            self.assertEqual(rows[0]["board_id"], board["id"])
            self.assertEqual(rows[0]["board_name"], "历史板")
            self.assertIn("note_ratio", rows[0]["print"])

    def test_reset_appends_the_paper_it_throws_away(self):
        with tempfile.TemporaryDirectory() as vault:
            board, _ = self._board_with_paper(vault)
            reset_printed(vault, board["id"])
            rows = read_printed_history(vault)
            self.assertEqual([row["event"] for row in rows], ["reset"])
            self.assertEqual(rows[0]["mode"], "")
            self.assertEqual(rows[0]["pages"], 2)
            reset_printed(vault, board["id"])                                  # 已经空了，没有历史可留
            self.assertEqual(len(read_printed_history(vault)), 1)

    def test_history_is_newest_first_filtered_by_board_and_limited(self):
        with tempfile.TemporaryDirectory() as vault:
            first, _ = self._board_with_paper(vault, "板一")
            second, _ = self._board_with_paper(vault, "板二")
            for board in (first, second, first):
                ids = [(item["question_id"], item["uid"]) for item in get_board(vault, board["id"])["items"]]
                record_printed(vault, board["id"], "all", layout_for(ids, pages=4))
            rows = read_printed_history(vault)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["board_id"], first["id"])                 # 倒序：最后一次事件在最前
            self.assertEqual([row["board_id"] for row in read_printed_history(vault, first["id"])],
                             [first["id"], first["id"]])
            self.assertEqual(len(read_printed_history(vault, limit=1)), 1)
            self.assertEqual(read_printed_history(vault, limit=0), [])

    def test_corrupt_lines_are_skipped_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as vault:
            board, _ = self._board_with_paper(vault)
            reset_printed(vault, board["id"])                                  # 产生 1 行合法记录
            with open(printed_history_path(vault), "a", encoding="utf-8") as file:
                file.write("\n")
                file.write("{不是 json}\n")
                file.write("[1,2,3]\n")                                        # 合法 JSON 但不是对象
                file.write(json.dumps({"board_id": board["id"], "event": "record", "pages": 9}) + "\n")
            rows = read_printed_history(vault)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["pages"], 9)
