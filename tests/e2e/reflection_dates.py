"""错因日期回归：临时 Vault、真实 HTTP 与浏览器，不连接生产。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from omrs import problems
from omrs.creation import create_question
from omrs.data_repository import mastery_rows
from omrs.sessions import create_session_from_selection

spec = importlib.util.spec_from_file_location('visual_run', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='/tmp/omrs-reflection-dates')
    parser.add_argument('--before-source', type=Path, help='可选：基线错因模块副本，用于同份数据的前后截图')
    args = parser.parse_args()
    evidence = Path(args.out)
    evidence.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, value):
        checks.append({'name': name, 'ok': bool(value)})
        print(name, bool(value), flush=True)
        assert value, name

    with tempfile.TemporaryDirectory(prefix='omrs-reflection-dates-') as vault:
        q = create_question(vault, '数学', '日期核对', 5, question_text='合成题：核对解集边界。',
                            answer_text='先检查端点。', cause='没有日期的旧笔记')
        qid = q['question_id']
        unknown = problems.execute(vault, 'add_reflection_entry', {
            'question_id': qid, 'content_md': '已知记录时间的补记', 'request_id': 'unknown'})['entry']
        dated = problems.execute(vault, 'add_reflection_entry', {
            'question_id': qid, 'content_md': '旧日期错因', 'occurred_at': '2026-10-01', 'request_id': 'dated'})['entry']
        session = create_session_from_selection(vault, [{'question_id': qid}])
        baseline = mastery_rows(vault)
        proc, port = visual.start_server(str(ROOT), vault, str(evidence / 'server.log'))
        try:
            with sync_playwright() as pw:
                browser = visual.launch_chromium(pw)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                              timezone_id='America/Los_Angeles', locale='zh-CN')
                # 上海已跨日、设备仍在前一日，检验默认值没有误用 UTC 或设备日期。
                context.add_init_script('''(() => {
                    const D = Date, now = D.parse('2026-11-15T16:30:00Z');
                    globalThis.Date = class extends D {
                        constructor(...args) { super(...(args.length ? args : [now])); }
                        static now() { return now; }
                    };
                })();''')
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                base = f'http://127.0.0.1:{port}'

                def capture(target, side):
                    for theme in ('light', 'dark'):
                        target.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                        for width, height in ((1440, 1000), (1024, 900), (390, 844), (320, 720)):
                            target.set_viewport_size({'width': width, 'height': height})
                            target.locator(f'.ref-entry[data-key="{unknown["id"]}"]').scroll_into_view_if_needed()
                            target.evaluate('document.fonts.ready')
                            target.add_style_tag(content=visual.STILL_CSS)
                            target.screenshot(path=str(evidence / f'{side}-{theme}-{width}.png'), animations='disabled')

                if args.before_source:
                    before = context.new_page()
                    before.on('pageerror', lambda error: errors.append(str(error)))
                    for name in ('reflection-state.js', 'reflections-view.js'):
                        source = args.before_source / 'assets/app/domain/question' / name
                        before.route(f'**/domain/question/{name}*', lambda route, request, source=source: route.fulfill(
                            path=str(source), content_type='text/javascript'))
                    before.goto(base + '/?unlocked=1#/questions', wait_until='networkidle')
                    before.locator(f'tr[data-q-row="{q["uid"]}"] td').nth(1).click()
                    expect(before.locator('#modal .ref-entry')).to_have_count(3)
                    capture(before, 'before')
                    before.close()
                page.goto(base + '/?unlocked=1#/questions', wait_until='networkidle')
                page.locator(f'tr[data-q-row="{q["uid"]}"] td').nth(1).click()
                host = page.locator('#modal .reflections')
                expect(host.locator('.ref-entry')).to_have_count(3)
                if args.before_source:
                    capture(page, 'after')
                    page.set_viewport_size({'width': 1440, 'height': 1000})

                def entry(value):
                    return host.locator(f'.ref-entry[data-key="{value["id"]}"]')

                check('旧笔记保持发生日期未知', '发生日期未知' in host.inner_text())
                check('未知发生日期明确显示记录于', entry(unknown).locator(':scope > .ref-note').first.inner_text().startswith('记录于 '))
                check('已知发生日期有明确标签', entry(dated).locator(':scope > .ref-note').first.inner_text() == '发生日期：2026-10-01')
                entry(unknown).locator('summary').first.click()
                check('详情区分记录时间与未知发生日期', '记录时间：' in entry(unknown).inner_text()
                      and '发生日期：未知' in entry(unknown).inner_text())
                page.locator('#modal [data-qv-reflection]').click()
                editor = host.locator('[data-ref-input="content_md"]')
                date = host.locator('[data-ref-input="occurred_at"]')
                check('新记录使用上海当天而非设备日期', date.input_value() == '2026-11-16')

                def save():
                    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/problems/write')) as pending:
                        host.locator('[data-ref="save"]').click()
                    response = pending.value
                    assert response.ok, response.text()
                    expect(editor).to_have_value('')
                    return response.json()['entry']

                editor.fill('默认当天的新错因')
                today = save()
                check('不操作日期即可保存为当天', today['occurred_at'] == '2026-11-16')
                check('连续新增重新默认当天', date.input_value() == '2026-11-16')
                host.locator('[data-ref-disclosure="more"] summary').click()
                date.fill('')
                editor.fill('明确不知道发生日期')
                cleared = save()
                check('主动清空仍保存未知且有记录时间', cleared['occurred_at'] is None and bool(cleared['created_at']))
                host.get_by_role('tab', name='历史记录', exact=False).click()
                entry(dated).locator('summary').first.click()
                entry(dated).locator('[data-ref="recurrence"]').click()
                check('再次发生使用当天而不继承旧发生日期', date.input_value() == '2026-11-16')
                repeated = save()
                check('再次发生保留引用且保存当天', repeated['recurrence_of'] == dated['id']
                      and repeated['occurred_at'] == '2026-11-16')
                host.get_by_role('tab', name='历史记录', exact=False).click()
                entry(unknown).locator('[data-ref="revise"]').click()
                check('修订历史未知日期不会自动补今天', date.input_value() == '')
                editor.fill('补记修订后依然未知')
                revised = save()
                check('仅修正文保留未知日期与原记录时间', revised['occurred_at'] is None
                      and revised['created_at'] == unknown['created_at'])
                page.reload(wait_until='networkidle')
                page.locator(f'tr[data-q-row="{q["uid"]}"] td').nth(1).click()
                expect(entry(today)).to_contain_text('发生日期：2026-11-16')
                expect(entry(cleared).locator(':scope > .ref-note').first).to_contain_text('记录于 ')
                check('刷新保留当天与主动清空的区别', len(problems.reflections(vault, qid)['items']) == 6)
                for theme in ('light', 'dark'):
                    page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                    for width, height in ((1440, 1000), (1024, 900), (390, 844), (320, 720)):
                        page.set_viewport_size({'width': width, 'height': height})
                        entry(cleared).scroll_into_view_if_needed()
                        check(f'{theme}-{width}日期文案不撑宽页面', page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                              and host.evaluate('el => el.scrollWidth <= el.clientWidth + 1'))
                        page.screenshot(path=str(evidence / f'history-{theme}-{width}.png'), animations='disabled')
                page.locator('#modal [data-dialog-cancel]').click()
                page.goto(base + '/?unlocked=1#/feedback', wait_until='networkidle')
                expect(page.locator(f'#fb-session-picker option[value="{session["session_id"]}"]')).to_have_count(1)
                page.select_option('#fb-session-picker', session['session_id'])
                feedback = page.locator('[data-reflections-host]')
                expect(feedback.locator('.ref-entry')).to_have_count(6)
                feedback.get_by_role('tab', name='记录本次', exact=True).click()
                check('反馈页复用当天默认值', feedback.locator('[data-ref-input="occurred_at"]').input_value() == '2026-11-16')
                check('日期录入不改变学习状态', mastery_rows(vault) == baseline)
                check('浏览器无脚本错误', not errors)
                context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
            (evidence / 'checks.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
        finally:
            proc.terminate()
            proc.wait(timeout=15)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
