"""录入题目 P6 分步迁移：工作区导航、上传与快速录入主路径。"""
import os
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


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = b''.join(b'\0' + b'\xff\xff\xff' * 64 for _ in range(64))
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
          and page.locator('#ib-grid [data-ib-open]').count() == 1)
    page.evaluate("""bytes => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(bytes)], '题图.png', { type: 'image/png' }));
      document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    }""", list(png()))
    check('上传区粘贴图片走同一暂存入口，重复图自动合并',
          wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('已合并')")
          and page.locator('#ib-grid [data-ib-open]').count() == 1)
    page.route('**/api/inbox/upload', lambda route: route.fulfill(status=503, content_type='application/json', body='{"msg":"上传服务暂不可用"}'))
    page.locator('#ib-file').set_input_files({'name': '另一张.png', 'mimeType': 'image/png', 'buffer': png()})
    check('上传失败保留已有收件箱并在控件旁显示原因',
          wait(page, "() => document.querySelector('#ib-up-status')?.textContent.includes('上传服务暂不可用')")
          and page.locator('#ib-grid [data-ib-open]').count() == 1)
    page.unroute('**/api/inbox/upload')
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
    page.click('#cr-btn')
    check('快速录入成功写入题库', wait(page, "() => !!document.querySelector('#cr-result .create-result.ok')"))


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
