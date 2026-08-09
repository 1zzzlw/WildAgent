import unittest
from copy import deepcopy

from app.tools.spatial_tools import (
    fix_element_dimensions,
    fix_material_references,
    fix_opening_coords,
    fix_opening_fit,
    fix_wall_junctions,
    validate_collision,
    validate_element_dimensions,
    validate_opening_coords,
    validate_opening_fit,
    validate_reference_integrity,
    validate_wall_junctions,
)


def run_tool(tool, blueprint):
    return getattr(tool, "func", tool)(blueprint)


class SpatialValidationTest(unittest.TestCase):
    def test_component_world_coordinate_is_projected_back_to_parent_wall(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building"},
            "geometry": {
                "elements": [{
                    "id": "wall_right",
                    "type": "wall",
                    "from": [8, 0, 0],
                    "to": [8, 3, 6],
                    "thickness": 0.2,
                }],
                "components": [{
                    "id": "window_side",
                    "type": "window",
                    "parentWall": "wall_right",
                    "from": [8, 0.9, 2],
                    "width": 1.2,
                    "height": 1.2,
                }],
            },
            "materials": {},
            "behaviors": {},
        }

        self.assertIn("法向偏移超出", run_tool(validate_opening_coords, blueprint))
        self.assertIn("世界坐标投影", run_tool(fix_opening_coords, blueprint))
        self.assertEqual(
            blueprint["geometry"]["components"][0]["from"],
            [2.0, 0.9, 0.0],
        )
        self.assertIn("格式正确", run_tool(validate_opening_coords, blueprint))

    def test_zero_height_story_walls_are_completed_from_floor_levels(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {
                        "id": "floor_ground",
                        "type": "floor",
                        "from": [0, 0, 0],
                        "to": [8, 0, 6],
                        "thickness": 0.2,
                    },
                    {
                        "id": "floor_upper",
                        "type": "floor",
                        "from": [0, 3, 0],
                        "to": [8, 3, 6],
                        "thickness": 0.2,
                    },
                    {
                        "id": "wall_ground",
                        "type": "wall",
                        "from": [0, 0, 0],
                        "to": [8, 0, 0],
                        "thickness": 0.2,
                    },
                    {
                        "id": "wall_upper",
                        "type": "wall",
                        "from": [0, 3, 0],
                        "to": [8, 3, 0],
                        "thickness": 0.2,
                    },
                ],
            },
        }

        self.assertIn("❌ [wall_ground] wall 高度=0.0m", run_tool(validate_element_dimensions, blueprint))
        self.assertIn("按楼板标高/常用层高补全", run_tool(fix_element_dimensions, blueprint))
        walls = [item for item in blueprint["geometry"]["elements"] if item["type"] == "wall"]
        self.assertEqual([wall["to"][1] for wall in walls], [3.0, 6.0])
        self.assertNotIn("❌", run_tool(validate_element_dimensions, blueprint))

    def test_missing_component_material_reference_is_rejected(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [6, 3, 0],
                }],
                "components": [{
                    "id": "door",
                    "type": "door",
                    "parentWall": "wall",
                    "from": [2, 0, 0],
                    "width": 1,
                    "height": 2.2,
                    "frameMaterial": "missing_wood",
                }],
            },
            "materials": {"wood": {"baseColor": [0.4, 0.2, 0.1]}},
        }

        result = run_tool(validate_reference_integrity, blueprint)

        self.assertIn("❌ [component:door]", result)
        self.assertIn("missing_wood", result)

    def test_unique_material_alias_is_repaired(self):
        blueprint = {
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
        }

        self.assertIn("未在 Blueprint.materials 中定义", run_tool(validate_reference_integrity, blueprint))
        self.assertIn("'wood' → 'wood_oak'", run_tool(fix_material_references, blueprint))
        self.assertNotIn("❌", run_tool(validate_reference_integrity, blueprint))

    def test_dimension_validator_reports_invalid_vectors_without_crashing(self):
        for element_type in ("wall", "floor", "beam", "stair"):
            with self.subTest(element_type=element_type):
                blueprint = {
                    "geometry": {
                        "elements": [{
                            "id": f"{element_type}_bad",
                            "type": element_type,
                            "from": [-7, 0, -2.5],
                            "to": [7, 10.5],
                        }],
                    },
                }

                result = run_tool(validate_element_dimensions, blueprint)

                self.assertIn("❌", result)
                self.assertIn(f"{element_type}_bad.to", result)

    def test_openings_fit_walls_with_explicit_height(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {
                        "id": "wall_ground",
                        "type": "wall",
                        "from": [0, 0, 0],
                        "to": [12, 0, 0],
                        "height": 3,
                        "thickness": 0.25,
                    },
                    {
                        "id": "wall_upper",
                        "type": "wall",
                        "from": [0, 3.2, 0],
                        "to": [12, 3.2, 0],
                        "height": 3,
                        "thickness": 0.25,
                    },
                    {
                        "id": "door",
                        "type": "opening",
                        "parentWall": "wall_ground",
                        "from": [5, 0, 0],
                        "width": 2,
                        "height": 2.6,
                    },
                    {
                        "id": "upper_window",
                        "type": "opening",
                        "parentWall": "wall_upper",
                        "from": [2, 4.1, 0],
                        "width": 1.5,
                        "height": 1.5,
                    },
                ],
            },
        }
        before = deepcopy(blueprint)

        self.assertIn("均在 parentWall 范围内", run_tool(validate_opening_fit, blueprint))
        self.assertIn("无需修正", run_tool(fix_opening_fit, blueprint))
        self.assertEqual(blueprint, before)

    def test_component_only_opening_is_still_checked_for_wall_fit(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [6, 0, 0],
                    "height": 3,
                }],
                "components": [{
                    "id": "window_outside",
                    "type": "window",
                    "parentWall": "wall",
                    "from": [5.5, 1, 0],
                    "width": 1.2,
                    "height": 1.2,
                }],
            },
        }

        result = run_tool(validate_opening_fit, blueprint)

        self.assertIn("❌ [component:window_outside]", result)
        self.assertIn("超出父墙右端", result)
        self.assertIn("已自动修正", run_tool(fix_opening_fit, blueprint))
        self.assertIn("均在 parentWall 范围内", run_tool(validate_opening_fit, blueprint))

    def test_overlapping_door_and_window_on_same_wall_are_rejected(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [8, 0, 0],
                    "height": 3,
                }],
                "components": [
                    {
                        "id": "door",
                        "type": "door",
                        "parentWall": "wall",
                        "from": [2, 0, 0],
                        "width": 1.2,
                        "height": 2.2,
                    },
                    {
                        "id": "window",
                        "type": "window",
                        "parentWall": "wall",
                        "from": [2.8, 0.9, 0],
                        "width": 1.4,
                        "height": 1.2,
                    },
                ],
            },
        }

        result = run_tool(validate_opening_fit, blueprint)

        self.assertIn("❌ [component:door]", result)
        self.assertIn("❌ [component:window]", result)
        self.assertIn("重叠", result)

    def test_adjacent_floor_and_balcony_are_not_collision(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {
                        "id": "floor_sf",
                        "type": "floor",
                        "from": [0, 3.05, 0],
                        "to": [12, 3.2, 10],
                        "thickness": 0.15,
                    },
                    {
                        "id": "balcony_slab",
                        "type": "floor",
                        "from": [4, 3.1, -1.5],
                        "to": [8, 3.2, 0],
                        "thickness": 0.1,
                    },
                ],
            },
        }

        self.assertIn("碰撞检测通过", run_tool(validate_collision, blueprint))

    def test_open_railing_walls_are_not_snapped(self):
        structural_walls = [
            {"id": "s", "type": "wall", "from": [0, 0, 0], "to": [12, 0, 0], "height": 3, "thickness": 0.25},
            {"id": "e", "type": "wall", "from": [12, 0, 0], "to": [12, 0, 10], "height": 3, "thickness": 0.25},
            {"id": "n", "type": "wall", "from": [12, 0, 10], "to": [0, 0, 10], "height": 3, "thickness": 0.25},
            {"id": "w", "type": "wall", "from": [0, 0, 10], "to": [0, 0, 0], "height": 3, "thickness": 0.25},
        ]
        railings = [
            {"id": "rail_front", "type": "wall", "from": [4, 3.2, -1.5], "to": [8, 3.2, -1.5], "height": 1, "thickness": 0.05},
            {"id": "rail_left", "type": "wall", "from": [4, 3.2, -1.5], "to": [4, 3.2, 0], "height": 1, "thickness": 0.05},
            {"id": "rail_right", "type": "wall", "from": [8, 3.2, -1.5], "to": [8, 3.2, 0], "height": 1, "thickness": 0.05},
        ]
        blueprint = {"geometry": {"elements": structural_walls + railings}}
        before = deepcopy(blueprint)

        self.assertIn("闭合良好", run_tool(validate_wall_junctions, blueprint))
        self.assertIn("无需修正", run_tool(fix_wall_junctions, blueprint))
        self.assertEqual(blueprint, before)
