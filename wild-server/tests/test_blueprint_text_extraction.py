import unittest

from app.utils.blueprint_parser import (
    extract_blueprint_from_text,
    extract_patch_from_text,
    normalize_blueprint_input,
)
from app.agent.nodes.skeleton_node import (
    _parse_components_from_reply,
    _parse_design_brief,
)


class BlueprintTextExtractionTest(unittest.TestCase):
    def test_unfenced_blueprint_is_found_after_reasoning_json(self):
        text = """
        先规划数量：{"component_quota":{"door":{"min":1,"max":2}}}
        _components: door, window, roof
        {
          "meta": {"version": "1.1", "type": "building", "name": "欧式别墅"},
          "geometry": {"elements": [], "components": []},
          "materials": {},
          "behaviors": {}
        }
        DESIGN_BRIEF: {"facade_plan": {}}
        """

        blueprint = extract_blueprint_from_text(text)

        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint["meta"]["name"], "欧式别墅")

    def test_patch_extraction_does_not_depend_on_blueprint_shape(self):
        text = """
        ```json
        {"operations":[{"op":"remove_element","id":"wall_old"}]}
        ```
        """

        patch = extract_patch_from_text(text)

        self.assertEqual(patch["summary"], "修改场景")
        self.assertEqual(patch["operations"][0]["id"], "wall_old")

    def test_blueprint_is_found_inside_common_model_wrapper(self):
        text = """
        {
          "result": {
            "blueprint": {
              "meta": {"version": "1.1", "type": "building", "name": "包装骨架"},
              "geometry": {"elements": [{"id": "floor_1", "type": "floor"}], "components": []},
              "materials": {}
            }
          },
          "design_brief": {"component_quota": {"door": {"min": 1}}}
        }
        """

        blueprint = extract_blueprint_from_text(text)

        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint["meta"]["name"], "包装骨架")

    def test_normalization_fills_deterministic_blueprint_metadata(self):
        normalized = normalize_blueprint_input({
            "meta": {"type": "building"},
            "geometry": {"elements": [], "components": []},
            "materials": {},
        })

        self.assertEqual(normalized["meta"]["version"], "1.1")
        self.assertEqual(normalized["meta"]["type"], "building")
        self.assertEqual(normalized["meta"]["name"], "AI生成建筑")

    def test_reasoning_markers_skip_planning_mentions_and_parse_final_values(self):
        text = """
        需要输出：_components: 列表（door, window, roof）
        DESIGN_BRIEF: JSON
        _components: door, window, roof, stair
        DESIGN_BRIEF:
        {"facade_plan":{"wall_front":{"max_openings":2}},
         "component_quota":{"door":{"min":1,"max":1}}}
        检查完毕。
        """

        self.assertEqual(
            _parse_components_from_reply(text),
            ["door", "window", "roof", "stair"],
        )
        brief = _parse_design_brief(text)
        self.assertEqual(brief["component_quota"]["door"]["min"], 1)


if __name__ == "__main__":
    unittest.main()
