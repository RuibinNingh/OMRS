"""A4 导出的真实 Chromium/PDF 回归，仅使用合成题目。"""
from pathlib import Path
import re
import tempfile
import unittest

from playwright.sync_api import sync_playwright

from omrs.boards import create_board
from omrs.creation import create_question
from omrs.exporting import _build_html, _text_to_blocks, export_board_html
from tests.browser_runtime import launch_chromium


DIAGNOSTICS = """() => ({
  overflow: [...document.querySelectorAll('.col')].flatMap(col => {
    const bottom = col.getBoundingClientRect().bottom;
    return [...col.children].filter(node => node.getBoundingClientRect().bottom > bottom + .03)
      .map(node => ({text: node.textContent.slice(0, 40), excess: node.getBoundingClientRect().bottom - bottom}));
  }),
  fonts: [...document.fonts].filter(font => font.family.includes('OMRS Print')).map(font => font.status),
  heads: [...document.querySelectorAll('.q-head .no')].map(node => node.textContent),
  options: [...document.querySelectorAll('.q-text')].map(node => node.textContent).filter(text => /^D_MARK_/.test(text)),
  katex: document.querySelectorAll('.katex').length
})"""
PLACEMENT = "JSON.stringify([...document.querySelectorAll('.col')].map(col => [...col.children].map(node => node.textContent)))"


def fixture(two_columns=True):
    questions = []
    for idx in range(1, 25):
        questions.append({
            "idx": idx, "uid": f"synthetic-{idx}", "subject": "化学", "category": "离子反应",
            "difficulty": 5, "tags": "合成打印夹具，溶液与离子方程式", "labels": [], "notes": {},
            "blocks": [{"t": "txt", "text": "请判断下列反应。" + "结合溶液性质分析实验现象。" * 8},
                       {"t": "txt", "text": r"$H^+ + OH^- = H_2O$，选择正确的离子方程式。"},
                       *[{"t": "txt", "text": f"{option}_MARK_{idx}：合成选项。"} for option in "ABCD"]],
        })
    return {"meta": {"title": "A4 打印回归", "a4_two_columns": two_columns, "question_gap_lines": 1},
            "questions": questions, "answers": [], "feedback": []}


