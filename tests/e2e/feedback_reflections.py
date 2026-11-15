"""反馈页错因回归：真实临时 Vault、Session、HTTP 与 Chromium，不连接生产。"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from omrs import problems
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.sessions import create_session_from_selection

spec = importlib.util.spec_from_file_location('visual_run', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


def main():
    evidence = Path(os.environ.get('OMRS_FEEDBACK_REFLECTION_EVIDENCE', '/tmp/omrs-feedback-reflections'))
    evidence.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, value):
        checks.append({'name': name, 'ok': bool(value)})
        print(name, value, flush=True)
        assert value, name

    with tempfile.TemporaryDirectory(prefix='omrs-feedback-reflections-') as vault:
        questions = [create_question(vault, '数学', '不等式与边界', 5,
            question_text=f'解不等式 ${n + 2} - 2x > 0$，说明每一步的依据。',
            answer_text='除以负数时改变不等号方向，并检验边界。',
            cause='旧错因：没有改变不等号方向。' if n == 0 else '') for n in range(3)]
        qid = questions[0]['question_id']
        problems.execute(vault, 'add_reflection_entry', {
            'question_id': qid, 'content_md': '**端点检查**：代入 $x=1$，再核对解集。',
            'occurred_at': '2026-11-15', 'request_id': 'feedback-reflection-seed'})
        session = create_session_from_selection(vault, [{'question_id': q['question_id']} for q in questions])
        baseline = mastery_rows(vault)
        proc, port = visual.start_server(str(ROOT), vault, str(evidence / 'server.log'))
        base = f'http://127.0.0.1:{port}'
        try:
            with sync_playwright() as pw:
                browser = launch_chromium(pw)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                open_app(page, base, 'feedback')
                page.locator(f'#fb-session-picker option[value="{session["session_id"]}"]').wait_for(state='attached')
                page.select_option('#fb-session-picker', session['session_id'])
                host = page.locator('[data-reflections-host]')
                expect(host.locator('.ref-entry')).to_have_count(2)
                expect(host.get_by_role('tab', name='历史记录', exact=False)).to_have_attribute('aria-selected', 'true')
                check('反馈页默认展示统一错因历史', '旧错因：没有改变不等号方向。' in host.inner_text()
                      and '2026-11-15' in host.inner_text() and host.locator('[data-ref-panel="new"]').is_hidden())
                check('错因正常排版且不混入题目备注', host.locator('.q-md strong').inner_text() == '端点检查'
                      and page.locator('[data-qv-host]').get_by_text('旧错因：没有改变不等号方向。', exact=False).count() == 0)
                page.evaluate("window.feedbackReflectionHost = document.querySelector('[data-reflections-host]')")
                page.locator('.fbw-verdict__btn--no').click()
                page.locator('[data-input="feedback.score"]').fill('3')
                page.locator('[data-input="feedback.score"]').dispatch_event('input')
                page.locator('[data-input="feedback.note"]').fill('练习册第 18 页')
                check('判定打分不重建错因区', host.evaluate('(el) => el === window.feedbackReflectionHost'))

                host.get_by_role('tab', name='记录本次', exact=True).click()
                editor = host.locator('textarea')
                editor.fill('本次补记：先圈出负数，再逐步检查符号。')
                page.locator('.fbw-q').nth(1).click()
                guard = page.locator('dialog[open]').last
                expect(guard.get_by_text('还有未保存的错因', exact=True)).to_be_visible()
                guard.get_by_role('button', name='继续编辑', exact=True).click()
                check('取消换题保留草稿与原题', editor.input_value() == '本次补记：先圈出负数，再逐步检查符号。'
                      and host.get_attribute('data-question-id') == qid)
                page.locator('dialog.is-closing').wait_for(state='detached')
                page.route('**/api/problems/write', lambda route: route.abort('failed'), times=1)
                editor.press('Control+Enter')
                expect(host.locator('.ref-message')).to_contain_text('草稿已保留')
                check('保存失败保留错因和反馈判定', editor.input_value() == '本次补记：先圈出负数，再逐步检查符号。'
                      and page.locator('.fbw-verdict__btn--no').get_attribute('aria-pressed') == 'true'
                      and page.locator('[data-input="feedback.note"]').input_value() == '练习册第 18 页')
                editor.press('Control+Enter')
                expect(editor).to_have_value('')
                check('错因快捷保存只写一条，不提交作答', len(problems.reflections(vault, qid)['items']) == 3
                      and mastery_rows(vault) == baseline)
                host.get_by_role('tab', name='历史记录', exact=False).click()
                expect(host.locator('.ref-entry')).to_have_count(3)

                # 实际滚轮确认新增区域可达，不能只依赖 Playwright 自动滚入。
                for theme in ('light', 'dark'):
                    for width, height in ((1440, 1000), (1024, 900), (390, 844), (320, 720)):
                        shot_context = browser.new_context(viewport={'width': width, 'height': height})
                        shot_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        shot = shot_context.new_page()
                        shot.on('pageerror', lambda error: errors.append(str(error)))
                        open_app(shot, base, 'feedback')
                        shot.locator(f'#fb-session-picker option[value="{session["session_id"]}"]').wait_for(state='attached')
                        shot.select_option('#fb-session-picker', session['session_id'])
                        expect(shot.locator('.ref-entry')).to_have_count(3)
                        shot.evaluate('document.fonts.ready')
                        panel = shot.locator('.fbw-panel').bounding_box()
                        shot.mouse.move(panel['x'] + 100, min(panel['y'] + 100, height - 100))
                        for _ in range(12):
                            top = shot.locator('.ref-head').bounding_box()['y']
                            if 0 <= top < height - 40:
                                break
                            shot.mouse.wheel(0, max(-250, min(250, top - height / 2)))
                            shot.wait_for_timeout(100)  # 等待浏览器消费真实滚轮事件。
                        shot.wait_for_function("() => { const r = document.querySelector('.ref-head').getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; }")
                        check(f'{theme} {width}px 错因可滚动到达且页面不横向溢出',
                              shot.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                        shot.screenshot(path=str(evidence / f'feedback-{theme}-{width}.png'), full_page=True, animations='disabled')
                        shot_context.close()
                page.bring_to_front()

                page.locator('.fbw-q').nth(1).click()
                expect(host).to_have_attribute('data-question-id', questions[1]['question_id'])
                expect(host.locator('.ref-empty')).to_contain_text('还没有错因记录')
                check('换题切换历史并显示空状态', host.locator('.ref-entry').count() == 0)
                page.locator('.fbw-q').nth(0).click()
                expect(host.locator('.ref-entry')).to_have_count(3)
                check('切回原题保留判定、主观分和备注', page.locator('.fbw-verdict__btn--no').get_attribute('aria-pressed') == 'true'
                      and page.locator('[data-input="feedback.score"]').input_value() == '3'
                      and page.locator('[data-input="feedback.note"]').input_value() == '练习册第 18 页')

                # 题目详情与反馈页同时挂载时，页签 ID 不能相互指向。
                page.evaluate("async uid => { const q = await import('/assets/app/domain/question/index.js'); await q.viewQ(uid); }", questions[0]['uid'])
                expect(page.locator('#modal .ref-entry')).to_have_count(3)
                check('弹窗与反馈区并存时页签身份唯一', page.evaluate("() => { const ids = [...document.querySelectorAll('[id]')].map(el => el.id); return ids.length === new Set(ids).size; }"))
                page.locator('#modal [data-dialog-cancel]').click()
                page.locator('#modal').wait_for(state='detached')

                host.get_by_role('tab', name='记录本次', exact=True).click()
                editor.fill('离页前保留的草稿。')
                page.evaluate("() => { window.__omrs.router.go('questions'); }")
                guard = page.locator('dialog[open]').last
                expect(guard.get_by_text('还有未保存的错因', exact=True)).to_be_visible()
                guard.get_by_role('button', name='继续编辑', exact=True).click()
                check('离页取消保持反馈页与错因草稿', page.url.endswith('#/feedback') and editor.input_value() == '离页前保留的草稿。')
                page.locator('dialog.is-closing').wait_for(state='detached')
                page.locator('.fbw-q').nth(1).click()
                guard = page.locator('dialog[open]').last
                guard.get_by_role('button', name='保存后离开', exact=True).click()
                expect(host).to_have_attribute('data-question-id', questions[1]['question_id'])
                check('保存后换题写回原题身份', len(problems.reflections(vault, qid)['items']) == 4
                      and len(problems.reflections(vault, questions[1]['question_id'])['items']) == 0)
                page.locator('dialog.is-closing').wait_for(state='detached')
                page.locator('.fbw-q').nth(0).click()
                expect(host.locator('.ref-entry')).to_have_count(4)
                page.locator('[data-action="feedback.submit"]').click()
                expect(page.locator('dialog[open]').last).to_contain_text('1/1 条写入成功')
                page.locator('dialog[open]').last.get_by_role('button', name='知道了', exact=True).click()
                page.locator('dialog.is-closing').wait_for(state='detached')
                page.locator('.fbw-q').nth(0).click()
                expect(page.locator('.fbw-readonly')).to_contain_text('本题已录入反馈')
                expect(host.locator('.ref-entry')).to_have_count(4)
                check('已录入作答的题仍可查看错因历史', host.locator('[data-ref-panel="history"]').is_visible())
                check('浏览器没有脚本错误', not errors)
                context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            (evidence / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
    print(f'反馈错因：{len(checks)} 项通过；截图与结果：{evidence}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
