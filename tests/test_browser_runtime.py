import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from browser_runtime import launch_chromium


class LaunchChromiumTests(unittest.TestCase):
    def test_configured_cdp_endpoint_connects_without_spawning_browser(self):
        chromium = Mock()
        chromium.connect_over_cdp.return_value = object()
        playwright = SimpleNamespace(chromium=chromium)

        with patch.dict(os.environ, {"OMRS_TEST_CDP_URL": "  http://127.0.0.1:9222  "}):
            browser = launch_chromium(
                playwright,
                executable="/usr/bin/google-chrome",
                args=["--no-sandbox"],
            )

        self.assertIs(browser, chromium.connect_over_cdp.return_value)
        chromium.connect_over_cdp.assert_called_once_with(
            "http://127.0.0.1:9222", timeout=15000
        )
        chromium.launch.assert_not_called()

    def test_empty_cdp_endpoint_preserves_standalone_launch(self):
        chromium = Mock()
        chromium.launch.return_value = object()
        playwright = SimpleNamespace(chromium=chromium)

        with patch.dict(os.environ, {"OMRS_TEST_CDP_URL": ""}):
            browser = launch_chromium(
                playwright,
                executable="/usr/bin/google-chrome",
                args=["--no-sandbox"],
            )

        self.assertIs(browser, chromium.launch.return_value)
        chromium.launch.assert_called_once_with(
            executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]
        )
        chromium.connect_over_cdp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
