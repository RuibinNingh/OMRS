"""Shared Playwright browser launcher for OMRS test scripts.

Set OMRS_TEST_CDP_URL to use a trusted, local Chromium CDP endpoint instead
of spawning a separate browser process.
"""
import os
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


CDP_TIMEOUT_MS = 15000


def launch_chromium(playwright, *, executable=None, args=None):
    """Connect to an explicitly configured CDP browser or launch Chromium."""
    endpoint = os.environ.get("OMRS_TEST_CDP_URL", "").strip()
    if endpoint:
        return playwright.chromium.connect_over_cdp(
            endpoint,
            timeout=CDP_TIMEOUT_MS,
        )

    options = {}
    if executable:
        options["executable_path"] = executable
    if args is not None:
        options["args"] = args
    return playwright.chromium.launch(**options)


def app_url(base, route="dashboard"):
    """普通页面验收明确进入主应用；入口/PIN专项仍直接访问锁屏。"""
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query))
    query["unlocked"] = "1"
    return urlunsplit((parts.scheme, parts.netloc, "/", urlencode(query), "/" + route))


def open_app(page, base, route="dashboard", *, timeout=15000):
    """等待真实模块和目标面板就绪，不注入生产状态或绕过 PIN 会话。"""
    page.goto(app_url(base, route), wait_until="networkidle")
    page_id = route.split("?", 1)[0]
    page.wait_for_function(
        "id => !!window.__omrs && window.__omrs.router.current() === id "
        "&& document.querySelector('.content > .panel.active')?.id === 'panel-' + id",
        arg=page_id, timeout=timeout,
    )
