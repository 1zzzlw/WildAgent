"""设计事实、局部产物与失败状态应跨生成边界保留。"""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.agent.plan import implementation as impl
from app.design.markers import implementation_records
from app.design.relations import coalesce_body_walls
from app.services.agent_delivery import retain_generation_blueprint
from tests.plan.test_drawing_fragment_retries import column, slab
from tests.plan.test_drawing_implementation import drawing, empty_state, patch_services, reply, run, task


@pytest.mark.parametrize("origin", [(0, 0), (-17, 23)])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("floor_y,height", [(0, 3), (4.2, 2.7)])
def test_projected_interior_wall_height_is_reused_without_an_opening(origin, reverse, floor_y, height):
    document = drawing()
    document.decisions.massing.floor_height = height
    x, z = origin
    volume = document.decisions.volumes[0]
    volume.x, volume.z = x, z
    a, b = [x + 2, z + 1], [x + 2, z + 6]
    if reverse:
        a, b = b, a
    document.decisions.floor_layouts = [{"floor": 1, "level": floor_y, "rooms": [],
        "walls": [{"id": "partition", "from": a, "to": b, "thickness": 0.15}]}]
    state = empty_state(document)
    marker = state["resolved_design"]["component_markers"][0]
    context = impl._item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    expected = next(w for w in state["drawing_hosts"] if w["id"] == "partition")
    assert expected in context["diagram_hosts"]
    wall = {"id": "partition", "type": "wall", "from": [a[0], floor_y, a[1]],
            "to": [b[0], floor_y, b[1]], "thickness": 0.15}
    row = {"geometry": {"elements": [wall], "components": []}}
    before = deepcopy(row)
    placed, changes = coalesce_body_walls(state["skeleton_blueprint"], row,
        state["resolved_design"]["component_markers"], diagram_hosts=state["drawing_hosts"])
    assert placed["geometry"]["elements"][0]["from"] == expected["from"]
    assert placed["geometry"]["elements"][0]["to"] == expected["to"]
    assert changes[0]["rule"] == "compiler.interior_wall_levels"
    assert row == before


def test_projection_does_not_relocate_a_different_wall_or_replace_a_nonzero_height():
    host = {"id": "partition", "type": "wall", "from": [1, 0, 0], "to": [1, 3, 5],
            "design_path": "/decisions/floor_layouts/0/walls/0"}
    for wall in [
        {"id": "partition", "type": "wall", "from": [2, 0, 0], "to": [2, 0, 5], "thickness": 0.2},
        {"id": "partition", "type": "wall", "from": [1, 0, 0], "to": [1, 2, 5], "thickness": 0.2},
    ]:
        row = {"geometry": {"elements": [wall], "components": []}}
        actual, changes = coalesce_body_walls({"geometry": {"elements": [], "components": []}}, row, [],
                                             diagram_hosts=[host])
        assert actual == row and changes == []


def test_failed_group_retains_passed_geometry_without_claiming_completion(monkeypatch):
    state = empty_state()
    stable, bad = column(), slab(valid=False)
    patch_services(monkeypatch, [reply("building_body", [stable, bad])] * 3)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "aborted" and ids == []
    assert implementation_records(updates)["building_body"]["status"] == "abandoned"
    assert updates["component_fragments"]["generate_1"] == []
    draft = retain_generation_blueprint({**state, **updates})
    assert draft["geometry"]["elements"] == [stable, bad]
    partial = updates["component_diagnostics"]["generate_1"]["partial_implementations"]
    assert partial["building_body"]["geometry"]["elements"] == [stable]


def test_empty_open_body_feedback_identifies_the_undelegated_floor(monkeypatch):
    import json
    import app.llm.invocation as invocation

    state = empty_state()
    before = deepcopy(state["design_document"])
    patch_services(monkeypatch, [])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return reply("building_body", [] if len(contexts) == 1 else [slab()])
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and ids == ["slab"]
    feedback = contexts[1]["validation_feedback"]["building_body"]
    assert "未另派 floor" in feedback and "楼面顶减板厚" in feedback
    assert state["design_document"] == before


