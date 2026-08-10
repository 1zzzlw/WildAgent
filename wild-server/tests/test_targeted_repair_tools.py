import unittest
from types import SimpleNamespace

from app.agent.nodes.validate_node import _trace_errors_to_components
from app.agent.repair_tools import execute_repair_actions, extract_repair_actions
from app.agent.validation_issues import compare_issue_sets, validation_issues_from_results


def _blueprint() -> dict:
    return {
        "meta": {"version": "1.1", "type": "building", "name": "repair-test"},
        "geometry": {
            "elements": [{
                "id": "wall_front",
                "type": "wall",
                "from": [0, 0, 0],
                "to": [6, 3, 0],
                "thickness": 0.2,
            }],
            "components": [{
                "id": "door_front",
                "type": "door",
                "parentWall": "wall_front",
                "from": [5.5, 0, 0],
                "width": 1.2,
                "height": 2.2,
                "material": "wood_oak",
            }],
        },
        "materials": {
            "wood_oak": {"baseColor": [0.5, 0.3, 0.1]},
            "wood_dark": {"baseColor": [0.2, 0.1, 0.05]},
        },
        "behaviors": {},
    }


class TargetedRepairToolsTest(unittest.TestCase):
    def test_repair_action_parser_skips_planning_arrays(self):
        text = '''
        可用字段：["from", "width"]
        最终动作：
        [{"tool":"move_opening","arguments":{"entity_id":"door_front","along":3.0}}]
        '''

        actions = extract_repair_actions(text)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "move_opening")

    def test_validation_issues_keep_multiple_errors_for_same_entity(self):
        results = [
            SimpleNamespace(
                step="4b",
                name="validate_opening_fit",
                output=(
                    "❌ [component:door_front] 右端超出父墙\n"
                    "❌ [component:door_front] 与 window_front 重叠"
                ),
                has_error=True,
                has_warning=False,
            )
        ]

        issues = validation_issues_from_results(results, _blueprint())
        failed = _trace_errors_to_components(
            results,
            _blueprint(),
            validation_issues=issues,
        )

        self.assertEqual(len(issues), 2)
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(failed[0]["issues"]), 2)
        self.assertIn("move_opening", failed[0]["suggested_tools"])
        self.assertIn("resize_opening", failed[0]["suggested_tools"])

    def test_facade_overage_exposes_attached_openings_as_repair_targets(self):
        blueprint = _blueprint()
        blueprint["geometry"]["components"].append({
            "id": "window_front",
            "type": "window",
            "parentWall": "wall_front",
            "from": [3.0, 0.9, 0],
            "width": 1.2,
            "height": 1.2,
        })
        results = [SimpleNamespace(
            name="validate_design_brief",
            output="❌ [design] 墙 wall_front 有 2 个门窗，超过立面上限 1",
            has_error=True,
        )]

        issues = validation_issues_from_results(results, blueprint)
        failed = _trace_errors_to_components(
            results,
            blueprint,
            validation_issues=issues,
        )

        self.assertEqual(issues[0]["entity_id"], "wall_front")
        self.assertEqual(
            set(issues[0]["related_entity_ids"]),
            {"door_front", "window_front"},
        )
        self.assertEqual(
            issues[0]["suggested_tools"],
            ["remove_entity", "reparent_opening"],
        )
        self.assertEqual(
            set(failed[0]["related_entity_ids"]),
            {"door_front", "window_front"},
        )
        self.assertEqual(
            {item["type"] for item in failed[0]["related_entities"]},
            {"door", "window"},
        )

    def test_model_actions_modify_only_allowed_failed_entity(self):
        original = _blueprint()
        candidate, reports = execute_repair_actions(
            original,
            [
                {
                    "tool": "move_opening",
                    "arguments": {
                        "entity_id": "door_front",
                        "along": 3.0,
                        "elevation": 0.0,
                    },
                    "reason": "移入父墙范围",
                },
                {
                    "tool": "resize_opening",
                    "arguments": {
                        "entity_id": "door_front",
                        "width": 1.0,
                    },
                },
            ],
            allowed_entity_ids={"door_front"},
        )

        door = candidate["geometry"]["components"][0]
        self.assertEqual(original["geometry"]["components"][0]["from"][0], 5.5)
        self.assertEqual(door["from"], [3.0, 0.0, 0])
        self.assertEqual(door["width"], 1.0)
        self.assertTrue(all(report["success"] for report in reports))

    def test_add_entity_is_limited_to_missing_design_type(self):
        candidate, reports = execute_repair_actions(
            _blueprint(),
            [{
                "tool": "add_entity",
                "arguments": {
                    "repair_target": "design:window",
                    "entity": {
                        "id": "window_front",
                        "type": "window",
                        "parentWall": "wall_front",
                        "from": [3.5, 0.9, 0],
                        "width": 1.2,
                        "height": 1.2,
                    },
                },
            }],
            allowed_entity_ids=set(),
            allowed_add_types={"window"},
        )

        self.assertTrue(reports[0]["success"])
        self.assertEqual(len(candidate["geometry"]["components"]), 2)
        self.assertEqual(candidate["geometry"]["components"][1]["id"], "window_front")

    def test_remove_entity_is_limited_to_related_overage_ids(self):
        original = _blueprint()
        original["geometry"]["components"].append({
            "id": "window_front",
            "type": "window",
            "parentWall": "wall_front",
            "from": [3.0, 0.9, 0],
            "width": 1.2,
            "height": 1.2,
        })

        candidate, reports = execute_repair_actions(
            original,
            [
                {
                    "tool": "remove_entity",
                    "arguments": {"entity_id": "wall_front"},
                },
                {
                    "tool": "remove_entity",
                    "arguments": {"entity_id": "window_front"},
                },
            ],
            allowed_entity_ids={"wall_front", "window_front"},
            allowed_remove_ids={"window_front"},
        )

        self.assertFalse(reports[0]["success"])
        self.assertTrue(reports[1]["success"])
        self.assertEqual(candidate["geometry"]["elements"][0]["id"], "wall_front")
        self.assertEqual(
            [item["id"] for item in candidate["geometry"]["components"]],
            ["door_front"],
        )
        self.assertEqual(len(original["geometry"]["components"]), 2)

    def test_action_cannot_touch_passed_entity_or_identity_fields(self):
        candidate, reports = execute_repair_actions(
            _blueprint(),
            [
                {
                    "tool": "patch_entity",
                    "arguments": {
                        "entity_id": "wall_front",
                        "changes": {"thickness": 0.3},
                    },
                },
                {
                    "tool": "patch_entity",
                    "arguments": {
                        "entity_id": "door_front",
                        "changes": {"id": "door_replaced"},
                    },
                },
            ],
            allowed_entity_ids={"door_front"},
        )

        self.assertFalse(reports[0]["success"])
        self.assertFalse(reports[1]["success"])
        self.assertEqual(candidate["geometry"]["elements"][0]["thickness"], 0.2)
        self.assertEqual(candidate["geometry"]["components"][0]["id"], "door_front")

    def test_material_tool_requires_defined_material(self):
        candidate, reports = execute_repair_actions(
            _blueprint(),
            [{
                "tool": "set_material_reference",
                "arguments": {
                    "entity_id": "door_front",
                    "field": "material",
                    "material_id": "missing_material",
                },
            }],
            allowed_entity_ids={"door_front"},
        )

        self.assertFalse(reports[0]["success"])
        self.assertEqual(
            candidate["geometry"]["components"][0]["material"],
            "wood_oak",
        )

    def test_repair_must_reduce_errors_without_introducing_new_issue(self):
        before = [
            {"code": "OPENING_FIT", "entity_id": "door_front"},
            {"code": "OPENING_COORDINATES", "entity_id": "door_front"},
        ]

        improved = compare_issue_sets(before, [before[0]])
        replaced = compare_issue_sets(before, [
            {"code": "COLLISION", "entity_id": "door_front"},
        ])

        self.assertTrue(improved["accepted"])
        self.assertFalse(replaced["accepted"])
        self.assertEqual(
            replaced["introduced_issues"],
            [("COLLISION", "door_front")],
        )


if __name__ == "__main__":
    unittest.main()
