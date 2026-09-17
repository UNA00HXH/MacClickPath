"""Shared data models and state definitions.

The persistent model deliberately separates *what to do* from *when to do it*.
That keeps keyboard/window/image actions and richer conditions from turning
``Step`` back into a bag of unrelated optional fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TypeAlias
from uuid import uuid4

from .coordinates import Rect


ACTION_LABELS = {"move": "移动", "click": "点击", "double_click": "双击"}
LABEL_ACTIONS = {label: action for action, label in ACTION_LABELS.items()}


class AccessibilityPermission(Enum):
    GRANTED = "granted"
    DENIED = "denied"
    NOT_MACOS = "not_macos"
    CHECK_FAILED = "check_failed"


class ExecutionState(Enum):
    IDLE = "idle"
    COUNTDOWN = "countdown"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MouseAction:
    """A pointer action. Other action families can be added as new classes."""

    operation: str
    x: float
    y: float
    coordinate_mode: str = "absolute"
    display_id: str | None = None
    target_window: str | None = None
    expected_color: tuple[int, int, int] | None = None
    color_tolerance: int = 0
    allowed_region: Rect | None = None


Action: TypeAlias = MouseAction


@dataclass(frozen=True, slots=True)
class AlwaysCondition:
    """An unconditional step."""


@dataclass(frozen=True, slots=True)
class MouseAtCondition:
    x: float
    y: float
    coordinate_mode: str = "absolute"
    display_id: str | None = None
    target_window: str | None = None


@dataclass(frozen=True, slots=True)
class PixelColorCondition:
    x: float
    y: float
    color: tuple[int, int, int]
    coordinate_mode: str = "absolute"
    display_id: str | None = None
    target_window: str | None = None


Condition: TypeAlias = AlwaysCondition | MouseAtCondition | PixelColorCondition


@dataclass(frozen=True, slots=True, init=False)
class Step:
    """One workflow node with stable identity and structured behavior.

    The legacy positional constructor (``Step("click", x, y, wait)``) remains
    accepted so callers can migrate independently. New code should pass a
    structured ``MouseAction`` and a structured condition.
    """

    id: str = field(compare=False)
    action: Action
    condition: Condition
    wait_seconds: float
    repeat_count: int
    wait_max_seconds: float | None
    condition_timeout_seconds: float
    retry_count: int
    timeout_seconds: float | None
    on_success: str | int | None
    on_failure: str | int | None

    def __init__(
        self,
        action: Action | str,
        x: int | None = None,
        y: int | None = None,
        wait_seconds: float = 0.0,
        repeat_count: int = 1,
        wait_max_seconds: float | None = None,
        condition: Condition | str = "always",
        condition_value: str = "",
        condition_timeout_seconds: float = 0.0,
        retry_count: int = 0,
        timeout_seconds: float | None = None,
        on_success: str | int | None = None,
        on_failure: str | int | None = None,
        *,
        id: str | None = None,
    ) -> None:
        if isinstance(action, str):
            if x is None or y is None:
                raise TypeError("mouse actions require x and y")
            normalized_action: Action = MouseAction(action, x, y)
        else:
            normalized_action = action

        if isinstance(condition, str):
            if condition == "always":
                normalized_condition: Condition = AlwaysCondition()
            elif condition == "mouse_at":
                if x is None or y is None:
                    raise TypeError("mouse_at requires x and y")
                normalized_condition = MouseAtCondition(
                    x, y, normalized_action.coordinate_mode,
                    normalized_action.display_id, normalized_action.target_window,
                )
            elif condition == "pixel_color":
                if x is None or y is None:
                    raise TypeError("pixel_color requires x and y")
                parts = tuple(int(part.strip()) for part in condition_value.split(","))
                if len(parts) != 3:
                    raise ValueError("pixel_color requires R,G,B")
                normalized_condition = PixelColorCondition(
                    x, y, parts, normalized_action.coordinate_mode,
                    normalized_action.display_id, normalized_action.target_window,
                )  # type: ignore[arg-type]
            else:
                raise ValueError(f"unknown condition: {condition}")
        else:
            normalized_condition = condition

        object.__setattr__(self, "id", id or uuid4().hex)
        object.__setattr__(self, "action", normalized_action)
        object.__setattr__(self, "condition", normalized_condition)
        object.__setattr__(self, "wait_seconds", wait_seconds)
        object.__setattr__(self, "repeat_count", repeat_count)
        object.__setattr__(self, "wait_max_seconds", wait_max_seconds)
        object.__setattr__(self, "condition_timeout_seconds", condition_timeout_seconds)
        object.__setattr__(self, "retry_count", retry_count)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)
        object.__setattr__(self, "on_success", on_success)
        object.__setattr__(self, "on_failure", on_failure)

    @property
    def x(self) -> float:
        return self.action.x

    @property
    def y(self) -> float:
        return self.action.y

    @property
    def action_type(self) -> str:
        return self.action.operation

    @property
    def condition_type(self) -> str:
        if isinstance(self.condition, AlwaysCondition):
            return "always"
        if isinstance(self.condition, MouseAtCondition):
            return "mouse_at"
        return "pixel_color"

    @property
    def condition_value(self) -> str:
        if isinstance(self.condition, PixelColorCondition):
            return ",".join(str(component) for component in self.condition.color)
        return ""


@dataclass(frozen=True, slots=True)
class Workflow:
    steps: tuple[Step, ...]
    repeat_count: int | None = 1

    def __post_init__(self) -> None:
        """Normalize legacy integer jumps once all target IDs are available."""

        normalized: list[Step] = []
        changed = False
        for step in self.steps:
            success = self._legacy_target(step.on_success)
            failure = self._legacy_target(step.on_failure)
            if success != step.on_success or failure != step.on_failure:
                step = replace(step, on_success=success, on_failure=failure)
                changed = True
            normalized.append(step)
        if changed:
            object.__setattr__(self, "steps", tuple(normalized))

    def _legacy_target(self, target: str | int | None) -> str | int | None:
        if isinstance(target, int) and not isinstance(target, bool):
            if 0 <= target < len(self.steps):
                return self.steps[target].id
        return target
