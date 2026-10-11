"""图纸事实只交接一次：主体、屋顶归属及直墙门窗定位。"""
from copy import deepcopy
import json

import pytest

from app.agent.plan import implementation as impl
from app.agent.plan.expand import expand_design_markers
from app.design import relations
from app.design.compilation import project_drawing
from app.design.contracts import ComponentInstance
from app.design.markers import component_markers, implementation_records
from tests.plan.test_drawing_implementation import drawing, empty_state, patch_services, reply, run, task


def explicit_drawing():
    document = drawing()
    document.decisions.roof.type = "flat"
    document.decisions.roof.overhang = 0.8
    document.decisions.components = [
        ComponentInstance(id="body_main", type="building_body", host="main",
                          description="白墙主体", size={"width": 10, "depth": 8, "height": 3}),
        ComponentInstance(id="roof_main", type="roof", host="main",
                          size={"width": 11.6, "depth": 9.6, "height": 0.2}),
        ComponentInstance(id="entry", type="door", host="wall_main_front_L1",
                          placement={"position": [5, 1.2, 0]}, size={"width": 1.8, "height": 2.4}),
    ]
    return document


def test_explicit_body_is_part_of_the_single_body_task_without_changing_drawing():
    document = explicit_drawing()
    before = document.model_dump(mode="json")
    markers = component_markers(document)
    bodies = [m for m in markers if m["type"] == "building_body"]
    assert len(bodies) == 1
    assert bodies[0]["design"]["body_components"][0]["description"] == "白墙主体"
    state = {"resolved_design": project_drawing(document).model_dump(mode="json"),
             "design_document": before}
    assert len([i for i in expand_design_markers(state).items if i.kind == "building_body"]) == 1
    assert document.model_dump(mode="json") == before


def test_explicit_roof_keeps_volume_overhang_and_support_elevation():
    document = explicit_drawing()
    before = document.model_dump(mode="json")
    roof = next(m for m in component_markers(document) if m["id"] == "roof_main")
    assert roof["design"]["volume"]["id"] == "main"
    assert roof["design"]["overhang"] == 0.8
    assert roof["design"]["roof_type"] == "flat"
    assert roof["entity"]["position"] == [5, 3, 4]
    assert roof["design"]["size"]["width"] == 11.6
    assert document.model_dump(mode="json") == before


@pytest.mark.parametrize("axis,direction", [(0, 1), (0, -1), (2, 1), (2, -1)])
@pytest.mark.parametrize("shift", [-20, 0, 17])
def test_group_placement_uses_drawing_anchor_on_translated_and_reversed_walls(axis, direction, shift):
    base = empty_state()["skeleton_blueprint"]
    a = [shift, 0, shift]
    b = [shift, 3, shift]
    b[axis] += 10*direction
    wall = {"id": "host", "type": "wall", "from": a, "to": b, "thickness": 0.2}
    base["geometry"]["elements"] = [wall]
    marker = {"id": "group", "type": "combination_window", "host": "host",
              "entity": {"parentWall": "host", "centerAlong": 4.5, "bottomY": 1},
              "diagram_host": wall, "design": {}}
    panes = [{"id": f"pane_{i}", "type": "window", "parentWall": "host",
              "from": [4.5+0.8*i, 1.2, 0], "width": 0.8, "height": 1.5} for i in range(3)]
    row = {"geometry": {"components": panes}}
    before = deepcopy(row)
    placed, changes = relations.place_opening_group(base, row, marker)
    actual = placed["geometry"]["components"]
    assert [p["from"][0] for p in actual] == pytest.approx([3.3, 4.1, 4.9])
    assert all(p["from"][1] == 1 for p in actual)
    assert changes and row == before
    assert relations.opening_design_errors(base, actual, marker) == []
    with pytest.raises(ValueError, match="图纸"):
        impl._accept_group(base, before, marker)


