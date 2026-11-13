"""临时 Vault 的真实导出闭环：参数、记忆、失败重试、纸面历史与浅深/窄屏截图。"""
from pathlib import Path
import json
import os
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from omrs.creation import create_question
from omrs.data_repository import resolve_question
from omrs.sessions import create_session_from_selection
from tests.browser_runtime import launch_chromium, open_app
from tests.test_schedule_export_history import seed_history
from tests.visual.run import start_server


def main():
    shots = Path(os.environ.get('OMRS_EXPORT_SHOTS', tempfile.mkdtemp(prefix='omrs-export-shots-')))
    shots.mkdir(parents=True, exist_ok=True)
    checks = 0

    def check(label, condition):
        nonlocal checks
        assert condition, label
        checks += 1
        print(f'通过：{label}', flush=True)

    with tempfile.TemporaryDirectory(prefix='omrs-export-e2e-') as temp:
        vault = Path(temp) / 'vault'
        questions = []
        for index, (question, answer) in enumerate([
            (r'已知函数 $f(x)=x^2-4x+3$，求其单调区间与最小值。', r'递减区间为 $(-\infty,2]$，递增区间为 $[2,+\infty)$，最小值为 $-1$。'),
            (r'等差数列 $\{a_n\}$ 满足 $a_1=2$，$a_5=14$，求前十项和。', r'公差 $d=3$，$S_{10}=155$。'),
            (r'在直角三角形中，两条直角边分别为 $3$ 和 $4$，求斜边上的高。', r'斜边长为 $5$，由面积关系得到高为 $\frac{12}{5}$。'),
            ('这是一道尚未练习的题目。', ''),
        ]):
            created = create_question(str(vault), '数学', ['二次函数', '等差数列', '平面几何', '综合'][index], 5,
                                      question_text=question, answer_text=answer)
            row = resolve_question(str(vault), created['uid'])
            questions.append(row)
            if index < 3:
                seed_history(str(vault), row['question_id'], row['uid'])
        session = create_session_from_selection(str(vault), [{'question_id': q['question_id'], 'source': 'due'} for q in questions])
        proc, port = start_server(str(ROOT), str(vault), str(Path(temp) / 'server.log'))
        base = f'http://127.0.0.1:{port}'
        try:
            with sync_playwright() as runtime:
                browser = launch_chromium(runtime)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('omrs-theme','light')")
                page = context.new_page()
                errors, requests = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: requests.append(request.post_data_json) if request.method == 'POST' and request.url.endswith('/api/export') else None)
                open_app(page, base, 'schedule')
                page.click('#sch-tab-plans')
                page.click(f'.schd-plan[data-arg="{session["session_id"]}"]')
                page.click('[data-action="schedule.export"][data-arg="a4"]')
                panel = page.locator('#schedule-export-dialog')
                panel.wait_for()
                check('导出先打开参数面板，未提交请求', not requests)
                check('默认双栏、反馈区、最近8次', panel.locator('[name="columns"][value="two"]').is_checked()
                      and panel.locator('[name="historyPosition"][value="feedback"]').is_checked() and panel.locator('#historyLimit').input_value() == '8')
                panel.locator('.ui-dialog__panel').screenshot(path=str(shots / 'export-dialog-light.png'))
                page.evaluate("document.documentElement.dataset.theme = 'dark'")
                panel.locator('.ui-dialog__panel').screenshot(path=str(shots / 'export-dialog-dark.png'))
                page.evaluate("document.documentElement.dataset.theme = 'light'")
                panel.locator('#answers').check()
                panel.locator('#gap').fill('2')
                with page.expect_download() as pending:
                    panel.locator('#gap').press('Enter')
                artifact = shots / 'review-feedback.html'
                pending.value.save_as(str(artifact))
                page.wait_for_selector('#schedule-export-dialog', state='detached')
                check('请求使用计划身份与历史参数，回车保留最后输入', requests[-1]['session_id'] == session['session_id']
                      and requests[-1]['history']['position'] == 'feedback' and requests[-1]['question_gap_lines'] == 2)
                printed = context.new_page()
                printed.goto(artifact.as_uri())
                printed.wait_for_function('window.__OMRS_RESULT && !document.getElementById("btnPrint").disabled')
                data = printed.evaluate('window.OMRS_DATA')
                records = data['answers'][0]['history']
                check('按答题时间倒序，保留零分与高分答错', [r['score'] for r in records] == [0, 4, 9, 8, 2, 7, 3, 6]
                      and not records[2]['correct'])
                check('没有历史的题不占位，历史仅在反馈区', printed.locator('#stage .review-history').count() == 3
                      and all(not q['history'] for q in data['questions']))
                check('图高不超过15mm，零分细条可见', printed.locator('.review-history').first.evaluate('(e) => e.getBoundingClientRect().height') <= 56.7
                      and printed.locator('[data-score="0"] rect').first.get_attribute('height') == '1.2')
                check('对错独立于分数着色，黑白有符号', printed.locator('.history-wrong[data-score="9"]').count() == 3
                      and printed.locator('.history-right[data-score="4"]').count() == 3
                      and '×' in printed.locator('.history-wrong').first.text_content())
                printed.locator('.page').first.screenshot(path=str(shots / 'export-feedback-page.png'))
                printed.wait_for_timeout(200)
                region = printed.locator('.q-head--history').first.bounding_box()
                printed.screenshot(path=str(shots / 'export-history-detail.png'), clip=region)
                pdf = printed.pdf(prefer_css_page_size=True, print_background=False)
                (shots / 'review-feedback.pdf').write_bytes(pdf)
                check('离线 A4 排版完整、PDF页数一致', not printed.evaluate('window.__OMRS_RESULT.errors.length')
                      and len(re.findall(rb'/Type /Page\b', pdf)) == printed.evaluate('window.__OMRS_RESULT.pages'))
                printed.close()
                page.reload(wait_until='networkidle')
                page.wait_for_function('!!window.__omrs')
                page.click('#sch-tab-plans')
                page.click(f'.schd-plan[data-arg="{session["session_id"]}"]')
                page.click('[data-action="schedule.export"][data-arg="a4"]')
                check('刷新恢复上次成功导出的参数', panel.locator('#answers').is_checked() and panel.locator('#gap').input_value() == '2')
                panel.locator('[name="historyPosition"][value="question"] + span').click()
                panel.locator('[data-dialog-cancel]').first.click()
                page.wait_for_selector('#schedule-export-dialog', state='detached')
                page.click('[data-action="schedule.export"][data-arg="a4"]')
                check('取消不覆盖上次成功设置', panel.locator('[name="historyPosition"][value="feedback"]').is_checked())
                page.route('**/api/export', lambda route: route.fulfill(status=400, content_type='application/json', body='{"msg":"合成导出失败"}'))
                panel.locator('[data-dialog-ok]').click()
                panel.locator('[role="alert"]').wait_for()
                check('失败留在面板，可修正重试', '合成导出失败' in panel.inner_text() and panel.locator('[data-dialog-ok]').is_enabled())
                page.unroute('**/api/export')
                panel.locator('[name="historyPosition"][value="question"] + span').click()
                panel.locator('[name="columns"][value="one"] + span').click()
                panel.locator('#answers').uncheck()
                with page.expect_download() as pending:
                    panel.locator('[data-dialog-ok]').click()
                artifact = shots / 'review-question.html'
                pending.value.save_as(str(artifact))
                page.wait_for_selector('#schedule-export-dialog', state='detached')
                printed = context.new_page()
                printed.goto(artifact.as_uri())
                printed.wait_for_function('window.__OMRS_RESULT && !document.getElementById("btnPrint").disabled')
                check('切换题目区与单栏后实际导出同步', printed.locator('.page.single').count() > 0
                      and printed.evaluate('OMRS_DATA.questions[0].history.length') == 8
                      and printed.evaluate('OMRS_DATA.answers.every(a => !a.history.length && !a.blocks.length)'))
                printed.locator('.page').first.screenshot(path=str(shots / 'export-question-page.png'))
                printed.close()
                # 从全库入口打开同一套设置，跨入口记忆，屏幕版不污染纸面答案开关。
                page.click('.schd-top [data-arg="export"]')
                page.click('[data-action="schedule.xaddFiltered"]')
                page.click('[data-action="schedule.xexport"]')
                check('全库导出共用上次参数', panel.locator('[name="columns"][value="one"]').is_checked()
                      and panel.locator('[name="historyPosition"][value="question"]').is_checked())
                panel.locator('[name="variant"][value="screen"] + span').click()
                check('屏幕版强制答案并禁用纸面选项', panel.locator('#answers').is_checked() and panel.locator('#answers').is_disabled()
                      and panel.locator('#gap').is_disabled())
                with page.expect_download() as pending:
                    panel.locator('[data-dialog-ok]').click()
                artifact = shots / 'review-screen.html'
                pending.value.save_as(str(artifact))
                page.wait_for_selector('#schedule-export-dialog', state='detached')
                screen = context.new_page()
                screen.goto(artifact.as_uri())
                check('屏幕版离线显示同一历史图', screen.locator('.review-history').count() == 3)
                screen.close()
                # 手机与深浅主题实际打开面板，审核滚动、触控目标和横向溢出。
                for width in (320, 390, 1440):
                    page.set_viewport_size({'width': width, 'height': 844 if width < 760 else 1000})
                    for theme in ('light', 'dark'):
                        page.evaluate('(theme) => { document.documentElement.dataset.theme = theme; }', theme)
                        page.click('[data-action="schedule.xexport"]')
                        panel.locator('[name="variant"][value="a4"] + span').click()
                        panel.locator('summary').click()
                        audit = panel.evaluate('''el => ({
                            overflow: el.querySelector('.ui-dialog__panel').scrollWidth > el.querySelector('.ui-dialog__panel').clientWidth + 1,
                            inline: el.querySelectorAll('[style],[onclick]').length,
                            small: [...el.querySelectorAll('button,summary,.ui-segmented__label')].filter(e => e.offsetParent && e.getBoundingClientRect().height < (innerWidth < 760 ? 39 : 27)).length,
                        })''')
                        check(f'{width}px {theme} 无横向溢出、行内样式或过小控件', not audit['overflow'] and not audit['inline'] and not audit['small'])
                        panel.locator('.ui-dialog__panel').screenshot(path=str(shots / f'export-dialog-{width}-{theme}.png'))
                        panel.locator('[data-dialog-cancel]').first.click()
                        page.wait_for_selector('#schedule-export-dialog', state='detached')
                check('页面脚本错误为零', not errors)
                context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print(f'{checks} 项通过；截图与离线文件：{shots}', flush=True)


if __name__ == '__main__':
    main()
