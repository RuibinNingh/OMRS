"""展示板打印引擎冒烟测试（需要 playwright + Chromium；缺失时自动跳过）。

真实链路：建库 → 建板 → 导出 HTML → 无头浏览器排版 → 断言页数 / 无溢出 / KaTeX /
长图切片续排 → 记录纸面 → 加题 → 增量导出：新题从原纸 cursor 处续排、页码绝对。
第二个用例用一块短板保证「原纸空白处续排」（占位页）这条分支一定走到；第一个用例里
最后一页是否排满取决于字体，占位页按设计可能被丢弃，所以那里按 cursor.y 条件断言。
运行：python -m unittest tests.smoke_board_print
"""
import base64
import json
import os
import struct
import tempfile
import unittest
import zlib

from omrs.boards import add_items, create_board, get_board, record_printed, update_board
from omrs.creation import create_question
from omrs.exporting import export_board_html

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None


def _png(width, height, pix):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pix(x, y))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _tall_figure(width=600, height=1600, band=80, gap=25):
    """条纹长图：每 band 行有 (band-gap) 行墨、gap 行空白缝，供切片找白缝。"""
    def pix(x, y):
        inside = 30 < x < width - 30 and (y % band) < band - gap
        return (20, 20, 20) if inside and ((x // 10) + (y // 5)) % 3 else (255, 255, 255)
    return _png(width, height, pix)


# 与浏览器模板 board.js 一致的栏高：A4 297mm - 上下 12mm - 页脚安全带 8.5mm - 页眉 39px
_MM = 3.779528
COL_H = 297 * _MM - 2 * 12 * _MM - 8.5 * _MM - 39


DIAG_JS = """() => [...document.querySelectorAll('.page')].map(p => {
  const col = p.querySelector('.col'); const r = col.getBoundingClientRect();
  const kids = [...col.querySelectorAll('.blk,.slice')];
  const bottom = Math.max(0, ...kids.map(k => k.getBoundingClientRect().bottom));
  return {page: Number(p.dataset.page), partial: p.classList.contains('partial'),
          overflow: bottom - r.bottom, katex: p.querySelectorAll('.katex').length,
          cont: p.querySelectorAll('.q-head.cont').length, ghost: !!col.querySelector('.ghost')};
})"""


@unittest.skipIf(sync_playwright is None, "playwright 未安装")
class BoardPrintSmokeTest(unittest.TestCase):
    def _render(self, browser, html):
        with tempfile.NamedTemporaryFile("wb", suffix=".html", delete=False) as fh:
            fh.write(html)
            path = fh.name
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("file://" + path)
        page.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'", timeout=30000)
        layout = page.evaluate("window.OMRS_LAYOUT")
        diag = page.evaluate(DIAG_JS)
        page.close()
        os.unlink(path)
        self.assertEqual(errors, [])
        return layout, diag

    def test_full_then_incremental_print(self):
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            image = "data:image/png;base64," + base64.b64encode(_tall_figure()).decode("ascii")
            uids = []
            for i in range(1, 5):
                uids.append(create_question(
                    vault, subject="数学", category="代数", difficulty=5,
                    question_text=f"第 {i} 题 $\\dfrac{{{i}}}{{{i + 1}}}$\n" + "叙述文字。" * 20,
                    answer_text=f"答案 {i}",
                )["uid"])
            uids.append(create_question(
                vault, subject="物理", category="电学", difficulty=8, question_text="长图题",
                question_images=[{"data": image, "name": "tall.png"}],
            )["uid"])
            board = create_board(vault, "冒烟板", uids)

            layout, diag = self._render(browser, export_board_html(vault, board["id"], mode="all"))
            self.assertGreaterEqual(layout["pages"], 2)
            self.assertEqual(layout["page_numbers"], list(range(1, layout["pages"] + 1)))
            self.assertTrue(all(d["overflow"] <= 0.5 for d in diag), diag)
            self.assertTrue(any(d["katex"] > 0 for d in diag))
            self.assertTrue(any(d["cont"] > 0 for d in diag), "长图跨页应有（续）题头")
            self.assertEqual(len(layout["items"]), 5)
            self.assertEqual(layout["warnings"], [])
            record_printed(vault, board["id"], "all", layout)
            before = get_board(vault, board["id"])["printed_summary"]

            new_uid = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="新增题 $y=x$")["uid"]
            add_items(vault, board["id"], [new_uid])
            layout2, diag2 = self._render(browser, export_board_html(vault, board["id"], mode="new"))
            self.assertEqual(layout2["mode"], "new")
            self.assertEqual(len(layout2["items"]), 1)
            self.assertEqual(layout2["items"][0]["idx"], 6)
            first = diag2[0]
            if before["cursor"]["y"] < COL_H - 60:
                # 原纸还有空：第一页是占位页，新题顶在 cursor 处
                self.assertTrue(first["partial"] and first["ghost"], diag2)
                self.assertEqual(first["page"], before["cursor"]["page"])
                top = layout2["items"][0]["segments"][0]["top"]
                self.assertAlmostEqual(top, before["cursor"]["y"], delta=1.0)
            else:
                # 原纸已排满：占位页被丢弃，新题直接从新页开始（页码仍是绝对页码）
                self.assertFalse(first["partial"] or first["ghost"], diag2)
                self.assertEqual(first["page"], before["pages"] + 1)
            self.assertTrue(all(d["overflow"] <= 0.5 for d in diag2), diag2)
            self.assertGreaterEqual(layout2["pages"], before["pages"])
            self.assertTrue(all(n == before["cursor"]["page"] or n > before["pages"] for n in layout2["page_numbers"]))
            after = record_printed(vault, board["id"], "new", layout2)["printed_summary"]
            self.assertEqual(after["count"], 6)
            self.assertEqual(after["new_count"], 0)
            browser.close()

    def test_incremental_print_continues_on_partial_page(self):
        """短板：第一次只印一道短题，纸上大片空白 → 补印必须走占位页，新题顶在 cursor 处。"""
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            first_uid = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="第一题 $a+b$")["uid"]
            board = create_board(vault, "短板", [first_uid])
            layout, diag = self._render(browser, export_board_html(vault, board["id"], mode="all"))
            self.assertEqual(layout["pages"], 1)
            self.assertLess(layout["cursor"]["y"], COL_H / 2)
            record_printed(vault, board["id"], "all", layout)
            before = get_board(vault, board["id"])["printed_summary"]

            new_uid = create_question(vault, subject="数学", category="代数", difficulty=5, question_text="第二题 $c+d$\n" + "补印。" * 30)["uid"]
            add_items(vault, board["id"], [new_uid])
            layout2, diag2 = self._render(browser, export_board_html(vault, board["id"], mode="new"))
            self.assertEqual(layout2["page_numbers"], [1])
            self.assertEqual(layout2["partial_page"], 1)
            self.assertTrue(diag2[0]["partial"] and diag2[0]["ghost"], diag2)
            top = layout2["items"][0]["segments"][0]["top"]
            self.assertAlmostEqual(top, before["cursor"]["y"], delta=1.0)
            self.assertGreater(layout2["cursor"]["y"], before["cursor"]["y"])
            self.assertTrue(all(d["overflow"] <= 0.5 for d in diag2), diag2)
            after = record_printed(vault, board["id"], "new", layout2)["printed_summary"]
            self.assertEqual((after["count"], after["pages"], after["new_count"]), (2, 1, 0))
            browser.close()

    def test_wide_photo_is_sliced_via_downscaled_analysis(self):
        """宽于 600px 的长图走缩图分析：仍能沿白缝切片、跨页续排、不溢出，且一趟排版就绪。"""
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            image = "data:image/png;base64," + base64.b64encode(_tall_figure(width=1400, height=4200, band=160, gap=50)).decode("ascii")
            uid = create_question(vault, subject="物理", category="力学", difficulty=6, question_text="宽长图题",
                                  question_images=[{"data": image, "name": "wide.png"}])["uid"]
            board = create_board(vault, "宽图板", [uid])
            layout, diag = self._render(browser, export_board_html(vault, board["id"], mode="all"))
            self.assertGreaterEqual(layout["pages"], 2)
            self.assertTrue(all(d["overflow"] <= 0.5 for d in diag), diag)
            self.assertTrue(any(d["cont"] > 0 for d in diag), "长图跨页应有（续）题头")
            self.assertEqual(layout["warnings"], [])            # 缩图后仍能找到白缝，没有被迫硬切
            self.assertEqual(len(layout["items"]), 1)
            self.assertEqual(len(layout["items"][0]["segments"]), layout["pages"])
            browser.close()


