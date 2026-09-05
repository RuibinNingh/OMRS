"""展示板导出：服务端数据契约（分页在浏览器完成，见 tests/smoke_board_print.js）。"""
import json
import re
import tempfile
import unittest

from omrs.boards import create_board, get_board, update_board
from omrs.creation import create_question
from omrs.exporting import _board_label_ink, board_export_filename, export_board_html


def _data(html):
    match = re.search(r"window\.OMRS_DATA = (\{.*?\});</script>", html.decode("utf-8"), re.DOTALL)
    assert match
    return json.loads(match.group(1))


class BoardExportTests(unittest.TestCase):
    def test_labels_meta_and_filename(self):
        with tempfile.TemporaryDirectory() as vault:
            from omrs.labels import save_label
            from omrs.question_ops import set_question_labels
            question = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="题目 <b>")
            save_label(vault, name="考前必看", color="#dc2626")
            set_question_labels(vault, question["uid"], ["考前必看"])
            board = create_board(vault, "标记板", [question["uid"]])
            data = _data(export_board_html(vault, board["id"]))
            labels = data["questions"][0]["labels"]
            self.assertEqual(labels[0]["name"], "考前必看")
            self.assertEqual(labels[0]["color"], "#dc2626")
            self.assertTrue(labels[0]["ink"].startswith("#"))
            self.assertEqual(data["questions"][0]["blocks"][0]["text"], "题目 <b>")   # 文字原样交给浏览器 textContent
            update_board(vault, board["id"], print={"show_labels": False})
            data = _data(export_board_html(vault, board["id"]))
            self.assertEqual(data["questions"][0]["labels"], [])
            name = board_export_filename(get_board(vault, board["id"]), "new")
            self.assertTrue(name.startswith("OMRS-BD-标记板-新增") and name.endswith(".html"))

    def test_label_ink_reaches_aa_contrast_on_paper(self):
        def luminance(rgb):
            values = []
            for component in rgb:
                channel = component / 255
                values.append(channel / 12.92 if channel <= .03928 else ((channel + .055) / 1.055) ** 2.4)
            return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]
        for color in ["#dc2626", "#ca8a04", "#16a34a", "#ffff00", "#000000", "#64748b"]:
            ink = _board_label_ink(color)
            r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            background = tuple(round(v * .18 + 255 * .82) for v in (r, g, b))
            fr, fg, fb = (int(ink[i:i + 2], 16) for i in (1, 3, 5))
            first, second = luminance((fr, fg, fb)), luminance(background)
            self.assertGreaterEqual((max(first, second) + .05) / (min(first, second) + .05), 4.5, color)


if __name__ == "__main__":
    unittest.main()
