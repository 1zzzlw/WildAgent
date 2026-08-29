from app.agent.architecture_plan import (
    build_deterministic_skeleton,
    conform_openings_to_slots,
    normalize_architecture_plan,
    resolve_facade_layout,
)
from app.agent.spatial_plan import (
    architecture_plan_to_svgs,
    apply_spatial_plan_to_blueprint,
    deterministic_baseline_spatial_plan,
    fallback_spatial_plan,
    normalize_spatial_plan,
    spatial_opening_slots,
    spatial_plan_to_svg,
    validate_spatial_plan,
)
from app.agent.floor_plan_rules import (
    auto_repair_floor_plan_rules,
    evaluate_floor_plan_rules,
)


def _massing(floors: int = 1) -> dict:
    return {
        "shape": "rectangle",
        "width": 12.0,
        "depth": 9.0,
        "floor_height": 3.2,
        "modeled_floors": floors,
    }


def _two_room_raw_plan() -> dict:
    return {
        "levels": [{
            "level": 1,
            "entrance_space_id": "living",
            "spaces": [
                {
                    "id": "living",
                    "name": "起居室",
                    "space_type": "living",
                    "bounds": [0, 0, 6, 9],
                },
                {
                    "id": "service",
                    "name": "服务空间",
                    "space_type": "service",
                    "bounds": [6, 0, 12, 9],
                },
            ],
            "walls": [{
                "id": "partition",
                "from": [6, 0],
                "to": [6, 9],
                "thickness": 0.12,
            }],
            "openings": [{
                "id": "connection",
                "type": "door",
                "host_wall_id": "partition",
                "offset": 4,
                "width": 0.9,
                "height": 2.1,
                "sill_height": 0,
                "connects": ["living", "service"],
            }],
        }],
    }


def test_normalize_spatial_plan_uses_xz_and_preserves_connectivity() -> None:
    plan = normalize_spatial_plan(_two_room_raw_plan(), _massing())

    assert plan["source"] == "model"
    assert plan["coordinate_system"]["horizontal_axes"] == ["x", "z"]
    assert plan["coordinate_system"]["vertical_axis"] == "y"
    assert validate_spatial_plan(plan) == []
    assert plan["levels"][0]["openings"][0]["connects"] == [
        "space_1_living",
        "space_1_service",
    ]


def test_invalid_disconnected_plan_falls_back_instead_of_guessing() -> None:
    raw = _two_room_raw_plan()
    raw["levels"][0]["openings"] = []

    plan = normalize_spatial_plan(raw, _massing())

    assert plan["source"] == "deterministic_fallback"
    assert "无法从入口到达" in plan["fallback_reason"]
    assert len(plan["levels"][0]["spaces"]) == 1
    assert plan["levels"][0]["walls"] == []


def test_door_connection_must_match_the_rooms_at_its_real_position() -> None:
    raw = {
        "levels": [{
            "level": 1,
            "entrance_space_id": "left_bottom",
            "spaces": [
                {"id": "left_bottom", "bounds": [0, 0, 6, 4.5]},
                {"id": "left_top", "bounds": [0, 4.5, 6, 9]},
                {"id": "right_bottom", "bounds": [6, 0, 12, 4.5]},
                {"id": "right_top", "bounds": [6, 4.5, 12, 9]},
            ],
            "walls": [{"id": "middle", "from": [6, 0], "to": [6, 9]}],
            "openings": [{
                "id": "wrong_door",
                "type": "door",
                "host_wall_id": "middle",
                "offset": 1,
                "width": 0.9,
                "connects": ["left_top", "right_top"],
            }],
        }],
    }

    plan = normalize_spatial_plan(raw, _massing())

    assert plan["source"] == "deterministic_fallback"
    assert "位置不在 connects" in plan["fallback_reason"]


def test_spatial_plan_compiles_wall_and_parent_local_opening_slot() -> None:
    plan = normalize_spatial_plan(_two_room_raw_plan(), _massing())
    blueprint = {
        "geometry": {"elements": [], "components": []},
        "materials": {"wall_finish": {"baseColor": [0.8, 0.8, 0.8]}},
    }

    result = apply_spatial_plan_to_blueprint(blueprint, plan)
    wall = blueprint["geometry"]["elements"][0]
    slot = spatial_opening_slots(plan)[0]

    assert result == {"walls_added": 1, "walls_replaced": 0}
    assert wall["from"] == [6.0, 0.0, 0.0]
    assert wall["to"] == [6.0, 3.2, 9.0]
    assert slot["wall_id"] == wall["id"]
    assert slot["from"] == [4.0, 0.0, 0.0]


