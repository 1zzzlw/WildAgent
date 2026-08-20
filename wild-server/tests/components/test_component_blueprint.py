import unittest

from app.services.agent_service import _apply_patch_to_blueprint
from app.tools.spatial_tools import (
    validate_blueprint_structure,
    validate_element_required_fields,
    validate_reference_integrity,
)
from app.utils.blueprint_parser import validate_blueprint_schema


def run_tool(tool, blueprint):
    return getattr(tool, "func", tool)(blueprint)


class ComponentBlueprintTest(unittest.TestCase):
    def test_supported_components_pass_backend_validation(self):
        blueprint = make_blueprint()

        self.assertEqual(validate_blueprint_schema(blueprint), [])
        self.assertNotIn("❌", run_tool(validate_blueprint_structure, blueprint))
        self.assertNotIn("❌", run_tool(validate_element_required_fields, blueprint))
        self.assertNotIn("❌", run_tool(validate_reference_integrity, blueprint))

    def test_component_and_element_ids_share_one_namespace(self):
        blueprint = make_blueprint()
        blueprint["geometry"]["components"][0]["id"] = "front_wall"

        issues = validate_blueprint_schema(blueprint)

        self.assertTrue(any("重复的构件 ID" in issue for issue in issues))

    def test_unknown_component_field_is_rejected(self):
        blueprint = make_blueprint()
        blueprint["geometry"]["components"][0]["swing"] = "left"

        issues = validate_blueprint_schema(blueprint)

        self.assertTrue(any("不支持的字段" in issue for issue in issues))

    def test_door_and_window_depth_fields_are_supported(self):
        blueprint = make_blueprint()
        door, window = blueprint["geometry"]["components"][:2]
        door.update({
            "frameDepth": 0.24,
            "leafDepth": 0.04,
            "openingStyle": "rectangular",
            "doorStyle": "single",
        })
        window.update({"frameDepth": 0.24, "glassDepth": 0.012})

        self.assertEqual(validate_blueprint_schema(blueprint), [])

        door["leafDepth"] = 0
        issues = validate_blueprint_schema(blueprint)
        self.assertTrue(any("leafDepth 必须是正有限数字" in issue for issue in issues))

    def test_scene_patch_can_add_update_and_remove_component(self):
        blueprint = make_blueprint()
        blueprint["geometry"]["components"] = []

        added = _apply_patch_to_blueprint(blueprint, {
            "operations": [{
                "op": "add_component",
                "component": {
                    "type": "railing",
                    "id": "patch_railing",
                    "path": [[0, 0, 0], [2, 0, 0]],
                    "height": 1.0,
                },
            }],
        })
        updated = _apply_patch_to_blueprint(added, {
            "operations": [{
                "op": "update_component",
                "id": "patch_railing",
                "changes": {"height": 1.2},
            }],
        })
        removed = _apply_patch_to_blueprint(updated, {
            "operations": [{
                "op": "remove_component",
                "id": "patch_railing",
            }],
        })

        self.assertEqual(updated["geometry"]["components"][0]["height"], 1.2)
        self.assertEqual(removed["geometry"]["components"], [])


def make_blueprint():
    return {
        "meta": {"version": "1.1", "type": "building", "name": "components"},
        "geometry": {
            "elements": [{
                "type": "wall",
                "id": "front_wall",
                "from": [0, 0, 0],
                "to": [8, 3, 0],
                "thickness": 0.24,
            }],
            "components": [
                {
                    "type": "door",
                    "id": "front_door",
                    "parentWall": "front_wall",
                    "from": [1, 0, 0],
                    "width": 1,
                    "height": 2.2,
                },
                {
                    "type": "window",
                    "id": "front_window",
                    "parentWall": "front_wall",
                    "from": [3, 0.9, 0],
                    "width": 1.5,
                    "height": 1.2,
                    "verticalMullions": 1,
                },
                {
                    "type": "railing",
                    "id": "terrace_railing",
                    "path": [[0, 0, 2], [3, 0, 2]],
                    "height": 1.1,
                },
                {
                    "type": "light",
                    "id": "desk_lamp",
                    "fixtureType": "table_lamp",
                    "position": [1.5, 0.75, 1.0],
                    "lightType": "point",
                    "color": [1.0, 0.78, 0.52],
                    "lowIntensity": 18,
                    "highIntensity": 65,
                    "distance": 8,
                    "height": 0.72,
                    "shadeRadius": 0.28,
                    "draggable": True,
                },
            ],
        },
        "materials": {},
        "behaviors": {},
    }


if __name__ == "__main__":
    unittest.main()
