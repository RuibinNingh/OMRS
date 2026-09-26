"""Shared Playwright browser launcher for OMRS test scripts.

Set OMRS_TEST_CDP_URL to use a trusted, local Chromium CDP endpoint instead
of spawning a separate browser process.
"""
import os


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
