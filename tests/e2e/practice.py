"""P5：隔离 Vault 真浏览器，聊天练习卡 → 即时练习 → Ledger 幂等与部分成功。"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tests", "e2e"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, ROOT)

from assistant import make_vault, start  # noqa: E402
from browser_runtime import launch_chromium  # noqa: E402
from fixtures.make_vault import free_port  # noqa: E402
from omrs.ledger import connect, read_commits, verify_ledger  # noqa: E402
from omrs.agent.store import AgentStore  # noqa: E402


def review_count(vault):
    return len([c for c in read_commits(vault) if c["commit_type"] == "review.batch_submit"])


def session_count(vault):
    return len([c for c in read_commits(vault) if c["commit_type"] == "session.create"])


def attempts(vault, uid):
    with connect(vault) as db:
        return db.execute("SELECT m.attempts FROM mastery_projection m JOIN question_projection q ON q.question_id=m.question_id WHERE q.uid=?", (uid,)).fetchone()[0]


def main():
    from playwright.sync_api import sync_playwright
    vault, port = make_vault(), free_port()
    proc = start(vault, port)
    base = f"http://127.0.0.1:{port}"
    results = []

    def check(label, condition):
        results.append((label, bool(condition)))

    try:
        before = {uid: attempts(vault, uid) for uid in ("三角函数1", "三角函数2", "三角函数3")}
        reviews_before, sessions_before = review_count(vault), session_count(vault)
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            responses = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("response", lambda r: responses.append((r.status, r.url)) if '/api/agent/' in r.url else None)
            page.goto(base + "/#/assistant", wait_until="networkidle")
            page.wait_for_selector(".ast-empty", timeout=10000)
            page.fill("#ast-input", "给我一张临时练习卡")
            page.click('[data-action="assistant.send"]')
            card_button = page.locator('[data-action="assistant.openPractice"]')
            try:
                card_button.wait_for(timeout=30000)
            except Exception:
                print(page.locator("#panel-assistant").inner_text()[-1800:])
                print("脚本错误：", errors)
                print("响应：", responses[-20:])
                print("输入：", page.locator("#ast-input").input_value())
                raise
            card_id = card_button.get_attribute("data-arg")
            check("聊天显示服务端结构化练习卡", bool(card_id and card_id.startswith("PC-")))
            check("建卡不写反馈或正式 Session", review_count(vault) == reviews_before and session_count(vault) == sessions_before)
            card_button.click()
            page.wait_for_function("() => document.querySelectorAll('#panel-instant .inst-q').length === 3", timeout=12000)
            order = page.locator("#panel-instant .inst-q").evaluate_all("xs => xs.map(x => x.textContent)")
            check("卡片直接进入即时练习，保持明确题序", all(uid in order[i] for i, uid in enumerate(before)))
            check("打开卡片仍不增加 Attempts", all(attempts(vault, uid) == before[uid] for uid in before))
            check("路由只携带 card_id", page.evaluate("location.hash") == f"#/instant?practice={card_id}")

            page.keyboard.press("Space")
            page.click(".inst-verdict__btn--ok")
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => document.querySelectorAll('#panel-instant .inst-q').length === 3", timeout=12000)
            check("刷新恢复未提交判定", page.locator(".inst-verdict__btn--ok").get_attribute("aria-pressed") == "true")

            dropped = {"once": False}

            def lose_response(route):
                if not dropped["once"]:
                    dropped["once"] = True
                    route.fetch()
                    route.abort()
                else:
                    route.continue_()

            page.route("**/api/feedback", lose_response)
            page.click('[data-action="instant.submit"]')
            page.wait_for_function("() => document.querySelector('.inst-sum .inst-state') || document.querySelector('.inst-sum').textContent.includes('提交失败')", timeout=12000)
            check("响应丢失后 Ledger 已真实落账", attempts(vault, "三角函数1") == before["三角函数1"] + 1)
            page.click('[data-action="instant.submit"]')
            page.wait_for_function("() => document.querySelector('.inst-sum').textContent.includes('已提交 1')", timeout=12000)
            check("重试只计一次 Attempts", attempts(vault, "三角函数1") == before["三角函数1"] + 1)
            page.unroute("**/api/feedback", lose_response)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => document.querySelectorAll('#panel-instant .inst-q').length === 3", timeout=12000)
            check("刷新从 Ledger 恢复已提交进度", page.locator(".inst-sum__meta").inner_text().find("已提交 1") >= 0)

            for index in (1, 2):
                page.click(f'.inst-q[data-arg="{index}"]')
                page.click('.inst-card__title')
                page.keyboard.press("Space")
                page.click(".inst-verdict__btn--ok")

            def one_bad(route):
                body = route.request.post_data_json
                body["feedbacks"][0]["sub_score"] = 99
                route.continue_(post_data=__import__("json").dumps(body))

            page.route("**/api/feedback", one_bad)
            page.evaluate("() => { const b=document.querySelector('[data-action=\"instant.submit\"]'); b.click(); b.click(); }")
            page.wait_for_function("() => document.querySelectorAll('.inst-res__row').length === 2", timeout=12000)
            check("三题批次的一题失败不锁定，另一题成功", page.locator(".inst-res__row.is-err").count() == 1
                  and page.locator(".inst-res__row.is-ok").count() == 1
                  and "待提交 1" in page.locator(".inst-sum__meta").inner_text())
            page.unroute("**/api/feedback", one_bad)
            page.click('[data-action="instant.submit"]')
            page.wait_for_function("() => document.querySelector('.inst-sum__meta')?.textContent.includes('已提交 3')", timeout=12000)
            check("修正重试后每题恰好增加一次", all(attempts(vault, uid) == before[uid] + 1 for uid in before))
            check("未创建正式 Session，Ledger 链有效", session_count(vault) == sessions_before and verify_ledger(vault)["valid"])
            page.evaluate("() => { const b=document.querySelector('[data-action=\"instant.restartPractice\"]'); b.click(); b.click(); }")
            page.wait_for_function("() => location.hash.includes('&attempt=')", timeout=12000)
            first_restart = page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('attempt')")
            check("双击重练只签发一个新 attempt", AgentStore(vault).default_practice_attempt(card_id)["attempt_id"] == first_restart)
            page.goto(base + "/#/assistant", wait_until="networkidle")
            page.locator('[data-action="assistant.openPractice"]').wait_for(timeout=12000)
            page.click('[data-action="assistant.openPractice"]')
            page.wait_for_function("() => document.querySelectorAll('#panel-instant .inst-q').length === 3", timeout=12000)
            check("从聊天卡再进入续最新一轮", AgentStore(vault).default_practice_attempt(card_id)["attempt_id"] == first_restart)
            page.goto(base + f"/#/instant?practice={card_id}&attempt={first_restart}", wait_until="networkidle")

            dropped_restart = {"done": False}

            def lose_restart(route):
                route.fetch()
                route.abort()
                dropped_restart["done"] = True

            page.route("**/api/agent/practice/start", lose_restart)
            page.click('[data-action="instant.restartPractice"]')
            for _ in range(100):
                if dropped_restart["done"]:
                    break
                page.wait_for_timeout(50)
            check("重练请求已在服务端成功但响应丢失", dropped_restart["done"])
            page.unroute("**/api/agent/practice/start", lose_restart)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => new URLSearchParams(location.hash.split('?')[1]).get('attempt') !== null", timeout=12000)
            recovered = page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('attempt')")
            check("旧 attempt URL 下重练响应丢失，刷新恢复新 attempt", recovered != first_restart
                  and AgentStore(vault).default_practice_attempt(card_id)["attempt_id"] == recovered)
            check("页面脚本错误为零", not errors)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(vault, ignore_errors=True)
    for name, ok in results:
        print(("  ok    " if ok else "  FAIL  ") + name)
    print(f"E2E practice：{sum(ok for _, ok in results)}/{len(results)} 通过")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
