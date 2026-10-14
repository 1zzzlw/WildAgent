"""图纸事实只交接一次：主体、屋顶归属及直墙门窗定位。"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.agent.plan import implementation as impl
from app.agent.plan.expand import expand_design_markers
from app.design import relations
from app.design.compilation import project_drawing
from app.design.contracts import ComponentInstance
from app.design.markers import component_markers, implementation_records
from tests.plan.test_drawing_implementation import drawing, empty_state, patch_services, reply, run, task


@pytest.mark.parametrize("face", ["front", "back", "left", "right"])
def test_open_face_has_no_wall_host_and_body_receives_only_required_opening_hosts(face):
    document = explicit_drawing()
    document.decisions.facades[face].ground_pattern = ["open"]
    document.decisions.components = []
    before = document.model_dump(mode="json")
    projected = project_drawing(document)
    assert f"wall_main_{face}_L1" not in {w["id"] for w in projected.projection_elements}
    state = empty_state(document)
    body = next(m for m in projected.component_markers if m["type"] == "building_body")
    context = impl._item_context(state, {"building_body": body}, state["skeleton_blueprint"])
    assert context["diagram_hosts"] == []
    assert document.model_dump(mode="json") == before


@pytest.mark.parametrize("face", ["front", "back", "left", "right"])
@pytest.mark.parametrize("thickness", [0.05, 0.24])
def test_open_face_rejects_physical_reference_wall_before_partial_adoption(face, thickness):
    document = drawing()
    projected = project_drawing(document)
    wall = {**next(w for w in projected.projection_elements if w["id"] == f"wall_main_{face}_L1"),
            "thickness": thickness}
    document.decisions.facades[face].ground_pattern = ["open"]
    markers = component_markers(document)
    body = markers[0]
    base = empty_state(document)["skeleton_blueprint"]
    _, accepted, rejected, _ = impl._accept_fragment(base, {"geometry": {"elements": [wall]}}, body,
                                                    dependent_markers=markers)
    assert accepted is None and "开敞" in rejected["error"] and wall["id"] in rejected["error"]


def test_body_context_retains_real_opening_host_without_materializing_other_diagrams():
    state = empty_state(explicit_drawing())
    marker = state["resolved_design"]["component_markers"][0]
    context = impl._item_context(state, {"building_body": marker}, state["skeleton_blueprint"])
    assert [w["id"] for w in context["diagram_hosts"]] == ["wall_main_front_L1"]


@pytest.mark.parametrize("face", ["front", "back", "left", "right"])
@pytest.mark.parametrize("origin", [(0, 0), (-19, 12)])
def test_declared_enclosure_wall_is_owned_by_body_and_door_uses_its_real_host(face, origin, monkeypatch):
    document = drawing()
    volume = document.decisions.volumes[0]
    volume.x, volume.z = origin
    length = volume.width if face in {"front", "back"} else volume.depth
    document.decisions.facades[face].ground_pattern = ["door"]
    document.decisions.components = [
        ComponentInstance(id="entry", type="door", host="enclosure",
            placement={"offset": 2, "sill_height": 0}, size={"width": 1.8, "height": 2.4}),
        ComponentInstance(id="enclosure", type="solid_wall", host=volume.id,
            placement={"face": face, "floor": 1}, size={"width": length, "height": 2.8, "thickness": 0.24},
            form={"material": "stone"}),
    ]
    before = document.model_dump(mode="json")
    state = empty_state(document)
    markers = state["resolved_design"]["component_markers"]
    assert {m["id"] for m in markers} == {"building_body", "entry", "roof_main"}
    body, marker = (next(m for m in markers if m["id"] == i) for i in ("building_body", "entry"))
    assert body["design"]["body_components"][0]["id"] == "enclosure"
    assert body["design"]["body_components"][0]["size"] == before["decisions"]["components"][1]["size"]
    assert marker["host"] == f"wall_main_{face}_L1" and marker["depends_on"] == ["building_body"]
    wall = {**deepcopy(marker["diagram_host"]), "thickness": 0.24}
    wall["to"][1] = 2.8
    state["skeleton_blueprint"]["geometry"]["elements"] = [wall]
    context = impl._item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    assert context["opening_hosts"]["entry"] == {"parentWall": wall["id"], "from": [2, 0, 0]}
    door = {"id": "entry", "type": "door", "parentWall": "enclosure", "from": [2, 0, 0],
            "width": 1.8, "height": 2.4, "interaction": {"mode": "swing"}}
    events = patch_services(monkeypatch, [SimpleNamespace(content=json.dumps({"implementations": [
        {"id": "entry", "geometry": {"elements": [], "components": [door]}}]}), token_usage={})])
    updates, status, ids, _, error = run(impl.run_marker_generate(state, task(state, "entry")))
    assert status == "succeeded" and events == ["rag", "model"] and ids == ["entry"], (error, updates)
    fragment = updates["component_fragments"][task(state, "entry").id][0]
    assert fragment["parentWall"] == wall["id"] and fragment["from"] == [2, 0, 0]
    assert relations.body_host_errors(state["skeleton_blueprint"], markers, diagram_hosts=state["drawing_hosts"]) == []
    assert document.model_dump(mode="json") == before


def test_opening_host_probe_with_no_placed_component_does_not_abort_item(monkeypatch):
    document = drawing()
    document.decisions.components = [ComponentInstance(
        id="entry", type="door", host="wall_main_front_L1",
        placement={"offset": 2, "sill_height": 0}, size={"width": 1.8, "height": 2.4},
    )]
    state = empty_state(document)
    marker = next(m for m in state["resolved_design"]["component_markers"] if m["id"] == "entry")
    wall = {**deepcopy(marker["diagram_host"]), "thickness": 0.24}
    state["skeleton_blueprint"]["geometry"]["elements"] = [wall]
    monkeypatch.setattr(relations, "place_opening_group", lambda *args: ({"geometry": {"components": []}}, []))
    context = impl._item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    assert context["opening_hosts"] == {}


@pytest.mark.parametrize("difference", ["partial_width", "offset", "position", "open", "independent", "relation"])
def test_distinct_wall_is_not_absorbed_into_volume_enclosure(difference):
    document = drawing()
    spec = {"id": "separate_wall", "type": "solid_wall", "host": "main",
            "placement": {"face": "front", "floor": 1}, "size": {"width": 10, "height": 2.8}}
    if difference == "partial_width":
        spec["size"]["width"] = 4
    elif difference == "offset":
        spec["placement"]["normal_offset"] = 1
    elif difference == "position":
        spec["placement"]["position"] = [5, 1.4, -1]
    elif difference == "open":
        document.decisions.facades["front"].ground_pattern = ["open"]
    elif difference == "independent":
        spec["host"] = None
    else:
        spec["relation"] = {"target": "main", "kind": "supported_by"}
    document.decisions.components = [ComponentInstance.model_validate(spec)]
    markers = component_markers(document)
    assert "separate_wall" in {m["id"] for m in markers}
    assert markers[0]["design"]["body_components"] == []


@pytest.mark.parametrize("open_sides", [False, True])
def test_host_resolution_never_adds_a_door_to_a_design_without_openings(open_sides):
    document = drawing()
    document.decisions.components = []
    if open_sides:
        for facade in document.decisions.facades.values():
            facade.ground_pattern = ["open"]
    assert not any(m["type"] in {"door", "window"} for m in component_markers(document))


@pytest.mark.parametrize("host", [None, ""])
def test_independent_marker_keeps_world_position_and_generates_without_a_guessed_host(host, monkeypatch):
    doc = drawing()
    doc.decisions.components = [ComponentInstance(id="free_component", type="custom_lattice", host=host,
        placement={"position": [-3, 1, 7]}, form={"description": "独立构件"})]
    state = empty_state(doc)
    marker = next(m for m in state["resolved_design"]["component_markers"] if m["id"] == "free_component")
    context = impl._item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    assert context["markers"][0]["host"] == host and context["diagram_hosts"] == []
    assert context["markers"][0]["entity"]["position"] == [-3, 1, 7]
    element = {"type": "primitive", "id": "free_component_part", "shape": "box",
               "position": [-3, 1, 7], "dimensions": [1, 1, 1]}
    events = patch_services(monkeypatch, [reply("free_component", [element])])
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "free_component")))
    assert status == "succeeded" and events == ["rag", "model"] and ids == [element["id"]]
    assert updates["component_fragments"][task(state, "free_component").id][0]["position"] == [-3, 1, 7]


def test_enclosure_is_not_assumed_when_the_model_did_not_specify_it():
    assert drawing().decisions.envelope.system == "unspecified"


@pytest.mark.parametrize("system", ["开敞柱廊与封闭内部空间", "圆形壳体与曲线墙", "球体与斜撑结构"])
def test_body_retrieval_uses_approved_system_without_a_building_type_mapping(system, monkeypatch):
    from app.design.contracts import ArchitectureIntent
    from app.agent.plan import knowledge_tool
    doc = drawing()
    doc.decisions.design_intent = ArchitectureIntent(selected_systems=[system])
    state = empty_state(doc)
    floor = {"id": "building_body_floor", "type": "floor", "from": [0, -0.2, 0],
             "to": [10, -0.2, 8], "thickness": 0.2}
    patch_services(monkeypatch, [reply("building_body", [floor])])
    queries = []
    def search(query, **_options):
        queries.append(query)
        return {"text": "当前设计的局部实现参考", "has_shape_reference": True}
    monkeypatch.setattr(knowledge_tool, "search_knowledge_result", search)
    _, status, _, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and len(queries) == 1
    assert system in queries[0] and len(queries[0]) <= 1000


@pytest.mark.parametrize("origin,scale", [([0, 0], 1), ([-11, 6], 2)])
def test_open_outer_volume_preserves_enclosed_inner_volume(origin, scale):
    from app.design.contracts import VolumeDecision, FacadeDecision
    document = drawing()
    document.decisions.components = []
    document.decisions.massing.width *= scale
    document.decisions.massing.depth *= scale
    outer = document.decisions.volumes[0]
    outer.x, outer.z = origin
    outer.width *= scale
    outer.depth *= scale
    for facade in document.decisions.facades.values():
        facade.ground_pattern = ["open"]
    closed = {face: FacadeDecision(bays=1, ground_pattern=["empty"], upper_pattern=["empty"])
              for face in ("front", "back", "left", "right")}
    document.decisions.volumes.append(VolumeDecision(id="inside", x=outer.x+2*scale, z=outer.z+2*scale,
        width=6*scale, depth=4*scale, start_floor=1, end_floor=1, facades=closed))
    projected = project_drawing(document)
    assert len(projected.projection_elements) == 4
    assert all(w["id"].startswith("wall_inside_") for w in projected.projection_elements)
    walls = [{**w, "thickness": 0.24} for w in projected.projection_elements]
    body = projected.component_markers[0]
    base = empty_state(document)["skeleton_blueprint"]
    _, accepted, rejected, _ = impl._accept_fragment(base, {"geometry": {"elements": walls}}, body,
                                                    dependent_markers=projected.component_markers)
    assert rejected is None and accepted["geometry"]["elements"] == walls


def interface_drawing(face, origin=(0, 0), level=0):
    from app.design.contracts import VolumeDecision, FacadeDecision
    document = drawing()
    document.decisions.components = []
    document.decisions.floor_layouts = [{"floor": 1, "level": level, "walls": []}]
    main = document.decisions.volumes[0]
    main.id, main.x, main.z = "closed_space", *origin
    x, z = {"front": (2, -6), "back": (2, 8), "left": (-6, 1), "right": (10, 1)}[face]
    opposite = {"front": "back", "back": "front", "left": "right", "right": "left"}[face]
    wing = VolumeDecision(id="open_space", x=x+origin[0], z=z+origin[1], width=6, depth=6,
                          start_floor=1, end_floor=1,
                          facades={opposite: FacadeDecision(bays=1, ground_pattern=["open"], upper_pattern=["empty"])})
    document.decisions.volumes.append(wing)
    projected = project_drawing(document)
    wall = deepcopy(next(w for w in projected.projection_elements if w["id"] == f"wall_{main.id}_{face}_L1"))
    wall.update(id="physical_shared_wall", thickness=0.24)
    return document, wall


@pytest.mark.parametrize("face", ["front", "back", "left", "right"])
@pytest.mark.parametrize("origin,level,reverse", [((0, 0), 0, False), ((-19, 12), 1.25, True)])
def test_open_volume_does_not_cancel_the_adjacent_volumes_declared_wall(face, origin, level, reverse):
    document, wall = interface_drawing(face, origin, level)
    if reverse:
        document.decisions.volumes.reverse()
        wall["from"], wall["to"] = wall["to"], wall["from"]
    before = document.model_dump(mode="json")
    base = empty_state(document)["skeleton_blueprint"]
    base["geometry"]["elements"] = [wall]
    assert relations.body_host_errors(base, component_markers(document)) == []
    assert document.model_dump(mode="json") == before


@pytest.mark.parametrize("difference", ["both_open", "partial_coverage", "different_plane", "different_floor"])
def test_open_face_still_rejects_a_wall_without_full_declared_enclosure_coverage(difference):
    document, wall = interface_drawing("right")
    main, wing = document.decisions.volumes
    if difference == "both_open":
        document.decisions.facades["right"].ground_pattern = ["open"]
    elif difference == "partial_coverage":
        main.z += 4
    elif difference == "different_plane":
        main.x += 1
    else:
        document.decisions.massing.floors = document.decisions.massing.modeled_floors = 2
        wing.end_floor = 2
        wing.start_floor = 2
        wing.facades["left"].upper_pattern = ["open"]
        wall["from"][1], wall["to"][1] = 3, 6
    base = empty_state(document)["skeleton_blueprint"]
    base["geometry"]["elements"] = [wall]
    errors = relations.body_host_errors(base, component_markers(document))
    assert errors and any("open_space" in e and "开敞" in e for e in errors)


def test_open_face_feedback_does_not_hide_malformed_floor_endpoints():
    document = drawing()
    document.decisions.facades["front"].ground_pattern = ["open"]
    base = empty_state(document)["skeleton_blueprint"]
    wall = {"type": "wall", "id": "blocked_open_side", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.24}
    floor = {"type": "floor", "id": "floor_bad", "from": [0, -0.2, 0], "to": [10, 8], "thickness": 0.2}
    markers = component_markers(document)
    _, adopted, rejected, _ = impl._accept_fragment(base, {"geometry": {"elements": [wall, floor]}}, markers[0],
                                                   dependent_markers=markers)
    assert adopted is None and "开敞" in rejected["error"]
    assert "floor_bad.to" in rejected["error"] and "3 个有限数字" in rejected["error"]


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
