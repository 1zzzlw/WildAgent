"""把已确认 FloorPlanIR 编译为可校验的确定性主体 Blueprint。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.agent.architecture_plan import (
    _entrance_anchor,
    build_deterministic_skeleton,
    conform_balconies_to_slots,
    conform_openings_to_slots,
    conform_railings_to_slots,
    conform_roofs_to_slots,
    resolve_facade_layout,
)
from app.agent.plan2build.gates import GateReport, evaluate_body_gates
from app.agent.spatial_geometry import polygons_overlap, rectangle_polygon
from app.agent.spatial_plan import floor_cells_with_voids
from app.tools.spatial_tools import get_roof_support_bounds


class ApprovedPlanAssemblyError(ValueError):
    """已确认方案无法通过确定性主体闸门。"""

    def __init__(self, reports: list[GateReport]):
        self.reports = reports
        messages = [
            f"{report.gate} {issue.code}: {issue.message}"
            for report in reports
            for issue in report.issues
            if issue.severity == "error"
        ]
        super().__init__("；".join(messages) or "主体装配未通过")


def _synthesize_required_lights(
    blueprint: dict[str, Any],
    design_brief: dict[str, Any],
) -> int:
    """在合并校验前补齐入口壁灯，避免缺配额后再生成无语义台灯。"""

    components = blueprint.setdefault("geometry", {}).setdefault("components", [])
    limits = design_brief.get("component_quota", {}).get("light", {})
    minimum = int(limits.get("min") or 0) if isinstance(limits, dict) else 0
    existing = sum(1 for item in components if item.get("type") == "light")
    missing = max(0, minimum - existing)
    anchor = _entrance_anchor(design_brief, blueprint)
    if missing == 0 or anchor is None:
        return 0
    spread = min(1.5, max(0.8, anchor["length"] * 0.04))
    for index in range(missing):
        if missing == 1:
            lateral = 0.0
        else:
            lateral = -spread + 2 * spread * index / (missing - 1)
        along = max(0.2, min(anchor["along"] + lateral, anchor["length"] - 0.2))
        components.append({
            "type": "light",
            "id": f"light_main_entrance_{existing + index + 1:02d}",
            "position": [
                round(anchor["origin_x"] + anchor["run_x"] * along + anchor["normal_x"] * 0.35, 3),
                round(anchor["door_base_y"] + min(2.4, anchor["door_height"]), 3),
                round(anchor["origin_z"] + anchor["run_z"] * along + anchor["normal_z"] * 0.35, 3),
            ],
            "fixtureType": "bulb",
            "lightType": "point",
            "color": [1.0, 0.78, 0.56],
            "lowIntensity": 0.35,
            "highIntensity": 1.4,
            "distance": 8.0,
            "initiallyOn": True,
            "bulbRadius": 0.09,
            "material": "metal",
            "draggable": False,
        })
    return missing


def _select_approved_openings(design_brief: dict[str, Any]) -> dict[str, Any]:
    """从候选轴网槽位选出真正批准的槽位，并把选择写回契约。

    ``resolve_facade_layout`` 的 opening_slots 是“可用候选”，component_quota 才是
    设计数量。平面内门和阳台入口属于硬约束，必须优先保留；剩余立面槽位按
    楼层、朝向和轴号均匀采样。G3 后续只检查这个批准子集。
    """

    resolved = deepcopy(design_brief)
    quotas = resolved.setdefault("component_quota", {})
    raw_slots = [
        slot for slot in resolved.get("opening_slots", [])
        if isinstance(slot, dict) and slot.get("type") in {"door", "window"}
    ]
    selected: list[dict[str, Any]] = []
    facing_rank = {"front": 0, "back": 1, "left": 2, "right": 3, "internal": 4}

    for opening_type in ("door", "window"):
        candidates = sorted(
            (slot for slot in raw_slots if slot.get("type") == opening_type),
            key=lambda slot: (
                float((slot.get("from") or [0.0, 0.0, 0.0])[1]),
                facing_rank.get(str(slot.get("facing") or ""), 5),
                int(slot.get("bay") or 0),
                str(slot.get("id") or ""),
            ),
        )
        limits = quotas.get(opening_type) if isinstance(quotas.get(opening_type), dict) else {}
        required = [
            slot for slot in candidates
            if slot.get("role") in {"interior_plan", "balcony_access"}
        ]
        maximum = limits.get("max") if isinstance(limits, dict) else None
        target = len(candidates) if not isinstance(maximum, (int, float)) else int(maximum)
        target = max(len(required), min(len(candidates), max(0, target)))
        optional = [slot for slot in candidates if slot not in required]
        remaining = target - len(required)
        if remaining >= len(optional):
            sampled = optional
        elif remaining <= 0:
            sampled = []
        elif remaining == 1:
            sampled = [optional[len(optional) // 2]]
        else:
            last = len(optional) - 1
            sampled = [
                optional[round(index * last / (remaining - 1))]
                for index in range(remaining)
            ]
        approved = [*required, *sampled]
        selected.extend(approved)
        quotas[opening_type] = {
            **(limits or {}),
            "min": len(approved),
            "max": len(approved),
            "note": "ApprovedPlanAssembler 已按配额与硬约束确定批准槽位",
        }

    selected_ids = {str(slot.get("id")) for slot in selected}
    resolved["opening_slots"] = [
        slot for slot in raw_slots if str(slot.get("id")) in selected_ids
    ]
    selected_by_wall: dict[str, list[dict[str, Any]]] = {}
    for slot in resolved["opening_slots"]:
        selected_by_wall.setdefault(str(slot.get("wall_id") or ""), []).append(slot)
    for wall_id, wall_plan in (resolved.get("facade_plan") or {}).items():
        if isinstance(wall_plan, dict):
            wall_plan["slots"] = deepcopy(selected_by_wall.get(str(wall_id), []))
            wall_plan["max_openings"] = len(wall_plan["slots"])
    return resolved


def _roof_type(plan: dict[str, Any]) -> str:
    value = (plan.get("roof") or {}).get("type")
    aliases = {
        "pitched": "gable",
        "slope": "gable",
        "坡屋顶": "gable",
        "平屋顶": "flat",
    }
    value = aliases.get(str(value), str(value or "flat"))
    return value if value in {"gable", "hip", "dome", "flat", "chinese_curved", "chinese_pagoda"} else "flat"


def _synthesize_supported_roof(
    blueprint: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any] | None:
    walls = [
        item for item in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(item, dict) and item.get("type") == "wall"
    ]
    if not walls:
        return None
    bounds = get_roof_support_bounds(walls)
    roof_plan = plan.get("roof") if isinstance(plan.get("roof"), dict) else {}
    overhang = roof_plan.get("overhang", 0.6)
    try:
        overhang = max(0.0, min(2.0, float(overhang)))
    except (TypeError, ValueError):
        overhang = 0.6
    roof_type = _roof_type(plan)
    requested_height = roof_plan.get("height")
    if isinstance(requested_height, (int, float)) and not isinstance(requested_height, bool):
        height = max(0.05, float(requested_height))
    elif roof_type == "flat":
        height = 0.12
    else:
        height = max(0.8, min(bounds["span"], bounds["depth"]) * 0.18)
    return {
        "type": "roof",
        "id": "roof_main",
        "roofType": roof_type,
        "span": round(bounds["span"] + overhang * 2, 3),
        "depth": round(bounds["depth"] + overhang * 2, 3),
        "height": round(height, 3),
        "thickness": round(max(0.12, float(roof_plan.get("thickness") or 0.25)), 3),
        "position": [
            round(bounds["center_x"], 3),
            round(bounds["support_y"], 3),
            round(bounds["center_z"], 3),
        ],
        "material": "roof",
    }


def _plan_region_roofs(
    plan: dict[str, Any],
    blueprint: dict[str, Any],
) -> list[dict[str, Any]]:
    """L/U/中庭顶层按实际占用单元铺屋面，禁止用外包矩形填平凹口或中庭。"""

    spatial_plan = plan.get("spatial_plan")
    levels = spatial_plan.get("levels") if isinstance(spatial_plan, dict) else None
    if not isinstance(levels, list) or not levels:
        return []
    top_level = max(
        (item for item in levels if isinstance(item, dict)),
        key=lambda item: float(item.get("elevation") or 0),
        default=None,
    )
    if not top_level:
        return []
    regions = top_level.get("envelope_regions")
    voids = [
        item.get("polygon") for item in top_level.get("voids", [])
        if (
            isinstance(item, dict)
            and item.get("type") in {"atrium", "courtyard", "open_to_below"}
            and isinstance(item.get("polygon"), list)
        )
    ]
    shape = str((plan.get("massing") or {}).get("shape") or "rectangle")
    if shape not in {"l_shape", "u_shape", "courtyard"} and not voids:
        return []
    if not isinstance(regions, list) or (len(regions) <= 1 and not voids):
        return []
    cells = _roof_cells(regions, voids)
    roof_type = _roof_type(plan)
    support_y = float(top_level.get("elevation") or 0) + float(top_level.get("height") or 3.2)
    material_id = "roof" if "roof" in blueprint.get("materials", {}) else next(iter(blueprint.get("materials", {}) or {"concrete": {}}))
    height = 0.12 if roof_type == "flat" else 0.8
    roofs: list[dict[str, Any]] = []
    for index, cell in enumerate(cells, start=1):
        x0, z0, x1, z1 = (float(value) for value in cell)
        if x1 - x0 <= 0.05 or z1 - z0 <= 0.05:
            continue
        roofs.append({
            "type": "roof",
            "id": f"roof_region_{index:02d}",
            "roofType": roof_type,
            "span": round(x1 - x0, 3),
            "depth": round(z1 - z0, 3),
            "height": height,
            "thickness": 0.25,
            "position": [round((x0 + x1) / 2, 3), round(support_y, 3), round((z0 + z1) / 2, 3)],
            "material": material_id,
        })
    return roofs


def _roof_cells(
    regions: list[list[float]],
    voids: list[list[list[float]]],
) -> list[list[float]]:
    """顶层屋面单元：先求避开洞口的占用单元，再把相邻单元合并成整片屋面。

    网格分解（``floor_cells_with_voids`` / ``rectangle_union_cells``）会把回字
    环廊等连续区域沿分界线切碎（四臂各切成三片），再逐片铺屋面会得到 8 片屋顶
    而非自然的 4 片。合并共享整边的相邻单元后，回字环恢复为 4 个完整臂区，
    L/U/中庭等凹凸轮廓仍按占用面覆盖、不越界进洞口。
    """
    if voids:
        rects = [rectangle_polygon(region) for region in regions]
        overlaps_void = any(
            polygons_overlap(rect, polygon)
            for rect in rects
            for polygon in voids
        )
        if overlaps_void:
            return _merge_rect_cells(floor_cells_with_voids(regions, voids))
    return _merge_rect_cells(regions)


_EPS = 1e-6


def _merge_rect_cells(cells: list[list[float]]) -> list[list[float]]:
    """把共享整条边的相邻矩形单元合并成更大的矩形，减少屋面碎片。"""
    rects = [tuple(float(value) for value in cell) for cell in cells]
    changed = True
    while changed:
        changed = False
        for index in range(len(rects)):
            for other in range(index + 1, len(rects)):
                merged = _try_merge_rect(rects[index], rects[other])
                if merged is None:
                    continue
                rects[index] = merged
                rects.pop(other)
                changed = True
                break
            if changed:
                break
    return [[round(value, 3) for value in rect] for rect in rects]


def _try_merge_rect(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    """两条矩形若能拼成矩形则返回合并结果；只允许共享整边，不允许角点相接。"""
    # 同 x 范围、z 方向相邻
    if (
        abs(first[0] - second[0]) <= _EPS and abs(first[2] - second[2]) <= _EPS
        and (abs(first[3] - second[1]) <= _EPS or abs(second[3] - first[1]) <= _EPS)
    ):
        return (
            first[0],
            min(first[1], second[1]),
            first[2],
            max(first[3], second[3]),
        )
    # 同 z 范围、x 方向相邻
    if (
        abs(first[1] - second[1]) <= _EPS and abs(first[3] - second[3]) <= _EPS
        and (abs(first[2] - second[0]) <= _EPS or abs(second[2] - first[0]) <= _EPS)
    ):
        return (
            min(first[0], second[0]),
            first[1],
            max(first[2], second[2]),
            first[3],
        )
    return None


def _finalize_schema_fields(
    blueprint: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    """移除仅供规划阶段使用的标记，并补齐确定性构件的 schema 字段。"""

    geometry = blueprint.get("geometry", {})
    for component in geometry.get("components", []):
        if not isinstance(component, dict):
            continue
        component.pop("role", None)
        rail_count = component.pop("railCount", None)
        if component.get("type") == "railing" and "railLevels" not in component:
            count = max(1, min(8, int(rail_count or 2)))
            component["railLevels"] = [
                round((index + 1) / count, 3) for index in range(count)
            ]
        if component.get("type") == "railing":
            component.setdefault("material", "metal")
    for element in geometry.get("elements", []):
        if not isinstance(element, dict) or element.get("type") != "roof":
            continue
        element["roofType"] = _roof_type(plan)
        element["height"] = max(0.05, float(element.get("height") or 0.12))
        element["thickness"] = max(0.12, float(element.get("thickness") or 0.25))
        element.setdefault("material", "roof")


def assemble_approved_plan(
    architecture_plan: dict[str, Any],
    material_plan: dict[str, Any] | None,
    user_message: str = "",
    *,
    enforce_gates: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], list[GateReport], dict[str, int]]:
    """一次性装配主体；相同输入得到相同坐标和稳定 ID。"""

    plan = deepcopy(architecture_plan)
    spatial_plan = plan.get("spatial_plan")
    blueprint = build_deterministic_skeleton(plan, user_message)
    # 延迟导入：material_plan_node 依赖 nodes 包，而 nodes 包又依赖本模块，
    # 顶层导入会形成循环；运行时 nodes 包已初始化完毕。
    from app.agent.nodes.material_plan_node import apply_resolved_material_plan
    apply_resolved_material_plan(blueprint, material_plan)

    design_brief = _select_approved_openings(resolve_facade_layout(blueprint, plan))
    geometry = blueprint.setdefault("geometry", {})
    elements = geometry.setdefault("elements", [])
    components = geometry.setdefault("components", [])

    components, opening_stats = conform_openings_to_slots(
        components,
        design_brief,
        blueprint.get("materials", {}),
    )
    components, balcony_stats = conform_balconies_to_slots(components, design_brief)
    components, railing_stats = conform_railings_to_slots(components, design_brief)
    geometry["components"] = components
    light_synthesized = _synthesize_required_lights(blueprint, design_brief)
    elements, roof_slot_stats = conform_roofs_to_slots(elements, design_brief)
    if not any(item.get("type") == "roof" for item in elements if isinstance(item, dict)):
        region_roofs = _plan_region_roofs(plan, blueprint)
        if region_roofs:
            elements.extend(region_roofs)
            roof_slot_stats["synthesized"] = roof_slot_stats.get("synthesized", 0) + len(region_roofs)
        else:
            roof = _synthesize_supported_roof(blueprint, plan)
            if roof:
                elements.append(roof)
                roof_slot_stats["synthesized"] = roof_slot_stats.get("synthesized", 0) + 1

    geometry["elements"] = elements
    geometry["components"] = components
    _finalize_schema_fields(blueprint, plan)
    reports = evaluate_body_gates(spatial_plan, blueprint, design_brief)
    if enforce_gates and any(not report.passed for report in reports):
        raise ApprovedPlanAssemblyError(reports)

    stats = {
        "opening_snapped": opening_stats.get("snapped", 0),
        "opening_synthesized": opening_stats.get("synthesized", 0),
        "balcony_synthesized": balcony_stats.get("synthesized", 0),
        "railing_synthesized": railing_stats.get("synthesized", 0),
        "roof_synthesized": roof_slot_stats.get("synthesized", 0),
        "light_synthesized": light_synthesized,
    }
    return blueprint, design_brief, reports, stats
