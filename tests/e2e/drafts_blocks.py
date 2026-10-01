"""多块草稿：真实隔离服务验证编辑、菜单、稳定身份、图文入库与窄屏。"""
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, ROOT)
sys.path.insert(0, str(Path(ROOT, 'tests')))
from browser_runtime import launch_chromium
from omrs import drafts as store
import drafts as support

SHOTS = Path('/tmp/omrs-ai-draft-blocks-shots')


def seed(vault):
    images = [store.add_image(vault, 'data:image/png;base64,' + base64.b64encode(support.png(shade)).decode(),
                             'blocks-browser', 'blocks-run') for shade in (120, 225)]
    body = {'subject': '数学', 'category': '函数与导数', 'difficulty': 5,
            'knowledge_points': ['导数'], 'cause': '遗漏区间端点', 'cause_statement': '遗漏区间端点',
            'source_images': [image['sha256'] for image in images], 'blocks': [
                {'section': '题目', 'kind': 'text', 'text': '已知函数 $f(x)=x^2$。'},
                {'section': '题目', 'kind': 'text', 'text': '（1）求 $f(2)$。'},
                {'section': '题目', 'kind': 'text', 'text': '（2）说明函数的单调性。'},
                {'section': '答案', 'kind': 'text', 'text': '第一问：$f(2)=4$。'},
                {'section': '答案', 'kind': 'text', 'text': '第二问：导数为 $2x$。'},
            ]}
    def create(name, payload):
        return store.create_draft(vault, payload, {'conversation_id': 'blocks-browser',
                    'run_id': 'blocks-run', 'tool_call_id': name})
    first = create('first', body)
    second = create('second', {**body, 'category': '下一题', 'blocks': body['blocks'][:1]})
    mobile = create('mobile', {**body, 'category': '窄屏多块'})
    return first, second, mobile, images


