"""UI-independent workflow execution engine.

The runner owns flow control, pausable time budgets, cancellation, and events.
It has no Tk dependency; a GUI can consume ``RunnerEvent`` objects from a queue
or callback without exposing UI state to the worker thread.
"""

from __future__ import annotations

import multiprocessing
import queue
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import pyautogui

from .models import Action, Condition, Step, Workflow
from .steps import perform_action
from .workflow import evaluate_condition, validate_workflow


class ExecutionCancelled(Exception):
    """Internal control-flow signal for a requested stop."""


class PausableClock:
    """A monotonic clock whose value does not advance while paused."""

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._paused_at: float | None = None
        self._paused_total = 0.0

    def now(self) -> float:
        with self._lock:
            wall_now = self._paused_at if self._paused_at is not None else self._monotonic()
            return wall_now - self._paused_total

    def pause(self) -> None:
        with self._lock:
            if self._paused_at is None:
                self._paused_at = self._monotonic()

    def resume(self) -> None:
        with self._lock:
            if self._paused_at is not None:
                self._paused_total += self._monotonic() - self._paused_at
                self._paused_at = None


@dataclass(frozen=True, slots=True)
class ActiveTimeBudget:
    """A deadline measured on a ``PausableClock``."""

    clock: PausableClock
    deadline: float | None

    @classmethod
    def from_duration(cls, clock: PausableClock, seconds: float | None) -> "ActiveTimeBudget":
        return cls(clock, None if seconds is None else clock.now() + seconds)

    def remaining(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - self.clock.now())

    def expired(self) -> bool:
        remaining = self.remaining()
        return remaining is not None and remaining <= 0


@dataclass(frozen=True, slots=True)
class RunnerEvent:
    type: str
    step_id: str | None = None
    step_number: int | None = None
    completed_operations: int | None = None
    message: str | None = None


class ActionExecutor(Protocol):
    """Action boundary used by the runner."""

    def execute(
        self,
        action: Action,
        cancel_event: threading.Event,
        budget: ActiveTimeBudget,
    ) -> None: ...


class DirectActionExecutor:
    """Run a known-short action in-process."""

    def __init__(self, callback: Callable[[Action], None] = perform_action) -> None:
        self._callback = callback

    def execute(self, action: Action, cancel_event: threading.Event, budget: ActiveTimeBudget) -> None:
        if cancel_event.is_set():
            raise ExecutionCancelled
        self._callback(action)


class CancellableActionExecutor:
    """Adapt a cooperative long action to the runner's cancellation contract."""

    def __init__(
        self,
        callback: Callable[[Action, threading.Event, ActiveTimeBudget], None],
    ) -> None:
        self._callback = callback

    def execute(
        self,
        action: Action,
        cancel_event: threading.Event,
        budget: ActiveTimeBudget,
    ) -> None:
        self._callback(action, cancel_event, budget)


def _isolated_worker(callback: Callable[[Action], None], action: Action, result: multiprocessing.Queue) -> None:
    try:
        callback(action)
        result.put((True, None))
    except BaseException as error:  # the parent must receive child failures
        result.put((False, f"{type(error).__name__}: {error}"))


class IsolatedActionExecutor:
    """Run an unsafe blocking action in a process that can be terminated.

    Extension actions that cannot implement cooperative cancellation should use
    this executor. Cancellation and active-time timeout both terminate and join
    the child, so no blocked action thread is left behind in the application.
    """

    def __init__(
        self,
        callback: Callable[[Action], None],
        *,
        poll_interval: float = 0.01,
        context: multiprocessing.context.BaseContext | None = None,
    ) -> None:
        self._callback = callback
        self._poll_interval = poll_interval
        self._context = context or multiprocessing.get_context()

    def execute(self, action: Action, cancel_event: threading.Event, budget: ActiveTimeBudget) -> None:
        result = self._context.Queue()
        process = self._context.Process(target=_isolated_worker, args=(self._callback, action, result))
        process.start()
        try:
            while process.is_alive():
                if cancel_event.wait(self._poll_interval):
                    process.terminate()
                    raise ExecutionCancelled
                if budget.expired():
                    process.terminate()
                    raise TimeoutError("单步执行超时")
            process.join()
            try:
                succeeded, detail = result.get(timeout=0.2)
            except queue.Empty:
                if process.exitcode:
                    raise RuntimeError(f"隔离动作进程退出（{process.exitcode}）")
                return
            if not succeeded:
                raise RuntimeError(detail)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            result.close()


