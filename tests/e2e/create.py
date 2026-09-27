"""录入题目 P6 分步迁移：工作区导航、上传与快速录入主路径。"""
import os
import json
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from browser_runtime import launch_chromium

AUDIT = """target => {
  const root = document.querySelector('#ib-stage-quick');
  const shown = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('.katex'));
  const text = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const sizes = [...new Set(shown.filter(text)
    .map(e => parseFloat(getComputedStyle(e).fontSize)))].sort((a,b) => a-b);
  const hit = e => ['BUTTON','INPUT','SELECT','SUMMARY'].includes(e.tagName) || e.getAttribute('role') === 'button';
  const tappable = e => e.matches('input[type="file"], input[type="checkbox"]') && e.closest('label') ? e.closest('label') : e;
  const small = shown.filter(hit).filter(e => { const r=tappable(e).getBoundingClientRect(); return r.width && r.height < target; })
    .map(e => `${e.tagName}#${e.id}.${e.className}:${Math.round(tappable(e).getBoundingClientRect().height)}`);
  const inline = shown.filter(e => (e.getAttribute('style') || '').trim()).length;
  const handlers = shown.filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length;
  const over = shown.filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible')
    .map(e => `${e.tagName}#${e.id}.${e.className}: ${e.scrollWidth}/${e.clientWidth}`);
  return { sizes, small, inline, handlers, over, overflow: document.documentElement.scrollWidth > innerWidth + 1, shown: shown.length };
}"""
AUDIT_UPLOAD = AUDIT.replace("'#ib-stage-quick'", "'#ib-stage-upload'")


