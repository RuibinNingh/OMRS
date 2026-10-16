"""端到端测试复用真实导航；不注入页面业务状态。"""
import time


def open_drafts(page):
    tab = page.locator('.sidebar-nav [data-tab="ai-review"]')
    tab.wait_for(state='attached')
    if not tab.is_visible():
        page.locator('.topbar-hamburger[data-action="app.drawer"]').click()
    tab.click()
    page.locator('#panel-ai-review.active').wait_for(state='visible')
    kind = page.locator('[data-change="ai-review.type"]')
    kind.wait_for(state='attached')
    back = page.locator('[data-action="ai-review.back"]')
    if not kind.is_visible() and back.is_visible():
        back.click()
    kind.select_option('draft')


def ensure_assistant_rail(page, selector):
    from playwright.sync_api import TimeoutError as BrowserTimeout
    page.wait_for_selector(selector, state='attached')
    deadline = time.monotonic() + 5
    while True:
        if page.locator('#panel-assistant .ast').get_attribute('data-rail') != 'open':
            page.locator('[data-action="assistant.toggleRail"]').click()
        try:
            page.wait_for_selector(selector, state='visible', timeout=300)
            return
        except BrowserTimeout:
            if time.monotonic() >= deadline:
                raise
