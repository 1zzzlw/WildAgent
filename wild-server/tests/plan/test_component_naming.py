"""模型换语言或叫法后，任务分类与知识查询仍使用同一构件名称。"""
from types import SimpleNamespace

import pytest

from app.agent.plan.expand import expand_design_markers
from app.agent.plan.knowledge_tool import search_knowledge_impl
from app.spec.loader import SpecLoadResult


@pytest.mark.parametrize("names,kind,label", [
    (["实墙", "实体墙", "Solid Wall", "solid_wall"], "solid_wall", "实墙"),
    (["落地窗", "floor-to-ceiling window", "floorWindow"], "floor_window", "落地窗"),
    (["窗", "Window", "window"], "window", "窗"),
    (["窗", "window_rectangular", "window_center", "rectangularWindow", "矩形窗"], "window", "窗"),
    (["门", "opening_door", "door_entrance", "openingDoor"], "door", "门"),
    (["屋顶", "Roof", "roof"], "roof", "屋顶"),
    (["building_body", "建筑主体", "building body"], "building_body", "建筑主体"),
])
def test_aliases_share_one_plan_group(names, kind, label):
    markers = [{"id": f"part_{i}", "type": name, "depends_on": [], "design": {}}
               for i, name in enumerate(names)]
    state = {"resolved_design": {"design_hash": "approved", "component_markers": markers}}
    plan = expand_design_markers(state)
    assert len(plan.items) == 1
    assert (plan.items[0].kind, plan.items[0].label) == (kind, label)
    assert plan.items[0].target["marker_ids"] == [m["id"] for m in markers]
    assert [m["type"] for m in markers] == names


def test_batch_load_measures_the_actual_markers_and_keeps_minimal_window_coalescing():
    import json
    markers = [{"id": "body", "type": "building_body", "depends_on": [], "design": {}}]
    windows = [{"id": f"window_{i}", "type": "落地窗" if i % 2 else "window",
                "depends_on": ["body"], "host": f"wall_{i % 2}",
                "design": {"floor": i % 2 + 1, "form": {"description": "自然采光"}}}
               for i in range(8)]
    markers.extend(windows)
    state = {"design_document": {"decisions": {"complexity": {"level": "minimal"}}},
             "resolved_design": {"design_hash": "approved", "component_markers": markers}}
    plan = expand_design_markers(state)
    assert len(plan.items) == 2
    item = plan.items[1]
    assert item.kind == "window" and item.depends_on == [plan.items[0].id]
    assert item.target["marker_ids"] == [m["id"] for m in windows]
    assert item.params["batch_load"] == {"marker_count": 8, "host_count": 2,
        "floor_count": 2, "dependency_count": 1,
        "marker_chars": len(json.dumps(windows, ensure_ascii=False, separators=(",", ":")))}


@pytest.mark.parametrize("names,entity_type,kind,label", [
    (["落地窗", "floor-to-ceiling window", "floor_window"], "window", "floor_window", "落地窗"),
    (["实墙", "实体墙", "solid_wall"], "wall", "solid_wall", "实墙"),
    (["opening_door", "door_entrance", "openingDoor", "门"], "door", "door", "门"),
    (["window_rectangular", "window_center", "rectangularWindow", "矩形窗"], "window", "window", "窗"),
])
def test_aliases_produce_identical_knowledge_queries(monkeypatch, names, entity_type, kind, label):
    from app.services import agent_service as service_module
    calls = []

    def load_many_result(queries, **kwargs):
        calls.append((queries[0].text, queries[0].metadata_filter))
        return SpecLoadResult("构件示例")

    loader = SimpleNamespace(load_many_result=load_many_result)
    monkeypatch.setattr(service_module, "agent_service", SimpleNamespace(spec_loader=loader))
    for name in names:
        search_knowledge_impl("WILD JSON 实现示例", kind=name)
    expected = {"doc_type": "component", "entity_name" if kind != entity_type else "entity_type": kind}
    assert calls == [(f"{kind} {label} WILD JSON 实现示例", expected)] * len(names)


def test_custom_component_remains_available_with_chinese_display_name():
    marker = {"id": "custom_1", "type": "Solar Mesh Canopy", "depends_on": [],
              "design": {"name": "太阳能网格雨棚", "form": {"pattern": "自由网格"}}}
    state = {"resolved_design": {"design_hash": "approved", "component_markers": [marker]}}
    item = expand_design_markers(state).items[0]
    assert (item.kind, item.label) == ("solar_mesh_canopy", "太阳能网格雨棚")
    assert marker["design"]["form"] == {"pattern": "自由网格"}


def test_prompt_uses_the_same_names_as_plan():
    from app.agent.prompts.planning import build_architecture_plan_prompt
    prompt = build_architecture_plan_prompt("")
    assert "floor_window=落地窗" in prompt
    assert "solid_wall=实墙" in prompt
    assert "roof=屋顶" in prompt
    assert "新构件可自行取" in prompt


def test_new_single_component_document_supplies_names_without_code_changes(tmp_path, monkeypatch):
    from app.agent.knowledge import component_names as naming
    config = tmp_path / "config.yaml"
    config.write_text("defaults:\n  knowledge_revision: rules-v1\n", encoding="utf-8")
    document = tmp_path / "twisted-column.md"
    document.write_text("""---
entity_name: twisted_column
entity_type: column
doc_scope: generation
knowledge_role: capability
topic: composition
status: experimental
authority: schema
primary_terms:
  - 扭转柱
synonyms:
  - twisted column
---
# 扭转柱

以下是局部示例，具体截面、位置和尺寸仍由图纸选择。

```json
{"elements":[],"components":[]}
```
""", encoding="utf-8")
    signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in (config, document))
    monkeypatch.setattr(naming, "_catalog", lambda: naming._catalog_for_files(signature))
    for name in ("扭转柱", "twisted column", "twistedColumn"):
        assert naming.resolve_component_name(name) == {
            "kind": "twisted_column", "label": "扭转柱", "entity_type": "column"}
