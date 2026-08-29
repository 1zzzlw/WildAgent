"""建筑平面 IR v2：归一化、确定性校验、工程预审、SVG 与骨架编译。

平面轴固定为 X/Z，Y 只表示标高。v2 同时兼容旧版 ``bounds`` 空间，并支持
多矩形轮廓、多边形空间、斜墙、WILD 原生曲墙、跨层洞口和电梯井语义。
"""

from __future__ import annotations

from copy import deepcopy
from html import escape
import math
import re
from typing import Any

from app.agent.floor_plan_rules import (
    evaluate_floor_plan_rules,
    normalize_review_rules,
    rule_gate_issues,
)
from app.agent.spatial_geometry import (
    EPSILON,
    curve_points,
    floor_cells_with_voids,
    is_simple_polygon,
    path_length,
    point_at_path_offset,
    point_in_regions,
    point_in_polygon,
    polygon_area,
    polygon_centroid,
    polygon_inside_regions,
    polygons_overlap,
    rectangle_polygon,
    rectangle_union_area,
    rectangle_union_cells,
    slice_path,
    snap_to_grid,
)


_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_EPSILON = EPSILON


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _stable_id(prefix: str, value: object, index: int) -> str:
    raw = _ID_RE.sub("_", str(value or "")).strip("_")[:64]
    if not raw:
        raw = str(index)
    return raw if raw.startswith(f"{prefix}_") else f"{prefix}_{raw}"


def _fallback_level(
    level: int,
    envelope: list[float],
    height: float,
    envelope_regions: list[list[float]] | None = None,
) -> dict[str, Any]:
    x0, z0, x1, z1 = envelope
    regions = deepcopy(envelope_regions or [envelope])
    space_geometry = (
        {"bounds": [round(x0, 3), round(z0, 3), round(x1, 3), round(z1, 3)]}
        if len(regions) == 1
        else {"polygons": [rectangle_polygon(region) for region in regions]}
    )
    return {
        "id": f"level_{level}",
        "level": level,
        "elevation": round((level - 1) * height, 3),
        "height": round(height, 3),
        "envelope": [round(value, 3) for value in envelope],
        "envelope_regions": regions,
        "entrance_space_id": f"space_{level}_main",
        "spaces": [{
            "id": f"space_{level}_main",
            "name": "主要空间",
            "space_type": "unspecified",
            **space_geometry,
        }],
        "walls": [],
        "openings": [],
        "voids": [],
    }


def _level_regions(
    massing: dict[str, Any],
    volumes: list[dict[str, Any]] | None,
) -> dict[int, list[list[float]]]:
    """把每层活动体量转换为矩形并集；矩形可重叠，也可组成 L/U/回字形。"""

    modeled_floors = max(1, int(_number(massing.get("modeled_floors"), 1)))
    if not volumes:
        width = max(1.0, _number(massing.get("width"), 8.0))
        depth = max(1.0, _number(massing.get("depth"), 8.0))
        return {level: [[0.0, 0.0, width, depth]] for level in range(1, modeled_floors + 1)}
    result: dict[int, list[list[float]]] = {}
    for level in range(1, modeled_floors + 1):
        active = [
            item for item in volumes
            if int(item.get("start_floor", 1)) <= level <= int(item.get("end_floor", 1))
        ]
        regions = []
        for item in active:
            x0, z0 = _number(item.get("x")), _number(item.get("z"))
            x1 = x0 + max(0.0, _number(item.get("width")))
            z1 = z0 + max(0.0, _number(item.get("depth")))
            if x1 - x0 >= 0.5 and z1 - z0 >= 0.5:
                regions.append([round(x0, 3), round(z0, 3), round(x1, 3), round(z1, 3)])
        if not regions:
            width = max(1.0, _number(massing.get("width"), 8.0))
            depth = max(1.0, _number(massing.get("depth"), 8.0))
            regions = [[0.0, 0.0, width, depth]]
        result[level] = rectangle_union_cells(regions)
    return result


def _level_envelopes(
    massing: dict[str, Any],
    volumes: list[dict[str, Any]] | None,
) -> dict[int, list[float]]:
    result = {}
    for level, regions in _level_regions(massing, volumes).items():
        result[level] = [
            min(region[0] for region in regions),
            min(region[1] for region in regions),
            max(region[2] for region in regions),
            max(region[3] for region in regions),
        ]
    return result


