"""P3 助手主聊天区拖图、站内预览和手机输入布局；隔离 Vault + 假模型浏览器验证。"""
import base64
import shutil
import sys

from assistant import make_vault, start
from fixtures.make_vault import free_port
from browser_runtime import launch_chromium
from tests.test_drafts import make_png


def main():
    from playwright.sync_api import sync_playwright
    vault, port = make_vault(), free_port()
    base = f"http://127.0.0.1:{port}"
    process = start(vault, port)
    results = []
    errors = []

    def check(label, ok):
        results.append((label, bool(ok)))

    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{base}/#/assistant", wait_until="networkidle")
            page.wait_for_selector(".ast-empty")
            png = base64.b64encode(make_png(12, 12)).decode()
            page.evaluate("""async encoded => {
              const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
              const file = new File([bytes], 'chat.png', {type: 'image/png'});
              const transfer = new DataTransfer(); transfer.items.add(file);
              const zone = document.querySelector('.ast-scroll');
              zone.dispatchEvent(new DragEvent('dragenter', {bubbles: true, dataTransfer: transfer}));
              const child = document.querySelector('.ast-stream');
              child.dispatchEvent(new DragEvent('dragenter', {bubbles: true, dataTransfer: transfer}));
              child.dispatchEvent(new DragEvent('dragleave', {bubbles: true, dataTransfer: transfer}));
              window.__p3DragVisible = document.querySelector('.ast-main').classList.contains('is-dragging');
              zone.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: transfer}));
            }""", png)
            page.wait_for_selector(".ast-attachment")
            check("消息区拖图显示统一遮罩并加入待发送图片", page.evaluate("window.__p3DragVisible") and not page.locator('.ast-main').evaluate("e => e.classList.contains('is-dragging')"))
            page.locator('.ast-attachment__preview').click()
            check("待发送图在站内浮层预览", page.locator('dialog.ui-image-viewer[open] img').count() == 1)
            page.keyboard.press('Escape')
            page.wait_for_selector('dialog.ui-image-viewer', state='detached')
            check("Esc 关闭预览并恢复焦点", page.locator('.ast-attachment__preview').evaluate("e => document.activeElement === e"))
            page.fill('#ast-input', '图像测试')
            page.locator('[data-action="assistant.send"]').click()
            page.wait_for_selector('.ast-turn:not(.is-live)', timeout=30000)
            page.locator('.ast-user__images .ast-image').last.click()
            check("历史图片使用持久引用站内预览", page.locator('dialog.ui-image-viewer[open] img').get_attribute('src').startswith('/api/drafts/image?sha='))
            page.go_back(wait_until='domcontentloaded')
            page.wait_for_selector('dialog.ui-image-viewer', state='detached')
            check("返回键关闭图片浮层", page.locator('dialog.ui-image-viewer[open]').count() == 0)
            before = page.locator('.ast-user').count()
            long_text = '长消息内容' * 80
            page.fill('#ast-input', long_text)
            page.locator('#ast-input').dispatch_event('compositionstart')
            page.locator('#ast-input').dispatch_event('compositionend')
            page.press('#ast-input', 'Enter')
            check("桌面输入法确认后紧接 Enter 不误发", page.locator('.ast-user').count() == before)
            page.locator('[data-action="assistant.send"]').click()
            page.wait_for_function(f"() => document.querySelectorAll('.ast-user').length > {before}")
            check("长消息折叠时保留可复制原文", page.locator('.ast-user').last.locator('.ast-user__b').text_content() == long_text and page.locator('.ast-user').last.locator('.ast-user__expand').count() == 1)
            page.locator('.ast-user').last.locator('.ast-user__expand').click()
            page.wait_for_selector('.ast-user__expand[aria-expanded="true"]')
            check("长消息可以展开全文", page.locator('.ast-user').last.locator('.ast-user__expand').get_attribute('aria-expanded') == 'true')

            page.locator('.ast-head [data-action="assistant.newConv"]').click()
            page.wait_for_selector('.ast-empty')
            page.evaluate("""() => {
              const transfer = new DataTransfer(); transfer.setData('text/plain', '普通网页文字');
              const zone = document.querySelector('.ast-scroll');
              zone.dispatchEvent(new DragEvent('dragenter', {bubbles:true, dataTransfer:transfer}));
              window.__p3TextDrag = document.querySelector('.ast-main').classList.contains('is-dragging');
            }""")
            check("文字拖拽不触发文件遮罩", not page.evaluate('window.__p3TextDrag'))
            page.set_input_files('#ast-image-picker', {"name": "notes.pdf", "mimeType": "application/pdf", "buffer": b'%PDF-1.4'})
            page.wait_for_selector('.ui-toast')
            check("PDF 明确提示当前不支持", '只支持 PNG' in page.locator('.ui-toast').last.text_content() and page.locator('.ast-attachment').count() == 0)
            page.evaluate("""() => {
              const original = window.fetch;
              window.__p3OriginalFetch = original;
              window.fetch = async (...args) => {
                if (String(args[0]).includes('/api/agent/conversation?id=')) await new Promise(resolve => setTimeout(resolve, 700));
                return original(...args);
              };
              window.__p3TargetConv = document.querySelector('.ast-conv:not(.is-active)').dataset.arg;
              document.querySelector('.ast-conv:not(.is-active)').click();
            }""")
            page.set_input_files('#ast-image-picker', {"name": "switching.png", "mimeType": "image/png", "buffer": make_png(12, 12)})
            page.wait_for_selector('.ast-attachment')
            page.wait_for_function("() => document.querySelector('.ast-conv.is-active')?.dataset.arg === window.__p3TargetConv")
            check("会话 GET 期间拖图在切换完成后清除", page.locator('.ast-attachment').count() == 0)
            page.evaluate("() => { window.fetch = window.__p3OriginalFetch; delete window.__p3OriginalFetch; }")
            page.evaluate("""() => {
              const original = FileReader.prototype.readAsDataURL;
              FileReader.prototype.readAsDataURL = function(file) { setTimeout(() => original.call(this, file), 500); };
            }""")
            page.set_input_files('#ast-image-picker', {"name": "late.png", "mimeType": "image/png", "buffer": make_png(12, 12)})
            page.wait_for_function("() => document.querySelector('.ast-attachment__pending')")
            check("图片处理中禁止发送", page.locator('[data-action="assistant.send"]').is_disabled())
            page.locator('.ast-head [data-action="assistant.newConv"]').click()
            page.wait_for_timeout(900)
            check("换对话后迟到的读取不串入新对话", page.locator('.ast-attachment').count() == 0)

            for width in (360, 390, 430):
                mobile = browser.new_page(viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True)
                mobile.on("pageerror", lambda error: errors.append(str(error)))
                mobile.goto(f"{base}/#/assistant", wait_until="networkidle")
                mobile.wait_for_selector('#ast-input')
                metrics = mobile.evaluate("""() => ({scroll:document.documentElement.scrollWidth, inner:innerWidth,
                  topbar:getComputedStyle(document.querySelector('.content > .topbar')).display,
                  nav:document.querySelector('.ast-app-toggle').getBoundingClientRect().width})""")
                check(f"{width}px 无页面横向溢出且单层聊天头部 {metrics}", metrics['scroll'] <= metrics['inner'] + 1 and metrics['topbar'] == 'none' and metrics['nav'] >= 44)
                before = mobile.locator('.ast-user').count()
                mobile.fill('#ast-input', '中文输入测试')
                mobile.locator('#ast-input').dispatch_event('compositionstart')
                mobile.press('#ast-input', 'Enter')
                mobile.locator('#ast-input').dispatch_event('compositionend')
                check(f"{width}px 输入法候选和 Enter 不发送", mobile.locator('.ast-user').count() == before and mobile.locator('#ast-input').input_value().startswith('中文输入测试'))
                mobile.evaluate("""() => {
                  Object.defineProperty(window, 'visualViewport', {configurable: true, value: {height: 480, offsetTop: 0, scale: 1}});
                  dispatchEvent(new Event('resize'));
                }""")
                mobile.wait_for_timeout(100)
                check(f"{width}px 可视视口缩短时输入区仍可见", mobile.evaluate("""() => {
                  const dock = document.querySelector('.ast-dock').getBoundingClientRect();
                  return dock.bottom <= 482 && dock.top >= 0;
                }"""))
                mobile.locator('[data-action="assistant.send"]').click()
                mobile.wait_for_selector('.ast-turn:not(.is-live)', timeout=30000)
                mobile.close()
            browser.close()
    except Exception as error:  # noqa: BLE001
        results.append((f"执行出错：{error!r}", False))
    finally:
        process.terminate()
        process.wait(timeout=10)
        shutil.rmtree(vault, ignore_errors=True)
    check("无页面脚本错误", not errors)
    for label, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(f"{sum(ok for _, ok in results)}/{len(results)} 通过")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == '__main__':
    sys.exit(main())