def test_center_position_is_converted_to_door_bottom_without_resizing():
    base = empty_state()["skeleton_blueprint"]
    wall = {"type": "wall", "id": "host", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}
    base["geometry"]["elements"] = [wall]
    marker = {"id": "entry", "type": "door", "host": "host", "diagram_host": wall,
              "entity": {"parentWall": "host", "position": [5, 1.2, 0]},
              "design": {"size": {"width": 1.8, "height": 2.4}}}
    door = {"id": "entry", "type": "door", "parentWall": "host", "from": [4.1, 1.2, 0],
            "width": 1.8, "height": 2.4, "interaction": {"mode": "swing"}}
    placed, changes = relations.place_opening_group(base, {"geometry": {"components": [door]}}, marker)
    _, actual, _ = impl._accept_group(base, placed, marker)
    assert actual[0]["from"] == pytest.approx([4.1, 0, 0])
    assert actual[0]["height"] == door["height"] == 2.4
    assert changes and door["from"][1] == 1.2


def test_body_cannot_lock_the_roof_owned_by_a_later_task(monkeypatch):
    document = explicit_drawing()
    state = empty_state()
    state["design_document"] = document.model_dump(mode="json")
    projected = project_drawing(document)
    state["resolved_design"] = projected.model_dump(mode="json")
    state["drawing_hosts"] = projected.projection_elements
    floor = {"id": "ground", "type": "floor", "from": [0, -0.2, 0], "to": [10, -0.2, 8], "thickness": 0.2}
    wall = {**projected.projection_elements[0], "thickness": 0.2}
    wall.pop("facing")
    premature = {"id": "roof_main", "type": "primitive", "shape": "box",
                 "position": [5, 3.1, 4], "dimensions": [10, 0.2, 8]}
    roof = {"id": "roof_main", "type": "roof", "roofType": "flat", "span": 11.6,
            "depth": 9.6, "height": 0.2, "thickness": 0.2, "position": [5, 3, 4]}
    events = patch_services(monkeypatch, [reply("building_body", [floor, wall, premature]), reply("roof_main", [roof])])
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and ids == ["ground", wall["id"]]
    state.update(updates)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "roof_main")))
    assert status == "succeeded" and ids == ["roof_main"]
    assert events == ["rag", "model", "rag", "model"]
    assert implementation_records(updates)["roof_main"]["status"] == "implemented"


def test_executor_places_native_door_in_one_model_call_and_records_derivation(monkeypatch):
    document = explicit_drawing()
    state = empty_state()
    state["design_document"] = document.model_dump(mode="json")
    projected = project_drawing(document)
    state["resolved_design"] = projected.model_dump(mode="json")
    state["drawing_hosts"] = projected.projection_elements
    wall = {**projected.projection_elements[0], "thickness": 0.2}
    wall.pop("facing")
    state["skeleton_blueprint"]["geometry"]["elements"] = [wall]
    door = {"id": "entry", "type": "door", "parentWall": wall["id"], "from": [4.1, 1.2, 0],
            "width": 1.8, "height": 2.4, "interaction": {"mode": "swing"}}
    output = reply("entry", [])
    payload = json.loads(output.content)
    payload["implementations"][0]["geometry"]["components"] = [door]
    output.content = json.dumps(payload)
    events = patch_services(monkeypatch, [output])
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state, "entry")))
    assert status == "succeeded" and events == ["rag", "model"]
    record = implementation_records(updates)["entry"]
    assert record["assembly_changes"][0]["rule"] == "compiler.opening_placement"
    actual = updates["component_fragments"][task(state, "entry").id][0]
    assert actual["from"] == pytest.approx([4.1, 0, 0])
    assert record["attempts"][1]["output"] == output.content


