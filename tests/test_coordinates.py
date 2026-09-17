"""Coordinate resolution and pointer-safety tests."""

import unittest

from clickflow.coordinates import DisplayInfo, Rect, WindowInfo, preview_region, resolve_point, validate_action_target
from clickflow.models import MouseAction, Step, Workflow
from clickflow.runner import DirectActionExecutor, WorkflowRunner
from clickflow.workflow import workflow_from_dict, workflow_to_dict


class FakeImage:
    pass


class FakeDesktop:
    def __init__(self, pixel=(10, 20, 30)) -> None:
        self._pixel = pixel
        self.captured = None

    def displays(self):
        return (
            DisplayInfo("main", "Main", Rect(0, 0, 1000, 800), True),
            DisplayInfo("left", "Left", Rect(-800, 100, 800, 600)),
        )

    def windows(self):
        return (WindowInfo("7", "Document", "Editor", Rect(200, 300, 640, 480)),)

    def pixel(self, _x, _y):
        return self._pixel

    def screenshot(self, region):
        self.captured = region
        return FakeImage()


class CoordinateTests(unittest.TestCase):
    def test_resolves_percent_on_selected_negative_origin_display(self) -> None:
        action = MouseAction("move", 25.0, 50.0, "display_percent", "left")
        self.assertEqual(resolve_point(action, FakeDesktop()), (-600, 400))

    def test_one_hundred_percent_stays_inside_display(self) -> None:
        action = MouseAction("move", 100.0, 100.0, "display_percent", "left")
        self.assertEqual(resolve_point(action, FakeDesktop()), (-1, 699))

    def test_resolves_window_relative_point_by_stable_label(self) -> None:
        action = MouseAction("click", 12, 34, "window", target_window="Editor — Document")
        self.assertEqual(resolve_point(action, FakeDesktop()), (212, 334))

    def test_window_relative_point_cannot_escape_target_window(self) -> None:
        action = MouseAction("click", 640, 10, "window", target_window="Editor — Document")
        with self.assertRaisesRegex(RuntimeError, "超出目标窗口"):
            resolve_point(action, FakeDesktop())

    def test_pixel_guard_honors_tolerance_and_rejects_mismatch(self) -> None:
        action = MouseAction("click", 10, 20, expected_color=(12, 18, 32), color_tolerance=2)
        validate_action_target(action, 10, 20, FakeDesktop())
        with self.assertRaisesRegex(RuntimeError, "颜色不匹配"):
            validate_action_target(action, 10, 20, FakeDesktop((50, 20, 30)))

    def test_allowed_region_blocks_outside_target(self) -> None:
        action = MouseAction("move", 0, 0, allowed_region=Rect(10, 20, 30, 40))
        validate_action_target(action, 10, 20, FakeDesktop())
        with self.assertRaisesRegex(RuntimeError, "超出允许区域"):
            validate_action_target(action, 40, 20, FakeDesktop())

    def test_color_mismatch_uses_existing_failure_branch(self) -> None:
        fallback = Step("move", 1, 1, 0, id="fallback")
        guarded = Step(
            MouseAction("click", 10, 20, expected_color=(255, 255, 255)),
            wait_seconds=0, id="guarded", on_failure=fallback.id,
        )
        executed = []

        def execute(action):
            if action.operation == "click":
                validate_action_target(action, 10, 20, FakeDesktop((0, 0, 0)))
            executed.append(action)

        events = []
        WorkflowRunner(
            Workflow((guarded, fallback)), events.append,
            action_executor=DirectActionExecutor(execute),
        ).run()
        self.assertEqual(executed, [fallback.action])
        self.assertEqual(events[-1].type, "completed")

    def test_preview_uses_allowed_region_and_does_not_require_color_match(self) -> None:
        desktop = FakeDesktop((0, 0, 0))
        action = MouseAction(
            "click", 20, 30, expected_color=(255, 255, 255),
            allowed_region=Rect(10, 20, 50, 60),
        )
        image, marker, region = preview_region(action, desktop)
        self.assertIsInstance(image, FakeImage)
        self.assertEqual(marker, (10, 10))
        self.assertEqual(region, Rect(10, 20, 50, 60))
        self.assertEqual(desktop.captured, (10, 20, 50, 60))

    def test_safety_fields_round_trip_in_existing_versioned_format(self) -> None:
        action = MouseAction(
            "double_click", 50.5, 25.25, "display_percent", "left",
            expected_color=(1, 2, 3), color_tolerance=4,
            allowed_region=Rect(-800, 100, 800, 600),
        )
        workflow = Workflow((Step(action, wait_seconds=0),))
        self.assertEqual(workflow_from_dict(workflow_to_dict(workflow)), workflow)


if __name__ == "__main__":
    unittest.main()
