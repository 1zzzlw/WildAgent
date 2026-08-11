from app.agent.architecture_plan import (
    build_deterministic_skeleton,
    conform_openings_to_slots,
    normalize_architecture_plan,
    resolve_facade_layout,
    select_architecture_plan,
)
from app.utils.blueprint_parser import validate_blueprint_schema


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


def test_high_rise_keeps_semantic_floor_count_and_uses_schematic_geometry() -> None:
    message = "建造一栋60层高层办公大厦，宽80米，深45米"
    plan = normalize_architecture_plan({
        "massing": {
            "width": 20,
            "depth": 20,
            "floors": 60,
            "floor_height": 3.8,
            "shape": "rectangle",
        },
        "required_components": ["door", "window", "roof"],
    }, message)

    assert plan["profile"] == "high_rise"
    assert plan["massing"]["width"] == 80
    assert plan["massing"]["floors"] == 60
    assert plan["massing"]["modeled_floors"] == 10
    assert plan["massing"]["representation_mode"] == "schematic"
    assert validate_blueprint_schema(build_deterministic_skeleton(plan, message)) == []

    fallback_plan, _ = select_architecture_plan({}, message)
    assert fallback_plan["massing"]["width"] == 80
    assert fallback_plan["massing"]["depth"] == 45


def test_chinese_floor_count_does_not_confuse_twenty_one_with_one() -> None:
    plan, _ = select_architecture_plan({}, "建造二十一层办公楼")
    assert plan["profile"] == "high_rise"
    assert plan["massing"]["floors"] == 21


def test_long_span_public_building_is_not_clipped_to_residential_dimensions() -> None:
    message = "建造180米宽、120米深的体育馆"
    plan = normalize_architecture_plan({
        "massing": {
            "width": 180,
            "depth": 120,
            "floors": 3,
            "floor_height": 5,
            "shape": "rectangle",
        },
        "required_components": ["door", "roof"],
    }, message)

    assert plan["profile"] == "long_span_public"
    assert plan["massing"]["width"] == 180
    assert plan["massing"]["depth"] == 120
    assert "window" not in plan["required_components"]


def test_underground_transport_does_not_force_entrance_or_roof() -> None:
    message = "建造地下三层地铁站，长240米，宽32米"
    plan = normalize_architecture_plan({
        "massing": {
            "width": 32,
            "depth": 240,
            "floors": 3,
            "floor_height": 4.5,
            "shape": "linear",
        },
        "required_components": ["light"],
    }, message)

    assert plan["profile"] == "underground_transport"
    assert plan["required_components"] == ["light"]
    assert plan["component_quota"]["roof"]["max"] == 0
    assert plan["component_quota"]["door"]["min"] == 0
