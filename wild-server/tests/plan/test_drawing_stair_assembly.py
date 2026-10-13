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
from app.tools.spatial_tools import collect_stair_placement_issues, validate_stair_alignment, validate_collision
from app.agent.generation.spatial.stair_openings import cut_stair_openings, stair_opening_issues


@pytest.mark.parametrize("base,height", [(0.45, 3.6), (-2, 3), (5, 4.2)])
def test_declared_floor_surfaces_drive_hosts_openings_and_roof_without_rewriting_design(base, height):
    from tests.plan.test_drawing_implementation import drawing
    from app.design.resolver import architecture_plan_from_document
    raw = architecture_plan_from_document(drawing())
    raw["massing"].update(floors=2, modeled_floors=2, floor_height=height)
    raw["volumes"][0]["end_floor"] = 2
    raw["floor_layouts"] = [{"floor": 1, "level": base}, {"floor": 2, "level": base+height}]
    raw["components"] = [{"id": "upper_window", "type": "window", "host": "main",
        "placement": {"face": "front", "floor": 2, "offset": 2, "sill_height": 0.5},
        "size": {"width": 1, "height": 1}}]
    document = build_design_document(raw, session_id="elevations", source_request="生成两层建筑")
    before = document.model_dump(mode="json")
    resolved = resolve_design(document)
    assert [level.base_y for level in resolved.levels] == pytest.approx([base, base+height])
    assert [level.top_y for level in resolved.levels] == pytest.approx([base+height, base+2*height])
    wall = next(w for w in resolved.projection_elements if w["id"] == "wall_main_front_L2")
    assert wall["from"][1] == pytest.approx(base+height)
    opening = next(m for m in resolved.component_markers if m["id"] == "upper_window")
    assert opening["entity"]["from"][1] == pytest.approx(base+height+0.5)
    roof = next(m for m in resolved.component_markers if m["id"] == "roof_main")
    assert roof["entity"]["position"][1] == pytest.approx(base+2*height)
    context = impl._item_context({"design_document": before, "resolved_design": resolved.model_dump(mode="json"),
        "drawing_hosts": resolved.projection_elements}, {"building_body": resolved.component_markers[0]},
        {"geometry": {"elements": [], "components": []}, "materials": {}})
    assert context["levels"] == [level.model_dump(mode="json") for level in resolved.levels]
    assert document.model_dump(mode="json") == before


@pytest.mark.parametrize("levels", [
    [{"floor": 1, "level": 0}, {"floor": 2, "level": -1}],
    [{"floor": 1, "level": 0.45}, {"floor": 1, "level": 0.7}],
    [{"floor": 1, "level": float("nan")}],
])
def test_conflicting_or_invalid_floor_elevations_are_reported_before_approval(levels):
    state, _ = state_with_stair()
    raw = deepcopy(state["design_document"])
    raw["decisions"]["floor_layouts"] = levels
    from app.design.contracts import DesignDocument
    with pytest.raises(ValueError, match="floor_layouts"):
        DesignDocument.model_validate(raw)


@pytest.mark.parametrize("axis,scale", [(0, 1), (2, 2), (0, 0.5)])
@pytest.mark.parametrize("field", ["stepDepth", "stepHeight"])
def test_explicit_treads_and_risers_match_the_entire_flight(axis, scale, field):
    start, end = [0, 0, 0], [0, 1.8*scale, 0]
    end[axis] = 2.34*scale
    stair = {"type": "stair", "id": "flight", "from": start, "to": end, "width": 1.1*scale,
             "stepCount": 9, "stepDepth": 0.26*scale, "stepHeight": 0.2*scale}
    bp = {"geometry": {"elements": [stair]}}
    assert not any(i["code"] == "stair_step_span_mismatch" for i in collect_stair_placement_issues(bp))
    stair[field] *= 0.5
    issues = [i for i in collect_stair_placement_issues(bp) if i["code"] == "stair_step_span_mismatch"]
    assert len(issues) == 1 and field in issues[0]["message"]
    assert issues[0]["entity_ids"] == ("flight",)


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


