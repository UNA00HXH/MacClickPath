"""macOS GUI integration checks that never control the real mouse."""

import platform
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import ClickFlowApp
from clickflow.models import AccessibilityPermission, ExecutionState, Step


@unittest.skipUnless(platform.system() == "Darwin", "macOS Tk integration test")
class GuiAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        permission_patch = patch(
            "app.get_accessibility_permission",
            return_value=AccessibilityPermission.GRANTED,
        )
        position_patch = patch(
            "app.pyautogui.position",
            return_value=SimpleNamespace(x=100, y=200),
        )
        countdown_patch = patch("app.START_COUNTDOWN_SECONDS", 0)
        self.addCleanup(permission_patch.stop)
        self.addCleanup(position_patch.stop)
        self.addCleanup(countdown_patch.stop)
        permission_patch.start()
        position_patch.start()
        countdown_patch.start()
        self.window = ClickFlowApp()
        self.window.withdraw()
        self.addCleanup(self._close_window)

    def _close_window(self) -> None:
        if self.window.winfo_exists():
            self.window._on_close()

    def _pump_until(self, expected: ExecutionState, timeout: float = 1.5) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.window.update()
            if self.window._execution_state is expected:
                return
            time.sleep(0.005)
        self.fail(f"状态未在限定时间内变为 {expected.value}")

    @patch("app.perform_action")
    def test_ordered_run_updates_progress_and_count(self, perform_action) -> None:
        steps = [
            Step("move", 10, 20, 0.02),
            Step("click", 30, 40, 0.02),
        ]
        self.window.steps = steps
        self.window._refresh_steps_table()

        self.window._start_execution()
        self._pump_until(ExecutionState.COMPLETED)

        self.assertEqual(
            [call.args[0] for call in perform_action.call_args_list], steps
        )
        self.assertEqual(self.window.step_progress.get(), "当前步骤：2 / 2")
        self.assertEqual(self.window.completed_display.get(), "已完成操作：2 次")
        self.assertFalse(self.window._editor_locked)
        self.assertEqual(
            self.window.steps_table.item("step-1", "tags"), ("current_step",)
        )

    @patch("app.perform_action")
    def test_pause_resume_and_stop_keep_window_responsive(
        self, perform_action
    ) -> None:
        self.window.steps = [Step("click", 30, 40, 1.0)]
        self.window._refresh_steps_table()
        heartbeats = 0

        def heartbeat() -> None:
            nonlocal heartbeats
            heartbeats += 1
            self.window.after(5, heartbeat)

        self.window.after(0, heartbeat)
        self.window._start_execution()
        self.window._pause_execution()
        pause_deadline = time.monotonic() + 0.06
        while time.monotonic() < pause_deadline:
            self.window.update()
            time.sleep(0.005)

        self.assertEqual(self.window._execution_state, ExecutionState.PAUSED)
        self.window._resume_execution()
        self.window._stop_execution()
        self._pump_until(ExecutionState.STOPPED)

        self.assertGreater(heartbeats, 2)
        self.assertFalse(self.window._editor_locked)
        perform_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