CUT_JS = """() => [...document.querySelectorAll('.page')].map(p => {
  const inner = p.querySelector('.page-inner');
  const ir = inner.getBoundingClientRect();
  return {page: Number(p.dataset.page), answer: p.classList.contains('answer-page'),
          cuts: [...inner.querySelectorAll('.cut-line')].map(c => {
            const r = c.getBoundingClientRect();
            return {top: Math.round((r.top - ir.top) * 100) / 100, width: Math.round(r.width * 100) / 100,
                    solid: getComputedStyle(c).borderTopStyle, visible: r.height >= 0 && getComputedStyle(c).display !== 'none',
                    tag: (c.querySelector('.tag') || {}).textContent || ''};
          })};
})"""

_MARGIN_R_PX = 10 * _MM


@unittest.skipIf(sync_playwright is None, "playwright 未安装")
class BoardCutLineSmokeTest(unittest.TestCase):
    """切割线是纸面上「这道题写到这里为止」的提示，只能靠真实排版验收。"""

    def _cuts(self, browser, html):
        with tempfile.NamedTemporaryFile("wb", suffix=".html", delete=False) as fh:
            fh.write(html)
            path = fh.name
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("file://" + path)
        page.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'", timeout=30000)
        layout = page.evaluate("window.OMRS_LAYOUT")
        pages = page.evaluate(CUT_JS)
        page.close()
        os.unlink(path)
        self.assertEqual(errors, [])
        return layout, pages

    def _board(self, vault, count=4):
        uids = [create_question(vault, subject="数学", category="代数", difficulty=5,
                                question_text=f"第 {i} 题\n" + "叙述。" * 12,
                                answer_text=f"答案 {i}")["uid"] for i in range(1, count + 1)]
        board = create_board(vault, "切割线板", uids)
        update_board(vault, board["id"], print={"gap_lines": 4})
        return board

    def test_dash_draws_one_line_per_question_gap_at_full_content_width(self):
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            board = self._board(vault, count=4)
            layout, pages = self._cuts(browser, export_board_html(vault, board["id"], mode="all"))
            cuts = [cut for page in pages for cut in page["cuts"]]
            self.assertTrue(cuts, "dash 模式下应画出切割线")
            # 每题留白末尾至多一条；贴页底 / 顶到新页顶部的那条按设计不画，所以是「≤ 题数」
            self.assertLessEqual(len(cuts), 4)
            content_w = round(210 * _MM - 2 * _MARGIN_R_PX, 2)
            for cut in cuts:
                self.assertAlmostEqual(cut["width"], content_w, delta=1.0)      # 题栏 + 间距 + 留白区，全宽
                self.assertEqual(cut["solid"], "dashed")
                self.assertEqual(cut["tag"], "")                                # 默认不标「第 N 题止」
                self.assertGreater(cut["top"], 0)
            browser.close()

    def test_none_removes_every_cut_line_from_the_dom(self):
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            board = self._board(vault, count=4)
            update_board(vault, board["id"], print={"cut_line": "none"})
            _, pages = self._cuts(browser, export_board_html(vault, board["id"], mode="all"))
            self.assertEqual([cut for page in pages for cut in page["cuts"]], [])

    def test_solid_with_label_shows_the_question_number_and_a_solid_rule(self):
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            board = self._board(vault, count=4)
            update_board(vault, board["id"], print={"cut_line": "solid", "cut_label": True})
            _, pages = self._cuts(browser, export_board_html(vault, board["id"], mode="all"))
            cuts = [cut for page in pages for cut in page["cuts"]]
            self.assertTrue(cuts)
            for cut in cuts:
                self.assertEqual(cut["solid"], "solid")
                self.assertRegex(cut["tag"], r"^第 \d+ 题止$")

    def test_answer_pages_never_carry_question_cut_lines(self):
        with tempfile.TemporaryDirectory() as vault, sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # pragma: no cover
                self.skipTest(f"Chromium 不可用: {exc}")
            board = self._board(vault, count=4)
            update_board(vault, board["id"], print={"answers": "append", "cut_line": "solid"})
            layout, pages = self._cuts(browser, export_board_html(vault, board["id"], mode="all"))
            answer_pages = set(layout.get("answer_pages") or [])
            self.assertTrue(answer_pages, "附答案模式应产出答案页")
            for page in pages:
                if page["page"] in answer_pages:
                    self.assertEqual(page["cuts"], [], f"答案页 {page['page']} 不应有题目切割线")
            browser.close()


if __name__ == "__main__":
    unittest.main()