@pytest.mark.parametrize("axis,offset", [(0, 0), (0, -20), (2, 15)])
@pytest.mark.parametrize("platform_type", ["floor", "primitive"])
@pytest.mark.parametrize("thickness", [0.15, 0.6])
def test_return_flights_connect_through_a_full_width_landing(axis, offset, platform_type, thickness):
    state, _ = state_with_stair()
    base = impl.implementation_blueprint(state)
    base["geometry"]["elements"] = [e for e in base["geometry"]["elements"] if e["type"] != "stair"]
    points = [[2, 0, 4], [7, 1.6, 4], [7, 1.6, 5.4], [2, 3.2, 5.4]]
    first = {"type": "stair", "id": "run_a", "from": points[0], "to": points[1], "width": 1.2}
    second = {"type": "stair", "id": "run_b", "from": points[2], "to": points[3], "width": 1.2}
    platform = ({"type": "floor", "id": "landing", "from": [7, 1.6-thickness, 3.4],
                 "to": [8.5, 1.6-thickness, 6], "thickness": thickness} if platform_type == "floor" else
                {"type": "primitive", "id": "landing", "shape": "box",
                 "position": [7.75, 1.6-thickness/2, 4.7], "dimensions": [1.5, thickness, 2.6]})
    entities = base["geometry"]["elements"] + [first, second, platform]
    for entity in entities:
        for key in ("from", "to", "position"):
            if key in entity:
                x, y, z = entity[key]
                entity[key] = [x+offset, y, z+offset] if axis == 0 else [z+offset, y, x+offset]
        if axis == 2 and "dimensions" in entity:
            entity["dimensions"][0], entity["dimensions"][2] = entity["dimensions"][2], entity["dimensions"][0]
    base["geometry"]["elements"] = entities
    cut_stair_openings(base)
    assert collect_stair_placement_issues(base) == []
    assert "不匹配任何参考高度" not in validate_stair_alignment.func(base)
    assert "悬空" not in validate_collision.func(base)
    if thickness == 0.6:
        first["to"][1] -= thickness
        second["from"][1] -= thickness
        assert collect_stair_placement_issues(base)  # 平台底不是承托面。
        first["to"][1] += thickness
        second["from"][1] += thickness
    base["geometry"]["elements"].remove(platform)
    issues = collect_stair_placement_issues(base)
    unsupported = [i for i in issues if i["code"] in {"stair_start_outside_floor", "stair_end_outside_floor"}]
    assert len(unsupported) == 2
    assert all("1.6m" in i["message"] and "平台实体" in i["message"]
               and "完整梯宽" in i["message"] and "不能只移动 X/Z" in i["message"] for i in unsupported)
    assert all("端点=" in i["message"] and "承托范围=" in i["message"] for i in unsupported)


def test_failed_stair_keeps_its_support_and_decoration_in_the_same_revision():
    state, stair = state_with_stair(axis=2)
    base = impl.implementation_blueprint(state)
    base["geometry"]["elements"] = [e for e in base["geometry"]["elements"] if e["type"] != "stair"]
    stair["to"][2] = 11
    finish = {"type": "primitive", "id": "stairs_finish", "shape": "box",
              "position": [5, 1, 5], "dimensions": [1, 0.02, 1]}
    row = {"geometry": {"elements": [stair, finish], "components": []}}
    candidate, accepted, rejected, record = impl._accept_fragment(base, row, {"type": "stair", "design": {}})
    assert candidate == base and accepted is None and record is None
    assert rejected["row"]["geometry"] == row["geometry"]


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
    task_id = next(i["id"] for i in state["plan"]["items"] if i["kind"] == "stair")
    failed_row = {"id": "stairs", "geometry": {"elements": [{"type": "stair", "id": "wrong_flight",
        "from": [5, 0, 5], "to": [5, 3.2, 11], "width": 1.2}], "components": []}}
    state["component_diagnostics"][task_id]["failed_implementations"] = {"stairs": deepcopy(failed_row)}
    state["component_diagnostics"][task_id]["failures"] = {"stairs": "终点没有承托"}
    result = run(compile_node(state))
    body_task = next(i for i in result["plan"]["items"] if i["kind"] == "building_body")
    stair_task = next(i for i in result["plan"]["items"] if i["kind"] == "stair")
    assert body_task["status"] == "done"
    assert "assembly_feedback" not in body_task["params"]
    assert result["component_fragments"][body_task["id"]] == state["component_fragments"][body_task["id"]]
    if exhausted:
        assert result["compile_report"]["ok"] is False
        assert not result["compile_report"].get("retry_implementation")
        assert implementation_records(result)["stairs"]["reason"] == "楼梯实现失败"
    else:
        assert result["compile_report"]["retry_implementation"]
        assert stair_task["params"]["retry_marker_ids"] == ["stairs"]
        assert result["component_diagnostics"][task_id]["failed_implementations"]["stairs"] == failed_row


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
    assert updates["component_diagnostics"][item.id]["failed_implementations"] == {}
    for key in ("component_fragments", "component_diagnostics"):
        state[key].update(updates[key])
    assert run(compile_node(state))["compile_report"]["ok"]


def test_assembly_retry_receives_last_failed_stair_geometry_and_local_reason(monkeypatch):
    import json
    from types import SimpleNamespace
    import app.llm.client as client
    import app.llm.invocation as invocation
    from app.agent.plan.contracts import PlanDocument
    state, stair = state_with_stair(axis=2)
    item = next(i for i in PlanDocument.model_validate(state["plan"]).items if i.kind == "stair")
    state["component_fragments"][item.id] = []
    failed = deepcopy(stair)
    failed["to"][2] = 11
    row = {"id": "stairs", "geometry": {"elements": [failed], "components": []}}
    state["component_diagnostics"][item.id] = {"references": "已检索的楼梯示例", "trace": [],
        "implementations": {}, "failed_implementations": {"stairs": row}, "failures": {"stairs": "终点没有承托"}}
    item.params.update(assembly_feedback="没有 stair 构件", retry_marker_ids=["stairs"])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return SimpleNamespace(content=json.dumps({"implementations": [{"id": "stairs",
            "geometry": {"elements": [stair], "components": []}}]}), token_usage={})
    monkeypatch.setattr(client, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, _, _, _ = run(impl.run_marker_generate(state, item))
    assert status == "succeeded" and len(contexts) == 1
    assert contexts[0]["failed_implementations"]["stairs"] == row
    assert "终点没有承托" in contexts[0]["validation_feedback"]["stairs"]
    assert "没有 stair" in contexts[0]["validation_feedback"]["stairs"]
    assert implementation_records(updates)["stairs"]["status"] == "implemented"


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

