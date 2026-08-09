"""合并节点的空间归一化与设计硬约束回归测试。"""

import unittest

from app.agent.nodes.merge_node import merge_fragments_node
from app.agent.nodes.validate_node import validate_node
from app.tools.spatial_tools import validate_opening_fit


def _skeleton() -> dict:
    return {
        "meta": {"version": "1.1", "type": "building", "name": "merge-test"},
        "geometry": {
            "elements": [{
                "id": "wall_back",
                "type": "wall",
                "from": [0, 0, 6],
                "to": [8, 3, 6],
                "thickness": 0.2,
            }],
            "components": [],
        },
        "materials": {},
        "behaviors": {},
    }


def _design_brief(minimum_doors: int = 1) -> dict:
    return {
        "component_quota": {
            "door": {"min": minimum_doors, "max": 1},
        },
        "facade_plan": {
            "wall_back": {"max_openings": 1},
        },
    }


class MergePrecisionTest(unittest.IsolatedAsyncioTestCase):
    async def test_merge_repairs_world_coordinate_normal_offset(self):
        result = await merge_fragments_node({
            "skeleton_blueprint": _skeleton(),
            "design_brief": _design_brief(),
            "door_fragments": [{
                "id": "door_back",
                "type": "door",
                "parentWall": "wall_back",
                "from": [3.4, 0, 6],
                "width": 1.2,
                "height": 2.2,
                "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90},
            }],
        })

        door = result["merged_blueprint"]["geometry"]["components"][0]
        self.assertEqual(door["from"], [3.4, 0, 0.0])
        self.assertEqual(result["merge_diag"]["final_errors"], 0)
        self.assertEqual(result["merge_diag"]["design_errors"], [])

    async def test_missing_required_component_blocks_final_validation(self):
        merged = await merge_fragments_node({
            "skeleton_blueprint": _skeleton(),
            "design_brief": _design_brief(),
        })

        self.assertIn("door 数量 0 少于设计下限 1", merged["merge_diag"]["design_errors"])
        self.assertEqual(merged["merge_diag"]["final_errors"], 1)

        final = await validate_node(merged)
        self.assertEqual(final["status"], "partial")
        self.assertEqual(final["validation_error_count"], 1)
        self.assertTrue(any(
            result["name"] == "validate_design_brief"
            for result in final["validation_results"]
        ))
        self.assertEqual(final["failed_components"][0]["component_id"], "design:door")
        self.assertEqual(final["failed_components"][0]["suggested_tools"], ["add_entity"])

    async def test_overlapping_door_and_window_cannot_pass_merge(self):
        result = await merge_fragments_node({
            "skeleton_blueprint": _skeleton(),
            "design_brief": {
                "component_quota": {
                    "door": {"min": 1, "max": 1},
                    "window": {"min": 1, "max": 1},
                },
                "facade_plan": {"wall_back": {"max_openings": 2}},
            },
            "door_fragments": [{
                "id": "door_back",
                "type": "door",
                "parentWall": "wall_back",
                "from": [2, 0, 0],
                "width": 1.2,
                "height": 2.2,
            }],
            "window_fragments": [{
                "id": "window_back",
                "type": "window",
                "parentWall": "wall_back",
                "from": [2.8, 0.9, 0],
                "width": 1.4,
                "height": 1.2,
            }],
        })

        self.assertGreater(result["merge_diag"]["final_errors"], 0)
        components = result["merged_blueprint"]["geometry"]["components"]
        self.assertEqual([item["from"][0] for item in components], [2, 2.8])
        output = getattr(validate_opening_fit, "func", validate_opening_fit)(
            result["merged_blueprint"]
        )
        self.assertIn("重叠", output)