def test_group_decoration_moves_with_the_opening_without_changing_its_form():
    base = empty_state()["skeleton_blueprint"]
    wall = {"id": "host", "type": "wall", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}
    base["geometry"]["elements"] = [wall]
    marker = {"id": "window", "type": "window", "entity": {"parentWall": "host", "centerAlong": 4.5, "bottomY": 1}, "design": {}}
    pane = {"id": "pane", "type": "window", "parentWall": "host", "from": [4.5, 1, 0], "width": 2, "height": 1.5}
    bar = {"id": "bar", "type": "primitive", "shape": "box", "position": [5.5, 1.7, -0.2], "dimensions": [2, 0.04, 0.08]}
    row, changes = relations.place_opening_group(base, {"geometry": {"components": [pane], "elements": [bar]}}, marker)
    assert row["geometry"]["components"][0]["from"] == [3.5, 1, 0]
    assert row["geometry"]["elements"][0]["position"] == [4.5, 1.7, -0.2]
    assert row["geometry"]["elements"][0]["dimensions"] == bar["dimensions"]
    assert {c["entity_id"] for c in changes} == {"pane", "bar"}


def test_placement_converts_back_to_a_reversed_real_wall_segment():
    base = empty_state()["skeleton_blueprint"]
    diagram = {"id": "diagram", "type": "wall", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}
    segment = {**diagram, "id": "part", "from": [6, 0, 0], "to": [1, 3, 0]}
    base["geometry"]["elements"] = [segment]
    marker = {"id": "window", "type": "window", "diagram_host": diagram,
              "entity": {"parentWall": "diagram", "from": [2, 1, 0]}, "design": {"placement": {"offset": 2}}}
    pane = {"id": "pane", "type": "window", "parentWall": "part", "from": [1, 1, 0], "width": 1, "height": 1}
    row, _ = relations.place_opening_group(base, {"geometry": {"components": [pane]}}, marker)
    assert row["geometry"]["components"][0]["from"] == [3, 1, 0]
    assert relations.opening_design_errors(base, row["geometry"]["components"], marker) == []


@pytest.mark.parametrize("axis,direction", [(0, 1), (0, -1), (2, 1), (2, -1)])
def test_stair_width_does_not_extend_its_run_or_hide_a_real_wall_intersection(axis, direction):
    from app.tools.spatial_tools import validate_collision

    start, end = [5, 0, 5], [5, 3, 5]
    end[axis] += 3*direction
    cross_axis = 2 if axis == 0 else 0
    a, b = [*end], [*end]
    a[axis] += 0.5*direction
    b[axis] = a[axis]
    a[cross_axis] -= 2
    b[cross_axis] += 2
    a[1] = 0
    stair = {"id": "flight", "type": "stair", "from": start, "to": end, "width": 1.2}
    wall = {"id": "stop_wall", "type": "wall", "from": a, "to": b, "thickness": 0.24}
    blueprint = {"geometry": {"elements": [stair, wall]}}
    assert "与墙 [stop_wall]" not in validate_collision.func(blueprint)
    a[axis] -= 0.8*direction
    b[axis] = a[axis]
    assert "与墙 [stop_wall]" in validate_collision.func(blueprint)


def test_missing_marker_records_cannot_report_a_complete_design():
    from app.agent.validation.candidate import evaluate_candidate
    from app.agent.validation.diagnostics import blueprint_fingerprint
    from app.design.resolver import _stable_hash

    document = explicit_drawing()
    blueprint = empty_state()["skeleton_blueprint"]
    floor = {"id": "ground", "type": "floor", "from": [0, -0.2, 0], "to": [10, -0.2, 8], "thickness": 0.2}
    blueprint["geometry"]["elements"] = [floor]
    brief = {"implementation": {"design_hash": _stable_hash(document), "records": {
        "building_body": {"status": "implemented", "entity_ids": ["ground"], "entity_fingerprint": blueprint_fingerprint([floor])}
    }}}
    result = evaluate_candidate(blueprint, design_document=document.model_dump(mode="json"), design_brief=brief)
    assert result["errors"]
    assert result["fulfillment"]["implementation_summary"]["design_complete"] is False
