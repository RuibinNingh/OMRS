"""分档复核的真实页面闭环；临时Vault与随机高端口，不访问生产数据。"""
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.browser_runtime import open_app, launch_chromium
from tests.visual import run as visual
from omrs.common import business_today
from omrs.creation import create_question
from omrs.feedback import process_feedback


def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix="omrs-review-policy-e2e-") as work:
        vault = str(Path(work) / "vault")
        today = business_today()
        fresh, due, sleeping = [create_question(vault, "数学", category, 5, question_text="求 $x+1=2$ 的解。", answer_text="$x=1$")
                                for category in ("首次击杀", "到期复核", "低分巩固")]
        for question, days in ((due, 7), (sleeping, 1)):
            with patch("omrs.feedback.business_today", return_value=today - datetime.timedelta(days=days)):
                process_feedback(vault, [{"uid": question["uid"], "sub_score": 9, "is_correct": True}])
        proc, port = visual.start_server(str(ROOT), vault, str(Path(work) / "server.log"))
        base = f"http://127.0.0.1:{port}"
        results = []

        def http(path, body=None):
            request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)

        def check(name, condition):
            results.append(name)
            assert condition, name
            print("通过：" + name, flush=True)

        def item(uid):
            return next(row for row in http("/api/stats")["items"] if row["uid"] == uid)

        def submit(page, question, score=9, correct=True):
            before = {session["session_id"] for session in http("/api/sessions")["sessions"]}
            http("/api/confirm-schedule", {"selected": [{"uid": question["uid"], "source": "due"}], "persist": True})
            sid = next(session["session_id"] for session in http("/api/sessions")["sessions"] if session["session_id"] not in before)
            open_app(page, base, "dashboard")
            open_app(page, base, "feedback")
            page.locator("#fb-session-picker").select_option(sid)
            page.locator(".fbw-verdict__btn--ok").wait_for()
            page.locator(".fbw-panel__title").click()
            page.keyboard.press("1" if correct else "2")
            page.keyboard.press(str(score))
            with page.expect_response(lambda response: response.url.endswith("/api/feedback") and response.request.method == "POST") as response:
                page.locator('[data-action="feedback.submit"]').click()
            page.locator("dialog[open] .fbw-result__row").wait_for()
            result = response.value.json()["results"][0]
            text = page.locator("dialog[open]").inner_text()
            check("反馈结果显示状态与实际日期：" + question["uid"], result["label"] in text and result["new_due_date"] in text)
            page.locator("dialog[open] [data-dialog-ok]").click()
            return result

        try:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.set_default_timeout(10000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                result = submit(page, fresh)
                check("一次高分即可击杀并安排7天复核", result["label"] == "已击杀" and result["revive_stage"] == 1 and result["new_due_date"] == (today + datetime.timedelta(days=7)).isoformat())
                open_app(page, base, "dashboard")
                check("仪表盘今日待复习包含已击杀的到期复核题", int(page.locator(".dsh-today__value").inner_text()) == 1)
                open_app(page, base, "schedule")
                page.locator(".schd-cand").filter(has_text=due["uid"]).wait_for()
                check("复习调度显示复燃与当前第1档", "复燃" in page.locator(".schd-cand").filter(has_text=due["uid"]).inner_text())
                result = submit(page, due)
                check("到期高分升至第2档21天", result["revive_stage"] == 2 and result["new_interval"] == 21)
                before = item(due["uid"])
                submit(page, due)
                after = item(due["uid"])
                check("提前高分反馈保留档位、累计次数和原日期", all(before[key] == after[key] for key in ("revive_stage", "kill_count", "next_revive_date", "revive_anchor_at")))
                result = submit(page, due, 2, False)
                check("答错退出击杀且1天后重练", result["revive_stage"] == 0 and result["new_interval"] == 1 and result["new_mastery"] == .3)
                result = submit(page, sleeping, 6)
                check("低分答对退出击杀且3天后巩固", result["label"] == "磨合中" and result["revive_stage"] == 0 and result["new_interval"] == 3)
                result = submit(page, sleeping)
                check("重新击杀回到第1档7天", result["revive_stage"] == 1 and result["new_interval"] == 7)
                open_app(page, base, "questions")
                check("题库显示复核档位", page.get_by_text("复核第 1 档", exact=True).count() >= 1)
                page.locator(".qlb-status[data-status=kill]").first.wait_for()
                page.locator(".qlb-status[data-status=kill]").first.click()
                page.wait_for_function("() => !!document.querySelector('dialog[open]')")
                check("题目详情可见复核日期", "下次复核" in page.locator("dialog[open]").inner_text())
                page.keyboard.press("Escape")
                open_app(page, base, "data")
                page.wait_for_function("() => !!document.querySelector('#panel-data').textContent.includes('到期')")
                check("复盘接口同时返回复核档位和实际日期", all("revive_stage" in row and "next_revive_date" in row for row in http("/api/analytics")["items"]))
                open_app(page, base, "settings")
                page.locator('[data-action="settings.section"][data-arg="data"]').click()
                page.locator("#st-tuning-revive_intervals_days").wait_for()
                page.wait_for_function("() => !document.querySelector('#st-tuning-save').disabled")
                check("设置显示五档间隔并移除旧连对配置", page.locator("#st-tuning-revive_intervals_days").input_value() == "7,21,60,120,180" and page.locator("#st-tuning-kill_streak").count() == 0)
                page.locator("#st-tuning-revive_intervals_days").fill("7,21,21,120,180")
                page.locator("#st-tuning-save").click()
                check("设置拒绝非递增间隔并保留输入", "五个严格递增的正整数" in page.locator("#st-tuning-status").inner_text())
                page.locator("#st-tuning-revive_intervals_days").fill("8,22,61,121,181")
                with page.expect_response(lambda response: response.url.endswith("/api/config") and response.request.method == "POST") as saved:
                    page.locator("#st-tuning-save").click()
                check("设置通过真实接口重算历史并回传五档数组", saved.value.json()["tuning_effective"]["revive_intervals_days"] == [8, 22, 61, 121, 181])
                page.wait_for_function("() => document.querySelector('#st-tuning-status').textContent.includes('历史重算完成')")
                page.set_viewport_size({"width": 390, "height": 844})
                check("手机设置无横向溢出", page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
                check("完整闭环无页面脚本错误", not errors)
                context.close()
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        print(f"E2E review_policy：{len(results)}项通过")


if __name__ == "__main__":
    main()
