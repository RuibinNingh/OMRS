"""三种权限的真实页面与重启送审；临时 Vault、随机端口、假模型，无生产连接。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from browser_runtime import launch_chromium, open_app
from fixtures.make_vault import free_port

spec = importlib.util.spec_from_file_location('assistant_support', ROOT / 'tests/e2e/assistant.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def main():
    from playwright.sync_api import sync_playwright
    from omrs import ai_review
    from omrs.question_ops import get_question_raw
    vault, port = support.make_vault(), free_port()
    base = f'http://127.0.0.1:{port}'
    uid = '三角函数1'
    faux = Path(vault) / 'permission-faux.json'
    faux.write_text(json.dumps({'scenarios': [
        {'match': label, 'rounds': [{'tool_calls': [{'name': 'update_question_section',
          'arguments': {'uid': uid, 'section': '答案', 'content': answer}}]}, {'text': '已收到工具处理结果。'}]}
        for label, answer in [('手动写入', '手动答案'), ('滞留写入', '滞留答案'),
                              ('危险写入', '危险答案'), ('超时写入', '超时答案'), ('切换写入', '切换答案')]
    ]}, ensure_ascii=False))
    # 只在隔离测试进程缩短「超时写入」等待；正式默认的 600 秒由单测核对。
    runner = Path(vault) / 'permission-server.py'
    runner.write_text(f'''import sys
sys.path.insert(0, {str(ROOT)!r})
from omrs.agent import runtime
from omrs.cli import main
original = runtime.Hooks.before_tool_call
def before(self, call, tool):
    if call.get('args', {{}}).get('content') != '超时答案':
        return original(self, call, tool)
    ttl = runtime.CONFIRM_TTL_SECONDS
    runtime.CONFIRM_TTL_SECONDS = 0.4
    try:
        return original(self, call, tool)
    finally:
        runtime.CONFIRM_TTL_SECONDS = ttl
runtime.Hooks.before_tool_call = before
main()
''')
    logs = tempfile.NamedTemporaryFile(mode='w+', prefix='omrs-permission-server-', suffix='.log', delete=False)
    def start():
        env = {**os.environ, 'OMRS_AGENT_FAUX_SCRIPT': str(faux)}
        env.pop('OMRS_SYSTEMD_SERVICE', None); env.pop('OMRS_BOXDETECT_CONTROL', None)
        proc = subprocess.Popen([sys.executable, str(runner), '--vault', vault, 'serve', '-p', str(port)],
                                env=env, stdout=logs, stderr=logs)
        for _ in range(100):
            try:
                urllib.request.urlopen(base+'/api/auth/session', timeout=1)
                return proc
            except OSError:
                time.sleep(0.1)
        raise AssertionError('测试服务没有启动：'+logs.name)
    proc = start()
    checks, errors = [], []
    def check(name, passed, detail=''):
        checks.append(name)
        print(('PASS ' if passed else 'FAIL ')+name+(f'：{detail}' if detail else ''), flush=True)
        if not passed:
            raise AssertionError(name)
    shots = Path(os.environ.get('OMRS_PERMISSION_SHOTS', '/tmp/omrs-permission-shots'))
    shots.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: print('HTTP', response.status, response.url, response.text()[:500], flush=True)
                    if response.status >= 400 and '/api/' in response.url else None)
            open_app(page, base, route='assistant')
            page.locator('.ast-mode').wait_for()
            check('新对话默认手动', page.locator('.ast-mode').inner_text().strip() == '手动模式')
            check('桌面默认隐藏对话栏并保留入口', not page.locator('.ast-rail').is_visible()
                  and page.locator('[data-action="assistant.toggleRail"]').is_visible())
            page.locator('[data-action="assistant.toggleRail"]').click()
            page.locator('.ast-rail').wait_for(state='visible')
            check('桌面对话栏可以展开', page.locator('.ast-rail').is_visible())
            page.locator('[data-action="assistant.toggleRail"]').click()

            def choose(mode):
                page.locator('.ast-mode').click()
                page.get_by_role('menuitem', name={'hold': '滞留模式', 'danger': '危险模式', 'manual': '手动模式'}[mode], exact=False).click()
                page.wait_for_function('(mode) => document.querySelector(".ast-mode")?.textContent.includes(mode)',
                                       arg={'hold': '滞留模式', 'danger': '危险模式', 'manual': '手动模式'}[mode])
            def say(text):
                page.locator('#ast-input').fill(text)
                page.locator('[data-action="assistant.send"]').click()
                page.locator('.ast-op').wait_for()
            def finish():
                try:
                    page.wait_for_function('() => !!document.querySelector(".ast-turn") && !document.querySelector(".ast-turn.is-live")')
                except Exception:
                    page.screenshot(path=str(shots/'failure.png'), full_page=True)
                    print('页面诊断', page.locator('#panel-assistant').inner_text()[-2500:], flush=True)
                    print('运行诊断', support.api(base, '/api/agent/status'), flush=True)
                    raise
            def op_id():
                return page.locator('.ast-op').last.get_attribute('data-operation')
            def open_detail():
                page.locator('.ast-op').last.locator('[data-action="assistant.gate"]').click()
                page.locator('.ast-review-panel[open] .arv-operation').wait_for()
            def close_detail():
                page.locator('.ast-review-panel[open] [data-drawer-close]').click()
                page.wait_for_function('() => !document.querySelector(".ast-review-panel[open]")')
            def new():
                old = support.api(base, '/api/agent/conversations')['conversations'][0]['id'] if page.locator('.ast-op').count() else ''
                page.locator('#ast-head [data-action="assistant.newConv"]').click()
                page.wait_for_function('() => !document.querySelector(".ast-turn") && document.querySelector(".ast-mode")?.textContent.includes("手动模式")')
                return old

            original = get_question_raw(vault, uid)['markdown']
            say('手动写入')
            page.locator('[data-action="assistant.defer"]').wait_for()
            first = op_id()
            check('手动请求显示 10 分钟倒计时且未写入', '后自动送审' in page.locator('.ast-op__expiry').inner_text()
                  and ai_review.get(vault, first)['expires_at']-ai_review.get(vault, first)['created_at'] >= 599
                  and get_question_raw(vault, uid)['markdown'] == original)
            page.locator('[data-action="assistant.defer"]').click()
            finish()
            page.wait_for_function('() => document.querySelector(".ast-op")?.textContent.includes("已送审核")')
            check('手动送审释放聊天并保留长期提案', ai_review.get(vault, first)['expires_at'] is None)
            open_detail()
            page.locator('.ast-review-panel[open] [data-action="ai-review.approve"]').click()
            page.wait_for_function('() => document.querySelector(".arv-operation")?.textContent.includes("当前状态：已执行")')
            close_detail()
            page.locator('[data-action="assistant.undo"]').wait_for()
            check('审核后聊天显示完成和撤销入口', ai_review.get(vault, first)['status'] == 'applied'
                  and '手动答案' in get_question_raw(vault, uid)['markdown'])

            new(); choose('hold'); say('滞留写入'); finish()
            second = op_id()
            page.wait_for_function('() => document.querySelector(".ast-op")?.textContent.includes("已送审核")')
            check('滞留请求直接送审且不显示聊天批准按钮', not page.locator('[data-action="assistant.approve"]').count()
                  and ai_review.get(vault, second)['permission']['reason'] == 'hold')
            proc.terminate(); proc.wait(timeout=10); proc = start()
            page.reload(wait_until='networkidle')
            page.locator('.ast-op').wait_for()
            check('刷新和普通重启保留滞留模式与待审提案', '滞留模式' in page.locator('.ast-mode').inner_text()
                  and ai_review.get(vault, second)['status'] == 'pending_confirmation')
            page.locator('#ast-input').fill('保留输入')
            open_detail()
            check('中心详情展示送审原因和长期待审', '滞留模式直接送审' in page.locator('.arv-facts').inner_text()
                  and '长期待审' in page.locator('.arv-facts').inner_text())
            page.locator('.ast-review-panel[open] [data-action="ai-review.approve"]').click()
            page.wait_for_function('() => document.querySelector(".arv-operation")?.textContent.includes("当前状态：已执行")')
            close_detail()
            check('聊天结束后中心批准真实写入且保留输入', '滞留答案' in get_question_raw(vault, uid)['markdown']
                  and page.locator('#ast-input').input_value() == '保留输入')

            new(); choose('danger'); say('危险写入'); finish()
            third = op_id()
            page.wait_for_function('() => document.querySelector(".ast-op")?.textContent.includes("危险模式 · 自动同意")')
            check('危险模式自动批准并标明真实完成', ai_review.get(vault, third)['status'] == 'applied'
                  and '危险答案' in get_question_raw(vault, uid)['markdown'] and '自动同意全部权限请求' in page.locator('.ast-mode-note').inner_text())
            open_detail()
            check('危险决定记入来源而不是用户点击', '危险模式 · 自动同意' in page.locator('.arv-facts').inner_text()
                  and '模式设置来源' in page.locator('.arv-facts').inner_text())
            close_detail()
            saved = ai_review.detail(vault, third)['decision']
            choose('manual')
            check('切换模式保留已经完成的决定', ai_review.detail(vault, third)['decision'] == saved)

            new(); say('超时写入'); finish()
            fourth = op_id()
            page.wait_for_function('() => document.querySelector(".ast-op")?.textContent.includes("等待已满 10 分钟")')
            check('手动超时自动移交而不是丢弃', ai_review.get(vault, fourth)['status'] == 'pending_confirmation'
                  and ai_review.get(vault, fourth)['permission']['reason'] == 'timeout')
            open_detail()
            page.locator('.ast-review-panel[open] [data-action="ai-review.reject"]').click()
            page.locator('.ui-dialog[open] [data-dialog-ok]').click()
            page.wait_for_function('() => document.querySelector(".arv-operation")?.textContent.includes("当前状态：已拒绝")')
            close_detail()
            check('中心拒绝不产生写入', '危险答案' in get_question_raw(vault, uid)['markdown'])

            new(); say('切换写入')
            page.locator('[data-action="assistant.defer"]').wait_for()
            fifth = op_id()
            choose('danger'); finish()
            check('等待中切到危险模式处理当前请求', ai_review.get(vault, fifth)['status'] == 'applied'
                  and '切换答案' in get_question_raw(vault, uid)['markdown'])
            for width in (320, 390, 736, 1024, 1440):
                for theme in ('light', 'dark'):
                    page.set_viewport_size({'width': width, 'height': 900})
                    page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
                    page.locator('.ast-mode').click()
                    menu = page.get_by_role('menu', name='选择权限模式')
                    menu.wait_for()
                    dimensions = page.evaluate('''() => {
                      const menu = document.querySelector('[role="menu"][aria-label="选择权限模式"]').getBoundingClientRect();
                      const mode = document.querySelector('.ast-mode').getBoundingClientRect();
                      return { overflow: document.documentElement.scrollWidth > innerWidth+1,
                        menuFits: menu.left>=0 && menu.right<=innerWidth+1 && menu.top>=0 && menu.bottom<=innerHeight+1,
                        modeFits: mode.left>=0 && mode.right<=innerWidth+1, modeHeight: mode.height };
                    }''')
                    check(f'{width}px/{theme} 权限入口与菜单可见且无横向溢出', not dimensions['overflow']
                          and dimensions['menuFits'] and dimensions['modeFits'] and (width>760 or dimensions['modeHeight']>=40), dimensions)
                    if width in (390, 1440):
                        page.screenshot(path=str(shots/f'permission-{theme}-{width}.png'), full_page=True)
                    page.keyboard.press('Escape')
            check('所有新路径没有脚本错误', not errors, errors)
            browser.close()
        print(f'{len(checks)}/{len(checks)} 通过', flush=True)
    finally:
        proc.terminate(); proc.wait(timeout=10)
        logs.close()
        shutil.rmtree(vault, ignore_errors=True)


if __name__ == '__main__':
    main()
