"""FloorPlanIR v2 的可配置工程预审规则。

这些检查用于方案阶段尽早发现明显问题，并不替代所在地的法定施工图审查。
只有方案在 ``review_rules.enabled`` 中显式启用的规则才会成为确认闸门。
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import heapq
import math
from typing import Any

from app.agent.spatial_geometry import (
    EPSILON,
    curve_points,
    floor_cells_with_voids,
    path_length,
    polygon_area,
    polygon_centroid,
    point_in_polygon,
    polygons_overlap,
    rectangle_polygon,
)


DEFAULT_RULES: dict[str, Any] = {
    "enabled": [],
    "max_egress_distance": 30.0,
    "min_daylight_ratio": 0.10,
    "min_opening_corner_clearance": 0.30,
    "symmetry_tolerance": 0.25,
    "require_elevator_from_floors": 4,
    "required_flows": [],
}
SUPPORTED_GATES = {
    "elevator", "egress", "daylight", "symmetry", "opening_corner", "functional_flow",
}


def normalize_review_rules(raw: object, *, symmetry: bool = False) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    enabled_raw = source.get("enabled")
    enabled = [
        str(item) for item in enabled_raw
        if str(item) in SUPPORTED_GATES
    ] if isinstance(enabled_raw, list) else []
    if symmetry and "symmetry" not in enabled:
        enabled.append("symmetry")

    def positive(name: str, default: float) -> float:
        try:
            value = float(source.get(name, default))
        except (TypeError, ValueError):
            return default
        return value if math.isfinite(value) and value > 0 else default

    raw_flows = source.get("required_flows")
    flows = []
    if isinstance(raw_flows, list):
        for item in raw_flows[:24]:
            if isinstance(item, list) and 2 <= len(item) <= 8:
                flows.append([str(value)[:48] for value in item])
    return {
        "enabled": list(dict.fromkeys(enabled)),
        "max_egress_distance": positive("max_egress_distance", 30.0),
        "min_daylight_ratio": min(1.0, positive("min_daylight_ratio", 0.10)),
        "min_opening_corner_clearance": positive("min_opening_corner_clearance", 0.30),
        "symmetry_axis": str(source.get("symmetry_axis") or "x"),
        "symmetry_tolerance": positive("symmetry_tolerance", 0.25),
        "require_elevator_from_floors": max(1, int(positive("require_elevator_from_floors", 4))),
        "required_flows": flows,
    }


def _space_polygons(space: dict[str, Any]) -> list[list[list[float]]]:
    polygon = space.get("polygon")
    if isinstance(polygon, list):
        return [polygon]
    polygons = space.get("polygons")
    if isinstance(polygons, list):
        return [item for item in polygons if isinstance(item, list)]
    bounds = space.get("bounds")
    return [rectangle_polygon(bounds)] if isinstance(bounds, list) and len(bounds) == 4 else []


def _space_area(space: dict[str, Any]) -> float:
    return sum(polygon_area(polygon) for polygon in _space_polygons(space))


def _space_centroid(space: dict[str, Any]) -> tuple[float, float]:
    polygons = _space_polygons(space)
    weighted = [(polygon_centroid(polygon), polygon_area(polygon)) for polygon in polygons]
    total = sum(area for _, area in weighted)
    if total <= EPSILON:
        return 0.0, 0.0
    return (
        sum(center[0] * area for center, area in weighted) / total,
        sum(center[1] * area for center, area in weighted) / total,
    )


def _wall_length(wall: dict[str, Any]) -> float:
    points = curve_points(wall["from"], wall["to"], wall.get("curve") or {"type": "line"})
    return path_length(points)


def _finding(
    gate: str,
    passed: bool,
    message: str,
    *,
    level_id: str | None = None,
    entity_id: str | None = None,
    measured: float | None = None,
    limit: float | None = None,
) -> dict[str, Any]:
    result = {
        "gate": gate,
        "passed": passed,
        "severity": "info" if passed else "error",
        "level_id": level_id,
        "entity_id": entity_id,
        "message": message,
    }
    if measured is not None:
        result["measured"] = round(measured, 3)
    if limit is not None:
        result["limit"] = round(limit, 3)
    return result


def evaluate_floor_plan_rules(plan: dict[str, Any]) -> dict[str, Any]:
    rules = normalize_review_rules(plan.get("review_rules"))
    enabled = set(rules["enabled"])
    findings: list[dict[str, Any]] = []
    levels = [level for level in plan.get("levels", []) if isinstance(level, dict)]

    if "elevator" in enabled:
        threshold = int(rules["require_elevator_from_floors"])
        circulation = [
            item for item in plan.get("vertical_circulation", [])
            if isinstance(item, dict) and item.get("type") == "elevator"
        ]
        required = len(levels) >= threshold
        served = {
            int(value)
            for item in circulation
            for value in item.get("serves_levels", [])
            if isinstance(value, (int, float))
        }
        passed = not required or all(int(level.get("level", 0)) in served for level in levels)
        findings.append(_finding(
            "elevator", passed,
            "电梯井覆盖全部显式楼层" if passed else f"{threshold} 层及以上方案需要一个覆盖全部楼层的电梯井",
        ))

    for level in levels:
        level_id = str(level.get("id") or "unknown")
        spaces = [item for item in level.get("spaces", []) if isinstance(item, dict)]
        spaces_by_id = {str(item.get("id")): item for item in spaces if item.get("id")}
        centroids = {key: _space_centroid(value) for key, value in spaces_by_id.items()}
        adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
        outside_sources: set[str] = set()
        walls = {
            str(item.get("id")): item
            for item in level.get("walls", [])
            if isinstance(item, dict) and item.get("id")
        }
        daylight_area: dict[str, float] = defaultdict(float)
        for opening in level.get("openings", []):
            if not isinstance(opening, dict) or opening.get("type") not in {"door", "window"}:
                continue
            connects = [str(value) for value in opening.get("connects", [])]
            if len(connects) != 2:
                continue
            interior = [value for value in connects if value in spaces_by_id]
            if opening.get("type") == "window" and "outside" in connects and interior:
                daylight_area[interior[0]] += float(opening.get("width") or 0.0) * float(opening.get("height") or 0.0)
            if opening.get("type") != "door":
                continue
            if "outside" in connects and interior:
                outside_sources.add(interior[0])
            elif all(value in spaces_by_id for value in connects):
                first, second = connects
                weight = math.dist(centroids[first], centroids[second])
                adjacency[first].append((second, weight))
                adjacency[second].append((first, weight))

        # 立面轴网是外门窗的事实来源时，把每个窗投影到边界内侧并归属实际房间。
        facades = plan.get("facades") if isinstance(plan.get("facades"), dict) else {}
        if facades:
            envelope = level.get("envelope", [0, 0, 0, 0])
            ex0, ez0, ex1, ez1 = (float(value) for value in envelope)
            face_specs = {
                "front": (ex1 - ex0, lambda along: (ex0 + along, ez0 + 0.05)),
                "back": (ex1 - ex0, lambda along: (ex0 + along, ez1 - 0.05)),
                "left": (ez1 - ez0, lambda along: (ex0 + 0.05, ez0 + along)),
                "right": (ez1 - ez0, lambda along: (ex1 - 0.05, ez0 + along)),
            }
            pattern_key = "ground_pattern" if int(level.get("level") or 1) == 1 else "upper_pattern"
            for face, (wall_length, project) in face_specs.items():
                config = facades.get(face) if isinstance(facades.get(face), dict) else {}
                bays = max(1, int(config.get("bays") or 1))
                pattern = config.get(pattern_key) if isinstance(config.get(pattern_key), list) else []
                bay_width = wall_length / bays
                for index, opening_type in enumerate(pattern[:bays]):
                    if str(opening_type) != "window":
                        continue
                    width = max(0.6, min(1.8, bay_width * 0.62))
                    center = index * bay_width + bay_width / 2
                    point = project(center)
                    for space_id, space in spaces_by_id.items():
                        if any(point_in_polygon(point, polygon, include_boundary=True) for polygon in _space_polygons(space)):
                            daylight_area[space_id] += width * 1.5
                            break

        if "opening_corner" in enabled:
            clearance = float(rules["min_opening_corner_clearance"])
            for opening in level.get("openings", []):
                if not isinstance(opening, dict):
                    continue
                wall = walls.get(str(opening.get("host_wall_id") or ""))
                if wall is None:
                    continue
                length = _wall_length(wall)
                offset = float(opening.get("offset") or 0.0)
                width = float(opening.get("width") or 0.0)
                measured = min(offset, length - offset - width)
                findings.append(_finding(
                    "opening_corner", measured + EPSILON >= clearance,
                    f"洞口距墙端 {measured:.2f}m" + ("，满足预审值" if measured + EPSILON >= clearance else "，小于预审值"),
                    level_id=level_id, entity_id=str(opening.get("id") or ""), measured=measured, limit=clearance,
                ))

        if "egress" in enabled:
            max_distance = float(rules["max_egress_distance"])
            entrance = str(level.get("entrance_space_id") or "")
            sources = outside_sources or ({entrance} if entrance in spaces_by_id else set())
            distances = {space_id: math.inf for space_id in spaces_by_id}
            queue: list[tuple[float, str]] = []
            for source in sources:
                distances[source] = 0.0
                heapq.heappush(queue, (0.0, source))
            while queue:
                distance, current = heapq.heappop(queue)
                if distance > distances[current]:
                    continue
                for target, weight in adjacency[current]:
                    candidate = distance + weight
                    if candidate < distances[target]:
                        distances[target] = candidate
                        heapq.heappush(queue, (candidate, target))
            for space_id, distance in distances.items():
                passed = math.isfinite(distance) and distance <= max_distance + EPSILON
                findings.append(_finding(
                    "egress", passed,
                    f"空间 {space_id} 的近似疏散路径为 {distance:.2f}m" if math.isfinite(distance) else f"空间 {space_id} 没有通向入口/室外的疏散路径",
                    level_id=level_id, entity_id=space_id,
                    measured=distance if math.isfinite(distance) else None, limit=max_distance,
                ))

        if "daylight" in enabled:
            ratio_limit = float(rules["min_daylight_ratio"])
            exempt = {"corridor", "storage", "bathroom", "toilet", "shaft", "stair", "elevator"}
            for space_id, space in spaces_by_id.items():
                if str(space.get("space_type") or "").lower() in exempt or space.get("daylight_required") is False:
                    continue
                area = _space_area(space)
                ratio = daylight_area[space_id] / area if area > EPSILON else 0.0
                findings.append(_finding(
                    "daylight", ratio + EPSILON >= ratio_limit,
                    f"空间 {space_id} 的窗地面积比为 {ratio:.3f}",
                    level_id=level_id, entity_id=space_id, measured=ratio, limit=ratio_limit,
                ))

        if "functional_flow" in enabled:
            by_type: dict[str, list[str]] = defaultdict(list)
            for space_id, space in spaces_by_id.items():
                by_type[str(space.get("space_type") or "unspecified")].append(space_id)
            for flow in rules["required_flows"]:
                passed = True
                for first_type, second_type in zip(flow, flow[1:]):
                    if not any(
                        second in {target for target, _ in adjacency[first]}
                        for first in by_type.get(first_type, [])
                        for second in by_type.get(second_type, [])
                    ):
                        passed = False
                        break
                findings.append(_finding(
                    "functional_flow", passed,
                    f"功能流线 {' → '.join(flow)}" + ("已连通" if passed else "缺少直接门连接"),
                    level_id=level_id,
                ))

        if "symmetry" in enabled and spaces:
            axis = str(rules.get("symmetry_axis") or "x")
            envelope = level.get("envelope", [0, 0, 0, 0])
            axis_value = (float(envelope[0]) + float(envelope[2])) / 2 if axis == "x" else (float(envelope[1]) + float(envelope[3])) / 2
            tolerance = float(rules["symmetry_tolerance"])
            unmatched = []
            for space_id, space in spaces_by_id.items():
                cx, cz = centroids[space_id]
                mirrored = (2 * axis_value - cx, cz) if axis == "x" else (cx, 2 * axis_value - cz)
                area = _space_area(space)
                if not any(
                    str(other.get("space_type") or "") == str(space.get("space_type") or "")
                    and math.dist(mirrored, centroids[other_id]) <= tolerance
                    and abs(_space_area(other) - area) <= max(0.1, area * 0.03)
                    for other_id, other in spaces_by_id.items()
                ):
                    unmatched.append(space_id)
            findings.append(_finding(
                "symmetry", not unmatched,
                "空间轴线对称关系满足预审容差" if not unmatched else f"以下空间没有对称匹配: {', '.join(unmatched)}",
                level_id=level_id,
            ))

    failed = [item for item in findings if not item["passed"]]
    return {
        "profile": "generic_scheme_review",
        "legal_review": False,
        "enabled_gates": rules["enabled"],
        "passed": not failed,
        "findings": findings,
        "failed_count": len(failed),
        "notice": "仅用于方案阶段工程预审，不替代所在地法定建筑规范审查。",
    }


def rule_gate_issues(plan: dict[str, Any]) -> list[dict[str, Any]]:
    report = evaluate_floor_plan_rules(plan)
    return [
        {
            "code": f"rule_{finding['gate']}",
            "level_id": finding.get("level_id"),
            "entity_id": finding.get("entity_id"),
            "message": finding["message"],
        }
        for finding in report["findings"]
        if not finding["passed"]
    ]


def _level_regions(level: dict[str, Any]) -> list[list[float]]:
    raw_regions = level.get("envelope_regions")
    candidates = raw_regions if isinstance(raw_regions, list) else [level.get("envelope")]
    return [
        [float(value) for value in region]
        for region in candidates
        if isinstance(region, list)
        and len(region) == 4
        and float(region[2]) > float(region[0])
        and float(region[3]) > float(region[1])
    ]


def _common_level_regions(levels: list[dict[str, Any]]) -> list[list[float]]:
    """计算所有显式楼层共同拥有的轴对齐区域，供跨层井道选址。"""

    common = _level_regions(levels[0]) if levels else []
    for level in levels[1:]:
        intersections: list[list[float]] = []
        for first in common:
            for second in _level_regions(level):
                candidate = [
                    max(first[0], second[0]),
                    max(first[1], second[1]),
                    min(first[2], second[2]),
                    min(first[3], second[3]),
                ]
                if candidate[2] - candidate[0] > EPSILON and candidate[3] - candidate[1] > EPSILON:
                    intersections.append(candidate)
        common = intersections
        if not common:
            break
    return sorted(
        common,
        key=lambda region: (region[2] - region[0]) * (region[3] - region[1]),
        reverse=True,
    )


def _polygon_inside_rectangle(polygon: object, region: list[float]) -> bool:
    return (
        isinstance(polygon, list)
        and len(polygon) >= 3
        and all(
            isinstance(point, list)
            and len(point) == 2
            and region[0] - EPSILON <= float(point[0]) <= region[2] + EPSILON
            and region[1] - EPSILON <= float(point[1]) <= region[3] + EPSILON
            for point in polygon
        )
    )


def _elevator_polygon(regions: list[list[float]]) -> list[list[float]]:
    """在全层共同区域内确定性放置一个最小 1.6m、目标 2.4m 的井道。"""

    for x0, z0, x1, z1 in regions:
        width, depth = x1 - x0, z1 - z0
        margin = min(0.3, width * 0.08, depth * 0.08)
        shaft_width = min(2.4, width - margin * 2)
        shaft_depth = min(2.4, depth - margin * 2)
        if shaft_width < 1.6 or shaft_depth < 1.6:
            continue
        right = x1 - margin
        back = z1 - margin
        left = right - shaft_width
        front = back - shaft_depth
        return [
            [round(left, 3), round(front, 3)],
            [round(right, 3), round(front, 3)],
            [round(right, 3), round(back, 3)],
            [round(left, 3), round(back, 3)],
        ]
    return []


def _rectangle_bounds(polygon: object) -> list[float] | None:
    if not isinstance(polygon, list) or len(polygon) != 4:
        return None
    try:
        xs = sorted({float(point[0]) for point in polygon if isinstance(point, list) and len(point) == 2})
        zs = sorted({float(point[1]) for point in polygon if isinstance(point, list) and len(point) == 2})
    except (TypeError, ValueError):
        return None
    if len(xs) != 2 or len(zs) != 2:
        return None
    corners = {(x, z) for x in xs for z in zs}
    actual = {(float(point[0]), float(point[1])) for point in polygon}
    return [xs[0], zs[0], xs[1], zs[1]] if actual == corners else None


def _space_rectangles(space: dict[str, Any]) -> list[list[float]] | None:
    bounds = space.get("bounds")
    if isinstance(bounds, list) and len(bounds) == 4:
        return [[float(value) for value in bounds]]
    polygon = space.get("polygon")
    if isinstance(polygon, list):
        resolved = _rectangle_bounds(polygon)
        return [resolved] if resolved else None
    polygons = space.get("polygons")
    if not isinstance(polygons, list) or not polygons:
        return None
    resolved = [_rectangle_bounds(item) for item in polygons]
    return [item for item in resolved if item] if all(resolved) else None


def _carve_upper_storey_shaft(
    levels: list[dict[str, Any]],
    polygon: list[list[float]],
    first_level: int,
) -> bool:
    """从正交空间中扣除上层井道；任一受影响空间不可确定拆分时整体拒绝修复。"""

    for level in levels:
        if int(level.get("level") or 0) <= first_level:
            continue
        resolved_spaces: list[dict[str, Any]] = []
        for space in level.get("spaces", []):
            if not isinstance(space, dict):
                continue
            source_polygons = _space_polygons(space)
            overlaps = any(polygons_overlap(item, polygon) for item in source_polygons)
            if not overlaps:
                resolved_spaces.append(space)
                continue
            regions = _space_rectangles(space)
            if not regions:
                return False
            cells = [
                cell for cell in floor_cells_with_voids(regions, [polygon])
                if (cell[2] - cell[0]) * (cell[3] - cell[1]) >= 0.25
            ]
            if not cells:
                return False
            resolved = deepcopy(space)
            resolved.pop("bounds", None)
            resolved.pop("polygon", None)
            resolved["polygons"] = [rectangle_polygon(cell) for cell in cells]
            resolved_spaces.append(resolved)
        level["spaces"] = resolved_spaces
    return True


def auto_repair_floor_plan_rules(
    plan: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """修复无需用户取舍且可以重新被同一预审器验证的问题。

    当前只自动修复电梯覆盖：补建或扩展一个位于所有楼层共同轮廓内的井道，
    同时给上部楼层写入楼板 void。采光、流线和对称关系会交回平面模型自动
    重画，因为这些项目涉及功能取舍，不能用静默几何补丁猜测用户意图。
    """

    repaired = deepcopy(plan)
    report = evaluate_floor_plan_rules(repaired)
    failed_gates = {
        str(item.get("gate"))
        for item in report.get("findings", [])
        if isinstance(item, dict) and not item.get("passed")
    }
    levels = sorted(
        (level for level in repaired.get("levels", []) if isinstance(level, dict)),
        key=lambda level: int(level.get("level") or 0),
    )
    if "elevator" not in failed_gates or not levels:
        return repaired, []

    common_regions = _common_level_regions(levels)
    circulation = [
        item for item in repaired.get("vertical_circulation", [])
        if isinstance(item, dict)
    ]
    elevator = next((item for item in circulation if item.get("type") == "elevator"), None)
    polygon = (
        deepcopy(elevator.get("polygon"))
        if elevator and any(
            _polygon_inside_rectangle(elevator.get("polygon"), region)
            for region in common_regions
        )
        else _elevator_polygon(common_regions)
    )
    if not polygon:
        return repaired, []

    level_numbers = [int(level.get("level") or 0) for level in levels]
    first_level = min(level_numbers)
    if not _carve_upper_storey_shaft(levels, polygon, first_level):
        return plan, []
    elevator_id = str(elevator.get("id") or "vertical_elevator_auto") if elevator else "vertical_elevator_auto"
    resolved_elevator = {
        **(elevator or {}),
        "id": elevator_id,
        "type": "elevator",
        "name": str((elevator or {}).get("name") or "自动补全电梯"),
        "polygon": polygon,
        "serves_levels": level_numbers,
    }
    circulation = [item for item in circulation if item is not elevator]
    circulation.append(resolved_elevator)
    repaired["vertical_circulation"] = circulation

    for level in levels:
        level_number = int(level.get("level") or 0)
        void_id = f"{elevator_id}_shaft_{level_number}"
        voids = [
            item for item in level.get("voids", [])
            if isinstance(item, dict) and item.get("id") != void_id
        ]
        if level_number > first_level:
            voids.append({
                "id": void_id,
                "type": "elevator_shaft",
                "polygon": deepcopy(polygon),
            })
        level["voids"] = voids

    repaired["rule_review"] = evaluate_floor_plan_rules(repaired)
    if not repaired["rule_review"]["passed"] and any(
        not item["passed"] and item["gate"] == "elevator"
        for item in repaired["rule_review"]["findings"]
    ):
        return plan, []
    return repaired, [{
        "gate": "elevator",
        "action": "add_or_extend_full_height_shaft",
        "entity_id": elevator_id,
        "message": f"已自动补全覆盖 {len(level_numbers)} 层的电梯井",
    }]
