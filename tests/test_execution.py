"""Tests for background execution outcomes."""

import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pyautogui

from app import ClickFlowApp
from clickflow.models import Step
from clickflow.steps import format_elapsed


def make_runner(*, wait_result: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        _stop_event=threading.Event(),
        _run_event=threading.Event(),
        _execution_queue=queue.Queue(),
        _wait_interruptibly=lambda _duration: wait_result,
        _wait_until_resumed=lambda: wait_result,
    )


class BackgroundExecutionTests(unittest.TestCase):
    @patch("app.perform_action")
    def test_runs_move_and_click_steps_in_order(self, perform_action) -> None:
        runner = make_runner()
        steps = [
            Step("move", 10, 20, 0.1),
            Step("click", 30, 40, 0.2),
        ]

        ClickFlowApp._run_steps(runner, steps)

        self.assertEqual(
            [call.args[0] for call in perform_action.call_args_list],
            steps,
        )
        self.assertEqual(
            list(runner._execution_queue.queue),
            [
                ("step_started", "1"),
                ("step_completed", "1"),
                ("step_started", "2"),
                ("step_completed", "2"),
                ("completed", None),
            ],
        )

    @patch("app.perform_action")
    def test_reports_completion(self, perform_action) -> None:
        runner = make_runner()
        step = Step("move", 10, 20, 0.0)

        ClickFlowApp._run_steps(runner, [step])

        perform_action.assert_called_once_with(step)
        self.assertEqual(
            list(runner._execution_queue.queue),
            [
                ("step_started", "1"),
                ("step_completed", "1"),
                ("completed", None),
            ],
        )

    @patch("app.perform_action")
    def test_reports_stop_before_action(self, perform_action) -> None:
        runner = make_runner(wait_result=False)

        ClickFlowApp._run_steps(runner, [Step("click", 10, 20, 1.0)])

        perform_action.assert_not_called()
        self.assertEqual(
            list(runner._execution_queue.queue),
            [("step_started", "1"), ("stopped", None)],
        )

    @patch("app.perform_action", side_effect=RuntimeError("boom"))
    def test_reports_operation_error(self, _perform_action) -> None:
        runner = make_runner()

        ClickFlowApp._run_steps(runner, [Step("click", 10, 20, 0.0)])

        runner._execution_queue.get_nowait()
        event, detail = runner._execution_queue.get_nowait()
        self.assertEqual(event, "error")
        self.assertIn("RuntimeError: boom", detail)

    @patch("app.perform_action")
    def test_operation_error_prevents_later_steps(self, perform_action) -> None:
        runner = make_runner()
        steps = [
            Step("move", 10, 20, 0.0),
            Step("click", 30, 40, 0.0),
            Step("click", 50, 60, 0.0),
        ]
        perform_action.side_effect = [None, RuntimeError("second step failed")]

        ClickFlowApp._run_steps(runner, steps)

        self.assertEqual(perform_action.call_count, 2)
        events = list(runner._execution_queue.queue)
        self.assertNotIn(("step_started", "3"), events)
        self.assertEqual(events[-1][0], "error")

    @patch("app.perform_action", side_effect=pyautogui.FailSafeException)
    def test_reports_failsafe_as_emergency_stop(self, _perform_action) -> None:
        runner = make_runner()

        ClickFlowApp._run_steps(runner, [Step("move", 10, 20, 0.0)])

        runner._execution_queue.get_nowait()
        event, detail = runner._execution_queue.get_nowait()
        self.assertEqual(event, "error")
        self.assertIn("左上角紧急停止", detail)


class InterruptibleWaitTests(unittest.TestCase):
    def test_pause_freezes_remaining_wait(self) -> None:
        runner = make_runner()
        runner._run_event.clear()
        runner._wait_until_resumed = lambda: ClickFlowApp._wait_until_resumed(runner)
        result: list[bool] = []
        worker = threading.Thread(
            target=lambda: result.append(
                ClickFlowApp._wait_interruptibly(runner, 0.02)
            )
        )

        worker.start()
        time.sleep(0.04)
        self.assertTrue(worker.is_alive())
        runner._run_event.set()
        worker.join(timeout=0.3)

        self.assertEqual(result, [True])

    def test_stop_interrupts_a_paused_wait(self) -> None:
        runner = make_runner()
        runner._run_event.clear()
        runner._wait_until_resumed = lambda: ClickFlowApp._wait_until_resumed(runner)
        result: list[bool] = []
        worker = threading.Thread(
            target=lambda: result.append(
                ClickFlowApp._wait_interruptibly(runner, 10.0)
            )
        )

        worker.start()
        time.sleep(0.02)
        runner._stop_event.set()
        worker.join(timeout=0.3)

        self.assertEqual(result, [False])


class StatisticsFormattingTests(unittest.TestCase):
    def test_formats_elapsed_time(self) -> None:
        self.assertEqual(format_elapsed(0), "00:00:00")
        self.assertEqual(format_elapsed(65.9), "00:01:05")
        self.assertEqual(format_elapsed(3661), "01:01:01")

    def test_clamps_negative_elapsed_time(self) -> None:
        self.assertEqual(format_elapsed(-1), "00:00:00")


if __name__ == "__main__":
    unittest.main()
