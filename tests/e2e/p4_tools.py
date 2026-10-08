"""P4 隔离 Vault 真浏览器：分类确认、零题候选、草稿修订卡与审核跳转。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, ROOT)
from browser_runtime import launch_chromium  # noqa: E402
from fixtures.make_vault import free_port  # noqa: E402
from omrs.common import save_config  # noqa: E402


def main():
    from playwright.sync_api import sync_playwright
    checks, errors = [], []
    with tempfile.TemporaryDirectory(prefix="omrs-p4-") as vault:
        subprocess.run([sys.executable, os.path.join(ROOT, "tests/fixtures/make_vault.py"), "--out", vault],
                       check=True, stdout=subprocess.DEVNULL)
        save_config(vault, {"agent_enabled": True})
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, OMRS_AGENT_FAUX_SCRIPT=os.path.join(ROOT, "tests/fixtures/agent_p4_faux.json"))
        env.pop("OMRS_SYSTEMD_SERVICE", None)
        with tempfile.TemporaryFile(mode="w+") as log:
            proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "omrs_engine.py"), "--vault", vault,
                                     "serve", "-p", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(base + "/api/auth/session", timeout=2)
                        break
                    except OSError:
                        time.sleep(0.2)
                with sync_playwright() as playwright:
                    browser = launch_chromium(playwright)
                    page = browser.new_page(viewport={"width": 390, "height": 844})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base + "/#/assistant", wait_until="networkidle")

                    def check(label, value):
                        checks.append((label, bool(value)))

                    def send(message):
                        page.fill("#ast-input", message)
                        page.click(".ast-send")

                    send("创建零题分类")
                    page.wait_for_selector(".ast-op.is-waiting", timeout=15000)
                    check("分类工具进入确认级别", page.locator(".ast-tool.is-waiting").count() == 1)
                    page.click(".ast-op.is-waiting [data-action='assistant.gate']")
                    page.wait_for_selector('.arv-operation')
                    check("对话内详情明确永久创建", "不支持按运行自动撤销" in page.locator('.arv-operation').text_content() and '#/assistant' in page.url)
                    page.click('[data-action="ai-review.approve"]')
                    page.wait_for_function("() => !document.querySelector('[data-action=\"ai-review.approve\"]')")
                    page.locator('.ast-review-panel [data-drawer-close]').click()
                    page.locator('.ast-review-panel').wait_for(state='detached')
                    page.wait_for_function("() => document.querySelectorAll('.ast-turn:not(.is-live)').length >= 1")
                    check("无 Ledger 的分类写入显示活动预算", "写入 1" in page.locator(".ast-turn:last-of-type .ast-foot").text_content())
                    check("分类写入不显示自动撤销", page.locator(".ast-turn:last-of-type [data-action='assistant.undo']").count() == 0)
                    with urllib.request.urlopen(base + "/api/taxonomy") as response:
                        taxonomy = json.load(response)["taxonomy"]
                    check("零题分类进入统一词表", "矩阵" in taxonomy["categories_by_subject"]["数学"])
                    check("分类卡可见", "矩阵" in page.locator(".ast-turn:last-of-type").text_content())
                    page.goto(base + "/#/create", wait_until="networkidle")
                    page.click('[data-action="create.stage"][data-arg="quick"]')
                    page.fill("#cr-subject", "数学")
                    page.focus("#cr-category")
                    check("快速录入候选包含零题分类", "矩阵" in page.locator(".ui-combobox-menu:not([hidden])").text_content())
                    page.goto(base + "/#/assistant", wait_until="networkidle")
                    send("修改草稿")
                    page.wait_for_function("() => document.querySelectorAll('.ast-turn:not(.is-live)').length >= 2", timeout=30000)
                    check("草稿写入计入活动预算", "写入 2" in page.locator(".ast-turn:last-of-type .ast-foot").text_content())
                    check("修订卡显示新版本", page.locator(".ast-turn:last-of-type .ast-draft-card").count() >= 1
                          and "已保存第" in page.locator(".ast-turn:last-of-type").text_content())
                    page.locator('.ast-turn:last-of-type [data-action="assistant.openDraft"]').last.click()
                    page.wait_for_selector(".ast-review-panel #ib-stage-drafts", timeout=8000)
                    check("审核页显示修订正文", "修订答案" in page.locator("#ib-stage-drafts").text_content())
                    check("手机无页面横向溢出", page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
                    browser.close()
            finally:
                proc.terminate()
                proc.wait(timeout=10)
    for label, passed in checks:
        print(("通过" if passed else "失败") + "：" + label)
    for error in errors:
        print("页面错误：" + error)
    print(f"P4 E2E {sum(passed for _, passed in checks)}/{len(checks)}")
    return 0 if checks and all(passed for _, passed in checks) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
