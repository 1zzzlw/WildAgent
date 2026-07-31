import unittest
from pathlib import Path

from app.agent.prompts import build_system_prompt


SERVER_ROOT = Path(__file__).resolve().parents[1]
MINIMAL_SPEC = (
    SERVER_ROOT / "storage" / "knowledge_base" / "BLUEPRINT-SPEC-MINIMAL.md"
)


class PromptCompositionTest(unittest.TestCase):
    def test_loaded_spec_is_injected_once(self):
        marker = "UNIQUE_SPEC_MARKER"

        prompt = build_system_prompt(marker)

        self.assertEqual(prompt.count(marker), 1)

    def test_prompt_template_does_not_duplicate_wild_rules(self):
        prompt = build_system_prompt("UNIQUE_SPEC_MARKER")

        self.assertNotIn("# 空间规则", prompt)
        self.assertNotIn("## 规则 1：opening", prompt)
        self.assertNotIn("## 规则 5：必填字段", prompt)
        self.assertNotIn("## 规则 7：材质格式", prompt)

    def test_minimal_spec_contains_always_on_spatial_rules(self):
        minimal_spec = MINIMAL_SPEC.read_text(encoding="utf-8")

        self.assertIn("共享完全相同的端点坐标", minimal_spec)
        self.assertIn("get_wall_bounding_box", minimal_spec)
        self.assertIn("from[0] = 沿墙距离", minimal_spec)
        self.assertIn("baseColor 必须是 [R, G, B] 数组", minimal_spec)


if __name__ == "__main__":
    unittest.main()
