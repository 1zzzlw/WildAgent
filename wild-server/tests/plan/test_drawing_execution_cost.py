"""低档批处理、修订成本和主体宿主交接的回归。"""
from copy import deepcopy
import json

import pytest

from app.agent.plan import implementation as impl
from app.agent.plan.expand import expand_design_markers
from app.design import relations
from tests.plan.test_drawing_handoff import explicit_drawing
from tests.plan.test_drawing_implementation import empty_state, patch_services, reply, run, task


@pytest.mark.parametrize("level,expected", [("minimal", 6), ("simple", 11),
                                           ("standard", 11), ("detailed", 11)])
def test_low_detail_batches_native_families_without_losing_design(level, expected):
    types = ["building_body", "window", "floor_window", "small_window", "combination_window",
             "door", "side_door", "glass_sliding_door", "roof", "stair", "downlight"]
    markers = [{"id": f"mark_{i}", "type": kind, "design": {"description": kind},
                "depends_on": [] if i == 0 else ["mark_0"]} for i, kind in enumerate(types)]
    state = {"resolved_design": {"design_hash": "approved", "component_markers": markers},
             "design_document": {"decisions": {"complexity": {"level": level}}}}
    before = deepcopy(state)
    plan = expand_design_markers(state)
    assert len(plan.items) == expected
    assert sorted(i for item in plan.items for i in item.target["marker_ids"]) == sorted(m["id"] for m in markers)
    assert all(item.depends_on == [plan.items[0].id] for item in plan.items[1:])
    assert state == before
    if level == "minimal":
        assert {i.kind for i in plan.items} == {"building_body", "window", "door", "roof", "stair", "light"}


def test_low_detail_keeps_custom_design_and_dependent_tasks():
    state = {"resolved_design": {"design_hash": "approved", "component_markers": [
        {"id": "body", "type": "building_body", "depends_on": []},
        {"id": "win", "type": "window", "depends_on": ["body"]},
        {"id": "custom", "type": "freeform_art", "design": {"name": "曲线装饰"}, "depends_on": ["win"]},
    ]}, "design_document": {"decisions": {"complexity": {"level": "minimal"}}}}
    items = expand_design_markers(state).items
    assert items[2].kind == "freeform_art" and items[2].label == "曲线装饰"
    assert items[2].depends_on == [items[1].id]


@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed"])
@pytest.mark.parametrize("node_thinking", [None, False, True])
def test_local_repair_disables_deep_thinking_and_keeps_only_failed_markers(monkeypatch, level, node_thinking):
    import app.llm.client as client
    import app.llm.invocation as invocation
    state = empty_state()
    if node_thinking is not None:
        state["thinking_mode"] = node_thinking
    state["design_document"]["decisions"]["complexity"]["level"] = level
    patch_services(monkeypatch, [])
    options, contexts = [], []
    monkeypatch.setattr(client, "create_llm", lambda **kwargs: options.append(kwargs))
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        entity = {"id": "lattice_piece", "type": "primitive", "shape": "box", "position": [0, 0, 0],
                  "dimensions": [-1, 1, 1] if len(contexts) == 1 else [1, 1, 1]}
        return reply("lattice", [entity])
    monkeypatch.setattr(invocation, "invoke_llm", model)
    _, status, _, _, _ = run(impl.run_marker_generate(state, task(state, "lattice")))
    assert status == "succeeded"
    assert [o["enable_thinking"] for o in options] == [level != "minimal", False]
    assert contexts[1]["failed_implementations"]["lattice"]["geometry"]["elements"][0]["dimensions"][0] == -1


@pytest.mark.parametrize("axis,direction", [(0, 1), (0, -1), (2, 1), (2, -1)])
@pytest.mark.parametrize("shift", [-12, 0, 15])
def test_body_checks_dependent_opening_positions_before_accepting_short_hosts(axis, direction, shift):
    start = [shift, 3, shift]
    end = [shift, 6, shift]
    end[axis] += direction*10
    wall = {"id": "host", "type": "wall", "from": start, "to": end, "thickness": 0.2}
    marker = {"id": "win", "type": "window", "host": "host", "diagram_host": deepcopy(wall),
              "entity": {"parentWall": "host", "centerAlong": 5, "bottomY": 4},
              "design": {}}
    short = deepcopy(wall)
    short["to"][axis] = shift+direction*0.5
    blueprint = {"geometry": {"elements": [short], "components": []}}
    errors = relations.body_host_errors(blueprint, [marker])
    assert errors and "host" in errors[0] and "win" in errors[0]
    assert relations.body_host_errors({"geometry": {"elements": [wall]}}, [marker]) == []
    reversed_wall = {**wall, "from": [end[0], 3, end[2]], "to": [start[0], 6, start[2]]}
    assert relations.body_host_errors({"geometry": {"elements": [reversed_wall]}}, [marker]) == []