def test_svg_is_derived_from_valid_plan_and_escapes_room_label() -> None:
    raw = _two_room_raw_plan()
    raw["levels"][0]["spaces"][0]["name"] = "起居室 <测试>"
    plan = normalize_spatial_plan(raw, _massing())

    svg = spatial_plan_to_svg(plan)

    assert svg.startswith("<svg")
    assert "起居室 &lt;测试&gt;" in svg
    assert "#F87171" in svg
    assert "front = min Z" in svg
    assert "5m" in svg


def test_setback_level_uses_its_own_volume_envelope() -> None:
    massing = _massing(floors=2)
    raw = {
        "levels": [
            {
                "level": 1,
                "entrance_space_id": "ground",
                "spaces": [{"id": "ground", "bounds": [0, 0, 12, 9]}],
                "walls": [],
                "openings": [],
            },
            {
                "level": 2,
                "entrance_space_id": "upper",
                "spaces": [{"id": "upper", "bounds": [1.5, 1, 11.5, 8]}],
                "walls": [],
                "openings": [],
            },
        ],
    }
    volumes = [
        {"x": 0, "z": 0, "width": 12, "depth": 9, "start_floor": 1, "end_floor": 1},
        {"x": 1.5, "z": 1, "width": 10, "depth": 7, "start_floor": 2, "end_floor": 2},
    ]

    plan = normalize_spatial_plan(raw, massing, volumes)

    assert plan["source"] == "model"
    assert plan["levels"][1]["envelope"] == [1.5, 1.0, 11.5, 8.0]
    assert validate_spatial_plan(plan) == []


def test_review_svg_contains_facade_doors_windows_and_all_levels() -> None:
    spatial_plan = normalize_spatial_plan(_two_room_raw_plan(), _massing())
    architecture_plan = {
        "spatial_plan": spatial_plan,
        "facades": {
            "front": {
                "bays": 3,
                "ground_pattern": ["window", "door", "window"],
                "upper_pattern": ["window", "empty", "window"],
            },
            "back": {"bays": 2, "ground_pattern": ["window", "window"]},
            "left": {"bays": 1, "ground_pattern": ["window"]},
            "right": {"bays": 1, "ground_pattern": ["empty"]},
        },
    }

    svgs = architecture_plan_to_svgs(architecture_plan)

    assert list(svgs) == ["1"]
    assert svgs["1"].count("#F87171") >= 2  # 图例 + 外门（另含内门）
    assert svgs["1"].count("#60A5FA") >= 5  # 图例 + 四个外窗


def test_deterministic_baseline_is_valid_and_contains_real_rooms_and_doors() -> None:
    volumes = [
        {"x": 0, "z": 0, "width": 12, "depth": 9, "start_floor": 1, "end_floor": 1},
        {"x": 1, "z": 0.5, "width": 10, "depth": 7, "start_floor": 2, "end_floor": 2},
    ]

    plan = deterministic_baseline_spatial_plan(_massing(floors=2), volumes, "模型服务不可用")

    assert plan["source"] == "deterministic_template"
    assert validate_spatial_plan(plan) == []
    assert all(len(level["spaces"]) == 2 for level in plan["levels"])
    assert all(len(level["walls"]) == 1 for level in plan["levels"])
    assert all(len(level["openings"]) == 1 for level in plan["levels"])


def test_architecture_plan_drives_skeleton_and_component_slots() -> None:
    raw = {
        "massing": {
            "shape": "rectangle",
            "width": 12,
            "depth": 9,
            "floors": 1,
            "modeled_floors": 1,
            "floor_height": 3.2,
        },
        "spatial_plan": _two_room_raw_plan(),
    }
    plan = normalize_architecture_plan(raw, "生成一座单层住宅")
    blueprint = build_deterministic_skeleton(plan, "生成一座单层住宅")
    brief = resolve_facade_layout(blueprint, plan)

    planned_wall_ids = {
        wall["id"]
        for level in plan["spatial_plan"]["levels"]
        for wall in level["walls"]
    }
    blueprint_ids = {item["id"] for item in blueprint["geometry"]["elements"]}
    interior_slots = [
        slot for slot in brief["opening_slots"]
        if slot.get("role") == "interior_plan"
    ]

    assert planned_wall_ids <= blueprint_ids
    assert len(interior_slots) == 1
    assert interior_slots[0]["wall_id"] in planned_wall_ids
    assert brief["component_quota"]["door"]["min"] == sum(
        slot["type"] == "door" for slot in brief["opening_slots"]
    )


