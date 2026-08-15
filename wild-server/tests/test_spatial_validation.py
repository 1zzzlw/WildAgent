import unittest
from copy import deepcopy

from app.tools.spatial_tools import (
    fix_element_dimensions,
    fix_material_references,
    fix_opening_coords,
    fix_opening_fit,
    fix_roof_coverage,
    fix_wall_junctions,
    validate_collision,
    validate_element_dimensions,
    validate_model_quality,
    validate_opening_coords,
    validate_opening_fit,
    validate_reference_integrity,
    validate_roof_coverage,
    validate_wall_junctions,
)


def run_tool(tool, blueprint):
    return getattr(tool, "func", tool)(blueprint)


class SpatialValidationTest(unittest.TestCase):
    def test_duplicate_walls_and_overlapping_columns_are_model_quality_errors(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {"id": "wall_a", "type": "wall", "from": [0, 0, 0], "to": [6, 3.2, 0], "thickness": 0.24},
                    {"id": "wall_b", "type": "wall", "from": [6, 0, 0], "to": [0, 3.2, 0], "thickness": 0.24},
                    {"id": "column_a", "type": "column", "base": [1, 0, 1], "height": 3.2, "bottomRadius": 0.16, "topRadius": 0.16},
                    {"id": "column_b", "type": "column", "base": [1.1, 0, 1], "height": 3.2, "bottomRadius": 0.16, "topRadius": 0.16},
                ],
                "components": [],
            },
        }

        result = run_tool(validate_model_quality, blueprint)

        self.assertIn("wall_a, wall_b", result)
        self.assertIn("column_a / column_b", result)
        self.assertIn("❌", result)

    def test_separated_structure_passes_model_quality_gate(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {"id": "wall_a", "type": "wall", "from": [0, 0, 0], "to": [6, 3.2, 0], "thickness": 0.24},
                    {"id": "wall_b", "type": "wall", "from": [6, 0, 0], "to": [6, 3.2, 5], "thickness": 0.24},
                    {"id": "column_a", "type": "column", "base": [1, 0, 1], "height": 3.2, "bottomRadius": 0.16, "topRadius": 0.16},
                    {"id": "column_b", "type": "column", "base": [5, 0, 1], "height": 3.2, "bottomRadius": 0.16, "topRadius": 0.16},
                ],
                "components": [],
            },
        }

        self.assertNotIn("❌", run_tool(validate_model_quality, blueprint))

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

    def test_wall_declared_height_must_match_endpoint_vertical_range(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall_conflicting_height",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [12, 90, 0],
                    "height": 45,
                    "thickness": 0.2,
                }],
            },
        }

        result = run_tool(validate_element_dimensions, blueprint)

        self.assertIn("❌ [wall_conflicting_height]", result)
        self.assertIn("height=45.0m 与 from/to 竖向范围=90.0m 不一致", result)

    def test_dimension_fix_preserves_valid_tall_vertical_structure(self):
        for total_height in (100.8, 120.0, 150.0):
            with self.subTest(total_height=total_height):
                blueprint = {
                    "geometry": {
                        "elements": [
                            {
                                "id": "wall_shell",
                                "type": "wall",
                                "from": [0, 0, 0],
                                "to": [42, total_height, 0],
                                "thickness": 0.24,
                            },
                            {
                                "id": "column_full_height",
                                "type": "column",
                                "base": [1, 0, 1],
                                "height": total_height,
                                "bottomRadius": 0.3,
                                "topRadius": 0.3,
                            },
                        ],
                    },
                }

                run_tool(fix_element_dimensions, blueprint)

                wall, column = blueprint["geometry"]["elements"]
                self.assertEqual(wall["to"][1], total_height)
                self.assertNotIn("height", wall)
                self.assertEqual(column["height"], total_height)
                self.assertNotIn("❌", run_tool(validate_element_dimensions, blueprint))

    def test_dimension_fix_removes_wall_height_conflicting_with_endpoints(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall_conflicting_height",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [42, 100.8, 0],
                    "height": 45,
                    "thickness": 0.24,
                }],
            },
        }

        self.assertIn("❌", run_tool(validate_element_dimensions, blueprint))
        fix_output = run_tool(fix_element_dimensions, blueprint)

        wall = blueprint["geometry"]["elements"][0]
        self.assertNotIn("height", wall)
        self.assertEqual(wall["to"][1], 100.8)
        self.assertIn("保留 from/to 竖向范围=100.8m", fix_output)
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

    def test_overlapping_plain_windows_are_relocated_or_pruned(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall_short",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [1, 3.2, 0],
                    "height": 3.2,
                }],
                "components": [
                    {
                        "id": "window_05",
                        "type": "window",
                        "parentWall": "wall_short",
                        "from": [0.18, 0.96, 0],
                        "width": 0.5,
                        "height": 1.55,
                    },
                    {
                        "id": "window_06",
                        "type": "window",
                        "parentWall": "wall_short",
                        "from": [0.32, 0.96, 0],
                        "width": 0.5,
                        "height": 1.55,
                    },
                ],
            },
        }

        self.assertIn("0.36m × 1.55m", run_tool(validate_opening_fit, blueprint))
        fix_result = run_tool(fix_opening_fit, blueprint)

        self.assertIn("普通窗", fix_result)
        self.assertNotIn("❌", run_tool(validate_opening_fit, blueprint))
        self.assertEqual(
            [item["id"] for item in blueprint["geometry"]["components"]],
            ["window_05"],
        )

    def test_bay_window_overlapping_door_moves_to_safe_window_slot(self):
        blueprint = {
            "geometry": {
                "elements": [{
                    "id": "wall",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [10, 0, 0],
                    "height": 3,
                }],
                "components": [
                    {
                        "id": "door",
                        "type": "door",
                        "parentWall": "wall",
                        "from": [4.4, 0, 0],
                        "width": 1.2,
                        "height": 2.3,
                    },
                    {
                        "id": "bay",
                        "type": "bay_window",
                        "parentWall": "wall",
                        "from": [4.0, 0.9, 0],
                        "width": 2.0,
                        "height": 1.5,
                        "projectionDepth": 0.8,
                    },
                    {
                        "id": "safe_window",
                        "type": "window",
                        "parentWall": "wall",
                        "from": [1.0, 0.9, 0],
                        "width": 1.8,
                        "height": 1.4,
                    },
                ],
            },
        }

        self.assertIn("component:bay", run_tool(validate_opening_fit, blueprint))
        fix_result = run_tool(fix_opening_fit, blueprint)

        self.assertIn("凸窗移至安全窗位", fix_result)
        components = blueprint["geometry"]["components"]
        bay = next(item for item in components if item["id"] == "bay")
        self.assertEqual(bay["from"], [1.0, 0.9, 0])
        self.assertNotIn("safe_window", {item["id"] for item in components})
        self.assertNotIn("❌", run_tool(validate_opening_fit, blueprint))

    def test_bay_window_overlapping_door_is_pruned_without_safe_slot(self):
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
                        "from": [3, 0, 0],
                        "width": 1.2,
                        "height": 2.3,
                    },
                    {
                        "id": "bay",
                        "type": "bay_window",
                        "parentWall": "wall",
                        "from": [2.8, 0.9, 0],
                        "width": 1.8,
                        "height": 1.4,
                        "projectionDepth": 0.8,
                    },
                ],
            },
        }

        self.assertIn("无安全窗位", run_tool(fix_opening_fit, blueprint))
        self.assertEqual(
            [item["id"] for item in blueprint["geometry"]["components"]],
            ["door"],
        )
        self.assertNotIn("❌", run_tool(validate_opening_fit, blueprint))

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

    def test_l_shape_missing_notch_wall_is_repaired_while_t_junction_is_valid(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {"id": "floor_main", "type": "floor", "from": [0, 0, 0], "to": [18, 0, 8], "thickness": 0.2},
                    {"id": "floor_side", "type": "floor", "from": [12, 0, 8], "to": [18, 0, 12], "thickness": 0.2},
                    {"id": "front", "type": "wall", "from": [0, 0, 0], "to": [18, 3.2, 0], "thickness": 0.3},
                    {"id": "right", "type": "wall", "from": [18, 0, 0], "to": [18, 3.2, 12], "thickness": 0.3},
                    {"id": "side_back", "type": "wall", "from": [12, 0, 12], "to": [18, 3.2, 12], "thickness": 0.3},
                    {"id": "base_back", "type": "wall", "from": [0, 0, 8], "to": [12, 3.2, 8], "thickness": 0.3},
                    {"id": "left", "type": "wall", "from": [0, 0, 8], "to": [0, 3.2, 0], "thickness": 0.3},
                    {"id": "inner", "type": "wall", "from": [12, 0, 8], "to": [18, 3.2, 8], "thickness": 0.3},
                ],
                "components": [],
            }
        }

        initial = run_tool(validate_wall_junctions, blueprint)
        repair = run_tool(fix_wall_junctions, blueprint)

        self.assertIn("1 个孤立端点", initial)
        self.assertNotIn("inner.to", initial)
        self.assertIn("补齐楼板外边界墙段", repair)
        self.assertIn("闭合良好", run_tool(validate_wall_junctions, blueprint))
        repaired = next(
            item for item in blueprint["geometry"]["elements"]
            if item.get("id") == "wall_repair_1"
        )
        self.assertEqual(repaired["from"], [12.0, 0.0, 12.0])
        self.assertEqual(repaired["to"], [12.0, 3.2, 8.0])

    def test_structural_beam_joints_and_columns_embedded_in_walls_are_valid(self):
        blueprint = {
            "geometry": {
                "elements": [
                    {"id": "wall_x", "type": "wall", "from": [0, 0, 0], "to": [12, 3.2, 0], "thickness": 0.3},
                    {"id": "column_corner", "type": "column", "base": [0, 0, 0], "height": 3.2, "bottomRadius": 0.15, "topRadius": 0.15},
                    {"id": "beam_x", "type": "beam", "from": [0, 3.2, 0], "to": [12, 3.2, 0], "width": 0.2, "height": 0.3},
                    {"id": "beam_z", "type": "beam", "from": [12, 3.2, 0], "to": [12, 3.2, 8], "width": 0.2, "height": 0.3},
                ],
                "components": [],
            }
        }

        self.assertIn("碰撞检测通过", run_tool(validate_collision, blueprint))

        blueprint["geometry"]["elements"].append({
            "id": "beam_x_duplicate",
            "type": "beam",
            "from": [4, 3.2, 0],
            "to": [10, 3.2, 0],
            "width": 0.2,
            "height": 0.3,
        })
        self.assertIn("同轴重叠", run_tool(validate_collision, blueprint))

    def test_stepped_roof_is_fitted_to_top_storey_support_walls(self):
        base_walls = [
            {"id": "base_front", "type": "wall", "from": [0, 0, 0], "to": [18, 3.2, 0], "thickness": 0.3},
            {"id": "base_back", "type": "wall", "from": [18, 0, 12], "to": [0, 3.2, 12], "thickness": 0.3},
        ]
        upper_walls = [
            {"id": "upper_front", "type": "wall", "from": [0, 3.2, 0], "to": [12, 6.4, 0], "thickness": 0.3},
            {"id": "upper_back", "type": "wall", "from": [12, 3.2, 8], "to": [0, 6.4, 8], "thickness": 0.3},
            {"id": "upper_left", "type": "wall", "from": [0, 3.2, 8], "to": [0, 6.4, 0], "thickness": 0.3},
            {"id": "upper_right", "type": "wall", "from": [12, 3.2, 0], "to": [12, 6.4, 8], "thickness": 0.3},
        ]
        roof = {
            "id": "roof", "type": "roof", "roofType": "flat",
            "span": 18.6, "depth": 12.6, "position": [9, 6.4, 6],
            "height": 0.3, "thickness": 0.3,
        }
        blueprint = {"geometry": {"elements": [*base_walls, *upper_walls, roof], "components": []}}

        self.assertIn("悬空过多", run_tool(validate_roof_coverage, blueprint))
        run_tool(fix_roof_coverage, blueprint)

        self.assertEqual(roof["span"], 13.2)
        self.assertEqual(roof["depth"], 9.2)
        self.assertEqual(roof["position"], [6.0, 6.4, 4.0])
        self.assertIn("尺寸合理", run_tool(validate_roof_coverage, blueprint))
