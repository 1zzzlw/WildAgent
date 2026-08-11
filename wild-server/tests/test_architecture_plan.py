from app.agent.architecture_plan import (
    build_deterministic_skeleton,
    conform_openings_to_slots,
    evaluate_skeleton_complexity,
    normalize_architecture_plan,
    resolve_facade_layout,
    resolve_complexity_profile,
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

    for index, slot in enumerate(brief["opening_slots"]):
        for other in brief["opening_slots"][index + 1:]:
            if slot["wall_id"] != other["wall_id"]:
                continue
            slot_right = slot["from"][0] + slot["width"]
            other_right = other["from"][0] + other["width"]
            assert slot_right <= other["from"][0] or other_right <= slot["from"][0]


def test_short_wall_does_not_emit_overlapping_facade_slots() -> None:
    blueprint = {
        "geometry": {
            "elements": [{
                "id": "wall_front_short",
                "type": "wall",
                "from": [0, 0, 0],
                "to": [1, 3.2, 0],
                "thickness": 0.24,
            }],
            "components": [],
        },
    }
    plan = {
        "facades": {
            "front": {
                "bays": 3,
                "ground_pattern": ["window", "window", "window"],
                "upper_pattern": [],
            },
        },
        "component_quota": {"window": {"min": 0, "max": 3}},
    }

    brief = resolve_facade_layout(blueprint, plan)
    slots = brief["opening_slots"]

    assert len(slots) == 1
    assert brief["facade_plan"]["wall_front_short"]["max_openings"] == 1


def test_conformance_rejects_overlapping_legacy_slots() -> None:
    brief = {
        "opening_slots": [
            {
                "id": "short:window:1", "type": "window",
                "wall_id": "short", "from": [0.18, 0.96, 0],
                "width": 0.5, "height": 1.55,
            },
            {
                "id": "short:window:2", "type": "window",
                "wall_id": "short", "from": [0.32, 0.96, 0],
                "width": 0.5, "height": 1.55,
            },
        ],
        "component_quota": {"window": {"min": 0, "max": 2}},
    }
    components, stats = conform_openings_to_slots([
        {"id": "window_05", "type": "window", "parentWall": "short"},
        {"id": "window_06", "type": "window", "parentWall": "short"},
    ], brief)

    windows = [item for item in components if item["type"] == "window"]
    assert len(windows) == 1
    assert windows[0]["id"] == "window_05"
    assert stats["pruned"] == 1


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


def test_bay_window_claims_a_window_slot_without_duplicate_plain_window() -> None:
    blueprint = _two_storey_blueprint()
    plan, _ = select_architecture_plan({}, "生成带凸窗的两层欧式别墅")
    brief = resolve_facade_layout(blueprint, plan)
    target_slot = next(slot for slot in brief["opening_slots"] if slot["type"] == "window")

    components, _ = conform_openings_to_slots([{
        "id": "bay",
        "type": "bay_window",
        "parentWall": target_slot["wall_id"],
        "from": target_slot["from"],
        "width": target_slot["width"],
        "height": target_slot["height"],
        "projectionDepth": 0.8,
    }], brief, blueprint["materials"])

    bay = next(item for item in components if item["type"] == "bay_window")
    windows = [item for item in components if item["type"] == "window"]
    assert bay["parentWall"] == target_slot["wall_id"]
    assert bay["from"] == target_slot["from"]
    assert len(windows) + 1 == brief["component_quota"]["window"]["min"]
    assert not any(
        window["parentWall"] == bay["parentWall"]
        and window["from"] == bay["from"]
        for window in windows
    )


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


def test_precision_mode_compiles_detailed_plan_into_articulated_skeleton() -> None:
    message = "生成一座现代两层别墅，立面丰富、有层次感"
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan({}, message, complexity)

    assert complexity["level"] == "detailed"
    assert plan["massing"]["shape"] == "stepped"
    assert len(plan["volumes"]) >= 2
    assert len(plan["detail_packages"]) >= 3
    assert {"balcony", "canopy", "bay_window"}.issubset(plan["required_components"])

    blueprint = build_deterministic_skeleton(plan, message)
    assert validate_blueprint_schema(blueprint) == []
    evaluation = evaluate_skeleton_complexity(blueprint, plan)
    assert evaluation["meets_target"] is True
    assert evaluation["volume_footprint_count"] >= 2
    assert evaluation["element_type_counts"]["column"] >= 4
    assert evaluation["element_type_counts"]["beam"] >= 2

    transition_floors = [
        element for element in blueprint["geometry"]["elements"]
        if element["type"] == "floor" and element["from"][1] == 3.2
    ]
    assert len(transition_floors) == 1
    assert transition_floors[0]["from"] == [0.0, 3.2, 0.0]
    assert transition_floors[0]["to"] == [12.0, 3.2, 9.0]

    brief = resolve_facade_layout(blueprint, plan)
    assert brief["facade_plan"]["wall_front_2_upper_setback"]["max_openings"] > 0


def test_detailed_plan_rejects_plain_low_complexity_shell() -> None:
    message = "生成一座复杂的现代两层别墅"
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan({}, message, complexity)

    evaluation = evaluate_skeleton_complexity(_two_storey_blueprint(), plan)

    assert evaluation["meets_target"] is False
    assert evaluation["checks"]["structural_element_target"] is False
    assert evaluation["checks"]["volume_footprint_target"] is False


def test_detailed_plan_rejects_floor_outside_volume_floor_range() -> None:
    message = "生成一座复杂的现代两层别墅"
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan({}, message, complexity)
    blueprint = build_deterministic_skeleton(plan, message)
    blueprint["geometry"]["elements"].append({
        "id": "floor_outside_supported_transition",
        "type": "floor",
        "from": [-1, 3.2, -1],
        "to": [13, 3.2, 10],
        "thickness": 0.2,
        "material": "concrete",
    })

    evaluation = evaluate_skeleton_complexity(blueprint, plan)

    assert evaluation["meets_target"] is False
    assert evaluation["checks"]["volume_plan_conformance"] is False


def test_standard_plan_rejects_missing_interstorey_cap_floor() -> None:
    message = "生成一座普通两层现代住宅"
    plan = normalize_architecture_plan({}, message)
    blueprint = build_deterministic_skeleton(plan, message)
    blueprint["geometry"]["elements"] = [
        element for element in blueprint["geometry"]["elements"]
        if not (element["type"] == "floor" and element["from"][1] == 3.2)
    ]

    evaluation = evaluate_skeleton_complexity(blueprint, plan)

    assert evaluation["meets_target"] is False
    assert evaluation["checks"]["volume_plan_conformance"] is False


def test_single_storey_detailed_wings_remain_distinct_volume_footprints() -> None:
    message = "生成一座复杂的单层错落别墅"
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan({}, message, complexity)
    blueprint = build_deterministic_skeleton(plan, message)

    evaluation = evaluate_skeleton_complexity(blueprint, plan)

    assert evaluation["meets_target"] is True
    assert evaluation["volume_footprint_count"] >= 2


def test_explicit_simple_request_overrides_precision_default() -> None:
    message = "生成一个简单方盒子住宅，不要复杂装饰"
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan({}, message, complexity)

    assert complexity["level"] == "simple"
    assert len(plan["volumes"]) == 1
    assert plan["detail_packages"] == []
