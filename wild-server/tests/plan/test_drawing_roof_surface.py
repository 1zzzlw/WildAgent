"""组合屋顶必须形成屋面；窗框不能变成遮满玻璃的实心板。"""
from math import cos, sin, tan
import json
from types import SimpleNamespace

import pytest

from app.agent.plan import implementation as impl
from app.design.relations import opening_design_errors
from app.utils.json_extractor import extract_json_object
from tests.plan.test_drawing_implementation import empty_state
from tests.plan.test_drawing_opening_placement import base_and_marker, installed_window


def roof_case(offset=0):
    base = empty_state()["skeleton_blueprint"]
    marker = {"id": "designed_roof", "type": "roof", "host": "wing",
              "entity": {"position": [offset+2.5, 3.2, 3]},
              "design": {"type": "单坡屋顶", "overhang": 0,
                         "volume": {"x": offset, "z": 0, "width": 5, "depth": 6}}}
    return base, marker


def roof_box(entity_id, position, dimensions, **extra):
    return {"type": "primitive", "id": entity_id, "shape": "box",
            "position": position, "dimensions": dimensions, **extra}


@pytest.mark.parametrize("offset", [-20, 0, 18])
def test_roof_edge_blocks_do_not_prove_a_roof_surface(offset):
    base, marker = roof_case(offset)
    strips = [roof_box("front", [offset+2.5, 3.3, 0.25], [5, 0.2, 0.5]),
              roof_box("back", [offset+2.5, 3.3, 5.75], [5, 0.2, 0.5])]
    row = {"geometry": {"elements": strips}}
    with pytest.raises(ValueError, match="屋面.*覆盖"):
        impl._accept_group(base, row, marker)
    candidate, accepted, rejected, record = impl._accept_fragment(base, row, marker)
    assert candidate == base and accepted is None and record is None
    assert rejected["row"]["geometry"]["elements"] == strips


def test_adjacent_roof_slabs_cover_the_whole_volume_but_overlaps_cannot_hide_a_gap():
    base, marker = roof_case()
    strips = [roof_box("left", [1.25, 3.3, 3], [2.5, 0.2, 6]),
              roof_box("right", [3.75, 3.3, 3], [2.5, 0.2, 6])]
    _, _, record = impl._accept_group(base, {"geometry": {"elements": strips}}, marker)
    assert record["entity_ids"] == ["left", "right"]
    strips[1]["position"][0] = 1.25
    with pytest.raises(ValueError, match="屋面.*覆盖"):
        impl._accept_group(base, {"geometry": {"elements": strips}}, marker)


@pytest.mark.parametrize("axis", [0, 2])
def test_rotated_box_uses_its_roof_face_projection(axis):
    base, marker = roof_case()
    angle, thickness = 0.0872664626, 0.16
    span = 6 if axis == 0 else 5
    rotation = [0, 0, 0]
    rotation[axis] = angle
    dimensions = [5, thickness, 6]
    dimensions[2-axis] = span/cos(angle)
    position = [2.5, 3.2+span*tan(angle)/2+thickness/2*cos(angle), 3]
    position[2-axis] += (-1 if axis == 0 else 1)*thickness/2*sin(angle)
    slab = roof_box("sloped", position, dimensions, rotation=rotation)
    impl._accept_group(base, {"geometry": {"elements": [slab]}}, marker)
    slab["dimensions"][2-axis] = span*0.8
    with pytest.raises(ValueError, match="屋面.*覆盖"):
        impl._accept_group(base, {"geometry": {"elements": [slab]}}, marker)


def test_a_ground_floor_cannot_be_counted_as_roof_coverage():
    base, marker = roof_case()
    ground = {"type": "floor", "id": "ground", "from": [0, -0.18, 0],
              "to": [5, -0.18, 6], "thickness": 0.18}
    with pytest.raises(ValueError, match="屋面.*覆盖"):
        impl._accept_group(base, {"geometry": {"elements": [ground]}}, marker)


