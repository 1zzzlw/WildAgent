"""确定性成墙：从空间公共边界推导内墙，并把模型墙吸附到真实公共边界。

这是"让模型负责房间与空间关系、程序负责墙坐标"的核心。模型输出的墙坐标
即使与空间边界有偏差，也会被吸附到最近的公共边界，从根源上消除：
- 墙体没有落在空间边界；
- 两个房间重叠但墙体正常；
- 门引用了错误墙体；
- 墙体存在但两侧房间不正确；
- 同一条分隔墙被模型生成两次。
"""

from __future__ import annotations

import math
from typing import Any

from app.agent.spatial_geometry import EPSILON, point_on_segment, rectangle_polygon, snap_to_grid


def space_polygons(space: dict[str, Any]) -> list[list[list[float]]]:
    """提取空间的 2D 多边形（polygon / polygons / bounds 三种表达统一）。"""
    if isinstance(space.get("polygon"), list):
        return [space["polygon"]]
    if isinstance(space.get("polygons"), list):
        return [item for item in space["polygons"] if isinstance(item, list)]
    bounds = space.get("bounds")
    return [rectangle_polygon(bounds)] if isinstance(bounds, list) and len(bounds) == 4 else []


def _segment_key(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float, float, float]:
    """归一化线段键：端点排序后作为唯一标识（用于去重同一条分隔墙）。"""
    ax, az = round(a[0], 3), round(a[1], 3)
    bx, bz = round(b[0], 3), round(b[1], 3)
    return (min(ax, bx), min(az, bz), max(ax, bx), max(az, bz))