def test_component_catalog_exposes_applicability_and_keeps_generic_roofs_out_of_round_system():
    from app.agent.knowledge.component_names import component_reference_prompt, resolve_component_name

    assert resolve_component_name("圆形攒尖顶")["kind"] == "cone_roof_system"
    assert resolve_component_name("攒尖顶")["kind"] != "cone_roof_system"
    prompt = component_reference_prompt({"cone_roof_system"})
    assert "适用" in prompt and "圆形攒尖顶" in prompt


@pytest.mark.parametrize("host", ["", "main"])
def test_independent_task_ownership_reaches_the_roof_even_without_a_shared_host(host):
    state = empty_state()
    markers = state["resolved_design"]["component_markers"]
    roof = next(m for m in markers if m["type"] == "roof")
    markers.append({"id": "top_decoration", "type": "roof_finial", "host": host,
                    "design": {"size": {"height": 0.3}}})
    before = deepcopy(markers)
    context = impl._item_context(state, {roof["id"]: roof}, state["skeleton_blueprint"])
    assert {"id": "top_decoration", "type": "roof_finial", "host": host} in context["other_task_markers"]
    assert not any(m["id"] == roof["id"] for m in context["other_task_markers"])
    assert state["resolved_design"]["component_markers"] == before


@pytest.mark.parametrize("change", [{"height": 4}, {"material": "other"}])
def test_failed_revision_cannot_replace_or_duplicate_a_passed_draft_entity(change):
    state = empty_state()
    stable = column()
    state["component_diagnostics"] = {"generate_1": {
        "partial_implementations": {"building_body": {"geometry": {"elements": [stable], "components": []}}},
        "failed_implementations": {"building_body": {"geometry": {
            "elements": [{**stable, **change}, slab(valid=False)], "components": []}}},
    }}
    draft = retain_generation_blueprint(state)
    assert draft["geometry"]["elements"] == [stable, slab(valid=False)]
    assert state["component_diagnostics"]["generate_1"]["failed_implementations"]["building_body"][
        "geometry"]["elements"][0] == {**stable, **change}


def test_resumed_local_repair_reuses_passed_geometry(monkeypatch):
    state = empty_state()
    stable, bad = column(), slab(valid=False)
    patch_services(monkeypatch, [reply("building_body", [stable, bad])] * 3)
    first, *_ = run(impl.run_marker_generate(state, task(state, "building_body")))
    state.update(first)
    item = task(state, "building_body")
    item.params["assembly_feedback"] = "修订未通过的楼板"
    patch_services(monkeypatch, [reply("building_body", [slab()])])
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, item))
    assert status == "succeeded" and set(ids) == {stable["id"], "slab"}
    assert updates["component_fragments"][item.id].count(stable) == 1
    assert not updates["component_diagnostics"][item.id]["partial_implementations"]


def test_compile_does_not_replace_unexecuted_tasks_with_whole_building_repair(monkeypatch):
    from app.agent.design_flow.compile import compile_node
    import app.llm.invocation as invocation

    state = empty_state()
    stable, bad = column(), slab(valid=False)
    patch_services(monkeypatch, [reply("building_body", [stable, bad])] * 3)
    updates, *_ = run(impl.run_marker_generate(state, task(state, "building_body")))
    model = AsyncMock(side_effect=AssertionError("未完成任务应保留诊断，不集中重建整栋建筑"))
    monkeypatch.setattr(invocation, "invoke_llm", model)
    result = run(compile_node({**state, **updates}))
    model.assert_not_awaited()
    assert result["status"] == "failed"
    assert result["compile_report"]["repair"]["stop_reason"] == "implementation_incomplete"
    assert {e["id"] for e in result["merged_blueprint"]["geometry"]["elements"]} == {stable["id"], bad["id"]}


