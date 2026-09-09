"""实际构建组件提示词，覆盖生成前的代码路径；不依赖模型或网络。"""
import unittest

from app.agent.component_registry import COMPONENT_REGISTRY
from app.agent.prompts import build_component_prompt


class ComponentPromptTest(unittest.TestCase):
    def test_every_registered_component_builds_prompt(self):
        for component_type, config in COMPONENT_REGISTRY.items():
            with self.subTest(component_type=component_type):
                prompt = build_component_prompt("能力规则", component_type, "骨架摘要")
                self.assertIn(f"你是 {config.label} 组件生成专家", prompt)
                self.assertIn(f"只生成 {component_type}", prompt)
                self.assertIn("能力规则", prompt)
                self.assertIn("骨架摘要", prompt)

    def test_labels_do_not_replace_selected_quota_or_extra_rules(self):
        prompt = build_component_prompt(
            "", "balcony", "骨架", extra_rules="沿批准位置生成",
            design_brief={"component_quota": {"balcony": {"min": 2, "max": 2, "note": "两翼各一个"}},
                          "rag_reference": "已选阳台的宿主关系"},
        )
        self.assertIn("阳台总数: 2~2 个", prompt)
        self.assertIn("两翼各一个", prompt)
        self.assertIn("# 阳台 专属规则", prompt)
        self.assertIn("沿批准位置生成", prompt)
        self.assertIn("已选阳台的宿主关系", prompt)

    def test_opening_slots_stay_separate_for_door_and_window(self):
        brief = {"opening_slots": [
            {"type": "door", "wall_id": "door_host", "from": [1, 0, 0], "width": 1, "height": 2},
            {"type": "window", "wall_id": "window_host", "from": [2, 1, 0], "width": 1, "height": 1},
        ]}
        for component_type, own_host, other_host in (
            ("door", "door_host", "window_host"), ("window", "window_host", "door_host"),
        ):
            with self.subTest(component_type=component_type):
                prompt = build_component_prompt("", component_type, "骨架", design_brief=brief)
                self.assertIn(own_host, prompt)
                self.assertNotIn(other_host, prompt)

    def test_unmapped_label_falls_back_to_type_name(self):
        prompt = build_component_prompt("", "custom_type", "骨架")
        self.assertIn("你是 custom_type 组件生成专家", prompt)
        self.assertIn("楼梯 组件生成专家", build_component_prompt("", "stair", "骨架"))

    def test_opening_rules_do_not_reintroduce_fixed_building_templates(self):
        door_prompt = build_component_prompt(
            "", "door", "骨架", extra_rules=COMPONENT_REGISTRY["door"].extra_rules,
        )
        window_prompt = build_component_prompt(
            "", "window", "骨架", extra_rules=COMPONENT_REGISTRY["window"].extra_rules,
        )
        self.assertIn("服从 DesignDocument 解析出的槽位", door_prompt)
        self.assertIn("服从 DesignDocument 解析出的槽位", window_prompt)
        self.assertNotIn("一栋建筑通常只有 1~2 个门", door_prompt)
        self.assertNotIn("每面墙最多 2~3 个窗", window_prompt)


if __name__ == "__main__":
    unittest.main()