def test_component_quota_zero_removes_conflicting_spatial_opening() -> None:
    raw_spatial = _two_room_raw_plan()
    raw_spatial["levels"][0]["openings"].append({
        "id": "internal_window",
        "type": "window",
        "host_wall_id": "partition",
        "offset": 6,
        "width": 1.2,
        "height": 1.2,
        "sill_height": 0.9,
    })
    raw = {
        "massing": {
            "shape": "rectangle",
            "width": 12,
            "depth": 9,
            "floors": 1,
            "modeled_floors": 1,
            "floor_height": 3.2,
        },
        "spatial_plan": raw_spatial,
        "component_quota": {"window": {"min": 0, "max": 0}},
    }

    plan = normalize_architecture_plan(raw, "生成一座没有窗户的单层住宅")
    opening_types = {
        opening["type"]
        for level in plan["spatial_plan"]["levels"]
        for opening in level["openings"]
    }

    assert opening_types == {"door"}
    assert "window" not in plan["required_components"]


def test_fallback_plan_covers_every_modeled_floor() -> None:
    plan = fallback_spatial_plan(_massing(floors=2))

    assert validate_spatial_plan(plan) == []
    assert [level["elevation"] for level in plan["levels"]] == [0.0, 3.2]
    assert all(len(level["spaces"]) == 1 for level in plan["levels"])


def test_opening_quota_sampling_never_drops_approved_interior_slot() -> None:
    slots = [
        {
            "id": f"facade_{index}",
            "type": "window",
            "role": "facade",
            "wall_id": "wall_front",
            "facing": "front",
            "bay": index,
            "from": [float(index), 0.9, 0.0],
            "width": 0.8,
            "height": 1.2,
        }
        for index in range(3)
    ]
    slots.append({
        "id": "interior_window",
        "type": "window",
        "role": "interior_plan",
        "wall_id": "spatial_wall_1_partition",
        "facing": "internal",
        "bay": 0,
        "from": [2.0, 1.0, 0.0],
        "width": 0.8,
        "height": 1.2,
    })
    brief = {
        "opening_slots": slots,
        "component_quota": {"window": {"min": 2, "max": 2}},
    }

    components, stats = conform_openings_to_slots(
        [],
        brief,
        {"metal": {}, "glass": {"opacity": 0.35}},
    )

    assert stats["synthesized"] == 2
    assert any(item["parentWall"] == "spatial_wall_1_partition" for item in components)


def test_l_shape_volume_union_is_confirmable_instead_of_downgrading() -> None:
    volumes = [
        {"x": 0, "z": 0, "width": 4, "depth": 8, "start_floor": 1, "end_floor": 1},
        {"x": 4, "z": 4, "width": 6, "depth": 4, "start_floor": 1, "end_floor": 1},
    ]

    plan = deterministic_baseline_spatial_plan(
        {**_massing(), "width": 10, "depth": 8},
        volumes,
    )

    assert plan["schema_version"] == "2.0"
    assert plan["source"] == "deterministic_template"
    assert len(plan["levels"][0]["envelope_regions"]) == 3
    assert validate_spatial_plan(plan) == []
    assert "暂不支持" not in plan.get("fallback_reason", "")


def test_polygon_rooms_and_diagonal_wall_compile_to_real_wild_wall() -> None:
    raw = {
        "levels": [{
            "level": 1,
            "entrance_space_id": "lower",
            "spaces": [
                {"id": "lower", "polygon": [[0, 0], [12, 0], [0, 9]]},
                {"id": "upper", "polygon": [[12, 0], [12, 9], [0, 9]]},
            ],
            "walls": [{"id": "diagonal", "from": [12, 0], "to": [0, 9]}],
            "openings": [{
                "id": "door", "type": "door", "host_wall_id": "diagonal",
                "offset": 5, "width": 0.9, "height": 2.1,
                "connects": ["lower", "upper"],
            }],
        }],
    }
    plan = normalize_spatial_plan(raw, _massing())
    blueprint = {"geometry": {"elements": []}, "materials": {"concrete": {}}}

    apply_spatial_plan_to_blueprint(blueprint, plan)

    assert plan["source"] == "model"
    assert validate_spatial_plan(plan) == []
    assert blueprint["geometry"]["elements"][0]["from"] == [12.0, 0.0, 0.0]
    assert blueprint["geometry"]["elements"][0]["to"] == [0.0, 3.2, 9.0]


def test_curved_wall_is_preserved_for_wild_core_and_svg() -> None:
    raw = {
        "levels": [{
            "level": 1,
            "entrance_space_id": "main",
            "spaces": [{"id": "main", "bounds": [0, 0, 12, 9]}],
            "walls": [{
                "id": "curved", "kind": "exterior", "from": [12, 9], "to": [0, 9],
                "curve": {"type": "catenary", "rise": 1.2, "segments": 16},
            }],
            "openings": [],
        }],
    }
    plan = normalize_spatial_plan(raw, _massing())
    blueprint = {"geometry": {"elements": []}, "materials": {"concrete": {}}}

    apply_spatial_plan_to_blueprint(blueprint, plan)
    svg = spatial_plan_to_svg(plan)

    assert plan["source"] == "model"
    assert blueprint["geometry"]["elements"][0]["curve"]["type"] == "catenary"
    assert "polyline" in svg