def test_body_repairs_host_atomically_then_door_succeeds_on_first_call(monkeypatch):
    state = empty_state(explicit_drawing())
    diagram = next(w for w in state["drawing_hosts"] if w["id"] == "wall_main_front_L1")
    wall = {**diagram, "thickness": 0.2}
    wall.pop("facing", None)
    short = {**wall, "to": [0.5, 3, 0]}
    floor = {"id": "ground", "type": "floor", "from": [0, -0.2, 0], "to": [10, -0.2, 8], "thickness": 0.2}
    door = {"id": "entry", "type": "door", "parentWall": wall["id"], "from": [4.1, 0, 0],
            "width": 1.8, "height": 2.4, "interaction": {"mode": "swing"}}
    door_reply = reply("entry", [])
    payload = json.loads(door_reply.content)
    payload["implementations"][0]["geometry"]["components"] = [door]
    door_reply.content = json.dumps(payload)
    events = patch_services(monkeypatch, [reply("building_body", [floor, short]),
                                        reply("building_body", [floor, wall]), door_reply])
    updates, status, _, _, trace = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and events == ["rag", "model", "model"]
    failed = next(t for t in trace if t.get("stage") == "generate")
    assert "宿主" in failed["errors"]["building_body"]
    assert len(updates["component_fragments"][task(state, "building_body").id]) == 2
    state.update(updates)
    _, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "entry")))
    assert status == "succeeded" and ids == ["entry"]
    assert events == ["rag", "model", "model", "rag", "model"]


def test_body_checks_explicit_opening_extent_but_allows_exposed_partial_wall():
    wall = {"id": "host", "type": "wall", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}
    marker = {"id": "win", "type": "floor_window", "diagram_host": wall,
              "entity": {"parentWall": "host", "position": [8, 1.2, 0]},
              "design": {"size": {"width": 2, "height": 2.4}}}
    partial = {**wall, "from": [7, 0, 0]}
    assert relations.body_host_errors({"geometry": {"elements": [partial]}}, [marker]) == []
    too_short = {**partial, "to": [8.5, 3, 0]}
    assert relations.body_host_errors({"geometry": {"elements": [too_short]}}, [marker])
    assert relations.body_host_errors({"geometry": {"elements": []}}, [marker])


@pytest.mark.parametrize("change", ["level", "plane", "direction"])
def test_body_rejects_hosts_at_wrong_level_plane_or_direction(change):
    wall = {"id": "host", "type": "wall", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}
    marker = {"id": "win", "type": "window", "diagram_host": wall,
              "entity": {"parentWall": "host", "centerAlong": 5, "bottomY": 1}, "design": {}}
    wrong = deepcopy(wall)
    if change == "level":
        wrong["from"][1], wrong["to"][1] = 3, 6
    elif change == "plane":
        wrong["from"][2] = wrong["to"][2] = 1
    else:
        wrong["to"] = [0, 3, 10]
    assert relations.body_host_errors({"geometry": {"elements": [wrong]}}, [marker])


def test_low_detail_rag_query_keeps_each_window_variant(monkeypatch):
    import app.agent.plan.knowledge_tool as knowledge
    import app.llm.invocation as invocation
    state = empty_state()
    state["design_document"]["decisions"]["complexity"]["level"] = "minimal"
    state["resolved_design"]["component_markers"] = [
        {"id": "small", "type": "small_window", "design": {}, "entity": {}, "depends_on": []},
        {"id": "tall", "type": "floor_window", "design": {}, "entity": {}, "depends_on": []},
    ]
    patch_services(monkeypatch, [])
    queries = []
    def rag(query, **kwargs):
        queries.append((query, kwargs))
        return {"text": "原生窗构造", "has_shape_reference": True}
    async def model(*args, **kwargs):
        output = reply("small")
        payload = json.loads(output.content)
        payload["implementations"].append({"id": "tall", "geometry": {"elements": [
            {"id": "tall_part", "type": "primitive", "shape": "box", "position": [3, 0, 0], "dimensions": [1, 1, 1]}]}})
        output.content = json.dumps(payload)
        return output
    monkeypatch.setattr(knowledge, "search_knowledge_result", rag)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    _, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "small")))
    assert status == "succeeded" and len(ids) == 2 and len(queries) == 1
    assert queries[0][1]["kind"] == "window"
    assert "small_window" in queries[0][0] and "floor_window" in queries[0][0]
