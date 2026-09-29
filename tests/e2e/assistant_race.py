"""真实浏览器排列助手会话响应与旧运行结束顺序；只用临时 Vault。"""
import json
import shutil
import urllib.request

from assistant import api, make_vault, start
from browser_runtime import launch_chromium
from fixtures.make_vault import free_port


def create(base, title):
    request = urllib.request.Request(base + '/api/agent/conversation/create',
                                     data=json.dumps({'title': title}).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)['conversation']['id']


def main():
    from playwright.sync_api import sync_playwright

    vault, port = make_vault(), free_port()
    base = f'http://127.0.0.1:{port}'
    proc = start(vault, port)
    try:
        first, second = create(base, '会话 A'), create(base, '会话 B')
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page()
            page.goto(base + '/#/assistant', wait_until='networkidle')
            page.wait_for_selector(f'.ast-conv[data-arg="{second}"].is-active')
            page.evaluate("""first => {
              const original = window.fetch.bind(window);
              let release;
              const gate = new Promise(resolve => { release = resolve; });
              window.__releaseConversation = release;
              window.__conversationHeld = false;
              window.fetch = async (input, init) => {
                const response = await original(input, init);
                if (String(input).startsWith('/api/agent/conversation?id=' + encodeURIComponent(first))) {
                  window.__conversationHeld = true;
                  await gate;
                }
                return response;
              };
            }""", first)
            page.click(f'.ast-conv[data-arg="{first}"]')
            page.wait_for_function('window.__conversationHeld')
            page.click(f'.ast-conv[data-arg="{second}"]')
            page.wait_for_selector(f'.ast-conv[data-arg="{second}"].is-active')
            page.evaluate('window.__releaseConversation()')
            page.wait_for_timeout(100)
            assert page.locator(f'.ast-conv[data-arg="{second}"].is-active').count() == 1
            print('PASS 迟到的 A 会话响应不覆盖 B')

            page.reload(wait_until='networkidle')
            page.evaluate("""() => {
              const original = window.fetch.bind(window);
              window.__heldRuns = [];
              window.__releaseRuns = {};
              window.fetch = async (input, init) => {
                const response = await original(input, init);
                if (String(input).startsWith('/api/agent/events?')) {
                  const run = new URL(String(input), location.href).searchParams.get('run');
                  if (!window.__releaseRuns[run]) {
                    let release;
                    const gate = new Promise(resolve => { release = resolve; });
                    window.__releaseRuns[run] = {gate, release};
                    window.__heldRuns.push(run);
                  }
                  await window.__releaseRuns[run].gate;
                }
                return response;
              };
            }""")
            page.click(f'.ast-conv[data-arg="{first}"]')
            page.wait_for_selector(f'.ast-conv[data-arg="{first}"].is-active')
            page.fill('#ast-input', '最近哪块最弱？')
            page.press('#ast-input', 'Enter')
            page.wait_for_function('window.__heldRuns.length >= 1')
            page.wait_for_function("async () => (await (await fetch('/api/agent/status')).json()).active.length === 0",
                                   timeout=30000)
            page.click(f'.ast-conv[data-arg="{second}"]')
            page.wait_for_selector(f'.ast-conv[data-arg="{second}"].is-active')
            page.fill('#ast-input', '找一下和周期有关的题')
            for _ in range(30):
                with page.expect_response(lambda response: response.url.endswith('/api/agent/message'), timeout=10000) as sent:
                    page.press('#ast-input', 'Enter')
                if sent.value.status == 200:
                    break
                assert sent.value.status == 409, sent.value.text()
                page.wait_for_timeout(300)
            else:
                raise AssertionError('A 结束后仍无法启动 B')
            page.wait_for_function('window.__heldRuns.length >= 2', timeout=10000)
            page.wait_for_selector('.ast-turn.is-live')
            page.evaluate('window.__releaseRuns[window.__heldRuns[0]].release()')
            page.wait_for_timeout(300)
            assert page.locator(f'.ast-conv[data-arg="{second}"].is-active').count() == 1
            assert page.locator('.ast-turn.is-live').count() == 1
            print('PASS A 运行迟到结束不清除 B 的运行状态')
            page.evaluate('window.__releaseRuns[window.__heldRuns[1]].release()')
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(vault, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
