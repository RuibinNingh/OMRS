"""在隔离 Vault 验证题库和复习调度的录入日期筛选。"""
from datetime import datetime, time, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from omrs.common import business_today
from omrs.creation import create_question
from tests.browser_runtime import launch_chromium, open_app
from tests.fixtures.make_vault import post
from tests.visual.run import start_server
from playwright.sync_api import expect, sync_playwright


def seed(vault, today):
    questions = {}
    cases = [
        ("recent", "数学", "日期甲", 1, True), ("edge", "数学", "日期乙", 6, True),
        ("old", "数学", "日期丙", 7, True), ("occupied", "数学", "日期丁", 0, True),
        ("unmarked", "数学", "日期戊", 0, False), ("physics", "物理", "日期己", 0, True),
    ]
    for name, subject, category, age, _ in cases:
        with patch("omrs.creation.datetime", **{"date.today.return_value": today - timedelta(days=age)}):
            questions[name] = create_question(vault, subject, category, 5, question_text="求 1+1。", answer_text="2")
    return cases, questions


def show_date_editor(page, route):
    if route == "questions":
        page.locator(".qlb-filter-btn").click()
        return page.locator("#qlb-f-entry-date")
    page.locator("#rec-more-filters summary").click()
    return page.locator("#rec-filter-entry-date")


def library_flow(page, base, today, questions):
    uid = lambda name: questions[name]["uid"]
    open_app(page, base, "questions")
    rows = page.locator("tr[data-q-row]")
    expect(rows).to_have_count(len(questions))
    mode = show_date_editor(page, "questions")
    page.locator("#qlb-f-subject").select_option("数学")
    page.locator('.qlb-lblf__btn[data-arg="日期复盘"]').click()
    page.locator('[data-action="questions.seg"][data-arg="due|today"]').click()
    page.locator("#qlb-sort").select_option("entry-desc")
    mode.select_option("7days")
    expect(rows).to_have_count(3)
    assert rows.evaluate_all("rows => rows.map(row => row.dataset.qRow)") == [uid("occupied"), uid("recent"), uid("edge")]
    expect(rows.last.locator("time")).to_have_text((today - timedelta(days=6)).isoformat())
    print("  ok  题库：日期、科目、标记、到期交集与排序")

    rows.nth(1).get_by_role("checkbox").check()
    mode.select_option("custom")
    start = page.locator("#qlb-f-entry-date-from")
    end = page.locator("#qlb-f-entry-date-to")
    apply = page.get_by_role("button", name="应用日期")
    expect(apply).to_be_disabled()
    start.fill(today.isoformat())
    end.fill((today - timedelta(days=1)).isoformat())
    expect(page.locator("#qlb-f-entry-date-error")).to_have_text("开始日期不能晚于结束日期。")
    expect(apply).to_be_disabled()
    expect(rows).to_have_count(3)
    end.fill("")
    apply.click()
    expect(rows).to_have_count(1)
    assert rows.first.get_attribute("data-q-row") == uid("occupied")
    expect(page.locator(".qlb-batch")).to_contain_text("已选 1 题")
    page.locator('.qlb-chip[data-arg="entryDate|"]').click()
    expect(rows).to_have_count(4)
    expect(mode).to_have_value("")
    expect(rows.nth(1).get_by_role("checkbox")).to_be_checked()
    print("  ok  题库：无效草稿、单边范围、单独清除与勾选保留")

    mode.select_option("7days")
    page.locator('[data-action="questions.view"][data-arg="gallery"]').click()
    cards = page.locator(".qlb-gcard")
    expect(cards).to_have_count(3)
    expect(cards.first.locator("time")).to_have_text(today.isoformat())
    page.locator('#qlb-drawer [data-action="questions.saveView"]').click()
    dialog = page.get_by_role("dialog")
    dialog.locator("input").fill("最近录入复盘")
    dialog.get_by_role("button", name="确定").click()
    page.locator('.qlb-views__btn[data-arg="最近录入复盘"]').wait_for()
    saved = page.evaluate("JSON.parse(localStorage.getItem('omrs-question-views'))['最近录入复盘'].fields")
    assert saved["q-filter-entry-date"] == "7days" and not saved["q-filter-entry-date-from"]
    page.reload(wait_until="networkidle")
    show_date_editor(page, "questions")
    page.clock.set_fixed_time(datetime.combine(today + timedelta(days=1), time(2), ZoneInfo("Asia/Shanghai")))
    page.locator('.qlb-views__btn[data-arg="最近录入复盘"]').click()
    # 原视图也保存了「今日到期」，先移除这项，只查看相对录入日随业务日滚动的结果。
    page.locator('.qlb-chip[data-arg="due|"]').click()
    expect(cards).to_have_count(2)
    assert cards.evaluate_all("rows => rows.map(row => row.dataset.qRow)") == [uid("occupied"), uid("recent")]
    print("  ok  题库：画廊显示录入日，跨业务日应用保存的相对视图")