def run(page, base, first, second, images, check):
    def item():
        return support.api(base, '/api/drafts/item?id=' + first['id'])['draft']
    def row(key):
        return page.locator(f'.drf-block[data-key="{key}"]')
    def menu(key, name):
        row(key).locator('[data-action="create.draftBlockMenu"]').click()
        page.get_by_role('menuitem', name=name, exact=True).click()
    def keys(section):
        return page.locator('.drf-review-' + section + ' .drf-block').evaluate_all('els => els.map(e => e.dataset.key)')
    def saved():
        return support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存') && !document.querySelector('.drf-detail [aria-busy=true]')")
    q1, q2, q3, a1, a2 = [block['id'] for block in first['blocks']]
    page.goto(base + '/?unlocked=1#/create', wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    page.locator(f'.drf-item[data-arg="{first["id"]}"]').click()
    check('默认同时阅读题目、答案和信息摘要', page.locator('.drf-review-info').is_visible()
          and page.locator('.drf-review-answer').is_visible() and page.locator('[data-input="create.draftBlockText"]').count() == 0)
    width = page.locator('.drf-review-content').bounding_box()['width']
    check('1440 桌面正文宽于 700 像素', width > 700, str(width))
    row(q1).locator('[data-action="create.draftEditBlock"]').click()
    editor = page.locator('[data-input="create.draftBlockText"]')
    editor.fill('已知函数 $f(x)=x^2$，请分别回答。')
    editor.press('End')
    page.keyboard.type(' 补充条件。')
    check('逐字输入保留焦点和选区，编辑块没有重复预览', editor.evaluate('e => document.activeElement === e && e.selectionStart === e.value.length')
          and row(q1).locator('.drf-md').count() == 0)
    row(q2).locator('[data-action="create.draftEditBlock"]').click()
    check('换块只打开一个编辑框且保留上一块内容', editor.count() == 1 and '补充条件' in row(q1).inner_text())
    editor.fill('（1）求 $f(2)$ 并写出过程。')
    row(q2).locator('[data-action="create.draftEditBlock"]').click()
    menu(q2, '下移')
    check('同组下移保持相邻块身份', keys('question') == [q1, q3, q2])
    menu(q2, '上移')
    menu(q2, '在下方插入文字块')
    inserted = editor.get_attribute('data-arg')
    check('在下方插入后立即聚焦新块', keys('question') == [q1, q2, inserted, q3]
          and editor.evaluate('e => document.activeElement === e'))
    revision = item()['revision']
    page.locator('[data-action="create.draftSave"]').click()
    check('空块阻止暂存并保留新块', support.wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('文字块不能为空')")
          and item()['revision'] == revision)
    page.locator('[data-action="create.draftLocateIssue"]').click()
    check('底部检查定位空文字块', editor.get_attribute('data-arg') == inserted and editor.evaluate('e => document.activeElement === e'))
    editor.fill('补充说明：先求导数，再讨论正负。')
    menu(inserted, '移到答案')
    check('跨组移动追加到目标组末尾', keys('question') == [q1, q2, q3] and keys('answer') == [a1, a2, inserted])
    menu(q3, '删除块')
    page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
    check('取消删除保留块与修改', keys('question') == [q1, q2, q3])
    menu(q3, '删除块')
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('确认删除仅移除当前块', keys('question') == [q1, q2])
    page.locator('[data-action="create.draftSave"]').click()
    check('完整暂存保留原块 id 和组内顺序', saved() and [block['id'] for block in item()['blocks'][:4]] == [q1, q2, a1, a2])
    new_id = item()['blocks'][-1]['id']
    check('新块保存后继续编辑服务端身份', editor.get_attribute('data-arg') == new_id
          and '补充说明' in editor.input_value() and new_id != inserted)
    editor.fill('补充说明：这段需要保存后再切题。')
    page.locator('[data-change="create.draftFilter"]').select_option('done')
    page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
    check('取消筛选切换恢复下拉值和本地内容', page.locator('[data-change="create.draftFilter"]').input_value() == 'pending'
          and '保存后再切题' in editor.input_value())
    page.locator(f'.drf-item[data-arg="{second["id"]}"]').click()
    page.get_by_role('button', name='保存并离开', exact=True).click()
    check('切题保存保护真实写入后才离开', support.wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{second['id']}')")
          and '保存后再切题' in item()['blocks'][-1]['text'])
    page.locator(f'.drf-item[data-arg="{first["id"]}"]').click()
    check('重新读取恢复多块并回到阅读模式', support.wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{first['id']}')")
          and keys('answer') == [a1, a2, new_id] and editor.count() == 0)
    page.locator('[data-action="create.draftEditFields"]').click()
    difficulty = page.locator('[data-input="create.draftField"][data-arg="difficulty"]')
    difficulty.fill('11')
    page.locator('[data-action="create.draftLocateIssue"]').click()
    check('非法难度可从底部定位字段并阻止入库', difficulty.evaluate('e => document.activeElement === e')
          and page.locator('[data-action="create.draftCommit"]').is_disabled())
    difficulty.fill('5')
    subject = page.locator('[data-input="create.draftField"][data-arg="subject"]')
    subject.fill('')
    page.locator('[data-action="create.draftLocateIssue"]').click()
    check('缺失科目定位到正确输入框', subject.evaluate('e => document.activeElement === e'))
    subject.fill('数学')
    page.locator('[data-action="create.draftEditFields"]').click()
    page.locator('.drf-review-question [data-action="create.draftAddImage"]').click()
    source_ref = next(image['ref'] for image in item()['source_images'] if image['sha256'] == images[1]['sha256'])
    page.get_by_role('menuitem', name=source_ref, exact=True).click()
    note = page.locator('[data-input="create.draftBlockNote"]')
    image_key = note.get_attribute('data-arg')
    note.fill('补充题图')
    menu(image_key, '移到答案')
    check('图片跨组移动保留预览与说明', keys('answer')[-1] == image_key and note.input_value() == '补充题图')
    page.locator('[data-action="create.draftLocateIssue"]').click()
    check('未框图片定位到对应来源和图片区块', page.locator('.drf-source-workspace').is_visible()
          and page.locator('#drf-canvas-block').input_value() == image_key)
    page.locator('.drf-source-trigger').click()
    row(image_key).locator('[data-action="create.draftWhole"]').click()
    page.locator('[data-action="create.draftSave"]').click()
    check('图文混排暂存保留 SHA、整图框和说明', saved() and (lambda block: block['kind'] == 'image'
          and block['image_sha'] == images[1]['sha256'] and block['note'] == '补充题图'
          and block['box'] == {'x': 0, 'y': 0, 'w': 1, 'h': 1})(item()['blocks'][-1]))
    page.locator('[data-action="create.draftCommit"]').click()
    check('图文草稿入库后进入下一题', support.wait(page, f"() => document.querySelector('.drf-id') && !document.querySelector('.drf-id').textContent.includes('{first['id']}')")
          and item()['status'] == 'done' and bool(item()['uid']))
    page.locator('[data-change="create.draftFilter"]').select_option('done')
    page.locator(f'.drf-item[data-arg="{first["id"]}"]').click()
    check('已入库正文只读且来源原图仍保留', page.locator('[data-action="create.draftBlockMenu"], [data-action="create.draftEditBlock"], [data-action="create.draftAddText"]').count() == 0
          and len(item()['source_images']) == 2)
    page.locator('[data-change="create.draftFilter"]').select_option('pending')
    page.locator(f'.drf-item[data-arg="{second["id"]}"]').click()
    page.locator('[data-action="create.draftDiscard"]').click()
    page.locator('dialog[open] .ui-dialog__foot [data-dialog-cancel]').click()
    check('取消丢弃仍可继续审核', page.locator('[data-action="create.draftCommit"]').is_enabled())
    page.locator('[data-action="create.draftDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('已丢弃正文只读', support.wait(page, "() => document.querySelector('.drf-detail h2')?.textContent.includes('已丢弃')")
          and page.locator('[data-action="create.draftEditBlock"]').count() == 0)


def audit(browser, base, mobile, check):
    for theme in ('light', 'dark'):
        for width in (320, 390, 1024, 1440):
            touch = width < 760
            ctx = browser.new_context(viewport={'width': width, 'height': 844 if touch else 900}, is_mobile=touch, has_touch=touch)
            ctx.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(base + '/?unlocked=1#/create', wait_until='networkidle')
                page.locator('#create-flow [data-ib-stage="drafts"]').click()
                if touch:
                    check(f'{theme}·{width} 队列默认折叠', not page.locator('.drf-item').first.is_visible())
                    page.locator('[data-action="create.draftToggleQueue"]').tap()
                page.locator(f'.drf-item[data-arg="{mobile["id"]}"]').click()
                support.wait(page, f"() => document.querySelector('.drf-id')?.textContent.includes('{mobile['id']}')")
                page.evaluate('document.fonts.ready')
                page.screenshot(path=str(SHOTS / f'{theme}-{width}.png'), full_page=True)
                findings = page.evaluate(support.AUDIT)
                check(f'{theme}·{width} 连续正文无溢出且控件可点击', not errors and not findings['overflow']
                      and not findings['tiny'] and not findings['inline'] and not findings['handlers']
                      and page.locator('.drf-review-info').is_visible() and page.locator('.drf-review-answer').is_visible(), str(findings))
                block = page.locator('.drf-review-question .drf-block').first
                more = block.locator('[data-action="create.draftBlockMenu"]')
                more.click()
                check(f'{theme}·{width} 首块上移禁用', page.get_by_role('menuitem', name='上移', exact=True).get_attribute('aria-disabled') == 'true')
                page.keyboard.press('Escape')
                check(f'{theme}·{width} 菜单 Esc 返回触发按钮', more.evaluate('e => document.activeElement === e'))
                if touch:
                    edit = block.locator('[data-action="create.draftEditBlock"]')
                    edit.tap()
                    editor = page.locator('[data-input="create.draftBlockText"]')
                    editor.fill('触摸编辑仍然保留多块正文。')
                    check(f'{theme}·{width} 触摸编辑保留焦点', editor.evaluate('e => document.activeElement === e')
                          and edit.bounding_box()['height'] >= 40)
            finally:
                ctx.close()


def main():
    from playwright.sync_api import sync_playwright
    results = []
    SHOTS.mkdir(exist_ok=True)
    def check(name, passed, detail=''):
        results.append((name, bool(passed), detail))
        if not passed:
            raise AssertionError(name + ': ' + detail)
    with tempfile.TemporaryDirectory(prefix='omrs-draft-blocks-') as vault:
        subprocess.run([sys.executable, str(Path(ROOT, 'tests/fixtures/make_vault.py')), '--out', vault, '--profile', 'empty'],
                       check=True, stdout=subprocess.DEVNULL)
        first, second, mobile, images = seed(vault)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, '-c', support.SERVER, vault, str(port)], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    support.api(base, '/api/status'); break
                except OSError:
                    time.sleep(.1)
            with sync_playwright() as p:
                browser = launch_chromium(p)
                ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: errors.append(message.text) if '[events]' in message.text else None)
                try:
                    run(page, base, first, second, images, check)
                    check('真实主路径没有脚本错误或未注册动作', not errors, str(errors))
                    audit(browser, base, mobile, check)
                except Exception as error:
                    page.screenshot(path=str(SHOTS / 'failure.png'), full_page=True)
                    results.append(('多块主路径执行', False, repr(error)))
                finally:
                    ctx.close()
                    if not os.environ.get('OMRS_TEST_CDP_URL'):
                        browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    for name, passed, detail in results:
        print(('PASS' if passed else 'FAIL') + ' ' + name + (': ' + detail if detail else ''))
    print(f'{sum(passed for _, passed, _ in results)} / {len(results)}')
    return 0 if results and all(passed for _, passed, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
