import json
from pathlib import Path

import jsonschema

from app.agent.architecture_plan import (
    _append_curtain_wall_grid,
    normalize_architecture_plan,
    resolve_complexity_profile,
)
from app.agent.plan2build.assembler import _plan_region_roofs, assemble_approved_plan
from app.agent.plan2build.decor_assembler import assemble_decor
from app.agent.plan2build.gates import gate_g4_vertical_circulation
from app.agent.plan2build.style_registry import style_registry
from app.agent.spatial_plan import deterministic_baseline_spatial_plan


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "app" / "utils" / "wild_schema.json"


def _approved_plan(message: str = "生成一座两层现代住宅，有门窗") -> dict:
    plan = normalize_architecture_plan({}, message)
    plan["spatial_plan"] = deterministic_baseline_spatial_plan(
        plan["massing"],
        plan["volumes"],
        "test fixture",
    )
    return plan


def _strict_schema_check(blueprint: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(blueprint, schema)


def test_approved_plan_assembler_is_repeatable_and_passes_g1_to_g6() -> None:
    plan = _approved_plan()

    first, first_brief, first_reports, _ = assemble_approved_plan(plan, None)
    second, second_brief, second_reports, _ = assemble_approved_plan(plan, None)

    assert first == second
    assert first_brief == second_brief
    assert [report.gate for report in first_reports] == ["G1", "G2", "G3", "G4", "G5", "G6", "G8"]
    assert all(report.passed for report in first_reports)
    assert all(report.passed for report in second_reports)
    assert any(item["type"] == "door" for item in first["geometry"]["components"])
    assert any(item["type"] == "window" for item in first["geometry"]["components"])
    assert any(item["type"] == "roof" for item in first["geometry"]["elements"])
    _strict_schema_check(first)


def test_detailed_residential_assembly_realizes_bay_window_quota() -> None:
    message = "生成一座现代两层别墅，立面丰富、有层次感"
    plan = normalize_architecture_plan(
        {}, message, resolve_complexity_profile(message, precision_mode=True),
    )

    blueprint, design_brief, reports, _ = assemble_approved_plan(
        plan, None, message,
    )

    bay_windows = [
        item for item in blueprint["geometry"]["components"]
        if item.get("type") == "bay_window"
    ]
    assert len(bay_windows) >= design_brief["component_quota"]["bay_window"]["min"]
    assert all(report.passed for report in reports)
    _strict_schema_check(blueprint)


def test_all_style_packages_compile_repeatably_and_pass_g7() -> None:
    body, _, _, _ = assemble_approved_plan(_approved_plan(), None)

    package_ids = {package["id"] for package in style_registry.list()}
    assert package_ids == {
        "modern", "chinese", "european",
        "glass_corporate", "high_tech", "eco_contemporary",
    }
    for package_id in sorted(package_ids):
        package = style_registry.get(package_id)
        first, first_ir, first_report = assemble_decor(body, package)
        second, second_ir, second_report = assemble_decor(body, package)

        assert first == second
        assert first_ir == second_ir
        assert first_report.passed is True
        assert second_report.passed is True
        assert first_report.gate == "G7"
        operation_types = {operation["op"] for operation in first_ir["operations"]}
        assert operation_types >= {"set_roof", "anchor", "set_material"}
        cornices = [
            item for item in first["geometry"]["components"]
            if item.get("type") == "cornice"
        ]
        if not package["decor"]["cornice"]["enabled"]:
            assert not cornices
        elif package_id in {"modern", "european"}:
            assert cornices
            for cornice in cornices:
                roof = next(
                    item for item in first["geometry"]["elements"]
                    if item.get("id") == cornice.get("parentRoof")
                )
                assert all(abs(point[0]) <= roof["span"] / 2 + 1e-6 for point in cornice["path"])
                assert all(abs(point[2]) <= roof["depth"] / 2 + 1e-6 for point in cornice["path"])
                assert all(point[1] == 0 for point in cornice["path"])
        else:
            assert cornices
            # wild-compiler 尚不支持 chinese_curved 的 parentRoof 局部依附；
            # 中式檐口必须使用世界路径，不能提交一个必然编译失败的引用。
            assert all("parentRoof" not in cornice for cornice in cornices)
        _strict_schema_check(first)


def test_style_inference_is_keyword_driven_and_has_stable_default() -> None:
    assert style_registry.infer("做成新中式庭院住宅") == "chinese"
    assert style_registry.infer("欧式古典立面") == "european"
    assert style_registry.infer("没有明确风格偏好") == "modern"
    assert style_registry.infer("高层玻璃幕墙商业综合体") == "glass_corporate"


def test_style_options_are_recommended_from_confirmed_architecture() -> None:
    plan = normalize_architecture_plan({}, "生成一个高层玻璃幕墙商业综合体")

    recommended = style_registry.recommend("生成一个高层玻璃幕墙商业综合体", plan)

    assert recommended[0]["id"] == "glass_corporate"
    assert {item["id"] for item in recommended} == {
        "glass_corporate", "high_tech", "eco_contemporary", "modern",
    }


def test_courtyard_golden_keeps_roof_out_of_central_void() -> None:
    raw_spatial = {
        "vertical_spaces": [{
            "id": "courtyard", "type": "courtyard", "name": "中庭",
            "polygon": [[4, 3], [8, 3], [8, 7], [4, 7]], "levels": [1],
        }],
        "levels": [{
            "level": 1,
            "entrance_space_id": "ring",
            "spaces": [{
                "id": "ring", "name": "环廊", "space_type": "circulation",
                "polygons": [
                    [[0, 0], [4, 0], [4, 10], [0, 10]],
                    [[8, 0], [12, 0], [12, 10], [8, 10]],
                    [[4, 0], [8, 0], [8, 3], [4, 3]],
                    [[4, 7], [8, 7], [8, 10], [4, 10]],
                ],
            }],
            "walls": [],
            "openings": [],
        }],
    }
    plan = normalize_architecture_plan({
        "massing": {
            "shape": "rectangle", "width": 12, "depth": 10,
            "floors": 1, "modeled_floors": 1, "floor_height": 3.2,
        },
        "roof": {"type": "flat"},
        "spatial_plan": raw_spatial,
    }, "生成一座带中央露天中庭的单层住宅")

    blueprint, _, reports, _ = assemble_approved_plan(plan, None)
    roofs = [item for item in blueprint["geometry"]["elements"] if item["type"] == "roof"]

    assert all(report.passed for report in reports)
    assert len(roofs) == 4
    for roof in roofs:
        x, _, z = roof["position"]
        assert not (4 < x < 8 and 3 < z < 7)
    _strict_schema_check(blueprint)


def test_six_storey_residential_golden_has_continuous_stairs_and_repeatable_body() -> None:
    message = "生成一座六层住宅，每层有基础房间、门窗和连续楼梯"
    plan = normalize_architecture_plan({
        "massing": {
            "shape": "rectangle", "width": 18, "depth": 12,
            "floors": 6, "modeled_floors": 6, "floor_height": 3.1,
        },
    }, message)
    plan["spatial_plan"] = deterministic_baseline_spatial_plan(
        plan["massing"], plan["volumes"], "six-storey golden",
    )

    first, _, first_reports, _ = assemble_approved_plan(plan, None, message)
    second, _, second_reports, _ = assemble_approved_plan(plan, None, message)
    stairs = [item for item in first["geometry"]["elements"] if item["type"] == "stair"]

    assert first == second
    assert len(stairs) == 5
    assert all(report.passed for report in first_reports)
    assert all(report.passed for report in second_reports)
    assert {round(item["from"][1], 1) for item in stairs} == {0.0, 3.1, 6.2, 9.3, 12.4}
    _strict_schema_check(first)


def test_g4_rejects_stair_endpoint_outside_upper_floor() -> None:
    blueprint = {
        "geometry": {
            "elements": [
                {
                    "id": "floor_lower", "type": "floor",
                    "from": [0, 0, 0], "to": [12, 0, 9], "thickness": 0.2,
                },
                {
                    "id": "floor_upper", "type": "floor",
                    "from": [4, 3.2, 3], "to": [12, 3.2, 9], "thickness": 0.2,
                },
                {
                    "id": "stair_1_2", "type": "stair",
                    "from": [1, 0, 1], "to": [1, 3.2, 7], "width": 1.6,
                },
            ],
            "components": [],
        },
    }

    report = gate_g4_vertical_circulation(blueprint, floor_count=2)

    assert report.passed is False
    assert "stair_end_outside_floor" in {issue.code for issue in report.issues}


def test_schematic_high_rise_accepts_instanced_storey_stairs_at_g4() -> None:
    message = "生成一座24层商业综合体"
    plan = normalize_architecture_plan({
        "massing": {
            "shape": "tower", "width": 36, "depth": 24,
            "floors": 24, "modeled_floors": 6,
            "representation_mode": "schematic", "floor_height": 3.6,
        },
        "profile": "high_rise",
    }, message)
    plan["spatial_plan"] = deterministic_baseline_spatial_plan(
        plan["massing"], plan["volumes"], "schematic high-rise golden",
    )

    blueprint, design_brief, reports, _ = assemble_approved_plan(plan, None, message)
    g4 = next(report for report in reports if report.gate == "G4")

    assert g4.passed is True
    assert g4.metrics["stair_instance_count"] == 23
    approved_windows = [
        slot for slot in design_brief["opening_slots"] if slot["type"] == "window"
    ]
    assert len(approved_windows) == design_brief["component_quota"]["window"]["max"]
    assert len(approved_windows) < 100
    assert {
        "standard_storey_stair_forward",
        "standard_storey_stair_reverse",
    }.issubset(blueprint["geometry"]["templates"])
    stair_instances = [
        item for item in blueprint["geometry"]["instances"]
        if str(item.get("ref") or "").startswith("standard_storey_stair_")
    ]
    assert all(
        previous["ref"] != current["ref"]
        for previous, current in zip(stair_instances, stair_instances[1:])
    )
    _strict_schema_check(blueprint)


def test_schematic_curtain_wall_limits_real_openings_to_representative_storeys() -> None:
    message = "生成一座24层玻璃幕墙商业综合体"
    plan = normalize_architecture_plan({
        "massing": {
            "shape": "tower", "width": 36, "depth": 24,
            "floors": 24, "modeled_floors": 6,
            "representation_mode": "schematic", "floor_height": 3.6,
        },
        "profile": "high_rise",
    }, message)
    plan["spatial_plan"] = deterministic_baseline_spatial_plan(
        plan["massing"], plan["volumes"], "curtain-wall schematic golden",
    )

    blueprint, design_brief, reports, _ = assemble_approved_plan(plan, None, message)
    openings_by_wall: dict[str, int] = {}
    for component in blueprint["geometry"]["components"]:
        if component.get("type") not in {"door", "window"}:
            continue
        wall_id = str(component["parentWall"])
        openings_by_wall[wall_id] = openings_by_wall.get(wall_id, 0) + 1
    facade_window_levels = {
        float(slot["from"][1])
        for slot in design_brief["opening_slots"]
        if slot["type"] == "window" and slot.get("facing") != "internal"
    }

    assert all(report.passed for report in reports)
    assert len(facade_window_levels) <= plan["massing"]["modeled_floors"]
    assert max(openings_by_wall.values()) <= plan["massing"]["modeled_floors"] * 6
    _strict_schema_check(blueprint)


def test_schematic_glass_complex_uses_podium_tower_and_no_facade_cutout_grid() -> None:
    message = "生成一个高层玻璃幕墙商业综合体"
    plan = normalize_architecture_plan({}, message)
    plan["component_quota"]["light"] = {"min": 2, "max": 8}

    blueprint, design_brief, reports, stats = assemble_approved_plan(plan, None, message)
    elements = blueprint["geometry"]["elements"]
    components = blueprint["geometry"]["components"]
    shells = [
        item for item in elements
        if item.get("type") == "wall" and "_shell_" in str(item.get("id"))
    ]
    mullions = [
        item for item in elements
        if item.get("type") == "beam" and str(item.get("id")).startswith("curtain_mullion_")
    ]
    lights = [item for item in components if item.get("type") == "light"]
    exterior_windows = [
        slot for slot in design_brief["opening_slots"]
        if slot.get("type") == "window" and slot.get("facing") != "internal"
    ]
    roof = next(item for item in elements if item.get("type") == "roof")

    assert all(report.passed for report in reports)
    assert plan["massing"]["shape"] == "stepped"
    assert len({float(item["from"][1]) for item in shells}) == 2
    assert {item.get("material") for item in shells} == {"glass"}
    assert mullions
    floor_height = float(plan["massing"]["floor_height"])
    shell_ranges: dict[int, tuple[float, float]] = {}
    for shell in shells:
        parts = str(shell["id"]).split("_")
        zone_index = int(parts[3])
        shell_ranges[zone_index] = (
            float(shell["from"][1]),
            float(shell["to"][1]),
        )
    horizontal_levels: dict[int, set[float]] = {}
    for mullion in mullions:
        parts = str(mullion["id"]).split("_")
        if parts[2] != "h":
            continue
        horizontal_levels.setdefault(int(parts[3]), set()).add(float(mullion["from"][1]))
    for zone_index, (base_y, top_y) in shell_ranges.items():
        expected = {
            round(base_y + floor_height * offset, 3)
            for offset in range(1, round((top_y - base_y) / floor_height) + 1)
        }
        assert horizontal_levels[zone_index] == expected
    assert not exterior_windows
    assert len(lights) == 2 == stats["light_synthesized"]
    assert all(item.get("fixtureType") == "bulb" for item in lights)
    assert roof["span"] < plan["massing"]["width"]
    assert max(item["height"] for item in elements if item.get("type") == "column") <= 45
    _strict_schema_check(blueprint)


def test_curtain_wall_grid_uses_zone_local_base_height() -> None:
    elements: list[dict] = []

    _append_curtain_wall_grid(
        elements,
        [{"side": "front", "from": [0, 0], "to": [12, 0]}],
        base_y=10,
        top_y=22,
        start_floor=3,
        end_floor=5,
        floor_height=4,
        facades={"front": {"bays": 3}},
        zone_index=2,
    )

    horizontal_y = [
        item["from"][1]
        for item in elements
        if str(item.get("id")).startswith("curtain_mullion_h_")
    ]
    assert horizontal_y == [14, 18, 22]


def test_curtain_wall_gate_rejects_opaque_shell_and_concrete_mullion() -> None:
    """G6 必须拦住“有 glass 定义、实际幕墙却没用 glass”的假通过产物。"""
    from app.agent.plan2build.gates import gate_g6_references

    blueprint = {
        "materials": {
            "glass": {"materialClass": "glass", "transmission": 0.92, "ior": 1.5},
            "wall_finish": {},
            "concrete": {},
        },
        "geometry": {
            "elements": [
                {"id": "wall_front_shell_1_1", "type": "wall", "material": "wall_finish"},
                {"id": "curtain_mullion_h_front_1", "type": "beam", "material": "concrete"},
            ],
            "components": [],
        },
    }

    report = gate_g6_references(blueprint)
    assert report.passed is False
    assert {issue.code for issue in report.issues} >= {
        "curtain_shell_not_glass",
        "curtain_mullion_not_metal",
    }


def test_detailed_glass_complex_reconciles_detail_quotas_and_terrace_railing() -> None:
    message = "生成一个高层玻璃幕墙商业综合体"
    raw = {
        "massing": {
            "shape": "stepped", "width": 42, "depth": 36,
            "floors": 30, "modeled_floors": 10,
            "representation_mode": "schematic", "floor_height": 4,
        },
        "volumes": [
            {
                "id": "podium", "x": 0, "z": 0, "width": 42, "depth": 36,
                "start_floor": 1, "end_floor": 2,
            },
            {
                "id": "glass_tower", "x": 7, "z": 6, "width": 28, "depth": 24,
                "start_floor": 3, "end_floor": 10,
            },
        ],
        "detail_packages": ["canopy", "bay_window", "railing"],
        "component_quota": {
            "roof": {"min": 1, "max": 1},
        },
        "required_components": [
            "door", "window", "roof", "canopy", "bay_window", "railing",
        ],
    }
    plan = normalize_architecture_plan(
        raw,
        message,
        resolve_complexity_profile(message, precision_mode=True),
    )

    body, design_brief, reports, stats = assemble_approved_plan(plan, None, message)
    final, _, g7 = assemble_decor(body, style_registry.get("glass_corporate"))
    entities = [
        *final["geometry"]["elements"],
        *final["geometry"]["components"],
    ]
    counts: dict[str, int] = {}
    for item in entities:
        item_type = str(item.get("type") or "")
        counts[item_type] = counts.get(item_type, 0) + 1

    assert plan["detail_packages"] == ["canopy", "railing", "light"]
    assert "balcony" not in plan["component_quota"]
    assert "bay_window" not in plan["component_quota"]
    assert all(report.passed for report in reports)
    assert g7.passed is True
    assert counts.get("roof") == 1
    assert counts.get("balcony", 0) == 0
    assert counts.get("bay_window", 0) == 0
    assert counts.get("railing") == 1
    assert counts.get("light") == 2
    assert counts.get("canopy") == 1
    assert stats["railing_synthesized"] == 1
    for item_type, limits in design_brief["component_quota"].items():
        assert counts.get(item_type, 0) >= int(limits.get("min") or 0)
        maximum = limits.get("max")
        if isinstance(maximum, (int, float)):
            assert counts.get(item_type, 0) <= int(maximum)
    _strict_schema_check(final)


def test_elevator_shaft_does_not_cut_the_weather_roof_into_fragments() -> None:
    plan = _approved_plan("生成一个高层玻璃幕墙商业综合体")
    plan["massing"]["shape"] = "stepped"
    top_level = plan["spatial_plan"]["levels"][-1]
    top_level["envelope_regions"] = [[0, 0, 18, 12], [18, 0, 18.3, 12]]
    top_level["voids"] = [{
        "id": "lift_shaft", "type": "elevator_shaft",
        "polygon": [[8, 5], [10, 5], [10, 7], [8, 7]],
    }]

    assert _plan_region_roofs(plan, {"geometry": {"elements": []}}) == []
