import unittest
from copy import deepcopy

from app.tools.spatial_tools import (
    fix_opening_fit,
    fix_wall_junctions,
    validate_collision,
    validate_opening_fit,
    validate_wall_junctions,
)


def run_tool(tool, blueprint):
    return getattr(tool, "func", tool)(blueprint)


class SpatialValidationTest(unittest.TestCase):
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
