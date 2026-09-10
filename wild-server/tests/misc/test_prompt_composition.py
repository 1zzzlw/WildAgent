import unittest
from pathlib import Path

from app.agent.prompts import build_system_prompt
from app.services.agent_service import AgentService


SERVER_ROOT = Path(__file__).resolve().parents[2]
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
        self.assertIn('物理玻璃必须给出 `materialClass: "glass"`', minimal_spec)
        self.assertIn("`transmission > 0`", minimal_spec)
        self.assertIn("`opacity` 必须为 `1` 或省略", minimal_spec)

    def test_generation_prompt_requires_role_based_materials(self):
        prompt = build_system_prompt("UNIQUE_SPEC_MARKER")

        self.assertIn("墙、楼板、屋顶、门、玻璃使用角色独立的材质名", prompt)
        self.assertIn("新生成玻璃使用受控物理材质", prompt)
        self.assertIn("用户需求和已批准方案决定造型", prompt)
        self.assertIn("`cornice`、`chimney`、`light` 已由组合构件编译器支持", prompt)
        self.assertIn("fixtureType=table_lamp", prompt)
        self.assertIn("furniture.subtype=lamp 只是旧版静态家具占位", prompt)
        self.assertIn("只能写入 `geometry.components`", prompt)
        self.assertIn("严禁发明 sofa、counter 等值", prompt)

    def test_generation_rag_query_asks_for_implementation_relations(self):
        service = AgentService.__new__(AgentService)

        generation_query = service._build_rag_query("生成一个别墅", None)
        chat_query = service._build_rag_query("什么是别墅", None)

        self.assertIn("WILD 能力边界", generation_query)
        self.assertIn("构件宿主和组装关系", generation_query)
        self.assertNotIn("默认材质", generation_query)
        self.assertNotIn("默认材质", chat_query)

    def test_building_generation_uses_component_rag_queries(self):
        service = AgentService.__new__(AgentService)

        queries = service._build_rag_queries("生成一个别墅", None)
        asset_queries = service._build_rag_queries("生成一个篮球", None)
        combined = "\n".join(query.text for query in queries)

        self.assertEqual(len(queries), 7)
        self.assertIn("已选构件的条件关系", combined)
        self.assertIn("结构构件能力", combined)
        self.assertIn("墙体构件能力", combined)
        self.assertIn("窗构件能力", combined)
        self.assertIn("门构件能力", combined)
        self.assertIn("栏杆构件能力", combined)
        self.assertIn("屋顶构件能力", combined)
        self.assertEqual(len(asset_queries), 1)

    def test_building_queries_receive_business_metadata_filters(self):
        service = AgentService.__new__(AgentService)
        queries = service._build_rag_queries("生成一个别墅", None)

        self.assertEqual(
            [query.metadata_filter for query in queries],
            [
                {"doc_type": "recipe", "entity_name": "component_selection_conditions"},
                {"doc_type": "component", "entity_type": "structural_component"},
                {"doc_type": "component", "entity_type": "wall"},
                {"doc_type": "component", "entity_type": "window"},
                {"doc_type": "component", "entity_type": "door"},
                {"doc_type": "component", "entity_type": "railing"},
                {"doc_type": "component", "entity_type": "roof"},
            ],
        )

    def test_blueprint_edit_queries_cover_protocol_capability_and_relation(self):
        service = AgentService.__new__(AgentService)
        queries = service._build_rag_queries(
            "把 window_1 沿 Z 轴移动",
            {
                "meta": {"name": "current"},
                "geometry": {
                    "elements": [{"type": "wall"}],
                    "components": [{"type": "window"}],
                },
            },
        )

        self.assertEqual(len(queries), 3)
        self.assertEqual(
            [query.metadata_filter for query in queries],
            [
                {"doc_type": "blueprint_spec", "knowledge_role": "protocol"},
                {"doc_type": "component", "knowledge_role": "capability"},
                {"doc_type": "recipe", "knowledge_role": "relation"},
            ],
        )
        self.assertIn("window", queries[0].text)


if __name__ == "__main__":
    unittest.main()
