"""AI 草稿工作区 E2E：真实临时 Vault 与 HTTP API，审核、保存、通过、丢弃及四档页面审计。"""
import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from browser_runtime import launch_chromium
from omrs import drafts

SHOTS = '/tmp/omrs-ai-draft-p2-shots'


def png(shade):
    """本地生成带题目/解析内容的数学测试截图，不读取用户图片。"""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (560, 330), '#ffffff')
    draw = ImageDraw.Draw(image)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    label_font = ImageFont.truetype(font_path, 24) if os.path.exists(font_path) else ImageFont.load_default()
    math_font = ImageFont.truetype(font_path, 38) if os.path.exists(font_path) else ImageFont.load_default()
    heading = 'QUESTION 1' if shade < 200 else 'SOLUTION 1'
    lines = ('f(x) = x^2', 'Find f(2).') if shade < 200 else ('f(2) = 2^2', 'Answer: 4')
    draw.rounded_rectangle((22, 20, 538, 310), radius=18, outline='#9ca3af', width=3)
    draw.text((48, 48), heading, fill='#334155', font=label_font)
    draw.line((48, 93, 510, 93), fill='#cbd5e1', width=2)
    draw.text((48, 125), lines[0], fill='#111827', font=math_font)
    draw.text((48, 204), lines[1], fill='#111827', font=math_font)
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def seed(vault):
    conv = 'draft-e2e-conversation'
    images = [drafts.add_image(vault, 'data:image/png;base64,' + base64.b64encode(png(shade)).decode(), conv, 'run-test')
              for shade in (180, 220)]
    first = drafts.create_draft(vault, {
        'subject': '数学', 'category': '函数', 'knowledge_points': ['导数'], 'cause': '审题不清',
        'cause_statement': '审题不清', 'source_images': [image['sha256'] for image in images],
        'blocks': [
            {'section': '题目', 'kind': 'text', 'text': '已知 $f(x)=x^2$，求 $f(2)$。'},
            {'section': '题目', 'kind': 'image', 'image_sha': images[0]['sha256'], 'note': '图像证据'},
            {'section': '答案', 'kind': 'text', 'text': '答案是 4。'},
        ],
    }, {'conversation_id': conv, 'run_id': 'run-test', 'tool_call_id': 'tool-first'})
    second = drafts.create_draft(vault, {
        'subject': '数学', 'category': '代数', 'knowledge_points': [], 'cause': '', 'cause_statement': '',
        'source_images': [], 'blocks': [{'section': '题目', 'kind': 'text', 'text': '求 1+1。'}],
    }, {'conversation_id': conv, 'run_id': 'run-test', 'tool_call_id': 'tool-second'})
    old = drafts.create_draft(vault, {
        'subject': '数学', 'category': '几何', 'knowledge_points': [], 'cause': '', 'cause_statement': '',
        'blocks': [{'section': '题目', 'kind': 'text', 'text': '旧草稿来源待补。'}],
    }, {'conversation_id': conv, 'run_id': 'run-test', 'tool_call_id': 'tool-old'})
    return first, second, old, images


