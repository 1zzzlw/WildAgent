"""批量输出、跨任务归属和局部修订的共享边界。"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.plan import implementation as impl
from app.agent.plan.expand import expand_design_markers
from app.design.markers import implementation_records
from tests.plan.test_drawing_implementation import empty_state, patch_services, run


@pytest.mark.parametrize("count", [8, 45, 180])
@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed"])
def test_large_batches_keep_every_marker_and_dependency(count, level):
    markers = [{"id": "body", "type": "building_body", "design": {}, "depends_on": []}]
    markers += [{"id": f"window_{i}", "type": "window", "host": f"wall_{i//6}",
                 "depends_on": ["body"], "design": {"description": "窗框与玻璃" * 80}}
                for i in range(count)]
    state = {"resolved_design": {"design_hash": "approved", "component_markers": markers},
             "design_document": {"decisions": {"complexity": {"level": level}}}}
    before = deepcopy(state)
    plan = expand_design_markers(state)
    assert [i for item in plan.items for i in item.target["marker_ids"]] == [m["id"] for m in markers]
    assert all(item.depends_on == [plan.items[0].id] for item in plan.items[1:])
    assert all(item.params["batch_load"]["marker_chars"] <= 8000 for item in plan.items[1:])
    assert state == before


def test_mutually_dependent_markers_are_not_separated_by_input_batching():
    state = empty_state()
    state["resolved_design"]["component_markers"] = [
        {"id": "a", "type": "custom", "depends_on": ["b"], "design": {"description": "x"*9000}},
        {"id": "b", "type": "custom", "depends_on": ["a"], "design": {}}]
    plan = expand_design_markers(state)
    assert len(plan.items) == 1 and plan.items[0].target["marker_ids"] == ["a", "b"]


def test_length_truncation_splits_output_without_repeating_the_large_batch(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    markers = [{"id": f"detail_{i}", "type": "custom_detail", "host": "", "depends_on": [],
                "design": {}, "entity": {}} for i in range(7)]
    state["resolved_design"]["component_markers"] = markers
    item = expand_design_markers(state).items[0]
    patch_services(monkeypatch, [])
    sizes = []

    async def model(_llm, messages):
        selected = json.loads(messages[1]["content"])["markers"]
        sizes.append(len(selected))
        if len(selected) > 2:
            return SimpleNamespace(content='{"implementations":[', token_usage={"output": 64}, finish_reason="length")
        rows = [{"id": m["id"], "geometry": {"elements": [{"type": "primitive", "id": m["id"],
                 "shape": "box", "position": [int(m["id"].split('_')[-1])*3, 0, 0],
                 "dimensions": [1, 1, 1]}], "components": []}} for m in selected]
        return SimpleNamespace(content=json.dumps({"implementations": rows}), token_usage={}, finish_reason="stop")

    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, *_ = run(impl.run_marker_generate(state, item))
    assert status == "succeeded"
    assert sizes.count(7) == 1
    assert all(r["status"] == "implemented" for r in implementation_records(updates).values())
    assert len(implementation_records(updates)) == 7
    attempts = [t for t in updates["component_diagnostics"][item.id]["trace"] if t.get("stage")]
    assert len(attempts) < 4*len(markers)
    assert all(t["stage"] == "generate" for t in attempts)
    assert any(t.get("split_marker_ids") for t in attempts)


@pytest.mark.parametrize("echo", [False, True])
def test_repair_validates_retained_and_new_geometry_as_one_component(echo):
    base = empty_state()["skeleton_blueprint"]
    retained = {"type": "primitive", "id": "detail_left", "shape": "box",
                "position": [0.5, 0.5, 0.5], "dimensions": [1, 1, 1]}
    fresh = {**retained, "id": "detail_right", "position": [2.5, 0.5, 0.5], "dimensions": [3, 1, 1]}
    base["geometry"]["elements"] = [retained]
    marker = {"id": "detail", "type": "custom_detail", "entity": {},
              "design": {"size": {"width": 4, "height": 1, "depth": 1},
                         "placement": {"position": [2, 0.5, 0.5]}}}
    before = deepcopy(base)
    result, accepted, rejected, record = impl._accept_fragment(base,
        {"geometry": {"elements": ([retained] if echo else [])+[fresh], "components": []}},
        marker, {"elements": [retained], "components": []})
    assert rejected is None and record["status"] == "implemented"
    assert accepted["geometry"]["elements"] == [fresh]
    assert result["geometry"]["elements"] == [retained, fresh]
    assert base == before
    fresh["dimensions"][0] = 2
    assert impl._accept_fragment(base, {"geometry": {"elements": [fresh]}}, marker,
        {"elements": [retained], "components": []})[2] is not None


def test_roof_receives_sibling_ownership_and_rejects_delegated_parapet():
    state = empty_state()
    roof = {"id": "roof", "type": "roof", "host": "main", "entity": {"position": [5, 3, 4]},
            "design": {"type": "flat", "overhang": 0, "volume": {"x": 0, "z": 0, "width": 10, "depth": 8}}}
    parapet = {"id": "edge", "type": "parapet", "host": "main", "design": {"size": {"height": 1}}}
    state["resolved_design"]["component_markers"] = [roof, parapet]
    base = state["skeleton_blueprint"]
    context = impl._item_context(state, {"roof": roof}, base)
    assert any(m["id"] == "edge" for m in context["delegated_markers"])
    slab = {"type": "floor", "id": "roof_slab", "from": [0, 2.8, 0], "to": [10, 2.8, 8], "thickness": 0.2}
    wall = {"type": "wall", "id": "arbitrary_name", "from": [0, 3, 0], "to": [10, 4, 0], "thickness": 0.2}
    _, accepted, rejected, _ = impl._accept_fragment(base, {"geometry": {"elements": [slab, wall]}},
        roof, dependent_markers=[roof, parapet])
    assert accepted is None and "edge" in rejected["error"]
    assert impl._accept_fragment(base, {"geometry": {"elements": [slab]}}, roof,
        dependent_markers=[roof, parapet])[2] is None


def test_output_split_survives_interruption_without_regenerating_adopted_markers(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    state["resolved_design"]["component_markers"] = [
        {"id": f"detail_{i}", "type": "custom_detail", "host": "", "depends_on": [], "design": {}, "entity": {}}
        for i in range(4)]
    item = expand_design_markers(state).items[0]
    patch_services(monkeypatch, [])
    requests = []

    async def model(_llm, messages):
        markers = json.loads(messages[1]["content"])["markers"]
        requests.append([m["id"] for m in markers])
        if len(requests) == 3:
            raise RuntimeError("connection interrupted")
        if len(markers) > 2:
            return SimpleNamespace(content='{"implementations":[', token_usage={}, finish_reason="length")
        return SimpleNamespace(content=json.dumps({"implementations": [
            {"id": m["id"], "geometry": {"elements": [{"id": m["id"], "type": "primitive", "shape": "box",
             "position": [int(m["id"][-1])*3, 0, 0], "dimensions": [1, 1, 1]}]}} for m in markers]}),
            token_usage={}, finish_reason="stop")

    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, *_ = run(impl.run_marker_generate(state, item))
    assert status == "aborted"
    state.update(updates)
    updates, status, *_ = run(impl.run_marker_generate(state, item))
    assert status == "succeeded"
    assert requests == [["detail_0", "detail_1", "detail_2", "detail_3"],
                        ["detail_0", "detail_1"], ["detail_2", "detail_3"], ["detail_2", "detail_3"]]
    assert len(updates["component_fragments"][item.id]) == 4


@pytest.mark.parametrize("roof_type,host,wall_base,expected", [
    ("flat", "main", 3, True), ("flat", "other", 3, False),
    ("flat", "main", 0, False), ("gable", "main", 3, False)])
def test_delegated_roof_wall_check_preserves_supports_and_other_hosts(roof_type, host, wall_base, expected):
    from app.design.relations import delegated_geometry_errors
    roof = {"id": "roof", "type": "roof", "host": "main", "entity": {"position": [5, 3, 4]},
            "design": {"type": roof_type}}
    wall = {"id": "wall", "type": "wall", "from": [0, wall_base, 0], "to": [10, 4, 0]}
    sibling = {"id": "edge", "type": "parapet", "host": host}
    assert bool(delegated_geometry_errors([wall], roof, [sibling])) == expected


def test_split_generation_stays_inside_existing_call_budget(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    state["resolved_design"]["component_markers"] = [
        {"id": f"detail_{i}", "type": "custom_detail", "host": "", "depends_on": [], "design": {}, "entity": {}}
        for i in range(4)]
    item = expand_design_markers(state).items[0]
    patch_services(monkeypatch, [])
    async def model(*args):
        return SimpleNamespace(content='{"implementations":[', token_usage={}, finish_reason="length")
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, *_ = run(impl.run_marker_generate(state, item))
    assert status == "failed"
    state.update(updates)
    item.params["assembly_feedback"] = "重新核对完整设计"
    updates, status, *_ = run(impl.run_marker_generate(state, item))
    trace = updates["component_diagnostics"][item.id]["trace"]
    assert status == "failed" and sum(t.get("model_calls", 0) for t in trace) <= 16
    assert any(t.get("tool") == "implementation_budget_exhausted" for t in trace)


@pytest.mark.parametrize("axis,shift,reverse", [(0, 0, False), (2, -12, False), (0, 18, True)])
@pytest.mark.parametrize("width,height,valid", [(4, 1.8, True), (5, 1.8, False), (4, 3, False)])
def test_automatic_opening_reserves_its_cell_before_any_neighbor_is_generated(axis, shift, reverse, width, height, valid):
    from app.design.relations import opening_cell_limits, opening_design_errors, place_opening_group
    state = empty_state()
    base = state["skeleton_blueprint"]
    a, b = [shift, 3, shift], [shift, 6.6, shift]
    b[axis] += 18
    diagram = {"id": "wall", "type": "wall", "from": a, "to": b, "thickness": 0.2}
    actual = deepcopy(diagram)
    if reverse:
        actual["from"], actual["to"] = [*b], [*a]
        actual["from"][1], actual["to"][1] = 3, 6.6
    base["geometry"]["elements"] = [actual]
    marker = {"id": "opening", "type": "window", "host": "wall", "depends_on": [],
              "design": {"bay": 2, "bays": 4}, "diagram_host": diagram,
              "entity": {"parentWall": "wall", "centerAlong": 6.75, "bottomY": 4}}
    state["resolved_design"]["component_markers"] = [marker]
    limits = opening_cell_limits(marker)
    assert limits["max_width"] == 4.5 and limits["max_height"] == pytest.approx(2.6)
    assert impl._item_context(state, {"opening": marker}, base)["opening_cell_limits"]["opening"] == limits
    row = {"geometry": {"components": [{"id": "part", "type": "window", "parentWall": "wall",
             "from": [0, 0, 0], "width": width, "height": height}]}}
    placed, _ = place_opening_group(base, row, marker)
    issues = opening_design_errors(base, placed["geometry"]["components"], marker)
    assert bool(issues) != valid
    if not valid:
        assert "开间" in " ".join(issues)


def test_explicit_opening_is_not_resized_to_an_automatic_cell():
    from app.design.relations import opening_cell_limits
    marker = {"id": "wide", "type": "window", "design": {"size": {"width": 6}},
              "entity": {"parentWall": "wall", "from": [0, 1, 0]}}
    assert opening_cell_limits(marker) is None
    assert marker["design"]["size"]["width"] == 6