def png(shade=255):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = b''.join(b'\0' + bytes([shade]) * 3 * 64 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


def wait(page, expr, timeout=8000):
    try:
        page.wait_for_function(expr, timeout=timeout)
        return True
    except Exception:
        return False


def guarded(results, name, action):
    try:
        action()
    except Exception as error:
        results.append((name + '：执行出错', False, repr(error)[:300]))


def run(page, base, results):
    def check(name, ok):
        results.append((name, bool(ok), ''))

    page.goto(base + '/#/create', wait_until='networkidle')
    check('录入页由 features/create 注册并显示五个工作区',
          wait(page, "() => document.querySelectorAll('#create-flow button[data-ib-stage]').length === 5")
          and page.locator('#create-flow [aria-current="step"]').count() == 1)
    check('工作区导航与上传区没有行内事件和样式',
          page.locator('#create-flow [onclick]').count() == 0
          and page.locator('#create-flow button svg').count() == 2
          and page.locator('#create-upload [onclick], #create-upload [style]').count() == 0)
    page.locator('#ib-file').set_input_files({'name': '说明.txt', 'mimeType': 'text/plain', 'buffer': b'not an image'})
    check('非图片文件在上传区就地提示', wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('请选择图片文件')"))
    page.locator('#ib-file').set_input_files({'name': '题图.png', 'mimeType': 'image/png', 'buffer': png()})
    check('上传进入暂存收件箱并更新待处理数',
          wait(page, "() => document.querySelector('#ib-c-pending')?.textContent === '1'")
          and page.locator('.crw-inbox__grid [data-action="create.gridOpen"]').count() == 1)
    page.evaluate("""bytes => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], '题图.png', { type: 'image/png' }));
      document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    }""", list(png()))
    check('上传区粘贴图片走同一暂存入口，重复图自动合并',
          wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('已合并')")
          and page.locator('.crw-inbox__grid [data-action="create.gridOpen"]').count() == 1)
    page.route('**/api/inbox/upload', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"上传服务暂不可用"}'))
    page.locator('#ib-file').set_input_files({'name': '另一张.png', 'mimeType': 'image/png', 'buffer': png()})
    check('上传失败保留已有收件箱并在控件旁显示原因',
          wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('上传服务暂不可用')")
          and page.locator('.crw-inbox__grid [data-action="create.gridOpen"]').count() == 1)
    page.unroute('**/api/inbox/upload')
    page.locator('[data-action="create.gridFilter"][data-arg="boxed"]').click()
    check('收件箱状态筛选显示空态', page.locator('.crw-inbox__empty').count() == 1)
    page.locator('[data-action="create.gridFilter"][data-arg="all"]').click()
    page.locator('[data-change="create.gridAll"]').check()
    check('全选当前筛选后显示批量操作', page.locator('.crw-inbox__batch.is-open').count() == 1
          and page.locator('.crw-inbox__batch strong').inner_text() == '1 张已选')
    page.locator('[data-action="create.gridClear"]').click()
    check('清空选择后批量操作收起', page.locator('.crw-inbox__batch.is-open').count() == 0
          and not page.locator('[data-change="create.gridAll"]').is_checked())
    page.locator('[data-change="create.gridAll"]').check()
    page.locator('[data-action="create.gridWhole"]').click()
    check('整图批量框选写回旧处理队列并显示框位预览',
          wait(page, "() => !!document.querySelector('.crw-grid-item__status [data-status=\"boxed\"]') && !!document.querySelector('.crw-grid-item__thumb svg rect[data-role=\"question\"]')"))
    page.locator('[data-action="create.gridOpenSelected"]').click()
    check('批量去处理打开所选图片', page.locator('#ib-stage-process').evaluate('(e) => getComputedStyle(e).display !== "none"')
          and page.locator('#ib-pc-fname').inner_text().startswith('题图.png'))
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('[data-action="create.gridOpen"]').click()
    check('点击图片进入对应处理队列', page.locator('#ib-stage-process').evaluate('(e) => getComputedStyle(e).display !== "none"')
          and page.locator('#ib-pc-fname').inner_text().startswith('题图.png'))
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('#create-flow [data-ib-stage="process"]').focus()
    page.keyboard.press('Enter')
    check('键盘可进入处理工作区', page.locator('#ib-stage-process').evaluate('(e) => getComputedStyle(e).display !== "none"')
          and page.locator('#create-flow [data-ib-stage="process"]').get_attribute('aria-current') == 'step')
    page.locator('#create-flow [data-ib-stage="quick"]').click()
    check('快速录入工作区可打开', page.locator('#ib-stage-quick').evaluate('(e) => getComputedStyle(e).display !== "none"'))
    page.evaluate("switchTab('settings'); switchTab('create')")
    check('离开再返回仍停在原工作区', page.locator('#create-flow [data-ib-stage="quick"]').get_attribute('aria-current') == 'step'
          and page.locator('#ib-stage-quick').evaluate('(e) => getComputedStyle(e).display !== "none"'))
    page.fill('#cr-subject', '数学')
    page.fill('#cr-category', '函数')
    page.fill('#cr-question', '求函数的定义域')
    page.fill('#cr-answer', '全体实数')
    page.click('[data-action="create.submit"]')
    check('快速录入成功写入题库', wait(page, "() => !!document.querySelector('#cr-result .crw-result.is-success')"))
    check('提交后保留科目分类并清空题目内容',
          page.locator('#cr-subject').input_value() == '数学'
          and page.locator('#cr-category').input_value() == '函数'
          and page.locator('#cr-question').input_value() == ''
          and page.locator('#cr-answer').input_value() == '')
    page.locator('#cr-q-file').set_input_files({'name': '题目.png', 'mimeType': 'image/png', 'buffer': png()})
    page.locator('#cr-a-file').set_input_files({'name': '答案.png', 'mimeType': 'image/png', 'buffer': png()})
    check('题目与答案图片区各自暂存图片',
          wait(page, "() => document.querySelectorAll('#cr-q-images img').length === 1 && document.querySelectorAll('#cr-a-images img').length === 1"))
    page.evaluate("""bytes => {
      document.querySelector('#cr-a-paste').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], '粘贴答案.png', { type: 'image/png' }));
      document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    }""", list(png()))
    check('切换粘贴目标后图片进入答案区',
          wait(page, "() => document.querySelectorAll('#cr-a-images img').length === 2")
          and page.locator('#cr-q-images img').count() == 1)
    calls = []

    def ai_result(route):
        body = route.request.post_data_json
        calls.append(body)
        mode = body.get('mode')
        if mode == 'classify':
            data = {'subject': '物理', 'category': '动力学', 'difficulty': 7, 'knowledge_tags': ['定义域'], 'labels': []}
        elif mode == 'question_text':
            data = {'mode': mode, 'question_text': '求 $f(x)$ 的定义域'}
        else:
            data = {'mode': mode, 'answer': '答案：全体实数'}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data, ensure_ascii=False))

    page.route('**/api/ai-recognize', ai_result)
    page.click('#cr-classify-btn')
    check('分类识别保留已填科目分类并合并知识点',
          wait(page, "() => document.querySelector('#cr-related')?.value.includes('定义域')")
          and page.locator('#cr-subject').input_value() == '数学'
          and page.locator('#cr-category').input_value() == '函数'
          and page.locator('#cr-diff').input_value() == '7')
    page.click('#cr-question-text-btn')
    page.click('#cr-extract-btn')
    check('题面和答案提取使用各自第一张图片',
          wait(page, "() => document.querySelector('#cr-question')?.value === '求 $f(x)$ 的定义域' && document.querySelector('#cr-answer')?.value === '答案：全体实数'")
          and page.locator('#cr-question').input_value() == '求 $f(x)$ 的定义域'
          and page.locator('#cr-answer').input_value() == '答案：全体实数'
          and [call['mode'] for call in calls] == ['classify', 'question_text', 'answer']
          and all(call.get('image', call.get('question_image', '')).startswith('data:image/png;base64,') for call in calls))
    page.click('[data-action="create.submit"]')
    check('含图提交后上下文仍保留、图片已清空且可加入展示板',
          wait(page, "() => !!document.querySelector('#cr-result .crw-result.is-success') && document.querySelectorAll('#cr-q-images img, #cr-a-images img').length === 0")
          and page.locator('#cr-subject').input_value() == '数学'
          and page.locator('#cr-category').input_value() == '函数'
          and page.locator('#cr-related').input_value() == '定义域'
          and page.locator('[data-action="create.boardAdd"]').count() == 1)
    page.unroute('**/api/ai-recognize')
    page.locator('#create-flow [data-ib-stage="upload"]').click()
    page.locator('[data-change="create.gridSelect"]').check()
    page.route('**/api/inbox/discard', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"模拟丢弃故障"}'))
    page.locator('[data-action="create.gridDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('批量丢弃失败保留选择并就地提示', wait(page, "() => document.querySelector('.crw-inbox__error')?.textContent.includes('模拟丢弃故障')")
          and page.locator('[data-change="create.gridSelect"]').is_checked())
    page.unroute('**/api/inbox/discard')
    page.locator('[data-action="create.gridDiscard"]').click()
    page.locator('dialog[open] [data-dialog-cancel]').last.click()
    check('取消批量丢弃保留图片', page.locator('[data-action="create.gridOpen"]').count() == 1)
    page.locator('[data-action="create.gridDiscard"]').click()
    page.locator('dialog[open] [data-dialog-ok]').click()
    check('确认批量丢弃后网格与选择同步清空', wait(page, "() => document.querySelectorAll('.crw-inbox__grid [data-action=\"create.gridOpen\"]').length === 0")
          and page.locator('.crw-inbox__batch.is-open').count() == 0)


