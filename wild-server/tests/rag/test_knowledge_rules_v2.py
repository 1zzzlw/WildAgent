"""知识用途、来源隔离和类型路由回归；可用 unittest 离线运行。"""
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

from app.agent.knowledge_policy import (
    knowledge_hit_applies, matching_building_entities, plan_knowledge_query,
    restrict_building_query, term_is_requested,
)
from app.agent.research_evidence_gate import evaluate_knowledge_coverage
from app.agent.prompts import build_architecture_plan_prompt, build_skeleton_prompt


ROOT = Path(__file__).resolve().parents[3]
KB = ROOT / "wild-server/storage/knowledge_base"
LINT_PATH = ROOT / ".codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py"
spec = importlib.util.spec_from_file_location("rules_v2_linter", LINT_PATH)
lint = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lint
spec.loader.exec_module(lint)


class KnowledgeRulesTest(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "villa": {"filters": {"doc_type": "building_type"}, "applies_to": ["别墅", "villa"]},
            "courtyard": {"filters": {"doc_type": "building_type"}, "applies_to": ["四合院"]},
            "modern_villa": {"filters": {"doc_type": "building_type"}, "applies_to": ["现代别墅"]},
            "window": {"filters": {"doc_type": "component"}, "aliases": ["别墅", "窗"]},
        }

    def test_unknown_building_does_not_fall_back_to_villa(self):
        self.assertEqual(matching_building_entities("设计一栋自由形态建筑", self.catalog), [])
        result = restrict_building_query("设计一个火星基地", {"doc_type": "building_type"}, self.catalog)
        self.assertEqual(result["entity_name"], "__no_requested_building__")

    def test_generic_type_does_not_activate_specific_style(self):
        self.assertEqual(matching_building_entities("设计别墅", self.catalog), ["villa"])

    def test_explicit_type_supports_multiple_variants(self):
        self.assertEqual(matching_building_entities("比较现代别墅和四合院", self.catalog),
                         ["courtyard", "modern_villa", "villa"])

    def test_negated_style_is_not_activated(self):
        self.assertFalse(term_is_requested("不要四合院", "四合院"))
        self.assertFalse(term_is_requested("a house without courtyard", "courtyard"))
        self.assertFalse(term_is_requested("非对称", "对称"))
        self.assertTrue(term_is_requested("之前不要四合院，现在改成四合院", "四合院"))

    def test_explicit_filters_survive_routing(self):
        metadata = {"doc_type": "building_type", "entity_name": "villa", "building_category": "residential"}
        self.assertEqual(restrict_building_query("住宅", metadata, self.catalog), metadata)

    def test_global_query_also_rejects_unrequested_type(self):
        self.assertFalse(knowledge_hit_applies("生成办公楼", {"doc_type": "building_type", "applies_to": "别墅, villa"}))
        self.assertTrue(knowledge_hit_applies("设计一个 VILLA", {"doc_type": "building_type", "applies_to": "别墅, villa"}))

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

    def test_missing_optional_type_does_not_trigger_encyclopedia_research(self):
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

    def test_all_original_public_entities_retained(self):
        manifest = json.loads(
            (ROOT / "wild-server/tests/fixtures/rules_v2_public_entity_manifest.json")
            .read_text(encoding="utf-8")
        )
        current = (KB / "building_types/public/public-building-subtypes.md").read_text(encoding="utf-8")
        for entity in manifest:
            self.assertIn("entity_name: " + entity, current)

    def test_runtime_curtain_parameters_preserved_and_not_generation_context(self):
        text = (KB / "recipes/glass-curtain-wall-assembly.md").read_text(encoding="utf-8")
        block = text.split("entity_name: curtain_wall_deterministic_parameters", 1)[1].split("## ", 1)[0]
        self.assertIn("doc_scope: system", block)
        values = [json.loads(match) for match in re.findall(r"```json\s*\n(.*?)\n```", block, re.S)]
        self.assertEqual(values[0]["pane_module"], 1.4)


if __name__ == "__main__":
    unittest.main()
