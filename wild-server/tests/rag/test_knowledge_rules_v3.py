"""rules-v3 知识用途、来源隔离和条件路由回归；可用 unittest 离线运行。"""
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

from app.agent.knowledge_policy import (
    GENERATION_ROLES, chat_knowledge_query_specs, knowledge_hit_applies, plan_knowledge_query,
    term_is_requested,
)
from app.agent.research_evidence_gate import evaluate_knowledge_coverage
from app.agent.prompts import build_architecture_plan_prompt, build_skeleton_prompt


SERVER_ROOT = Path(__file__).resolve().parents[2]
KB = SERVER_ROOT / "storage/knowledge_base"
LINT_PATH = SERVER_ROOT / "scripts/rag/lint_wild_rag_docs.py"
spec = importlib.util.spec_from_file_location("rules_v3_linter", LINT_PATH)
lint = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lint
spec.loader.exec_module(lint)


class KnowledgeRulesTest(unittest.TestCase):
    def test_generation_roles_only_contain_executable_knowledge(self):
        self.assertEqual(GENERATION_ROLES, ("protocol", "capability", "relation"))
        self.assertNotIn("identity", GENERATION_ROLES)

    def test_active_knowledge_base_has_no_building_type_documents(self):
        self.assertFalse((KB / "building_types").exists())

    def test_active_knowledge_base_has_no_unconsumed_reference_strategy(self):
        self.assertFalse((KB / "patterns").exists())
        for path in KB.rglob("*.md"):
            metadata = lint._resolved_frontmatter(
                path, path.read_text(encoding="utf-8").splitlines()
            )
            self.assertNotEqual(metadata.get("doc_scope"), "reference", path)
            self.assertNotEqual(metadata.get("knowledge_role"), "strategy", path)

    def test_active_knowledge_base_has_no_proposed_chunks(self):
        for path in KB.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("status: proposed", text, path)

    def test_negated_style_is_not_activated(self):
        self.assertFalse(term_is_requested("不要四合院", "四合院"))
        self.assertFalse(term_is_requested("a house without courtyard", "courtyard"))
        self.assertFalse(term_is_requested("非对称", "对称"))
        self.assertTrue(term_is_requested("之前不要四合院，现在改成四合院", "四合院"))

    def test_specialized_recipe_requires_selected_system(self):
        metadata = {"doc_type": "recipe", "applies_to": "幕墙, curtain_wall"}
        self.assertFalse(knowledge_hit_applies("生成小屋", metadata))
        self.assertTrue(knowledge_hit_applies("已选方案：幕墙", metadata))
        self.assertTrue(knowledge_hit_applies("任何建筑", {"doc_type": "recipe"}))

    def test_plan_query_preserves_user_and_selected_system_without_coordinates(self):
        query = plan_knowledge_query("住宅", {"concept": "幕墙围护", "roof": {"type": "gable"},
            "curtain_wall": True, "circulation": {"vertical_strategy": "core_and_stair"},
            "required_components": ["window"], "detail_packages": ["canopy"],
            "volumes": [{"x": 12345}]})
        self.assertIn("住宅", query)
        self.assertIn("幕墙", query)
        self.assertIn("gable", query)
        self.assertIn("core_and_stair", query)
        self.assertIn("canopy", query)
        self.assertNotIn("12345", query)

    def test_unknown_use_does_not_trigger_encyclopedia_research(self):
        hits = [{"metadata": {"doc_type": "component", "topic": "parameters", "entity_type": "wall"}},
                {"metadata": {"doc_type": "recipe", "topic": "assembly"}}]
        decision = evaluate_knowledge_coverage("生成新类型建筑", "unknown", hits)
        self.assertTrue(decision.sufficient)
        self.assertFalse(decision.trigger_web_research)
        self.assertEqual(decision.missing_required, [])

    def test_missing_engine_knowledge_is_reported_without_web_invention(self):
        decision = evaluate_knowledge_coverage("设计别墅", "villa", [])
        self.assertFalse(decision.sufficient)
        self.assertTrue(decision.missing_required)
        self.assertFalse(decision.trigger_web_research)

    def test_plan_prompt_has_no_fixed_building_or_profile_defaults(self):
        prompt = build_architecture_plan_prompt("关系规则", {"default_massing": [12, 9, 2, 3.2], "default_roof": "flat"})
        self.assertNotIn('"default_massing"', prompt)
        self.assertNotIn('"upper_setback"', prompt)
        self.assertNotIn('"balcony","canopy","bay_window"', prompt)

    def test_skeleton_fallback_no_longer_requires_copying_rag_example(self):
        prompt = build_skeleton_prompt("关系规则")
        self.assertNotIn("10×8m", prompt)
        self.assertNotIn("最少可行模板", prompt)
        self.assertIn("DESIGN_BRIEF", prompt)

    def test_scene_patch_protocol_explains_contextual_coordinate_updates(self):
        text = (KB / "BLUEPRINT-PATCH-PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("当前 Blueprint", text)
        self.assertIn("from[2]` 是法向偏移，不是世界 Z", text)
        self.assertIn('"op": "update_component"', text)

    def test_chat_queries_follow_the_three_active_knowledge_roles(self):
        queries = chat_knowledge_query_specs("怎么修改窗户的 Z 坐标")
        filters = [metadata_filter for _text, metadata_filter in queries]
        self.assertEqual(len(queries), 3)
        self.assertEqual(
            filters,
            [
                {"doc_type": "blueprint_spec", "knowledge_role": "protocol"},
                {"doc_type": "component", "knowledge_role": "capability"},
                {"doc_type": "recipe", "knowledge_role": "relation"},
            ],
        )
        source = (SERVER_ROOT / "app/agent/nodes/chat_node.py").read_text(encoding="utf-8")
        self.assertNotIn("建筑类型学", source)
        self.assertIn("不补建筑百科", source)

    def test_all_active_documents_pass_semantic_linter(self):
        errors = [issue for path in KB.rglob("*.md")
                  for issue in lint.lint_file(path, 120, 1600) + lint.cross_check_issues(path)
                  if issue.severity == "error"]
        self.assertEqual(errors, [])

    def test_linter_rejects_complete_building_in_system_protocol(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.md"
            path.write_text('---\ndoc_scope: system\n---\n# 示例\n```json\n'
                '{"geometry":{"elements":[{"type":"wall"}]}}\n```\n', encoding="utf-8")
            issues = lint.generation_policy_issues(path, path.read_text(encoding="utf-8").splitlines())
            self.assertIn("full_blueprint_in_generation", [issue.code for issue in issues])

    def test_linter_rejects_building_type_generation_documents(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "building-type.md"
            path.write_text(
                "---\ndoc_type: building_type\ndoc_scope: generation\n"
                "knowledge_role: identity\nstatus: supported\nauthority: maintainer\n---\n"
                "# 别墅\n类型描述。\n",
                encoding="utf-8",
            )
            issues = lint.generation_policy_issues(
                path, path.read_text(encoding="utf-8").splitlines()
            )
            self.assertIn("building_type_in_generation", [issue.code for issue in issues])

    def test_linter_rejects_proposed_chunks_in_generation_documents(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "component.md"
            path.write_text(
                "---\ndoc_type: component\ndoc_scope: generation\n"
                "knowledge_role: capability\nstatus: supported\nauthority: engine\n---\n"
                "# 构件\n<!-- rag-meta\nstatus: proposed\n-->",
                encoding="utf-8",
            )
            issues = lint.generation_policy_issues(
                path, path.read_text(encoding="utf-8").splitlines()
            )
            self.assertIn("proposed_chunk_in_generation", [issue.code for issue in issues])

    def test_runtime_curtain_parameters_preserved_and_not_generation_context(self):
        text = (KB / "recipes/glass-curtain-wall-assembly.md").read_text(encoding="utf-8")
        block = text.split("entity_name: curtain_wall_deterministic_parameters", 1)[1].split("## ", 1)[0]
        self.assertIn("doc_scope: system", block)
        values = [json.loads(match) for match in re.findall(r"```json\s*\n(.*?)\n```", block, re.S)]
        self.assertEqual(values[0]["pane_module"], 1.4)


if __name__ == "__main__":
    unittest.main()
