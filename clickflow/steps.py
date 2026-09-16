"""Step validation, execution, and display helpers."""

import math
import time

import pyautogui

from .models import LABEL_ACTIONS, Step


pyautogui.FAILSAFE = True


def validate_step_input(
    action_label: str,
    x_text: str,
    y_text: str,
    wait_text: str,
) -> Step:
    """Validate form values and return a normalized step."""

    action = LABEL_ACTIONS.get(action_label.strip())
    if action is None:
        raise ValueError("请选择“移动”或“点击”操作。")

    if not x_text.strip() or not y_text.strip():
        raise ValueError("X 和 Y 坐标不能为空。")
    try:
        x = int(x_text.strip())
        y = int(y_text.strip())
    except ValueError as error:
        raise ValueError("X 和 Y 坐标必须是整数，可使用负数。") from error

    if not wait_text.strip():
        raise ValueError("执行前等待时间不能为空。")
    try:
        wait_seconds = float(wait_text.strip())
    except ValueError as error:
        raise ValueError("执行前等待时间必须是数字。") from error
    if not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise ValueError("执行前等待时间必须是大于或等于 0 的有限数字。")

    return Step(action=action, x=x, y=y, wait_seconds=wait_seconds)


def validate_step_sequence(steps: list[Step]) -> None:
    """Reject an empty sequence before an execution is started."""

    if not steps:
        raise ValueError("请至少添加一个操作步骤。")


def perform_step(step: Step) -> None:
    """Wait and perform one step using the agreed action semantics."""

    time.sleep(step.wait_seconds)
    perform_action(step)


def perform_action(step: Step) -> None:
    """Perform one step immediately, without its configured wait."""

    if step.action == "move":
        pyautogui.moveTo(step.x, step.y)
    elif step.action == "click":
        pyautogui.click(step.x, step.y)
    else:
        raise ValueError(f"未知操作类型：{step.action}")


def format_elapsed(seconds: float) -> str:
    """Format a non-negative duration as HH:MM:SS."""

    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
