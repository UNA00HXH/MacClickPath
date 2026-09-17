"""Workflow validation, conditions, version migration, and JSON persistence."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import pyautogui

from .models import (
    ACTION_LABELS,
    AlwaysCondition,
    MouseAction,
    MouseAtCondition,
    PixelColorCondition,
    Step,
    Workflow,
)
from .coordinates import Rect, SystemDesktopBackend, resolve_point


WORKFLOW_FORMAT_VERSION = 2
CONDITION_LABELS = {
    "always": "始终执行",
    "pixel_color": "像素颜色匹配",
    "mouse_at": "鼠标位于坐标",
}
LABEL_CONDITIONS = {label: value for value, label in CONDITION_LABELS.items()}


def _finite_nonnegative(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field}必须是数字。")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field}必须是大于或等于 0 的有限数字。")
    return result


def validate_workflow(workflow: Workflow) -> None:
    """Validate fields, unique IDs, and ID-based jump targets."""

    if not workflow.steps:
        raise ValueError("请至少添加一个操作步骤。")
    if workflow.repeat_count is not None and (
        not isinstance(workflow.repeat_count, int)
        or isinstance(workflow.repeat_count, bool)
        or workflow.repeat_count < 1
    ):
        raise ValueError("整套流程循环次数必须是大于或等于 1 的整数。")

    step_ids = [step.id for step in workflow.steps]
    if any(not isinstance(step_id, str) or not step_id for step_id in step_ids):
        raise ValueError("步骤 ID 必须是非空文本。")
    if len(step_ids) != len(set(step_ids)):
        raise ValueError("步骤 ID 不能重复。")
    known_ids = set(step_ids)

    for number, step in enumerate(workflow.steps, start=1):
        action = step.action
        if not isinstance(action, MouseAction) or action.operation not in ACTION_LABELS:
            raise ValueError(f"第 {number} 步的操作类型无效。")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in (action.x, action.y)):
            raise ValueError(f"第 {number} 步的坐标必须是有限数字。")
        if action.coordinate_mode not in {"absolute", "display_percent", "window"}:
            raise ValueError(f"第 {number} 步的坐标模式无效。")
        if action.coordinate_mode != "display_percent" and any(not float(value).is_integer() for value in (action.x, action.y)):
            raise ValueError(f"第 {number} 步的绝对/窗口坐标必须是整数。")
        if action.coordinate_mode == "display_percent" and any(not 0 <= value <= 100 for value in (action.x, action.y)):
            raise ValueError(f"第 {number} 步的百分比坐标必须在 0 到 100 之间。")
        if action.coordinate_mode == "window" and not action.target_window:
            raise ValueError(f"第 {number} 步缺少目标窗口。")
        if action.expected_color is not None:
            _validate_rgb(action.expected_color)
        if not isinstance(action.color_tolerance, int) or isinstance(action.color_tolerance, bool) or not 0 <= action.color_tolerance <= 255:
            raise ValueError(f"第 {number} 步的颜色容差必须是 0 到 255 的整数。")
        if action.allowed_region is not None and (
            not isinstance(action.allowed_region, Rect)
            or action.allowed_region.width <= 0 or action.allowed_region.height <= 0
        ):
            raise ValueError(f"第 {number} 步的允许区域无效。")
        if not isinstance(step.repeat_count, int) or isinstance(step.repeat_count, bool) or step.repeat_count < 1:
            raise ValueError(f"第 {number} 步的重复次数必须大于或等于 1。")
        minimum = _finite_nonnegative(step.wait_seconds, f"第 {number} 步等待下限")
        if step.wait_max_seconds is not None:
            maximum = _finite_nonnegative(step.wait_max_seconds, f"第 {number} 步等待上限")
            if maximum < minimum:
                raise ValueError(f"第 {number} 步等待上限不能小于下限。")
        if not isinstance(step.condition, (AlwaysCondition, MouseAtCondition, PixelColorCondition)):
            raise ValueError(f"第 {number} 步的条件类型无效。")
        if isinstance(step.condition, (MouseAtCondition, PixelColorCondition)) and any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
            for value in (step.condition.x, step.condition.y)
        ):
            raise ValueError(f"第 {number} 步的条件坐标必须是有限数字。")
        if isinstance(step.condition, (MouseAtCondition, PixelColorCondition)):
            if step.condition.coordinate_mode not in {"absolute", "display_percent", "window"}:
                raise ValueError(f"第 {number} 步的条件坐标模式无效。")
            if step.condition.coordinate_mode == "display_percent" and any(
                not 0 <= value <= 100 for value in (step.condition.x, step.condition.y)
            ):
                raise ValueError(f"第 {number} 步的条件百分比坐标必须在 0 到 100 之间。")
            if step.condition.coordinate_mode == "window" and not step.condition.target_window:
                raise ValueError(f"第 {number} 步的条件缺少目标窗口。")
        if isinstance(step.condition, PixelColorCondition):
            _validate_rgb(step.condition.color)
        _finite_nonnegative(step.condition_timeout_seconds, f"第 {number} 步条件等待时间")
        if not isinstance(step.retry_count, int) or isinstance(step.retry_count, bool) or step.retry_count < 0:
            raise ValueError(f"第 {number} 步失败重试次数不能小于 0。")
        if step.timeout_seconds is not None:
            timeout = _finite_nonnegative(step.timeout_seconds, f"第 {number} 步超时")
            if timeout == 0:
                raise ValueError(f"第 {number} 步超时必须大于 0。")
        for target in (step.on_success, step.on_failure):
            if target is not None and (not isinstance(target, str) or target not in known_ids):
                raise ValueError(f"第 {number} 步包含不存在的跳转目标。")


def _validate_rgb(rgb: tuple[int, ...]) -> tuple[int, int, int]:
    if len(rgb) != 3 or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255 for value in rgb):
        raise ValueError("像素颜色必须填写为 R,G,B，且每项在 0 到 255 之间。")
    return rgb  # type: ignore[return-value]


def parse_rgb(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError("像素颜色必须填写为 R,G,B，例如 255,255,255。")
    try:
        rgb = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as error:
        raise ValueError("像素颜色必须填写为 R,G,B，例如 255,255,255。") from error
    return _validate_rgb(rgb)


def evaluate_condition(condition: Step | AlwaysCondition | MouseAtCondition | PixelColorCondition) -> bool:
    """Evaluate one built-in structured condition against desktop state."""

    if isinstance(condition, Step):
        condition = condition.condition
    if isinstance(condition, AlwaysCondition):
        return True
    if isinstance(condition, MouseAtCondition):
        target_x, target_y = resolve_point(condition)
        position = pyautogui.position()
        return position.x == target_x and position.y == target_y
    if isinstance(condition, PixelColorCondition):
        target_x, target_y = resolve_point(condition)
        return SystemDesktopBackend().pixel(target_x, target_y) == condition.color
    raise ValueError(f"未知条件类型：{type(condition).__name__}")


def _action_to_dict(action: MouseAction) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "mouse", "operation": action.operation, "x": action.x, "y": action.y,
        "coordinate_mode": action.coordinate_mode,
        "display_id": action.display_id,
        "target_window": action.target_window,
        "expected_color": None if action.expected_color is None else list(action.expected_color),
        "color_tolerance": action.color_tolerance,
    }
    if action.allowed_region is None:
        result["allowed_region"] = None
    else:
        result["allowed_region"] = {
            "x": action.allowed_region.x, "y": action.allowed_region.y,
            "width": action.allowed_region.width, "height": action.allowed_region.height,
        }
    return result


def _action_from_dict(raw: dict[str, Any]) -> MouseAction:
    expected = raw.get("expected_color")
    if expected is not None:
        if not isinstance(expected, list):
            raise ValueError("expected_color 必须是数组。")
        expected_color = tuple(expected)
    else:
        expected_color = None
    region = raw.get("allowed_region")
    if region is not None:
        if not isinstance(region, dict):
            raise ValueError("allowed_region 必须是对象。")
        allowed_region = Rect(region.get("x"), region.get("y"), region.get("width"), region.get("height"))
    else:
        allowed_region = None
    return MouseAction(
        raw.get("operation"), raw.get("x"), raw.get("y"),
        raw.get("coordinate_mode", "absolute"), raw.get("display_id"),
        raw.get("target_window"), expected_color, raw.get("color_tolerance", 0),
        allowed_region,
    )


def _condition_to_dict(condition: object) -> dict[str, Any]:
    if isinstance(condition, AlwaysCondition):
        return {"type": "always"}
    if isinstance(condition, MouseAtCondition):
        return {
            "type": "mouse_at", "x": condition.x, "y": condition.y,
            "coordinate_mode": condition.coordinate_mode, "display_id": condition.display_id,
            "target_window": condition.target_window,
        }
    if isinstance(condition, PixelColorCondition):
        return {
            "type": "pixel_color", "x": condition.x, "y": condition.y,
            "color": list(condition.color), "coordinate_mode": condition.coordinate_mode,
            "display_id": condition.display_id, "target_window": condition.target_window,
        }
    raise ValueError(f"不支持的条件类型：{type(condition).__name__}")


def workflow_to_dict(workflow: Workflow) -> dict[str, Any]:
    validate_workflow(workflow)
    return {
        "format": "clickflow",
        "version": WORKFLOW_FORMAT_VERSION,
        "repeat_count": workflow.repeat_count,
        "steps": [
            {
                "id": step.id,
                "action": _action_to_dict(step.action),
                "condition": _condition_to_dict(step.condition),
                "timing": {
                    "wait_seconds": step.wait_seconds,
                    "wait_max_seconds": step.wait_max_seconds,
                    "condition_timeout_seconds": step.condition_timeout_seconds,
                    "timeout_seconds": step.timeout_seconds,
                },
                "repeat_count": step.repeat_count,
                "retry_count": step.retry_count,
                "on_success": step.on_success,
                "on_failure": step.on_failure,
            }
            for step in workflow.steps
        ],
    }


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("工作流 steps 必须是数组。")
    ids = [f"legacy-step-{index + 1}" for index in range(len(raw_steps))]
    migrated_steps: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index + 1} 步必须是对象。")
        condition_type = raw.get("condition", "always")
        condition: dict[str, Any] = {"type": condition_type}
        if condition_type in {"mouse_at", "pixel_color"}:
            condition.update({"x": raw.get("x"), "y": raw.get("y")})
        if condition_type == "pixel_color":
            condition["color"] = list(parse_rgb(raw.get("condition_value", "")))

        def target_id(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(ids):
                return ids[value]
            return value

        migrated_steps.append({
            "id": ids[index],
            "action": {"type": "mouse", "operation": raw.get("action"), "x": raw.get("x"), "y": raw.get("y")},
            "condition": condition,
            "timing": {
                "wait_seconds": raw.get("wait_seconds"),
                "wait_max_seconds": raw.get("wait_max_seconds"),
                "condition_timeout_seconds": raw.get("condition_timeout_seconds", 0.0),
                "timeout_seconds": raw.get("timeout_seconds"),
            },
            "repeat_count": raw.get("repeat_count", 1),
            "retry_count": raw.get("retry_count", 0),
            "on_success": target_id(raw.get("on_success")),
            "on_failure": target_id(raw.get("on_failure")),
        })
    return {"format": "clickflow", "version": 2, "repeat_count": data.get("repeat_count", 1), "steps": migrated_steps}


MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _migrate_v1_to_v2}


def migrate_workflow_dict(data: object) -> dict[str, Any]:
    """Upgrade a supported historical document through every migration step."""

    if not isinstance(data, dict):
        raise ValueError("工作流 JSON 顶层必须是对象。")
    if data.get("format", "clickflow") != "clickflow":
        raise ValueError("不是 MacClickPath 工作流文件。")
    version = data.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("工作流版本无效。")
    migrated = dict(data)
    while version < WORKFLOW_FORMAT_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"无法从工作流版本 {version} 迁移。")
        migrated = migration(migrated)
        version = migrated.get("version")
    if version != WORKFLOW_FORMAT_VERSION:
        raise ValueError("不支持此工作流文件版本。")
    return migrated


def _condition_from_dict(raw: object) -> object:
    if not isinstance(raw, dict):
        raise ValueError("condition 必须是对象。")
    kind = raw.get("type")
    if kind == "always":
        return AlwaysCondition()
    if kind == "mouse_at":
        return MouseAtCondition(
            raw.get("x"), raw.get("y"), raw.get("coordinate_mode", "absolute"),
            raw.get("display_id"), raw.get("target_window"),
        )
    if kind == "pixel_color":
        color = raw.get("color")
        if not isinstance(color, list):
            raise ValueError("pixel_color.color 必须是数组。")
        return PixelColorCondition(
            raw.get("x"), raw.get("y"), tuple(color),
            raw.get("coordinate_mode", "absolute"), raw.get("display_id"), raw.get("target_window"),
        )
    raise ValueError(f"未知条件类型：{kind}")


def workflow_from_dict(data: object) -> Workflow:
    migrated = migrate_workflow_dict(data)
    raw_steps = migrated.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("工作流 steps 必须是数组。")
    try:
        steps: list[Step] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                raise TypeError("step must be an object")
            action = raw.get("action")
            timing = raw.get("timing")
            if not isinstance(action, dict) or action.get("type") != "mouse":
                raise ValueError("当前版本仅支持 mouse 动作。")
            if not isinstance(timing, dict):
                raise ValueError("timing 必须是对象。")
            if not isinstance(raw.get("id"), str) or not raw["id"]:
                raise ValueError("步骤 ID 必须是非空文本。")
            steps.append(Step(
                _action_from_dict(action),
                wait_seconds=timing.get("wait_seconds"),
                repeat_count=raw.get("repeat_count", 1),
                wait_max_seconds=timing.get("wait_max_seconds"),
                condition=_condition_from_dict(raw.get("condition")),
                condition_timeout_seconds=timing.get("condition_timeout_seconds", 0.0),
                retry_count=raw.get("retry_count", 0),
                timeout_seconds=timing.get("timeout_seconds"),
                on_success=raw.get("on_success"),
                on_failure=raw.get("on_failure"),
                id=raw.get("id"),
            ))
        workflow = Workflow(tuple(steps), migrated.get("repeat_count", 1))
    except (TypeError, ValueError) as error:
        raise ValueError(f"工作流字段无效：{error}") from error
    validate_workflow(workflow)
    return workflow


def save_workflow(path: str | Path, workflow: Workflow) -> None:
    Path(path).write_text(json.dumps(workflow_to_dict(workflow), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_workflow(path: str | Path) -> Workflow:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取工作流：{error}") from error
    return workflow_from_dict(data)
