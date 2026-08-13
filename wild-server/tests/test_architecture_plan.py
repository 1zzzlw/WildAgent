from app.agent.architecture_plan import (
    build_deterministic_skeleton,
    conform_balconies_to_slots,
    conform_openings_to_slots,
    conform_railings_to_slots,
    conform_roofs_to_slots,
    evaluate_skeleton_complexity,
    normalize_architecture_plan,
    resolve_facade_layout,
    resolve_complexity_profile,
    select_architecture_plan,
)
from app.utils.blueprint_parser import validate_blueprint_schema
from app.tools.spatial_tools import validate_model_quality, validate_reference_integrity


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
    assert brief["realization"]["modeled_floors"] == 2
    assert brief["realization"]["floor_height"] == 3.2

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


def test_positive_component_quota_repairs_incomplete_required_component_list() -> None:
    message = "生成一栋30层高层住宅塔楼"
    plan = normalize_architecture_plan({
        "required_components": ["door", "window", "roof"],
        "component_quota": {
            "door": {"min": 1, "max": 4},
            "window": {"min": 8, "max": 32},
            "roof": {"min": 1, "max": 1},
            "light": {"min": 2, "max": 8},
        },
    }, message)

    assert "light" in plan["required_components"]


def test_composite_plan_dimensions_override_profile_defaults() -> None:
    cases = (
        ("生成30层住宅塔楼，标准层33×20m，平屋顶", 33.0, 20.0),
        ("生成18层办公楼，建筑平面 48 x 27 米", 48.0, 27.0),
    )

    for message, expected_width, expected_depth in cases:
        plan = normalize_architecture_plan({}, message)

        assert plan["massing"]["width"] == expected_width
        assert plan["massing"]["depth"] == expected_depth


def test_component_dimensions_are_not_misread_as_plan_dimensions() -> None:
    message = "生成30层住宅塔楼，阳台尺寸3×2m，建筑宽33米、深20米"

    plan = normalize_architecture_plan({}, message)

    assert plan["massing"]["width"] == 33.0
    assert plan["massing"]["depth"] == 20.0


