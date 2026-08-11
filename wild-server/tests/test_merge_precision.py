"""合并节点的空间归一化与设计硬约束回归测试。"""

import unittest

from app.agent.nodes.merge_node import (
    _deduplicate_balcony_representations,
    _validate_design_brief_constraints,
    merge_fragments_node,
)
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
    def test_balcony_named_railing_is_preserved_without_balcony_component(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "type": "wall", "id": "wall_front",
                    "from": [0, 0, 0], "to": [8, 3.2, 0], "thickness": 0.24,
                }],
                "components": [{
                    "type": "railing", "id": "balcony_guard_only",
                    "path": [[2, 0, 0], [4, 0, 0]], "height": 1.1,
                }],
            },
        }

        result = _deduplicate_balcony_representations(blueprint)

        self.assertEqual(result["removed_railing_count"], 0)
        self.assertEqual(blueprint["geometry"]["components"][0]["id"], "balcony_guard_only")

    def test_balcony_railing_only_satisfies_minimum_not_standalone_maximum(self):
        blueprint = {
            "geometry": {
                "elements": [],
                "components": [
                    {"type": "balcony", "id": "balcony_left"},
                    {"type": "balcony", "id": "balcony_right"},
                    {"type": "railing", "id": "stair_guard_left"},
                    {"type": "railing", "id": "stair_guard_right"},
                ],
            },
        }
        design_brief = {
            "component_quota": {
                "balcony": {"min": 2, "max": 2},
                "railing": {"min": 2, "max": 2},
            },
        }

        self.assertEqual(
            _validate_design_brief_constraints(blueprint, design_brief),
            [],
        )

    def test_embedded_balcony_railing_does_not_require_duplicate_component(self):
        blueprint = {
            "geometry": {
                "elements": [],
                "components": [{"type": "balcony", "id": "balcony_main"}],
            },
        }
        design_brief = {
            "component_quota": {
                "balcony": {"min": 1, "max": 1},
                "railing": {"min": 1, "max": 0},
            },
        }

        self.assertEqual(
            _validate_design_brief_constraints(blueprint, design_brief),
            [],
        )

    def test_missing_second_storey_and_stair_fail_realization_contract(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {"type": "floor", "id": "floor_ground", "from": [0, 0, 0], "to": [8, 0, 6], "thickness": 0.2},
                    {"type": "wall", "id": "wall_ground", "from": [0, 0, 0], "to": [8, 3.2, 0], "thickness": 0.24},
                ],
                "components": [],
            },
        }
        design_brief = {
            "component_quota": {},
            "realization": {
                "modeled_floors": 2,
                "floor_height": 3.2,
                "representation_mode": "full",
            },
        }

        errors = _validate_design_brief_constraints(blueprint, design_brief)

        self.assertIn("建筑方案要求 2 层，但缺少墙体标高 [3.2]", errors)
        self.assertIn("建筑方案要求 2 层，但缺少楼板标高 [3.2]", errors)
        self.assertIn("建筑方案要求 2 层，但没有 stair 构件", errors)

    async def test_balcony_component_removes_duplicate_floor_and_railings(self):
        skeleton = {
            "meta": {"version": "1.1", "type": "building", "name": "balcony-dedup"},
            "geometry": {
                "elements": [
                    {"type": "wall", "id": "wall_front", "from": [0, 3.2, 0], "to": [8, 6.4, 0], "thickness": 0.3},
                    {"type": "wall", "id": "wall_back", "from": [0, 3.2, 6], "to": [8, 6.4, 6], "thickness": 0.3},
                    {"type": "wall", "id": "wall_left", "from": [0, 3.2, 0], "to": [0, 6.4, 6], "thickness": 0.3},
                    {"type": "wall", "id": "wall_right", "from": [8, 3.2, 0], "to": [8, 6.4, 6], "thickness": 0.3},
                    {"type": "floor", "id": "floor_second", "from": [0, 3.2, 0], "to": [8, 3.2, 6], "thickness": 0.2},
                    {"type": "floor", "id": "floor_portico", "from": [2.8, 0, -1.5], "to": [5.2, 0, 0], "thickness": 0.2},
                    {"type": "floor", "id": "floor_balcony", "from": [2.8, 3.2, -1.5], "to": [5.2, 3.2, 0], "thickness": 0.2},
                ],
                "components": [],
            },
            "materials": {},
            "behaviors": {},
        }
        result = await merge_fragments_node({
            "skeleton_blueprint": skeleton,
            "design_brief": {
                "component_quota": {
                    "balcony": {"min": 1, "max": 1},
                    "railing": {"min": 1, "max": 2},
                },
                "facade_plan": {},
            },
            "balcony_fragments": [{
                "type": "balcony", "id": "balcony_main", "parentWall": "wall_front",
                "from": [2.8, 3.2, 0], "width": 2.4, "depth": 1.5,
                "slabThickness": 0.2,
            }],
            "railing_fragments": [
                {"type": "railing", "id": "balcony_front", "parentFloor": "floor_balcony", "path": [[0, 0, 0], [2.4, 0, 0]], "height": 1.1},
                {"type": "railing", "id": "balcony_left", "parentFloor": "floor_balcony", "path": [[0, 0, 0], [0, 0, 1.5]], "height": 1.1},
                {"type": "railing", "id": "railing_balcony_orphan", "path": [[5.5, 0, 0], [7, 0, -1.5]], "height": 1.1},
                {"type": "railing", "id": "portico_front", "parentFloor": "floor_portico", "path": [[0, 0, 0], [2.4, 0, 0]], "height": 1.0},
                {"type": "railing", "id": "stair_guard", "path": [[0, 0, 4], [2, 2, 4]], "height": 1.0},
            ],
        })

        blueprint = result["merged_blueprint"]
        self.assertEqual(
            [item["id"] for item in blueprint["geometry"]["elements"] if item["type"] == "floor"],
            ["floor_second", "floor_portico"],
        )
        self.assertCountEqual(
            [item["id"] for item in blueprint["geometry"]["components"]],
            ["balcony_main", "stair_guard"],
        )
        self.assertEqual(result["merge_diag"]["balcony_cleanup"], {
            "removed_floor_ids": ["floor_balcony"],
            "removed_railing_count": 3,
        })
        self.assertEqual(result["merge_diag"]["ground_railing_cleanup"], {
            "removed_railing_ids": ["portico_front"],
        })
        self.assertEqual(result["merge_diag"]["design_errors"], [])

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

    async def test_overlapping_plain_windows_are_fixed_in_merge(self):
        skeleton = {
            "meta": {"version": "1.1", "type": "building", "name": "short-wall"},
            "geometry": {
                "elements": [{
                    "id": "wall_short", "type": "wall",
                    "from": [0, 0, 0], "to": [1, 3.2, 0],
                    "thickness": 0.24,
                }],
                "components": [],
            },
            "materials": {},
            "behaviors": {},
        }
        result = await merge_fragments_node({
            "skeleton_blueprint": skeleton,
            "window_fragments": [
                {
                    "id": "window_05", "type": "window",
                    "parentWall": "wall_short", "from": [0.18, 0.96, 0],
                    "width": 0.5, "height": 1.55,
                },
                {
                    "id": "window_06", "type": "window",
                    "parentWall": "wall_short", "from": [0.32, 0.96, 0],
                    "width": 0.5, "height": 1.55,
                },
            ],
        })

        self.assertEqual(result["merge_diag"]["final_errors"], 0)
        self.assertEqual(
            [item["id"] for item in result["merged_blueprint"]["geometry"]["components"]],
            ["window_05"],
        )
