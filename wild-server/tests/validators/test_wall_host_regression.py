"""退化墙体不能进入组件生成；方案和补墙修复使用共享契约。"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from app.agent.generation.architecture import (
    build_deterministic_skeleton, evaluate_skeleton_complexity,
    normalize_architecture_plan, resolve_facade_layout,
)
from app.tools.spatial_tools import (
    fix_wall_junctions, validate_element_dimensions,
    validate_model_quality, validate_opening_fit,
)


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/degenerate_wall_hosts.json"


def run_tool(tool, blueprint):
    return getattr(tool, "func", tool)(blueprint)


class WallHostRegressionTest(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_recorded_zero_length_hosts_fail_before_component_dispatch(self):
        # 粒度选择已下线（2026-09-30），使用固定标准档
        plan = deepcopy(self.case["architecture_plan"])
        result = evaluate_skeleton_complexity(self.case["skeleton_blueprint"], plan)
        self.assertFalse(result["meets_target"])
        self.assertFalse(result["checks"]["valid_wall_hosts"])
        self.assertEqual(len(result["degenerate_wall_ids"]), 8)
        output = run_tool(validate_element_dimensions, self.case["skeleton_blueprint"])
        self.assertIn("❌", output)
        self.assertIn("水平长度", output)

    def test_unknown_quota_type_is_attempted_via_generic_channel(self):
        """开放集契约（用户决策 2026-09-29，替代旧"未知构件拦截"守卫）：

        配额里注册表没有的类型（如 sunshade）不再进 ``unsupported`` 被拦下，
        而是保留配额、进入 required_components，由 plan 条目用
        ``generic_component_config`` 尝试生成——字段契约靠知识库检索，
        校验与修复环兜底。``unsupported_component_types`` 从此恒空。
        """
        plan = normalize_architecture_plan(self.case["architecture_plan"], self.case["user_message"])
        self.assertEqual(plan["unsupported_component_types"], [])
        self.assertIn("sunshade", plan["component_quota"])
        self.assertIn("sunshade", plan["required_components"])
        self.assertEqual(plan["component_quota"]["window"]["min"], 17)

    def test_rebuilt_plan_has_valid_hosts_and_sufficient_opening_slots(self):
        for width, depth in ((15, 12), (12, 9)):
            with self.subTest(width=width, depth=depth):
                raw = deepcopy(self.case["architecture_plan"])
                raw["massing"].update(width=width, depth=depth)
                raw["volumes"][0].update(width=width, depth=depth)
                plan = normalize_architecture_plan(raw, self.case["user_message"])
                blueprint = build_deterministic_skeleton(plan, self.case["user_message"])
                self.assertTrue(evaluate_skeleton_complexity(blueprint, plan)["meets_target"])
                self.assertNotIn("❌", run_tool(validate_element_dimensions, blueprint))
                self.assertNotIn("❌", run_tool(validate_model_quality, blueprint))
                brief = resolve_facade_layout(blueprint, plan)
                for kind in ("door", "window"):
                    slots = [slot for slot in brief["opening_slots"] if slot["type"] == kind]
                    self.assertGreaterEqual(len(slots), plan["component_quota"][kind]["min"])
                    self.assertLessEqual(len(slots), plan["component_quota"][kind]["max"])
                blueprint["geometry"]["components"] = [
                    {"type": slot["type"], "id": f"opening_{index}", "parentWall": slot["wall_id"],
                     "from": slot["from"], "width": slot["width"], "height": slot["height"]}
                    for index, slot in enumerate(brief["opening_slots"])
                ]
                self.assertNotIn("❌", run_tool(validate_opening_fit, blueprint))

    def test_degenerate_walls_are_not_used_to_guess_new_walls(self):
        blueprint = self.case["skeleton_blueprint"]
        before = deepcopy(blueprint)
        self.assertIn("❌", run_tool(fix_wall_junctions, blueprint))
        self.assertEqual(blueprint, before)

    def test_gap_is_filled_once_with_idempotent_repair(self):
        for width, depth in ((12, 9), (8, 6)):
            with self.subTest(width=width, depth=depth):
                blueprint = {"geometry": {"elements": [
                    {"type": "floor", "id": "plate", "from": [0, 0, 0], "to": [width, 0, depth], "thickness": 0.2},
                    {"type": "wall", "id": "a", "from": [0, 0, 0], "to": [width, 3, 0], "thickness": 0.3},
                    {"type": "wall", "id": "b", "from": [width, 0, 0], "to": [width, 3, depth], "thickness": 0.3},
                    {"type": "wall", "id": "c", "from": [width, 0, depth], "to": [0, 3, depth], "thickness": 0.3},
                ], "components": []}}
                run_tool(fix_wall_junctions, blueprint)
                self.assertEqual(len(blueprint["geometry"]["elements"]), 5)
                before = deepcopy(blueprint)
                run_tool(fix_wall_junctions, blueprint)
                self.assertEqual(blueprint, before)
                self.assertNotIn("❌", run_tool(validate_model_quality, blueprint))


if __name__ == "__main__":
    unittest.main()
