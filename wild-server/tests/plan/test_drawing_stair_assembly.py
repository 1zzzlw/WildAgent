"""楼梯与主体楼板分属任务时，局部修订和装配仍完成通道关系。"""
from copy import deepcopy

import pytest

from app.agent.design_flow.compile import compile_node
from app.agent.plan import implementation as impl
from app.agent.plan.expand import expand_design_markers
from app.agent.validation.candidate import evaluate_candidate
from app.agent.validation.diagnostics import blueprint_fingerprint
from app.design.markers import implementation_records
from app.design.resolver import build_design_document, resolve_design, _stable_hash
from app.tools.spatial_tools import collect_stair_placement_issues
from app.agent.generation.spatial.stair_openings import stair_opening_issues


def state_with_stair(*, axis=0, direction=1, offset=0, stair_status="implemented", exhausted=False):
    document = build_design_document({
        "concept": "楼梯装配", "massing": {"shape": "rect", "width": 10, "depth": 10, "floors": 2,
            "modeled_floors": 2, "floor_height": 3.2, "representation_mode": "full"},
        "volumes": [{"id": "main", "x": offset, "z": offset, "width": 10, "depth": 10,
                     "start_floor": 1, "end_floor": 2}],
        "structural_grid": {"system": "frame", "x_bays": 2, "z_bays": 2},
        "facades": {face: {"bays": 1, "ground_pattern": ["empty"], "upper_pattern": ["empty"]}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "flat"}, "circulation": {"vertical_strategy": "stair"},
        "components": [{"id": "stairs", "type": "stair", "host": "main", "size": {"width": 1.2}}],
    }, session_id="stair_test", source_request="生成两层建筑")
    resolved = resolve_design(document)
    state = {"design_document": document.model_dump(mode="json"),
        "resolved_design": resolved.model_dump(mode="json"), "drawing_hosts": resolved.projection_elements,
        "skeleton_blueprint": {"meta": {"version": "1.1", "type": "building", "name": "stairs",
            "designHash": _stable_hash(document), "designRevision": document.revision},
            "geometry": {"elements": [], "components": []}, "materials": {}, "assets": {}},
        "component_fragments": {}, "component_diagnostics": {}}
    plan = expand_design_markers(state)
    floors = [{"type": "floor", "id": f"floor_{i}", "from": [offset, y-0.15, offset],
               "to": [offset+10, y-0.15, offset+10], "thickness": 0.15} for i, y in enumerate((0, 3.2))]
    walls = [{k: v for k, v in wall.items() if k != "facing"} | {"thickness": 0.2}
             for wall in state["drawing_hosts"]]
    start, end = [offset+5, 0, offset+5], [offset+5, 3.2, offset+5]
    start[axis], end[axis] = offset+(2 if direction == 1 else 8), offset+(8 if direction == 1 else 2)
    stair = {"type": "stair", "id": "stairs", "from": start, "to": end, "width": 1.2}
    roof = {"type": "roof", "id": "roof_main", "roofType": "flat", "position": [offset+5, 6.4, offset+5],
            "span": 10.4, "depth": 10.4, "height": 0.2, "thickness": 0.2}
    for item in plan.items:
        marker_id = item.target["marker_ids"][0]
        entities = walls+floors if marker_id == "building_body" else [roof] if marker_id == "roof_main" else [stair]
        record = {"status": "implemented", "entity_ids": [e["id"] for e in entities],
                  "entity_fingerprint": blueprint_fingerprint(entities), "attempted_stages": ["generate"]}
        if marker_id == "stairs" and stair_status == "abandoned":
            entities = []
            record.update(status="abandoned", entity_ids=[], reason="楼梯实现失败",
                attempted_stages=["generate", "repair_1", "repair_2"] + (["assembly_revision"] if exhausted else []),
                attempts=[{"tool": "search_knowledge", "web_required": False},
                          *[{"stage": stage} for stage in ("generate", "repair_1", "repair_2")]])
        state["component_fragments"][item.id] = entities
        state["component_diagnostics"][item.id] = {"elements": [e["id"] for e in entities], "components": [],
            "implementations": {marker_id: record}}
        item.status = "abandoned" if record["status"] == "abandoned" else "done"
        item.run.artifacts = [e["id"] for e in entities]
    state["plan"] = plan.model_dump(mode="json")
    return state, stair


@pytest.mark.parametrize("axis,direction,offset", [(0, 1, 0), (0, -1, -12), (2, 1, 25), (2, -1, 0)])
def test_compile_opens_passage_without_rerunning_body_and_keeps_source_evidence(axis, direction, offset):
    state, _ = state_with_stair(axis=axis, direction=direction, offset=offset)
    before = deepcopy(state)
    result = run(compile_node(state))
    assert not result["compile_report"].get("retry_implementation")
    assert result["compile_report"]["ok"]
    assert state == before  # 保存的模型片段仍可用于追溯，编译只派生楼板分片。
    bp = result["merged_blueprint"]
    assert stair_opening_issues(bp) == []
    assert collect_stair_placement_issues(bp) == []
    original = impl.implementation_blueprint(state)
    assert bp["geometry"]["elements"][0] == original["geometry"]["elements"][0]
    assert next(e for e in bp["geometry"]["elements"] if e["id"] == "floor_0") == next(
        e for e in original["geometry"]["elements"] if e["id"] == "floor_0")
    records = result["design_brief"]["implementation"]["records"]
    assert records["stairs"] == implementation_records(state)["stairs"]
    assert records["building_body"]["assembly_changes"][0]["rule"] == "compiler.stair_openings"
    assert not evaluate_candidate(bp, design_document=state["design_document"],
                                  design_brief=result["design_brief"])["errors"]
    repeated = run(compile_node({**state, **result}))
    assert repeated["merged_blueprint"] == bp


