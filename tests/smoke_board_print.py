"""展示板打印引擎冒烟测试（需要 playwright + Chromium；缺失时自动跳过）。

真实链路：建库 → 建板 → 导出 HTML → 无头浏览器排版 → 断言页数 / 无溢出 / KaTeX /
长图切片续排 → 记录纸面 → 加题 → 增量导出：新题从原纸 cursor 处续排、页码绝对。
运行：python -m unittest tests.smoke_board_print
"""
import base64
import json
import os
import struct
import tempfile
import unittest
import zlib

from omrs.boards import add_items, create_board, get_board, record_printed
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


def _tall_figure(width=600, height=1600):
    def pix(x, y):
        inside = 30 < x < width - 30 and (y % 80) < 55
        return (20, 20, 20) if inside and ((x // 10) + (y // 5)) % 3 else (255, 255, 255)
    return _png(width, height, pix)


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
            self.assertTrue(first["partial"] and first["ghost"])
            self.assertEqual(first["page"], before["cursor"]["page"])
            top = layout2["items"][0]["segments"][0]["top"]
            self.assertAlmostEqual(top, before["cursor"]["y"], delta=1.0)
            self.assertTrue(all(d["overflow"] <= 0.5 for d in diag2), diag2)
            self.assertGreaterEqual(layout2["pages"], before["pages"])
            self.assertTrue(all(n == before["cursor"]["page"] or n > before["pages"] for n in layout2["page_numbers"]))
            after = record_printed(vault, board["id"], "new", layout2)["printed_summary"]
            self.assertEqual(after["count"], 6)
            self.assertEqual(after["new_count"], 0)
            browser.close()


if __name__ == "__main__":
    unittest.main()
