"""隔离 HTTP + Chromium：真实预览、记录、锁定加题与新增打印栏宽一致。

运行 python3 -B -m unittest tests.smoke_board_print_geometry，需要 Playwright/Chromium。
"""
import copy
import socketserver
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright

from omrs.boards import create_board, get_board, update_board
from omrs.creation import create_question
from omrs.server import OMRSHandler


class BoardPrintGeometrySmokeTest(unittest.TestCase):
    def test_recorded_geometry_matches_preview_and_incremental_export(self):
        class Handler(OMRSHandler):
            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as vault, sync_playwright() as pw:
            first = create_question(vault, subject="数学", category="代数", difficulty=5,
                                    question_text="已打印的题 $a+b$。" * 12)
            new = create_question(vault, subject="数学", category="代数", difficulty=5,
                                  question_text="新增的题 $c+d$。" * 12)
            board = create_board(vault, "栏宽回归", [first["uid"]])
            bid = board["id"]
            update_board(vault, bid, print={"note_ratio": .42})
            Handler.vault_path = vault
            server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            errors = []
            context.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
            base = f"http://127.0.0.1:{server.server_address[1]}"

            def width(view):
                return view.locator(".page .col").first.evaluate("e => parseFloat(getComputedStyle(e).width)")

            def preview(page, mode):
                page.wait_for_function("mode => boardPreviewIsReady() && boardPreviewLayout()?.mode === mode", arg=mode)
                return page.locator(".bd-preview-frame").element_handle().content_frame()

            try:
                page = context.new_page()
                page.goto(base)
                page.evaluate("async id => { switchTab('board'); await boardReloadData(); await boardLoad(id); }", bid)
                full = preview(page, "all")
                # 实时预览先变为 50%，磁盘仍是 42%；记录必须跟随实测布局。
                page.evaluate("() => boardPreviewRelayout({...BOARD_DETAIL.print, note_ratio: .5}, {})")
                page.wait_for_function("() => boardPreviewLayout()?.print?.note_ratio === .5")
                full_width = width(full)
                self.assertAlmostEqual(full_width, 347.05, delta=.02)
                self.assertEqual(get_board(vault, bid)["print"]["note_ratio"], .42)
                # 使用页面真实的记录按钮，仅替代人对已打印的确认；无物理打印机。
                page.evaluate("() => { window.uiConfirm = async () => true; boardMarkAwaiting('all'); }")
                page.locator("[data-board-primary]").click()
                page.wait_for_function("() => BOARD_DETAIL.printed_summary.count === 1")
                paper = copy.deepcopy(get_board(vault, bid)["printed"])
                self.assertEqual(paper["print"]["note_ratio"], .5)
                page.evaluate("async () => { await boardApplyPrintField('note_ratio', 50); await boardFlushSave(); await boardApplyPrintField('locked', true); await boardFlushSave(); }")
                page.evaluate("async args => boardAddToBoard(args.id, [args.uid], {silent: true})", {"id": bid, "uid": new["uid"]})
                self.assertEqual(get_board(vault, bid)["printed"], paper)
                page.locator('[data-board-mode="new"]').click()
                inc = preview(page, "new")
                self.assertEqual(width(inc), full_width)
                page.evaluate("async uid => { await boardSetItemGap(uid, 5); await boardFlushSave(); }", new["uid"])
                page.wait_for_function("() => boardPreviewLayout()?.items?.length === 1")
                self.assertEqual(width(inc), full_width)
                with page.expect_popup() as opened:
                    page.locator("[data-board-primary]").click()
                popup = opened.value
                popup.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
                self.assertEqual(width(popup), full_width)
                popup.emulate_media(media="print")
                self.assertEqual(width(popup), full_width)
                layout = popup.evaluate("window.OMRS_LAYOUT")
                self.assertEqual(layout["print"]["note_ratio"], .5)
                self.assertEqual(layout["items"][0]["idx"], 2)
                self.assertAlmostEqual(layout["items"][0]["segments"][0]["top"], paper["cursor"]["y"], delta=1)

                # 未锁定、当前比例与纸面不同：实时重排/刷新/导出都必须仍用纸面宽度。
                page.evaluate("async () => { boardClearAwaiting(); await boardApplyPrintField('locked', false); await boardFlushSave(); await boardApplyPrintField('note_ratio', 42); await boardFlushSave(); }")
                page.wait_for_timeout(250)  # 120ms relayout 去抖已完成
                self.assertEqual(width(inc), full_width)
                self.assertEqual(page.evaluate("boardPreviewLayout().print.note_ratio"), .5)
                self.assertEqual(get_board(vault, bid)["print"]["note_ratio"], .42)
                page.reload()
                page.evaluate("async id => { switchTab('board'); await boardReloadData(); await boardLoad(id); }", bid)
                page.locator('[data-board-mode="new"]').click()
                inc = preview(page, "new")
                self.assertEqual(width(inc), full_width)
                page.evaluate("async uid => { await boardSetItemGap(uid, 7); await boardFlushSave(); }", new["uid"])
                page.wait_for_timeout(250)
                self.assertEqual(width(inc), full_width)
                self.assertEqual(get_board(vault, bid)["printed"], paper)
                self.assertEqual(errors, [])
                print(f"HTTP/Chromium: all/new/print/reload width={full_width}px, snapshot=50%, no page errors")
            finally:
                context.close()
                browser.close()
                server.shutdown()
                server.server_close()
                thread.join()
