"""Step validation, execution, and display helpers."""

import math
import time

import pyautogui

from .coordinates import Rect, resolve_point, validate_action_target
from .models import LABEL_ACTIONS, MouseAction, Step
from .workflow import parse_rgb


pyautogui.FAILSAFE = True
DOUBLE_CLICK_INTERVAL_SECONDS = 0.1


def validate_step_input(
    action_label: str,
    x_text: str,
    y_text: str,
    wait_text: str,
    *,
    repeat_text: str = "1",
    wait_max_text: str = "",
    condition: str = "always",
    condition_value: str = "",
    condition_timeout_text: str = "0",
    retry_text: str = "0",
    timeout_text: str = "",
    on_success: str | int | None = None,
    on_failure: str | int | None = None,
    coordinate_mode: str = "absolute",
    display_id: str | None = None,
    target_window: str | None = None,
    expected_color_text: str = "",
    color_tolerance_text: str = "0",
    allowed_region_text: str = "",
) -> Step:
    """Validate form values and return a normalized step."""

    action = LABEL_ACTIONS.get(action_label.strip())
    if action is None:
        raise ValueError("请选择“移动”“点击”或“双击”操作。")

    if not x_text.strip() or not y_text.strip():
        raise ValueError("X 和 Y 坐标不能为空。")
    try:
        if coordinate_mode == "display_percent":
            x = float(x_text.strip())
            y = float(y_text.strip())
        else:
            x = int(x_text.strip())
            y = int(y_text.strip())
    except ValueError as error:
        requirement = "数字" if coordinate_mode == "display_percent" else "整数，可使用负数"
        raise ValueError(f"X 和 Y 坐标必须是{requirement}。") from error
    if coordinate_mode not in {"absolute", "display_percent", "window"}:
        raise ValueError("坐标模式无效。")
    if coordinate_mode == "display_percent":
        if not all(math.isfinite(value) and 0 <= value <= 100 for value in (x, y)):
            raise ValueError("百分比坐标必须在 0 到 100 之间。")
    if coordinate_mode == "window" and not (target_window or "").strip():
        raise ValueError("窗口相对坐标必须选择目标窗口。")

    expected_color = None
    if expected_color_text.strip():
        expected_color = parse_rgb(expected_color_text.strip())
    try:
        color_tolerance = int(color_tolerance_text.strip() or "0")
    except ValueError as error:
        raise ValueError("颜色容差必须是 0 到 255 的整数。") from error
    if not 0 <= color_tolerance <= 255:
        raise ValueError("颜色容差必须是 0 到 255 的整数。")

    allowed_region = None
    if allowed_region_text.strip():
        try:
            region_values = tuple(int(part.strip()) for part in allowed_region_text.split(","))
        except ValueError as error:
            raise ValueError("允许区域必须填写为 X,Y,宽,高。") from error
        if len(region_values) != 4 or region_values[2] <= 0 or region_values[3] <= 0:
            raise ValueError("允许区域必须填写为 X,Y,宽,高，且宽高大于 0。")
        allowed_region = Rect(*region_values)

    if not wait_text.strip():
        raise ValueError("执行前等待时间不能为空。")
    try:
        wait_seconds = float(wait_text.strip())
    except ValueError as error:
        raise ValueError("执行前等待时间必须是数字。") from error
    if not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise ValueError("执行前等待时间必须是大于或等于 0 的有限数字。")

    try:
        repeat_count = int(repeat_text.strip())
        retry_count = int(retry_text.strip())
    except ValueError as error:
        raise ValueError("重复次数和失败重试次数必须是整数。") from error
    if repeat_count < 1:
        raise ValueError("单步重复次数必须大于或等于 1。")
    if retry_count < 0:
        raise ValueError("失败重试次数不能小于 0。")

    wait_max_seconds = None
    if wait_max_text.strip():
        try:
            wait_max_seconds = float(wait_max_text.strip())
        except ValueError as error:
            raise ValueError("随机等待上限必须是数字。") from error
        if not math.isfinite(wait_max_seconds) or wait_max_seconds < wait_seconds:
            raise ValueError("随机等待上限必须是有限数字，且不能小于等待下限。")

    try:
        condition_timeout_seconds = float(condition_timeout_text.strip() or "0")
    except ValueError as error:
        raise ValueError("条件等待时间必须是数字。") from error
    if not math.isfinite(condition_timeout_seconds) or condition_timeout_seconds < 0:
        raise ValueError("条件等待时间必须是大于或等于 0 的有限数字。")

    timeout_seconds = None
    if timeout_text.strip():
        try:
            timeout_seconds = float(timeout_text.strip())
        except ValueError as error:
            raise ValueError("单步超时必须是数字。") from error
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("单步超时必须是大于 0 的有限数字。")

    if condition == "always":
        structured_condition = "always"
    elif condition == "mouse_at":
        structured_condition = "mouse_at"
    elif condition == "pixel_color":
        parse_rgb(condition_value.strip())
        structured_condition = "pixel_color"
    else:
        raise ValueError("执行条件无效。")

    return Step(
        action=MouseAction(
            action, x, y, coordinate_mode, display_id or None,
            (target_window or "").strip() or None, expected_color,
            color_tolerance, allowed_region,
        ),
        wait_seconds=wait_seconds,
        repeat_count=repeat_count,
        wait_max_seconds=wait_max_seconds,
        condition=structured_condition,
        x=x,
        y=y,
        condition_value=condition_value.strip(),
        condition_timeout_seconds=condition_timeout_seconds,
        retry_count=retry_count,
        timeout_seconds=timeout_seconds,
        on_success=on_success,
        on_failure=on_failure,
    )


def validate_step_sequence(steps: list[Step]) -> None:
    """Reject an empty sequence before an execution is started."""

    if not steps:
        raise ValueError("请至少添加一个操作步骤。")


def perform_step(step: Step) -> None:
    """Wait and perform one step using the agreed action semantics."""

    time.sleep(step.wait_seconds)
    perform_action(step)


def perform_action(step: Step | MouseAction) -> None:
    """Perform one structured mouse action immediately."""

    action = step.action if isinstance(step, Step) else step
    x, y = resolve_point(action)
    validate_action_target(action, x, y)
    if action.operation == "move":
        pyautogui.moveTo(x, y)
    elif action.operation == "click":
        pyautogui.click(x, y)
    elif action.operation == "double_click":
        pyautogui.doubleClick(
            x,
            y,
            interval=DOUBLE_CLICK_INTERVAL_SECONDS,
        )
    else:
        raise ValueError(f"未知操作类型：{action.operation}")


def format_elapsed(seconds: float) -> str:
    """Format a non-negative duration as HH:MM:SS."""

    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
