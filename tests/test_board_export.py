import json
import re
import tempfile
import unittest

from omrs.boards import create_board, get_board, update_board
from omrs.creation import create_question
from omrs.exporting import _board_text_html, export_board_html


def _data(html):
    match = re.search(r"window\.OMRS_DATA = (\{.*?\});</script>", html.decode("utf-8"), re.DOTALL)
    assert match
    return json.loads(match.group(1))


class BoardExportTests(unittest.TestCase):
    def test_board_export_geometry_gap_and_metadata(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(
                vault, subject="物理", category="力学", difficulty=7,
                question_text="题目", answer_text="答案",
            )
            board = create_board(vault, "不应上纸", [question["uid"]])
            detail = get_board(vault, board["id"])
            detail["items"][0]["extra_gap_lines"] = 2
            update_board(
                vault, board["id"],
                items=[{
                    key: detail["items"][0].get(key)
                    for key in ("question_id", "uid", "added_at", "extra_gap_lines", "pin")
                }],
                print={"note_ratio": 0.5, "gap_lines": 8, "binding_mm": 25},
            )
            payload = export_board_html(vault, board["id"])
            data = _data(payload)
            self.assertEqual(data["note_ratio"], 0.5)
            self.assertEqual(data["binding_px"], 25 * 3.7795)
            self.assertEqual(data["all_questions"][0]["gap_px"], 144)
            self.assertEqual(data["all_questions"][0]["extra_gap_px"], 36)
            self.assertEqual(data["board_id"], board["id"])
            html = payload.decode("utf-8")
            self.assertIn("<title>错题集</title>", html)
            self.assertNotIn("不应上纸", html)

    def test_board_text_keeps_tables_and_escapes_text(self):
        html = _board_text_html(
            "| A | B |\n| --- | --- |\n| <script> | $x$ |",
        )
        self.assertIn("bd-table", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_board_export_passes_binding_mark_choice_to_browser_template(self):
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(
                vault, subject="数学", category="代数", difficulty=5,
                question_text="题目",
            )
            board = create_board(vault, "孔位测试", [question["uid"]])
            update_board(vault, board["id"], print={"binding_marks": "26hole"})
            payload = export_board_html(vault, board["id"])
            data = _data(payload)
            self.assertEqual(data["binding_marks"], "26hole")
            self.assertIn("bd-binding-marks", payload.decode("utf-8"))
