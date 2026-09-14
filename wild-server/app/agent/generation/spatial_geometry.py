"""建筑生成使用的通用二维几何工具。

这里故意只实现建筑生成需要的有限运算，避免把几何结果绑定到某个建筑样例。
坐标统一使用 ``[x, z]``；函数不修改传入数据。
"""

from __future__ import annotations

import math


EPSILON = 0.01
Point = tuple[float, float]

# 构造网格（米）：门窗、墙端等坐标吸附到该网格，保证视觉整齐并避免毫米级
# 契约漂移。0.1m 是常见建筑模数，足够精细且能显著减少不对齐。
CONSTRUCTION_GRID = 0.1


def snap_to_grid(value: float, step: float = CONSTRUCTION_GRID) -> float:
    """把数值吸附到构造网格（round 到 step 的整数倍）。"""
    return round(round(float(value) / step) * step, 6)
def shared_stair_layout(
    level_regions: list[list[list[float]]],
    floor_height: float,
    preferred_width: float = 1.8,
) -> dict[str, object] | None:
    """在全部楼层共同覆盖区内布置一组可交替连接的直梯端点。"""

    if not level_regions or any(not regions for regions in level_regions):
        return None
    candidates = [
        [float(value) for value in region]
        for region in level_regions[0]
        if len(region) == 4
    ]
    for regions in level_regions[1:]:
        intersections: list[list[float]] = []
        for first in candidates:
            for second in regions:
                if len(second) != 4:
                    continue
                x0 = max(first[0], float(second[0]))
                z0 = max(first[1], float(second[1]))
                x1 = min(first[2], float(second[2]))
                z1 = min(first[3], float(second[3]))
                if x1 - x0 > EPSILON and z1 - z0 > EPSILON:
                    intersections.append([x0, z0, x1, z1])
        candidates = intersections
        if not candidates:
            return None

    bounds = max(
        candidates,
        key=lambda item: (item[2] - item[0]) * (item[3] - item[1]),
    )
    span_x = bounds[2] - bounds[0]
    span_z = bounds[3] - bounds[1]
    width = min(float(preferred_width), min(span_x, span_z) - 0.4)
    if width < 0.8:
        return None
    inset = width / 2 + 0.2
    available_run = max(span_x, span_z) - inset * 2
    if available_run < 1.2:
        return None
    run = min(available_run, max(1.2, float(floor_height) * 1.65))
    center_x = (bounds[0] + bounds[2]) / 2
    center_z = (bounds[1] + bounds[3]) / 2
    if span_z >= span_x:
        start = [center_x, center_z - run / 2]
        end = [center_x, center_z + run / 2]
    else:
        start = [center_x - run / 2, center_z]
        end = [center_x + run / 2, center_z]
    return {
        "bounds": [round(value, 3) for value in bounds],
        "start": [round(value, 3) for value in start],
        "end": [round(value, 3) for value in end],
        "width": round(width, 3),
    }


def point_in_regions(point: Point, regions: list[list[float]]) -> bool:
    x, z = point
    return any(
        float(region[0]) - EPSILON <= x <= float(region[2]) + EPSILON
        and float(region[1]) - EPSILON <= z <= float(region[3]) + EPSILON
        for region in regions
    )


def curve_points(start: list[float], end: list[float], curve: object) -> list[Point]:
    """与 wild-core 的曲线求值约定保持一致。"""
    ax, az = float(start[0]), float(start[1])
    bx, bz = float(end[0]), float(end[1])
    segments = curve if isinstance(curve, list) else [curve]
    points: list[Point] = []
    for raw in segments:
        item = raw if isinstance(raw, dict) else {"type": "line"}
        kind = str(item.get("type") or "line")
        count = max(3, min(96, int(item.get("segments") or 24)))
        sx, sz = points[-1] if points else (ax, az)
        if kind == "arc":
            center = item.get("center")
            if not isinstance(center, list) or len(center) not in {2, 3}:
                return []
            cx, cz = float(center[0]), float(center[-1])
            sweep = math.radians(float(item.get("sweep") or 0.0))
            radius = math.hypot(sx - cx, sz - cz)
            start_angle = math.atan2(sz - cz, sx - cx)
            generated = [
                (cx + radius * math.cos(start_angle + sweep * index / count),
                 cz + radius * math.sin(start_angle + sweep * index / count))
                for index in range(count + 1)
            ]
        elif kind == "ellipse":
            center = item.get("center")
            if not isinstance(center, list) or len(center) not in {2, 3}:
                return []
            cx, cz = float(center[0]), float(center[-1])
            rx, rz = float(item.get("radiusX") or 0.0), float(item.get("radiusZ") or 0.0)
            start_angle = math.radians(float(item.get("startAngle") or 0.0))
            sweep = math.radians(float(item.get("sweep") if item.get("sweep") is not None else 360.0))
            generated = [
                (cx + rx * math.cos(start_angle + sweep * index / count),
                 cz + rz * math.sin(start_angle + sweep * index / count))
                for index in range(count + 1)
            ]
        elif kind == "catenary":
            length = math.hypot(bx - sx, bz - sz)
            if length <= EPSILON:
                return []
            ux, uz = (bx - sx) / length, (bz - sz) / length
            rise = float(item.get("rise") or 0.0)
            generated = [
                (sx + ux * length * ratio - uz * rise * math.sin(math.pi * ratio),
                 sz + uz * length * ratio + ux * rise * math.sin(math.pi * ratio))
                for ratio in (index / count for index in range(count + 1))
            ]
        else:
            generated = [
                (sx + (bx - sx) * index / count, sz + (bz - sz) * index / count)
                for index in range(count + 1)
            ]
        points.extend(generated if not points else generated[1:])
    compact: list[Point] = []
    for point in points:
        if not compact or math.dist(compact[-1], point) > EPSILON:
            compact.append(point)
    return compact


def path_length(points: list[Point]) -> float:
    return sum(math.dist(start, end) for start, end in zip(points, points[1:]))
