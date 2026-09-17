"""Independent tests for the UI-free workflow runner."""

import queue
import threading
import time
import unittest

from clickflow.models import MouseAction, Step, Workflow
from clickflow.runner import DirectActionExecutor, IsolatedActionExecutor, RunnerEvent, WorkflowRunner
from clickflow.steps import format_elapsed


def blocking_action(_action: MouseAction) -> None:
    """Top-level target so it also works with multiprocessing spawn."""

    time.sleep(5)


class RunnerTests(unittest.TestCase):
    def run_runner(self, workflow: Workflow, *, action=None, condition=None, random_uniform=None):
        events: list[RunnerEvent] = []
        actions: list[MouseAction] = []
        options = {"action_executor": DirectActionExecutor(action or actions.append)}
        if condition is not None:
            options["condition_evaluator"] = condition
        if random_uniform is not None:
            options["random_uniform"] = random_uniform
        WorkflowRunner(workflow, events.append, **options).run()
        return events, actions

    def test_runs_steps_and_emits_typed_events(self) -> None:
        steps = (Step("move", 10, 20, 0, id="move"), Step("click", 30, 40, 0, id="click"))
        events, actions = self.run_runner(Workflow(steps))
        self.assertEqual(actions, [step.action for step in steps])
        self.assertEqual([event.type for event in events], [
            "step_started", "step_completed", "step_started", "step_completed", "completed"
        ])
        self.assertEqual(events[0].step_id, "move")
        self.assertEqual(events[3].completed_operations, 2)

    def test_id_jump_survives_insert_and_reorder(self) -> None:
        target = Step("move", 3, 3, 0, id="target")
        skipped = Step("click", 2, 2, 0, id="inserted")
        source = Step("click", 1, 1, 0, id="source", on_success=target.id)
        events, actions = self.run_runner(Workflow((source, skipped, target)))
        self.assertEqual(actions, [source.action, target.action])
        self.assertNotIn("inserted", [event.step_id for event in events])

    def test_backward_jump_loop_can_be_cancelled(self) -> None:
        actions: list[MouseAction] = []
        holder: list[WorkflowRunner] = []
        first = Step("click", 1, 1, 0, id="first", on_success="second")
        second = Step("move", 2, 2, 0, id="second", on_success="first")

        def execute(action: MouseAction) -> None:
            actions.append(action)
            if len(actions) == 4:
                holder[0].cancel()

        events: list[RunnerEvent] = []
        runner = WorkflowRunner(
            Workflow((first, second)), events.append,
            action_executor=DirectActionExecutor(execute),
        )
        holder.append(runner)
        runner.run()

        self.assertEqual(actions, [first.action, second.action, first.action, second.action])
        self.assertEqual(events[-1].type, "stopped")

    def test_pause_freezes_condition_and_step_timeouts(self) -> None:
        condition_ready = threading.Event()
        action_called = threading.Event()
        events: queue.Queue[RunnerEvent] = queue.Queue()
        step = Step(
            "click", 1, 2, 0, id="paused", condition="mouse_at",
            condition_timeout_seconds=0.05, timeout_seconds=0.06,
        )
        runner = WorkflowRunner(
            Workflow((step,)), events.put,
            action_executor=DirectActionExecutor(lambda _action: action_called.set()),
            condition_evaluator=lambda _condition: condition_ready.is_set(),
        )
        runner.start()
        time.sleep(0.015)
        runner.pause()
        time.sleep(0.10)
        condition_ready.set()
        runner.resume()
        runner.join(0.5)
        self.assertTrue(action_called.is_set())
        self.assertEqual(list(events.queue)[-1].type, "completed")

    def test_step_timeout_uses_failure_id_branch(self) -> None:
        failed = Step("click", 1, 1, 0.04, id="slow", timeout_seconds=0.01, on_failure="fallback")
        fallback = Step("move", 2, 2, 0, id="fallback")
        events, actions = self.run_runner(Workflow((failed, fallback)))
        self.assertEqual(actions, [fallback.action])
        self.assertEqual(events[-1].type, "completed")

    def test_retry_and_whole_workflow_loop(self) -> None:
        attempts = 0
        actions: list[MouseAction] = []

        def flaky(action: MouseAction) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("once")
            actions.append(action)

        step = Step("click", 1, 2, 0, id="retry", retry_count=1)
        events, _ = self.run_runner(Workflow((step,), repeat_count=2), action=flaky)
        self.assertEqual(attempts, 3)
        self.assertEqual(len(actions), 2)
        self.assertIn("step_retry", [event.type for event in events])

    def test_cancel_terminates_isolated_blocking_action(self) -> None:
        events: queue.Queue[RunnerEvent] = queue.Queue()
        runner = WorkflowRunner(
            Workflow((Step("click", 1, 2, 0, id="blocked"),)), events.put,
            action_executor=IsolatedActionExecutor(blocking_action),
        )
        runner.start()
        time.sleep(0.08)
        started = time.monotonic()
        runner.cancel()
        runner.join(0.8)
        self.assertFalse(runner.is_alive)
        self.assertLess(time.monotonic() - started, 0.8)
        self.assertEqual(list(events.queue)[-1].type, "stopped")


class StatisticsFormattingTests(unittest.TestCase):
    def test_formats_and_clamps_elapsed_time(self) -> None:
        self.assertEqual(format_elapsed(65.9), "00:01:05")
        self.assertEqual(format_elapsed(3661), "01:01:01")
        self.assertEqual(format_elapsed(-1), "00:00:00")


if __name__ == "__main__":
    unittest.main()
