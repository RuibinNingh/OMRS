"""快捷错因布局回归：临时题库、真实服务和浏览器；不连接生产。"""
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

spec = importlib.util.spec_from_file_location('visual_run', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-only', action='store_true')
    args = parser.parse_args()
    evidence = Path(os.environ.get('OMRS_REFLECTION_EVIDENCE', '/tmp/omrs-reflection-layout'))
    evidence.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, value):
        checks.append({'name': name, 'ok': bool(value)})
        print(name, value, flush=True)
        assert value, name

    with tempfile.TemporaryDirectory(prefix='omrs-reflection-layout-') as vault:
        questions = [create_question(vault, '数学', '不等式与边界', 5,
            question_text=f'解不等式 ${2 + n} - 2x > 0$，并写明每一步变形的依据。\n\n分别代入一个满足条件和一个不满足条件的数，检查不等号方向和端点。',
            answer_text='两边除以负数时必须改变不等号方向，再检查边界。') for n in range(2)]
        baseline = mastery_rows(vault)
        problem = problems.execute(vault, 'create_problem', {
            'title': '不等式变形中的符号检查', 'description_md': '先判断乘除项的符号，再检验端点。',
            'question_ids': [q['question_id'] for q in questions], 'request_id': 'layout-problem'})['problem']
        for n, content in enumerate(['两边除以 −2 时，没有改变不等号方向。', '核对时遗漏了解集端点。', '同样的符号错误再次发生。']):
            problems.execute(vault, 'add_reflection_entry', {
                'question_id': questions[0]['question_id'], 'content_md': content, 'request_id': f'layout-{n}'})
        proc, port = visual.start_server(str(ROOT), vault, str(evidence / 'server.log'))
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}/#/problems')
                page.locator(f'[data-prb="open"][data-id="{problem["id"]}"]').click()
                page.locator('[data-prb="question"]').first.click()
                page.locator('#modal .ref-head').wait_for()
                page.locator('[data-qv-reflection]').click()
                editor = page.locator('#modal [data-ref-input="content_md"]')
                expect(editor).to_be_visible()
                page.evaluate('document.fonts.ready')
                if args.capture_only:
                    editor.fill('尚未保存的下一条观察')
                    for width, height in [(1440, 1000), (1024, 900), (390, 844)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        page.screenshot(path=str(evidence / f'before-{width}.png'), full_page=True, animations='disabled')
                    return 0
                q = page.locator('#modal .qv-q')
                aside = page.locator('#modal .qv-dialog__reflections')
                check('宽屏题干与侧栏并排且首屏可见',
                      q.bounding_box()['x'] + q.bounding_box()['width'] <= aside.bounding_box()['x'] + 1
                      and q.bounding_box()['y'] < 320)
                check('默认录入不展示历史堆栈', page.locator('#modal [data-ref-panel="history"]').is_hidden())
                top = q.bounding_box()['y']
                editor.fill('翻页和切换页签仍要保留的草稿')
                editor.evaluate('(el) => { window.layoutEditor = el; el.setSelectionRange(3, 7); }')
                page.get_by_role('tab', name='历史记录', exact=False).click()
                expect(page.locator('#modal .ref-entry').first).to_be_visible()
                check('切换历史不挤动题干', abs(q.bounding_box()['y'] - top) < 1)
                page.get_by_role('tab', name='记录本次', exact=True).click()
                check('页签复用同一编辑框并保留草稿', editor.evaluate('(el) => el === window.layoutEditor')
                      and editor.input_value() == '翻页和切换页签仍要保留的草稿')
                check('切页签保留文字选区', editor.evaluate('(el) => el.selectionStart === 3 && el.selectionEnd === 7'))
                page.get_by_role('tab', name='记录本次', exact=True).focus()
                page.keyboard.press('ArrowRight')
                expect(page.get_by_role('tab', name='历史记录', exact=False)).to_have_attribute('aria-selected', 'true')
                page.keyboard.press('ArrowLeft')
                check('页签方向键不会触发翻题', page.locator('#qv-nav-pos').inner_text() == '第 1 / 2 题'
                      and editor.is_visible())
                page.set_viewport_size({'width': 1024, 'height': 900})
                check('空间不足错因移至题目下方', aside.bounding_box()['y'] >= page.locator('#modal .qv-dialog__stage').bounding_box()['y'] + page.locator('#modal .qv-dialog__stage').bounding_box()['height'] - 1)
                page.locator('[data-qv-reflection]').click()
                expect(editor).to_be_in_viewport()
                check('顶部错因入口能到达底部编辑框', editor.is_visible())
                page.set_viewport_size({'width': 1440, 'height': 1000})
                check('恢复宽度重新并排且草稿不丢', q.bounding_box()['x'] + q.bounding_box()['width'] <= aside.bounding_box()['x'] + 1
                      and editor.input_value() == '翻页和切换页签仍要保留的草稿')
                page.screenshot(path=str(evidence / 'sidebar-1440.png'), full_page=True, animations='disabled')
                page.route('**/api/problems/write', lambda route: route.abort('failed'), times=1)
                page.locator('#modal [data-ref="save"]').click()
                page.get_by_text('草稿已保留，可重试。', exact=False).wait_for()
                check('失败保留编辑内容', editor.input_value() == '翻页和切换页签仍要保留的草稿')
                page.locator('#modal [data-ref="save"]').click()
                expect(editor).to_have_value('')
                check('保存后焦点回到可编辑输入框', editor.evaluate('(el) => el === document.activeElement && !el.matches(":disabled")'))
                check('重试只追加一条记录', len(problems.reflections(vault, questions[0]['question_id'])['items']) == 4)
                page.get_by_role('tab', name='历史记录', exact=False).click()
                page.locator('#modal .ref-entry').first.locator('summary').first.click()
                page.locator('#modal [data-ref="revise"]').first.click()
                expect(editor).to_be_visible()
                editor.fill('修订：先标出负数，再改变不等号方向。')
                page.locator('#modal [data-ref="save"]').click()
                expect(editor).to_have_value('')
                page.get_by_role('tab', name='历史记录', exact=False).click()
                expect(page.locator('#modal .ref-entry').first).to_contain_text('第 2 版')
                check('修订入口返回录入且保留历史版本', any(e['revision'] == 2 for e in problems.reflections(vault, questions[0]['question_id'])['items']))
                page.screenshot(path=str(evidence / 'history-1440.png'), full_page=True, animations='disabled')
                page.locator('[data-qv-reflection]').click()
                editor.fill('需要保护的草稿')
                page.locator('#modal [data-qv-nav="next"]').click()
                page.get_by_role('button', name='继续编辑', exact=True).click()
                page.wait_for_function("!document.querySelector('dialog.is-closing')")
                check('翻题取消仍保留当前草稿', editor.input_value() == '需要保护的草稿')
                editor.fill('')
                page.locator('#modal [data-qv-nav="next"]').click()
                page.wait_for_function("document.querySelector('#modal .ref-head strong')?.textContent.includes('0 条')")
                check('翻题身份隔离', editor.input_value() == '' and page.locator('#modal .ref-entry').count() == 0)
                page.locator('#modal [data-qv-nav="prev"]').click()
                page.wait_for_function("document.querySelectorAll('#modal .ref-entry').length === 4")
                for theme in ['light', 'dark']:
                    page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                    for width, height in [(1440, 1000), (1160, 900), (1024, 900), (760, 900), (390, 844), (320, 720)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        page.locator('[data-qv-reflection]').click()
                        editor.fill('宽度变化时仍在同一个编辑框中。')
                        editor.scroll_into_view_if_needed()
                        check(f'{theme}-{width}没有横向溢出', page.locator('#modal .qv-dialog__body').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1')
                              and editor.bounding_box()['x'] + editor.bounding_box()['width'] <= width + 1)
                        check(f'{theme}-{width}顶部按钮不重叠且可点', page.locator('#modal .qv-dialog__head').evaluate('''(el) => {
                            const boxes = [...el.querySelectorAll('button')].map(b => b.getBoundingClientRect()).filter(r => r.width > 0);
                            const size = innerWidth <= 760 ? 40 : 28;
                            return boxes.every((r, i) => r.height >= size && r.width >= size
                                && r.left >= 0 && r.right <= innerWidth
                                && (!i || boxes[i - 1].right <= r.left + 1));
                        }'''))
                        page.screenshot(path=str(evidence / f'{theme}-{width}.png'), full_page=True, animations='disabled')
                page.set_viewport_size({'width': 1024, 'height': 1100})
                page.locator('[data-qv-reflection]').click()
                editor.fill('保存成功后的刷新失败不应再次提交。')
                page.route('**/api/reflections?question_id=*', lambda route: route.abort('failed'), times=1)
                page.locator('#modal [data-ref="save"]').click()
                page.get_by_text('已保存，但历史记录刷新失败', exact=False).wait_for()
                check('写入后刷新失败明确提示已保存', editor.input_value() == ''
                      and len(problems.reflections(vault, questions[0]['question_id'])['items']) == 5)
                page.locator('#modal [data-dialog-cancel]').click()
                page.wait_for_selector('#modal', state='detached')
                page.locator('[data-prb="question"]').first.click()
                page.wait_for_function("document.querySelectorAll('#modal .ref-entry').length === 5")
                check('窄屏重新打开题干在首屏且编辑区在后', q.bounding_box()['y'] < 320
                      and aside.bounding_box()['y'] >= page.locator('#modal .qv-dialog__stage').bounding_box()['y'] + page.locator('#modal .qv-dialog__stage').bounding_box()['height'] - 1)
                page.screenshot(path=str(evidence / 'bottom-1024.png'), full_page=True, animations='disabled')
                check('错因没有改变学习状态', mastery_rows(vault) == baseline)
                check('无脚本错误', not errors)
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=15)
            (evidence / 'results.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
