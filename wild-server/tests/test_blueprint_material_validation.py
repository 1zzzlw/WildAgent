import unittest

from app.utils.blueprint_parser import normalize_blueprint_input, validate_blueprint_schema
from app.tools.spatial_tools import (
    validate_element_dimensions,
    validate_element_required_fields,
)


class BlueprintMaterialValidationTest(unittest.TestCase):
    def test_hex_color_shorthand_is_normalized(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "test"},
            "geometry": {"elements": []},
            "materials": {
                "wall": {"color": "#F5F0E8", "roughness": 0.8},
            },
        }

        normalized = normalize_blueprint_input(blueprint)
        material = normalized["materials"]["wall"]

        self.assertAlmostEqual(material["baseColor"][0], 245 / 255)
        self.assertEqual(material["metallic"], 0.0)
        self.assertEqual(material["albedo"], 1.0)
        self.assertNotIn("color", material)

    def test_wall_height_shorthand_is_normalized(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "test"},
            "geometry": {
                "elements": [{
                    "id": "wall",
                    "type": "wall",
                    "from": [0, 3.2, 0],
                    "to": [12, 3.2, 0],
                    "height": 3,
                    "thickness": 0.25,
                }],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)
        wall = normalized["geometry"]["elements"][0]

        self.assertEqual(wall["to"][1], 6.2)
        self.assertNotIn("height", wall)

    def test_known_furniture_aliases_are_normalized(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "test"},
            "geometry": {
                "elements": [
                    {
                        "id": "sofa",
                        "type": "furniture",
                        "subtype": "sofa",
                        "position": [0, 0, 0],
                        "dimensions": {"width": 2, "depth": 1, "height": 0.8},
                    },
                    {
                        "id": "counter",
                        "type": "furniture",
                        "subtype": "counter",
                        "position": [3, 0, 0],
                        "dimensions": {"width": 2, "depth": 0.6, "height": 0.9},
                    },
                    {
                        "id": "bed",
                        "type": "furniture",
                        "subtype": "bed",
                        "position": [0, 0, 2],
                        "dimensions": {"width": 2, "depth": 2, "height": 0.5},
                    },
                ],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)
        subtypes = [
            element["subtype"]
            for element in normalized["geometry"]["elements"]
        ]

        self.assertEqual(subtypes, ["chair", "table", "bed"])
        self.assertEqual(blueprint["geometry"]["elements"][0]["subtype"], "sofa")
        validation = validate_element_required_fields.func(normalized)
        self.assertNotIn("❌", validation)

    def test_primitive_box_object_dimensions_are_normalized(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "asset", "name": "sofa"},
            "geometry": {
                "elements": [{
                    "id": "sofa_base",
                    "type": "primitive",
                    "shape": "box",
                    "position": [0, 0.15, 0],
                    "dimensions": {"width": 2.2, "height": 0.3, "depth": 0.9},
                }],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)
        dimensions = normalized["geometry"]["elements"][0]["dimensions"]

        self.assertEqual(dimensions, [2.2, 0.3, 0.9])
        self.assertEqual(
            blueprint["geometry"]["elements"][0]["dimensions"],
            {"width": 2.2, "height": 0.3, "depth": 0.9},
        )
        self.assertEqual(validate_blueprint_schema(normalized), [])
        self.assertNotIn("❌", validate_element_required_fields.func(normalized))

    def test_invalid_primitive_box_dimensions_are_rejected(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "asset", "name": "broken box"},
            "geometry": {
                "elements": [{
                    "id": "broken_box",
                    "type": "primitive",
                    "shape": "box",
                    "dimensions": {"width": 2.2, "height": 0.3},
                }],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)
        schema_issues = validate_blueprint_schema(normalized)
        field_issues = validate_element_required_fields.func(normalized)

        self.assertTrue(
            any("broken_box.dimensions" in issue for issue in schema_issues)
        )
        self.assertIn("❌", field_issues)
        self.assertIn("broken_box", field_issues)
        self.assertIn("[width, height, depth]", field_issues)

    def test_missing_base_color_is_rejected(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "test"},
            "geometry": {
                "elements": [{"id": "floor", "type": "floor"}],
            },
            "materials": {
                "broken": {
                    "roughness": 0.8,
                    "metallic": 0,
                    "albedo": 1,
                },
            },
        }

        issues = validate_blueprint_schema(blueprint)

        self.assertTrue(any("baseColor" in issue for issue in issues))

    def test_valid_base_color_is_accepted(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "test"},
            "geometry": {
                "elements": [{"id": "floor", "type": "floor"}],
            },
            "materials": {
                "valid": {
                    "baseColor": [0.2, 0.4, 0.6],
                    "roughness": 0.8,
                    "metallic": 0,
                    "albedo": 1,
                },
            },
        }

        issues = validate_blueprint_schema(blueprint)

        self.assertFalse(any("baseColor" in issue for issue in issues))

    def test_invalid_element_coordinate_is_rejected(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "test"},
            "geometry": {
                "elements": [{
                    "id": "floor_bad",
                    "type": "floor",
                    "from": [-7, 0, -2.5],
                    "to": [7, 10.5],
                    "thickness": 0.2,
                }],
            },
            "materials": {},
        }

        issues = validate_blueprint_schema(blueprint)

        self.assertTrue(
            any("floor_bad.to" in issue and "3 个有限数字" in issue for issue in issues)
        )

    def test_floor_coordinates_are_inferred_from_wall_footprint_and_story_levels(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "two floors"},
            "geometry": {
                "elements": [
                    {"id": "wall_front_1", "type": "wall", "from": [0, 0, 0], "to": [8, 3, 0]},
                    {"id": "wall_back_1", "type": "wall", "from": [8, 0, 6], "to": [0, 3, 6]},
                    {"id": "wall_left_1", "type": "wall", "from": [0, 0, 6], "to": [0, 3, 0]},
                    {"id": "wall_right_1", "type": "wall", "from": [8, 0, 0], "to": [8, 3, 6]},
                    {"id": "wall_front_2", "type": "wall", "from": [0, 3, 0], "to": [8, 6, 0]},
                    {"id": "wall_back_2", "type": "wall", "from": [8, 3, 6], "to": [0, 6, 6]},
                    {"id": "wall_left_2", "type": "wall", "from": [0, 3, 6], "to": [0, 6, 0]},
                    {"id": "wall_right_2", "type": "wall", "from": [8, 3, 0], "to": [8, 6, 6]},
                    {"id": "floor_ground", "type": "floor", "thickness": 0.2},
                    {"id": "floor_second", "type": "floor", "thickness": 0.2},
                ],
                "components": [],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)
        floors = {
            element["id"]: element
            for element in normalized["geometry"]["elements"]
            if element["type"] == "floor"
        }

        self.assertEqual(floors["floor_ground"]["from"], [0, 0, 0])
        self.assertEqual(floors["floor_ground"]["to"], [8, 0, 6])
        self.assertEqual(floors["floor_second"]["from"], [0, 3, 0])
        self.assertEqual(floors["floor_second"]["to"], [8, 3, 6])
        self.assertNotIn("❌", validate_element_dimensions.func(normalized))

    def test_floor_coordinate_objects_are_normalized_without_wall_inference(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "object coords"},
            "geometry": {
                "elements": [{
                    "id": "floor_ground",
                    "type": "floor",
                    "from": {"x": 0, "y": 0, "z": 0},
                    "to": {"x": 8, "y": 0, "z": 6},
                    "thickness": 0.2,
                }],
                "components": [],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)
        floor = normalized["geometry"]["elements"][0]

        self.assertEqual(floor["from"], [0, 0, 0])
        self.assertEqual(floor["to"], [8, 0, 6])
        self.assertNotIn("❌", validate_element_dimensions.func(normalized))

    def test_floor_without_coordinates_or_wall_footprint_remains_invalid(self):
        blueprint = {
            "meta": {"version": "1.1", "type": "building", "name": "unknown floor"},
            "geometry": {
                "elements": [{
                    "id": "floor_unknown",
                    "type": "floor",
                    "thickness": 0.2,
                }],
                "components": [],
            },
            "materials": {},
        }

        normalized = normalize_blueprint_input(blueprint)

        self.assertIn("❌", validate_element_dimensions.func(normalized))