def fallback_spatial_plan(
    massing: dict[str, Any],
    reason: str = "",
    volumes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """创建不会猜测房间关系的安全平面：每层一个未细分主要空间。"""

    height = max(2.4, _number(massing.get("floor_height"), 3.2))
    modeled_floors = max(1, int(_number(massing.get("modeled_floors"), 1)))
    regions = _level_regions(massing, volumes)
    envelopes = _level_envelopes(massing, volumes)
    plan = {
        "schema_version": "2.0",
        "source": "deterministic_fallback",
        "fallback_reason": reason or "模型未提供可验证的平面方案",
        "coordinate_system": {
            "horizontal_axes": ["x", "z"],
            "vertical_axis": "y",
            "front": "min_z",
            "north": "max_z",
            "units": "m",
        },
        "levels": [
            _fallback_level(level, envelopes[level], height, regions[level])
            for level in range(1, modeled_floors + 1)
        ],
        "vertical_spaces": [],
        "vertical_circulation": [],
        "review_rules": normalize_review_rules(None),
    }
    plan["rule_review"] = evaluate_floor_plan_rules(plan)
    return plan


def deterministic_baseline_spatial_plan(
    massing: dict[str, Any],
    volumes: list[dict[str, Any]] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """模型不可用时生成可校验的两区基础平面，避免审核流程无出口。

    这是通用占位方案，不宣称满足具体功能或建筑规范；用户仍可选择是否确认。
    """

    plan = fallback_spatial_plan(massing, reason, volumes)
    for level in plan["levels"]:
        level_number = int(level["level"])
        if len(level.get("envelope_regions", [])) > 1:
            # 组合轮廓已经由互不重叠的矩形单元表示。基础模板保留为一个连续功能区，
            # 不凭空猜测 L/U 形内部隔断，但可以审核和确认。
            continue
        x0, z0, x1, z1 = (float(value) for value in level["envelope"])
        width, depth = x1 - x0, z1 - z0
        primary_id = f"space_{level_number}_primary"
        service_id = f"space_{level_number}_service"
        wall_id = f"spatial_wall_{level_number}_baseline"
        opening_id = f"spatial_opening_{level_number}_baseline_door"
        if width >= depth and width >= 2.0:
            split = x0 + width * 0.68
            wall_from, wall_to = [split, z0], [split, z1]
            primary_bounds = [x0, z0, split, z1]
            service_bounds = [split, z0, x1, z1]
            wall_length = depth
        elif depth >= 2.0:
            split = z0 + depth * 0.68
            wall_from, wall_to = [x0, split], [x1, split]
            primary_bounds = [x0, z0, x1, split]
            service_bounds = [x0, split, x1, z1]
            wall_length = width
        else:
            return plan
        door_width = min(0.9, max(0.6, wall_length * 0.25))
        door_offset = max(0.1, (wall_length - door_width) / 2)
        level.update({
            "entrance_space_id": primary_id,
            "spaces": [
                {
                    "id": primary_id,
                    "name": "主要空间",
                    "space_type": "primary",
                    "bounds": [round(value, 3) for value in primary_bounds],
                },
                {
                    "id": service_id,
                    "name": "辅助空间",
                    "space_type": "service",
                    "bounds": [round(value, 3) for value in service_bounds],
                },
            ],
            "walls": [{
                "id": wall_id,
                "kind": "interior",
                "from": [round(value, 3) for value in wall_from],
                "to": [round(value, 3) for value in wall_to],
                "thickness": 0.12,
            }],
            "openings": [{
                "id": opening_id,
                "type": "door",
                "host_wall_id": wall_id,
                "offset": round(door_offset, 3),
                "width": round(door_width, 3),
                "height": min(2.1, round(float(level["height"]) - 0.1, 3)),
                "sill_height": 0.0,
                "connects": [primary_id, service_id],
            }],
        })
    plan["source"] = "deterministic_template"
    issues = validate_spatial_plan(plan)
    return plan if not issues else fallback_spatial_plan(massing, issues[0]["message"], volumes)


def recover_confirmable_spatial_plan(
    raw_spatial: dict[str, Any] | None,
    normalized: dict[str, Any],
    massing: dict[str, Any],
    volumes: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """把几何安全回退替换为可审核模板；保留模型明确启用的预审规则。"""

    if normalized.get("source") != "deterministic_fallback":
        return normalized, False
    requested_rules = normalize_review_rules(
        raw_spatial.get("review_rules") if isinstance(raw_spatial, dict) else None,
        # 体量对称不等于每个房间都必须镜像；只有模型明确启用的
        # 工程预审规则才有资格阻止用户确认基础平面。
        symmetry=False,
    )
    reason = str(normalized.get("fallback_reason") or "模型未返回可验证平面")
    recovered = deterministic_baseline_spatial_plan(massing, volumes, reason=reason)
    recovered["review_rules"] = requested_rules
    recovered["rule_review"] = evaluate_floor_plan_rules(recovered)
    return recovered, True


def is_confirmable_spatial_plan(
    plan: object,
    validation: list[dict[str, Any]] | None = None,
) -> bool:
    """模型细分或确定性基础模板都可确认；单空间安全轮廓不可确认。"""

    return (
        isinstance(plan, dict)
        and plan.get("source") in {"model", "deterministic_template"}
        and not (validation if validation is not None else validate_spatial_plan(plan))
    )


def normalize_spatial_plan(
    raw: object,
    massing: dict[str, Any],
    volumes: list[dict[str, Any]] | None = None,
    facades: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把模型平面压缩到 FloorPlanIR v2；结构错误仍安全回退。"""

    regions_by_level = _level_regions(massing, volumes)
    envelopes = _level_envelopes(massing, volumes)
    fallback = fallback_spatial_plan(massing, volumes=volumes)
    source = raw if isinstance(raw, dict) else {}
    raw_levels = source.get("levels")
    if not isinstance(raw_levels, list) or not raw_levels:
        return fallback

    height = float(massing["floor_height"])
    modeled_floors = int(massing["modeled_floors"])
    def normalize_polygon(value: object) -> list[list[float]]:
        if not isinstance(value, list):
            return []
        points = []
        for point in value[:96]:
            if not isinstance(point, list) or len(point) != 2:
                return []
            points.append([round(_number(point[0]), 3), round(_number(point[1]), 3)])
        return points if len(points) >= 3 else []

    vertical_spaces = []
    for index, item in enumerate(source.get("vertical_spaces", []) if isinstance(source.get("vertical_spaces"), list) else [], start=1):
        if not isinstance(item, dict):
            continue
        polygon = normalize_polygon(item.get("polygon"))
        served = sorted({
            max(1, min(modeled_floors, int(_number(value, 1))))
            for value in item.get("levels", [])
        }) if isinstance(item.get("levels"), list) else []
        kind = str(item.get("type") or "atrium")
        if polygon and served and kind in {"atrium", "courtyard", "double_height", "shaft"}:
            vertical_spaces.append({
                "id": _stable_id("vertical_space", item.get("id"), index),
                "type": kind,
                "name": str(item.get("name") or kind)[:80],
                "polygon": polygon,
                "levels": served,
            })

    vertical_circulation = []
    for index, item in enumerate(source.get("vertical_circulation", []) if isinstance(source.get("vertical_circulation"), list) else [], start=1):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "stair")
        polygon = normalize_polygon(item.get("polygon"))
        served = sorted({
            max(1, min(modeled_floors, int(_number(value, 1))))
            for value in item.get("serves_levels", [])
        }) if isinstance(item.get("serves_levels"), list) else []
        if kind in {"elevator", "stair"} and polygon and served:
            vertical_circulation.append({
                "id": _stable_id("vertical", item.get("id"), index),
                "type": kind,
                "name": str(item.get("name") or ("电梯" if kind == "elevator" else "楼梯"))[:80],
                "polygon": polygon,
                "serves_levels": served,
            })

    levels: list[dict[str, Any]] = []
    seen_levels: set[int] = set()

    for raw_level in raw_levels[:modeled_floors]:
        if not isinstance(raw_level, dict):
            continue
        level_number = max(1, min(
            modeled_floors,
            int(_number(raw_level.get("level"), len(levels) + 1)),
        ))
        if level_number in seen_levels:
            continue
        seen_levels.add(level_number)

        raw_spaces = raw_level.get("spaces")
        if not isinstance(raw_spaces, list) or not raw_spaces:
            continue
        space_id_map: dict[str, str] = {}
        spaces: list[dict[str, Any]] = []
        for index, raw_space in enumerate(raw_spaces[:48], start=1):
            if not isinstance(raw_space, dict):
                continue
            raw_id = str(raw_space.get("id") or index)
            space_id = _stable_id(f"space_{level_number}", raw_id, index)
            space_id_map[raw_id] = space_id
            bounds = raw_space.get("bounds")
            polygon = normalize_polygon(raw_space.get("polygon"))
            polygons = [
                normalized for item in raw_space.get("polygons", [])
                if (normalized := normalize_polygon(item))
            ] if isinstance(raw_space.get("polygons"), list) else []
            geometry: dict[str, Any]
            if polygon:
                geometry = {"polygon": polygon}
            elif polygons:
                geometry = {"polygons": polygons}
            elif isinstance(bounds, list) and len(bounds) == 4:
                geometry = {"bounds": [round(_number(value), 3) for value in bounds]}
            else:
                continue
            spaces.append({
                "id": space_id,
                "name": str(raw_space.get("name") or f"空间 {index}")[:80],
                "space_type": str(raw_space.get("space_type") or "unspecified")[:48],
                "daylight_required": raw_space.get("daylight_required") is not False,
                **geometry,
            })

        wall_id_map: dict[str, str] = {}
        walls: list[dict[str, Any]] = []
        raw_walls = raw_level.get("walls")
        if isinstance(raw_walls, list):
            for index, raw_wall in enumerate(raw_walls[:64], start=1):
                if not isinstance(raw_wall, dict):
                    continue
                start = raw_wall.get("from")
                end = raw_wall.get("to")
                if not isinstance(start, list) or len(start) != 2:
                    continue
                if not isinstance(end, list) or len(end) != 2:
                    continue
                raw_id = str(raw_wall.get("id") or index)
                wall_id = _stable_id(f"spatial_wall_{level_number}", raw_id, index)
                wall_id_map[raw_id] = wall_id
                wall = {
                    "id": wall_id,
                    "kind": str(raw_wall.get("kind") or "interior") if str(raw_wall.get("kind") or "interior") in {"interior", "exterior", "shaft"} else "interior",
                    "from": [round(_number(value), 3) for value in start],
                    "to": [round(_number(value), 3) for value in end],
                    "thickness": round(max(0.08, min(0.3, _number(raw_wall.get("thickness"), 0.12))), 3),
                }
                curve = raw_wall.get("curve")
                if isinstance(curve, dict) and str(curve.get("type")) in {"arc", "ellipse", "catenary", "line"}:
                    normalized_curve = deepcopy(curve)
                    if isinstance(normalized_curve.get("center"), list):
                        center = normalized_curve["center"]
                        normalized_curve["center"] = [round(_number(center[0]), 3), round(_number(center[-1]), 3)]
                    normalized_curve["segments"] = max(3, min(96, int(_number(normalized_curve.get("segments"), 24))))
                    wall["curve"] = normalized_curve
                walls.append(wall)

        openings: list[dict[str, Any]] = []
        raw_openings = raw_level.get("openings")
        if isinstance(raw_openings, list):
            for index, raw_opening in enumerate(raw_openings[:96], start=1):
                if not isinstance(raw_opening, dict):
                    continue
                opening_type = str(raw_opening.get("type") or "door").lower()
                if opening_type not in {"door", "window"}:
                    continue
                raw_host = str(raw_opening.get("host_wall_id") or "")
                connects = raw_opening.get("connects")
                normalized_connects = [
                    "outside" if str(item) == "outside" else space_id_map.get(str(item), str(item))
                    for item in connects[:2]
                ] if isinstance(connects, list) else []
                openings.append({
                    "id": _stable_id(f"spatial_opening_{level_number}", raw_opening.get("id"), index),
                    "type": opening_type,
                    "host_wall_id": wall_id_map.get(raw_host, raw_host),
                    "offset": round(_number(raw_opening.get("offset")), 3),
                    "width": round(max(0.4, min(4.0, _number(raw_opening.get("width"), 0.9))), 3),
                    "height": round(max(0.6, min(height - 0.1, _number(raw_opening.get("height"), 2.1))), 3),
                    "sill_height": round(max(0.0, _number(raw_opening.get("sill_height"))), 3),
                    "connects": normalized_connects,
                })

        raw_entrance = str(raw_level.get("entrance_space_id") or "")
        raw_voids = raw_level.get("voids") if isinstance(raw_level.get("voids"), list) else []
        voids = []
        for index, raw_void in enumerate(raw_voids, start=1):
            if not isinstance(raw_void, dict):
                continue
            polygon = normalize_polygon(raw_void.get("polygon"))
            if polygon:
                voids.append({
                    "id": _stable_id(f"void_{level_number}", raw_void.get("id"), index),
                    "type": str(raw_void.get("type") or "atrium")[:32],
                    "polygon": polygon,
                })
        for item in vertical_spaces:
            if level_number in item["levels"]:
                voids.append({"id": f"{item['id']}_{level_number}", "type": item["type"], "polygon": deepcopy(item["polygon"])})
        for item in vertical_circulation:
            if level_number in item["serves_levels"] and level_number > min(item["serves_levels"]):
                voids.append({"id": f"{item['id']}_shaft_{level_number}", "type": f"{item['type']}_shaft", "polygon": deepcopy(item["polygon"])})

        levels.append({
            "id": f"level_{level_number}",
            "level": level_number,
            "elevation": round((level_number - 1) * height, 3),
            "height": round(height, 3),
            "envelope": [round(value, 3) for value in envelopes[level_number]],
            "envelope_regions": deepcopy(regions_by_level[level_number]),
            "entrance_space_id": space_id_map.get(
                raw_entrance,
                spaces[0]["id"] if spaces else "",
            ),
            "spaces": spaces,
            "walls": walls,
            "openings": openings,
            "voids": voids,
        })

    candidate = {
        "schema_version": "2.0",
        "source": "model",
        "fallback_reason": "",
        "coordinate_system": deepcopy(fallback["coordinate_system"]),
        "levels": sorted(levels, key=lambda item: item["level"]),
        "vertical_spaces": vertical_spaces,
        "vertical_circulation": vertical_circulation,
        "review_rules": normalize_review_rules(source.get("review_rules"), symmetry=False),
        "facades": deepcopy(facades or {}),
    }
    candidate["rule_review"] = evaluate_floor_plan_rules(candidate)
    issues = validate_spatial_plan(candidate, include_rules=False)
    if issues or len(levels) != modeled_floors:
        reason = issues[0]["message"] if issues else "模型未覆盖全部显式楼层"
        return fallback_spatial_plan(massing, reason, volumes)
    return candidate


def validate_spatial_plan(
    plan: object,
    *,
    include_rules: bool = True,
) -> list[dict[str, Any]]:
    """返回稳定问题协议；几何错误和已启用规则失败都会阻止确认。"""

    issues: list[dict[str, Any]] = []
    if not isinstance(plan, dict):
        return [{"code": "plan_type", "level_id": None, "entity_id": None, "message": "平面方案必须是对象"}]
    coordinates = plan.get("coordinate_system")
    if not isinstance(coordinates, dict) or coordinates.get("horizontal_axes") != ["x", "z"]:
        issues.append({"code": "coordinate_frame", "level_id": None, "entity_id": None, "message": "平面必须使用 X/Z 水平轴"})
    levels = plan.get("levels")
    if not isinstance(levels, list) or not levels:
        issues.append({"code": "missing_levels", "level_id": None, "entity_id": None, "message": "平面缺少楼层"})
        return issues

    level_numbers = {int(_number(level.get("level"))) for level in levels if isinstance(level, dict)}
    for field, served_field in (("vertical_spaces", "levels"), ("vertical_circulation", "serves_levels")):
        seen_vertical_ids: set[str] = set()
        for item in plan.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("id") or "")
            polygon = item.get("polygon")
            served = item.get(served_field)
            if not entity_id or entity_id in seen_vertical_ids:
                issues.append({"code": "invalid_vertical_id", "level_id": None, "entity_id": entity_id or None, "message": f"{field} 存在缺失或重复 id"})
            seen_vertical_ids.add(entity_id)
            if not isinstance(polygon, list) or not is_simple_polygon(polygon):
                issues.append({"code": "invalid_vertical_polygon", "level_id": None, "entity_id": entity_id or None, "message": f"跨层实体 {entity_id} 缺少有效 polygon"})
            if not isinstance(served, list) or not served or not {int(_number(value)) for value in served} <= level_numbers:
                issues.append({"code": "invalid_vertical_levels", "level_id": None, "entity_id": entity_id or None, "message": f"跨层实体 {entity_id} 引用了不存在的楼层"})

    for level in levels:
        if not isinstance(level, dict):
            continue
        level_id = str(level.get("id") or "unknown")
        envelope = level.get("envelope")
        if not isinstance(envelope, list) or len(envelope) != 4:
            issues.append({"code": "invalid_envelope", "level_id": level_id, "entity_id": None, "message": "楼层 envelope 必须是 [x0,z0,x1,z1]"})
            continue
        ex0, ez0, ex1, ez1 = (_number(value) for value in envelope)
        if ex1 - ex0 < 1 or ez1 - ez0 < 1:
            issues.append({"code": "invalid_envelope", "level_id": level_id, "entity_id": None, "message": "楼层 envelope 尺寸无效"})
            continue

        regions = level.get("envelope_regions")
        if not isinstance(regions, list) or not regions:
            regions = [envelope]
        if any(not isinstance(region, list) or len(region) != 4 for region in regions):
            issues.append({"code": "invalid_envelope_regions", "level_id": level_id, "entity_id": None, "message": "envelope_regions 必须是矩形数组"})
            continue

        voids = [item for item in level.get("voids", []) if isinstance(item, dict)]
        void_polygons = [item.get("polygon") for item in voids if isinstance(item.get("polygon"), list)]
        for item in voids:
            polygon = item.get("polygon")
            if not isinstance(polygon, list) or not is_simple_polygon(polygon) or not polygon_inside_regions(polygon, regions):
                issues.append({"code": "invalid_void", "level_id": level_id, "entity_id": str(item.get("id") or ""), "message": f"洞口区域 {item.get('id')} 不是楼层轮廓内的有效简单多边形"})

        spaces = [item for item in level.get("spaces", []) if isinstance(item, dict)]
        raw_space_ids = [str(item.get("id")) for item in spaces if item.get("id")]
        space_ids = set(raw_space_ids)
        if len(raw_space_ids) != len(space_ids):
            issues.append({"code": "duplicate_space_id", "level_id": level_id, "entity_id": None, "message": "同一楼层存在重复空间 id"})
        def space_polygons(space: dict[str, Any]) -> list[list[list[float]]]:
            if isinstance(space.get("polygon"), list):
                return [space["polygon"]]
            if isinstance(space.get("polygons"), list):
                return [item for item in space["polygons"] if isinstance(item, list)]
            bounds = space.get("bounds")
            return [rectangle_polygon(bounds)] if isinstance(bounds, list) and len(bounds) == 4 else []

        def contains(space: dict[str, Any], point: tuple[float, float], *, boundary: bool = True) -> bool:
            return any(point_in_polygon(point, polygon, include_boundary=boundary) for polygon in space_polygons(space))

        space_area = 0.0
        for index, space in enumerate(spaces):
            entity_id = str(space.get("id") or "")
            polygons = space_polygons(space)
            if not entity_id or not polygons:
                issues.append({"code": "invalid_space", "level_id": level_id, "entity_id": entity_id or None, "message": "空间缺少 id 或 bounds/polygon/polygons 几何"})
                continue
            for polygon in polygons:
                area = polygon_area(polygon)
                space_area += area
                if not is_simple_polygon(polygon) or area < 0.25:
                    issues.append({"code": "invalid_space_polygon", "level_id": level_id, "entity_id": entity_id, "message": f"空间 {entity_id} 不是有效简单多边形"})
                if not polygon_inside_regions(polygon, regions):
                    issues.append({"code": "space_outside_envelope", "level_id": level_id, "entity_id": entity_id, "message": f"空间 {entity_id} 超出楼层组合轮廓"})
                if any(polygons_overlap(polygon, void_polygon) or point_in_polygon(polygon_centroid(polygon), void_polygon, include_boundary=False) for void_polygon in void_polygons):
                    issues.append({"code": "space_over_void", "level_id": level_id, "entity_id": entity_id, "message": f"空间 {entity_id} 覆盖了中庭或跨层洞口"})
            for other in spaces[index + 1:]:
                if any(polygons_overlap(first, second) for first in polygons for second in space_polygons(other)):
                    issues.append({"code": "space_overlap", "level_id": level_id, "entity_id": entity_id, "message": f"空间 {entity_id} 与 {other.get('id')} 重叠"})
        envelope_area = rectangle_union_area(regions) - sum(polygon_area(polygon) for polygon in void_polygons)
        if abs(space_area - envelope_area) > max(0.25, envelope_area * 0.02):
            issues.append({"code": "incomplete_space_coverage", "level_id": level_id, "entity_id": None, "message": "空间没有完整覆盖组合轮廓扣除中庭/跨层洞口后的可用面积"})

        wall_by_id: dict[str, dict[str, Any]] = {}
        for wall in (item for item in level.get("walls", []) if isinstance(item, dict)):
            entity_id = str(wall.get("id") or "")
            start, end = wall.get("from"), wall.get("to")
            if not entity_id or not isinstance(start, list) or not isinstance(end, list) or len(start) != 2 or len(end) != 2:
                issues.append({"code": "invalid_wall", "level_id": level_id, "entity_id": entity_id or None, "message": "内墙缺少 id 或二维端点"})
                continue
            if entity_id in wall_by_id:
                issues.append({"code": "duplicate_wall_id", "level_id": level_id, "entity_id": entity_id, "message": f"同一楼层存在重复内墙 id: {entity_id}"})
            points = curve_points(start, end, wall.get("curve") or {"type": "line"})
            length = path_length(points)
            if length < 0.5:
                issues.append({"code": "wall_too_short", "level_id": level_id, "entity_id": entity_id, "message": f"内墙 {entity_id} 长度小于 0.5m"})
            if not points or any(not point_in_regions(point, regions) for point in points):
                issues.append({"code": "wall_outside_envelope", "level_id": level_id, "entity_id": entity_id, "message": f"内墙 {entity_id} 超出楼层边界"})
            probe = max(0.08, float(wall.get("thickness") or 0.12))
            kind = str(wall.get("kind") or "interior")
            boundary_failed = False
            if kind == "interior":
                for first_path_point, second_path_point in zip(points, points[1:]):
                    segment_length = math.dist(first_path_point, second_path_point)
                    if segment_length <= _EPSILON:
                        continue
                    midpoint = ((first_path_point[0] + second_path_point[0]) / 2, (first_path_point[1] + second_path_point[1]) / 2)
                    tangent = ((second_path_point[0] - first_path_point[0]) / segment_length, (second_path_point[1] - first_path_point[1]) / segment_length)
                    normal = (-tangent[1], tangent[0])
                    side_sets = [
                        {str(space["id"]) for space in spaces if space.get("id") and contains(space, point, boundary=False)}
                        for point in (
                            (midpoint[0] + normal[0] * probe, midpoint[1] + normal[1] * probe),
                            (midpoint[0] - normal[0] * probe, midpoint[1] - normal[1] * probe),
                        )
                    ]
                    if not side_sets[0] or not side_sets[1]:
                        boundary_failed = True
                        break
            if boundary_failed:
                issues.append({"code": "wall_not_space_boundary", "level_id": level_id, "entity_id": entity_id, "message": f"内墙 {entity_id} 没有位于两个空间的公共边界上"})
            wall_by_id[entity_id] = wall

        adjacency: dict[str, set[str]] = {space_id: set() for space_id in space_ids}
        openings = [item for item in level.get("openings", []) if isinstance(item, dict)]
        opening_ids = [str(item.get("id")) for item in openings if item.get("id")]
        if len(opening_ids) != len(set(opening_ids)):
            issues.append({"code": "duplicate_opening_id", "level_id": level_id, "entity_id": None, "message": "同一楼层存在重复洞口 id"})
        intervals_by_wall: dict[str, list[tuple[float, float, float, float, str]]] = {}
        for opening in openings:
            entity_id = str(opening.get("id") or "")
            host_id = str(opening.get("host_wall_id") or "")
            host = wall_by_id.get(host_id)
            if host is None:
                issues.append({"code": "missing_opening_host", "level_id": level_id, "entity_id": entity_id, "message": f"洞口 {entity_id} 的宿主墙不存在"})
                continue
            points = curve_points(host["from"], host["to"], host.get("curve") or {"type": "line"})
            wall_length = path_length(points)
            offset = _number(opening.get("offset"))
            opening_width = _number(opening.get("width"))
            sill_height = _number(opening.get("sill_height"))
            opening_height = _number(opening.get("height"))
            if offset < -_EPSILON or opening_width <= 0 or offset + opening_width > wall_length + _EPSILON:
                issues.append({"code": "opening_outside_host", "level_id": level_id, "entity_id": entity_id, "message": f"洞口 {entity_id} 超出宿主墙长度"})
            if sill_height < -_EPSILON or opening_height <= 0 or sill_height + opening_height > _number(level.get("height")) + _EPSILON:
                issues.append({"code": "opening_outside_wall_height", "level_id": level_id, "entity_id": entity_id, "message": f"洞口 {entity_id} 超出本层墙高"})
            interval = (
                offset,
                offset + opening_width,
                sill_height,
                sill_height + opening_height,
                entity_id,
            )
            for existing in intervals_by_wall.setdefault(host_id, []):
                along_overlap = min(interval[1], existing[1]) - max(interval[0], existing[0])
                vertical_overlap = min(interval[3], existing[3]) - max(interval[2], existing[2])
                if along_overlap > _EPSILON and vertical_overlap > _EPSILON:
                    issues.append({"code": "opening_overlap", "level_id": level_id, "entity_id": entity_id, "message": f"洞口 {entity_id} 与 {existing[4]} 在同一宿主墙上重叠"})
            intervals_by_wall[host_id].append(interval)
            if opening.get("type") == "door":
                connects = opening.get("connects")
                if not isinstance(connects, list) or len(connects) != 2 or connects[0] == connects[1]:
                    issues.append({"code": "invalid_door_connection", "level_id": level_id, "entity_id": entity_id, "message": f"门 {entity_id} 必须连接两个不同空间"})
                    continue
                first, second = str(connects[0]), str(connects[1])
                if first != "outside" and first not in space_ids or second != "outside" and second not in space_ids:
                    issues.append({"code": "unknown_connected_space", "level_id": level_id, "entity_id": entity_id, "message": f"门 {entity_id} 引用了不存在的空间"})
                    continue
                center_distance = offset + opening_width / 2
                center, tangent = point_at_path_offset(points, center_distance)
                normal = (-tangent[1], tangent[0])
                probe = max(0.08, float(host.get("thickness") or 0.12))
                plus_side, minus_side = [
                    {str(space["id"]) for space in spaces if space.get("id") and contains(space, point, boundary=False)}
                    for point in (
                        (center[0] + normal[0] * probe, center[1] + normal[1] * probe),
                        (center[0] - normal[0] * probe, center[1] - normal[1] * probe),
                    )
                ]
                if "outside" in {first, second}:
                    interior = second if first == "outside" else first
                    position_matches = (
                        (interior in plus_side and not minus_side)
                        or (interior in minus_side and not plus_side)
                    )
                else:
                    position_matches = (
                        (first in plus_side and second in minus_side)
                        or (first in minus_side and second in plus_side)
                    )
                if not position_matches:
                    issues.append({"code": "door_connection_mismatch", "level_id": level_id, "entity_id": entity_id, "message": f"门 {entity_id} 的位置不在 connects 指定的实际两侧空间"})
                    continue
                if first != "outside" and second != "outside":
                    adjacency[first].add(second)
                    adjacency[second].add(first)

        entrance = str(level.get("entrance_space_id") or "")
        if entrance not in space_ids:
            issues.append({"code": "invalid_entrance_space", "level_id": level_id, "entity_id": entrance or None, "message": "入口空间不存在"})
        elif space_ids:
            reached = {entrance}
            frontier = [entrance]
            while frontier:
                current = frontier.pop()
                for target in adjacency[current] - reached:
                    reached.add(target)
                    frontier.append(target)
            missing = sorted(space_ids - reached)
            if missing:
                issues.append({"code": "disconnected_spaces", "level_id": level_id, "entity_id": None, "message": f"以下空间无法从入口到达: {', '.join(missing)}"})
    if include_rules:
        issues.extend(rule_gate_issues(plan))
    return issues


def apply_spatial_plan_to_blueprint(
    blueprint: dict[str, Any],
    spatial_plan: dict[str, Any] | None,
) -> dict[str, int]:
    """把批准平面中的墙、电梯井和跨层洞口确定性写入骨架。"""

    if not isinstance(spatial_plan, dict) or validate_spatial_plan(spatial_plan):
        return {"walls_added": 0, "walls_replaced": 0}
    geometry = blueprint.setdefault("geometry", {})
    elements = geometry.setdefault("elements", [])
    planned_ids = {
        str(wall["id"])
        for level in spatial_plan["levels"]
        for wall in level.get("walls", [])
    }
    existing_ids = {
        str(item.get("id"))
        for item in elements
        if isinstance(item, dict) and item.get("id") in planned_ids
    }
    elements[:] = [
        item for item in elements
        if not isinstance(item, dict) or item.get("id") not in planned_ids
    ]
    material = "wall_finish" if "wall_finish" in blueprint.get("materials", {}) else "concrete"
    floor_material = "concrete"
    floors_replaced = 0
    planned_3d_walls: list[dict[str, Any]] = []
    for level in spatial_plan["levels"]:
        base_y = float(level["elevation"])
        top_y = base_y + float(level["height"])
        for wall in level.get("walls", []):
            start, end = wall["from"], wall["to"]
            # 内墙端点是 LLM 写的二维坐标；吸附到构造网格保证视觉整齐。注意不
            # 打断相交墙段：打断会改变墙 id 或产生重复 id，破坏 G2 唯一性与
            # 洞口宿主引用，收益远低于风险。
            element = {
                "type": "wall",
                "id": wall["id"],
                "from": [snap_to_grid(float(start[0])), base_y, snap_to_grid(float(start[1]))],
                "to": [snap_to_grid(float(end[0])), top_y, snap_to_grid(float(end[1]))],
                "thickness": float(wall["thickness"]),
                "material": material,
            }
            curve = deepcopy(wall.get("curve"))
            if isinstance(curve, dict):
                center = curve.get("center")
                if isinstance(center, list) and len(center) == 2:
                    curve["center"] = [float(center[0]), base_y, float(center[1])]
                element["curve"] = curve
            planned_3d_walls.append(element)

        # 当前 WILD 没有 elevator 构件；以四周井道墙落实可编译的建筑骨架。
        for circulation in spatial_plan.get("vertical_circulation", []):
            if circulation.get("type") != "elevator" or int(level["level"]) not in circulation.get("serves_levels", []):
                continue
            polygon = circulation.get("polygon", [])
            for index, (start, end) in enumerate(zip(polygon, polygon[1:] + polygon[:1]), start=1):
                wall_id = f"{circulation['id']}_shaft_wall_{level['level']}_{index}"
                elements[:] = [item for item in elements if not isinstance(item, dict) or item.get("id") != wall_id]
                elements.append({
                    "type": "wall", "id": wall_id,
                    "from": [float(start[0]), base_y, float(start[1])],
                    "to": [float(end[0]), top_y, float(end[1])],
                    "thickness": 0.18, "material": material,
                })

        void_polygons = [
            item["polygon"] for item in level.get("voids", [])
            if isinstance(item, dict) and isinstance(item.get("polygon"), list)
        ]
        if void_polygons:
            kept = []
            for item in elements:
                if not isinstance(item, dict) or item.get("type") != "floor":
                    kept.append(item)
                    continue
                start = item.get("from")
                if not isinstance(start, list) or len(start) != 3 or abs(float(start[1]) - base_y) > _EPSILON:
                    kept.append(item)
                    continue
                floors_replaced += 1
                floor_material = str(item.get("material") or floor_material)
            elements[:] = kept
            for index, bounds in enumerate(floor_cells_with_voids(level["envelope_regions"], void_polygons), start=1):
                x0, z0, x1, z1 = bounds
                elements.append({
                    "type": "floor", "id": f"spatial_floor_{level['level']}_{index}",
                    "from": [x0, base_y, z0], "to": [x1, base_y, z1],
                    "thickness": 0.2, "material": floor_material,
                })

    # 去重：删除与平面外墙几何重合的 v1 骨架外墙，避免同一立面双墙叠加
    # （骨架壳墙 id 与平面墙 id 不同，按 footprint 判断）。
    if planned_3d_walls:
        elements[:] = [
            item for item in elements
            if not isinstance(item, dict)
            or item.get("type") != "wall"
            or not any(_walls_coincident(item, planned) for planned in planned_3d_walls)
        ]
        elements.extend(planned_3d_walls)

    result = {
        "walls_added": len(planned_ids - existing_ids),
        "walls_replaced": len(existing_ids),
    }
    if floors_replaced:
        result["floors_replaced"] = floors_replaced
    return result


def _walls_coincident(first: dict[str, Any], second: dict[str, Any], tol: float = 0.05) -> bool:
    """判断两段 3D 墙是否在同一水平线上且竖向范围重叠（视为重复墙）。"""
    try:
        f1, t1 = first["from"], first["to"]
        f2, t2 = second["from"], second["to"]
        if len(f1) != 3 or len(t1) != 3 or len(f2) != 3 or len(t2) != 3:
            return False
        dx1, dz1 = float(t1[0]) - float(f1[0]), float(t1[2]) - float(f1[2])
        dx2, dz2 = float(t2[0]) - float(f2[0]), float(t2[2]) - float(f2[2])
        along_x = (abs(dx1) >= abs(dz1)) and (abs(dx2) >= abs(dz2))
        along_z = (abs(dz1) > abs(dx1)) and (abs(dz2) > abs(dx2))
        if not along_x and not along_z:
            return False
        if along_z:
            if abs(float(f1[0]) - float(f2[0])) > tol or abs(float(t1[0]) - float(t2[0])) > tol:
                return False
            run1 = (min(float(f1[2]), float(t1[2])), max(float(f1[2]), float(t1[2])))
            run2 = (min(float(f2[2]), float(t2[2])), max(float(f2[2]), float(t2[2])))
        else:
            if abs(float(f1[2]) - float(f2[2])) > tol or abs(float(t1[2]) - float(t2[2])) > tol:
                return False
            run1 = (min(float(f1[0]), float(t1[0])), max(float(f1[0]), float(t1[0])))
            run2 = (min(float(f2[0]), float(t2[0])), max(float(f2[0]), float(t2[0])))
        y1 = (min(float(f1[1]), float(t1[1])), max(float(f1[1]), float(t1[1])))
        y2 = (min(float(f2[1]), float(t2[1])), max(float(f2[1]), float(t2[1])))
        run_overlap = min(run1[1], run2[1]) - max(run1[0], run2[0])
        y_overlap = min(y1[1], y2[1]) - max(y1[0], y2[0])
        return run_overlap > tol and y_overlap > tol
    except (TypeError, ValueError, IndexError):
        return False


def spatial_opening_slots(spatial_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """把平面洞口转换成现有组件节点使用的父墙局部槽位。"""

    if not isinstance(spatial_plan, dict) or validate_spatial_plan(spatial_plan):
        return []
    slots: list[dict[str, Any]] = []
    for level in spatial_plan["levels"]:
        elevation = float(level["elevation"])
        for opening in level.get("openings", []):
            slots.append({
                "id": opening["id"],
                "type": opening["type"],
                "role": "interior_plan",
                "wall_id": opening["host_wall_id"],
                "facing": "internal",
                "bay": 0,
                "from": [
                    float(opening["offset"]),
                    elevation + float(opening.get("sill_height", 0.0)),
                    0.0,
                ],
                "width": float(opening["width"]),
                "height": float(opening["height"]),
                "connects": deepcopy(opening.get("connects", [])),
            })
    return slots


def spatial_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    levels = plan.get("levels", []) if isinstance(plan, dict) else []
    rule_report = evaluate_floor_plan_rules(plan) if isinstance(plan, dict) else {}
    return {
        "source": plan.get("source") if isinstance(plan, dict) else None,
        "level_count": len(levels),
        "space_count": sum(len(level.get("spaces", [])) for level in levels),
        "interior_wall_count": sum(len(level.get("walls", [])) for level in levels),
        "opening_count": sum(len(level.get("openings", [])) for level in levels),
        "void_count": sum(len(level.get("voids", [])) for level in levels),
        "vertical_circulation_count": len(plan.get("vertical_circulation", [])) if isinstance(plan, dict) else 0,
        "rule_review": rule_report,
        "fallback_reason": plan.get("fallback_reason", "") if isinstance(plan, dict) else "",
    }


def _facade_openings(
    level: dict[str, Any],
    facades: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    """把已批准立面轴网投影成审核图上的外门窗，不提前生成三维构件。"""

    result: dict[str, list[dict[str, Any]]] = {
        "front": [], "back": [], "left": [], "right": [],
    }
    source = facades if isinstance(facades, dict) else {}
    level_number = int(level["level"])
    x0, z0, x1, z1 = (float(value) for value in level["envelope"])
    lengths = {"front": x1 - x0, "back": x1 - x0, "left": z1 - z0, "right": z1 - z0}
    for face, wall_length in lengths.items():
        config = source.get(face) if isinstance(source.get(face), dict) else {}
        bays = max(1, int(_number(config.get("bays"), 1)))
        pattern_key = "ground_pattern" if level_number == 1 else "upper_pattern"
        pattern = config.get(pattern_key) if isinstance(config.get(pattern_key), list) else []
        bay_width = wall_length / bays
        for index, opening_type in enumerate(pattern[:bays]):
            opening_type = str(opening_type).lower()
            if opening_type not in {"door", "window"}:
                continue
            width = min(1.2 if opening_type == "door" else 1.8, bay_width * 0.62)
            width = max(0.6, width)
            offset = index * bay_width + (bay_width - width) / 2
            result[face].append({
                "type": opening_type,
                "offset": round(offset, 3),
                "width": round(min(width, wall_length - offset), 3),
            })
    return result


def spatial_plan_to_svg(
    plan: dict[str, Any],
    level_number: int = 1,
    facades: dict[str, Any] | None = None,
) -> str:
    """从已校验 PlanIR 与立面轴网投影完整审核 SVG；不生成三维构件。"""

    issues = validate_spatial_plan(plan, include_rules=False)
    if issues:
        raise ValueError(issues[0]["message"])
    level = next(
        (item for item in plan["levels"] if int(item["level"]) == level_number),
        None,
    )
    if level is None:
        raise ValueError(f"不存在第 {level_number} 层")
    x0, z0, x1, z1 = (float(value) for value in level["envelope"])
    scale = min(24.0, 620.0 / max(x1 - x0, z1 - z0))
    margin = 56.0
    width = max(320.0, (x1 - x0) * scale + margin * 2)
    height = max(220.0, (z1 - z0) * scale + margin * 2)

    def sx(x: float) -> float:
        return margin + (x - x0) * scale

    def sy(z: float) -> float:
        return margin + (z1 - z) * scale

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" role="img" aria-label="第{level_number}层平面">',
        '<rect width="100%" height="100%" fill="#111118"/>',
        f'<text x="{margin:.1f}" y="28" fill="#e5e7eb" font-size="16">第 {level_number} 层平面（北 ↑）</text>',
        f'<g transform="translate({max(margin, width-178):.1f},18)">',
        '<line x1="0" y1="0" x2="18" y2="0" stroke="#FACC15" stroke-width="3"/><text x="23" y="4" fill="#9CA3AF" font-size="9">墙</text>',
        '<line x1="50" y1="0" x2="68" y2="0" stroke="#F87171" stroke-width="3"/><text x="73" y="4" fill="#9CA3AF" font-size="9">门</text>',
        '<line x1="100" y1="0" x2="118" y2="0" stroke="#60A5FA" stroke-width="3"/><text x="123" y="4" fill="#9CA3AF" font-size="9">窗</text>',
        '</g>',
    ]
    def polygons_for_space(space: dict[str, Any]) -> list[list[list[float]]]:
        if isinstance(space.get("polygon"), list):
            return [space["polygon"]]
        if isinstance(space.get("polygons"), list):
            return space["polygons"]
        return [rectangle_polygon(space["bounds"])]

    for space in level["spaces"]:
        polygons = polygons_for_space(space)
        for polygon in polygons:
            points = " ".join(f"{sx(float(point[0])):.2f},{sy(float(point[1])):.2f}" for point in polygon)
            lines.append(f'<polygon points="{points}" fill="#FACC15" fill-opacity="0.05" stroke="#475569" stroke-width="0.6"/>')
        cx, cz = polygon_centroid(max(polygons, key=polygon_area))
        lines.append(
            f'<text x="{sx(cx):.2f}" y="{sy(cz):.2f}" fill="#cbd5e1" font-size="11" text-anchor="middle">{escape(str(space["name"]))}</text>'
        )
    for void in level.get("voids", []):
        polygon = void.get("polygon", [])
        points = " ".join(f"{sx(float(point[0])):.2f},{sy(float(point[1])):.2f}" for point in polygon)
        cx, cz = polygon_centroid(polygon)
        lines.append(f'<polygon points="{points}" fill="#0f172a" stroke="#A78BFA" stroke-width="2" stroke-dasharray="5 3"/>')
        lines.append(f'<text x="{sx(cx):.2f}" y="{sy(cz):.2f}" fill="#C4B5FD" font-size="10" text-anchor="middle">{escape(str(void.get("type") or "跨层洞口"))}</text>')
    facade_openings = _facade_openings(level, facades)

    def append_wall_with_openings(
        start: tuple[float, float],
        end: tuple[float, float],
        openings: list[dict[str, Any]],
    ) -> None:
        wx0, wz0 = start
        wx1, wz1 = end
        length = math.hypot(wx1 - wx0, wz1 - wz0)
        ux, uz = (wx1 - wx0) / length, (wz1 - wz0) / length
        cursor = 0.0
        for opening in sorted(openings, key=lambda item: float(item["offset"])):
            offset = max(cursor, float(opening["offset"]))
            end_offset = min(length, offset + float(opening["width"]))
            if offset > cursor:
                lines.append(
                    f'<line x1="{sx(wx0+ux*cursor):.2f}" y1="{sy(wz0+uz*cursor):.2f}" x2="{sx(wx0+ux*offset):.2f}" y2="{sy(wz0+uz*offset):.2f}" stroke="#FACC15" stroke-width="3"/>'
                )
            color = "#F87171" if opening["type"] == "door" else "#60A5FA"
            lines.append(
                f'<line x1="{sx(wx0+ux*offset):.2f}" y1="{sy(wz0+uz*offset):.2f}" x2="{sx(wx0+ux*end_offset):.2f}" y2="{sy(wz0+uz*end_offset):.2f}" stroke="{color}" stroke-width="4"/>'
            )
            if opening["type"] == "window":
                nx, nz = -uz * 0.08, ux * 0.08
                lines.append(
                    f'<line x1="{sx(wx0+ux*offset+nx):.2f}" y1="{sy(wz0+uz*offset+nz):.2f}" x2="{sx(wx0+ux*end_offset+nx):.2f}" y2="{sy(wz0+uz*end_offset+nz):.2f}" stroke="{color}" stroke-width="1"/>'
                )
            cursor = end_offset
        if cursor < length:
            lines.append(
                f'<line x1="{sx(wx0+ux*cursor):.2f}" y1="{sy(wz0+uz*cursor):.2f}" x2="{sx(wx1):.2f}" y2="{sy(wz1):.2f}" stroke="#FACC15" stroke-width="3"/>'
            )

    # 从矩形并集求真实外边界，L/U 形不再画出跨越凹口的假墙。
    regions = level.get("envelope_regions", [level["envelope"]])
    boundary_segments: list[tuple[str, tuple[float, float], tuple[float, float]]] = []
    for region in regions:
        rx0, rz0, rx1, rz1 = (float(value) for value in region)
        candidates = [
            ("front", (rx0, rz0), (rx1, rz0), ((rx0 + rx1) / 2, rz0 - 0.02)),
            ("back", (rx0, rz1), (rx1, rz1), ((rx0 + rx1) / 2, rz1 + 0.02)),
            ("left", (rx0, rz0), (rx0, rz1), (rx0 - 0.02, (rz0 + rz1) / 2)),
            ("right", (rx1, rz0), (rx1, rz1), (rx1 + 0.02, (rz0 + rz1) / 2)),
        ]
        boundary_segments.extend(
            (face, start, end) for face, start, end, probe in candidates
            if not point_in_regions(probe, regions)
        )

    for face, start, end in boundary_segments:
        global_start = start[0] - x0 if face in {"front", "back"} else start[1] - z0
        segment_length = math.dist(start, end)
        segment_openings = []
        for opening in facade_openings[face]:
            opening_start = float(opening["offset"])
            opening_end = opening_start + float(opening["width"])
            clipped_start = max(global_start, opening_start)
            clipped_end = min(global_start + segment_length, opening_end)
            if clipped_end - clipped_start > _EPSILON:
                segment_openings.append({
                    **opening,
                    "offset": clipped_start - global_start,
                    "width": clipped_end - clipped_start,
                })
        append_wall_with_openings(start, end, segment_openings)
    openings_by_wall: dict[str, list[dict[str, Any]]] = {}
    for opening in level.get("openings", []):
        openings_by_wall.setdefault(str(opening["host_wall_id"]), []).append(opening)
    for wall in level.get("walls", []):
        path = curve_points(wall["from"], wall["to"], wall.get("curve") or {"type": "line"})
        length = path_length(path)
        cursor = 0.0
        for opening in sorted(openings_by_wall.get(str(wall["id"]), []), key=lambda item: item["offset"]):
            offset = float(opening["offset"])
            end_offset = offset + float(opening["width"])
            before = slice_path(path, cursor, offset)
            lines.append(f'<polyline points="{" ".join(f"{sx(x):.2f},{sy(z):.2f}" for x,z in before)}" fill="none" stroke="#FACC15" stroke-width="3"/>')
            color = "#F87171" if opening["type"] == "door" else "#60A5FA"
            opening_path = slice_path(path, offset, end_offset)
            lines.append(f'<polyline points="{" ".join(f"{sx(x):.2f},{sy(z):.2f}" for x,z in opening_path)}" fill="none" stroke="{color}" stroke-width="3"/>')
            cursor = end_offset
        after = slice_path(path, cursor, length)
        lines.append(f'<polyline points="{" ".join(f"{sx(x):.2f},{sy(z):.2f}" for x,z in after)}" fill="none" stroke="#FACC15" stroke-width="3"/>')
    scale_bar_m = min(5.0, x1 - x0)
    scale_bar_px = scale_bar_m * scale
    lines.extend([
        f'<line x1="{margin:.1f}" y1="{height-37:.1f}" x2="{margin+scale_bar_px:.1f}" y2="{height-37:.1f}" stroke="#9CA3AF" stroke-width="1.5"/>',
        f'<line x1="{margin:.1f}" y1="{height-41:.1f}" x2="{margin:.1f}" y2="{height-33:.1f}" stroke="#9CA3AF" stroke-width="1.5"/>',
        f'<line x1="{margin+scale_bar_px:.1f}" y1="{height-41:.1f}" x2="{margin+scale_bar_px:.1f}" y2="{height-33:.1f}" stroke="#9CA3AF" stroke-width="1.5"/>',
        f'<text x="{margin:.1f}" y="{height-24:.1f}" fill="#9CA3AF" font-size="9">0</text>',
        f'<text x="{margin+scale_bar_px:.1f}" y="{height-24:.1f}" fill="#9CA3AF" font-size="9" text-anchor="end">{scale_bar_m:g}m</text>',
        f'<text x="{margin:.1f}" y="{height-9:.1f}" fill="#9CA3AF" font-size="9">X 向右，Z 向北；front = min Z</text>',
        '</svg>',
    ])
    return "".join(lines)


def architecture_plan_to_svgs(plan: dict[str, Any]) -> dict[str, str]:
    """为全部显式楼层生成审核图，键为楼层号字符串。"""

    spatial_plan = plan.get("spatial_plan") if isinstance(plan, dict) else None
    if not isinstance(spatial_plan, dict):
        return {}
    facades = plan.get("facades") if isinstance(plan.get("facades"), dict) else {}
    return {
        str(level["level"]): spatial_plan_to_svg(
            spatial_plan,
            level_number=int(level["level"]),
            facades=facades,
        )
        for level in spatial_plan.get("levels", [])
        if isinstance(level, dict) and level.get("level") is not None
    }
