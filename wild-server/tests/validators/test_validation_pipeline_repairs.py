import unittest

from app.services.agent_service import _final_errors, run_validation_pipeline
from app.agent.validation_issues import validation_issues_from_results


class ValidationPipelineRepairTest(unittest.TestCase):
    def test_validation_issue_uses_finite_root_cause_category(self):
        blueprint = {
            "geometry": {
                "elements": [{"id": "roof_1", "type": "roof"}],
                "components": [],
            }
        }
        issues = validation_issues_from_results([{
            "name": "validate_roof_coverage",
            "output": "❌ [roof_1] 屋顶未覆盖最高承托墙",
            "has_error": True,
        }], blueprint)

        self.assertEqual(issues[0]["category"], "coverage_geometry")
        self.assertEqual(issues[0]["recommended_repair_level"], "deterministic_fix")

    def test_material_alias_is_repaired_before_final_reference_result(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "alias repair"},
            "geometry": {
                "elements": [{
                    "id": "floor_attic",
                    "type": "floor",
                    "from": [0, 3, 0],
                    "to": [6, 3, 5],
                    "thickness": 0.2,
                    "material": "wood",
                }],
                "components": [],
            },
            "materials": {
                "wood_oak": {"baseColor": [0.5, 0.3, 0.1]},
                "concrete": {"baseColor": [0.6, 0.6, 0.6]},
            },
            "behaviors": {},
        }

        results = run_validation_pipeline(blueprint)

        self.assertEqual(
            blueprint["geometry"]["elements"][0]["material"],
            "wood_oak",
        )
        self.assertFalse(
            any(result.name == "validate_reference_integrity" for result in _final_errors(results))
        )


if __name__ == "__main__":
    unittest.main()
