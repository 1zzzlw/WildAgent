import unittest

from app.utils.blueprint_parser import normalize_blueprint_input, validate_blueprint_schema


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