def test_native_roof_must_include_the_declared_eaves():
    base, marker = roof_case()
    marker["design"]["overhang"] = 0.6
    roof = {"type": "roof", "id": "native", "roofType": "flat", "position": [2.5, 3.2, 3],
            "span": 5, "depth": 6, "height": 0.1, "thickness": 0.2}
    with pytest.raises(ValueError, match="屋面.*覆盖"):
        impl._accept_group(base, {"geometry": {"elements": [roof]}}, marker)
    roof.update(span=6.2, depth=7.2)
    impl._accept_group(base, {"geometry": {"elements": [roof]}}, marker)


def test_opaque_full_window_frame_is_rejected_but_bars_and_glass_are_allowed():
    base, marker = base_and_marker()
    window = installed_window()
    panel = roof_box("solid_frame", [3.2, 5, -0.16], [2.6, 2, 0.04], material="wood")
    base["materials"]["wood"] = {"baseColor": [0.2, 0.1, 0.1]}
    with pytest.raises(ValueError, match="实心板"):
        impl._accept_group(base, {"geometry": {"elements": [panel], "components": [window]}}, marker)
    panel["dimensions"][0] = 0.04
    impl._accept_group(base, {"geometry": {"elements": [panel], "components": [window]}}, marker)
    panel["dimensions"][0] = 2.6
    base["materials"]["wood"]["transmission"] = 0.92
    assert not opening_design_errors(base, [window, panel], marker)


def test_json_extraction_can_require_the_implementation_envelope():
    text = '分析示例：```json\n{"id":"part","geometry":{}}\n```\n结果：```json\n{"implementations":[{"id":"marker"}]}\n```'
    assert extract_json_object(text)["id"] == "part"
    assert extract_json_object(text, required_key="implementations")["implementations"] == [{"id": "marker"}]
    assert extract_json_object('{"id":"part"}', required_key="implementations") is None


@pytest.mark.parametrize("origin,direction", [(10, 1), (-30, 1), (15, -1)])
def test_explicit_offset_is_local_to_translated_or_reversed_wall(origin, direction):
    from app.design.coordinates import opening_coordinate_errors
    _, marker = base_and_marker()
    marker["design_path"] = "/decisions/components/0"
    marker["diagram_host"] = {"id": "host", "type": "wall", "from": [origin, 3.2, 0],
                              "to": [origin+direction*5, 6.4, 0]}
    assert not opening_coordinate_errors([marker])
    marker["entity"]["from"][0] = 13.2
    errors = opening_coordinate_errors([marker])
    assert len(errors) == 1 and "/placement" in errors[0] and "局部距离" in errors[0]


def test_model_example_before_final_json_does_not_trigger_a_format_retry(monkeypatch):
    from tests.plan.test_drawing_implementation import patch_services, reply, run, task
    state = empty_state()
    correct = reply("lattice")
    correct.content = '```json\n{"id":"analysis_part","geometry":{}}\n```\n' + correct.content
    events = patch_services(monkeypatch, [correct])
    _, status, _, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and events == ["rag", "model"]
    attempts = [a for a in trace if a.get("tool") == "generate_wild"]
    assert len(attempts) == 1 and attempts[0]["errors"] == {}


def test_roof_surface_failure_repairs_the_whole_current_roof_group(monkeypatch):
    from tests.plan.test_drawing_implementation import patch_services, reply, run, task
    from app.design.markers import implementation_records
    base, marker = roof_case()
    marker["depends_on"] = []
    state = empty_state()
    state["skeleton_blueprint"] = base
    state["resolved_design"]["component_markers"] = [marker]
    strips = [roof_box("front", [2.5, 3.3, 0.25], [5, 0.2, 0.5]),
              roof_box("back", [2.5, 3.3, 5.75], [5, 0.2, 0.5])]
    full = roof_box("surface", [2.5, 3.3, 3], [5, 0.2, 6])
    events = patch_services(monkeypatch, [reply(marker["id"], strips), reply(marker["id"], [full])])
    updates, status, _, _, trace = run(impl.run_marker_generate(state, task(state, marker["id"])))
    assert status == "succeeded" and events == ["rag", "model", "model"]
    record = implementation_records(updates)[marker["id"]]
    assert record["entity_ids"] == ["surface"]
    assert record["attempted_stages"] == ["generate", "repair_1"]
    attempt = next(a for a in trace if a.get("stage") == "generate")
    assert "屋面" in attempt["errors"][marker["id"]]


