"""AI 助手页：隔离 Vault + 假模型（OMRS_AGENT_FAUX_SCRIPT）的真实浏览器流程与版式审计。

覆盖：入口显示、空状态权限表、流式回答与引用芯片、需确认写入（对话框允许 / 内联拒绝）、停止、运行中插话、
检查器、按运行撤销、窄屏抽屉；审计无行内样式（KaTeX 除外）、无横向溢出。用法：python3 tests/e2e/assistant.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, ROOT)
from browser_runtime import launch_chromium  # noqa: E402

FAUX = os.path.join(ROOT, "tests", "fixtures", "agent_faux.json")
AUDIT = """() => {
  const root = document.getElementById('panel-assistant');
  const shown = [...root.querySelectorAll('*')].filter(e => e.getClientRects().length && !e.closest('.katex'));
  return { inline: shown.filter(e => (e.getAttribute('style') || '').trim()).map(e => e.className).slice(0, 5),
           overflow: document.documentElement.scrollWidth > innerWidth + 1 };
}"""


def make_vault():
    vault = tempfile.mkdtemp(prefix="omrs-ast-")
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "fixtures", "make_vault.py"), "--out", vault], check=True,
                   stdout=subprocess.DEVNULL)
    from omrs.common import save_config
    save_config(vault, {"agent_enabled": True})
    return vault


def start(vault, port):
    env = dict(os.environ, OMRS_AGENT_FAUX_SCRIPT=FAUX)
    env.pop("OMRS_SYSTEMD_SERVICE", None)
    log = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "omrs_engine.py"), "--vault", vault, "serve", "-p", str(port)],
                            env=env, stdout=log, stderr=log)
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auth/session", timeout=2)
            break
        except OSError:
            time.sleep(0.2)
    return proc


def api(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main():
    from playwright.sync_api import sync_playwright
    from fixtures.make_vault import free_port
    vault, port = make_vault(), free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(vault, port)
    results, errors = [], []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), str(detail)[:300]))

    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: m.type == "error" and errors.append(m.text[:300]))
            page.goto(f"{base}/#/assistant", wait_until="networkidle")
            page.wait_for_selector(".ast-empty", timeout=8000)
            check("侧栏入口在启用后显示", page.is_visible('.tab[data-tab="assistant"]'))
            check("空状态列出四级权限", page.locator(".ast-perm__row").count() == 4)

            def say(text):
                page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)  # 弹窗关闭动画结束后再输入
                page.fill("#ast-input", text)
                page.press("#ast-input", "Enter")

            def done(n, timeout=30000):
                page.wait_for_function(f"() => document.querySelectorAll('.ast-turn:not(.is-live)').length >= {n}", timeout=timeout)

            say("找一下和「周期」有关的题")
            page.wait_for_selector(".ast-turn.is-live", timeout=5000)
            page.fill("#ast-input", "顺便看看数列")
            page.press("#ast-input", "Enter")
            done(1)
            last = ".ast-turn:last-of-type"
            check("流式回答完成并渲染引用芯片", page.locator(f"{last} .ast-md .ast-ref").count() >= 1)
            check("运行中插话显示为送达的插话", page.wait_for_selector(f"{last} .ast-user--steer", timeout=3000) is not None,
                  page.locator(f"{last} .ast-user--steer").first.text_content() if page.locator(f"{last} .ast-user--steer").count() else "")
            page.locator(f"{last} .ast-md .ast-ref").first.click()
            check("点引用芯片打开题目", page.wait_for_selector("dialog[open]", timeout=5000) is not None)
            page.keyboard.press("Escape")
            check("Esc 关闭题目弹窗", page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000) is not None)

            say("帮我把今天要复习的题排出来，8 道以内。另外三角函数1的错因补一下")
            page.wait_for_selector(".ast-gate", timeout=20000)
            check("需确认写入先停在确认卡", page.locator(".ast-tool.is-waiting").count() == 1)
            page.click(".ast-gate [data-action='assistant.gate']")
            page.wait_for_selector(".ast-gate-dlg", timeout=5000)
            check("确认框展示现在 / 修改后", page.locator(".ast-gate-dlg .ast-diff__box").count() >= 2)
            page.click(".ast-gate-dlg [data-gate='allow']")
            done(2)
            check("允许后写入两条 commit", "写入 2" in page.locator(f"{last} .ast-foot").text_content())
            md = api(base, "/api/question?uid=" + urllib.request.quote("三角函数1")).get("markdown", "")
            check("错因写进题目文件", "第二象限" in json.dumps(api(base, "/api/question/raw?uid=" + urllib.request.quote("三角函数1")), ensure_ascii=False) or "第二象限" in md)

            page.click("[data-action='assistant.toggleInsp']")
            check("检查器列出写入记录", page.wait_for_selector(".ast-insp .ast-commit", timeout=3000) is not None)
            check("检查器画出时间线", page.locator(".ast-insp svg.ast-wf rect").count() >= 4)

            say("第一道做错了，自评 3 分；第二道做对了，8 分")
            page.wait_for_selector(".ast-gate", timeout=20000)
            page.click(".ast-gate [data-action='assistant.deny']")
            done(3)
            check("内联拒绝后反馈没有执行", page.locator(f"{last} .ast-tool.is-denied").count() == 1)

            page.locator(".ast-turn").nth(1).locator("[data-action='assistant.undo']").click()
            page.wait_for_selector(".ui-dialog .ast-undo-list", timeout=5000)
            page.click(".ui-dialog [data-dialog-ok]")
            page.wait_for_function("() => document.querySelectorAll('.ast-turn')[1].querySelector('.ast-foot')?.textContent.includes('已撤销')", timeout=10000)
            check("按运行撤销成功", True)
            check("撤销后 Ledger 仍有效", api(base, "/api/ledger/verify").get("valid", True))

            say("最近哪块最弱？")
            page.wait_for_selector("[data-action='assistant.stop']", timeout=5000)
            page.click("[data-action='assistant.stop']")
            done(4)
            check("停止后运行标为已中止", "已中止" in page.locator(f"{last} .ast-foot").text_content())

            audit = page.evaluate(AUDIT)
            check("桌面：没有行内样式、没有横向溢出", not audit["inline"] and not audit["overflow"], audit)

            page.goto(f"{base}/#/settings", wait_until="networkidle")
            page.click("#st-tab-assistant")
            page.wait_for_function("() => document.getElementById('st-agent-enabled')?.checked === true", timeout=5000)
            page.uncheck("#st-agent-enabled")
            page.click("[data-action='settings.saveAgent']")
            page.wait_for_function("() => document.querySelector('.tab[data-tab=\"assistant\"]').hidden", timeout=5000)
            check("设置里关闭后侧栏入口隐藏", api(base, "/api/agent/status")["enabled"] is False)
            page.check("#st-agent-enabled")
            page.click("[data-action='settings.agentTest']")
            page.wait_for_function("() => document.getElementById('st-agent-status')?.textContent.includes('连接正常')", timeout=10000)
            check("测试连接成功且入口恢复", page.is_visible('.tab[data-tab="assistant"]'))

            mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            mobile.goto(f"{base}/#/assistant", wait_until="networkidle")
            mobile.wait_for_selector(".ast-turn", timeout=8000)
            audit = mobile.evaluate(AUDIT)
            check("390px：没有行内样式、没有横向溢出", not audit["inline"] and not audit["overflow"], audit)
            mobile.click("[data-action='assistant.toggleRail']")
            mobile.wait_for_timeout(400)
            check("390px：对话列表从左侧抽屉打开", mobile.evaluate("() => document.querySelector('.ast').dataset.rail === 'open' && document.querySelector('.ast-rail').getBoundingClientRect().left >= 0"))
            browser.close()
    except Exception as exc:  # noqa: BLE001
        results.append(("执行出错", False, repr(exc)[:400]))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(vault, ignore_errors=True)
    check("页面没有脚本错误", not errors, errors[:3])
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
    print(f"{len(results) - len(failed)}/{len(results)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