def test_schematic_storeys_use_templates_and_facade_slots_cover_full_height() -> None:
    for message, floors, floor_height in (
        ("生成30层住宅塔楼，标准层33×20m，平屋顶", 30, 4.0),
        ("生成18层办公塔楼，建筑平面48×27m，平屋顶", 18, 4.0),
    ):
        plan = normalize_architecture_plan({}, message)
        blueprint = build_deterministic_skeleton(plan, message)
        geometry = blueprint["geometry"]

        assert "❌" not in validate_reference_integrity.func(blueprint)
        assert "standard_floor_plate" in geometry["templates"]
        floor_instances = [
            instance for instance in geometry["instances"]
            if instance["ref"] == "standard_floor_plate"
        ]
        assert len(floor_instances) == floors - 1
        assert floor_instances[0]["position"][1] == floor_height
        assert floor_instances[-1]["position"][1] == (floors - 1) * floor_height

        core_walls = [
            element for element in geometry["elements"]
            if element.get("id", "").startswith("wall_core_")
        ]
        assert len(core_walls) >= 4

        brief = resolve_facade_layout(blueprint, plan)
        window_levels = {
            round(slot["from"][1] // floor_height)
            for slot in brief["opening_slots"]
            if slot["type"] == "window"
        }
        assert min(window_levels) == 0
        assert max(window_levels) == floors - 1


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


def test_standard_plan_rejects_missing_vertical_circulation() -> None:
    message = "生成一座普通两层现代住宅"
    plan = normalize_architecture_plan({}, message)
    blueprint = build_deterministic_skeleton(plan, message)
    blueprint["geometry"]["elements"] = [
        element for element in blueprint["geometry"]["elements"]
        if element["type"] != "stair"
    ]

    evaluation = evaluate_skeleton_complexity(blueprint, plan)

    assert evaluation["meets_target"] is False
    assert evaluation["checks"]["vertical_circulation"] is False


def test_standard_plan_rejects_exact_duplicate_wall() -> None:
    message = "生成一座普通单层现代住宅"
    plan = normalize_architecture_plan({}, message)
    blueprint = build_deterministic_skeleton(plan, message)
    wall = next(
        element for element in blueprint["geometry"]["elements"]
        if element["type"] == "wall"
    )
    blueprint["geometry"]["elements"].append({**wall, "id": "wall_duplicate"})

    evaluation = evaluate_skeleton_complexity(blueprint, plan)

    assert evaluation["meets_target"] is False
    assert evaluation["checks"]["duplicate_wall_free"] is False
    assert evaluation["duplicate_wall_count"] == 1


def test_explicit_two_storey_u_shape_overrides_stale_single_storey_plan() -> None:
    message = (
        "生成一个有退台表现，一层为矩形，二层为U形的两层新中式别墅，"
        "别墅二层U形两端分别有一个宽1.5米的带栏杆的阳台，"
        "阳台突出墙体骨架，阳台后面没有墙体，直接通向室内"
    )
    raw = {
        "massing": {
            "shape": "stepped", "width": 4, "depth": 9,
            "floors": 1, "modeled_floors": 1, "floor_height": 3.2,
        },
        "volumes": [
            {"id": "base", "x": 0, "z": 0, "width": 4, "depth": 9, "start_floor": 1, "end_floor": 1},
            {"id": "left_wing", "x": 0, "z": 0, "width": 3, "depth": 9, "start_floor": 1, "end_floor": 1},
            {"id": "right_wing", "x": 3, "z": 0, "width": 1, "depth": 9, "start_floor": 1, "end_floor": 1},
        ],
    }
    complexity = resolve_complexity_profile(message, precision_mode=True)

    plan = normalize_architecture_plan(raw, message, complexity)

    assert plan["massing"]["floors"] == 2
    assert plan["massing"]["modeled_floors"] == 2
    assert plan["massing"]["shape"] == "u_shape"
    assert plan["massing"]["width"] >= 5.0
    assert plan["balcony_access_count"] == 2
    assert plan["balcony_width"] == 1.5
    assert plan["component_quota"]["balcony"]["min"] == 2
    assert plan["component_quota"]["balcony"]["max"] == 2
    assert {volume["id"] for volume in plan["volumes"]} == {
        "base", "upper_left_wing", "upper_right_wing", "upper_back_link",
    }
    assert any(volume["start_floor"] == 2 for volume in plan["volumes"])


def test_balcony_width_is_not_misread_as_building_width() -> None:
    message = "生成宽12米的两层U形别墅，二层两端分别设置宽1.5米的阳台，阳台直接通向室内"

    plan = normalize_architecture_plan({}, message)

    assert plan["massing"]["width"] == 12.0
    assert plan["balcony_width"] == 1.5


def test_u_shape_skeleton_uses_union_perimeter_and_balcony_access_slots() -> None:
    message = (
        "生成一个有退台表现，一层为矩形，二层为U形的两层新中式别墅，"
        "别墅二层U形两端分别有一个宽1.5米的带栏杆的阳台，"
        "阳台突出墙体骨架，阳台后面没有墙体，直接通向室内"
    )
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan({}, message, complexity)
    blueprint = build_deterministic_skeleton(plan, message)

    assert validate_blueprint_schema(blueprint) == []
    quality = getattr(validate_model_quality, "func", validate_model_quality)(blueprint)
    assert "❌" not in quality
    evaluation = evaluate_skeleton_complexity(blueprint, plan)
    assert evaluation["meets_target"] is True
    assert evaluation["overlapping_column_count"] == 0
    columns = [
        element for element in blueprint["geometry"]["elements"]
        if element.get("type") == "column"
    ]
    assert columns
    assert all(column["base"][0] not in {0.0, 12.0} for column in columns)
    assert all(column["base"][2] not in {0.0, 9.0} for column in columns)

    upper_front_walls = [
        element for element in blueprint["geometry"]["elements"]
        if element["type"] == "wall"
        and min(element["from"][1], element["to"][1]) == 3.2
        and element["id"].startswith("wall_front_")
        and element["from"][2] == 0
    ]
    assert len(upper_front_walls) == 2

    brief = resolve_facade_layout(blueprint, plan)
    access_slots = [
        slot for slot in brief["opening_slots"]
        if slot.get("role") == "balcony_access"
    ]
    assert len(access_slots) == 2
    assert all(slot["width"] == 1.5 for slot in access_slots)

    components, stats = conform_openings_to_slots(
        [], brief, blueprint.get("materials"),
    )
    assert stats["synthesized"] >= 3
    assert len([item for item in components if item.get("role") == "balcony_access"]) == 2


def test_u_shape_flat_roof_balconies_and_terrace_are_conformed_to_plan() -> None:
    message = (
        "生成一座两层U形退台新中式别墅，二层两端分别设置宽1.5米的带栏杆阳台，"
        "阳台直接通向室内，采用平屋顶"
    )
    complexity = resolve_complexity_profile(message, precision_mode=True)
    plan = normalize_architecture_plan(
        {"roof": {"type": "flat", "overhang": 0.4}},
        message,
        complexity,
    )
    blueprint = build_deterministic_skeleton(plan, message)
    brief = resolve_facade_layout(blueprint, plan)

    assert len(brief["balcony_slots"]) == 2
    assert len(brief["roof_slots"]) == 3
    assert len(brief["railing_slots"]) == 1
    assert brief["component_quota"]["roof"]["min"] == 3
    assert brief["component_quota"]["roof"]["max"] == 3

    wrong_balconies = [
        {
            "type": "balcony", "id": "balcony_left", "parentWall": "wrong_wall",
            "from": [0.1, 3.2, 0], "width": 2.8, "depth": 1.5,
            "slabThickness": 0.18, "railingHeight": 1.1,
        },
        {
            "type": "balcony", "id": "balcony_right", "parentWall": "wrong_center_wall",
            "from": [2.9, 3.2, 0], "width": 2.8, "depth": 1.5,
            "slabThickness": 0.18, "railingHeight": 1.1,
        },
    ]
    balconies, balcony_stats = conform_balconies_to_slots(wrong_balconies, brief)
    expected_walls = {slot["wall_id"] for slot in brief["balcony_slots"]}

    assert balcony_stats == {"snapped": 2, "synthesized": 0, "pruned": 0}
    assert {item["parentWall"] for item in balconies} == expected_walls
    assert all(item["width"] == 1.5 for item in balconies)

    roof_template = {
        "type": "roof", "id": "roof_main", "roofType": "flat",
        "span": 13, "depth": 10, "height": 0, "thickness": 0.3,
        "material": "roof", "position": [6, 6.4, 4.5],
    }
    roofs, roof_stats = conform_roofs_to_slots([roof_template], brief)
    roof_parts = [item for item in roofs if item.get("type") == "roof"]

    assert roof_stats["split"] == 2
    assert len(roof_parts) == 3
    for index, first in enumerate(roof_parts):
        first_x0 = first["position"][0] - first["span"] / 2
        first_x1 = first["position"][0] + first["span"] / 2
        first_z0 = first["position"][2] - first["depth"] / 2
        first_z1 = first["position"][2] + first["depth"] / 2
        for second in roof_parts[index + 1:]:
            second_x0 = second["position"][0] - second["span"] / 2
            second_x1 = second["position"][0] + second["span"] / 2
            second_z0 = second["position"][2] - second["depth"] / 2
            second_z1 = second["position"][2] + second["depth"] / 2
            overlap_x = min(first_x1, second_x1) - max(first_x0, second_x0)
            overlap_z = min(first_z1, second_z1) - max(first_z0, second_z0)
            assert overlap_x <= 0 or overlap_z <= 0

    railings, railing_stats = conform_railings_to_slots([], brief)
    assert railing_stats["synthesized"] == 1
    assert railings[0]["path"][0][1] == 3.4


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
