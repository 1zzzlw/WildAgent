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


if __name__ == "__main__":
    unittest.main()
