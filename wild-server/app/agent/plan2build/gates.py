"""Plan2Build 主体阶段的统一质量闸门。

闸门只报告可定位、可复现的问题，不调用大模型，也不在这里修改 Blueprint。
确定性修复由装配器负责，避免校验器一边检查一边偷偷改变事实源。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.agent.spatial_plan import validate_spatial_plan
from app.agent.spatial_geometry import curve_points, path_length
from app.tools.spatial_tools import (
    collect_stair_placement_issues,
    get_roof_support_bounds,
)


Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class GateIssue:
    code: str
    message: str
    severity: Severity = "error"
    entity_ids: tuple[str, ...] = ()
    repairable: bool = False


@dataclass(frozen=True, slots=True)
class GateReport:
    gate: str
    name: str
    passed: bool
    issues: tuple[GateIssue, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _report(
    gate: str,
    name: str,
    issues: list[GateIssue],
    **metrics: Any,
) -> GateReport:
    return GateReport(
        gate=gate,
        name=name,
        passed=not any(issue.severity == "error" for issue in issues),
        issues=tuple(issues),
        metrics=metrics,
    )


def _elements(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    values = blueprint.get("geometry", {}).get("elements", [])
    return [item for item in values if isinstance(item, dict)]


def _components(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    values = blueprint.get("geometry", {}).get("components", [])
    return [item for item in values if isinstance(item, dict)]


def gate_g1_plan(spatial_plan: dict[str, Any] | None) -> GateReport:
    """G1：FloorPlanIR 本身必须通过几何与建筑规则检查。"""

    raw_issues = validate_spatial_plan(spatial_plan) if isinstance(spatial_plan, dict) else [
        {"code": "missing_spatial_plan", "message": "缺少可装配的 FloorPlanIR"}
    ]
    issues = [
        GateIssue(
            code=str(item.get("code") or "invalid_floor_plan"),
            message=str(item.get("message") or "平面方案无效"),
            entity_ids=tuple(
                str(value) for value in item.get("entity_ids", []) if value
            ),
        )
        for item in raw_issues
        if isinstance(item, dict)
    ]
    return _report(
        "G1",
        "平面方案契约",
        issues,
        floor_count=len((spatial_plan or {}).get("levels", [])),
    )


def gate_g2_body(blueprint: dict[str, Any]) -> GateReport:
    """G2：必须形成有墙、有楼板、ID 唯一的主体。"""

    elements = _elements(blueprint)
    walls = [item for item in elements if item.get("type") == "wall"]
    floors = [item for item in elements if item.get("type") == "floor"]
    issues: list[GateIssue] = []
    if not walls:
        issues.append(GateIssue("missing_walls", "主体装配后没有墙体"))
    if not floors:
        issues.append(GateIssue("missing_floors", "主体装配后没有楼板"))
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in [*elements, *_components(blueprint)]:
        item_id = str(item.get("id") or "")
        if not item_id:
            issues.append(GateIssue("missing_id", "构件缺少稳定 ID"))
        elif item_id in seen:
            duplicates.append(item_id)
        seen.add(item_id)
    if duplicates:
        issues.append(GateIssue(
            "duplicate_ids",
            f"存在重复构件 ID：{', '.join(sorted(set(duplicates)))}",
            entity_ids=tuple(sorted(set(duplicates))),
        ))
    return _report("G2", "主体完整性", issues, wall_count=len(walls), floor_count=len(floors))


def _wall_shape(wall: dict[str, Any]) -> tuple[float, float, float] | None:
    start = wall.get("from")
    end = wall.get("to")
    if not isinstance(start, list) or not isinstance(end, list) or len(start) < 3 or len(end) < 3:
        return None
    try:
        start_2d = [float(start[0]), float(start[2])]
        end_2d = [float(end[0]), float(end[2])]
        points = curve_points(start_2d, end_2d, wall.get("curve"))
        length = path_length(points) if points else (
            (float(end[0]) - float(start[0])) ** 2
            + (float(end[2]) - float(start[2])) ** 2
        ) ** 0.5
        bottom = min(float(start[1]), float(end[1]))
        height = abs(float(end[1]) - float(start[1]))
    except (TypeError, ValueError):
        return None
    return length, bottom, bottom + height


def gate_g3_openings(blueprint: dict[str, Any], design_brief: dict[str, Any]) -> GateReport:
    """G3：每个已批准门窗槽位都必须成为宿主墙内的真实组件。"""

    walls = {
        str(item.get("id")): item
        for item in _elements(blueprint)
        if item.get("type") == "wall" and item.get("id")
    }
    openings = [
        item for item in _components(blueprint)
        if item.get("type") in {"door", "window", "bay_window"}
    ]
    issues: list[GateIssue] = []
    by_signature: set[tuple[str, str, float, float]] = set()
    for item in openings:
        local = item.get("from")
        if not isinstance(local, list) or len(local) < 2:
            continue
        item_type = str(item.get("type") or "")
        accepted_slot_types = (
            ("bay_window", "window")
            if item_type == "bay_window"
            else (item_type,)
        )
        for slot_type in accepted_slot_types:
            by_signature.add((
                str(item.get("parentWall") or ""),
                slot_type,
                round(float(local[0]), 3),
                round(float(local[1]), 3),
            ))
    slots = [
        slot for slot in design_brief.get("opening_slots", [])
        if isinstance(slot, dict) and slot.get("type") in {"door", "window"}
    ]
    for opening in openings:
        opening_id = str(opening.get("id") or "?")
        wall_id = str(opening.get("parentWall") or "")
        wall = walls.get(wall_id)
        shape = _wall_shape(wall) if wall else None
        if shape is None:
            issues.append(GateIssue(
                "opening_host_missing",
                f"门窗 {opening_id} 的宿主墙 {wall_id or '(空)'} 不存在",
                entity_ids=(opening_id, wall_id) if wall_id else (opening_id,),
            ))
            continue
        try:
            local = opening["from"]
            left = float(local[0])
            bottom = float(local[1])
            width = float(opening["width"])
            height = float(opening["height"])
            wall_length, wall_bottom, wall_top = shape
        except (KeyError, TypeError, ValueError, IndexError):
            issues.append(GateIssue("opening_invalid_dimensions", f"门窗 {opening_id} 的尺寸或局部坐标无效", entity_ids=(opening_id,)))
            continue
        if (
            width <= 0 or height <= 0
            or left < -0.001 or left + width > wall_length + 0.001
            or bottom < wall_bottom - 0.001 or bottom + height > wall_top + 0.001
        ):
            issues.append(GateIssue("opening_outside_host", f"门窗 {opening_id} 超出宿主墙范围", entity_ids=(opening_id, wall_id)))
    for slot in slots:
        signature = (
            str(slot.get("wall_id") or ""),
            str(slot.get("type") or ""),
            round(float((slot.get("from") or [0, 0, 0])[0]), 3),
            round(float((slot.get("from") or [0, 0, 0])[1]), 3),
        )
        if signature not in by_signature:
            issues.append(GateIssue(
                "approved_opening_missing",
                f"已批准槽位 {slot.get('id', '?')} 未生成对应门窗",
                entity_ids=(str(slot.get("id") or "?"), str(slot.get("wall_id") or "?")),
                repairable=True,
            ))
    return _report("G3", "洞口与宿主关系", issues, slot_count=len(slots), opening_count=len(openings))


def gate_g4_vertical_circulation(blueprint: dict[str, Any], floor_count: int) -> GateReport:
    """G4：多层建筑必须存在覆盖相邻标高的楼梯或电梯。"""

    elements = _elements(blueprint)
    stairs = [item for item in elements if item.get("type") == "stair"]
    geometry = blueprint.get("geometry", {})
    templates = geometry.get("templates", {}) if isinstance(geometry, dict) else {}
    instances = geometry.get("instances", []) if isinstance(geometry, dict) else []
    stair_template_ids = {
        str(template_id)
        for template_id, template in (templates.items() if isinstance(templates, dict) else [])
        if isinstance(template, dict) and template.get("type") == "stair"
    }
    instanced_stairs = [
        item for item in instances
        if isinstance(item, dict) and str(item.get("ref") or "") in stair_template_ids
    ] if isinstance(instances, list) else []
    shafts = [
        item for item in elements
        if item.get("type") == "wall" and "shaft_wall" in str(item.get("id") or "")
    ]
    issues: list[GateIssue] = []
    circulation_count = len(stairs) + len(instanced_stairs)
    if floor_count > 1 and not circulation_count and not shafts:
        issues.append(GateIssue("missing_vertical_circulation", "多层建筑缺少楼梯或电梯竖向交通"))
    elif floor_count > 1 and not shafts and circulation_count < floor_count - 1:
        issues.append(GateIssue(
            "incomplete_vertical_circulation",
            f"{floor_count} 层建筑至少需要连接 {floor_count - 1} 组相邻标高，当前仅有 {circulation_count} 组楼梯",
            entity_ids=tuple(str(item.get("id") or "?") for item in [*stairs, *instanced_stairs]),
        ))
    for stair in stairs:
        try:
            if float(stair["to"][1]) <= float(stair["from"][1]):
                raise ValueError
        except (KeyError, TypeError, ValueError, IndexError):
            stair_id = str(stair.get("id") or "?")
            issues.append(GateIssue("invalid_stair_levels", f"楼梯 {stair_id} 没有连接两个递增标高", entity_ids=(stair_id,)))
    for placement_issue in collect_stair_placement_issues(blueprint):
        issues.append(GateIssue(
            str(placement_issue.get("code") or "invalid_stair_placement"),
            str(placement_issue.get("message") or "楼梯位置无效"),
            entity_ids=tuple(
                str(entity_id)
                for entity_id in placement_issue.get("entity_ids", ())
            ),
            repairable=True,
        ))
    return _report(
        "G4",
        "竖向交通连续性",
        issues,
        stair_count=len(stairs),
        stair_instance_count=len(instanced_stairs),
        shaft_wall_count=len(shafts),
    )


def gate_g5_roof(blueprint: dict[str, Any]) -> GateReport:
    """G5：屋顶必须位于最高承托墙顶，并覆盖对应顶层范围。"""

    elements = _elements(blueprint)
    walls = [item for item in elements if item.get("type") == "wall"]
    roofs = [item for item in elements if item.get("type") == "roof"]
    issues: list[GateIssue] = []
    if walls and not roofs:
        issues.append(GateIssue("missing_roof", "有围护墙体但没有屋顶", repairable=True))
    for roof in roofs:
        roof_id = str(roof.get("id") or "?")
        bounds = get_roof_support_bounds(walls, roof)
        try:
            span = float(roof.get("span"))
            depth = float(roof.get("depth"))
            position = roof.get("position")
            roof_y = float(position[1])
        except (TypeError, ValueError, IndexError):
            issues.append(GateIssue("invalid_roof_dimensions", f"屋顶 {roof_id} 的尺寸或位置无效", entity_ids=(roof_id,)))
            continue
        if span + 0.001 < bounds["span"] or depth + 0.001 < bounds["depth"]:
            issues.append(GateIssue("roof_undercoverage", f"屋顶 {roof_id} 未覆盖承托墙范围", entity_ids=(roof_id,), repairable=True))
        if abs(roof_y - bounds["support_y"]) > 0.16:
            issues.append(GateIssue("roof_support_gap", f"屋顶 {roof_id} 与承托墙顶相差 {abs(roof_y - bounds['support_y']):.2f}m", entity_ids=(roof_id,), repairable=True))
    return _report("G5", "屋顶承托与覆盖", issues, roof_count=len(roofs))


def gate_g6_references(blueprint: dict[str, Any]) -> GateReport:
    """G6：材质/父级引用必须闭合，连续幕墙还必须满足物理材质契约。"""

    materials = blueprint.get("materials", {})
    material_ids = set(materials) if isinstance(materials, dict) else set()
    entities = [*_elements(blueprint), *_components(blueprint)]
    ids = {str(item.get("id")) for item in entities if item.get("id")}
    issues: list[GateIssue] = []
    reference_fields = ("parentWall", "parentFloor", "parentRoof")
    material_fields = (
        "material", "frameMaterial", "leafMaterial", "glassMaterial",
        "supportMaterial", "railingMaterial", "capMaterial",
    )
    for item in entities:
        item_id = str(item.get("id") or "?")
        for field_name in reference_fields:
            target = item.get(field_name)
            if target and str(target) not in ids:
                issues.append(GateIssue("dangling_reference", f"{item_id}.{field_name} 引用了不存在的 {target}", entity_ids=(item_id, str(target))))
        for field_name in material_fields:
            target = item.get(field_name)
            if target and str(target) not in material_ids:
                issues.append(GateIssue("missing_material", f"{item_id}.{field_name} 引用了不存在的材质 {target}", entity_ids=(item_id,)))

    curtain_mullions = [
        item for item in _elements(blueprint)
        if str(item.get("id") or "").startswith("curtain_mullion_")
    ]
    if curtain_mullions:
        curtain_shells = [
            item for item in _elements(blueprint)
            if item.get("type") == "wall" and "_shell_" in str(item.get("id") or "")
        ]
        wrong_shells = [
            str(item.get("id") or "?")
            for item in curtain_shells
            if item.get("material") != "glass"
        ]
        wrong_mullions = [
            str(item.get("id") or "?")
            for item in curtain_mullions
            if item.get("material") != "metal"
        ]
        glass = materials.get("glass") if isinstance(materials, dict) else None
        try:
            glass_is_physical = (
                isinstance(glass, dict)
                and glass.get("materialClass") == "glass"
                and float(glass.get("transmission", 0)) > 0
                and 1.0 <= float(glass.get("ior", 0)) <= 2.5
                and float(glass.get("opacity", 1)) >= 0.99
            )
        except (TypeError, ValueError):
            glass_is_physical = False
        if wrong_shells:
            issues.append(GateIssue(
                "curtain_shell_not_glass",
                "连续幕墙壳体被覆盖为非玻璃材质",
                entity_ids=tuple(wrong_shells),
            ))
        if wrong_mullions:
            issues.append(GateIssue(
                "curtain_mullion_not_metal",
                "幕墙龙骨被覆盖为非金属材质",
                entity_ids=tuple(wrong_mullions),
            ))
        if not glass_is_physical:
            issues.append(GateIssue(
                "invalid_curtain_glass_material",
                "glass 必须使用 materialClass=glass、正 transmission 和有效 ior，且不能用低 opacity 模拟",
                entity_ids=("glass",),
            ))
    return _report("G6", "引用闭环", issues, entity_count=len(entities), material_count=len(material_ids))


def evaluate_body_gates(
    spatial_plan: dict[str, Any] | None,
    blueprint: dict[str, Any],
    design_brief: dict[str, Any],
) -> list[GateReport]:
    floor_count = len((spatial_plan or {}).get("levels", []))
    return [
        gate_g1_plan(spatial_plan),
        gate_g2_body(blueprint),
        gate_g3_openings(blueprint, design_brief),
        gate_g4_vertical_circulation(blueprint, floor_count),
        gate_g5_roof(blueprint),
        gate_g6_references(blueprint),
    ]
