"""Shared data models and state definitions."""

from dataclasses import dataclass
from enum import Enum


ACTION_LABELS = {"move": "移动", "click": "点击"}
LABEL_ACTIONS = {label: action for action, label in ACTION_LABELS.items()}


class AccessibilityPermission(Enum):
    """Possible results of the macOS Accessibility permission check."""

    GRANTED = "granted"
    DENIED = "denied"
    NOT_MACOS = "not_macos"
    CHECK_FAILED = "check_failed"


class ExecutionState(Enum):
    """Lifecycle states for one execution run."""

    IDLE = "idle"
    COUNTDOWN = "countdown"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Step:
    """One mouse automation step."""

    action: str
    x: int
    y: int
    wait_seconds: float
