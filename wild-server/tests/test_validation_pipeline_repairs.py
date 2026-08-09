import unittest

from app.services.agent_service import _final_errors, run_validation_pipeline


class ValidationPipelineRepairTest(unittest.TestCase):
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
