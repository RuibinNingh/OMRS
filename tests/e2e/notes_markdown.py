"""备注错因排版回归：临时Vault、真实服务与Chromium，不连接生产。"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import zlib

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from omrs.common import ATTACHMENTS_DIR, questions_root
from omrs.content_history import projection_row, question_file
from omrs.creation import create_question
from omrs.data_repository import mastery_rows

spec = importlib.util.spec_from_file_location('visual_run', ROOT / 'tests/visual/run.py')
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)

CAUSE = r'''**漏看负号**，导致不等号方向错误。

- 两边除以 $-2$ 时，不等号要反向。
- 代回原式，检查边界点。

> 先判断符号，再做变形。

### 复查依据
\[
2 - 2x > 0 \Longrightarrow x < 1
\]

| 检查项 | 结果 |
| --- | --- |
| 代入 $x = 0$ | 满足原式 |

用 `2 - 2x > 0` 核对，补充 \(x = 1\) 的边界。

![[复查.png|160]]

```md
## 代码保留源码
\(x\)
```

<script>window.notesScriptRan = true</script>'''


def write_image(vault):
    """生成合成题图，覆盖真实受控图片读取与解码。"""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = b''.join(b'\x00' + bytes((227, 237, 233)) * 160 for _ in range(32))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 160, 32, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    path = Path(questions_root(vault)) / ATTACHMENTS_DIR / '复查.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='/tmp/omrs-notes-markdown')
    parser.add_argument('--before-source', type=Path, help='可选：本轮开工前的文件副本，仅用于浏览器前后截图')
    args = parser.parse_args()
    evidence = Path(args.out)
    evidence.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, value):
        checks.append({'name': name, 'ok': bool(value)})
        print(name, bool(value), flush=True)
        assert value, name

    def open_question(browser, base, uid, before=None):
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        ctx.add_init_script("localStorage.setItem('omrs-theme', 'light')")
        page = ctx.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        if before:
            for name in ['view.js', 'qview.css']:
                source = before / 'assets/app/domain/question' / name
                page.route(f'**/domain/question/{name}*', lambda route, request, source=source: route.fulfill(
                    path=str(source), content_type='text/css' if source.suffix == '.css' else 'text/javascript'))
        page.goto(f'{base}/?unlocked=1#/questions', wait_until='networkidle')
        page.locator(f'tr[data-q-row="{uid}"] td').nth(1).click()
        page.locator('#modal-stage .qv-a').wait_for()
        page.locator('#modal .ref-head').wait_for()
        page.evaluate('document.fonts.ready')
        page.add_style_tag(content=visual.STILL_CSS)
        return ctx, page

    with tempfile.TemporaryDirectory(prefix='omrs-notes-markdown-') as vault:
        question = create_question(vault, '数学', '不等式与边界', 5,
            question_text='解不等式 $2 - 2x > 0$，并说明变形依据。\n\n1. 给出解集。\n2. 代入边界点复核。',
            answer_text='两边同除以 $-2$ 时改变不等号方向，得到 $x < 1$。', cause=CAUSE)
        write_image(vault)
        path = Path(question_file(vault, projection_row(vault, uid=question['uid'])))
        before_bytes = path.read_bytes()
        before_mastery = mastery_rows(vault)
        proc, port = visual.start_server(str(ROOT), vault, str(evidence / 'server.log'))
        try:
            with sync_playwright() as pw:
                browser = visual.launch_chromium(pw)
                base = f'http://127.0.0.1:{port}'
                if args.before_source:
                    ctx, page = open_question(browser, base, question['uid'], args.before_source)
                    old_notes = page.locator('#modal-stage .qv-a .q-md').last
                    check('修改前确实显示Markdown源码', old_notes.locator('h2').count() == 0 and '## 错因' in old_notes.inner_text())
                    old_notes.screenshot(path=str(evidence / 'notes-before.png'), animations='disabled')
                    ctx.close()

                ctx, page = open_question(browser, base, question['uid'])
                plain_notes = page.locator('#modal-stage .q-notes-md')
                expect(plain_notes.locator('h2')).to_have_text(['关联'])
                check('备注区保留关联且不重复显示错因', '漏看负号' not in plain_notes.inner_text()
                      and page.locator('#modal-stage .qv-a > .qv-label').last.inner_text() == '备注')
                notes = page.locator('#modal .ref-entry > .q-md').first
                expect(notes).to_be_visible()
                check('默认历史展示旧错因与未知日期', page.locator('#modal [data-ref-panel="new"]').is_hidden()
                      and '日期未知' in page.locator('#modal .ref-entry').first.inner_text())
                check('加粗与列表真实渲染', notes.locator('strong').inner_text() == '漏看负号' and notes.locator('ul li').count() == 2)
                check('引用与小标题真实渲染', notes.locator('blockquote').inner_text() == '先判断符号，再做变形。'
                      and notes.locator('h3').inner_text() == '复查依据')
                expect(notes.locator('.katex-display')).to_have_count(1)
                check('美元与反斜杠公式渲染为KaTeX', notes.locator('.katex').count() == 4)
                check('表格保留', notes.locator('table.md-table tbody td').count() == 2)
                expect(notes.locator('img')).to_be_visible()
                page.wait_for_function("document.querySelector('.ref-entry .q-md img')?.naturalWidth === 160")
                check('题图按受控入口解码', '/api/image?name=' in notes.locator('img').get_attribute('src'))
                check('行内与围栏代码保持源码', notes.locator('p code').inner_text() == '2 - 2x > 0'
                      and notes.locator('pre code').inner_text() == '## 代码保留源码\n\\(x\\)')
                check('HTML只显示文字且不执行', notes.locator('script').count() == 0
                      and page.evaluate('window.notesScriptRan === undefined') and '<script>' in notes.inner_text())
                check('题目编号与答案保留原样', page.locator('#modal-stage .qv-q ol').count() == 0
                      and '1. 给出解集。' in page.locator('#modal-stage .qv-q').inner_text()
                      and '得到' in page.locator('#modal-stage .q-answer-md').inner_text())
                check('只查看不会改写旧Markdown', path.read_bytes() == before_bytes)
                notes.screenshot(path=str(evidence / 'notes-after.png'), animations='disabled')
                page.locator('#modal-stage, #modal .qv-dialog__body').evaluate_all('els => els.forEach(el => el.scrollTop = 0)')
                page.screenshot(path=str(evidence / 'dialog-after.png'), full_page=True, animations='disabled')
                for theme in ['light', 'dark']:
                    page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                    for width, height in [(1440, 1000), (1024, 900), (390, 844), (320, 720)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        notes.locator('h3').first.scroll_into_view_if_needed()
                        check(f'{theme}-{width}备注可读且页面无横向溢出', notes.evaluate('''el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.left >= 0 && r.right <= innerWidth + 1
                                && el.scrollWidth <= el.clientWidth + 1
                                && document.documentElement.scrollWidth <= innerWidth + 1;
                        }'''))
                        check(f'{theme}-{width}公式和代码限于各自容器', notes.evaluate('''el => {
                            return [...el.querySelectorAll('pre, .katex-display, .md-table-wrap')].every(child => {
                                const r = child.getBoundingClientRect(), p = el.getBoundingClientRect();
                                return r.left >= p.left && r.right <= p.right + 1;
                            });
                        }'''))
                        page.screenshot(path=str(evidence / f'{theme}-{width}.png'), full_page=True, animations='disabled')
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.locator('#modal-stage [data-qv-act="edit"]').click()
                editor = page.locator('#md-edit-text')
                expect(editor).to_be_visible()
                editor.fill(editor.input_value().replace('## 关联', '## 关联\n**保存后仍渲染**'))
                page.locator('#md-editor [data-dialog-ok]').click()
                expect(page.locator('#md-editor')).to_have_count(0)
                expect(plain_notes.locator('strong').last).to_have_text('保存后仍渲染')
                check('编辑保存后重新渲染', b'**' in path.read_bytes() and '保存后仍渲染' in path.read_text())
                page.locator('#modal [data-qv-reflection]').click()
                record_editor = page.locator('#modal [data-ref-input="content_md"]')
                record_editor.fill('检查乘除负号\n\n## 核对步骤\n先验端点。')
                page.locator('#modal [data-ref-disclosure="more"] summary').click()
                page.locator('#modal [data-ref-input="occurred_at"]').fill('2026-11-15')
                page.locator('#modal [data-ref="save"]').click()
                expect(record_editor).to_have_value('')
                page.get_by_role('tab', name='历史记录', exact=False).click()
                expect(page.locator('#modal .ref-entry')).to_have_count(2)
                check('日期和多级标题保存到原题且仅在历史显示', '### 2026-11-15 · REF-' in path.read_text()
                      and '检查乘除负号' in page.locator('#modal .ref-entry').first.inner_text()
                      and '检查乘除负号' not in plain_notes.inner_text())
                page.locator('#modal-stage [data-qv-act="edit"]').click()
                expect(editor).to_be_visible()
                editor.fill(editor.input_value().replace('> 检查乘除负号', '> 外部复核之后的新观察'))
                page.locator('#md-editor [data-dialog-ok]').click()
                expect(page.locator('#md-editor')).to_have_count(0)
                expect(page.locator('#modal .ref-entry').first).to_contain_text('外部复核之后的新观察')
                check('Markdown保存后历史即时刷新且不出现双份', page.locator('#modal .ref-entry').count() == 2)
                from omrs.exporting import _parse_notes_subsections
                from omrs.reflection_markdown import notes_of
                exported = _parse_notes_subsections(notes_of(path.read_text()))['错因']
                check('导出统一后的有效错因且不泄漏元数据', '外部复核之后的新观察' in exported
                      and '漏看负号' in exported and 'omrs-reflection' not in exported)
                page.locator('#modal [data-dialog-cancel]').click()
                page.wait_for_selector('#modal', state='detached')
                page.locator(f'tr[data-q-row="{question["uid"]}"] td').nth(1).click()
                expect(page.get_by_role('tab', name='历史记录', exact=False)).to_have_attribute('aria-selected', 'true')
                expect(page.locator('#modal .ref-entry')).to_have_count(2)
                check('重新打开默认历史并保留两条', page.locator('#modal .ref-entry').count() == 2)
                check('查看和编辑备注不改变学习状态', mastery_rows(vault) == before_mastery)
                check('全程没有脚本错误', not errors)
                ctx.close()
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=15)
            (evidence / 'results.json').write_text(json.dumps({'checks': checks, 'errors': errors}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
