"""骨架到组件节点之间共享的确定性空间约束。"""

from __future__ import annotations

from typing import Any


def _as_finite_vec3(value: object) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        vector = [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None
    if not all(number == number and abs(number) != float("inf") for number in vector):
        return None
    return vector


def build_spatial_invariants(blueprint: dict[str, Any], wall_bbox: dict[str, Any]) -> dict[str, Any]:
    """提取下游节点必须遵守的坐标系、墙体方向和楼层标高。"""
    walls: list[dict[str, Any]] = []
    floors: list[dict[str, Any]] = []
    geometry = blueprint.get("geometry", {})
    elements = geometry.get("elements", []) if isinstance(geometry, dict) else []
    for element in elements:
        if not isinstance(element, dict):
            continue
        start = _as_finite_vec3(element.get("from"))
        end = _as_finite_vec3(element.get("to"))
        if start is None or end is None:
            continue
        element_type = element.get("type")
        if element_type == "wall":
            dx = end[0] - start[0]
            dz = end[2] - start[2]
            length = (dx * dx + dz * dz) ** 0.5
            direction = [dx / length, 0.0, dz / length] if length else [0.0, 0.0, 0.0]
            walls.append({
                "id": element.get("id"),
                "from": start,
                "to": end,
                "length_xz": length,
                "direction_xz": direction,
                "normal_xz": [-direction[2], 0.0, direction[0]],
            })
        elif element_type == "floor":
            floors.append({
                "id": element.get("id"),
                "from": start,
                "to": end,
                "elevation": min(start[1], end[1]),
            })
    return {
        "coordinate_system": "Y-up, metres",
        "wall_bounding_box": wall_bbox,
        "walls": walls,
        "floors": floors,
    }