def main():
    from playwright.sync_api import sync_playwright
    results = []
    with tempfile.TemporaryDirectory(prefix='omrs-create-e2e-') as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tests/fixtures/make_vault.py'), '--out', vault, '--profile', 'empty'], check=True, stdout=subprocess.DEVNULL)
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env.pop('OMRS_SYSTEMD_SERVICE', None)
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'omrs_engine.py'), '--vault', vault, 'serve', '--port', str(port)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=.2).close()
                    break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                guarded(results, '录入题目主路径', lambda: run(page, f'http://127.0.0.1:{port}', results))
                results.append(('页面脚本错误为零', not errors, str(errors[:3])))
                context.close()
                for theme in ('light', 'dark'):
                    for label, viewport, target in (('桌面', (1440, 900), 28), ('手机', (390, 844), 40)):
                        audit_context = browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]})
                        audit_context.add_init_script(f"localStorage.setItem('omrs-theme', '{theme}')")
                        audit_page = audit_context.new_page()
                        audit_page.goto(f'http://127.0.0.1:{port}/#/create', wait_until='networkidle')
                        wait(audit_page, "() => !!document.querySelector('#create-grid .crw-inbox__filters') && !!document.querySelector('#create-upload .ui-filedrop') && document.querySelector('#panel-create')?.classList.contains('active') && document.querySelector('#ib-stage-upload')?.classList.contains('on')")
                        audit_page.locator('#ib-file').set_input_files({'name': f'审计-{theme}-{label}.png', 'mimeType': 'image/png', 'buffer': png(180 + len(results) % 60)})
                        wait(audit_page, "() => document.querySelectorAll('.crw-inbox__grid .crw-grid-item').length > 0")
                        upload_audit = audit_page.evaluate(AUDIT_UPLOAD, target)
                        upload_ok = upload_audit['shown'] >= 50 and len(upload_audit['sizes']) <= 6 and min(upload_audit['sizes']) >= 12 and not any(
                            upload_audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'收件箱网格审计 {label}·{theme}', upload_ok, str(upload_audit)))
                        audit_page.locator('#create-flow [data-ib-stage="quick"]').click()
                        audit = audit_page.evaluate(AUDIT, target)
                        ok = len(audit['sizes']) <= 6 and min(audit['sizes']) >= 12 and not any(
                            audit[key] for key in ('small', 'inline', 'handlers', 'over', 'overflow'))
                        results.append((f'快速录入审计 {label}·{theme}', ok, str(audit)))
                        audit_context.close()
                if not os.environ.get('OMRS_TEST_CDP_URL'):
                    browser.close()
        finally:
            proc.terminate(); proc.wait(timeout=10)
    for name, passed, detail in results:
        print(('PASS' if passed else 'FAIL') + ' ' + name + (': ' + detail if detail else ''))
    print(f'{sum(ok for _, ok, _ in results)} / {len(results)}')
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
