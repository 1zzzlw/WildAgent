"""相邻体量共用一份物理墙，不删除被引用的宿主或独立构造。"""
from copy import deepcopy
import json

import pytest

from app.agent.plan import implementation as impl
from app.design.markers import implementation_records
from tests.plan.test_drawing_implementation import empty_state, patch_services, reply, run, task


def wall(entity_id, start=0, end=10, *, axis=2, plane=12, bottom=0, top=3.6):
    a, b = [0, bottom, 0], [0, top, 0]
    a[axis], b[axis] = start, end
    a[2-axis] = b[2-axis] = plane
    return {"id": entity_id, "type": "wall", "from": a, "to": b, "thickness": 0.24}


@pytest.mark.parametrize("axis,plane,reverse", [(0, 0, False), (0, -8, True), (2, 12, False), (2, 30, True)])
def test_contained_interface_wall_is_realized_once_without_model_retries(monkeypatch, axis, plane, reverse):
    state = empty_state()
    outer = wall("wall_long", axis=axis, plane=plane)
    shared = wall("wall_short", 10 if reverse else 2, 2 if reverse else 10, axis=axis, plane=plane)
    upper = wall("wall_upper", axis=axis, plane=plane, bottom=3.6, top=7.2)
    events = patch_services(monkeypatch, [reply("building_body", [shared, upper, outer])] * 3)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded"
    assert set(ids) == {"wall_long", "wall_upper"}
    assert events == ["rag", "model"]
    record = implementation_records(updates)["building_body"]
    assert record["assembly_changes"][0]["entity_id"] == "wall_short"
    assert record["assembly_changes"][0]["retained_entity_id"] == "wall_long"
    assert record["assembly_changes"][0]["semantic_change"] is False


def test_only_bad_floor_remains_in_local_repair_after_shared_wall_assembly(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    original = [wall("wall_long"), wall("wall_short", 10, 2),
                {"id": "slab", "type": "floor", "from": [0, 0, 0], "to": [0, 0, 2], "thickness": 0.2}]
    outputs = [reply("building_body", original), reply("building_body", [
        {"id": "slab", "type": "floor", "from": [0, 0, 0], "to": [2, 0, 2], "thickness": 0.2}])]
    patch_services(monkeypatch, [])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return outputs.pop(0)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and set(ids) == {"wall_long", "slab"}
    assert len(contexts) == 2
    assert [e["id"] for e in contexts[1]["failed_implementations"]["building_body"]["geometry"]["elements"]] == ["slab"]
    assert implementation_records(updates)["building_body"]["assembly_changes"]


@pytest.mark.parametrize("difference", ["material", "thickness", "height", "plane", "curve", "reference", "explicit_id", "duplicate_id", "invalid_thickness", "invalid_height", "invalid_coords"])
def test_wall_assembly_preserves_distinct_or_referenced_geometry(difference):
    from app.design.relations import coalesce_body_walls
    outer, shared = wall("wall_long"), wall("wall_short", 2, 10)
    markers = []
    row = {"geometry": {"elements": [outer, shared], "components": []}}
    if difference == "material":
        shared["material"] = "different_finish"
    elif difference == "thickness":
        shared["thickness"] = 0.3
    elif difference == "height":
        shared["to"][1] = 5
    elif difference == "plane":
        shared["from"][0] = shared["to"][0] = 12.1
    elif difference == "curve":
        shared["curve"] = {"radius": 2}
    elif difference == "reference":
        row["geometry"]["components"].append({"id": "window", "type": "window", "parentWall": shared["id"]})
    elif difference == "explicit_id":
        markers = [{"id": shared["id"], "type": "wall", "host": "main"}]
    elif difference == "duplicate_id":
        shared["id"] = outer["id"]
    elif difference == "invalid_thickness":
        shared["thickness"] = -0.24
    elif difference == "invalid_height":
        shared["height"] = -1
    elif difference == "invalid_coords":
        shared["from"][0] = float("inf")
    before = deepcopy(row)
    assembled, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, markers)
    assert assembled == before and changes == []
    assert row == before


@pytest.mark.parametrize("axis", [0, 2])
@pytest.mark.parametrize("plane", [-18, 12])
@pytest.mark.parametrize("reverse", [False, True])
def test_partial_interface_overlap_keeps_the_uncovered_wall_and_its_direction(axis, plane, reverse):
    from app.design.relations import coalesce_body_walls
    outer = wall("wall_long", axis=axis, plane=plane)
    shared = wall("wall_short", 14 if reverse else 6, 6 if reverse else 14, axis=axis, plane=plane)
    row = {"geometry": {"elements": [outer, shared]}}
    original = deepcopy(row)
    assembled, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, [])
    by_id = {e["id"]: e for e in assembled["geometry"]["elements"]}
    retained = by_id[shared["id"]]
    assert by_id[outer["id"]] == outer
    assert [retained["from"][axis], retained["to"][axis]] == ([14, 10] if reverse else [10, 14])
    assert retained["from"][1] == shared["from"][1] and retained["to"][1] == shared["to"][1]
    assert sum(abs(e["to"][axis]-e["from"][axis]) for e in by_id.values()) == 14
    assert changes[0]["before"] == shared and changes[0]["after"] == retained
    assert changes[0]["semantic_change"] is False and row == original


