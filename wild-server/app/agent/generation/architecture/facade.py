"""解析立面槽位并约束门窗、阳台、屋顶和栏杆。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from typing import Any

from app.agent.generation.spatial_geometry import snap_to_grid

from .recipes import load_curtain_wall_parameters
from .skeleton import _schematic_volume_ranges
def _wall_descriptor(wall: dict[str, Any]) -> dict[str, Any] | None:
    start = wall.get("from")
    end = wall.get("to")
    if not isinstance(start, list) or not isinstance(end, list) or len(start) != 3 or len(end) != 3:
        return None
    try:
        values = [float(value) for value in (*start, *end)]
    except (TypeError, ValueError):
        return None
    x1, y1, z1, x2, y2, z2 = values
    length = math.hypot(x2 - x1, z2 - z1)
    height = abs(y2 - y1)
    if length < 0.5 or height < 0.5:
        return None
    return {
        "id": wall.get("id"), "x": (x1 + x2) / 2, "z": (z1 + z2) / 2,
        "base_y": min(y1, y2), "height": height, "length": length,
        "axis": "x" if abs(x2 - x1) >= abs(z2 - z1) else "z",
    }


def _expand_schematic_facade_storeys(
    walls: list[dict[str, Any]],
    realization: dict[str, Any],
) -> list[dict[str, Any]]:
    """把连续高墙映射为覆盖全高的代表性楼层，宿主仍是同一真实 wall。

    schematic 只允许 ``modeled_floors`` 个立面采样层；旧实现按语义总层数展开，
    24 层幕墙会产生数百个真实 window 并集中切割四面通高墙。代表层首尾对齐
    建筑底部和顶部，中间均匀分布，既保留总高度读数又限制几何复杂度。
    """
    if realization.get("representation_mode") != "schematic":
        return walls
    semantic_floors = max(1, int(realization.get("floors") or realization.get("modeled_floors") or 1))
    represented_floors = max(
        1,
        min(semantic_floors, int(realization.get("modeled_floors") or semantic_floors)),
    )
    floor_height = max(0.1, float(realization.get("floor_height") or 3.2))
    expanded: list[dict[str, Any]] = []
    for wall in walls:
        wall_story_count = max(1, round(wall["height"] / floor_height))
        if wall_story_count <= 1:
            expanded.append(wall)
            continue
        wall_represented = max(
            1,
            min(
                wall_story_count,
                round(represented_floors * wall_story_count / semantic_floors),
            ),
        )
        first_story = max(1, round(wall["base_y"] / floor_height) + 1)
        last_base_offset = max(0.0, wall["height"] - floor_height)
        for index in range(wall_represented):
            ratio = index / (wall_represented - 1) if wall_represented > 1 else 0.0
            base_offset = last_base_offset * ratio
            story_index = round(first_story + ratio * (wall_story_count - 1))
            expanded.append({
                **wall,
                "base_y": round(wall["base_y"] + base_offset, 3),
                "height": min(floor_height, wall["height"] - base_offset),
                "story_index": story_index,
            })
    return expanded


def _opening_slots_overlap(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    horizontal_clearance: float = 0.0,
) -> bool:
    """判断同一父墙上的两个门窗槽位是否在墙面矩形中相交。"""
    if first.get("wall_id") != second.get("wall_id"):
        return False
    try:
        first_from = first["from"]
        second_from = second["from"]
        first_left = float(first_from[0])
        first_bottom = float(first_from[1])
        second_left = float(second_from[0])
        second_bottom = float(second_from[1])
        first_width = float(first["width"])
        first_height = float(first["height"])
        second_width = float(second["width"])
        second_height = float(second["height"])
    except (KeyError, TypeError, ValueError, IndexError):
        return True
    if min(first_width, first_height, second_width, second_height) <= 0:
        return True
    vertical_overlap = (
        first_bottom < second_bottom + second_height
        and second_bottom < first_bottom + first_height
    )
    horizontal_overlap = (
        first_left < second_left + second_width + horizontal_clearance
        and second_left < first_left + first_width + horizontal_clearance
    )
    return vertical_overlap and horizontal_overlap


def _stable_unit_interval(value: str) -> float:
    """把稳定标识映射到 [0, 1]，为未指定参数提供可复现的小幅变化。"""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _default_entrance_dimensions(slot_id: str, wall_height: float) -> tuple[float, float]:
    width = 0.9 + _stable_unit_interval(f"{slot_id}:width") * 0.25
    height = 2.1 + _stable_unit_interval(f"{slot_id}:height") * 0.25
    return round(width, 3), round(min(height, wall_height - 0.25), 3)


def _evenly_spaced_opening_slots(
    slots: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """在配额小于候选槽位时保留覆盖完整标高范围的规则采样。"""
    if limit <= 0:
        return []
    if len(slots) <= limit:
        return slots
    ordered = sorted(slots, key=lambda slot: (
        float(slot.get("from", [0.0, 0.0, 0.0])[1]),
        {"front": 0, "back": 1, "left": 2, "right": 3}.get(slot.get("facing"), 4),
        int(slot.get("bay") or 0),
        str(slot.get("id") or ""),
    ))
    required = [
        slot for slot in ordered
        if slot.get("role") == "balcony_access"
    ]
    if len(required) >= limit:
        return required[:limit]
    optional = [slot for slot in ordered if slot not in required]
    remaining = limit - len(required)
    if remaining == 1:
        sampled = [optional[len(optional) // 2]]
    else:
        last = len(optional) - 1
        sampled = [
            optional[round(index * last / (remaining - 1))]
            for index in range(remaining)
        ]
    selected_ids = {str(slot.get("id")) for slot in (*required, *sampled)}
    return [slot for slot in ordered if str(slot.get("id")) in selected_ids]


# 能按体量分段的屋顶类型 —— 屋面本身是"逐块可平铺"的线性/平面形态。
# 不在此表的三类是整体式造型，拆开只会得到互不相容的碎曲面：
#   dome            单一穹顶，居中控制整栋
#   chinese_pagoda  重檐逐层自成一套坡面，层间关系由 tiers 表达
#   chinese_curved  整栋一体的曲面壳（飞檐沿整圈连续起翘），不能按体量切断
_PER_VOLUME_ROOF_TYPES = frozenset({"flat", "gable", "hip"})


def _planned_roof_slots(plan: dict[str, Any], realization: dict[str, Any]) -> list[dict[str, Any]]:
    """为多体量顶层生成互不重叠的分段屋顶，避免单块屋面盖住内院/天井。

    门禁只有两条，且都与形状标签无关：
    ① 屋顶类型是"逐块可平铺"的形态（见 ``_PER_VOLUME_ROOF_TYPES``）；
    ② 顶层确实有 ≥2 个独立体量 —— 只有一个体量时保持模型自己的整块屋顶，
       不抢走单一体量的造型自由。

    L 形 / U 形 / 退台 / 合院只是体量组合的结果，不应当是门禁条件：
    早期实现只认 ``shape == "u_shape"``，导致同样多体量的 L 形别墅拿不到槽位，
    进而 roof 配额停留在 1~1，最终整栋只长出一块屋顶。
    """
    roof = plan.get("roof") if isinstance(plan.get("roof"), dict) else {}
    if str(roof.get("type") or "") not in _PER_VOLUME_ROOF_TYPES:
        return []
    modeled_floors = int(realization.get("modeled_floors") or 1)
    floor_height = float(realization.get("floor_height") or 3.2)
    volumes = [
        volume for volume in realization.get("volumes", [])
        if isinstance(volume, dict)
        and int(volume.get("start_floor", 1)) <= modeled_floors <= int(volume.get("end_floor", 1))
    ]
    if len(volumes) < 2:
        return []

    rectangles = [
        (
            float(volume["x"]),
            float(volume["z"]),
            float(volume["x"]) + float(volume["width"]),
            float(volume["z"]) + float(volume["depth"]),
        )
        for volume in volumes
    ]
    overhang = max(0.15, min(0.8, float(roof.get("overhang") or 0.35)))

    def has_adjacent(rectangle: tuple[float, float, float, float], edge: str) -> bool:
        x0, z0, x1, z1 = rectangle
        for other in rectangles:
            if other == rectangle:
                continue
            ox0, oz0, ox1, oz1 = other
            if edge == "left" and abs(ox1 - x0) <= 1e-6 and min(z1, oz1) - max(z0, oz0) > 1e-6:
                return True
            if edge == "right" and abs(ox0 - x1) <= 1e-6 and min(z1, oz1) - max(z0, oz0) > 1e-6:
                return True
            if edge == "front" and abs(oz1 - z0) <= 1e-6 and min(x1, ox1) - max(x0, ox0) > 1e-6:
                return True
            if edge == "back" and abs(oz0 - z1) <= 1e-6 and min(x1, ox1) - max(x0, ox0) > 1e-6:
                return True
        return False

    slots: list[dict[str, Any]] = []
    for index, (volume, rectangle) in enumerate(zip(volumes, rectangles), start=1):
        x0, z0, x1, z1 = rectangle
        roof_x0 = x0 if has_adjacent(rectangle, "left") else x0 - overhang
        roof_x1 = x1 if has_adjacent(rectangle, "right") else x1 + overhang
        roof_z0 = z0 if has_adjacent(rectangle, "front") else z0 - overhang
        roof_z1 = z1 if has_adjacent(rectangle, "back") else z1 + overhang
        slots.append({
            "id": f"roof:{volume.get('id') or index}",
            "position": [
                round((roof_x0 + roof_x1) / 2, 3),
                round(modeled_floors * floor_height, 3),
                round((roof_z0 + roof_z1) / 2, 3),
            ],
            "span": round(roof_x1 - roof_x0, 3),
            "depth": round(roof_z1 - roof_z0, 3),
        })
    return slots


def _planned_terrace_railing_slots(
    blueprint: dict[str, Any],
    opening_slots: list[dict[str, Any]],
    realization: dict[str, Any],
) -> list[dict[str, Any]]:
    """为 U 形或退台体量的可达屋面边缘生成确定性安全栏杆。"""
    if realization.get("shape") == "stepped":
        semantic_floors = max(1, int(realization.get("floors") or 1))
        modeled_floors = max(1, int(realization.get("modeled_floors") or 1))
        floor_height = max(0.1, float(realization.get("floor_height") or 3.2))
        raw_volumes = [
            item for item in realization.get("volumes", [])
            if isinstance(item, dict)
        ]
        volumes = (
            _schematic_volume_ranges(raw_volumes, semantic_floors, modeled_floors)
            if realization.get("representation_mode") == "schematic"
            else [
                {
                    **item,
                    "semantic_start_floor": int(item.get("start_floor", 1)),
                    "semantic_end_floor": int(item.get("end_floor", modeled_floors)),
                }
                for item in raw_volumes
            ]
        )
        for lower in volumes:
            lower_end = int(lower["semantic_end_floor"])
            uppers = [
                item for item in volumes
                if int(item["semantic_start_floor"]) == lower_end + 1
                and float(item["width"]) < float(lower["width"]) - 0.1
                and float(item["depth"]) < float(lower["depth"]) - 0.1
            ]
            if not uppers:
                continue
            x0 = float(lower["x"])
            z0 = float(lower["z"])
            x1 = x0 + float(lower["width"])
            z1 = z0 + float(lower["depth"])
            y = round(lower_end * floor_height + 0.2, 3)
            return [{
                "id": f"railing:podium_terrace:{lower.get('id') or 'base'}",
                "path": [
                    [round(x0, 3), y, round(z0, 3)],
                    [round(x1, 3), y, round(z0, 3)],
                    [round(x1, 3), y, round(z1, 3)],
                    [round(x0, 3), y, round(z1, 3)],
                    [round(x0, 3), y, round(z0, 3)],
                ],
                "height": 1.1,
            }]
        return []
    if realization.get("shape") != "u_shape":
        return []
    access_slots = [slot for slot in opening_slots if slot.get("role") == "balcony_access"]
    if len(access_slots) < 2:
        return []
    walls = {
        element.get("id"): element
        for element in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(element, dict) and element.get("type") == "wall"
    }
    ranges: list[tuple[float, float, float, float]] = []
    for slot in access_slots:
        wall = walls.get(slot.get("wall_id"))
        start = wall.get("from") if isinstance(wall, dict) else None
        end = wall.get("to") if isinstance(wall, dict) else None
        if not isinstance(start, list) or not isinstance(end, list) or len(start) != 3 or len(end) != 3:
            continue
        if abs(float(start[2]) - float(end[2])) > 1e-6:
            continue
        ranges.append((
            min(float(start[0]), float(end[0])),
            max(float(start[0]), float(end[0])),
            float(start[2]),
            float(slot.get("from", [0, 0, 0])[1]),
        ))
    ranges.sort()
    if len(ranges) < 2:
        return []
    left, right = ranges[0], ranges[-1]
    if abs(left[2] - right[2]) > 0.05 or right[0] - left[1] < 0.8:
        return []
    slab_thickness = 0.2
    for floor in blueprint.get("geometry", {}).get("elements", []):
        start = floor.get("from") if isinstance(floor, dict) and floor.get("type") == "floor" else None
        if isinstance(start, list) and len(start) == 3 and abs(float(start[1]) - left[3]) <= 0.05:
            slab_thickness = max(slab_thickness, float(floor.get("thickness") or 0.0))
    y = round(left[3] + slab_thickness, 3)
    return [{
        "id": "railing:upper_terrace_front",
        "path": [[round(left[1], 3), y, round(left[2], 3)], [round(right[0], 3), y, round(right[2], 3)]],
        "height": 1.1,
    }]


def _derived_balcony_slots(
    opening_slots: list[dict[str, Any]],
    walls: list[dict[str, Any]],
    *,
    count: int,
    minimum_y: float,
    requested_width: float | None,
) -> list[dict[str, Any]]:
    """从上层立面开口推导阳台槽位，使悬挑板与入口轴线对齐。"""
    if count <= 0:
        return []
    wall_by_id = {str(wall["id"]): wall for wall in walls}
    candidates: list[tuple[tuple[int, float, str], dict[str, Any]]] = []
    for opening in opening_slots:
        wall = wall_by_id.get(str(opening.get("wall_id") or ""))
        if (
            opening.get("type") != "window"
            or opening.get("role")
            or not wall
            or float(wall["base_y"]) <= minimum_y + 0.25
        ):
            continue
        wall_length = float(wall["length"])
        opening_width = float(opening["width"])
        target_width = (
            float(requested_width)
            if isinstance(requested_width, (int, float)) and not isinstance(requested_width, bool)
            else max(2.4, min(3.2, opening_width + 1.2))
        )
        width = min(wall_length, max(opening_width, target_width))
        center = float(opening["from"][0]) + opening_width / 2
        edge_clearance = min(0.18, max(0.0, (wall_length - width) / 2))
        left = max(
            edge_clearance,
            min(wall_length - width - edge_clearance, center - width / 2),
        )
        # 夹到墙边时无法保持轴线对齐的候选不自动采用。
        if abs(left + width / 2 - center) > 0.05:
            continue
        facing = str(opening.get("facing") or "")
        rank = (
            {"front": 0, "back": 1, "left": 2, "right": 3}.get(facing, 4),
            abs(center - wall_length / 2),
            str(opening.get("id") or ""),
        )
        candidates.append((rank, {
            "id": str(opening["id"]).replace(":window:", ":balcony:"),
            "wall_id": opening["wall_id"],
            "from": [round(left, 3), round(float(wall["base_y"]), 3), 0.0],
            "width": round(width, 3),
            "opening_slot_id": opening["id"],
        }))

    ordered = [candidate for _, candidate in sorted(candidates, key=lambda item: item[0])]
    selected: list[dict[str, Any]] = []
    used_walls: set[str] = set()
    for candidate in ordered:
        wall_id = str(candidate["wall_id"])
        if wall_id in used_walls:
            continue
        selected.append(candidate)
        used_walls.add(wall_id)
        if len(selected) >= count:
            return selected
    for candidate in ordered:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= count:
            break
    return selected


def _curtain_wall_mullions(span: float, *, pane: float | None = None) -> int:
    """玻璃幕墙窗格密铺：按知识库配方的分格模数计算竖向/横向梃数量（上限 32）。

    方案 A（``wall + window``）中，窗编译器会按 ``verticalMullions`` 与
    ``horizontalMullions`` 生成框、竖梃、横梃和玻璃。这里把每个窗切到配方
    ``pane_module`` 见方的窗格，从而避免「整片纯玻璃墙」的观感。分格模数随
    知识库 `glass-curtain-wall-assembly.md` 的确定性参数变化，不在代码里写死。
    """
    if pane is None:
        pane = load_curtain_wall_parameters().pane_module
    if not isinstance(span, (int, float)) or isinstance(span, bool) or span <= 0:
        return 0
    panes = max(1, int(round(float(span) / pane)))
    return min(32, max(0, panes - 1))


def _retry_slot_position(
    slot: dict[str, Any],
    wall: dict[str, Any],
    bay_index: int,
    bays: int,
    existing_slots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """槽位重叠时向相邻开间重排一次。

    先尝试把窗移动到相邻 bay 的中点（向左再向右），仍与既有槽位重叠则放弃。
    """
    candidate = dict(slot)
    width = float(candidate.get("width") or 1.0)
    bay_width = float(wall["length"]) / max(1, bays)
    for direction in (-1, 1):
        neighbor = bay_index + direction
        if neighbor < 0 or neighbor >= bays:
            continue
        center = bay_width * (neighbor + 0.5)
        edge_clearance = min(0.18, max(0.0, (float(wall["length"]) - width) / 2))
        left = max(
            edge_clearance,
            min(float(wall["length"]) - width - edge_clearance, center - width / 2),
        )
        candidate["from"] = [
            round(snap_to_grid(left), 3),
            round(float(slot["from"][1]), 3),
            round(float(slot["from"][2]), 3),
        ]
        candidate["bay"] = neighbor + 1
        if not any(
            _opening_slots_overlap(candidate, existing, horizontal_clearance=0.1)
            for existing in existing_slots
        ):
            return candidate
    return None


def resolve_facade_layout(blueprint: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """把抽象立面轴网解析成真实 wall id 与精确门窗局部坐标。"""
    massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
    curtain_wall = bool(plan.get("curtain_wall"))
    curtain_params = load_curtain_wall_parameters() if curtain_wall else None
    realization = {
        "floors": int(massing.get("floors") or massing.get("modeled_floors") or 1),
        "modeled_floors": int(massing.get("modeled_floors") or massing.get("floors") or 1),
        "floor_height": float(massing.get("floor_height") or 3.2),
        "representation_mode": str(massing.get("representation_mode") or "full"),
        "shape": str(massing.get("shape") or "rectangle"),
        "symmetry": bool(massing.get("symmetry")),
        "volumes": deepcopy(plan.get("volumes") or []),
    }
    walls = []
    for element in blueprint.get("geometry", {}).get("elements", []):
        if (
            isinstance(element, dict)
            and element.get("type") == "wall"
            and not str(element.get("id") or "").startswith("wall_core_")
        ):
            descriptor = _wall_descriptor(element)
            if descriptor:
                walls.append(descriptor)
    walls = _expand_schematic_facade_storeys(walls, realization)
    if not walls:
        roof_slots = _planned_roof_slots(plan, realization)
        quotas = deepcopy(plan.get("component_quota", {}))
        if roof_slots:
            quotas["roof"] = {**quotas.get("roof", {}), "min": len(roof_slots), "max": len(roof_slots)}
        return {
            "facade_plan": {},
            "component_quota": quotas,
            "opening_slots": [],
            "balcony_slots": [],
            "roof_slots": roof_slots,
            "railing_slots": [],
            "realization": realization,
        }

    min_y = min(wall["base_y"] for wall in walls)
    level_bounds: dict[float, dict[str, float]] = {}
    for wall in walls:
        level_key = round(float(wall["base_y"]), 3)
        bounds = level_bounds.setdefault(level_key, {
            "min_x": wall["x"], "max_x": wall["x"],
            "min_z": wall["z"], "max_z": wall["z"],
        })
        bounds["min_x"] = min(bounds["min_x"], wall["x"])
        bounds["max_x"] = max(bounds["max_x"], wall["x"])
        bounds["min_z"] = min(bounds["min_z"], wall["z"])
        bounds["max_z"] = max(bounds["max_z"], wall["z"])

    facade_plan: dict[str, dict[str, Any]] = {}
    slots: list[dict[str, Any]] = []
    meta = blueprint.get("meta", {}) if isinstance(blueprint.get("meta"), dict) else {}
    variation_scope = str(
        meta.get("seed")
        or meta.get("name")
        or plan.get("concept")
        or "default-building"
    )
    balcony_access_remaining = max(0, int(plan.get("balcony_access_count") or 0))
    balcony_width = plan.get("balcony_width")
    for wall in sorted(walls, key=lambda item: (item["base_y"], str(item["id"]))):
        bounds = level_bounds[round(float(wall["base_y"]), 3)]
        span = max(
            bounds["max_x"] - bounds["min_x"],
            bounds["max_z"] - bounds["min_z"],
            1.0,
        )
        boundary_tolerance = max(0.35, span * 0.04)
        if wall["axis"] == "x":
            distances = {
                "front": abs(wall["z"] - bounds["min_z"]),
                "back": abs(wall["z"] - bounds["max_z"]),
            }
        else:
            distances = {
                "left": abs(wall["x"] - bounds["min_x"]),
                "right": abs(wall["x"] - bounds["max_x"]),
            }
        facing = min(distances, key=distances.get)
        external = distances[facing] <= boundary_tolerance
        facade = plan.get("facades", {}).get(facing, {})
        bays = max(1, int(facade.get("bays", 1)))
        is_ground = abs(wall["base_y"] - min_y) < 0.25
        pattern_key = "ground_pattern" if is_ground else "upper_pattern"
        pattern = facade.get(pattern_key, []) if external else []
        bay_width = wall["length"] / bays
        wall_slots: list[dict[str, Any]] = []
        is_balcony_access_wall = (
            balcony_access_remaining > 0
            and not is_ground
            and external
            and facing == "front"
            and wall["axis"] == "x"
            and wall["length"] >= 1.0
        )
        if is_balcony_access_wall:
            requested_access_width = (
                float(balcony_width)
                if isinstance(balcony_width, (int, float)) and not isinstance(balcony_width, bool)
                else wall["length"] - 0.2
            )
            access_width = max(0.8, min(wall["length"], requested_access_width))
            wall_slots.append({
                "id": f"{wall['id']}:floor_{wall.get('story_index', 1)}:door:balcony_access",
                "type": "door",
                "role": "balcony_access",
                "wall_id": wall["id"],
                "facing": facing,
                "bay": 1,
                "from": [round((wall["length"] - access_width) / 2, 3), round(wall["base_y"], 3), 0.0],
                "width": round(access_width, 3),
                "height": round(max(0.8, min(2.6, wall["height"] - 0.25)), 3),
            })
            slots.extend(wall_slots)
            balcony_access_remaining -= 1
        for bay_index, opening_type in enumerate(pattern[:bays]):
            if is_balcony_access_wall:
                break
            if opening_type not in {"door", "window"}:
                continue
            if (
                curtain_wall
                and realization["representation_mode"] == "schematic"
                and opening_type == "window"
            ):
                # 示意高层的连续玻璃墙和龙骨已表达幕墙；不再对通高墙重复切
                # 数百个 window 洞口，避免墙网格顶点爆炸。
                continue
            if opening_type == "door" and not is_ground:
                continue
            if opening_type == "door":
                slot_id = (
                    f"{wall['id']}:floor_{wall.get('story_index', 1)}:"
                    f"{opening_type}:{bay_index + 1}"
                )
                target_width, target_height = _default_entrance_dimensions(
                    f"{variation_scope}:{slot_id}",
                    wall["height"],
                )
                # 门可以跨越立面轴网，不能因为单个 bay 偏窄而失去基本通行宽度。
                available_width = min(wall["length"], max(0.5, wall["length"] - 0.36))
                if wall["length"] >= 0.9:
                    available_width = max(0.9, available_width)
                width = min(target_width, available_width)
            elif curtain_wall:
                # 幕墙窗带贴合开间，只留配方设定的细窄竖梃缝；不再用固定上限卡宽。
                width = max(curtain_params.min_window_width, bay_width - curtain_params.mullion_gap)
            else:
                width = max(0.75, min(2.2, bay_width * 0.62))
                width = min(width, max(0.5, bay_width - 0.35))
            width = snap_to_grid(width)
            center = bay_width * (bay_index + 0.5)
            edge_clearance = min(0.18, max(0.0, (wall["length"] - width) / 2))
            left = max(
                edge_clearance,
                min(wall["length"] - width - edge_clearance, center - width / 2),
            )
            left = snap_to_grid(left)
            if opening_type == "door":
                bottom = wall["base_y"]
                height_cap = target_height
            elif curtain_wall:
                # 幕墙窗台压薄、窗带加高，缩小层间不透明缝。
                bottom = wall["base_y"] + min(
                    curtain_params.sill_height,
                    wall["height"] * curtain_params.sill_ratio,
                )
                height_cap = wall["height"] - (bottom - wall["base_y"]) - curtain_params.top_clearance
            else:
                bottom = wall["base_y"] + min(1.0, wall["height"] * 0.3)
                height_cap = 1.55
            height = min(
                height_cap,
                wall["height"] - (bottom - wall["base_y"]) - 0.25,
            )
            slot = {
                "id": (
                    f"{wall['id']}:floor_{wall.get('story_index', 1)}:"
                    f"{opening_type}:{bay_index + 1}"
                ),
                "type": opening_type,
                "wall_id": wall["id"],
                "facing": facing,
                "bay": bay_index + 1,
                "from": [round(left, 3), round(bottom, 3), 0.0],
                "width": round(width, 3),
                "height": round(max(0.8, height), 3),
            }
            if curtain_wall and opening_type == "window":
                slot["vertical_mullions"] = _curtain_wall_mullions(width)
                slot["horizontal_mullions"] = _curtain_wall_mullions(height)
            # 槽位重叠时先尝试向相邻开间重排一次，而不是直接丢弃，避免开间
            # 密集时窗户被静默删掉；仍无法安置才放弃该槽位。
            if any(
                _opening_slots_overlap(
                    slot,
                    existing,
                    horizontal_clearance=0.1,
                )
                for existing in wall_slots
            ):
                alternative = _retry_slot_position(slot, wall, bay_index, bays, wall_slots)
                if alternative is None:
                    continue
                slot = alternative
            wall_slots.append(slot)
            slots.append(slot)
        wall_plan = facade_plan.setdefault(str(wall["id"]), {
            "facing": facing if external else "internal",
            "intent": (
                "阳台后方设置通室内入口"
                if is_balcony_access_wall
                else "按建筑方案轴网布置门窗"
                if external
                else "内部/退台墙，不自动开口"
            ),
            "max_openings": 0,
            "is_main_facade": False,
            "slots": [],
        })
        wall_plan["max_openings"] += len(wall_slots)
        wall_plan["is_main_facade"] = (
            wall_plan["is_main_facade"] or (external and facing == "front")
        )
        wall_plan["slots"].extend(wall_slots)

    slots.sort(key=lambda slot: (
        {"front": 0, "back": 1, "left": 2, "right": 3}.get(slot["facing"], 4),
        slot["bay"],
        slot["from"][1],
    ))

    quotas = deepcopy(plan.get("component_quota", {}))
    for opening_type in ("door", "window"):
        available = sum(1 for slot in slots if slot["type"] == opening_type)
        limits = quotas.setdefault(opening_type, {})
        if curtain_wall and opening_type == "window":
            # 幕墙全立面密铺：每个窗槽位都必须有窗。这里忽略模型/回退配额上限，
            # 直接按实际立面槽位数量补齐，否则按少量配额沿全高抽样会变成
            # 「每几层才一个窗」的错乱散布。
            limits["max"] = available
            limits["min"] = available
            continue
        maximum = limits.get("max")
        limits["max"] = available if not isinstance(maximum, (int, float)) else min(int(maximum), available)
        minimum = limits.get("min", 0)
        limits["min"] = min(int(minimum) if isinstance(minimum, (int, float)) else 0, limits["max"])

    balcony_slots = [
        {
            "id": str(slot["id"]).replace(":door:", ":balcony:"),
            "wall_id": slot["wall_id"],
            "from": deepcopy(slot["from"]),
            "width": slot["width"],
        }
        for slot in slots
        if slot.get("role") == "balcony_access"
    ]
    balcony_limits = quotas.get("balcony", {})
    balcony_minimum = (
        int(balcony_limits.get("min", 0))
        if isinstance(balcony_limits, dict)
        and isinstance(balcony_limits.get("min", 0), (int, float))
        else 0
    )
    if len(balcony_slots) < balcony_minimum:
        balcony_slots.extend(_derived_balcony_slots(
            slots,
            walls,
            count=balcony_minimum - len(balcony_slots),
            minimum_y=min_y,
            requested_width=(
                float(balcony_width)
                if isinstance(balcony_width, (int, float)) and not isinstance(balcony_width, bool)
                else None
            ),
        ))
    roof_slots = _planned_roof_slots(plan, realization)
    if roof_slots:
        quotas["roof"] = {
            **quotas.get("roof", {}),
            "min": len(roof_slots),
            "max": len(roof_slots),
            "note": "每个体量各一块，不跨越内院/退台凹口",
        }
    railing_slots = _planned_terrace_railing_slots(blueprint, slots, realization)

    return {
        "facade_plan": facade_plan,
        "component_quota": quotas,
        "opening_slots": slots,
        "balcony_slots": balcony_slots,
        "roof_slots": roof_slots,
        "railing_slots": railing_slots,
        "realization": realization,
        "rag_reference": "建筑方案节点已确定体量、立面轴网、屋顶类型；门窗坐标由程序解析。",
    }


def conform_openings_to_slots(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
    materials: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """把模型门窗吸附到槽位，并补足设计下限；凸窗优先占用普通窗槽位。"""
    if not isinstance(design_brief, dict) or not isinstance(design_brief.get("opening_slots"), list):
        return components, {"snapped": 0, "synthesized": 0, "pruned": 0}
    material_names = list((materials or {}).keys())
    default_material = material_names[0] if material_names else "default"
    glass_material = next(
        (name for name, value in (materials or {}).items() if "glass" in name.lower() or (isinstance(value, dict) and value.get("opacity", 1) < 0.99)),
        default_material,
    )
    fallback_frame_material = next(
        (name for name in material_names if "wood" in name.lower()),
        default_material,
    )
    frame_material = next(
        (name for name in material_names if any(word in name.lower() for word in ("frame", "metal"))),
        fallback_frame_material,
    )
    leaf_material = next(
        (name for name in material_names if any(word in name.lower() for word in ("wood", "door", "accent"))),
        frame_material,
    )
    non_openings = [
        item for item in components
        if item.get("type") not in {"door", "window", "bay_window"}
    ]
    result_openings: list[dict[str, Any]] = []
    stats = {"snapped": 0, "synthesized": 0, "pruned": 0}
    quotas = design_brief.get("component_quota", {})
    all_slots: list[dict[str, Any]] = []
    for raw_slot in design_brief["opening_slots"]:
        if (
            not isinstance(raw_slot, dict)
            or raw_slot.get("type") not in {"door", "window"}
            or not raw_slot.get("id")
            or not raw_slot.get("wall_id")
        ):
            continue
        slot = deepcopy(raw_slot)
        if any(_opening_slots_overlap(slot, existing) for existing in all_slots):
            continue
        all_slots.append(slot)

    # 凸窗本质上也是父墙洞口。先让它占用最近的普通窗槽位，后续普通窗只能
    # 使用剩余槽位，从源头避免独立节点生成的凸窗和门窗在合并后重复切洞。
    window_slots = [
        slot for slot in all_slots
        if isinstance(slot, dict) and slot.get("type") == "window"
    ]
    used_window_slots: set[str] = set()
    bay_windows = [deepcopy(item) for item in components if item.get("type") == "bay_window"]
    bay_limits = (
        quotas.get("bay_window", {})
        if isinstance(quotas.get("bay_window"), dict)
        else {}
    )
    bay_minimum = min(
        len(window_slots),
        max(0, int(bay_limits.get("min", 0))),
    )
    missing_bay_windows = max(0, bay_minimum - len(bay_windows))
    for index in range(missing_bay_windows):
        bay_windows.append({
            "id": f"bay_window_planned_{len(bay_windows) + 1:02d}",
            "type": "bay_window",
            "projectionDepth": 0.8,
            "frameWidth": 0.08,
            "frameDepth": 0.12,
            "frameMaterial": frame_material,
            "glassMaterial": glass_material,
        })
    stats["synthesized"] += missing_bay_windows
    for bay_window in bay_windows:
        available = [slot for slot in window_slots if slot["id"] not in used_window_slots]
        if not available:
            stats["pruned"] += 1
            continue
        original_from = bay_window.get("from", [0, 0, 0])
        original_center = (
            float(original_from[0]) + float(bay_window.get("width", 0)) / 2
            if isinstance(original_from, list) and original_from else 0.0
        )
        original_y = (
            float(original_from[1])
            if isinstance(original_from, list) and len(original_from) > 1 else 0.0
        )

        def bay_slot_rank(slot: dict[str, Any]) -> tuple[int, float, float, str]:
            slot_from = slot.get("from", [0, 0, 0])
            return (
                0 if slot.get("wall_id") == bay_window.get("parentWall") else 1,
                abs(float(slot_from[1]) - original_y),
                abs(float(slot_from[0]) + float(slot.get("width", 0)) / 2 - original_center),
                str(slot.get("id", "")),
            )

        slot = min(available, key=bay_slot_rank)
        used_window_slots.add(slot["id"])
        bay_window["parentWall"] = slot["wall_id"]
        bay_window["from"] = deepcopy(slot["from"])
        bay_window["width"] = slot["width"]
        bay_window["height"] = slot["height"]
        result_openings.append(bay_window)
        stats["snapped"] += 1

    for opening_type in ("door", "window"):
        items = [deepcopy(item) for item in components if item.get("type") == opening_type]
        slots = [
            slot for slot in all_slots
            if isinstance(slot, dict)
            and slot.get("type") == opening_type
            and (opening_type != "window" or slot["id"] not in used_window_slots)
        ]
        limits = quotas.get(opening_type, {}) if isinstance(quotas.get(opening_type), dict) else {}
        bay_count = (
            sum(1 for item in result_openings if item.get("type") == "bay_window")
            if opening_type == "window" else 0
        )
        maximum = min(len(slots), max(0, int(limits.get("max", len(slots))) - bay_count))
        slots = _evenly_spaced_opening_slots(slots, maximum)
        maximum = len(slots)
        minimum = min(maximum, max(0, int(limits.get("min", 0)) - bay_count))
        if len(items) > maximum:
            stats["pruned"] += len(items) - maximum
            items = items[:maximum]
        used_slots: set[str] = set()
        ordered_items: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for item in items:
            preferred = next((slot for slot in slots if slot["id"] not in used_slots and slot["wall_id"] == item.get("parentWall")), None)
            slot = preferred or next((slot for slot in slots if slot["id"] not in used_slots), None)
            if not slot:
                break
            used_slots.add(slot["id"])
            ordered_items.append((item, slot))
        while len(ordered_items) < minimum:
            slot = next((candidate for candidate in slots if candidate["id"] not in used_slots), None)
            if not slot:
                break
            used_slots.add(slot["id"])
            index = len(ordered_items) + 1
            if opening_type == "door":
                is_balcony_access = slot.get("role") == "balcony_access"
                item = {
                    "id": (
                        f"door_balcony_access_{index:02d}"
                        if is_balcony_access else f"door_planned_{index:02d}"
                    ),
                    "type": "door",
                    "interaction": {"mode": "swing", "hingeSide": "left", "openAngle": 90},
                    "frameMaterial": frame_material, "leafMaterial": leaf_material,
                }
            else:
                item = {
                    "id": f"window_planned_{index:02d}", "type": "window",
                    "verticalMullions": int(slot.get("vertical_mullions", 1)),
                    "horizontalMullions": int(slot.get("horizontal_mullions", 0)),
                    "frameMaterial": frame_material, "glassMaterial": glass_material,
                }
            ordered_items.append((item, slot))
            stats["synthesized"] += 1
        for item, slot in ordered_items:
            if slot.get("role"):
                item["role"] = slot["role"]
            item["parentWall"] = slot["wall_id"]
            item["from"] = deepcopy(slot["from"])
            item["width"] = slot["width"]
            item["height"] = slot["height"]
            if opening_type == "window" and "vertical_mullions" in slot:
                # 幕墙窗格：统一到骨架解析出的分格模数，覆盖模型任意梃数，保证整面密铺。
                item["verticalMullions"] = int(slot["vertical_mullions"])
                item["horizontalMullions"] = int(slot.get("horizontal_mullions", 0))
                item["frameMaterial"] = frame_material
                item["glassMaterial"] = glass_material
            if opening_type == "door":
                variant = _stable_unit_interval(f"{item.get('id', slot['id'])}:frame")
                item.setdefault("frameWidth", round(0.065 + variant * 0.025, 3))
                item.setdefault("frameMaterial", frame_material)
                item.setdefault("leafMaterial", leaf_material)
                item.setdefault("interaction", {
                    "mode": "swing",
                    "hingeSide": "left" if variant < 0.5 else "right",
                    "openAngle": 90,
                })
            result_openings.append(item)
            stats["snapped"] += 1
    return [*non_openings, *result_openings], stats


def conform_balconies_to_slots(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """把阳台与阳台门槽位一一绑定，修正挂错墙和宽度漂移。"""
    slots = design_brief.get("balcony_slots") if isinstance(design_brief, dict) else None
    if not isinstance(slots, list) or not slots:
        return components, {"snapped": 0, "synthesized": 0, "pruned": 0}
    sources = [deepcopy(item) for item in components if item.get("type") == "balcony"]
    non_balconies = [item for item in components if item.get("type") != "balcony"]
    stats = {
        "snapped": min(len(sources), len(slots)),
        "synthesized": max(0, len(slots) - len(sources)),
        "pruned": max(0, len(sources) - len(slots)),
    }
    balconies: list[dict[str, Any]] = []
    for index, slot in enumerate(slots, start=1):
        item = sources[index - 1] if index <= len(sources) else {
            "type": "balcony",
            "id": f"balcony_planned_{index:02d}",
            "depth": 1.5,
            "slabThickness": 0.18,
            "railingHeight": 1.1,
            "postSpacing": 0.9,
        }
        item["parentWall"] = slot["wall_id"]
        item["from"] = deepcopy(slot["from"])
        item["width"] = slot["width"]
        item["depth"] = round(max(0.8, min(2.5, float(item.get("depth") or 1.5))), 3)
        item["slabThickness"] = round(max(0.12, float(item.get("slabThickness") or 0.18)), 3)
        item["railingHeight"] = round(max(0.9, float(item.get("railingHeight") or 1.1)), 3)
        balconies.append(item)
    return [*non_balconies, *balconies], stats


def _plan_winding(plan: dict[str, Any] | None, frm: list[Any], ux: float, uz: float) -> float:
    """用体量联合轮廓的有向面积（shoelace）判定建筑平面绕向。

    返回面积为正表示逆时针（右旋法向朝外），为负表示顺时针（需取反）。
    无法从 plan 恢复轮廓时，退化为沿墙方向右旋的默认假设。
    """
    volumes = plan.get("volumes") if isinstance(plan, dict) else None
    if not isinstance(volumes, list) or not volumes:
        # 只有单面入口墙时无法判定绕向，保留既有右旋假设（返回正面积）。
        return 1.0
    corners: list[tuple[float, float]] = []
    for volume in volumes:
        if not isinstance(volume, dict):
            continue
        try:
            x = float(volume.get("x") or 0.0)
            z = float(volume.get("z") or 0.0)
            w = float(volume.get("width") or 0.0)
            d = float(volume.get("depth") or 0.0)
        except (TypeError, ValueError):
            continue
        corners.extend([(x, z), (x + w, z), (x + w, z + d), (x, z + d)])
    if len(corners) < 3:
        return 1.0
    # 用凸包顶点计算有向面积（shoelace 法）。
    hull = _convex_hull(corners)
    area2 = 0.0
    for index in range(len(hull)):
        x1, z1 = hull[index]
        x2, z2 = hull[(index + 1) % len(hull)]
        area2 += x1 * z2 - x2 * z1
    if abs(area2) < 1e-9:
        return 1.0
    return area2


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew 单调链凸包；返回逆时针顶点序列。"""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _entrance_anchor(
    design_brief: dict[str, Any] | None,
    blueprint: dict[str, Any] | None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """定位主入口门的墙体、沿墙中心与世界坐标，供雨棚/入口灯对齐。"""
    if not isinstance(design_brief, dict):
        return None
    slots = design_brief.get("opening_slots")
    if not isinstance(slots, list):
        return None
    door_slots = [
        slot for slot in slots
        if isinstance(slot, dict)
        and slot.get("type") == "door"
        and slot.get("wall_id")
    ]
    if not door_slots:
        return None
    entrance = min(
        door_slots,
        key=lambda slot: (
            0 if slot.get("facing") == "front" else 1,
            0 if slot.get("role") != "balcony_access" else 1,
            str(slot.get("id", "")),
        ),
    )
    wall_id = str(entrance["wall_id"])
    wall = next(
        (
            element for element in (blueprint or {}).get("geometry", {}).get("elements", [])
            if isinstance(element, dict)
            and element.get("type") == "wall"
            and element.get("id") == wall_id
        ),
        None,
    )
    if not isinstance(wall, dict):
        return None
    frm, to = wall.get("from"), wall.get("to")
    if (
        not isinstance(frm, list) or len(frm) != 3
        or not isinstance(to, list) or len(to) != 3
    ):
        return None
    dx = float(to[0]) - float(frm[0])
    dz = float(to[2]) - float(frm[2])
    length = (dx * dx + dz * dz) ** 0.5
    if length < 1e-6:
        return None
    ux, uz = dx / length, dz / length
    door_from = entrance.get("from") or [0.0, 0.0, 0.0]
    door_width = max(0.0, float(entrance.get("width") or 1.0))
    along = float(door_from[0]) + door_width / 2.0
    # 外法向不能假设“墙按逆时针围合”：LLM 的 volumes 组合出顺时针或凹形
    # 轮廓时，固定右旋 90° 会把入口附属件放到室内一侧。用体量联合轮廓的
    # 有向面积（shoelace）判定实际绕向：逆时针用右旋，顺时针取反。
    winding = _plan_winding(plan, frm, ux, uz)
    normal_sign = 1.0 if winding >= 0 else -1.0
    return {
        "wall_id": wall_id,
        "facing": entrance.get("facing"),
        "along": along,
        "length": length,
        "run_x": ux,
        "run_z": uz,
        "normal_x": uz * normal_sign,
        "normal_z": -ux * normal_sign,
        "origin_x": float(frm[0]),
        "origin_z": float(frm[2]),
        "door_base_y": float(door_from[1]),
        "door_height": max(0.5, float(entrance.get("height") or 2.1)),
        "constant_x": abs(dx) <= abs(dz),  # 沿 Z 走向（左右墙）时为 True
    }


def conform_entrance_accessories(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
    blueprint: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """把入口雨棚与入口墙灯具吸附到主入口门，消除模型自由摆放导致的对不齐。

    门/窗由 ``conform_openings_to_slots`` 吸附，而雨棚、灯具此前只做形状校验，
    模型会随手放到整面墙的几何中心或悬空高度。这里只对齐「与主入口墙同面的」
    附属件，不越界改动其它墙上的合法构件。
    """
    stats = {"canopy_snapped": 0, "light_snapped": 0}
    anchor = _entrance_anchor(design_brief, blueprint, plan=design_brief)
    if anchor is None:
        return components, stats

    result = deepcopy(components)
    for comp in result:
        ctype = comp.get("type")

        if ctype == "canopy" and comp.get("parentWall") == anchor["wall_id"]:
            width = max(0.0, float(comp.get("width") or 0.0))
            along = max(0.0, min(anchor["along"] - width / 2.0, anchor["length"] - width))
            comp_from = comp.get("from")
            if isinstance(comp_from, list) and len(comp_from) == 3:
                comp["from"] = [round(along, 3), comp_from[1], comp_from[2]]
                stats["canopy_snapped"] += 1

        elif ctype == "light":
            position = comp.get("position")
            if not isinstance(position, list) or len(position) != 3:
                continue
            on_entrance_wall = (
                abs(float(position[2]) - anchor["origin_z"]) < 0.75
                if anchor["constant_x"] is False
                else abs(float(position[0]) - anchor["origin_x"]) < 0.75
            )
            fixture_type = str(comp.get("fixtureType") or "table_lamp")
            # 台灯/落地灯悬浮到半空是常见模型错误，统一落到地面；壁灯保留安装高度。
            if fixture_type == "table_lamp" and float(position[1]) > 2.0:
                position[1] = 0.0
            if on_entrance_wall:
                offset = 0.35
                along = anchor["along"]
                if fixture_type == "bulb":
                    along = (
                        (float(position[0]) - anchor["origin_x"]) * anchor["run_x"]
                        + (float(position[2]) - anchor["origin_z"]) * anchor["run_z"]
                    )
                    along = max(0.15, min(along, anchor["length"] - 0.15))
                position[0] = round(
                    anchor["origin_x"]
                    + anchor["run_x"] * along
                    + anchor["normal_x"] * offset,
                    3,
                )
                position[1] = (
                    round(max(anchor["door_base_y"] + 1.8, float(position[1])), 3)
                    if fixture_type == "bulb" else 0.0
                )
                position[2] = round(
                    anchor["origin_z"]
                    + anchor["run_z"] * along
                    + anchor["normal_z"] * offset,
                    3,
                )
                stats["light_snapped"] += 1

    return result, stats


def conform_roofs_to_slots(
    elements: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """用一个模型屋顶作为风格模板，按已批准的多体量拆成多个无重叠屋面。

    模型只负责"这块屋顶长什么样"（roofType / height / thickness / material），
    位置与尺度由体量槽位决定 —— 模型无需、也无法输出多块屋顶。
    """
    slots = design_brief.get("roof_slots") if isinstance(design_brief, dict) else None
    if not isinstance(slots, list) or not slots:
        return elements, {"split": 0, "synthesized": 0}
    roofs = [deepcopy(item) for item in elements if item.get("type") == "roof"]
    non_roofs = [item for item in elements if item.get("type") != "roof"]
    template = roofs[0] if roofs else {
        "type": "roof", "roofType": "flat", "height": 0,
        "thickness": 0.25, "material": "default",
    }
    planned: list[dict[str, Any]] = []
    for index, slot in enumerate(slots, start=1):
        item = deepcopy(template)
        item["id"] = f"roof_planned_{index:02d}"
        item["position"] = deepcopy(slot["position"])
        item["span"] = slot["span"]
        item["depth"] = slot["depth"]
        planned.append(item)
    return [*non_roofs, *planned], {
        "split": max(0, len(planned) - len(roofs)),
        "synthesized": 1 if not roofs else 0,
    }


def conform_railings_to_slots(
    components: list[dict[str, Any]],
    design_brief: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """补齐方案要求的退台临空栏杆，并优先替换无明确位置的超额栏杆。"""
    slots = design_brief.get("railing_slots") if isinstance(design_brief, dict) else None
    if not isinstance(slots, list) or not slots:
        return components, {"synthesized": 0, "replaced": 0}
    result = list(components)
    maximum = int(design_brief.get("component_quota", {}).get("railing", {}).get("max", 4))
    stats = {"synthesized": 0, "replaced": 0}
    for index, slot in enumerate(slots, start=1):
        if any(item.get("type") == "railing" and item.get("path") == slot.get("path") for item in result):
            continue
        railing_indices = [i for i, item in enumerate(result) if item.get("type") == "railing"]
        if maximum >= 0 and len(railing_indices) >= maximum and railing_indices:
            result.pop(railing_indices[-1])
            stats["replaced"] += 1
        result.append({
            "type": "railing",
            "id": f"railing_planned_{index:02d}",
            "path": deepcopy(slot["path"]),
            "height": float(slot.get("height") or 1.1),
            "postSpacing": 1.0,
            "railCount": 2,
        })
        stats["synthesized"] += 1
    return result, stats
