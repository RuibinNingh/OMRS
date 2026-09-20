"""Real HTTP + Chromium regression of the review workbench using an isolated vault.

Run: python3 -m unittest tests.smoke_schedule_workbench
Set OMRS_TEST_BROWSER to override the installed Chromium executable.
"""
import json
import os
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

from omrs.creation import create_question
from omrs.labels import save_label
from omrs.server import OMRSHandler
from omrs.sessions import get_session, list_sessions


class ScheduleWorkbenchSmokeTests(unittest.TestCase):
    def test_review_flow_filters_exports_feedback_and_failures(self):
        class Handler(OMRSHandler):
            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as vault, sync_playwright() as pw:
            save_label(vault, name="考前")
            save_label(vault, name="易错")
            questions = []
            for index in range(14):
                questions.append(create_question(
                    vault, "数学" if index < 10 else "物理", "代数" if index < 10 else "力学",
                    3 + index % 5, question_text=f"第 {index+1} 道题：计算 $1+1$。", answer_text="$2$",
                    related_tags=["运算" if index < 10 else "受力"],
                    labels=["考前", "易错"] if index < 3 else ["考前"] if index < 6 else []))
            Handler.vault_path = vault
            server = socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever,daemon=True).start()
            executable = os.environ.get('OMRS_TEST_BROWSER') or shutil.which('google-chrome') or shutil.which('chromium')
            browser = pw.chromium.launch(**({'executable_path':executable} if executable else {}),args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Shanghai')
            context.route('https://fonts.googleapis.com/**',lambda route: route.abort())
            errors = []
            page = context.new_page()
            page.on('pageerror',lambda error: errors.append(str(error)))
            base = f'http://127.0.0.1:{server.server_address[1]}'

            def arrange():
                page.locator('[data-tab="schedule"]').click()
                page.locator('#sch-tab-arrange').click()
                page.wait_for_function('!REC_LOADING && REC_DATA_V2 !== null')

            def submit_one():
                page.locator('[data-fb-act="verdict"][data-fb-value="1"]').click()
                page.locator('#fb-submit').click()
                expect(page.locator('#fb-result-modal')).to_have_class('modal-overlay open')
                page.locator('#fb-result-ok').click()
                page.wait_for_function("!document.getElementById('fb-status').textContent.includes('正在刷新')")

            try:
                page.goto(base,wait_until='networkidle')
                arrange()
                page.locator('#sch-tab-arrange').focus()
                page.keyboard.press('ArrowRight')
                expect(page.locator('#sch-plans')).to_be_visible()
                page.keyboard.press('ArrowLeft')
                expect(page.locator('#recommend-panel-v2')).to_be_visible()
                expect(page.locator('.sch-question')).to_have_count(14)
                self.assertEqual(page.locator('#rec-subject-v2 option').count(),3)
                page.locator('#rec-suggest').click()
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 10 题')
                page.locator('#rec-view-gallery').click()
                expect(page.locator('.sch-gallery .sch-question')).to_have_count(14)
                expect(page.locator('.sch-gallery-preview .q-md').first).to_contain_text('计算')
                expect(page.locator('.sch-gallery-preview .katex').first).to_be_visible()
                expect(page.locator('.sch-gallery-preview .q-answer-md')).to_have_count(0)
                page.locator('.sch-gallery .sch-question input').first.uncheck()
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 9 题')
                page.locator('#rec-subject-v2').select_option('物理')
                expect(page.locator('.sch-gallery .sch-question')).to_have_count(4)
                page.locator('#rec-view-list').click()
                expect(page.locator('.sch-gallery-preview')).to_have_count(0)
                expect(page.locator('.sch-question')).to_have_count(4)
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 9 题')
                page.locator('#rec-subject-v2').select_option('')
                page.locator('#rec-view-gallery').click()
                # A failed shared question preview offers a working retry in the gallery.
                uid = page.locator('[data-rec-preview-uid]').first.get_attribute('data-rec-preview-uid')
                page.route('**/api/question?*',lambda r:r.fulfill(status=503,content_type='application/json',body='{"msg":"题面离线"}'))
                page.evaluate('(uid) => qvInvalidate(uid)',uid)
                expect(page.locator('.sch-gallery-preview').first).to_contain_text('重试')
                page.unroute('**/api/question?*')
                page.locator('.sch-gallery-preview').first.get_by_role('button',name='重试').click()
                expect(page.locator('.sch-gallery-preview .q-md').first).to_contain_text('计算')
                gallery_shots = Path(tempfile.gettempdir())/'omrs-schedule-verification'
                gallery_shots.mkdir(exist_ok=True)
                page.screenshot(path=str(gallery_shots/'gallery-desktop.png'),animations='disabled')
                page.set_viewport_size({'width':390,'height':844})
                page.locator('.sch-gallery-preview').first.scroll_into_view_if_needed()
                page.screenshot(path=str(gallery_shots/'gallery-phone.png'),animations='disabled')
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                page.set_viewport_size({'width':1440,'height':1000})
                # The view preference survives refresh; ephemeral selections are deliberately not persisted.
                page.reload(wait_until='networkidle')
                arrange()
                expect(page.locator('#rec-view-gallery')).to_have_attribute('aria-pressed','true')
                expect(page.locator('.sch-gallery .sch-question')).to_have_count(14)
                page.locator('#rec-view-list').click()
                page.locator('#rec-suggest').click()
                # Choosing a subject does not silently discard the existing selection.
                page.locator('#rec-subject-v2').select_option('物理')
                expect(page.locator('.sch-question')).to_have_count(4)
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 10 题')
                expect(page.locator('#rec-hidden-count')).to_contain_text('被筛选隐藏')
                page.locator('#rec-suggest').click()
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 4 题')
                page.locator('#rec-filter-chips button').filter(has_text='清除筛选').click()
                page.locator('#rec-more-filters summary').click()
                # Real label buttons and all/any controls, rather than a direct call of the filter function.
                page.locator('[data-label-filter="rec-v2"][data-label-name="易错"]').click()
                expect(page.locator('.sch-question')).to_have_count(3)
                page.locator('[data-label-filter="rec-v2"][data-label-name="考前"]').click()
                expect(page.locator('.sch-question')).to_have_count(6)
                page.locator('#rec-v2-label-mode').select_option('all')
                expect(page.locator('.sch-question')).to_have_count(3)
                page.locator('#rec-filter-chips button').filter(has_text='清除筛选').click()
                page.locator('#rec-filter-category-v2').select_option('力学')
                expect(page.locator('.sch-question')).to_have_count(4)
                page.locator('#rec-filter-ktag-v2').select_option('运算')
                expect(page.locator('.sch-question')).to_have_count(0)
                expect(page.locator('#rec-unified-list-v2')).to_contain_text('放宽筛选')
                page.locator('#rec-filter-chips button').filter(has_text='清除筛选').click()
                page.locator('#rec-filter-due-v2').select_option('today')
                expect(page.locator('.sch-question')).to_have_count(14)
                page.locator('#rec-filter-mastery-max-v2').fill('0')
                expect(page.locator('.sch-question')).to_have_count(14)
                page.locator('#rec-filter-diff-min-v2').fill('9')
                page.locator('#rec-filter-diff-max-v2').fill('2')
                expect(page.locator('#rec-status-v2')).to_contain_text('下限不能大于上限')
                page.locator('#rec-filter-chips button').filter(has_text='清除筛选').click()
                page.locator('#rec-more-filters summary').click()
                page.locator('#rec-suggest').click()
                # Preview is the shared accessible question view; selection survives closing it.
                page.locator('.sch-question .btn').first.click()
                expect(page.locator('#modal')).to_be_visible()
                page.keyboard.press('Escape')
                # Separate full-library export view and back, without duplicated content.
                page.get_by_role('button',name='全题库导出 ↗').click()
                expect(page.locator('#export-panel')).to_be_visible()
                expect(page.locator('#recommend-panel-v2')).to_be_hidden()
                page.get_by_role('button',name='← 返回复习调度').click()
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 10 题')
                # Snapshot the layout, both themes and a phone viewport.
                screenshot_root = Path(tempfile.gettempdir())/'omrs-schedule-verification'
                screenshot_root.mkdir(exist_ok=True)
                for theme in ('light','dark'):
                    page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                    page.screenshot(path=str(screenshot_root/f'arrange-{theme}.png'),animations='disabled')
                page.set_viewport_size({'width':390,'height':844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                page.screenshot(path=str(screenshot_root/'arrange-phone.png'),animations='disabled')
                self.assertGreater(page.locator('.sch-question-info .sch-meta').first.bounding_box()['width'],50)
                self.assertLess(page.locator('.sch-question').first.bounding_box()['height'],140)
                page.set_viewport_size({'width':1440,'height':1000})
                # Failure preserves selection. Retry then creates exactly one plan despite double invocation.
                page.route('**/api/confirm-schedule',lambda r:r.fulfill(status=400,content_type='application/json',body=json.dumps({'msg':'所选题目已在其他计划中'})))
                page.locator('#rec-confirm').click()
                expect(page.locator('#rec-status-v2')).to_contain_text('选择已保留')
                expect(page.locator('#rec-selected-count-v2')).to_have_text('已选 10 题')
                page.unroute('**/api/confirm-schedule')
                page.evaluate('() => { confirmScheduleV2(); confirmScheduleV2(); }')
                expect(page.locator('#sch-plan-detail')).to_contain_text('共 10 题')
                plans=list_sessions(vault)
                self.assertEqual(len(plans),1)
                sid=plans[0]['session_id']
                self.assertEqual(len(get_session(vault,sid)['items']),10)
                page.reload(wait_until='networkidle')
                page.locator('[data-tab="schedule"]').click()
                page.locator('#sch-tab-plans').click()
                page.locator('.sch-plan').first.click()
                expect(page.locator('#sch-plan-detail')).to_contain_text(sid)
                # Both export variants download real standalone HTML and preserve the plan ID.
                with page.expect_download() as download_info:
                    page.get_by_role('button',name='导出屏幕版',exact=True).click()
                screen_download=download_info.value
                self.assertIn(sid,screen_download.suggested_filename)
                html=Path(screen_download.path()).read_text()
                self.assertIn(sid,html)
                self.assertIn('第 ',html)
                with page.expect_download() as download_info:
                    page.get_by_role('button',name='导出打印版',exact=True).click()
                    page.locator('[data-ui-ok]').click()
                self.assertIn('a4',download_info.value.suggested_filename)
                # Partial feedback through real controls, then return to its updated plan.
                page.get_by_role('button',name='录入结果',exact=True).click()
                expect(page.locator('#fb-session-picker')).to_have_value(sid)
                submit_one()
                page.locator('[data-tab="schedule"]').click()
                expect(page.locator('#sch-plan-detail')).to_contain_text('已录入 1 / 共 10 题')
                page.screenshot(path=str(screenshot_root/'plans-desktop.png'),animations='disabled')
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('#sch-plan-detail')).to_be_visible()
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
                page.screenshot(path=str(screenshot_root/'plan-phone.png'),animations='disabled')
                page.get_by_role('button',name='← 返回计划列表').click()
                expect(page.locator('#sch-plan-list')).to_be_visible()
                expect(page.locator('#sch-plan-detail')).to_be_hidden()
                page.set_viewport_size({'width':1440,'height':1000})
                # Finish the remaining rows by navigating and judging each real feedback row.
                page.get_by_role('button',name='录入结果',exact=True).click()
                for _ in range(9):
                    submit_one()
                page.locator('[data-tab="schedule"]').click()
                page.locator('#sch-plan-filter').select_option('completed')
                expect(page.locator('.sch-plan')).to_have_count(1)
                page.locator('.sch-plan').click()
                expect(page.locator('#sch-plan-detail')).to_contain_text('本次复习已全部录入')
                expect(page.get_by_role('button',name='录入结果',exact=True)).to_be_disabled()
                # A single question is a persisted plan too.
                page.locator('#sch-tab-arrange').click()
                page.locator('#rec-target-count').fill('1')
                page.locator('#rec-suggest').click()
                page.locator('#rec-confirm').click()
                expect(page.locator('#sch-plan-detail')).to_contain_text('共 1 题')
                self.assertEqual(len(list_sessions(vault)),2)
                self.assertEqual(len(list_sessions(vault,status='active')),1)
                # Empty recommendations point to pending plans; network errors are distinct and retryable.
                page.route('**/api/recommend?*',lambda r:r.fulfill(content_type='application/json',body='{"due":[],"proficiency":[]}'))
                arrange()
                expect(page.locator('#rec-unified-list-v2')).to_contain_text('查看已有计划')
                page.unroute('**/api/recommend?*')
                page.route('**/api/recommend?*',lambda r:r.fulfill(status=503,content_type='application/json',body='{"msg":"测试离线"}'))
                page.get_by_role('button',name='刷新推荐',exact=True).click()
                expect(page.locator('#rec-status-v2')).to_contain_text('推荐加载失败')
                expect(page.locator('#rec-confirm')).to_be_disabled()
                page.unroute('**/api/recommend?*')
                page.locator('#rec-status-v2').get_by_role('button',name='重试').click()
                page.wait_for_function('!REC_ERROR && !REC_LOADING')
                page.route('**/api/sessions',lambda r:r.fulfill(status=503,content_type='application/json',body='{"msg":"测试离线"}'))
                page.locator('#sch-tab-plans').click()
                page.get_by_role('button',name='刷新计划',exact=True).click()
                expect(page.locator('#sch-session-status')).to_contain_text('计划加载失败')
                page.unroute('**/api/sessions')
                page.locator('#sch-session-status').get_by_role('button',name='重试').click()
                expect(page.locator('#sch-session-status')).to_be_empty()
                page.route('**/api/session?*',lambda r:r.fulfill(status=404,content_type='application/json',body='{"msg":"计划不存在"}'))
                page.locator('.sch-plan').first.click()
                expect(page.locator('#sch-plan-detail')).to_contain_text('无法读取计划')
                page.unroute('**/api/session?*')
                page.locator('#sch-plan-detail').get_by_role('button',name='重试',exact=True).click()
                expect(page.locator('#sch-plan-detail')).to_contain_text('共 1 题')
                # Shared neighboring flows still load normally.
                page.locator('[data-tab="questions"]').click()
                expect(page.locator('#panel-questions')).to_be_visible()
                page.locator('[data-tab="instant"]').click()
                page.get_by_role('button',name='加载推荐',exact=True).click()
                page.wait_for_function('INSTANT_QUEUE.length > 0')
                self.assertEqual(errors,[])
                print(f'Browser screenshots: {screenshot_root}')
            finally:
                browser.close()
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
