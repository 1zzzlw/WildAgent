"""并发结果的冲突归因、显式开口优先级及实际承托上下文。"""
from copy import deepcopy

import pytest

from app.agent.plan import implementation as impl
from app.design.markers import component_markers
from app.design.resolver import build_design_document


def blueprint():
    return {"meta": {"version": "1.1", "type": "building", "name": "test"}, "materials": {}, "assets": {},
            "geometry": {"elements": [{"type": "wall", "id": "wall_main_front_L1",
                "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}],
                "components": [window("old_a", 1), window("old_b", 1.5)]}}


def window(entity_id, x):
    return {"type": "window", "id": entity_id, "parentWall": "wall_main_front_L1",
            "from": [x, 1, 0], "width": 1, "height": 1}


@pytest.mark.parametrize("entity,bucket", [
    ({"type": "roof", "id": "new_roof", "roofType": "flat", "span": 10.4,
      "depth": 8.4, "height": 0.1, "thickness": 0.1, "position": [5, 3, 4]}, "elements"),
    (window("new_window", 7), "components"),
    ({"type": "stair", "id": "new_stair", "from": [5, 0, 4], "to": [5, 3, 8], "width": 1.2}, "elements"),
    ({"type": "light", "id": "new_light", "position": [5, 2.9, 4]}, "components"),
])
def test_existing_window_conflict_does_not_reject_unrelated_new_fragment(entity, bucket):
    base = blueprint()
    if entity["type"] == "stair":
        base["geometry"]["elements"].extend({"type": "floor", "id": f"support_{y}",
            "from": [0, y, 0], "to": [10, y, 10], "thickness": 0.15} for y in (0, 3))
    before = deepcopy(base)
    row = {"geometry": {"elements": [], "components": [], bucket: [entity]}}
    candidate, _, record = impl._accept_group(base, row, {"type": entity["type"], "design": {}})
    assert record["entity_ids"] == [entity["id"]]
    assert base == before
    assert impl.implementation_errors(candidate)  # 原冲突仍由统一装配处理，不能藏掉。


def test_new_conflict_still_fails_even_with_existing_window_conflict():
    with pytest.raises(ValueError, match="new_window"):
        impl._accept_group(blueprint(), {"geometry": {"components": [window("new_window", 1.2)]}},
                           {"type": "window", "design": {}})


def drawing():
    return build_design_document({"concept": "L形别墅", "massing": {"shape": "L", "width": 14, "depth": 10,
        "floors": 2, "modeled_floors": 2, "floor_height": 3},
        "volumes": [{"id": "main", "x": 0, "z": 0, "width": 10, "depth": 10,
                     "start_floor": 1, "end_floor": 2},
                    {"id": "annex", "x": 10, "z": 4, "width": 4, "depth": 6,
                     "start_floor": 1, "end_floor": 2}],
        "facades": {f: {"bays": 4, "ground_pattern": ["glass_sliding_door", "chinese_lattice_window", "window", "small_window"],
                          "upper_pattern": ["window"] * 4} for f in ("front", "back", "left", "right")},
        "structural_grid": {"system": "frame", "x_bays": 2, "z_bays": 2},
        "circulation": {"vertical_strategy": "central_stair"}, "roof": {"type": "gable"},
        "components": [{"id": "entry", "type": "glass_sliding_door", "host": "main",
                        "placement": {"position": [3.5, 1.2, 0]}, "size": {"width": 2.8, "height": 2.4}},
                       {"id": "lattice", "type": "chinese_lattice_window", "host": "main",
                        "placement": {"position": [6.5, 1.35, 0]}, "size": {"width": 1.5, "height": 1.8}},
                       {"id": "stairs", "type": "staircase", "host": "main",
                        "placement": {"position": [5, 1.5, 5]}, "size": {"width": 1.2, "height": 3, "depth": 3.6}}]},
        session_id="integration", source_request="生成别墅")


def test_volume_hosted_explicit_openings_replace_covered_facade_marks_without_mutating_design():
    document = drawing()
    before = document.model_dump(mode="json")
    markers = component_markers(document)
    ids = {m["id"] for m in markers}
    assert "glass_sliding_door_main_front_L1_1" not in ids
    assert "chinese_lattice_window_main_front_L1_2" not in ids
    assert "window_main_front_L1_3" not in ids
    assert "small_window_main_front_L1_4" in ids
    assert "glass_sliding_door_annex_front_L1_1" in ids
    assert {"entry", "lattice", "stairs"} <= ids
    assert document.model_dump(mode="json") == before


def test_volume_context_includes_real_supports_and_other_items_on_that_volume():
    document = drawing()
    markers = component_markers(document)
    roof = next(m for m in markers if m["id"] == "roof_main")
    base = blueprint()
    base["geometry"]["elements"].extend([
        {"type": "wall", "id": "wall_main_front_L2", "from": [0, 3, 0], "to": [10, 5.85, 0], "thickness": 0.2},
        {"type": "floor", "id": "slab_main", "from": [0, 2.85, 0], "to": [10, 2.85, 10], "thickness": 0.15},
        {"type": "wall", "id": "wall_annex_front_L2", "from": [10, 3, 4], "to": [14, 5.85, 4], "thickness": 0.2},
    ])
    context = impl._item_context({"design_document": document.model_dump(mode="json"), "resolved_design": {"component_markers": markers}},
                                 {roof["id"]: roof}, base)
    ids = {e["id"] for e in context["existing_blueprint"]["geometry"]["elements"]}
    assert {"wall_main_front_L1", "wall_main_front_L2", "slab_main"} <= ids
    assert "wall_annex_front_L2" not in ids
    body = impl._item_context({"design_document": document.model_dump(mode="json")}, {"building_body": markers[0]}, base)
    assert body["drawing"]["delegated_components"][0]["id"] == "stairs"


def test_staircase_alias_receives_native_stair_schema_and_chinese_label():
    from app.agent.knowledge.component_names import resolve_component_name
    from app.agent.generation.capability import load_engine_schema
    assert resolve_component_name("staircase") == {"kind": "stair", "label": "楼梯", "entity_type": "stair"}
    marker = {"type": "staircase", "design": {}}
    protocol = impl._output_protocol(load_engine_schema(), {"stairs": marker}, "", {})
    assert '"const":"stair"' in protocol


def test_named_shape_uses_exact_knowledge_before_family_fallback(monkeypatch):
    from types import SimpleNamespace
    from app.services import agent_service as service_module
    from app.agent.plan.knowledge_tool import search_knowledge_result
    calls = []
    chunk = SimpleNamespace(document='```json\n{"type":"window"}\n```', metadata={
        "entity_name": "chinese_lattice_window", "entity_type": "window", "topic": "composition"})
    loader = SimpleNamespace(last_results=[])
    def load_many(queries, **kwargs):
        calls.append(queries[0].metadata_filter)
        loader.last_results = [chunk]
        return chunk.document
    loader.load_many = load_many
    monkeypatch.setattr(service_module, "agent_service", SimpleNamespace(spec_loader=loader))
    assert search_knowledge_result("格棂窗 JSON 示例", kind="chinese_lattice_window")["has_shape_reference"]
    assert calls == [{"doc_type": "component", "entity_name": "chinese_lattice_window"}]


@pytest.mark.parametrize("query,expected", [("chinese_lattice_window JSON 示例", True),
                                         ("现代中式别墅", False),
                                         ("不要 chinese_lattice_window", False)])
def test_named_shape_is_not_rejected_by_inherited_system_terms(query, expected):
    from app.agent.knowledge.policy import knowledge_hit_applies
    assert knowledge_hit_applies(query, {"entity_name": "chinese_lattice_window",
        "applies_to": "中式格棂门窗,隔扇门"}) is expected


@pytest.mark.parametrize("scale,offset", [(1, 0), (0.8, -9), (2, 25)])
def test_l_shaped_body_slabs_preserve_void_under_translation_and_scale(scale, offset):
    from app.design.markers import body_floor_errors
    design = component_markers(drawing())[0]["design"]
    for v in design["volumes"]:
        for key in ("x", "z"):
            v[key] = v[key]*scale + offset
        for key in ("width", "depth"):
            v[key] *= scale
    slabs = [{"type": "floor", "id": "bounding_slab", "from": [offset, 2.85, offset],
              "to": [offset+14*scale, 2.85, offset+10*scale], "thickness": 0.15}]
    assert body_floor_errors(slabs, design)
    correct = [{"type": "floor", "id": v["id"]+"_slab", "from": [v["x"], 2.85, v["z"]],
                "to": [v["x"]+v["width"], 2.85, v["z"]+v["depth"]], "thickness": 0.15}
               for v in design["volumes"]]
    assert body_floor_errors(correct, design) == []


def test_body_floor_guard_is_used_by_fragment_validation():
    design = component_markers(drawing())[0]["design"]
    base = blueprint()
    base["geometry"] = {"elements": [], "components": []}
    bad = {"type": "floor", "id": "bad_slab", "from": [0, 2.85, 0], "to": [14, 2.85, 10], "thickness": 0.15}
    with pytest.raises(ValueError, match="体量并集"):
        impl._accept_group(base, {"geometry": {"elements": [bad]}}, {"type": "building_body", "design": design})


def test_final_gate_rechecks_body_footprint_despite_valid_implementation_fingerprint():
    from app.agent.validation.candidate import evaluate_candidate
    from app.agent.validation.diagnostics import blueprint_fingerprint
    from app.design.resolver import _stable_hash
    document = drawing()
    base = blueprint()
    base["geometry"] = {"elements": [], "components": []}
    records = {}
    for marker in component_markers(document):
        entity = ({"type": "floor", "id": "bad_slab", "from": [0, 2.85, 0], "to": [14, 2.85, 10], "thickness": 0.15}
                  if marker["id"] == "building_body" else {"type": "primitive", "id": marker["id"],
                      "shape": "box", "dimensions": [0.1, 0.1, 0.1], "position": [0, 0, 0]})
        base["geometry"]["elements"].append(entity)
        records[marker["id"]] = {"status": "implemented", "entity_ids": [entity["id"]],
                               "entity_fingerprint": blueprint_fingerprint([entity])}
    result = evaluate_candidate(base, design_document=document.model_dump(mode="json"),
        design_brief={"implementation": {"design_hash": _stable_hash(document), "records": records}})
    assert any(e.name == "design_body_footprint" for e in result["errors"])
    assert result["snapshot"]["status"] == "partial"


@pytest.mark.parametrize("face,position", [("front", [3.75, 1.5, 0]), ("back", [6.25, 1.5, 10]),
                                          ("right", [10, 1.5, 3.75]), ("left", [0, 1.5, 6.25])])
def test_explicit_world_opening_uses_wall_direction_on_all_facades(face, position):
    from app.design.contracts import ComponentInstance, FacadeDecision
    document = drawing()
    document.decisions.volumes = document.decisions.volumes[:1]
    document.decisions.components = [ComponentInstance(id="explicit_window", type="window", host="main",
        placement={"position": position}, size={"width": 1, "height": 1})]
    document.decisions.facades[face] = FacadeDecision(bays=4, ground_pattern=["window"]*4, upper_pattern=["window"]*4)
    markers = component_markers(document)
    ids = {m["id"] for m in markers}
    assert f"window_main_{face}_L1_2" not in ids
    assert f"window_main_{face}_L1_1" in ids
    assert f"window_main_{face}_L1_3" in ids
    assert next(m for m in markers if m["id"] == "explicit_window")["host"] == f"wall_main_{face}_L1"
