"""Tests for advanced workflow control and JSON persistence."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clickflow.models import Step, Workflow
from clickflow.workflow import (
    load_workflow,
    save_workflow,
    validate_workflow,
    workflow_from_dict,
    workflow_to_dict,
)


class WorkflowPersistenceTests(unittest.TestCase):
    def test_round_trip_preserves_all_flow_fields(self) -> None:
        workflow = Workflow(
            (
                Step(
                    "click", 10, 20, 0.2,
                    repeat_count=3,
                    wait_max_seconds=0.8,
                    condition="pixel_color",
                    condition_value="1, 2, 3",
                    condition_timeout_seconds=5,
                    retry_count=2,
                    timeout_seconds=8,
                    on_success=1,
                    on_failure=1,
                ),
                Step("move", -5, 4, 0),
            ),
            repeat_count=None,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            save_workflow(path, workflow)
            loaded = load_workflow(path)

        self.assertEqual(loaded, workflow)

    def test_dict_uses_versioned_clickflow_format(self) -> None:
        workflow = Workflow((Step("move", 1, 2, 0),), 4)

        data = workflow_to_dict(workflow)

        self.assertEqual(data["format"], "clickflow")
        self.assertEqual(data["version"], 2)
        self.assertIsInstance(data["steps"][0]["action"], dict)
        self.assertEqual(workflow_from_dict(data), workflow)

    def test_migrates_v1_indexes_to_stable_ids(self) -> None:
        loaded = workflow_from_dict({
            "format": "clickflow", "version": 1, "repeat_count": 1,
            "steps": [
                {"action": "click", "x": 1, "y": 2, "wait_seconds": 0, "on_success": 1},
                {"action": "move", "x": 3, "y": 4, "wait_seconds": 0},
            ],
        })
        self.assertEqual(loaded.steps[0].id, "legacy-step-1")
        self.assertEqual(loaded.steps[0].on_success, "legacy-step-2")
        self.assertEqual(workflow_to_dict(loaded)["version"], 2)

    def test_stable_jump_does_not_change_when_steps_are_reordered(self) -> None:
        first = Step("click", 1, 2, 0, id="first", on_success="last")
        last = Step("move", 3, 4, 0, id="last")
        reordered = Workflow((last, first))
        self.assertEqual(reordered.steps[1].on_success, "last")
        validate_workflow(reordered)

    def test_rejects_invalid_jump_and_wait_range(self) -> None:
        invalid_jump = Workflow((Step("click", 1, 2, 0, on_success=3),))
        invalid_wait = Workflow(
            (Step("click", 1, 2, 2, wait_max_seconds=1),)
        )

        with self.assertRaisesRegex(ValueError, "跳转目标"):
            validate_workflow(invalid_jump)
        with self.assertRaisesRegex(ValueError, "等待上限"):
            validate_workflow(invalid_wait)

    def test_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "无法读取工作流"):
                load_workflow(path)


if __name__ == "__main__":
    unittest.main()