@pytest.mark.parametrize("reverse", [False, True])
def test_existing_host_can_share_a_middle_segment_without_losing_either_outer_end(reverse):
    from app.design.relations import coalesce_body_walls
    base = empty_state()["skeleton_blueprint"]
    base["geometry"]["elements"] = [wall("existing", 0, 10)]
    original = deepcopy(base)
    incoming = wall("new_wall", 12 if reverse else -2, -2 if reverse else 12)
    assembled, changes = coalesce_body_walls(base, {"geometry": {"elements": [incoming]}}, [])
    pieces = assembled["geometry"]["elements"]
    assert len(pieces) == 2 and len({p["id"] for p in pieces}) == 2
    assert pieces[0]["id"] == incoming["id"]
    assert sorted(sorted([p["from"][2], p["to"][2]]) for p in pieces) == [[-2, 0], [10, 12]]
    assert all((p["to"][2]-p["from"][2]) * (incoming["to"][2]-incoming["from"][2]) > 0 for p in pieces)
    assert base == original and changes[0]["retained_entity_id"] == "existing"


def test_shared_wall_piece_id_cannot_collide_with_another_incoming_entity():
    from app.design.relations import coalesce_body_walls
    base = empty_state()["skeleton_blueprint"]
    base["geometry"]["elements"] = [wall("existing", 0, 10)]
    row = {"geometry": {"elements": [wall("new_wall", -2, 12), wall("new_wall__shared_2", plane=25)]}}
    result, _ = coalesce_body_walls(base, row, [])
    assert len({e["id"] for e in result["geometry"]["elements"]}) == 3


@pytest.mark.parametrize("reference", ["marker", "opening"])
def test_partial_shared_wall_keeps_referenced_host_unchanged(reference):
    from app.design.relations import coalesce_body_walls
    row = {"geometry": {"elements": [wall("long"), wall("required", 6, 14)], "components": []}}
    markers = [{"host": "required"}] if reference == "marker" else []
    if reference == "opening":
        row["geometry"]["components"] = [{"id": "window", "parentWall": "required"}]
    original = deepcopy(row)
    result, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, markers)
    assert result == original and not changes


@pytest.mark.parametrize("family", ["terrace_railing", "window"])
@pytest.mark.parametrize("fits", [False, True])
def test_end_trim_preserves_referenced_host_origin_and_installation_range(family, fits):
    from app.design.relations import coalesce_body_walls
    outer, host = wall("long"), wall("host", 14, 6)
    marker = {"id": "attached", "type": family, "host": host["id"], "diagram_host": deepcopy(host),
              "entity": {"parentWall": host["id"], "centerAlong": 2 if fits else 6, "bottomY": 0},
              "design": {"bay": 1 if fits else 2, "bays": 2}}
    row = {"geometry": {"elements": [outer, host]}}
    original = deepcopy(row)
    result, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, [marker])
    after = next(e for e in result["geometry"]["elements"] if e["id"] == host["id"])
    assert after["from"] == host["from"]
    assert after["to"][2] == (10 if fits else 6)
    assert bool(changes) is fits and row == original


def test_referenced_non_opening_host_start_cannot_move():
    from app.design.relations import coalesce_body_walls
    outer, host = wall("long"), wall("host", 6, 14)
    marker = {"id": "railing", "type": "railing", "host": host["id"], "diagram_host": deepcopy(host),
              "entity": {"parentWall": host["id"], "from": [5, 1, 0]}, "design": {"size": {"width": 1}}}
    row = {"geometry": {"elements": [outer, host]}}
    result, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, [marker])
    assert result == row and not changes


@pytest.mark.parametrize("axis,reverse", [(0, False), (0, True), (2, False), (2, True)])
def test_opening_host_origin_can_change_with_world_installation_preserved(axis, reverse):
    from app.design.relations import coalesce_body_walls, place_opening_group
    outer = wall("long", axis=axis)
    host = wall("host", 4 if reverse else 6, -4 if reverse else 14, axis=axis)
    marker = {"id": "window", "type": "window", "host": host["id"], "diagram_host": deepcopy(host),
              "entity": {"parentWall": host["id"], "from": [5, 1, 0]},
              "design": {"placement": {"offset": 5}, "size": {"width": 1, "height": 1}}}
    row = {"geometry": {"elements": [outer, host]}}
    before = deepcopy(marker)
    base = empty_state()["skeleton_blueprint"]
    assembled, changes = coalesce_body_walls(base, row, [marker])
    retained = next(e for e in assembled["geometry"]["elements"] if e["id"] == "host")
    assert changes and retained["from"][axis] == (0 if reverse else 10)
    base["geometry"] = assembled["geometry"]
    opening = {"id": "opening", "type": "window", "parentWall": "host", "from": [0, 1, 0], "width": 1, "height": 1}
    placed, _ = place_opening_group(base, {"geometry": {"components": [opening]}}, marker)
    actual = placed["geometry"]["components"][0]
    direction = -1 if reverse else 1
    assert retained["from"][axis]+direction*actual["from"][0] == host["from"][axis]+direction*5
    assert marker == before and row["geometry"]["elements"][1] == host