@pytest.mark.parametrize("roof_type", ["chinese_curved", "custom_curved_hip"])
def test_roof_retrieval_includes_selected_shape_even_without_a_catalog_alias(monkeypatch, roof_type):
    import app.agent.plan.knowledge_tool as knowledge

    document = drawing()
    document.decisions.roof.type = roof_type
    state = empty_state(document)
    patch_services(monkeypatch, [])
    queries = []
    def retrieve(query, **kwargs):
        queries.append((query, kwargs))
        return {"text": "字段协议", "has_shape_reference": True}
    monkeypatch.setattr(knowledge, "search_knowledge_result", retrieve)
    run(impl.run_marker_generate(state, task(state, "roof_main")))
    assert len(queries) == 1 and roof_type in queries[0][0]
    assert queries[0][1]["kind"] == "roof"


def test_local_compile_repair_receives_actual_entity_protocol(monkeypatch):
    from types import SimpleNamespace
    import app.agent.design_flow.compile as compiler
    import app.agent.validation.candidate as candidate
    import app.llm.invocation as invocation

    state = empty_state()
    blueprint = deepcopy(state["skeleton_blueprint"])
    blueprint["geometry"]["elements"] = [slab()]
    patch_services(monkeypatch, [])
    monkeypatch.setattr(compiler, "_assemble_with_relations", lambda *args: (blueprint, [], {}))
    monkeypatch.setattr(candidate, "evaluate_candidate", lambda *args, **kwargs:
                        {"errors": [SimpleNamespace(output="字段需要修订")], "issues": []})
    messages = []
    async def capture(_llm, prompt, **kwargs):
        messages.extend(prompt)
        raise RuntimeError("仅检查实际修复输入")
    monkeypatch.setattr(invocation, "invoke_llm", capture)
    run(compiler.compile_node({**state, "thinking_mode": False}))
    assert "当前输出字段协议" in messages[0]["content"]
    assert '"thickness"' in messages[0]["content"] and "floor:elements" in messages[0]["content"]


def test_abandoned_markers_cannot_be_reported_as_complete_when_geometry_passes(monkeypatch):
    import app.agent.design_flow.compile as compiler
    import app.agent.validation.candidate as candidate

    state = empty_state()
    blueprint = deepcopy(state["skeleton_blueprint"])
    blueprint["geometry"]["elements"] = [slab()]
    records = {"building_body": {"status": "implemented", "entity_ids": ["slab"]},
               "furniture": {"status": "abandoned", "entity_ids": [], "reason": "尺寸错误"}}
    monkeypatch.setattr(compiler, "_assemble_with_relations", lambda *args: (blueprint, [], records))
    monkeypatch.setattr(candidate, "evaluate_candidate", lambda *args, **kwargs: {"errors": [], "issues": []})
    result = run(compiler.compile_node(state))
    assert result["status"] == "failed" and "furniture" in result["error"]
    assert result["compile_report"]["ok"] is False
    assert result["compile_report"]["design_complete"] is False
    assert result["compile_report"]["repair"]["attempted"] is False
    assert result["merged_blueprint"]["geometry"]["elements"] == [slab()]


@pytest.mark.parametrize("base", [0, 3.12, 11])
def test_explicit_roof_center_is_not_mistaken_for_its_support_elevation(base):
    from app.design.relations import roof_design_errors

    marker = {"id": "cover", "type": "roof", "entity": {"position": [2, base+0.5, 2]},
              "design": {"volume": {"x": 0, "z": 0, "width": 4, "depth": 4},
                         "size": {"height": 1}, "placement": {"position": [2, base+0.5, 2]}}}
    roof = {"id": "cover", "type": "roof", "roofType": "hip", "position": [2, base, 2],
            "span": 4, "depth": 4, "height": 1, "thickness": 0.1}
    blueprint = {"geometry": {"elements": [roof], "components": []}}
    assert roof_design_errors(blueprint, [roof], marker) == []
    assert roof_design_errors(blueprint, [{**roof, "position": [2, base-0.1, 2]}], marker)


