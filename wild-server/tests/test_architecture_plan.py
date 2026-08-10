from app.agent.architecture_plan import (
    conform_openings_to_slots,
    resolve_facade_layout,
    select_architecture_plan,
)


def _two_storey_blueprint() -> dict:
    elements = []
    for level, base_y in enumerate((0, 3.2), start=1):
        top_y = base_y + 3.2
        elements.extend([
            {"id": f"wall_front_{level}", "type": "wall", "from": [0, base_y, 0], "to": [12, top_y, 0], "thickness": 0.24},
            {"id": f"wall_back_{level}", "type": "wall", "from": [12, base_y, 9], "to": [0, top_y, 9], "thickness": 0.24},
            {"id": f"wall_left_{level}", "type": "wall", "from": [0, base_y, 9], "to": [0, top_y, 0], "thickness": 0.24},
            {"id": f"wall_right_{level}", "type": "wall", "from": [12, base_y, 0], "to": [12, top_y, 9], "thickness": 0.24},
        ])
    return {
        "meta": {"version": "1.1", "type": "building", "name": "planned"},
        "geometry": {"elements": elements, "components": []},
        "materials": {
            "wall": {"baseColor": [0.8, 0.8, 0.8]},
            "glass": {"baseColor": [0.5, 0.7, 0.9], "opacity": 0.35},
        },
    }


def test_candidate_selection_respects_explicit_floor_count() -> None:
    raw = {"candidates": [
        {"concept": "单层", "massing": {"floors": 1}},
        {"concept": "三层", "massing": {"floors": 3}},
    ]}
    plan, diag = select_architecture_plan(raw, "生成三层欧式别墅")
    assert plan["massing"]["floors"] == 3
    assert diag["candidate_count"] == 2
    assert len(diag["candidate_summaries"]) == 2
    assert diag["candidate_summaries"][diag["selected_index"]]["score"] == max(diag["candidate_scores"])


def test_facade_layout_resolves_exact_non_overlapping_slots() -> None:
    plan, _ = select_architecture_plan({}, "生成两层欧式别墅")
    brief = resolve_facade_layout(_two_storey_blueprint(), plan)
    doors = [slot for slot in brief["opening_slots"] if slot["type"] == "door"]
    windows = [slot for slot in brief["opening_slots"] if slot["type"] == "window"]
    assert len(doors) == 1
    assert len(windows) >= 6
    assert doors[0]["wall_id"] == "wall_front_1"
    assert doors[0]["from"][2] == 0
    assert brief["facade_plan"]["wall_front_2"]["max_openings"] == 3


def test_merge_conformance_snaps_and_fills_minimum_openings() -> None:
    blueprint = _two_storey_blueprint()
    plan, _ = select_architecture_plan({}, "生成两层欧式别墅")
    brief = resolve_facade_layout(blueprint, plan)
    components, stats = conform_openings_to_slots([
        {"id": "bad_door", "type": "door", "parentWall": "missing", "from": [99, 0, 8], "width": 4, "height": 4},
    ], brief, blueprint["materials"])
    door = next(item for item in components if item["type"] == "door")
    windows = [item for item in components if item["type"] == "window"]
    assert door["parentWall"] == "wall_front_1"
    assert door["from"][2] == 0
    assert len(windows) == brief["component_quota"]["window"]["min"]
    assert stats["synthesized"] == len(windows)
