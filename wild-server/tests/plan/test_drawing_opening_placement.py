"""门窗按图纸位置落实，默认立面不能重复实例或封堵体量接口。"""
from copy import deepcopy

import pytest

from app.agent.knowledge.component_names import resolve_component_name
from app.agent.plan import implementation as impl
from app.design.contracts import ComponentInstance, FacadeDecision
from app.design.markers import component_markers
from tests.plan.test_drawing_integration import drawing
from tests.plan.test_drawing_implementation import empty_state, patch_services, reply, run, task


@pytest.mark.parametrize("name,kind,family", [
    ("入口门", "door", "door"), ("组合窗", "combination_window", "window"),
    ("格栅窗", "louvered_window", "window"), ("厨房窗", "window", "window"),
    ("卧室窗", "window", "window"), ("设备百叶", "ventilation_louvre", "window"),
])
def test_facade_aliases_use_the_same_component_family(name, kind, family):
    actual = resolve_component_name(name)
    assert (actual["kind"], actual["entity_type"]) == (kind, family)


def test_fill_and_no_opening_are_body_design_and_not_extra_tasks():
    document = drawing()
    document.decisions.facades["front"] = FacadeDecision(bays=4,
        ground_pattern=["实墙", "无开口", "solid_wall", "empty"],
        upper_pattern=["实体墙", "no_opening", "solid", "open"])
    before = document.model_dump(mode="json")
    markers = component_markers(document)
    assert not any(m.get("design_path") == "/decisions/facades/front" for m in markers)
    assert document.model_dump(mode="json") == before


@pytest.mark.parametrize("kind,alias", [("door", "入口门"), ("combination_window", "组合窗")])
def test_explicit_opening_suppresses_its_default_alias(kind, alias):
    document = drawing()
    document.decisions.facades["front"] = FacadeDecision(bays=4,
        ground_pattern=[alias]*4, upper_pattern=[alias]*4)
    document.decisions.components = [ComponentInstance(id="explicit", type=kind,
        host="wall_main_front_L1", placement={"offset": 1, "sill_height": 0}, size={"width": 3})]
    markers = component_markers(document)
    assert {m["id"] for m in markers}.isdisjoint(f"{alias}_main_front_L1_{i}" for i in (1, 2))
    assert any(m["id"] == f"{alias}_main_front_L1_3" for m in markers)


def test_volume_facades_override_default_without_repeating_main_layout():
    document = drawing()
    wing = document.decisions.volumes[1]
    wing.facades = {"front": FacadeDecision(bays=1, ground_pattern=["door"], upper_pattern=["empty"])}
    markers = component_markers(document)
    assert [m["id"] for m in markers if m["host"] == "wall_annex_front_L1"] == ["door_annex_front_L1_1"]
    assert any(m["id"] == "window_main_front_L2_3" for m in markers)


def test_absent_volume_facade_override_preserves_existing_serialized_design():
    volume = drawing().decisions.volumes[0]
    assert "facades" not in volume.model_dump(mode="json")
    volume.facades = {"front": FacadeDecision(bays=1, ground_pattern=["door"], upper_pattern=["empty"])}
    assert volume.model_dump(mode="json")["facades"]["front"]["ground_pattern"] == ["door"]


@pytest.mark.parametrize("offset", [-20, 0, 15])
def test_adjacent_volumes_do_not_receive_default_exterior_openings_on_shared_faces(offset):
    document = drawing()
    document.decisions.volumes[1].end_floor = 1
    document.decisions.volumes[1].z = 1
    document.decisions.volumes[1].depth = 8
    for volume in document.decisions.volumes:
        volume.x += offset
        volume.z += offset
    markers = component_markers(document)
    assert not any(m["host"] == "wall_annex_left_L1" for m in markers)
    assert not any(m["host"] == "wall_main_right_L1" and m.get("design", {}).get("bay") in (1, 2) for m in markers)
    assert any(m["host"] == "wall_main_right_L2" for m in markers)


def installed_window(entity_id="opening", along=2, width=2.4, y=4.1, host="host"):
    return {"type": "window", "id": entity_id, "parentWall": host,
            "from": [along, y, 0], "width": width, "height": 1.8}


def base_and_marker():
    base = empty_state()["skeleton_blueprint"]
    wall = {"type": "wall", "id": "host", "from": [0, 3.2, 0], "to": [10, 6.4, 0], "thickness": 0.3}
    base["geometry"]["elements"] = [wall]
    marker = {"id": "designed", "type": "combination_window", "host": "host",
        "entity": {"parentWall": "host", "from": [2, 4.1, 0]},
        "design": {"placement": {"offset": 2, "sill_height": 0.9}, "size": {"width": 2.4, "height": 1.8}}}
    return base, marker


