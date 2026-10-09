"""完整门禁不能用合并缓存的旧通过结论替代。"""

import unittest
from unittest.mock import patch

from app.agent.validation.diagnostics import blueprint_fingerprint
from app.agent.validation.workflow import validate_node


class ValidationCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_successful_merge_cache_still_runs_the_current_full_gate(self) -> None:
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "cached"},
            "geometry": {"elements": [{"id": "floor", "type": "floor", "from": [0, 0, 0],
                                      "to": [6, 0, 4], "thickness": 0.2}], "components": []},
            "materials": {},
        }
        state = {
            "merged_blueprint": blueprint,
            "merge_diag": {
                "final_errors": 0,
                "blueprint_fingerprint": blueprint_fingerprint(blueprint),
                "design_errors": [],
                "validation_results": [{
                    "step": 1,
                    "name": "validate_blueprint_structure",
                    "output": "✅ OK",
                    "has_error": False,
                    "has_warning": False,
                }],
            },
        }

        with patch("app.services.agent_service.run_validation_pipeline", return_value=[]) as pipeline:
            result = await validate_node(state)

        pipeline.assert_called_once()
        self.assertFalse(pipeline.call_args.kwargs["auto_fix"])
        self.assertFalse(result["validation_cache_reused"])
        self.assertEqual(result["validation_error_count"], 0)
        self.assertEqual(result["status"], "complete")

    async def test_callback_blueprint_recomputes_design_quota_instead_of_reusing_stale_error(self) -> None:
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "repaired"},
            "geometry": {
                "elements": [],
                "components": [
                    {"id": "light_1", "type": "light", "position": [1, 2, 0]},
                    {"id": "light_2", "type": "light", "position": [2, 2, 0]},
                ],
            },
            "materials": {},
        }
        state = {
            "merged_blueprint": blueprint,
            "design_brief": {
                "component_quota": {"light": {"min": 2, "max": 8}},
            },
            "merge_diag": {
                "final_errors": 1,
                "design_errors": ["light 数量 0 少于设计下限 2"],
                "validation_results": [],
            },
            "retry_count": 1,
        }

        with patch(
            "app.services.agent_service.run_validation_pipeline",
            return_value=[],
        ):
            result = await validate_node(state)

        self.assertEqual(result["validation_error_count"], 0)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(any(
            step["name"] == "validate_design_brief"
            for step in result["validation_results"]
        ))


if __name__ == "__main__":
    unittest.main()
