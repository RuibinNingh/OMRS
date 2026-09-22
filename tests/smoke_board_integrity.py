"""展示板异步完整性：真实 HTTP/Chromium 覆盖保存、导出、记录、撤销和切板。

运行：python3 -B -m unittest tests.smoke_board_integrity
所有写操作均在独立临时题库；延迟只作用于真实 HTTP 响应，不伪造业务数据。
"""
import socketserver
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright

from omrs.boards import create_board, get_board
from omrs.creation import create_question
from omrs.server import OMRSHandler


class BoardIntegritySmokeTest(unittest.TestCase):
    def setUp(self):
        class Handler(OMRSHandler):
            def log_message(self, *args):
                pass

        self.temp = tempfile.TemporaryDirectory(prefix="omrs-board-integrity-")
        self.vault = self.temp.name
        self.first = create_question(self.vault, subject="数学", category="审查", difficulty=5,
                                     question_text="问题甲 $a+b$。" * 8, answer_text="答案甲 $a+b=2$。")
        self.second = create_question(self.vault, subject="数学", category="审查", difficulty=5,
                                      question_text="问题乙 $c+d$。" * 8, answer_text="答案乙 $c+d=4$。")
        Handler.vault_path = self.vault
        self.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.errors = []
        self.context.on("page", lambda page: page.on("pageerror", lambda error: self.errors.append(str(error))))

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self.pw.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def board(self, name="测试板", uids=None):
        return create_board(self.vault, name, uids or [self.first["uid"]])["id"]

    def open_board(self, bid):
        page = self.context.new_page()
        page.goto(self.base)
        page.evaluate("""async id => {
            switchTab('board'); await boardReloadData(); await boardLoad(id); boardSetView('paper');
            window.uiConfirm = async () => true;
        }""", bid)
        self.wait_preview(page, bid)
        return page

    def wait_preview(self, page, bid):
        page.wait_for_function("""id => boardPreviewIsReady() && boardPreviewLayout()?.board_id === id
            && BP_FRAME?.contentDocument?.body?.classList.contains('embedded')""", arg=bid)

    def popup(self, page):
        with page.expect_popup() as opened:
            page.evaluate("() => { window.__exporting = boardPrintPreview(); }")
        popup = opened.value
        popup.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
        return popup

    def test_content_settings_refresh_preview_and_record_answers(self):
        from omrs.labels import save_label
        from omrs.question_ops import set_question_labels
        save_label(self.vault, name="测试标记")
        set_question_labels(self.vault, self.first["uid"], ["测试标记"])
        bid = self.board()
        page = self.open_board(bid)
        page.locator('[data-board-seg="answers"] [data-value="append"]').click()
        page.wait_for_function("boardPreviewLayout()?.answer_pages?.length === 1")
        self.assertEqual(page.evaluate("boardPreviewLayout().pages"), 2)
        # 同样受服务端内容裁剪影响的标记开关，往返切换均应生效。
        for shown in (False, True):
            page.locator('[data-board-print="show_labels"]').set_checked(shown)
            page.wait_for_function("""shown => boardPreviewIsReady()
                && BP_FRAME.contentWindow.OMRS_DATA.meta.print.show_labels === shown
                && !!BP_FRAME.contentDocument.querySelector('.lbl') === shown""", arg=shown)
        popup = self.popup(page)
        exported = popup.evaluate("OMRS_LAYOUT")
        page.locator('[data-board-primary]').click()
        page.wait_for_function("BOARD_DETAIL.printed.pages === 2")
        paper = get_board(self.vault, bid)["printed"]
        self.assertEqual(paper["answer_pages"], exported["answer_pages"])
        self.assertEqual(paper["answer_pages"], [2])
        page.locator('[data-board-seg="answers"] [data-value="none"]').click()
        page.wait_for_function("boardPreviewLayout()?.pages === 1 && !boardPreviewLayout()?.answer_pages.length")

    def test_save_response_preserves_later_edits_and_switch_waits(self):
        bid, other = self.board(), self.board("另一板")
        page = self.open_board(bid)
        page.evaluate("""() => {
            const original = window.fetch; let n = 0;
            window.fetch = async (...args) => {
                const response = await original(...args);
                if (args[0] === '/api/board/update' && ++n === 1) {
                    window.__firstSaved = true;
                    await new Promise(resolve => setTimeout(resolve, 350));
                }
                return response;
            };
        }""")
        page.evaluate("async () => { await boardApplyPrintField('note_ratio', 42); window.__saving = boardFlushSave(); }")
        page.wait_for_function("window.__firstSaved")
        page.evaluate("async () => { await boardApplyPrintField('note_ratio', 54); await boardFlushSave(); }")
        page.wait_for_function("boardPreviewLayout()?.print.note_ratio === .54")
        self.assertEqual(get_board(self.vault, bid)["print"]["note_ratio"], .54)
        self.assertEqual(page.evaluate("BOARD_DETAIL.print.note_ratio"), .54)
        page.evaluate("async id => { await boardApplyPrintField('gap_lines', 7); await boardLoad(id); }", other)
        self.assertEqual(get_board(self.vault, bid)["print"]["gap_lines"], 7)
        self.assertEqual(get_board(self.vault, other)["print"]["gap_lines"], 2)

    def test_immediate_print_waits_for_save_and_failed_save_stops_export(self):
        bid = self.board()
        page = self.open_board(bid)
        with page.expect_popup() as opened:
            page.evaluate("async () => { await boardApplyPrintField('note_ratio', 42); window.__exporting = boardPrintPreview(); }")
        popup = opened.value
        popup.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
        self.assertEqual(popup.evaluate("OMRS_LAYOUT.print.note_ratio"), .42)
        self.assertEqual(get_board(self.vault, bid)["print"]["note_ratio"], .42)
        # 网络失败不能打印旧数据，也不能带着脏字段切到另一板。
        other = self.board("保存失败时的目标")
        page.route("**/api/board/update", lambda route: route.abort())
        requests = []
        page.on("request", lambda request: requests.append(request.url) if request.url.endswith('/api/export') else None)
        page.evaluate("async id => { await boardApplyPrintField('note_ratio', 54); await boardExportCurrent(false); await boardLoad(id); }", other)
        self.assertEqual(requests, [])
        self.assertEqual(page.evaluate("BOARD_DETAIL.id"), bid)
        self.assertTrue(page.evaluate("!!BOARD_DIRTY?.print"))
        page.unroute("**/api/board/update")
        page.evaluate("async () => boardFlushSave()")
        self.assertEqual(get_board(self.vault, bid)["print"]["note_ratio"], .54)

    def test_switch_during_export_records_original_board_only(self):
        first, second = self.board("甲"), self.board("乙", [self.second["uid"]])
        page = self.open_board(first)
        page.evaluate("""() => {
            const original = window.fetch;
            window.fetch = async (...args) => {
                const response = await original(...args);
                if (args[0] === '/api/export') {
                    window.__exportFetched = true;
                    await new Promise(resolve => setTimeout(resolve, 700));
                }
                return response;
            };
        }""")
        with page.expect_popup() as opened:
            page.evaluate("() => { window.__exporting = boardPrintPreview(); }")
        popup = opened.value
        page.wait_for_function("window.__exportFetched")
        page.evaluate("async id => boardLoad(id)", second)
        popup.wait_for_function("document.documentElement.dataset.omrsLayoutReady === '1'")
        self.assertEqual(popup.evaluate("OMRS_LAYOUT.board_id"), first)
        self.assertEqual(page.evaluate("Array.from(BOARD_WINDOWS.values())[0].boardId"), first)
        popup.locator('#btnDone').click()
        page.wait_for_function("""async id => (await (await fetch('/api/board?id=' + id)).json()).board.printed.pages > 0""", arg=first)
        self.assertEqual(get_board(self.vault, second)["printed"]["pages"], 0)
        self.assertEqual(get_board(self.vault, first)["printed"]["items"][0]["uid"], self.first["uid"])
        # 服务端也拒绝调用方把 A 版面写到 B，且不改变 B 的数据。
        response = self.context.request.post(self.base + '/api/board/printed', data={
            'id': second, 'mode': 'all', 'layout': popup.evaluate('OMRS_LAYOUT')})
        self.assertEqual(response.status, 400)
        self.assertEqual(get_board(self.vault, second)["printed"]["pages"], 0)

    def test_record_keeps_export_snapshot_after_edits_for_popup_and_download(self):
        for download in (False, True):
            with self.subTest(download=download):
                bid = self.board("快照")
                page = self.open_board(bid)
                if download:
                    with page.expect_download():
                        page.evaluate("async () => boardExportCurrent(false)")
                else:
                    popup = self.popup(page)
                    self.assertEqual(popup.evaluate('OMRS_LAYOUT.print.note_ratio'), .5)
                page.evaluate("async () => { await boardApplyPrintField('note_ratio', 42); await boardFlushSave(); }")
                page.wait_for_function("boardPreviewLayout()?.print.note_ratio === .42")
                page.locator('[data-board-primary]').click()
                page.wait_for_function("BOARD_DETAIL.printed.pages > 0")
                self.assertEqual(get_board(self.vault, bid)["printed"]["print"]["note_ratio"], .5)
                page.close()

    def test_direct_add_undo_preserves_existing_references(self):
        bid = self.board()
        page = self.open_board(bid)
        page.evaluate("async ids => boardPickerOpen(ids, {direct: true})", [self.first["uid"], self.second["uid"]])
        self.assertEqual(len(get_board(self.vault, bid)["items"]), 2)
        page.get_by_role('button', name='撤销', exact=True).last.click()
        page.wait_for_function("BOARD_DETAIL.items.length === 1")
        self.assertEqual([item['uid'] for item in get_board(self.vault, bid)['items']], [self.first['uid']])
        # 全部已存在时，不提供可以删除原有引用的撤销动作。
        page.evaluate("async uid => boardPickerOpen([uid], {direct: true})", self.first["uid"])
        self.assertEqual(len(get_board(self.vault, bid)["items"]), 1)

    def test_switch_while_old_document_is_laying_out(self):
        first, second = self.board("旧板"), self.board("新板")
        page = self.open_board(self.board("初始板"))
        page.evaluate("""({first, second}) => {
            const original = window.fetch;
            window.fetch = async (...args) => {
                const response = await original(...args);
                if (args[0] === '/api/export' && JSON.parse(args[1].body).board_id === second)
                    await new Promise(resolve => setTimeout(resolve, 500));
                return response;
            };
            window.__switched = false;
            const timer = setInterval(() => {
                const doc = BP_FRAME?.contentDocument;
                if (doc?.defaultView?.OMRS_DATA?.meta?.board_id === first && doc.documentElement.dataset.omrsLayoutReady !== '1') {
                    clearInterval(timer); window.__switched = true; boardLoad(second);
                }
            }, 1);
            boardLoad(first);
        }""", {"first": first, "second": second})
        page.wait_for_function("window.__switched")
        self.wait_preview(page, second)
        page.wait_for_function("BP_FRAME.contentDocument.getElementById('omrs-view-style')?.textContent.includes('display:none')")
        frame = page.locator('.bd-preview-frame').element_handle().content_frame()
        self.assertEqual(frame.locator('#bar').evaluate('e => getComputedStyle(e).display'), 'none')
        self.assertEqual(frame.evaluate('OMRS_LAYOUT.board_id'), second)
        self.assertEqual(page.evaluate('boardPreviewLayout().board_id'), second)


if __name__ == '__main__':
    unittest.main()
