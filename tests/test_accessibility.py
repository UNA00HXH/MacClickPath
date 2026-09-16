"""Tests for macOS Accessibility permission handling."""

import unittest
from unittest.mock import Mock, patch

from clickflow.accessibility import (
    get_accessibility_permission,
    open_accessibility_settings,
)
from clickflow.models import AccessibilityPermission


class AccessibilityPermissionTests(unittest.TestCase):
    @patch("clickflow.accessibility.platform.system", return_value="Linux")
    def test_non_macos_is_distinct_from_check_failure(self, _system) -> None:
        self.assertIs(
            get_accessibility_permission(),
            AccessibilityPermission.NOT_MACOS,
        )

    @patch("clickflow.accessibility.ctypes.CDLL", side_effect=OSError)
    @patch("clickflow.accessibility.ctypes.util.find_library", return_value=None)
    @patch("clickflow.accessibility.platform.system", return_value="Darwin")
    def test_framework_load_failure_has_explicit_result(
        self, _system, _find_library, _cdll
    ) -> None:
        self.assertIs(
            get_accessibility_permission(),
            AccessibilityPermission.CHECK_FAILED,
        )

    @patch("clickflow.accessibility.subprocess.run")
    @patch("clickflow.accessibility.platform.system", return_value="Darwin")
    def test_open_settings_uses_fallback(self, _system, run) -> None:
        run.side_effect = [
            OSError("deep link unavailable"),
            Mock(),
        ]

        self.assertTrue(open_accessibility_settings())
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