def run(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("确定性装配不应执行异步 IO")


@pytest.mark.parametrize("endpoint", [[5, 3.2, 11], [5, 3.2, 10]])
def test_stair_endpoint_outside_or_at_edge_without_landing_is_local_failure(endpoint):
    state, stair = state_with_stair(axis=2)
    base = impl.implementation_blueprint(state)
    base["geometry"]["elements"] = [e for e in base["geometry"]["elements"] if e["type"] != "stair"]
    stair["to"] = endpoint
    with pytest.raises(ValueError, match="终点不在"):
        impl._accept_group(base, {"geometry": {"elements": [stair]}}, {"type": "stair", "design": {}})


def test_compiler_does_not_resign_tampered_source_floor():
    state, _ = state_with_stair()
    body_task = next(i for i in state["plan"]["items"] if i["kind"] == "building_body")
    floor = next(e for e in state["component_fragments"][body_task["id"]] if e["id"] == "floor_1")
    floor["thickness"] = 0.16
    result = run(compile_node(state))
    assert result["compile_report"]["retry_implementation"]
    assert "实现被修改" in result["compile_report"]["reason"]


@pytest.mark.parametrize("exhausted", [False, True])
def test_missing_stair_returns_to_its_marker_and_never_rebuilds_body(exhausted):
    state, _ = state_with_stair(stair_status="abandoned", exhausted=exhausted)
    result = run(compile_node(state))
    body_task = next(i for i in result["plan"]["items"] if i["kind"] == "building_body")
    stair_task = next(i for i in result["plan"]["items"] if i["kind"] == "stair")
    assert body_task["status"] == "done"
    assert "assembly_feedback" not in body_task["params"]
    assert result["component_fragments"][body_task["id"]] == state["component_fragments"][body_task["id"]]
    if exhausted:
        assert result["compile_report"]["ok"] is False
        assert not result["compile_report"].get("retry_implementation")
    else:
        assert result["compile_report"]["retry_implementation"]
        assert stair_task["params"]["retry_marker_ids"] == ["stairs"]


def test_local_revision_fixes_endpoint_before_assembly_and_reuses_knowledge(monkeypatch):
    import json
    from types import SimpleNamespace
    import app.llm.client as client
    import app.llm.invocation as invocation
    import app.agent.plan.knowledge_tool as knowledge
    from app.agent.plan.contracts import PlanDocument

    state, stair = state_with_stair(axis=2)
    item = next(i for i in PlanDocument.model_validate(state["plan"]).items if i.kind == "stair")
    state["component_fragments"].pop(item.id)
    state["component_diagnostics"].pop(item.id)
    events, contexts = [], []
    def rag(*args, **kwargs):
        events.append("rag")
        return {"text": "楼梯 JSON 示例", "has_shape_reference": True}
    async def model(_llm, messages):
        events.append("model")
        contexts.append(json.loads(messages[1]["content"]))
        entity = deepcopy(stair)
        if len(contexts) == 1:
            entity["to"][2] = 11
        return SimpleNamespace(content=json.dumps({"implementations": [{"id": "stairs",
            "geometry": {"elements": [entity], "components": []}}]}), token_usage={})
    monkeypatch.setattr(client, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    monkeypatch.setattr(knowledge, "search_knowledge_result", rag)
    updates, status, _, _, _ = run(impl.run_marker_generate(state, item))
    assert status == "succeeded" and events == ["rag", "model", "model"]
    record = implementation_records(updates)["stairs"]
    assert record["status"] == "implemented"
    assert record["attempted_stages"] == ["generate", "repair_1"]
    assert "终点不在" in contexts[1]["validation_feedback"]["stairs"]
    for key in ("component_fragments", "component_diagnostics"):
        state[key].update(updates[key])
    assert run(compile_node(state))["compile_report"]["ok"]


def test_discarding_invalid_stair_restores_unsplit_source_floor():
    state, stair = state_with_stair(axis=2)
    stair["to"][2] = 10  # 开洞后没有到达平台。
    record = implementation_records(state)["stairs"]
    record.update(entity_fingerprint=blueprint_fingerprint([stair]), attempted_stages=["generate", "assembly_revision"])
    result = run(compile_node(state))
    assert result["compile_report"]["ok"] is False
    assert result["compile_report"]["abandoned_markers"] == ["stairs"]
    floors = [e for e in result["merged_blueprint"]["geometry"]["elements"] if e["type"] == "floor"]
    assert len(floors) == 2
    assert not any("_opening_" in e["id"] for e in floors)