def test_cross_level_elevator_shaft_rebuilds_upper_floor_with_void() -> None:
    ring = [
        [[0, 0], [4, 0], [4, 10], [0, 10]],
        [[6, 0], [10, 0], [10, 10], [6, 10]],
        [[4, 0], [6, 0], [6, 4], [4, 4]],
        [[4, 6], [6, 6], [6, 10], [4, 10]],
    ]
    raw = {
        "vertical_circulation": [{
            "id": "lift", "type": "elevator", "polygon": [[4, 4], [6, 4], [6, 6], [4, 6]],
            "serves_levels": [1, 2],
        }],
        "review_rules": {"enabled": ["elevator"], "require_elevator_from_floors": 2},
        "levels": [
            {"level": 1, "entrance_space_id": "ground", "spaces": [{"id": "ground", "bounds": [0, 0, 10, 10]}]},
            {"level": 2, "entrance_space_id": "upper", "spaces": [{"id": "upper", "polygons": ring}]},
        ],
    }
    massing = {**_massing(2), "width": 10, "depth": 10}
    plan = normalize_spatial_plan(raw, massing)
    blueprint = {
        "geometry": {"elements": [
            {"type": "floor", "id": "floor_1", "from": [0, 0, 0], "to": [10, 0, 10], "thickness": 0.2},
            {"type": "floor", "id": "floor_2", "from": [0, 3.2, 0], "to": [10, 3.2, 10], "thickness": 0.2},
        ]},
        "materials": {"concrete": {}},
    }

    result = apply_spatial_plan_to_blueprint(blueprint, plan)
    elements = blueprint["geometry"]["elements"]

    assert plan["source"] == "model"
    assert validate_spatial_plan(plan) == []
    assert evaluate_floor_plan_rules(plan)["passed"] is True
    assert result["floors_replaced"] == 1
    assert len([item for item in elements if "shaft_wall" in item.get("id", "")]) == 8
    assert "floor_2" not in {item.get("id") for item in elements}


def test_missing_required_elevator_is_repaired_before_user_review() -> None:
    plan = deterministic_baseline_spatial_plan(_massing(4), reason="auto repair")
    plan["review_rules"] = {
        "enabled": ["elevator"],
        "require_elevator_from_floors": 4,
    }
    assert evaluate_floor_plan_rules(plan)["passed"] is False

    repaired, repairs = auto_repair_floor_plan_rules(plan)
    elevator = next(
        item for item in repaired["vertical_circulation"]
        if item["type"] == "elevator"
    )

    assert repairs[0]["action"] == "add_or_extend_full_height_shaft"
    assert elevator["serves_levels"] == [1, 2, 3, 4]
    assert evaluate_floor_plan_rules(repaired)["passed"] is True
    assert validate_spatial_plan(repaired) == []
    assert all(
        any(void["type"] == "elevator_shaft" for void in level["voids"])
        for level in repaired["levels"][1:]
    )


def test_configured_review_gates_report_real_measurements() -> None:
    raw = _two_room_raw_plan()
    raw["review_rules"] = {
        "enabled": ["egress", "opening_corner", "functional_flow"],
        "max_egress_distance": 8,
        "min_opening_corner_clearance": 0.3,
        "symmetry_axis": "x",
        "required_flows": [["living", "service"]],
    }
    raw["levels"][0]["spaces"][0]["space_type"] = "living"
    raw["levels"][0]["spaces"][1]["space_type"] = "service"
    plan = normalize_spatial_plan(raw, _massing())
    plan["review_rules"]["enabled"].append("symmetry")
    report = evaluate_floor_plan_rules(plan)

    assert {item["gate"] for item in report["findings"]} == {
        "egress", "opening_corner", "functional_flow", "symmetry",
    }
    assert report["legal_review"] is False
    assert any(item["gate"] == "symmetry" and not item["passed"] for item in report["findings"])


def test_daylight_gate_uses_facade_windows_instead_of_model_claim() -> None:
    raw = {
        "review_rules": {"enabled": ["daylight"], "min_daylight_ratio": 0.1},
        "levels": [{
            "level": 1,
            "entrance_space_id": "main",
            "spaces": [{"id": "main", "space_type": "living", "bounds": [0, 0, 12, 9]}],
        }],
    }
    facades = {
        "front": {"bays": 3, "ground_pattern": ["window", "window", "window"]},
        "back": {"bays": 3, "ground_pattern": ["window", "window", "window"]},
    }

    plan = normalize_spatial_plan(raw, _massing(), facades=facades)
    daylight = next(item for item in plan["rule_review"]["findings"] if item["gate"] == "daylight")

    assert plan["source"] == "model"
    assert daylight["passed"] is True
    assert daylight["measured"] >= 0.1
