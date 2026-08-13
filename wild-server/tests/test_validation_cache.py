"""验证 merge → final_validate 的校验结果复用。"""

import unittest
from unittest.mock import patch

from app.agent.nodes.validate_node import validate_node


class ValidationCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_successful_merge_validation_is_not_run_twice(self) -> None:
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "cached"},
            "geometry": {"elements": [], "components": []},
            "materials": {},
        }
        state = {
            "merged_blueprint": blueprint,
            "merge_diag": {
                "final_errors": 0,
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

        with patch("app.services.agent_service.run_validation_pipeline") as pipeline:
            result = await validate_node(state)

        pipeline.assert_not_called()
        self.assertTrue(result["validation_cache_reused"])
        self.assertEqual(result["validation_error_count"], 0)
        self.assertEqual(result["status"], "complete")

    async def test_callback_blueprint_recomputes_design_quota_instead_of_reusing_stale_error(self) -> None:
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "repaired"},
            "geometry": {
                "elements": [],
                "components": [
                    {"id": "light_1", "type": "light"},
                    {"id": "light_2", "type": "light"},
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