@pytest.mark.parametrize("along,y", [(1, 4.1), (2, 3.2), (5, 4.3)])
def test_explicit_window_cannot_be_moved_to_avoid_conflicts(along, y):
    base, marker = base_and_marker()
    with pytest.raises(ValueError, match="图纸"):
        impl._accept_group(base, {"geometry": {"components": [installed_window(along=along, y=y)]}}, marker)


def test_composite_window_holes_keep_the_designed_group_extent():
    base, marker = base_and_marker()
    good = [installed_window("left", 2, 1.2), installed_window("right", 3.2, 1.2)]
    _, _, record = impl._accept_group(base, {"geometry": {"components": good}}, marker)
    assert record["entity_ids"] == ["left", "right"]
    with pytest.raises(ValueError, match="图纸"):
        impl._accept_group(base, {"geometry": {"components": [good[0], installed_window("right", 4, 1.2)]}}, marker)


def test_door_with_transom_keeps_the_door_clear_opening_dimensions():
    base, marker = base_and_marker()
    marker["type"] = "door"
    marker["design"]["size"] = {"width": 1.2, "height": 2}
    door = {**installed_window(width=1.2), "type": "door", "height": 2,
            "interaction": {"mode": "swing"}}
    transom = {**installed_window("transom", width=1.2, y=6.1), "height": 0.2}
    _, _, record = impl._accept_group(base, {"geometry": {"components": [door, transom]}}, marker)
    assert record["entity_ids"] == ["opening", "transom"]


def test_opposite_normal_offsets_cannot_cancel_each_other_in_a_window_group():
    base, marker = base_and_marker()
    holes = [installed_window("left", 2, 1.2), installed_window("right", 3.2, 1.2)]
    holes[0]["from"][2], holes[1]["from"][2] = 0.01, -0.01
    with pytest.raises(ValueError, match="法向位置"):
        impl._accept_group(base, {"geometry": {"components": holes}}, marker)


def test_body_receives_opening_locations_before_building_walls_and_frame():
    document = drawing()
    document.decisions.components = [ComponentInstance(id="entry", type="door",
        host="wall_main_front_L1", placement={"offset": 1}, size={"width": 1.2, "height": 2.6})]
    body = component_markers(document)[0]
    entry = next(m for m in body["design"]["opening_layout"] if m["id"] == "entry")
    assert entry["entity"]["from"] == [1, 0, 0]
    assert entry["size"] == {"width": 1.2, "height": 2.6}


def test_primitive_glass_on_wall_is_not_a_window_without_a_hole():
    base, marker = base_and_marker()
    primitive = {"type": "primitive", "id": "glass_panel", "shape": "box",
                 "position": [3.2, 5, 0], "dimensions": [2.4, 1.8, 0.01]}
    with pytest.raises(ValueError, match="洞口"):
        impl._accept_group(base, {"geometry": {"elements": [primitive]}}, marker)


def test_louvres_attached_to_an_existing_window_do_not_need_another_wall_hole():
    base, marker = base_and_marker()
    base["geometry"]["components"] = [installed_window()]
    marker["type"] = "louvered_window"
    marker["entity"]["parentWall"] = "opening"
    shade = {"type": "primitive", "id": "shade", "shape": "box",
             "position": [3.2, 5, -0.2], "dimensions": [2.4, 0.05, 0.1]}
    _, _, record = impl._accept_group(base, {"geometry": {"elements": [shade]}}, marker)
    assert record["entity_ids"] == ["shade"]


def test_window_task_cannot_add_a_whole_wall_to_close_the_body_interface():
    base, marker = base_and_marker()
    base["geometry"]["elements"] = []
    extra = {"type": "wall", "id": "new_wall", "from": [0, 3.2, 0], "to": [10, 6.4, 0], "thickness": 0.2}
    with pytest.raises(ValueError, match="补墙"):
        impl._accept_group(base, {"geometry": {"elements": [extra], "components": [installed_window(host="new_wall")]}}, marker)


