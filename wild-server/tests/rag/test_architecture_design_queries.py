"""检索由当前设计阶段与选择驱动，不由建筑用途附加造型套餐。"""
from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME, block_knowledge_query_specs


def test_intent_query_targets_design_expression():
    queries = block_knowledge_query_specs(BLOCK_BY_NAME["intent"], "生成一个别墅")
    assert queries[0].metadata_filter == {"doc_type": "component", "entity_name": "architecture_design_expression"}


def test_roof_query_uses_current_roof_without_inventing_tower_keywords():
    queries = block_knowledge_query_specs(BLOCK_BY_NAME["roof"], "生成一座塔",
        {"roof": {"type": "gable"}, "design_intent": {"selected_systems": ["elevator"]}})
    assert len(queries) == 1
    assert "gable" in queries[0].text
    assert "斗拱" not in queries[0].text and "chinese_pagoda" not in queries[0].text


def test_components_query_preserves_relations_and_selected_systems():
    queries = block_knowledge_query_specs(BLOCK_BY_NAME["components"], "生成一个别墅",
        {"design_intent": {"selected_systems": ["canopy", "canopy"]}, "components": [{"type": "cornice"}]})
    assert any(q.metadata_filter.get("entity_name") == "supported_assembly_relations" for q in queries)
    assert len([q for q in queries if q.text.startswith("canopy ")]) == 1
    assert any(q.text.startswith("cornice ") for q in queries)
    assert all(q.metadata_filter for q in queries)


def test_stage_queries_have_answers_in_current_corpus():
    from pathlib import Path
    import yaml
    from app.spec.loader import MarkdownChunker
    root = Path(__file__).parents[2] / "storage/knowledge_base"
    names = {yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1]).get("entity_name")
             for path in root.rglob("*.md") if path.read_text(encoding="utf-8").startswith("---")}
    for block in BLOCK_BY_NAME.values():
        for query in block.knowledge_queries:
            assert query.metadata_filter["entity_name"] in names
    chunks = MarkdownChunker().split_file(root / "knowledge/components/architecture-design-expression.md", namespace="test")
    assert chunks
