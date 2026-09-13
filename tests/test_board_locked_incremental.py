"""锁定保护纸面，不冻结板内引用；临时题库执行真实读写和 HTML 导出。"""
import copy
import tempfile
import unittest

from omrs.boards import (add_items, create_board, get_board, read_printed_history,
                         record_printed, remove_items, update_board)
from omrs.creation import create_question
from omrs.exporting import export_board_html
from test_boards import embedded_data, layout_for


class LockedIncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = self.tmp.name
        self.questions = [create_question(self.vault, subject="数学", category="代数",
                          difficulty=5, question_text=f"锁定回归题 {i}") for i in range(4)]
        self.board = create_board(self.vault, "增量纸面", [q["uid"] for q in self.questions[:2]])
        layout = layout_for([(i["question_id"], i["uid"]) for i in self.board["items"]],
                            pages=3, cursor_y=456.78)
        layout["cursor"]["page"] = 2
        layout["answer_pages"] = [3]
        self.board = record_printed(self.vault, self.board["id"], "all", layout)
        self.paper = copy.deepcopy(self.board["printed"])

    def assert_paper(self, board):
        self.assertEqual(board["printed"], self.paper)
        self.assertEqual(get_board(self.vault, board["id"])["printed"], self.paper)
        self.assertEqual(read_printed_history(self.vault), [])

    def assert_new(self, uids):
        data = embedded_data(export_board_html(self.vault, self.board["id"], mode="new"))
        self.assertEqual([q["uid"] for q in data["questions"]], uids)
        self.assertEqual([q["idx"] for q in data["questions"]], list(range(3, 3 + len(uids))))
        self.assertEqual(data["meta"]["printed"]["cursor"], self.paper["cursor"])
        self.assertEqual(data["meta"]["index_start"], 3)

    def test_append_and_duplicate_preserve_entire_paper_and_continue_export(self):
        for locked in (False, True):
            with self.subTest(locked=locked):
                update_board(self.vault, self.board["id"], print={"locked": locked})
                board = add_items(self.vault, self.board["id"], [self.questions[2]["uid"]], position=0)
                self.assert_paper(board)
                board = add_items(self.vault, self.board["id"], [self.questions[2]["uid"]] * 2)
                self.assertEqual(board["added"], 0)
                self.assert_paper(board)
                self.assert_new([self.questions[2]["uid"]])
                # 下一轮需要真正追加，而不是仅重复追加。
                update_board(self.vault, self.board["id"], print={"locked": False})
                remove_items(self.vault, self.board["id"], [self.questions[2]["uid"]])

    def test_replace_items_preserves_paper_for_membership_order_and_unprinted_gap(self):
        board = update_board(self.vault, self.board["id"], print={"locked": True})
        new = {"question_id": self.questions[2]["question_id"], "uid": self.questions[2]["uid"]}
        variants = [
            ("append", board["items"] + [new]),
            ("duplicate", board["items"] + [new, new]),
            ("reorder", [new] + list(reversed(board["items"]))),
            ("unprinted_gap", [{**new, "gap_lines": 17}] + board["items"]),
            ("equivalent_printed_gap", [new] + [{**i, "gap_lines": 2, "pin": True} for i in board["items"]]),
            ("remove_printed", [new, board["items"][1]]),
            ("readd_printed", [new] + board["items"]),
            ("remove_unprinted", board["items"]),
            ("clear", []),
        ]
        for name, items in variants:
            with self.subTest(change=name):
                updated = update_board(self.vault, self.board["id"], items=items)
                self.assert_paper(updated)
                if any(i["uid"] == new["uid"] for i in items):
                    self.assert_new([new["uid"]])
        board = update_board(self.vault, self.board["id"], items=[new] + board["items"])
        self.assert_paper(board)
        self.assert_new([new["uid"]])
        updated = update_board(self.vault, self.board["id"], items=[
            {**i, "gap_lines": 9} if i["printed"] else i for i in board["items"]])
        self.assertEqual(updated["printed"]["pages"], 0, "已印题真实留白变化仍保留锁定兜底")

    def test_global_gap_without_affected_printed_items_preserves_paper(self):
        board = update_board(self.vault, self.board["id"], items=[{**i, "gap_lines": 2} for i in self.board["items"]])
        update_board(self.vault, self.board["id"], print={"locked": True})
        board = add_items(self.vault, self.board["id"], [self.questions[2]["uid"]])
        board = update_board(self.vault, self.board["id"], print={"gap_lines": 11, "answers": "append"})
        self.assert_paper(board)
        self.assertEqual(board["items"][-1]["effective_gap_lines"], 11)
        self.assert_new([self.questions[2]["uid"]])
        board = update_board(self.vault, self.board["id"], items=[i for i in board["items"] if not i["printed"]], print={"gap_lines": 14})
        self.assert_paper(board)
        self.assert_new([self.questions[2]["uid"]])

    def test_inactive_cut_label_preserves_paper(self):
        update_board(self.vault, self.board["id"], print={"cut_line": "none"})
        update_board(self.vault, self.board["id"], print={"locked": True})
        board = update_board(self.vault, self.board["id"], print={"cut_label": True})
        self.assert_paper(board)

    def test_uid_only_updates_cannot_bypass_printed_gap_protection(self):
        update_board(self.vault, self.board["id"], print={"locked": True})
        updated = update_board(self.vault, self.board["id"], items=[
            {"uid": i["uid"], "gap_lines": 9} for i in self.board["items"]])
        self.assertEqual(updated["printed"]["pages"], 0)
        self.assertEqual([i["question_id"] for i in updated["items"]],
                         [i["question_id"] for i in self.board["items"]])

    def test_remove_preserves_old_slots_and_readd_does_not_reprint(self):
        update_board(self.vault, self.board["id"], print={"locked": True})
        add_items(self.vault, self.board["id"], [q["uid"] for q in self.questions[2:]])
        for question in (self.questions[2], self.questions[0]):
            with self.subTest(remove=question["uid"]):
                board = remove_items(self.vault, self.board["id"], [question["question_id"]])
                self.assert_paper(board)
                self.assert_new([self.questions[3]["uid"]])
        board = add_items(self.vault, self.board["id"], [self.questions[0]["uid"]], position=0)
        self.assert_paper(board)
        self.assertTrue(board["items"][0]["printed"])
        self.assert_new([self.questions[3]["uid"]])
