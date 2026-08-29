"""FloorPlanIR 使用的二维几何工具。

这里故意只实现平面审核需要的有限运算，避免把校验结果绑定到某个建筑样例。
坐标统一使用 ``[x, z]``；函数不修改传入数据。
"""

from __future__ import annotations

import math
from typing import Iterable


EPSILON = 0.01
Point = tuple[float, float]


def rectangle_polygon(bounds: Iterable[float]) -> list[list[float]]:
    x0, z0, x1, z1 = (float(value) for value in bounds)
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


def polygon_area(points: list[list[float]] | list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(sum(
        float(points[index][0]) * float(points[(index + 1) % len(points)][1])
        - float(points[(index + 1) % len(points)][0]) * float(points[index][1])
        for index in range(len(points))
    )) / 2.0


def polygon_centroid(points: list[list[float]] | list[Point]) -> Point:
    if not points:
        return 0.0, 0.0
    signed_twice_area = 0.0
    cx = 0.0
    cz = 0.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        cross = float(current[0]) * float(following[1]) - float(following[0]) * float(current[1])
        signed_twice_area += cross
        cx += (float(current[0]) + float(following[0])) * cross
        cz += (float(current[1]) + float(following[1])) * cross
    if abs(signed_twice_area) <= EPSILON:
        return (
            sum(float(point[0]) for point in points) / len(points),
            sum(float(point[1]) for point in points) / len(points),
        )
    return cx / (3.0 * signed_twice_area), cz / (3.0 * signed_twice_area)


def point_on_segment(point: Point, start: Point, end: Point, tolerance: float = EPSILON) -> bool:
    px, pz = point
    ax, az = start
    bx, bz = end
    cross = (px - ax) * (bz - az) - (pz - az) * (bx - ax)
    if abs(cross) > tolerance * max(1.0, math.hypot(bx - ax, bz - az)):
        return False
    return (
        min(ax, bx) - tolerance <= px <= max(ax, bx) + tolerance
        and min(az, bz) - tolerance <= pz <= max(az, bz) + tolerance
    )


def point_in_polygon(point: Point, polygon: list[list[float]], *, include_boundary: bool = True) -> bool:
    if len(polygon) < 3:
        return False
    vertices = [(float(item[0]), float(item[1])) for item in polygon]
    if include_boundary and any(
        point_on_segment(point, vertices[index], vertices[(index + 1) % len(vertices)])
        for index in range(len(vertices))
    ):
        return True
    inside = False
    px, pz = point
    previous = vertices[-1]
    for current in vertices:
        ax, az = previous
        bx, bz = current
        if (az > pz) != (bz > pz):
            crossing_x = (bx - ax) * (pz - az) / (bz - az) + ax
            if px < crossing_x:
                inside = not inside
        previous = current
    return inside


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(a: Point, b: Point, c: Point, d: Point, *, allow_touch: bool = True) -> bool:
    values = (_orientation(a, b, c), _orientation(a, b, d), _orientation(c, d, a), _orientation(c, d, b))
    if values[0] * values[1] < -EPSILON and values[2] * values[3] < -EPSILON:
        return True
    if not allow_touch:
        return False
    return (
        (abs(values[0]) <= EPSILON and point_on_segment(c, a, b))
        or (abs(values[1]) <= EPSILON and point_on_segment(d, a, b))
        or (abs(values[2]) <= EPSILON and point_on_segment(a, c, d))
        or (abs(values[3]) <= EPSILON and point_on_segment(b, c, d))
    )


def is_simple_polygon(polygon: list[list[float]]) -> bool:
    if len(polygon) < 3 or polygon_area(polygon) <= EPSILON:
        return False
    points = [(float(item[0]), float(item[1])) for item in polygon]
    count = len(points)
    for index in range(count):
        a, b = points[index], points[(index + 1) % count]
        if math.dist(a, b) <= EPSILON:
            return False
        for other in range(index + 1, count):
            if other in {index, (index + 1) % count} or (other + 1) % count == index:
                continue
            if segments_cross(a, b, points[other], points[(other + 1) % count]):
                return False
    return True


def polygons_overlap(first: list[list[float]], second: list[list[float]]) -> bool:
    """只把有正面积的交叠视为重叠；共享墙线是合法的。"""
    a = [(float(item[0]), float(item[1])) for item in first]
    b = [(float(item[0]), float(item[1])) for item in second]
    for index in range(len(a)):
        for other in range(len(b)):
            if segments_cross(
                a[index], a[(index + 1) % len(a)],
                b[other], b[(other + 1) % len(b)],
                allow_touch=False,
            ):
                return True
    return point_in_polygon(a[0], second, include_boundary=False) or point_in_polygon(
        b[0], first, include_boundary=False
    )


def rectangle_union_area(regions: list[list[float]]) -> float:
    xs = sorted({float(region[index]) for region in regions for index in (0, 2)})
    if len(xs) < 2:
        return 0.0
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        if right - left <= EPSILON:
            continue
        intervals = sorted(
            (float(region[1]), float(region[3]))
            for region in regions
            if float(region[0]) < right - EPSILON and float(region[2]) > left + EPSILON
        )
        covered = 0.0
        cursor_start = cursor_end = None
        for start, end in intervals:
            if cursor_start is None:
                cursor_start, cursor_end = start, end
            elif start <= float(cursor_end) + EPSILON:
                cursor_end = max(float(cursor_end), end)
            else:
                covered += float(cursor_end) - float(cursor_start)
                cursor_start, cursor_end = start, end
        if cursor_start is not None:
            covered += float(cursor_end) - float(cursor_start)
        area += (right - left) * covered
    return area


def rectangle_union_cells(regions: list[list[float]]) -> list[list[float]]:
    """把可能重叠的矩形并集切成互不重叠的小矩形，便于楼板和多区域空间编译。"""
    xs = sorted({float(region[index]) for region in regions for index in (0, 2)})
    zs = sorted({float(region[index]) for region in regions for index in (1, 3)})
    cells = []
    for x0, x1 in zip(xs, xs[1:]):
        for z0, z1 in zip(zs, zs[1:]):
            if x1 - x0 <= EPSILON or z1 - z0 <= EPSILON:
                continue
            center = ((x0 + x1) / 2, (z0 + z1) / 2)
            if point_in_regions(center, regions):
                cells.append([x0, z0, x1, z1])
    return cells


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


def floor_cells_with_voids(
    regions: list[list[float]],
    voids: list[list[list[float]]],
) -> list[list[float]]:
    """生成矩形楼板单元；正交洞口为精确结果，斜边洞口按顶点网格保守剔除。"""
    xs = sorted({
        *[float(region[index]) for region in regions for index in (0, 2)],
        *[float(point[0]) for polygon in voids for point in polygon],
    })
    zs = sorted({
        *[float(region[index]) for region in regions for index in (1, 3)],
        *[float(point[1]) for polygon in voids for point in polygon],
    })
    cells = []
    for x0, x1 in zip(xs, xs[1:]):
        for z0, z1 in zip(zs, zs[1:]):
            if x1 - x0 <= EPSILON or z1 - z0 <= EPSILON:
                continue
            center = ((x0 + x1) / 2, (z0 + z1) / 2)
            cell_polygon = rectangle_polygon([x0, z0, x1, z1])
            if point_in_regions(center, regions) and not any(
                polygons_overlap(cell_polygon, polygon)
                or point_in_polygon(center, polygon, include_boundary=False)
                for polygon in voids
            ):
                cells.append([x0, z0, x1, z1])
    return cells


def point_in_regions(point: Point, regions: list[list[float]]) -> bool:
    x, z = point
    return any(
        float(region[0]) - EPSILON <= x <= float(region[2]) + EPSILON
        and float(region[1]) - EPSILON <= z <= float(region[3]) + EPSILON
        for region in regions
    )


def polygon_inside_regions(polygon: list[list[float]], regions: list[list[float]]) -> bool:
    """按所有矩形分界线切分边段，检查多边形边界和内部点都在并集内。"""
    if not polygon or not regions:
        return False
    boundaries_x = {float(region[index]) for region in regions for index in (0, 2)}
    boundaries_z = {float(region[index]) for region in regions for index in (1, 3)}
    points = [(float(item[0]), float(item[1])) for item in polygon]
    for start, end in zip(points, points[1:] + points[:1]):
        parameters = {0.0, 1.0}
        dx, dz = end[0] - start[0], end[1] - start[1]
        if abs(dx) > EPSILON:
            parameters.update((value - start[0]) / dx for value in boundaries_x if 0 < (value - start[0]) / dx < 1)
        if abs(dz) > EPSILON:
            parameters.update((value - start[1]) / dz for value in boundaries_z if 0 < (value - start[1]) / dz < 1)
        ordered = sorted(parameters)
        samples = ordered + [(left + right) / 2 for left, right in zip(ordered, ordered[1:])]
        if any(not point_in_regions((start[0] + dx * t, start[1] + dz * t), regions) for t in samples):
            return False
    return point_in_regions(polygon_centroid(polygon), regions)


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


def point_at_path_offset(points: list[Point], offset: float) -> tuple[Point, Point]:
    """返回路径上的点和所在分段的单位切向量。"""
    remaining = max(0.0, offset)
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if length <= EPSILON:
            continue
        if remaining <= length:
            ratio = remaining / length
            return (
                (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio),
                ((end[0] - start[0]) / length, (end[1] - start[1]) / length),
            )
        remaining -= length
    start, end = points[-2], points[-1]
    length = max(EPSILON, math.dist(start, end))
    return end, ((end[0] - start[0]) / length, (end[1] - start[1]) / length)


def slice_path(points: list[Point], start_offset: float, end_offset: float) -> list[Point]:
    total = path_length(points)
    start_offset = max(0.0, min(total, start_offset))
    end_offset = max(start_offset, min(total, end_offset))
    start_point, _ = point_at_path_offset(points, start_offset)
    end_point, _ = point_at_path_offset(points, end_offset)
    result = [start_point]
    walked = 0.0
    for start, end in zip(points, points[1:]):
        walked += math.dist(start, end)
        if start_offset + EPSILON < walked < end_offset - EPSILON:
            result.append(end)
    if math.dist(result[-1], end_point) > EPSILON:
        result.append(end_point)
    return result