class A4PrintSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = sync_playwright().start()
        cls.browser = launch_chromium(cls.runtime)

    @classmethod
    def tearDownClass(cls):
        # CDP 模式只关闭自己创建的上下文。
        cls.runtime.stop()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="omrs-a4-test-")
        self.context = self.browser.new_context(viewport={"width": 1000, "height": 1000})
        self.page = self.context.new_page()
        self.errors, self.network = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda req: self.network.append(req.url) if req.url.startswith(("http:", "https:")) else None)

    def tearDown(self):
        self.context.close()
        self.folder.cleanup()

    def load(self, data):
        # 显式 screen 模拟会让 Chromium 连 PDF 也采用屏幕的工具栏/页间距。
        # 清除上个子用例的模拟，恢复浏览器正常的打印媒体切换。
        self.page.emulate_media(media=None)
        path = Path(self.folder.name) / "export.html"
        path.write_text(_build_html(data, "a4"), encoding="utf-8")
        self.page.goto(path.as_uri())
        self.page.wait_for_function("window.__OMRS_RESULT?.errors?.length || !document.getElementById('btnPrint').disabled")

    def assert_complete(self):
        result = self.page.evaluate("window.__OMRS_RESULT")
        diag = self.page.evaluate(DIAGNOSTICS)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(diag["overflow"], [])
        self.assertEqual(diag["heads"], [f"第 {idx} 题" for idx in range(1, 25)])
        self.assertEqual(diag["options"], [f"D_MARK_{idx}：合成选项。" for idx in range(1, 25)])
        self.assertGreater(diag["katex"], 0)
        self.assertIn("loaded", diag["fonts"])
        self.assertNotIn("error", diag["fonts"])
        self.assertEqual(self.errors, [])
        self.assertEqual(self.network, [])
        return result["pages"]

    def test_double_column_offline_pdf_and_print_metric_change(self):
        self.check_column_mode(True)

    def test_single_column_offline_pdf_and_print_metric_change(self):
        self.check_column_mode(False)

    def check_column_mode(self, two_columns):
        self.load(fixture(two_columns))
        initial = self.assert_complete()
        pdf = self.page.pdf(prefer_css_page_size=True, print_background=True)
        self.assertEqual(len(re.findall(rb"/Type /Page\b", pdf)), initial)
        self.assertEqual(self.assert_complete(), initial)
        placement = self.page.evaluate(PLACEMENT)
        self.page.add_style_tag(content="@media print{.q-head .meta{line-height:34px}.q-head .tags{line-height:30px}}")
        self.page.emulate_media(media="print")
        self.page.wait_for_function("old => " + PLACEMENT + " !== old", arg=placement)
        # 额外行高必须触发重新分页，所有 D 选项仍保留并且没有栏底溢出。
        printed = self.assert_complete()
        self.assertGreaterEqual(printed, initial)
        pdf = self.page.pdf(prefer_css_page_size=True)
        self.assertEqual(len(re.findall(rb"/Type /Page\b", pdf)), printed)
        self.page.emulate_media(media="screen")
        self.page.wait_for_function("old => " + PLACEMENT + " === old", arg=placement)
        self.assertEqual(self.assert_complete(), initial)


    def test_resize_revalidates_changed_geometry(self):
        self.load(fixture())
        initial = self.assert_complete()
        placement = self.page.evaluate(PLACEMENT)
        self.page.add_style_tag(content=".q-head .meta{line-height:40px}.q-head .tags{line-height:35px}")
        self.page.set_viewport_size({"width": 780, "height": 900})
        self.page.wait_for_function("old => " + PLACEMENT + " !== old", arg=placement)
        self.assertGreaterEqual(self.assert_complete(), initial)

    def test_tables_keep_every_column_visible_in_screen_and_print(self):
        """多列表格不能把末列挤成零宽、逐字换行后撑高整表。"""
        headers = ["时刻", "A 球位移 $s_A$", "B 球净下降位移 $s_B$",
                   "相对追回距离 $s_A-s_B$", "B 球状态", "说明"]
        rows = [[f"${n}t$", f"${n*n}h$", "$h$" if n % 2 else "$0$",
                 f"${n*n-n%2}h$", "落地、反弹" if n % 2 else "最高点", "合成数据"]
                for n in range(9)]
        for mode in ("a4-double", "a4-single", "board"):
            for columns in range(1, 7):
                with self.subTest(mode=mode, columns=columns):
                    source = "\n".join("| " + " | ".join(row[:columns]) + " |"
                                       for row in [headers, ["---"] * len(headers), *rows])
                    if mode == "board":
                        with tempfile.TemporaryDirectory(prefix="omrs-table-vault-") as vault:
                            question = create_question(vault, subject="物理", category="合成测试", difficulty=5,
                                                       question_text=source, answer_text=source)
                            board = create_board(vault, "表格回归", [question["uid"]])
                            html = export_board_html(vault, board["id"], include_answers=True)
                        path = Path(self.folder.name) / "board.html"
                        path.write_bytes(html)
                        self.page.emulate_media(media=None)
                        self.page.goto(path.as_uri())
                        self.page.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
                        self.assertEqual(self.page.evaluate("window.OMRS_LAYOUT.warnings"), [])
                    else:
                        data = fixture(mode == "a4-double")
                        question = {**data["questions"][0], "blocks": _text_to_blocks(self.folder.name, source)}
                        data.update(questions=[question], answers=[question])
                        self.load(data)
                        self.assertEqual(self.page.evaluate("window.__OMRS_RESULT.errors"), [])
                    for media in ("screen", "print"):
                        self.page.emulate_media(media=media)
                        tables = self.page.evaluate("""() => [...document.querySelectorAll('.md-table')].map(table => {
                          const wrap = table.parentElement.getBoundingClientRect();
                          return {height: table.getBoundingClientRect().height,
                            rows: [...table.rows].map(row => [...row.cells].map(cell => {
                              const r = cell.getBoundingClientRect();
                              return {width: r.width, clipped: r.left < wrap.left - 1 || r.right > wrap.right + 1,
                                overflow: cell.scrollWidth > cell.clientWidth + 1};
                            }))};
                        })""")
                        self.assertEqual(len(tables), 2, media)
                        for table in tables:
                            self.assertLess(table["height"], 300, (media, table))
                            self.assertEqual(len(table["rows"]), 10)
                            for cells in table["rows"]:
                                self.assertEqual(len(cells), columns)
                                for cell in cells:
                                    self.assertGreater(cell["width"], 20, (media, cell))
                                    self.assertFalse(cell["clipped"] or cell["overflow"], (media, cell))
                    self.assertEqual(self.errors, [])
                    self.assertEqual(self.network, [])

    def test_oversized_formula_reports_failure_instead_of_clipping(self):
        data = fixture()
        data["questions"][0]["blocks"] = [{"t": "txt", "text": r"$$\rule{1em}{1300px}$$"}]
        self.load(data)
        result = self.page.evaluate("window.__OMRS_RESULT")
        self.assertEqual(result["pages"], 0)
        self.assertIn("超出 A4 栏高", result["errors"][0])
        self.assertTrue(self.page.locator("#btnPrint").is_disabled())
        self.assertEqual(self.page.locator(".page").count(), 0)
        self.page.emulate_media(media="print")
        self.assertTrue(self.page.locator(".layout-error").is_visible())

    def test_keyboard_print_while_loading_shows_pending_message(self):
        self.page.add_init_script("window.requestAnimationFrame = callback => window.__resumeFrame = callback")
        path = Path(self.folder.name) / "loading.html"
        path.write_text(_build_html(fixture(), "a4"), encoding="utf-8")
        self.page.goto(path.as_uri())
        self.assertTrue(self.page.locator("#btnPrint").is_disabled())
        self.page.emulate_media(media="print")
        self.page.wait_for_function("document.body.classList.contains('print-pending')", polling=50)
        text = self.page.evaluate("getComputedStyle(document.body, '::before').content")
        self.assertIn("等待页面排版完成", text)
        self.assertEqual(self.page.locator(".page:visible").count(), 0)


if __name__ == "__main__":
    unittest.main()