def test_body_opening_summary_does_not_block_verified_host_trim():
    from app.design.relations import coalesce_body_walls
    outer, host = wall("long"), wall("host", 14, 6)
    opening = {"id": "window", "type": "window", "host": "host", "diagram_host": deepcopy(host),
               "entity": {"parentWall": "host", "centerAlong": 2, "bottomY": 1},
               "design": {"size": {"width": 2}}}
    summary = {"id": "window", "type": "window", "host": "host", "entity": deepcopy(opening["entity"]), "size": {"width": 2}}
    body = {"id": "building_body", "type": "building_body", "design": {"opening_layout": [summary]}}
    row = {"geometry": {"elements": [outer, host]}}
    result, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, [body, opening])
    assert changes and result["geometry"]["elements"][1]["to"][2] == 10
    # 没有完整标记的摘要引用仍受保护。
    result, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, [body])
    assert result == row and not changes


def test_malformed_geometry_is_preserved_for_validation_instead_of_dropped():
    from app.design.relations import coalesce_body_walls
    row = {"geometry": {"elements": [None, "invalid", wall("valid")]}}
    result, changes = coalesce_body_walls(empty_state()["skeleton_blueprint"], row, [])
    assert result == row and not changes


@pytest.mark.parametrize("reference_source", ["marker_host", "marker_parent", "marker_relation", "base"])
def test_referenced_identical_wall_is_retained_regardless_of_reply_order(reference_source):
    from app.design.relations import coalesce_body_walls
    base = empty_state()["skeleton_blueprint"]
    a, b = wall("unreferenced"), wall("required")
    markers = []
    if reference_source == "marker_host":
        markers = [{"host": b["id"]}]
    elif reference_source == "marker_parent":
        markers = [{"entity": {"parentWall": b["id"]}}]
    elif reference_source == "marker_relation":
        markers = [{"design": {"relation": {"target": b["id"]}}}]
    else:
        base["geometry"]["components"] = [{"id": "existing_opening", "parentWall": b["id"]}]
    row = {"geometry": {"elements": [a, b]}}
    assembled, changes = coalesce_body_walls(base, row, markers)
    assert assembled["geometry"]["elements"] == [b]
    assert changes[0]["retained_entity_id"] == b["id"]


def test_new_contained_wall_can_use_existing_host_without_mutating_base():
    from app.design.relations import coalesce_body_walls
    base = empty_state()["skeleton_blueprint"]
    base["geometry"]["elements"] = [wall("existing")]
    original = deepcopy(base)
    row = {"geometry": {"elements": [wall("redundant", 10, 2), wall("other", plane=20)]}}
    assembled, changes = coalesce_body_walls(base, row, [])
    assert [e["id"] for e in assembled["geometry"]["elements"]] == ["other"]
    assert changes[0]["retained_entity_id"] == "existing"
    assert base == original


def test_explicit_shared_wall_host_is_not_silently_deleted_to_pass_validation(monkeypatch):
    state = empty_state()
    outer, shared = wall("wall_long"), wall("wall_short", 10, 2)
    state["resolved_design"]["component_markers"].append({
        "id": "required_window", "type": "window", "host": shared["id"], "design": {},
        "entity": {"parentWall": shared["id"]}, "diagram_host": shared, "depends_on": ["building_body"]})
    events = patch_services(monkeypatch, [reply("building_body", [outer, shared])] * 3)
    updates, status, _, message, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "aborted" and "共面重叠" in message
    assert events == ["rag", "model", "model", "model"]
    assert implementation_records(updates)["building_body"]["status"] == "abandoned"


def test_non_body_component_is_not_coalesced_as_a_volume_interface(monkeypatch):
    state = empty_state()
    row = reply("lattice", [wall("wall_long"), wall("wall_short", 2, 10)])
    patch_services(monkeypatch, [row] * 3)
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state, "lattice")))
    assert status == "succeeded" and ids == []
    assert implementation_records(updates)["lattice"]["status"] == "abandoned"
    attempts = [t for t in trace if t.get("tool") == "generate_wild"]
    assert all("shared_wall_changes" not in t for t in attempts)
    assert any("共面重叠" in t["errors"].get("lattice", "") for t in attempts)