def schedule_flow(page, base, today, questions):
    open_app(page, base, "schedule")
    page.locator(".schd-cand").first.wait_for()
    mode = show_date_editor(page, "schedule")
    page.locator("#rec-subject-v2").select_option("数学")
    page.locator('.schd-lblf[data-arg="日期复盘"]').click()
    page.locator("#rec-filter-due-v2").select_option("today")
    page.locator("#rec-filter-sort-v2").select_option("entry-desc")
    mode.select_option("7days")
    rows = page.locator(".schd-cand")
    expect(rows).to_have_count(2)
    assert rows.evaluate_all("rows => rows.map(row => row.dataset.key)") == [questions[name]["uid"] for name in ("recent", "edge")]
    rows.last.get_by_role("checkbox").check()
    mode.select_option("custom")
    same_day = (today - timedelta(days=1)).isoformat()
    page.locator("#rec-filter-entry-date-from").fill(same_day)
    page.locator("#rec-filter-entry-date-to").fill(same_day)
    page.get_by_role("button", name="应用日期").click()
    expect(rows).to_have_count(1)
    expect(page.locator("#rec-hidden-count")).to_contain_text("1 道已选题被筛选隐藏")
    page.locator("#rec-view-gallery").click()
    expect(rows.first.locator("time")).to_have_text(same_day)
    page.locator('#rec-filter-chips [data-arg="entryDate"]').click()
    expect(rows).to_have_count(3)
    expect(mode).to_have_value("")
    print("  ok  调度：可安排候选、日期组合、自定义、画廊与隐藏已选提示")

    mode.select_option("7days")
    page.locator("#rec-target-count").fill("1")
    page.locator("#rec-suggest").click()
    expect(rows.first.get_by_role("checkbox")).to_be_checked()
    expect(rows.last.get_by_role("checkbox")).not_to_be_checked()
    with page.expect_response("**/api/confirm-schedule") as response:
        page.locator("#rec-confirm").click()
    created = response.value.json()
    expect(page.locator("#sch-tab-plans")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#sch-plan-detail")).to_contain_text("原计划 1 题")
    assert response.value.ok and created["session_type"] == "exp" and created["count"] == 1, created
    detail = page.request.get(f"{base}/api/session?{urlencode({'id': created['session_id']})}").json()
    assert [(entry["question_id"], entry["source"]) for entry in detail["entries"]] == [(questions["recent"]["question_id"], "due")]
    print("  ok  调度：按当前排序替换选择并创建正式计划，核对稳定题目身份和来源")


def audit_layout(browser, base, today):
    shots = os.environ.get("OMRS_ENTRY_DATE_SHOTS")
    for theme in ("light", "dark"):
        for width in (320, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900}, has_touch=width == 320)
            context.add_init_script(f"localStorage.setItem('omrs-theme', {json.dumps(theme)}); localStorage.setItem('omrs-density', 'compact');")
            for route in ("questions", "schedule"):
                page = context.new_page()
                page.set_default_timeout(8000)
                open_app(page, base, route)
                show_date_editor(page, route).select_option("custom")
                field = page.locator(".panel.active .entry-date-field")
                start = field.get_by_label("开始日期")
                start.fill(today.isoformat())
                assert field.evaluate("el => el.scrollWidth <= el.clientWidth + 1 && document.documentElement.scrollWidth <= innerWidth + 1")
                apply = field.get_by_role("button", name="应用日期")
                if width == 320:
                    assert start.evaluate("el => parseFloat(getComputedStyle(el).fontSize) >= 16 && el.getBoundingClientRect().height >= 40")
                    apply.tap()
                else:
                    apply.click()
                chip = '.qlb-chip[data-arg="entryDate|"]' if route == "questions" else '#rec-filter-chips [data-arg="entryDate"]'
                expect(page.locator(chip)).to_have_text(f"录入日期 · {today.isoformat()} 起")
                if shots:
                    target = Path(shots)
                    target.mkdir(parents=True, exist_ok=True)
                    field.evaluate("el => el.scrollIntoView({block: 'center'})")
                    field.screenshot(path=target / f"{route}-{theme}-{width}.png")
                page.close()
                print(f"  ok  日期控件布局 {route} {theme} {width}px")
            context.close()


def main():
    today = business_today()
    with tempfile.TemporaryDirectory(prefix="omrs-entry-date-e2e-") as work:
        vault = str(Path(work) / "vault")
        cases, questions = seed(vault, today)
        proc, port = start_server(str(ROOT), vault, str(Path(work) / "server.log"))
        base = f"http://127.0.0.1:{port}"
        try:
            post(port, "/api/label/save", {"name": "日期复盘", "color": "#dc2626"})
            for name, _, _, _, marked in cases:
                if marked:
                    post(port, "/api/question/labels", {"uid": questions[name]["uid"], "labels": ["日期复盘"]})
            post(port, "/api/confirm-schedule", {"selected": [{"question_id": questions["occupied"]["question_id"], "source": "due"}], "persist": True})
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                context = browser.new_context(viewport={"width": 1440, "height": 900}, timezone_id="America/Los_Angeles")
                page = context.new_page()
                page.set_default_timeout(8000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                fixed_time = datetime.combine(today, time(2), ZoneInfo("Asia/Shanghai"))
                page.clock.set_fixed_time(fixed_time)
                library_flow(page, base, today, questions)
                page.clock.set_fixed_time(fixed_time)
                schedule_flow(page, base, today, questions)
                assert not errors, errors
                context.close()
                audit_layout(browser, base, today)
                if not os.environ.get("OMRS_TEST_CDP_URL"):
                    browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print("E2E entry_date_filters：13 项通过，0 个页面脚本错误")


if __name__ == "__main__":
    main()