def api(base, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def wait(page, expr, timeout=10000):
    try:
        page.wait_for_function(expr, timeout=timeout)
        return True
    except Exception:
        return False


AUDIT = """() => {
  const host = document.querySelector('#ib-stage-drafts');
  const shown = [...host.querySelectorAll('*')].filter(e => e.getClientRects().length && !e.closest('.katex'));
  const clickables = shown.filter(e => ['BUTTON','INPUT','SELECT','TEXTAREA'].includes(e.tagName));
  const tiny = clickables.filter(e => { const r=e.getBoundingClientRect(); return r.height < 28; }).map(e => `${e.tagName}:${e.className}:${Math.round(e.getBoundingClientRect().height)}`);
  const overflow = document.documentElement.scrollWidth > innerWidth + 1;
  return { overflow, tiny, inline: shown.filter(e => (e.getAttribute('style') || '').trim()).length,
    handlers: shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length,
    image: shown.filter(e => e.matches('.drf-source img')).length };
}"""


def run(page, base, first, second, old, images, results):
    def check(name, passed, detail=''):
        results.append((name, bool(passed), detail))

    page.goto(base + '/#/create', wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    check('工作区显示三份待审核草稿', wait(page, "() => document.querySelectorAll('.drf-item').length === 3"))
    page.locator(f'.drf-item[data-arg="{first["id"]}"]').click()
    check('来源两图和有序块真实读取', wait(page, "() => document.querySelectorAll('.drf-source img').length === 2 && document.querySelectorAll('.drf-block').length === 3"))
    check('未框图片阻止通过', page.locator('[data-action="create.draftCommit"]').is_disabled())
    page.locator('[data-input="create.draftField"][data-arg="cause"]').fill('计算时漏看平方')
    page.locator('[data-action="create.draftWhole"]').click()
    check('整图框使通过可选且显示未保存', wait(page, "() => !document.querySelector('[data-action=\"create.draftCommit\"]')?.disabled && document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
    page.locator('[data-action="create.draftSave"]').click()
    check('显式保存把框和错因写入真实 API', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存')")
          and (lambda item: item['draft']['cause'] == '计算时漏看平方' and item['draft']['blocks'][1]['box'] == {'x': 0, 'y': 0, 'w': 1, 'h': 1}
               and item['draft']['status'] == 'review')(api(base, '/api/drafts/item?id=' + first['id'])))
    page.locator('[data-action="create.draftCommit"]').click()
    check('通过只创建一次并变只读', wait(page, "() => document.querySelector('.drf-success')?.textContent.includes('已入库')")
          and api(base, '/api/drafts/item?id=' + first['id'])['draft']['status'] == 'done'
          and page.locator('[data-action="create.draftSave"]').count() == 0)
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    page.locator('[data-action="create.draftFilter"][data-arg="pending"]').click()
    page.locator(f'.drf-item[data-arg="{second["id"]}"]').click()
    page.locator('[data-action="create.draftDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('丢弃状态持久且待审核计数减少', wait(page, "() => document.querySelector('.drf-detail h2')?.textContent.includes('已丢弃')")
          and api(base, '/api/drafts/item?id=' + second['id'])['draft']['status'] == 'discarded'
          and api(base, '/api/drafts/counts')['counts']['discarded'] == 1)
    page.locator('[data-action="create.draftFilter"][data-arg="pending"]').click()
    page.locator(f'.drf-item[data-arg="{old["id"]}"]').click()
    check('旧来源不完整提示与可补关联图片', wait(page, "() => document.querySelector('.drf-hint')?.textContent.includes('来源未完整恢复') && document.querySelectorAll('#drf-source-select option').length === 3"))
    page.locator('#drf-source-select').select_option(images[1]['sha256'])
    page.locator('[data-action="create.draftSourceAdd"]').click()
    page.locator('[data-action="create.draftSave"]').click()
    check('补关联按 SHA 保存且来源完整', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('已保存') && !document.querySelector('.drf-detail [aria-busy=true]')")
          and (lambda item: item['draft']['sources_complete'] and images[1]['sha256'] in [image['sha256'] for image in item['draft']['source_images']])
              (api(base, '/api/drafts/item?id=' + old['id'])))
    page.locator('[data-input="create.draftField"][data-arg="note"]').fill('未保存的临时笔记')
    check('编辑备注进入未保存状态', wait(page, "() => document.querySelector('.drf-detail h2')?.textContent.includes('未保存')"))
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    check('离开工作区出现三动作对话框', wait(page, "() => !!document.querySelector('dialog[open]')")
          and page.locator('dialog[open] button').filter(has_text='保存并离开').count() == 1
          and page.locator('dialog[open] button').filter(has_text='放弃修改并离开').count() == 1
          and page.locator('dialog[open] button').filter(has_text='留在当前').count() == 1)
    page.locator('dialog[open] button').filter(has_text='留在当前').click()
    check('选择留在当前保留本地修改', page.locator('#ib-stage-drafts').is_visible()
          and page.locator('[data-input="create.draftField"][data-arg="note"]').input_value() == '未保存的临时笔记')
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('dialog[open] button').filter(has_text='保存并离开').click()
    check('保存后离开且刷新仍可读取', wait(page, "() => document.querySelector('#ib-stage-upload')?.classList.contains('on')")
          and api(base, '/api/drafts/item?id=' + old['id'])['draft']['note'] == '未保存的临时笔记')
    page.reload(wait_until='networkidle')
    page.locator('#create-flow [data-ib-stage="drafts"]').click()
    check('刷新恢复上次选中的草稿', wait(page, f"() => document.querySelector('.drf-detail .drf-id')?.textContent.includes('{old['id']}')"))
    current = api(base, '/api/drafts/item?id=' + old['id'])['draft']
    fields = {name: current[name] for name in ('subject', 'category', 'difficulty', 'knowledge_points', 'labels', 'cause', 'note')}
    fields['note'] = '另一标签页已修改'
    api(base, '/api/drafts/update', {'id': old['id'], 'revision': current['revision'], 'fields': fields,
                                     'blocks': current['blocks'], 'source_images': [image['sha256'] for image in current['source_images']]})
    page.locator('[data-input="create.draftField"][data-arg="note"]').fill('本地修改不能丢')
    page.locator('[data-action="create.draftSave"]').click()
    check('409 显示冲突并保留本地编辑', wait(page, "() => document.querySelector('.drf-message')?.textContent.includes('冲突')")
          and page.locator('[data-input="create.draftField"][data-arg="note"]').input_value() == '本地修改不能丢')
    page.locator('[data-action="create.draftReloadDetail"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('显式重读后采用服务端版本', wait(page, "() => document.querySelector('[data-input=\"create.draftField\"][data-arg=\"note\"]')?.value === '另一标签页已修改'"))
    page.route('**/api/drafts/list?status=pending&limit=500', lambda route: route.fulfill(
        status=503, content_type='application/json', body='{"status":"error","msg":"列表暂不可用"}'))
    page.locator('.drf-list-head [data-action="create.draftReload"]').click()
    check('列表读取失败与空态区分', wait(page, "() => document.querySelector('.drf-list .drf-error')?.textContent.includes('列表暂不可用')"))
    page.unroute('**/api/drafts/list?status=pending&limit=500')
    page.locator('.drf-list .drf-error [data-action="create.draftReload"]').click()
    check('列表失败后可重试', wait(page, "() => !document.querySelector('.drf-list .drf-error') && !!document.querySelector('.drf-item')"))


def main():
    from playwright.sync_api import sync_playwright
    results = []
    os.makedirs(SHOTS, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='omrs-drafts-e2e-') as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        first, second, old, images = seed(vault)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'omrs_engine.py'), '--vault', vault, 'serve', '--port', str(port)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    api(base, '/api/status')
                    break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    run(page, base, first, second, old, images, results)
                except Exception as error:
                    results.append(('草稿主路径执行', False, repr(error)[:500]))
                results.append(('主路径页面脚本无错误', not errors, str(errors[:3])))
                context.close()
                for theme in ('light', 'dark'):
                    for label, width, height in (('desktop', 1440, 900), ('mobile', 390, 844)):
                        audit_context = browser.new_context(viewport={'width': width, 'height': height})
                        audit_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        audit_page = audit_context.new_page()
                        audit_errors = []
                        audit_page.on('pageerror', lambda error: audit_errors.append(str(error)))
                        audit_page.goto(base + '/#/create', wait_until='networkidle')
                        audit_page.locator('#create-flow [data-ib-stage="drafts"]').click()
                        audit_page.locator('[data-action="create.draftFilter"][data-arg="done"]').click()
                        wait(audit_page, "() => document.querySelectorAll('.drf-source img').length === 2")
                        shot = os.path.join(SHOTS, f'{theme}-{label}.png')
                        audit_page.screenshot(path=shot, full_page=True)
                        findings = audit_page.evaluate(AUDIT)
                        results.append((f'草稿界面 {theme}·{label} 审计与截图',
                                        not audit_errors and not findings['overflow'] and not findings['inline']
                                        and not findings['handlers'] and findings['image'] == 2,
                                        str(findings) + ' ' + shot))
                        audit_context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    for name, passed, detail in results:
        print(('PASS' if passed else 'FAIL') + ' ' + name + (': ' + detail if detail else ''))
    print(f'{sum(ok for _, ok, _ in results)} / {len(results)}')
    return 0 if results and all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