def test_invalid_opening_group_is_not_partially_locked_before_its_repair(monkeypatch):
    base, marker = base_and_marker()
    state = empty_state()
    state["skeleton_blueprint"] = base
    state["resolved_design"]["component_markers"] = [marker]
    state["drawing_hosts"] = base["geometry"]["elements"]
    bad = {"type": "primitive", "id": "bad_glass", "shape": "box",
           "position": [3.2, 5, 0], "dimensions": [2.4, 1.8, 0.01]}
    corrected = installed_window()
    first, second = reply("designed", [bad]), reply("designed", [])
    import json
    payload = json.loads(second.content)
    payload["implementations"][0]["geometry"]["components"] = [corrected]
    second.content = json.dumps(payload)
    events = patch_services(monkeypatch, [first, second])
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "designed")))
    assert status == "succeeded" and ids == [corrected["id"]]
    assert events == ["rag", "model", "model"]
    assert bad not in updates["component_fragments"][task(state, "designed").id]


@pytest.mark.parametrize("axis,direction,offset", [(0, 1, -20), (0, -1, 10), (2, 1, 0), (2, -1, 15)])
def test_segmented_host_keeps_the_same_world_position(axis, direction, offset):
    base, marker = base_and_marker()
    wall = base["geometry"]["elements"][0]
    wall["from"][axis], wall["to"][axis] = offset, offset+10*direction
    wall["from"][2-axis] = wall["to"][2-axis] = 0
    marker["diagram_host"] = deepcopy(wall)
    segment = {**deepcopy(wall), "id": "host_part"}
    segment["from"][axis] += direction
    segment["to"][axis] = offset+6*direction
    base["geometry"]["elements"] = [segment]
    _, _, record = impl._accept_group(base,
        {"geometry": {"components": [installed_window(along=1, host="host_part")]}}, marker)
    assert record["status"] == "implemented"


def test_partial_wall_overlap_is_reported_without_rejecting_adjacent_panels():
    from app.tools.spatial_tools import validate_model_quality
    base, _ = base_and_marker()
    wall = base["geometry"]["elements"][0]
    extra = {**wall, "id": "fill", "from": [2, 3.2, 0], "to": [4, 6.4, 0]}
    base["geometry"]["elements"].append(extra)
    assert "共面" in validate_model_quality.func(base)
    wall["to"][0] = 2
    assert "❌" not in validate_model_quality.func(base)


@pytest.mark.parametrize("gap", [0, 0.1])
def test_coplanar_check_uses_real_window_holes_and_preserves_wall_piers(gap):
    from app.tools.spatial_tools import validate_model_quality
    base, _ = base_and_marker()
    base["geometry"]["components"] = [installed_window("left", 2, 1.2-gap),
                                      installed_window("right", 3.2+gap, 1.2-gap)]
    base["geometry"]["elements"].append({"type": "primitive", "id": "shade", "shape": "box",
        "position": [3.2, 5, -0.2], "dimensions": [2.4, 0.05, 0.1]})
    assert ("❌" in validate_model_quality.func(base)) == bool(gap)


def test_design_placement_error_keeps_its_entity_for_local_repair():
    from app.agent.validation.issues import validation_issues_from_results
    base, marker = base_and_marker()
    window = installed_window(along=1)
    base["geometry"]["components"] = [window]
    from app.design.relations import opening_design_errors
    errors = opening_design_errors(base, [window], marker)
    results = [{"name": "design_opening_placement", "has_error": True,
                "output": "\n".join("❌ [design] "+e for e in errors)}]
    issues = validation_issues_from_results(results, base)
    assert issues and all(i["entity_id"] == window["id"] for i in issues)


@pytest.mark.parametrize("index,kind", [(0, "ventilation_louvre"), (1, "exhaust_outlet")])
def test_ventilation_knowledge_examples_install_into_a_real_wall_hole(index, kind):
    import json
    from pathlib import Path
    import re
    source = Path(__file__).resolve().parents[2] / "storage/knowledge_base/knowledge/components/ventilation-detail-examples.md"
    examples = re.findall(r"```json\s*\n(.*?)\n```", source.read_text(encoding="utf-8"), re.S)
    example = json.loads(examples[index])
    base = empty_state()["skeleton_blueprint"]
    base["geometry"]["elements"] = [e for e in example["elements"] if e["type"] == "wall"]
    row = {"geometry": {"elements": [e for e in example["elements"] if e["type"] != "wall"],
                        "components": example["components"]}, "materials": example["materials"]}
    marker = {"id": kind, "type": kind, "entity": {"parentWall": "host_wall", "from": [1.4, 1, 0]},
              "design": {"placement": {"offset": 1.4, "sill_height": 1}, "size": {"width": 1.2, "height": 1}}}
    _, _, record = impl._accept_group(base, row, marker)
    assert "vent_hole" in record["entity_ids"]
