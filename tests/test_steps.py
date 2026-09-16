"""Tests for step validation and execution semantics."""

import unittest
from unittest.mock import patch

from clickflow.models import Step
from clickflow.steps import (
    perform_step,
    validate_step_input,
    validate_step_sequence,
)


class StepValidationTests(unittest.TestCase):
    def test_builds_move_step_and_accepts_negative_coordinate(self) -> None:
        step = validate_step_input("移动", "-120", "640", "0.5")

        self.assertEqual(step, Step("move", -120, 640, 0.5))

    def test_builds_click_step(self) -> None:
        step = validate_step_input("点击", "100", "200", "0")

        self.assertEqual(step, Step("click", 100, 200, 0.0))

    def test_rejects_empty_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能为空"):
            validate_step_input("移动", "", "200", "0.5")

    def test_rejects_non_integer_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须是整数"):
            validate_step_input("移动", "1.5", "200", "0.5")

    def test_rejects_invalid_wait_time(self) -> None:
        for value in ("", "later", "-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_step_input("点击", "100", "200", value)

    def test_rejects_empty_step_sequence(self) -> None:
        with self.assertRaisesRegex(ValueError, "至少添加一个"):
            validate_step_sequence([])


class StepExecutionTests(unittest.TestCase):
    @patch("clickflow.steps.time.sleep")
    @patch("clickflow.steps.pyautogui.moveTo")
    def test_move_only_moves_pointer(self, move_to, sleep) -> None:
        perform_step(Step("move", -120, 20, 0.25))

        sleep.assert_called_once_with(0.25)
        move_to.assert_called_once_with(-120, 20)

    @patch("clickflow.steps.time.sleep")
    @patch("clickflow.steps.pyautogui.click")
    def test_click_uses_target_coordinate(self, click, sleep) -> None:
        perform_step(Step("click", 30, 40, 1.0))

        sleep.assert_called_once_with(1.0)
        click.assert_called_once_with(30, 40)


if __name__ == "__main__":
    unittest.main()
