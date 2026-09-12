"""展示板导出：服务端数据契约（分页在浏览器完成，见 tests/smoke_board_print.js）。"""
import json
import re
import tempfile
import unittest

from omrs.boards import create_board, get_board, update_board
from omrs.creation import create_question
from omrs.exporting import _board_label_ink, _read_katex_bundle, board_export_filename, export_board_html


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

    def test_katex_bundle_inlines_only_woff2_and_is_cached(self):
        css, js = _read_katex_bundle()
        self.assertTrue(css and js)
        self.assertEqual(css.count("data:font/woff2;base64,"), 20)      # 每个字体族一份
        self.assertNotIn("data:font/ttf", css)
        self.assertNotIn("data:font/woff;", css)
        self.assertNotIn("url(fonts/", css)                               # 不残留相对路径
        self.assertLess(len(css), 450_000)                                # 三种格式全内联时约 1.4MB
        self.assertIs(css, _read_katex_bundle()[0])                       # 进程内缓存，不重复读盘编码
        with tempfile.TemporaryDirectory() as vault:
            question = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="$x$")
            board = create_board(vault, "字体板", [question["uid"]])
            html = export_board_html(vault, board["id"])
            self.assertLess(len(html), 1_100_000)
            self.assertNotIn(b"data:font/ttf", html)


if __name__ == "__main__":
    unittest.main()


class BoardExportGeometryTests(unittest.TestCase):
    """切割线与每题留白的服务端数据契约（画不画线由浏览器模板决定，见 smoke_board_print）。"""

    def _board(self, vault, texts=("题一", "题二")):
        uids = [create_question(vault, subject="数学", category="代数", difficulty=5,
                                question_text=text, answer_text="答")["uid"] for text in texts]
        return create_board(vault, "几何板", uids)

    def test_questions_carry_absolute_gap_lines_only(self):
        with tempfile.TemporaryDirectory() as vault:
            board = self._board(vault)
            detail = get_board(vault, board["id"])
            update_board(vault, board["id"], print={"gap_lines": 5}, items=[
                {"question_id": detail["items"][0]["question_id"], "uid": detail["items"][0]["uid"], "gap_lines": 12},
                {"question_id": detail["items"][1]["question_id"], "uid": detail["items"][1]["uid"], "gap_lines": None},
            ])
            questions = _data(export_board_html(vault, board["id"]))["questions"]
            self.assertEqual([q["gap_lines"] for q in questions], [12, 5])   # 覆盖值 / 继承全局
            for question in questions:
                self.assertNotIn("extra_gap_lines", question)
                self.assertIsInstance(question["gap_lines"], int)

    def test_per_question_gap_is_capped_at_48_before_it_reaches_the_template(self):
        with tempfile.TemporaryDirectory() as vault:
            board = self._board(vault, ("唯一题",))
            detail = get_board(vault, board["id"])
            update_board(vault, board["id"], items=[
                {"question_id": detail["items"][0]["question_id"], "uid": detail["items"][0]["uid"], "gap_lines": 900}])
            self.assertEqual(_data(export_board_html(vault, board["id"]))["questions"][0]["gap_lines"], 48)

    def test_cut_line_contract_covers_all_three_modes_and_the_label_flag(self):
        with tempfile.TemporaryDirectory() as vault:
            board = self._board(vault)
            self.assertEqual(_data(export_board_html(vault, board["id"]))["meta"]["print"]["cut_line"], "dash")
            for value in ("none", "dash", "solid"):
                update_board(vault, board["id"], print={"cut_line": value})
                self.assertEqual(_data(export_board_html(vault, board["id"]))["meta"]["print"]["cut_line"], value)
            update_board(vault, board["id"], print={"cut_line": "斜线"})       # 未知值回默认
            meta = _data(export_board_html(vault, board["id"]))["meta"]["print"]
            self.assertEqual(meta["cut_line"], "dash")
            self.assertIs(meta["cut_label"], False)
            update_board(vault, board["id"], print={"cut_label": True})
            self.assertIs(_data(export_board_html(vault, board["id"]))["meta"]["print"]["cut_label"], True)

    def test_incremental_export_keeps_paper_geometry_but_follows_current_display_flags(self):
        with tempfile.TemporaryDirectory() as vault:
            from omrs.boards import add_items, record_printed
            board = self._board(vault, ("先印的题",))
            detail = get_board(vault, board["id"])
            record_printed(vault, board["id"], "all", {
                "pages": 1, "cursor": {"page": 1, "y": 200.0},
                "items": [{"question_id": detail["items"][0]["question_id"], "uid": detail["items"][0]["uid"],
                           "segments": [{"page": 1, "top": 0.0, "height": 120.0}]}],
                "answer_pages": [],
            })
            later = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="后加的题")
            add_items(vault, board["id"], [later["uid"]])
            # 改掉几何 + 显示项，再看仅新增导出取哪一份
            update_board(vault, board["id"], print={
                "note_ratio": 0.55, "gap_lines": 20,
                "cut_line": "solid", "cut_label": True, "answers": "append",
            })
            settings = _data(export_board_html(vault, board["id"], mode="new"))["meta"]["print"]
            self.assertEqual((settings["note_ratio"], settings["gap_lines"]),
                             (0.5, 2))                                          # 几何沿用纸面
            self.assertEqual((settings["cut_line"], settings["cut_label"], settings["answers"]),
                             ("solid", True, "append"))                        # 显示项跟随当前