def _edge_overlap_with_polygons(
    a: tuple[float, float],
    b: tuple[float, float],
    polygons: list[list[list[float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """边 ab 与多边形集合的重叠区间（轴对齐边）。沿边采样聚类。"""
    length = math.dist(a, b)
    if length <= EPSILON:
        return []
    samples = 40
    overlap_points: list[float] = []
    for sample in range(samples + 1):
        t = sample / samples
        px = a[0] + (b[0] - a[0]) * t
        pz = a[1] + (b[1] - a[1]) * t
        if _point_near_polygon_edge((px, pz), polygons):
            overlap_points.append(t)
    if not overlap_points:
        return []
    intervals: list[tuple[float, float]] = []
    start_t = prev_t = overlap_points[0]
    for t in overlap_points[1:]:
        if t - prev_t <= 2.5 / samples:
            prev_t = t
        else:
            intervals.append((start_t, prev_t))
            start_t = prev_t = t
    intervals.append((start_t, prev_t))
    result: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for (t0, t1) in intervals:
        if t1 - t0 < 0.15 / length:
            continue
        a2 = (round(a[0] + (b[0] - a[0]) * t0, 3), round(a[1] + (b[1] - a[1]) * t0, 3))
        b2 = (round(a[0] + (b[0] - a[0]) * t1, 3), round(a[1] + (b[1] - a[1]) * t1, 3))
        result.append((a2, b2))
    return result


def _point_near_polygon_edge(point: tuple[float, float], polygons: list[list[list[float]]]) -> bool:
    """点是否接近任一多边形边界（在边 ±EPSILON 内）。"""
    probe = EPSILON
    for poly in polygons:
        count = len(poly)
        for index in range(count):
            c_raw, d_raw = poly[index], poly[(index + 1) % count]
            if len(c_raw) < 2 or len(d_raw) < 2:
                continue
            c = (float(c_raw[0]), float(c_raw[1]))
            d = (float(d_raw[0]), float(d_raw[1]))
            if point_on_segment(point, c, d, tolerance=probe):
                return True
    return False

def shared_boundary_segments(
    first_polygons: list[list[list[float]]],
    second_polygons: list[list[list[float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """返回两个空间多边形集合之间的公共边界线段（重叠边）。"""
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    seen: set[tuple[float, float, float, float]] = set()

    def add_segment(a: tuple[float, float], b: tuple[float, float]) -> None:
        key = _segment_key(a, b)
        if key in seen:
            return
        if math.dist(a, b) < 0.15:
            return
        seen.add(key)
        segments.append((a, b))

    for poly in first_polygons:
        count = len(poly)
        for index in range(count):
            a_raw, b_raw = poly[index], poly[(index + 1) % count]
            if len(a_raw) < 2 or len(b_raw) < 2:
                continue
            a = (float(a_raw[0]), float(a_raw[1]))
            b = (float(b_raw[0]), float(b_raw[1]))
            axis_aligned = abs(a[0] - b[0]) <= EPSILON or abs(a[1] - b[1]) <= EPSILON
            if not axis_aligned:
                continue
            overlaps = _edge_overlap_with_polygons(a, b, second_polygons)
            for (a2, b2) in overlaps:
                add_segment(a2, b2)
    return segments


def derive_interior_walls(
    spaces: list[dict[str, Any]],
    *,
    default_thickness: float = 0.12,
) -> list[dict[str, Any]]:
    """从所有空间对的公共边界生成分隔墙。

    返回的墙带 kind='interior'，端点吸附到 0.1m 构造网格，并按 (segment, side_a, side_b)
    去重。模型没有提供墙时用此结果。
    """
    walls: list[dict[str, Any]] = []
    seen: set[tuple[tuple[float, float, float, float], str, str]] = set()
    for first_index, first in enumerate(spaces):
        first_id = str(first.get("id") or "")
        first_polys = space_polygons(first)
        for second in spaces[first_index + 1:]:
            second_id = str(second.get("id") or "")
            second_polys = space_polygons(second)
            for (a, b) in shared_boundary_segments(first_polys, second_polys):
                key = (_segment_key(a, b), min(first_id, second_id), max(first_id, second_id))
                if key in seen:
                    continue
                seen.add(key)
                walls.append({
                    "id": "wall_" + first_id + "_x_" + second_id,
                    "kind": "interior",
                    "from": [snap_to_grid(a[0]), snap_to_grid(a[1])],
                    "to": [snap_to_grid(b[0]), snap_to_grid(b[1])],
                    "thickness": default_thickness,
                    "space_a": first_id,
                    "space_b": second_id,
                })
    return walls


def snap_wall_to_boundary(
    wall: dict[str, Any],
    spaces: list[dict[str, Any]],
    *,
    tolerance: float = 0.25,
) -> dict[str, Any]:
    """把模型墙端点吸附到最近的公共边界交点。

    吸附距离超过 tolerance 的端点保持不变（可能确实是外墙，交给后续校验）。
    """
    from_raw = wall.get("from")
    to_raw = wall.get("to")
    if not isinstance(from_raw, list) or len(from_raw) < 2:
        return wall
    if not isinstance(to_raw, list) or len(to_raw) < 2:
        return wall
    start = (float(from_raw[0]), float(from_raw[1]))
    end = (float(to_raw[0]), float(to_raw[1]))

    boundary_points: list[tuple[float, float]] = []
    for first_index, first in enumerate(spaces):
        first_polys = space_polygons(first)
        for second in spaces[first_index + 1:]:
            second_polys = space_polygons(second)
            for (a, b) in shared_boundary_segments(first_polys, second_polys):
                boundary_points.extend([a, b])
    if not boundary_points:
        return wall

    def _nearest(point: tuple[float, float]) -> tuple[float, float] | None:
        best: tuple[float, float] | None = None
        best_dist = tolerance
        for candidate in boundary_points:
            d = math.dist(point, candidate)
            if d <= best_dist:
                best, best_dist = candidate, d
        return best

    new_start = _nearest(start) or start
    new_end = _nearest(end) or end
    if new_start == start and new_end == end:
        return wall
    return {
        **wall,
        "from": [round(new_start[0], 3), round(new_start[1], 3)],
        "to": [round(new_end[0], 3), round(new_end[1], 3)],
    }