class WorkflowRunner:
    """Execute an immutable workflow snapshot and publish typed events."""

    def __init__(
        self,
        workflow: Workflow,
        event_sink: Callable[[RunnerEvent], None] | None = None,
        *,
        action_executor: ActionExecutor | None = None,
        condition_evaluator: Callable[[Condition], bool] = evaluate_condition,
        clock: PausableClock | None = None,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        validate_workflow(workflow)
        self.workflow = workflow
        self._event_sink = event_sink or (lambda _event: None)
        self._action_executor = action_executor or DirectActionExecutor()
        self._condition_evaluator = condition_evaluator
        self._clock = clock or PausableClock()
        self._random_uniform = random_uniform
        self._cancel_event = threading.Event()
        self._run_event = threading.Event()
        self._run_event.set()
        self._thread: threading.Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, *, daemon: bool = True) -> threading.Thread:
        if self.is_alive:
            raise RuntimeError("执行器已在运行。")
        self._thread = threading.Thread(target=self.run, name="clickflow-runner", daemon=daemon)
        self._thread.start()
        return self._thread

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def pause(self) -> None:
        self._run_event.clear()
        self._clock.pause()

    def resume(self) -> None:
        self._clock.resume()
        self._run_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._run_event.set()

    def _emit(self, event_type: str, **values: object) -> None:
        self._event_sink(RunnerEvent(event_type, **values))  # type: ignore[arg-type]

    def run(self) -> None:
        """Run synchronously. ``start`` is the background-thread convenience API."""

        try:
            self._run_workflow()
            self._emit("completed")
        except ExecutionCancelled:
            self._emit("stopped")
        except pyautogui.FailSafeException:
            self._emit("error", message="已触发左上角紧急停止，执行已终止。")
        except Exception as error:
            self._emit("error", message=f"{type(error).__name__}: {error}")

    def _run_workflow(self) -> None:
        steps = self.workflow.steps
        index_by_id = {step.id: index for index, step in enumerate(steps)}
        completed_operations = 0
        cycle = 0
        while self.workflow.repeat_count is None or cycle < self.workflow.repeat_count:
            step_index = 0
            while step_index < len(steps):
                self._check_cancelled()
                step = steps[step_index]
                self._emit("step_started", step_id=step.id, step_number=step_index + 1)
                step_succeeded = True
                last_error: Exception | None = None

                for _repetition in range(step.repeat_count):
                    operation_succeeded = False
                    for attempt in range(step.retry_count + 1):
                        budget = ActiveTimeBudget.from_duration(self._clock, step.timeout_seconds)
                        try:
                            self._wait_for_condition(step, budget)
                            maximum = step.wait_seconds if step.wait_max_seconds is None else step.wait_max_seconds
                            self._wait_active(self._random_uniform(step.wait_seconds, maximum), budget)
                            self._wait_until_resumed()
                            self._action_executor.execute(step.action, self._cancel_event, budget)
                            self._check_cancelled()
                            if budget.expired():
                                raise TimeoutError("单步执行超时")
                            operation_succeeded = True
                            completed_operations += 1
                            self._emit("step_completed", step_id=step.id, completed_operations=completed_operations)
                            break
                        except ExecutionCancelled:
                            raise
                        except pyautogui.FailSafeException:
                            raise
                        except Exception as error:
                            last_error = error
                            if attempt < step.retry_count:
                                self._emit(
                                    "step_retry",
                                    step_id=step.id,
                                    step_number=step_index + 1,
                                    message=f"第 {step_index + 1} 步重试 {attempt + 1}/{step.retry_count}",
                                )
                    if not operation_succeeded:
                        step_succeeded = False
                        break

                target = step.on_success if step_succeeded else step.on_failure
                if target is not None:
                    step_index = index_by_id[target]
                elif step_succeeded:
                    step_index += 1
                else:
                    raise last_error or RuntimeError("步骤执行失败")
            cycle += 1

    def _wait_for_condition(self, step: Step, step_budget: ActiveTimeBudget) -> None:
        condition_budget = ActiveTimeBudget.from_duration(self._clock, step.condition_timeout_seconds)
        while True:
            if step_budget.expired():
                raise TimeoutError("单步执行超时")
            if self._condition_evaluator(step.condition):
                return
            if condition_budget.expired():
                raise TimeoutError("等待条件成立超时")
            condition_remaining = condition_budget.remaining()
            self._wait_active(min(0.05, condition_remaining or 0.0), step_budget)

    def _wait_until_resumed(self) -> None:
        while not self._run_event.wait(0.05):
            self._check_cancelled()
        self._check_cancelled()

    def _wait_active(self, seconds: float, *budgets: ActiveTimeBudget) -> None:
        active_deadline = self._clock.now() + seconds
        while self._clock.now() < active_deadline:
            self._wait_until_resumed()
            for budget in budgets:
                if budget.expired():
                    raise TimeoutError("单步执行超时")
            remaining = active_deadline - self._clock.now()
            wait_slice = min(0.05, max(0.0, remaining))
            for budget in budgets:
                budget_remaining = budget.remaining()
                if budget_remaining is not None:
                    wait_slice = min(wait_slice, budget_remaining)
            if self._cancel_event.wait(wait_slice):
                raise ExecutionCancelled

    def _check_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise ExecutionCancelled