def test_mixed_flat_and_shed_roof_task_retrieves_the_specific_shed_example(monkeypatch):
    from copy import deepcopy
    import app.agent.plan.knowledge_tool as knowledge
    from tests.plan.test_drawing_implementation import patch_services, run, task
    base, marker = roof_case()
    marker["depends_on"] = []
    second = deepcopy(marker)
    second["id"] = "flat_roof"
    second["design"]["type"] = "平屋顶"
    second["design"]["volume"]["x"] = 8
    second["entity"]["position"][0] = 10.5
    state = empty_state()
    state["skeleton_blueprint"] = base
    state["resolved_design"]["component_markers"] = [marker, second]
    output = {"implementations": [{"id": m["id"], "geometry": {"elements": [
        roof_box(m["id"], [m["entity"]["position"][0], 3.3, 3], [5, 0.2, 6])]}}
        for m in (marker, second)]}
    patch_services(monkeypatch, [SimpleNamespace(content=json.dumps(output), token_usage={})])
    kinds = []
    def search(query, *, kind):
        kinds.append(kind)
        return {"text": "单坡连续薄板示例", "has_shape_reference": True}
    monkeypatch.setattr(knowledge, "search_knowledge_result", search)
    _, status, _, _, _ = run(impl.run_marker_generate(state, task(state, marker["id"])))
    assert status == "succeeded" and kinds == ["单坡屋顶"]


def test_final_gate_rechecks_roof_surface_even_if_old_record_says_implemented(monkeypatch):
    from app.agent.validation.candidate import evaluate_candidate
    from app.agent.validation.diagnostics import blueprint_fingerprint
    import app.services.agent_service as service
    from app.design.resolver import _stable_hash
    from tests.plan.test_drawing_implementation import drawing
    document = drawing()
    base = empty_state(document)["skeleton_blueprint"]
    strip = roof_box("edge", [5, 3.2, 0], [10, 0.2, 0.5])
    base["geometry"]["elements"] = [strip]
    brief = {"implementation": {"design_hash": _stable_hash(document), "records": {
        "roof_main": {"status": "implemented", "entity_ids": ["edge"],
                      "entity_fingerprint": blueprint_fingerprint([strip])}}}}
    monkeypatch.setattr(service, "run_validation_pipeline", lambda *a, **kw: [])
    result = evaluate_candidate(base, design_document=document.model_dump(mode="json"), design_brief=brief)
    roof_errors = [r for r in result["results"] if r.name == "design_roof_surface"]
    assert len(roof_errors) == 1 and roof_errors[0].has_error


@pytest.mark.asyncio
async def test_drawing_revises_local_coordinate_conflict_before_plan(monkeypatch):
    from app.agent.generation.architecture import design_workflow
    from app.agent.generation.architecture.workflow import architecture_planner
    from app.agent.prompts.planning import build_architecture_plan_prompt
    raw = extract_json_object(build_architecture_plan_prompt(""))
    volume = raw["volumes"][0]
    raw["components"] = [{"id": "side_window", "type": "window", "host": volume["id"],
                          "placement": {"face": "front", "floor": 1, "offset": volume["width"]+5, "sill_height": 1},
                          "size": {"width": 1, "height": 1}}]
    calls = []
    async def model(_llm, messages):
        calls.append(messages)
        if len(calls) == 2:
            raw["components"][0]["placement"]["offset"] = 1
        return SimpleNamespace(content=json.dumps(raw), token_usage=None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kw: None)
    result = await architecture_planner({"user_message": "生成别墅", "session_id": "local_coords"})
    assert not result.get("error"), result
    assert len(calls) == 2 and "局部距离" in calls[1][0]["content"]
