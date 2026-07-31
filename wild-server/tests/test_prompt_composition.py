import unittest
from pathlib import Path

from app.agent.prompts import build_system_prompt
from app.services.agent_service import AgentService


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
        self.assertIn("sRGB authored value", minimal_spec)
        self.assertIn("玻璃材质必须显式给出 `opacity`", minimal_spec)

    def test_generation_prompt_requires_role_based_materials(self):
        prompt = build_system_prompt("UNIQUE_SPEC_MARKER")

        self.assertIn("墙、楼板、屋顶、门、玻璃使用角色独立的材质名", prompt)
        self.assertIn("玻璃材质必须显式给出 opacity", prompt)

    def test_generation_rag_query_includes_appearance_terms(self):
        service = AgentService.__new__(AgentService)

        generation_query = service._build_rag_query("生成一个别墅", None)
        chat_query = service._build_rag_query("什么是别墅", None)

        self.assertIn("默认材质", generation_query)
        self.assertIn("玻璃透明度", generation_query)
        self.assertNotIn("默认材质", chat_query)


if __name__ == "__main__":
    unittest.main()
