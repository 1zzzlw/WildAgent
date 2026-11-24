"""回放设计节点漏检；不调用真实模型、不改写原始设计。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.design.contracts import ComponentPlacement
from app.domain.design.coordinates import DesignCoordinateConflict, stair_span_conflicts
from app.domain.design.resolver import build_design_document, resolve_design
from app.domain.design.parametric import expand_parameters


def trace_plan():
    path = Path(__file__).resolve().parents[1] / "fixtures/architecture-villa-spatial-conflicts.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))


def simple_plan():
    return {
        "massing": {"shape": "rect", "width": 10, "depth": 10, "floors": 1,
                    "modeled_floors": 1, "floor_height": 3.3},
        "volumes": [{"id": "main", "x": 0, "z": 0, "width": 10, "depth": 10,
                     "start_floor": 1, "end_floor": 1}],
        "structural_grid": {"system": "frame", "x_bays": 1, "z_bays": 1},
        "envelope": {"system": "wall"},
        "facades": {face: {"bays": 1, "ground_pattern": ["empty"], "upper_pattern": ["empty"]}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "none"},
        "components": [opening("entry", "door", "wall_main_front_L1", 1)],
        "floor_layouts": [{"floor": 1, "level": 0,
                          "rooms": [room("left", 0, 0, 5, 10), room("right", 5, 0, 5, 10)],
                          "walls": [{"id": "partition", "from": [5, 0], "to": [5, 10], "thickness": 0.15}]}],
    }


def room(identifier, x, z, width, depth):
    return {"id": identifier, "bounds": {"x": x, "z": z, "width": width, "depth": depth}}


def opening(identifier, kind, host, offset, sill=0):
    return {"id": identifier, "type": kind, "host": host,
            "size": {"width": 1, "height": 2.1, "depth": 0.1},
            "placement": {"offset": offset, "sill_height": sill}}


def resolve(plan):
    document = build_design_document(plan, session_id="spatial-replay", source_request="生成一个别墅")
    return resolve_design(document)


@pytest.mark.parametrize("position", [[7, "H1-0.05", 1], [0, "3.25", 0], [0, True, 0],
                                      [0, float("nan"), 0], [0, float("inf"), 0], [0, 1], [0, 1, 2, 3]])
def test_position_requires_three_finite_numbers(position):
    with pytest.raises(ValidationError):
        ComponentPlacement.model_validate({"position": position})


def test_numeric_position_and_omitted_position_stay_compatible():
    assert ComponentPlacement.model_validate({"position": [0, 3.25, -2]}).model_dump()["position"] == [0, 3.25, -2]
    assert "position" not in ComponentPlacement().model_dump()


def test_trace_rejects_all_three_unexpanded_light_coordinates():
    source = trace_plan()
    before = deepcopy(source)
    with pytest.raises(ValidationError) as exc:
        build_design_document(source, session_id="trace-replay", source_request="生成一个别墅")
    paths = {item["loc"] for item in exc.value.errors()}
    for index in (7, 8, 9):
        assert any(path[-5:] == ("components", index, "placement", "position", 1) for path in paths)
    assert source == before


def test_explicit_stair_cannot_stop_below_target_floor():
    source = trace_plan()
    before = deepcopy(source)
    errors = stair_span_conflicts(source)
    assert any("/components/5/size/height" in error and "2.52" in error and "3.3" in error for error in errors)
    assert source == before


def test_sealed_room_is_rejected_even_if_another_room_has_a_door():
    plan = simple_plan()
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "room_unreachable" and issue["actual"]["room_id"] == "right"
               for issue in exc.value.conflicts)


@pytest.mark.parametrize("access", ["door", "opening", "gap", "open_plan"])
def test_open_space_and_real_passages_remain_valid(access):
    plan = simple_plan()
    if access == "open_plan":
        plan["floor_layouts"][0]["walls"] = []
    elif access == "gap":
        plan["floor_layouts"][0]["walls"][0]["to"][1] = 9
    else:
        plan["components"].append(opening("passage", access, "partition", 4))
    resolve(plan)


@pytest.mark.parametrize("kind,sill", [("window", 0), ("door", 1), ("opening", 1)])
def test_windows_and_high_openings_do_not_make_a_room_accessible(kind, sill):
    plan = simple_plan()
    plan["components"].append(opening("not_a_passage", kind, "partition", 4, sill))
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "room_unreachable" for issue in exc.value.conflicts)


def test_partition_cannot_end_in_the_middle_of_an_exterior_window():
    plan = simple_plan()
    plan["components"].append(opening("window", "window", "wall_main_front_L1", 4.5, 0.5))
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "opening_partition_conflict" for issue in exc.value.conflicts)


def test_local_attachment_needs_a_reference_but_independent_world_placement_is_valid():
    plan = simple_plan()
    plan.pop("floor_layouts")
    plan["components"].append({"id": "canopy", "type": "canopy", "size": {"width": 3, "height": 0.15, "depth": 2},
                               "placement": {"face": "front", "floor": 1, "offset": 2, "sill_height": 2.6}})
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "design_placement_reference_missing" for issue in exc.value.conflicts)
    plan["components"][-1]["placement"] = {"position": [3.5, 2.6, -1]}
    resolve(plan)


def test_explicit_parameter_expression_is_evaluated_before_coordinate_validation():
    expanded, _ = expand_parameters({"parameters": {"H1": 3.3}, "placement": {"position": [7, "=H1-0.05", 1]}})
    assert ComponentPlacement.model_validate(expanded["placement"]).position == [7, 3.25, 1]


@pytest.mark.parametrize("height,expected", [(3.3, False), (2.52, True), (4, True)])
def test_stair_height_uses_explicit_connection_not_whole_building_height(height, expected):
    plan = simple_plan()
    plan["massing"].update(floors=3, modeled_floors=3)
    plan["volumes"][0]["end_floor"] = 3
    plan["components"] = [{"id": "upper_stair", "type": "stair", "size": {"height": height},
                           "floor_connections": [{"from_floor": 2, "to_floor": 3}]}]
    assert bool(stair_span_conflicts(plan)) is expected


def test_stair_span_respects_explicit_levels_and_does_not_restrict_partial_stairs_without_connections():
    plan = trace_plan()
    stair = plan["components"][5]
    plan["floor_layouts"][1]["level"] = 4.0
    stair["size"]["height"] = 3.3
    assert any("4m" in issue for issue in stair_span_conflicts(plan))
    stair["size"]["height"] = 4.0
    assert stair_span_conflicts(plan) == []
    stair.pop("floor_connections")
    stair["size"]["height"] = 1.5
    assert stair_span_conflicts(plan) == []


def test_trace_reports_relational_conflicts_together_after_numeric_fields_are_fixed():
    plan = trace_plan()
    original = deepcopy(plan)
    for index in (7, 8, 9):
        plan["components"][index]["placement"]["position"][1] = 3.25
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    codes = {issue["code"] for issue in exc.value.conflicts}
    assert {"design_stair_span_conflict", "design_placement_reference_missing", "room_unreachable",
            "opening_partition_conflict", "design_opening_conflict"} <= codes
    assert original == trace_plan()


@pytest.mark.parametrize("face,along", [("front", 3), ("back", 7), ("left", 6), ("right", 4)])
@pytest.mark.parametrize("shift", [(0, 0), (-20, 40)])
def test_opening_partition_check_uses_world_direction_and_allows_jamb_contact(face, along, shift):
    plan = simple_plan()
    dx, dz = shift
    plan["volumes"][0].update(x=dx, z=dz)
    points = ([3 + dx, dz], [3 + dx, 10 + dz]) if face in {"front", "back"} else ([dx, 4 + dz], [10 + dx, 4 + dz])
    plan["floor_layouts"][0]["rooms"] = []
    plan["floor_layouts"][0]["walls"][0].update({"from": points[0], "to": points[1]})
    plan["components"] = [opening("window", "window", f"wall_main_{face}_L1", along - 0.5, 0.5)]
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "opening_partition_conflict" for issue in exc.value.conflicts)
    plan["components"][0]["placement"]["offset"] = along
    resolve(plan)


def test_mixed_open_facade_cannot_host_a_door_in_its_wall_free_segment():
    plan = simple_plan()
    plan.pop("floor_layouts")
    plan["facades"]["front"] = {"bays": 2, "ground_pattern": ["empty", "open"], "upper_pattern": ["empty", "empty"]}
    plan["components"][0]["placement"]["offset"] = 6
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "design_opening_conflict" and "open" in issue["reason"] for issue in exc.value.conflicts)
    plan["components"][0]["placement"]["offset"] = 1
    resolve(plan)


def test_unknown_window_width_does_not_turn_its_known_left_edge_into_a_center():
    plan = simple_plan()
    plan["floor_layouts"][0]["rooms"] = []
    window = opening("window", "window", "wall_main_front_L1", 5, 0.5)
    window["size"].pop("width")
    plan["components"].append(window)
    resolve(plan)
    # 自动开间的 centerAlong 是中心：与内墙重合时，任意正宽度都会跨墙。
    plan["components"] = []
    plan["facades"]["front"]["ground_pattern"] = ["window"]
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert any(issue["code"] == "opening_partition_conflict" for issue in exc.value.conflicts)


def test_open_facade_and_reversed_partition_passages_are_accessible():
    plan = simple_plan()
    plan["facades"]["front"] = {"bays": 2, "ground_pattern": ["empty", "open"], "upper_pattern": ["empty", "empty"]}
    resolve(plan)
    plan["facades"]["front"]["ground_pattern"] = ["empty", "empty"]
    plan["floor_layouts"][0]["walls"][0].update({"from": [5, 10], "to": [5, 0]})
    plan["components"].append(opening("passage", "door", "partition", 4))
    resolve(plan)


def test_missing_access_is_reported_as_review_instead_of_guessing_an_entrance():
    plan = simple_plan()
    plan["components"] = []
    resolved = resolve(plan)
    assert any(gap.target == "floor_1" and gap.status == "needs_review" for gap in resolved.design_gaps)


def test_stair_behind_a_closed_partition_is_not_an_independent_entrance():
    plan = simple_plan()
    plan["massing"].update(floors=2, modeled_floors=2)
    plan["volumes"][0]["end_floor"] = 2
    plan["floor_layouts"].append({"floor": 2, "level": 3.3, "rooms": [room("upper", 0, 0, 10, 10)], "walls": []})
    plan["components"].append({"id": "stair_right", "type": "stair", "size": {"width": 1, "height": 3.3, "depth": 2},
                               "placement": {"position": [7, 1.65, 5]}, "floor_connections": [{"from_floor": 1, "to_floor": 2}]})
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    unreachable = {issue["actual"]["room_id"] for issue in exc.value.conflicts if issue["code"] == "room_unreachable"}
    assert unreachable == {"right", "upper"}
    # 允许经另一部楼梯到上层，再下到首层右侧，不强迫每层都有直连门。
    stair = deepcopy(plan["components"][-1])
    stair["id"] = "stair_left"
    stair["placement"]["position"][0] = 2
    plan["components"].append(stair)
    resolved = resolve(plan)
    assert not any(gap.target.startswith("floor_") for gap in resolved.design_gaps)
    plan["components"].pop(0)
    resolved = resolve(plan)
    assert any(gap.target == "circulation" and "室外入口" in gap.evidence for gap in resolved.design_gaps)


def test_disconnected_floor_connections_do_not_gain_an_undeclared_middle_flight():
    plan = simple_plan()
    plan["massing"].update(floors=4, modeled_floors=4)
    plan["volumes"][0]["end_floor"] = 4
    plan["circulation"] = {"vertical_strategy": "interior_stair"}
    plan["floor_layouts"] = [{"floor": floor, "level": (floor - 1) * 3.3,
                              "rooms": [room(f"room_{floor}", 0, 0, 10, 10)], "walls": []}
                             for floor in (1, 2, 3, 4)]
    plan["components"].append({"id": "stairs", "type": "stair", "size": {"width": 1, "height": 9.9, "depth": 2},
                               "placement": {"position": [2, 4.95, 5]},
                               "floor_connections": [{"from_floor": 1, "to_floor": 2}, {"from_floor": 3, "to_floor": 4}]})
    with pytest.raises(DesignCoordinateConflict) as exc:
        resolve(plan)
    assert {issue["actual"]["room_id"] for issue in exc.value.conflicts if issue["code"] == "room_unreachable"} == {"room_3", "room_4"}


def test_existing_architecture_repair_flow_can_fix_coordinates_then_add_a_passage(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.agent.workflows.design import architecture, drafting
    from app.infrastructure.llm.invocation import LlmResult

    plan = simple_plan()
    plan["components"].append({"id": "light", "type": "downlight", "placement": {"position": [2, "H1-0.05", 2]}})
    before = deepcopy(plan)
    replies = [plan,
               {"operations": [{"op": "replace", "path": "/components/1/placement/position/1", "value": 3.25}]},
               {"operations": [{"op": "add", "path": "/components/-", "value": opening("passage", "door", "partition", 4)}]}]
    calls = []

    async def reply(_model, messages, **_kwargs):
        calls.append(messages)
        return LlmResult(content=json.dumps(replies[len(calls) - 1], ensure_ascii=False))

    monkeypatch.setattr(architecture, "get_reasoning_callback", lambda: None)
    monkeypatch.setattr(drafting, "create_llm", lambda **_kwargs: SimpleNamespace(bind_tools=lambda _: object()))
    monkeypatch.setattr(drafting, "invoke_llm", reply)
    result = asyncio.run(architecture.architecture_planner({"user_message": "生成一个别墅", "detail_level": "minimal",
                                                          "intent_profile": "villa", "session_id": "repair-replay", "thinking_mode": False}))
    assert result.get("error") is None
    assert result["architecture_diag"]["settled"] is True
    assert result["architecture_diag"]["model_calls"] == len(calls) == 3
    assert plan == before
    accepted = result["architecture_plan"]
    assert [item["id"] for item in accepted["components"]] == ["entry", "light", "passage"]
    assert accepted["massing"]["width"] == 10
    assert '"room_id": "right"' in calls[2][0].content
    assert "/floor_layouts/0/walls" in calls[2][0].content