@pytest.mark.parametrize("origin", [0, -17])
@pytest.mark.parametrize("overhang", [0.3, 0.8])
def test_contradictory_roof_size_is_reported_before_component_generation(origin, overhang):
    from app.design.coordinates import roof_span_conflicts

    marker = {"id": "cover", "type": "roof", "design_path": "/decisions/components/0",
              "design": {"volume": {"x": origin, "z": origin, "width": 5, "depth": 5},
                         "overhang": overhang, "size": {"width": 5, "depth": 5},
                         "placement": {"position": [origin+2.5, 3.5, origin+2.5]}}}
    errors = roof_span_conflicts([marker])
    assert len(errors) == 2 and "/components/0/size/width" in errors[0]
    marker["design"]["size"] = {"width": 5+2*overhang, "depth": 5+2*overhang}
    assert roof_span_conflicts([marker]) == []
    marker["design"]["placement"]["position"][0] += 1
    assert roof_span_conflicts([marker])


@pytest.mark.parametrize("offset", [[0, 0, 0], {"x": 0, "y": 0, "z": 0}, None])
def test_placement_feedback_explains_scalar_offset_and_keeps_the_actual_input(offset):
    from pydantic import ValidationError
    from app.agent.generation.architecture.workflow import _validation_reason
    from app.design.contracts import ArchitectureDecisions

    data = drawing().decisions.model_dump(mode="json")
    data["components"][0]["placement"]["offset"] = offset
    with pytest.raises(ValidationError) as captured:
        ArchitectureDecisions.model_validate(data)
    reason = _validation_reason(captured.value)
    assert "单个有限数字" in reason and repr(offset) in reason
    assert "不是三维向量" in reason and "placement.position" in reason


@pytest.mark.parametrize("materials", [("timber", "stone"), ("深棕木色", "灰石")])
def test_explicit_different_materials_cannot_silently_share_one_role(materials):
    from app.agent.generation.architecture.workflow import _material_role_conflicts

    components = [{"id": str(i), "material_role": "accent", "form": {"material": m}}
                  for i, m in enumerate(materials)]
    before = deepcopy(components)
    errors = _material_role_conflicts(components)
    assert len(errors) == 1 and "/components" in errors[0]
    assert components == before
    components[0]["material_role"] = "structure"
    assert _material_role_conflicts(components) == []
    components[0]["material_role"] = "accent"
    components[1]["form"]["material"] = materials[0]
    assert _material_role_conflicts(components) == []


@pytest.mark.parametrize("origin", [0, -17])
def test_component_context_contains_calculated_world_bounds_and_exact_edge_feedback(origin):
    from app.design.relations import component_geometry_review

    state = empty_state()
    marker = {"id": "assembly", "type": "assembly", "host": "",
              "design": {"size": {"width": 2, "height": 1, "depth": 0.5},
                         "placement": {"position": [origin, 0.8, origin]}}}
    context = impl._item_context(state, {"assembly": marker}, state["skeleton_blueprint"])
    assert context["assembly_bounds"]["assembly"]["min"] == pytest.approx([origin-1, 0.3, origin-0.25])
    assert context["assembly_bounds"]["assembly"]["max"] == pytest.approx([origin+1, 1.3, origin+0.25])
    box = {"type": "primitive", "id": "part", "shape": "box", "position": [origin, 0.8, origin],
           "dimensions": [2.08, 0.94, 0.5]}
    errors = component_geometry_review(state["skeleton_blueprint"], [box], marker)["errors"]
    assert any("[part].position[1]" in error for error in errors)


@pytest.mark.parametrize("axis", [0, 2])
@pytest.mark.parametrize("offset", [-13, 0, 17])
def test_beam_span_is_not_confused_with_its_cross_section(axis, offset):
    from app.design.relations import component_geometry_review

    a, b = [offset, 3.65, offset], [offset, 3.65, offset]
    b[axis] += 3.5
    center = [(p+q)/2 for p, q in zip(a, b)]
    size = {"width": 3.5 if axis == 0 else 0.2, "height": 0.3, "depth": 0.2 if axis == 0 else 3.5}
    marker = {"id": "member", "type": "beam", "design": {"size": size, "placement": {"position": center}}}
    beam = {"id": "member", "type": "beam", "from": a, "to": b, "crossSection": "rect",
            "width": 0.2, "height": 0.3}
    blueprint = {"geometry": {"elements": [beam], "components": []}}
    assert component_geometry_review(blueprint, [beam], marker)["errors"] == []
    beam["width"] = 3.5
    assert component_geometry_review(blueprint, [beam], marker)["errors"]
