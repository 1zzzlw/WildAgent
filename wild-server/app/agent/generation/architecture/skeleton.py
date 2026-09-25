"""根据已归一化的建筑方案生成确定性主体骨架。"""

from __future__ import annotations

import math
from typing import Any

from app.agent.generation.spatial_geometry import shared_footprint, shared_stair_layout
from app.agent.generation.stair_openings import cut_stair_openings

from .planning import normalize_architecture_plan
from .profile import _fallback_volumes
def _resolve_floor_plate_plan(
    volumes: list[dict[str, Any]],
    modeled_floors: int,
    floor_height: float,
) -> list[dict[str, Any]]:
    """生成各楼层标高的非重复楼板覆盖。

    退台交接层必须由下层体量的完整顶板封闭；上层较小体量的底板若已被
    该顶板包含，则不能再生成一块共面楼板。
    """
    plates: list[dict[str, Any]] = []
    tolerance = 0.01

    def bounds(volume: dict[str, Any]) -> tuple[float, float, float, float]:
        x0 = float(volume["x"])
        z0 = float(volume["z"])
        return (
            x0,
            z0,
            x0 + float(volume["width"]),
            z0 + float(volume["depth"]),
        )

    def contains(
        outer: tuple[float, float, float, float],
        inner: tuple[float, float, float, float],
    ) -> bool:
        return (
            outer[0] <= inner[0] + tolerance
            and outer[1] <= inner[1] + tolerance
            and outer[2] >= inner[2] - tolerance
            and outer[3] >= inner[3] - tolerance
        )

    for level in range(1, modeled_floors + 1):
        current = [
            volume for volume in volumes
            if int(volume["start_floor"]) <= level <= int(volume["end_floor"])
        ]
        supporting = [] if level == 1 else [
            volume for volume in volumes
            if int(volume["start_floor"]) <= level - 1 <= int(volume["end_floor"])
        ]
        candidates = [*supporting, *current]
        if not candidates:
            continue

        ranked = sorted(
            candidates,
            key=lambda volume: (
                -(float(volume["width"]) * float(volume["depth"])),
                str(volume["id"]),
            ),
        )
        selected: list[tuple[dict[str, Any], tuple[float, float, float, float]]] = []
        for volume in ranked:
            footprint = bounds(volume)
            if any(contains(existing, footprint) for _, existing in selected):
                continue
            selected.append((volume, footprint))

        for volume, footprint in selected:
            plates.append({
                "level": level,
                "elevation": round((level - 1) * floor_height, 3),
                "volume_id": str(volume["id"]),
                "bounds": footprint,
            })
    return plates


def _resolve_union_wall_segments(
    volumes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把同层正交矩形体量编译成联合外轮廓，去掉共享边和被覆盖的内部边。"""
    rectangles = [
        (
            float(volume["x"]),
            float(volume["z"]),
            float(volume["x"]) + float(volume["width"]),
            float(volume["z"]) + float(volume["depth"]),
        )
        for volume in volumes
    ]
    xs = sorted({value for rectangle in rectangles for value in (rectangle[0], rectangle[2])})
    zs = sorted({value for rectangle in rectangles for value in (rectangle[1], rectangle[3])})
    occupied: set[tuple[int, int]] = set()
    for x_index in range(len(xs) - 1):
        for z_index in range(len(zs) - 1):
            center_x = (xs[x_index] + xs[x_index + 1]) / 2
            center_z = (zs[z_index] + zs[z_index + 1]) / 2
            if any(
                x0 < center_x < x1 and z0 < center_z < z1
                for x0, z0, x1, z1 in rectangles
            ):
                occupied.add((x_index, z_index))

    raw_segments: list[tuple[str, float, float, float]] = []
    for x_index, z_index in occupied:
        x0, x1 = xs[x_index], xs[x_index + 1]
        z0, z1 = zs[z_index], zs[z_index + 1]
        if (x_index, z_index - 1) not in occupied:
            raw_segments.append(("front", z0, x0, x1))
        if (x_index, z_index + 1) not in occupied:
            raw_segments.append(("back", z1, x0, x1))
        if (x_index - 1, z_index) not in occupied:
            raw_segments.append(("left", x0, z0, z1))
        if (x_index + 1, z_index) not in occupied:
            raw_segments.append(("right", x1, z0, z1))

    merged: list[tuple[str, float, float, float]] = []
    for side in ("front", "right", "back", "left"):
        constants = sorted({segment[1] for segment in raw_segments if segment[0] == side})
        for constant in constants:
            intervals = sorted(
                (segment[2], segment[3])
                for segment in raw_segments
                if segment[0] == side and abs(segment[1] - constant) <= 1e-6
            )
            if not intervals:
                continue
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start <= end + 1e-6:
                    end = max(end, next_end)
                else:
                    merged.append((side, constant, start, end))
                    start, end = next_start, next_end
            merged.append((side, constant, start, end))

    segments: list[dict[str, Any]] = []
    for side, constant, start, end in merged:
        if side == "front":
            start_point, end_point = (start, constant), (end, constant)
        elif side == "back":
            start_point, end_point = (end, constant), (start, constant)
        elif side == "left":
            start_point, end_point = (constant, end), (constant, start)
        else:
            start_point, end_point = (constant, start), (constant, end)
        segments.append({"side": side, "from": start_point, "to": end_point})
    return segments


def _schematic_volume_ranges(
    volumes: list[dict[str, Any]],
    semantic_floors: int,
    modeled_floors: int,
) -> list[dict[str, Any]]:
    """把代表层体量区间映射到完整语义层数，保持基座/塔身连续。

    规划协议中的 volume 楼层范围使用 ``modeled_floors``。示意高层不能直接
    把这些数字当真实楼层，也不能忽略 volume 退化成整高外包矩形；这里按连续
    分箱映射，例如 30 层/6 代表层中的第 1 段对应真实 1~5 层。
    """

    semantic_floors = max(1, int(semantic_floors))
    modeled_floors = max(1, int(modeled_floors))
    resolved: list[dict[str, Any]] = []
    for volume in volumes:
        start = max(1, min(modeled_floors, int(volume.get("start_floor", 1))))
        end = max(start, min(modeled_floors, int(volume.get("end_floor", modeled_floors))))
        semantic_start = math.floor((start - 1) * semantic_floors / modeled_floors) + 1
        semantic_end = max(
            semantic_start,
            math.floor(end * semantic_floors / modeled_floors),
        )
        resolved.append({
            **volume,
            "semantic_start_floor": semantic_start,
            "semantic_end_floor": min(semantic_floors, semantic_end),
        })
    return resolved


def _schematic_volume_zones(
    volumes: list[dict[str, Any]],
    semantic_floors: int,
    modeled_floors: int,
) -> list[dict[str, Any]]:
    mapped = _schematic_volume_ranges(volumes, semantic_floors, modeled_floors)
    boundaries = sorted({
        1,
        semantic_floors + 1,
        *(int(volume["semantic_start_floor"]) for volume in mapped),
        *(int(volume["semantic_end_floor"]) + 1 for volume in mapped),
    })
    zones: list[dict[str, Any]] = []
    for start, next_start in zip(boundaries, boundaries[1:]):
        end = next_start - 1
        active = [
            volume for volume in mapped
            if int(volume["semantic_start_floor"]) <= start <= int(volume["semantic_end_floor"])
        ]
        if active:
            zones.append({"start_floor": start, "end_floor": end, "volumes": active})
    return zones


def _append_curtain_wall_grid(
    elements: list[dict[str, Any]],
    wall_segments: list[dict[str, Any]],
    *,
    base_y: float,
    top_y: float,
    start_floor: int,
    end_floor: int,
    floor_height: float,
    facades: dict[str, Any],
    zone_index: int,
) -> None:
    """在连续玻璃外壳外侧生成轻量竖梃与逐层横梃，不再靠六条窗带冒充幕墙。"""

    normals = {
        "front": (0.0, -0.14), "back": (0.0, 0.14),
        "left": (-0.14, 0.0), "right": (0.14, 0.0),
    }
    for segment_index, segment in enumerate(wall_segments, start=1):
        side = str(segment["side"])
        start_x, start_z = (float(value) for value in segment["from"])
        end_x, end_z = (float(value) for value in segment["to"])
        normal_x, normal_z = normals[side]
        ax, az = start_x + normal_x, start_z + normal_z
        bx, bz = end_x + normal_x, end_z + normal_z
        bays = max(1, int((facades.get(side) or {}).get("bays", 6)))
        for bay in range(1, bays):
            ratio = bay / bays
            x = ax + (bx - ax) * ratio
            z = az + (bz - az) * ratio
            elements.append({
                "type": "beam",
                "id": f"curtain_mullion_v_{zone_index}_{segment_index}_{bay}",
                "from": [round(x, 3), round(base_y, 3), round(z, 3)],
                "to": [round(x, 3), round(top_y, 3), round(z, 3)],
                "crossSection": "rect", "width": 0.08, "height": 0.1,
                "material": "metal",
            })
        # 每个语义楼层的顶边都需要一道横梃。坐标必须相对当前分区的 base_y
        # 计算，不能假定整栋建筑从 0m 起步；分区顶边同时作为封边。
        for story in range(start_floor, end_floor + 1):
            y = base_y + (story - start_floor + 1) * floor_height
            elements.append({
                "type": "beam",
                "id": f"curtain_mullion_h_{zone_index}_{segment_index}_{story}",
                "from": [round(ax, 3), round(y, 3), round(az, 3)],
                "to": [round(bx, 3), round(y, 3), round(bz, 3)],
                "crossSection": "rect", "width": 0.08, "height": 0.1,
                "material": "metal",
            })


def evaluate_skeleton_complexity(
    blueprint: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """评估骨架是否兑现方案中的结构数量和体量层次目标。"""
    elements = [
        item for item in blueprint.get("geometry", {}).get("elements", [])
        if isinstance(item, dict)
    ]
    counts: dict[str, int] = {}
    floor_footprints: set[tuple[float, ...]] = set()
    floor_layouts: set[tuple[float, ...]] = set()
    wall_groups: dict[tuple[float, float], list[dict[str, Any]]] = {}
    wall_base_levels: set[float] = set()
    wall_keys: set[tuple[Any, ...]] = set()
    duplicate_wall_count = 0
    degenerate_wall_ids: list[str] = []
    columns: list[tuple[float, float, float, float, float]] = []
    for element in elements:
        element_type = str(element.get("type") or "unknown")
        counts[element_type] = counts.get(element_type, 0) + 1
        if element_type == "floor":
            start = element.get("from")
            end = element.get("to")
            if isinstance(start, list) and isinstance(end, list) and len(start) == 3 and len(end) == 3:
                floor_footprints.add(tuple(round(float(value), 2) for value in (
                    start[0], start[2], end[0], end[2],
                )))
                floor_layouts.add(tuple(round(float(value), 2) for value in (
                    start[1], start[0], start[2], end[0], end[2],
                )))
        elif element_type == "wall":
            start = element.get("from")
            end = element.get("to")
            if isinstance(start, list) and isinstance(end, list) and len(start) == 3 and len(end) == 3:
                if math.hypot(float(end[0]) - float(start[0]), float(end[2]) - float(start[2])) <= 0.01:
                    degenerate_wall_ids.append(str(element.get("id", "?")))
                vertical_range = tuple(sorted((round(float(start[1]), 2), round(float(end[1]), 2))))
                wall_groups.setdefault(vertical_range, []).append(element)
                wall_base_levels.add(vertical_range[0])
                horizontal_endpoints = tuple(sorted((
                    (round(float(start[0]), 2), round(float(start[2]), 2)),
                    (round(float(end[0]), 2), round(float(end[2]), 2)),
                )))
                wall_key = (horizontal_endpoints, vertical_range)
                if wall_key in wall_keys:
                    duplicate_wall_count += 1
                else:
                    wall_keys.add(wall_key)
        elif element_type == "column":
            base = element.get("base")
            if isinstance(base, list) and len(base) == 3:
                try:
                    height = float(element.get("height", 0))
                    radius = max(
                        float(element.get("bottomRadius", 0)),
                        float(element.get("topRadius", 0)),
                        float(element.get("radius", 0)),
                        float(element.get("width", 0)) / 2,
                        float(element.get("depth", 0)) / 2,
                        0.01,
                    )
                    columns.append((
                        float(base[0]), float(base[1]), float(base[2]), height, radius,
                    ))
                except (TypeError, ValueError):
                    pass

    volume_footprints: set[tuple[float, ...]] = set()
    for walls in wall_groups.values():
        pending = set(range(len(walls)))
        while pending:
            component = {pending.pop()}
            changed = True
            while changed:
                changed = False
                component_points = [
                    (float(walls[index][field][0]), float(walls[index][field][2]))
                    for index in component for field in ("from", "to")
                ]
                for index in list(pending):
                    wall_points = [
                        (float(walls[index][field][0]), float(walls[index][field][2]))
                        for field in ("from", "to")
                    ]
                    if any(
                        math.hypot(first[0] - second[0], first[1] - second[1]) <= 0.05
                        for first in component_points for second in wall_points
                    ):
                        pending.remove(index)
                        component.add(index)
                        changed = True
            connected_walls = [walls[index] for index in component]
            xs = [
                float(point) for wall in connected_walls
                for point in (wall["from"][0], wall["to"][0])
            ]
            zs = [
                float(point) for wall in connected_walls
                for point in (wall["from"][2], wall["to"][2])
            ]
            volume_footprints.add(tuple(round(value, 2) for value in (
                min(xs), min(zs), max(xs), max(zs),
            )))

    # 联合外轮廓会把相接矩形编译成一个连通墙组；凹多边形仍代表多个体量层次，
    # 不能再依赖旧的“重复矩形墙圈数量”来证明复杂度。
    articulated_levels = sum(1 for walls in wall_groups.values() if len(walls) > 4)
    resolved_volume_footprint_count = max(
        len(volume_footprints),
        1 + articulated_levels if volume_footprints else 0,
    )
    overlapping_column_count = 0
    for index, first in enumerate(columns):
        for second in columns[index + 1:]:
            vertical_overlap = min(first[1] + first[3], second[1] + second[3]) - max(first[1], second[1])
            horizontal_distance = math.hypot(first[0] - second[0], first[2] - second[2])
            if vertical_overlap > 0.05 and horizontal_distance < first[4] + second[4] - 0.02:
                overlapping_column_count += 1

    complexity = plan.get("complexity", {}) if isinstance(plan, dict) else {}
    level = str(complexity.get("level") or "standard")
    structural_count = sum(
        counts.get(item, 0) for item in ("wall", "floor", "column", "beam", "stair")
    )
    volume_target = min(
        int(complexity.get("min_volumes", 1)),
        max(1, len(plan.get("volumes", []))),
    )
    target = int(complexity.get("target_structural_elements", 6))
    massing = plan.get("massing", {})
    schematic = str(massing.get("representation_mode") or "full") == "schematic"
    floor_height = float(massing.get("floor_height", 3.2))
    plan_volumes = [
        volume for volume in plan.get("volumes", [])
        if isinstance(volume, dict)
    ]
    modeled_floors = int(massing.get("modeled_floors", massing.get("floors", 1)))
    geometry = blueprint.get("geometry", {}) if isinstance(blueprint, dict) else {}
    templates = geometry.get("templates", {}) if isinstance(geometry, dict) else {}
    stair_template_ids = {
        str(template_id)
        for template_id, template in (templates.items() if isinstance(templates, dict) else [])
        if isinstance(template, dict) and template.get("type") == "stair"
    }
    stair_instance_count = sum(
        1 for instance in geometry.get("instances", [])
        if isinstance(instance, dict) and str(instance.get("ref") or "") in stair_template_ids
    ) if isinstance(geometry, dict) and isinstance(geometry.get("instances"), list) else 0
    has_stair = counts.get("stair", 0) > 0 or stair_instance_count > 0
    has_core = any(
        isinstance(element, dict)
        and element.get("type") == "wall"
        and str(element.get("id") or "").startswith("wall_core_")
        for element in elements
    )
    vertical_strategy = str(
        (plan.get("circulation") or {}).get("vertical_strategy") or "stair"
    )
    circulation_valid = (
        modeled_floors <= 1
        or vertical_strategy == "stair" and has_stair
        or vertical_strategy == "core_and_stair" and has_stair and has_core
    )
    expected_plates = {
        "geometry": {"elements": [
            {"id": f"expected_floor_{index}", "type": "floor",
             "from": [plate["bounds"][0], plate["elevation"], plate["bounds"][1]],
             "to": [plate["bounds"][2], plate["elevation"], plate["bounds"][3]],
             "thickness": 0.2}
            for index, plate in enumerate(_resolve_floor_plate_plan(plan_volumes, modeled_floors, floor_height))
        ] + [element for element in elements if element.get("type") == "stair"]}
    }
    cut_stair_openings(expected_plates)
    expected_floor_layouts = {
        tuple(round(value, 2) for value in (
            plate["from"][1], plate["from"][0], plate["from"][2], plate["to"][0], plate["to"][2],
        ))
        for plate in expected_plates["geometry"]["elements"] if plate["type"] == "floor"
    }
    expected_wall_base_levels = {
        round(level * floor_height, 2) for level in range(modeled_floors)
    }
    checks = {
        "structural_element_target": structural_count >= target,
        "volume_footprint_target": resolved_volume_footprint_count >= volume_target,
        "volume_plan_conformance": (
            True if schematic
            else (not expected_floor_layouts or floor_layouts == expected_floor_layouts)
        ),
        "structural_type_diversity": len([value for value in counts.values() if value]) >= 3,
        "storey_wall_levels": (
            True if schematic
            else expected_wall_base_levels.issubset(wall_base_levels)
        ),
        "vertical_circulation": circulation_valid,
        "duplicate_wall_free": duplicate_wall_count == 0,
        "valid_wall_hosts": not degenerate_wall_ids,
        "overlapping_column_free": overlapping_column_count == 0,
    }
    realization_checks = (
        checks["volume_plan_conformance"],
        checks["storey_wall_levels"],
        checks["vertical_circulation"],
        checks["duplicate_wall_free"],
        checks["valid_wall_hosts"],
        checks["overlapping_column_free"],
    )
    return {
        "level": level,
        "meets_target": (
            (level == "minimal" and checks["valid_wall_hosts"])
            or (
                all(realization_checks)
                and (level != "detailed" or all(checks.values()))
            )
        ),
        "checks": checks,
        "structural_element_count": structural_count,
        "target_structural_elements": target,
        "floor_footprint_count": len(floor_footprints),
        "volume_footprint_count": resolved_volume_footprint_count,
        "floor_layout_count": len(floor_layouts),
        "expected_floor_layout_count": len(expected_floor_layouts),
        "target_volume_footprints": volume_target,
        "duplicate_wall_count": duplicate_wall_count,
        "degenerate_wall_ids": degenerate_wall_ids,
        "overlapping_column_count": overlapping_column_count,
        "element_type_counts": counts,
    }


#: 电梯井的**设备尺寸**（外廓，含两侧各 0.2m 混凝土井壁）：单井净空 2.0×2.2m，
#: 双联 4.2×2.2m。井道不是"按建筑宽深等比缩放"的房间，所以不参与 `width*0.24`
#: 这类推导 —— 一推导就会既失真（长条井道不像电梯）又跑出平面轮廓。
_ELEVATOR_SHAFT_SINGLE_WIDTH = 2.4
_ELEVATOR_SHAFT_TWIN_WIDTH = 4.6
_ELEVATOR_SHAFT_DEPTH = 2.6
#: 井道带与楼梯带之间的净距。
_VERTICAL_TRANSPORT_GAP = 0.3


def _resolve_vertical_transport_layout(
    footprint: list[float],
    *,
    floor_height: float,
    stair_width: float,
) -> dict[str, Any] | None:
    """在公共投影区内沿长轴依次排布「电梯井」与「楼梯」，两者互不重叠。

    旧实现把核心筒按建筑**包围盒**居中、尺寸取 ``width*0.24 / depth*0.28``，
    两个后果都是实测出来的：16×12 的 L 形平面上，核心筒 4.4×4.8 里有
    3.5×3.4m 悬在建筑轮廓之外；而且那是个 2.1m 宽 × 4.8m 深的长条井道，
    并不像电梯。这里改为：井道取固定设备尺寸（放得下双联时取双联，
    否则单井），楼梯沿长轴另占一段，整体在公共区内居中。

    返回 ``None`` 表示公共区放不下井道 —— 此时不生成核心筒，而不是硬塞。
    """

    rx0, rz0, rx1, rz1 = (float(value) for value in footprint)
    span_x = rx1 - rx0
    span_z = rz1 - rz0
    short_span = min(span_x, span_z)
    long_span = max(span_x, span_z)
    long_axis_z = span_z >= span_x

    twin = short_span >= _ELEVATOR_SHAFT_TWIN_WIDTH + 0.4
    shaft_width = _ELEVATOR_SHAFT_TWIN_WIDTH if twin else _ELEVATOR_SHAFT_SINGLE_WIDTH
    if short_span < shaft_width + 0.4:
        return None

    available = long_span - _ELEVATOR_SHAFT_DEPTH - _VERTICAL_TRANSPORT_GAP
    stair_run = min(max(1.2, float(floor_height) * 1.65), available - 0.4)
    if stair_run < 1.2:
        return None
    lead = (long_span - (_ELEVATOR_SHAFT_DEPTH + _VERTICAL_TRANSPORT_GAP + stair_run)) / 2
    stair_width = min(float(stair_width), short_span - 0.4)

    if long_axis_z:
        short_center = (rx0 + rx1) / 2
        core = [
            short_center - shaft_width / 2, rz0 + lead,
            short_center + shaft_width / 2, rz0 + lead + _ELEVATOR_SHAFT_DEPTH,
        ]
        stair_start = [short_center, core[3] + _VERTICAL_TRANSPORT_GAP]
        stair_end = [short_center, stair_start[1] + stair_run]
    else:
        short_center = (rz0 + rz1) / 2
        core = [
            rx0 + lead, short_center - shaft_width / 2,
            rx0 + lead + _ELEVATOR_SHAFT_DEPTH, short_center + shaft_width / 2,
        ]
        stair_start = [core[2] + _VERTICAL_TRANSPORT_GAP, short_center]
        stair_end = [stair_start[0] + stair_run, short_center]

    return {
        "core": [round(value, 3) for value in core],
        "twin": twin,
        # 候梯面/分隔墙的朝向由长轴决定，`_append_vertical_core` 必须知道，
        # 否则会把井道「进深」当「面宽」切开。
        "long_axis_z": bool(long_axis_z),
        "stair": {
            "bounds": [round(float(value), 3) for value in footprint],
            "start": [round(value, 3) for value in stair_start],
            "end": [round(value, 3) for value in stair_end],
            "width": round(stair_width, 3),
        },
    }


def _append_vertical_core(
    elements: list[dict[str, Any]],
    *,
    core: list[float],
    twin: bool,
    long_axis_z: bool,
    total_height: float,
    floor_height: float,
) -> None:
    """核心筒（电梯井）四壁 + 分隔墙，逐层带电梯门洞。

    井道外廓由 :func:`_resolve_vertical_transport_layout` 在公共投影区内给定
    （双联井 4.6×2.6、单井 2.4×2.6，均为含 0.2m 混凝土井壁的设备尺寸），
    本函数不再自行推导尺寸。

    **朝向不许硬编码在 x 轴上**：布局函数把井道放在公共区长轴的起点端、楼梯在外侧，
    所以候梯面恒为「长轴起点端那面墙」（长轴沿 z 时是 front、沿 x 时是 left），
    而分隔墙垂直于候梯面（＝垂直于轿厢并排方向）。早期实现把这两处都写死在 x 轴：
    长轴沿 x 时，井道的「进深」被当「面宽」对半切开，双联井被切成两格
    1.0×4.2m 的长条 —— 修复器只能把轿厢宽度夹到 0.9m（实测），形同电话亭。

    门洞：每层朝候梯面开门（双联井两个、单井一个居中），底层不开门
    （电梯不向基坑开门，也避免一层直接被洞贯穿）。
    楼板开口由组件生成阶段的 `_cut_core_shaft_openings` 在合并骨架后处理。
    """
    x0, z0, x1, z1 = (float(value) for value in core)
    mid_x = (x0 + x1) / 2
    mid_z = (z0 + z1) / 2
    core_runs: list[tuple[str, float, float, float, float]] = [
        ("front", x0, z0, x1, z0),
        ("right", x1, z0, x1, z1),
        ("back", x1, z1, x0, z1),
        ("left", x0, z1, x0, z0),
    ]
    if long_axis_z:
        # 长轴沿 z → 候梯面是 front（跨 x）、分隔墙沿 z 立在中线 x 上。
        if twin:
            core_runs.append(("partition", mid_x, z0, mid_x, z1))
        door_wall_side = "front"
        shaft_span = x1 - x0
    else:
        # 长轴沿 x → 候梯面是 left（跨 z、方向 z1→z0）、分隔墙沿 x 卧在中线 z 上。
        if twin:
            core_runs.append(("partition", x0, mid_z, x1, mid_z))
        door_wall_side = "left"
        shaft_span = z1 - z0
    # 🔴 分隔墙只在**双联井**里存在：单轿厢井再加一道分隔墙，会把 2.4m 面宽切成
    # 两格 0.9m（实测），而单井那扇居中的门恰好压在分隔墙身上 —— 井与门一起作废。
    # 电梯门洞尺寸：宽 0.9m（门扇 0.8m 级）、高 2.1m，双联井沿候梯面对称布置。
    # `from[0]` 是沿宿主墙从 `from` 端点起的距离，且指向门洞**左边缘**（不是中心）——
    # 所以这里要扣掉半个门宽；候梯墙的长度恒等于井道面宽，两种朝向下偏移量同号同值。
    door_width = 0.9
    door_height = min(2.1, max(1.8, floor_height - 1.0))
    door_offsets = [
        round(shaft_span * ratio - door_width / 2, 3)
        for ratio in ((0.25, 0.75) if twin else (0.5,))
    ]
    doors_per_floor = max(1, round(total_height / floor_height))
    for level in range(doors_per_floor):
        base_y = level * floor_height
        top_y = base_y + floor_height
        level_offsets = [] if level == 0 else door_offsets
        level_suffix = f"{level + 1}" if doors_per_floor > 1 else ""
        for side, start_x, start_z, end_x, end_z in core_runs:
            wall_id = f"wall_core_{side}_{level_suffix}" if doors_per_floor > 1 else f"wall_core_{side}"
            wall = {
                "type": "wall", "id": wall_id,
                "from": [start_x, round(base_y, 3), start_z],
                "to": [end_x, round(top_y, 3), end_z],
                "thickness": 0.2, "material": "concrete",
            }
            if side == door_wall_side and level_offsets:
                # 候梯墙逐层切出电梯门洞（用 opening 组件表达，
                # 由 wild-core resolver 在渲染时从墙上真实挖洞）。
                for door_index, offset in enumerate(level_offsets, start=1):
                    elements.append({
                        "type": "opening",
                        "id": f"elevator_door_{level + 1}_{door_index}",
                        "parentWall": wall_id,
                        "from": [offset, round(base_y, 3), 0],
                        "width": door_width,
                        "height": door_height,
                        "style": "rectangular",
                        "depth": 0.2,
                    })
            elements.append(wall)


def _cut_core_shaft_openings(blueprint: dict[str, Any], floor_height: float) -> None:
    """在跨越电梯井的楼板上挖井道开口（各层楼板都要留洞，电梯才能贯通）。

    复用 ``cut_stair_openings`` 的拆板逻辑：把与井道投影相交的楼板拆成
    「井洞 + 周围环板」，保留材质与厚度。只处理 core_and_stair 骨架生成的
    ``wall_core_*`` 围合出的矩形投影。
    """
    elements = blueprint.get("geometry", {}).get("elements", [])
    core_walls = [
        element for element in elements
        if element.get("type") == "wall" and str(element.get("id") or "").startswith("wall_core_")
    ]
    if not core_walls:
        return
    xs: list[float] = []
    zs: list[float] = []
    for wall in core_walls:
        xs.extend((wall["from"][0], wall["to"][0]))
        zs.extend((wall["from"][2], wall["to"][2]))
    shaft = (min(xs) + 0.2, min(zs) + 0.2, max(xs) - 0.2, max(zs) - 0.2)

    walls_only = blueprint
    # 走统一的楼板拆分通道：把井道投影临时注册为一个“楼梯式遮挡”，
    # 拆完再移除占位，避免引入第二套拆板实现。
    placeholder = {
        "type": "stair",
        "id": "__core_shaft_placeholder__",
        "from": [shaft[0], 0.0, shaft[1]],
        "to": [shaft[2], 0.0, shaft[3]],
        "width": 0.1,
    }
    elements.append(placeholder)
    try:
        from app.agent.generation.stair_openings import cut_stair_openings

        cut_stair_openings(walls_only)
    finally:
        try:
            elements.remove(placeholder)
        except ValueError:
            pass


def build_deterministic_skeleton(plan: dict[str, Any], user_message: str = "") -> dict[str, Any]:
    """在骨架模型不可用或复杂度不足时生成可校验的体量化概念骨架。

    full 模式按方案 volumes 落实组合体量；schematic 模式仍使用完整总高度外壳，
    避免一次生成数百层元素。
    """
    normalized = normalize_architecture_plan(
        plan,
        user_message,
        plan.get("complexity") if isinstance(plan, dict) else None,
    )
    massing = normalized["massing"]
    width = float(massing["width"])
    depth = float(massing["depth"])
    floors = int(massing["floors"])
    modeled_floors = int(massing["modeled_floors"])
    floor_height = float(massing["floor_height"])
    schematic = massing["representation_mode"] == "schematic"
    total_height = floors * floor_height
    volumes = normalized.get("volumes") or _fallback_volumes(
        width, depth, modeled_floors, normalized["complexity"],
    )
    vertical_strategy = str(
        (normalized.get("circulation") or {}).get("vertical_strategy") or "stair"
    )
    want_stair = vertical_strategy in {"stair", "core_and_stair"} and floors > 1
    want_core = vertical_strategy == "core_and_stair" and floors > 1
    level_regions = []
    for level in range(1, modeled_floors + 1):
        level_regions.append([
            [
                float(volume.get("x", 0.0)),
                float(volume.get("z", 0.0)),
                float(volume.get("x", 0.0)) + float(volume.get("width", width)),
                float(volume.get("z", 0.0)) + float(volume.get("depth", depth)),
            ]
            for volume in volumes
            if int(volume.get("start_floor", 1)) <= level <= int(volume.get("end_floor", modeled_floors))
        ])
    preferred_stair_width = min(1.8, max(1.0, width * 0.08))
    footprint = shared_footprint(level_regions)
    # 核心筒与楼梯必须在公共区内分工：旧实现里核心筒按包围盒居中、楼梯按公共区
    # 居中，两者都往中间挤，实测核心筒把整跑楼梯压在井道里。
    vertical_layout = (
        _resolve_vertical_transport_layout(
            footprint,
            floor_height=floor_height,
            stair_width=preferred_stair_width,
        )
        if want_core and footprint is not None
        else None
    )
    if want_core and vertical_layout is None:
        # 公共区放不下井道设备尺寸 → 降级为纯楼梯，而不是把井道硬塞进建筑里。
        want_core = False
    stair_layout = (
        vertical_layout["stair"] if vertical_layout is not None
        else shared_stair_layout(level_regions, floor_height, preferred_stair_width)
    ) if want_stair else None
    if want_stair and stair_layout is None:
        stair_x = max(1.0, min(width - 1.0, width * 0.2))
        stair_z0 = max(0.8, min(depth - 2.0, depth * 0.2))
        stair_z1 = max(stair_z0 + 1.0, min(depth - 0.8, depth * 0.65))
        stair_layout = {
            "start": [stair_x, stair_z0],
            "end": [stair_x, stair_z1],
            "width": preferred_stair_width,
        }

    elements: list[dict[str, Any]] = []
    templates: dict[str, dict[str, Any]] = {}
    instances: list[dict[str, Any]] = []
    schematic_zones: list[dict[str, Any]] = []
    if schematic:
        schematic_zones = _schematic_volume_zones(volumes, floors, modeled_floors)
        if not schematic_zones:
            schematic_zones = [{
                "start_floor": 1,
                "end_floor": floors,
                "volumes": [{
                    "id": "main", "x": 0.0, "z": 0.0,
                    "width": width, "depth": depth,
                    "semantic_start_floor": 1, "semantic_end_floor": floors,
                }],
            }]
        shell_material = "glass" if normalized.get("curtain_wall") else "wall_finish"
        for zone_index, zone in enumerate(schematic_zones, start=1):
            base_y = (int(zone["start_floor"]) - 1) * floor_height
            top_y = int(zone["end_floor"]) * floor_height
            segments = _resolve_union_wall_segments(zone["volumes"])
            side_counts: dict[str, int] = {}
            for segment in segments:
                side = str(segment["side"])
                side_counts[side] = side_counts.get(side, 0) + 1
                start_x, start_z = segment["from"]
                end_x, end_z = segment["to"]
                elements.append({
                    "type": "wall",
                    "id": f"wall_{side}_shell_{zone_index}_{side_counts[side]}",
                    "from": [start_x, base_y, start_z],
                    "to": [end_x, top_y, end_z],
                    "thickness": 0.24,
                    "material": shell_material,
                })
            if normalized.get("curtain_wall"):
                _append_curtain_wall_grid(
                    elements,
                    segments,
                    base_y=base_y,
                    top_y=top_y,
                    start_floor=int(zone["start_floor"]),
                    end_floor=int(zone["end_floor"]),
                    floor_height=floor_height,
                    facades=normalized.get("facades", {}),
                    zone_index=zone_index,
                )

        mapped_volumes = _schematic_volume_ranges(volumes, floors, modeled_floors)
        ground_volumes = [
            volume for volume in mapped_volumes
            if int(volume["semantic_start_floor"]) <= 1 <= int(volume["semantic_end_floor"])
        ]
        top_volumes = [
            volume for volume in mapped_volumes
            if int(volume["semantic_start_floor"]) <= floors <= int(volume["semantic_end_floor"])
        ]
        for label, elevation, active in (
            ("ground", 0.0, ground_volumes),
            ("top", total_height, top_volumes),
        ):
            for index, volume in enumerate(active, start=1):
                suffix = "" if len(active) == 1 else f"_{index}"
                elements.append({
                    "type": "floor", "id": f"floor_{label}{suffix}",
                    "from": [float(volume["x"]), elevation, float(volume["z"])],
                    "to": [
                        float(volume["x"]) + float(volume["width"]), elevation,
                        float(volume["z"]) + float(volume["depth"]),
                    ],
                    "thickness": 0.2, "material": "concrete",
                })

        if floors > 1:
            for volume in mapped_volumes:
                template_id = (
                    "standard_floor_plate"
                    if len(mapped_volumes) == 1
                    else f"standard_floor_plate_{volume['id']}"
                )
                templates[template_id] = {
                    "type": "floor", "id": template_id,
                    "from": [0.0, 0.0, 0.0],
                    "to": [float(volume["width"]), 0.0, float(volume["depth"])],
                    "thickness": 0.2, "material": "concrete",
                }
            for level in range(1, floors):
                supported_story = level + 1
                for volume in mapped_volumes:
                    if not (
                        int(volume["semantic_start_floor"])
                        <= supported_story
                        <= int(volume["semantic_end_floor"])
                    ):
                        continue
                    template_id = (
                        "standard_floor_plate"
                        if len(mapped_volumes) == 1
                        else f"standard_floor_plate_{volume['id']}"
                    )
                    instances.append({
                        "id": f"floor_standard_{level}_{volume['id']}",
                        "ref": template_id,
                        "position": [
                            float(volume["x"]), round(level * floor_height, 3),
                            float(volume["z"]),
                        ],
                    })

            if stair_layout:
                start = stair_layout["start"]
                end = stair_layout["end"]
                for direction, lower, upper in (
                    ("forward", start, end),
                    ("reverse", end, start),
                ):
                    template_id = f"standard_storey_stair_{direction}"
                    templates[template_id] = {
                        "type": "stair", "id": template_id,
                        "from": [lower[0], 0.0, lower[1]],
                        "to": [upper[0], floor_height, upper[1]],
                        "width": stair_layout["width"],
                        "material": "concrete",
                    }
                instances.extend({
                    "id": f"stair_standard_{level}_{level + 1}",
                    "ref": (
                        "standard_storey_stair_forward"
                        if level % 2 else "standard_storey_stair_reverse"
                    ),
                    "position": [0.0, round((level - 1) * floor_height, 3), 0.0],
                } for level in range(1, floors))

        if want_core and vertical_layout is not None:
            _append_vertical_core(
                elements,
                core=vertical_layout["core"],
                twin=bool(vertical_layout["twin"]),
                long_axis_z=bool(vertical_layout["long_axis_z"]),
                total_height=total_height,
                floor_height=floor_height,
            )
    else:
        detailed = normalized["complexity"]["level"] == "detailed"
        floor_plates = _resolve_floor_plate_plan(volumes, modeled_floors, floor_height)
        for level in range(1, modeled_floors + 1):
            active_volumes = [
                volume for volume in volumes
                if int(volume["start_floor"]) <= level <= int(volume["end_floor"])
            ] or [
                {
                    "id": "main", "x": 0.0, "z": 0.0,
                    "width": width, "depth": depth,
                }
            ]
            base_y = (level - 1) * floor_height
            top_y = level * floor_height
            for plate in (item for item in floor_plates if item["level"] == level):
                x0, z0, x1, z1 = plate["bounds"]
                elements.append({
                    "type": "floor",
                    "id": f"floor_{level}_{plate['volume_id']}",
                    "from": [x0, plate["elevation"], z0],
                    "to": [x1, plate["elevation"], z1],
                    "thickness": 0.2,
                    "material": "concrete",
                })
            if len(active_volumes) > 1:
                side_counts: dict[str, int] = {}
                for segment in _resolve_union_wall_segments(active_volumes):
                    side = str(segment["side"])
                    side_counts[side] = side_counts.get(side, 0) + 1
                    start_x, start_z = segment["from"]
                    end_x, end_z = segment["to"]
                    elements.append({
                        "type": "wall",
                        "id": f"wall_{side}_{level}_{side_counts[side]}",
                        "from": [start_x, base_y, start_z],
                        "to": [end_x, top_y, end_z],
                        "thickness": 0.24,
                        "material": "wall_finish",
                    })
                continue

            for volume in active_volumes:
                volume_id = str(volume["id"])
                x0 = float(volume["x"])
                z0 = float(volume["z"])
                x1 = x0 + float(volume["width"])
                z1 = z0 + float(volume["depth"])
                suffix = f"{level}_{volume_id}" if detailed or len(active_volumes) > 1 else str(level)
                elements.extend([
                    {
                        "type": "wall", "id": f"wall_front_{suffix}",
                        "from": [x0, base_y, z0], "to": [x1, top_y, z0],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                    {
                        "type": "wall", "id": f"wall_right_{suffix}",
                        "from": [x1, base_y, z0], "to": [x1, top_y, z1],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                    {
                        "type": "wall", "id": f"wall_back_{suffix}",
                        "from": [x1, base_y, z1], "to": [x0, top_y, z1],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                    {
                        "type": "wall", "id": f"wall_left_{suffix}",
                        "from": [x0, base_y, z1], "to": [x0, top_y, z0],
                        "thickness": 0.24, "material": "wall_finish",
                    },
                ])

    if not schematic and want_core and vertical_layout is not None:
        _append_vertical_core(
            elements,
            core=vertical_layout["core"],
            twin=bool(vertical_layout["twin"]),
            long_axis_z=bool(vertical_layout["long_axis_z"]),
            total_height=total_height,
            floor_height=floor_height,
        )

    if not schematic and modeled_floors > 1 and stair_layout:
        stair_start = stair_layout["start"]
        stair_end = stair_layout["end"]
        for level in range(modeled_floors - 1):
            base_y = level * floor_height
            lower, upper = (
                (stair_start, stair_end)
                if level % 2 == 0
                else (stair_end, stair_start)
            )
            elements.append({
                "type": "stair",
                "id": f"stair_{level + 1}_{level + 2}",
                "from": [lower[0], round(base_y, 3), lower[1]],
                "to": [upper[0], round(base_y + floor_height, 3), upper[1]],
                "width": stair_layout["width"],
                "material": "concrete",
            })

    if normalized["complexity"]["level"] == "detailed" and not schematic:
        radius = min(0.35, max(0.16, min(width, depth) * 0.015))
        column_keys: set[tuple[float, float, float, float]] = set()
        for volume in volumes:
            x0 = float(volume["x"])
            z0 = float(volume["z"])
            x1 = x0 + float(volume["width"])
            z1 = z0 + float(volume["depth"])
            beam_inset = min(0.35, float(volume["width"]) * 0.08, float(volume["depth"]) * 0.08)
            column_inset = min(
                max(radius + 0.04, 0.18),
                float(volume["width"]) * 0.2,
                float(volume["depth"]) * 0.2,
            )
            base_y = (int(volume["start_floor"]) - 1) * floor_height
            volume_height = (int(volume["end_floor"]) - int(volume["start_floor"]) + 1) * floor_height
            if int(volume["start_floor"]) > 1:
                base_y += 0.2
                volume_height = max(0.5, volume_height - 0.2)
            volume_id = str(volume["id"])
            corners = (
                (x0 + column_inset, z0 + column_inset),
                (x1 - column_inset, z0 + column_inset),
                (x1 - column_inset, z1 - column_inset),
                (x0 + column_inset, z1 - column_inset),
            )
            for index, (x, z) in enumerate(corners, start=1):
                column_key = (
                    round(x, 3), round(z, 3), round(base_y, 3),
                    round(base_y + volume_height, 3),
                )
                if column_key in column_keys:
                    continue
                column_keys.add(column_key)
                elements.append({
                    "type": "column", "id": f"column_{volume_id}_{index}",
                    "base": [x, base_y, z], "height": volume_height,
                    "bottomRadius": radius, "topRadius": radius,
                    "style": "modern", "material": "concrete",
                })
            beam_y = base_y + volume_height
            elements.append({
                "type": "beam", "id": f"beam_main_{volume_id}",
                "from": [x0 + beam_inset, beam_y, (z0 + z1) / 2],
                "to": [x1 - beam_inset, beam_y, (z0 + z1) / 2],
                "crossSection": "rect", "width": 0.18, "height": 0.28,
                "material": "concrete",
            })
    elif schematic:
        radius = min(0.6, max(0.2, min(width, depth) * 0.012))
        column_keys: set[tuple[float, float, float, float]] = set()
        for zone_index, zone in enumerate(schematic_zones, start=1):
            base_y = (int(zone["start_floor"]) - 1) * floor_height
            zone_height = (
                int(zone["end_floor"]) - int(zone["start_floor"]) + 1
            ) * floor_height
            segment_count = max(1, math.ceil(zone_height / 45.0))
            segment_height = zone_height / segment_count
            for volume in zone["volumes"]:
                x0 = float(volume["x"])
                z0 = float(volume["z"])
                x1 = x0 + float(volume["width"])
                z1 = z0 + float(volume["depth"])
                inset = min(
                    0.5,
                    max(radius + 0.04, 0.2),
                    float(volume["width"]) * 0.2,
                    float(volume["depth"]) * 0.2,
                )
                corners = (
                    (x0 + inset, z0 + inset),
                    (x1 - inset, z0 + inset),
                    (x1 - inset, z1 - inset),
                    (x0 + inset, z1 - inset),
                )
                for part in range(segment_count):
                    part_base = base_y + part * segment_height
                    for corner_index, (x, z) in enumerate(corners, start=1):
                        key = (
                            round(x, 3), round(z, 3), round(part_base, 3),
                            round(part_base + segment_height, 3),
                        )
                        if key in column_keys:
                            continue
                        column_keys.add(key)
                        elements.append({
                            "type": "column",
                            "id": (
                                f"column_zone_{zone_index}_{volume['id']}_"
                                f"{part + 1}_{corner_index}"
                            ),
                            "base": [x, round(part_base, 3), z],
                            "height": round(segment_height, 3),
                            "bottomRadius": radius,
                            "topRadius": radius,
                            "style": "modern",
                            "material": "concrete",
                        })
    elif normalized["profile"] in {"long_span_public", "high_rise"}:
        radius = min(0.6, max(0.2, min(width, depth) * 0.012))
        for index, (x, z) in enumerate((
            (0.5, 0.5), (width - 0.5, 0.5),
            (width - 0.5, depth - 0.5), (0.5, depth - 0.5),
        ), start=1):
            elements.append({
                "type": "column", "id": f"column_corner_{index}",
                "base": [x, 0.0, z], "height": total_height,
                "bottomRadius": radius, "topRadius": radius,
                "style": "modern", "material": "concrete",
            })

    blueprint = {
        "meta": {
            "version": "1.1",
            "type": "building",
            "name": str(normalized.get("concept") or "确定性回退建筑")[:80],
        },
        "geometry": {
            "elements": elements,
            "components": [],
            **({"templates": templates, "instances": instances} if templates else {}),
        },
        "materials": {
            "concrete": {
                "baseColor": [0.72, 0.72, 0.72], "roughness": 0.65,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "wall_finish": {
                "baseColor": [0.86, 0.84, 0.80], "roughness": 0.72,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "wood": {
                "baseColor": [0.42, 0.24, 0.12], "roughness": 0.68,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "metal": {
                "baseColor": [0.16, 0.17, 0.18], "roughness": 0.34,
                "metallic": 0.7, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
            "glass": {
                "baseColor": [0.52, 0.70, 0.82], "roughness": 0.12,
                "metallic": 0.0, "albedo": 1.0,
                "materialClass": "glass", "transmission": 0.9,
                "ior": 1.5, "thickness": 0.12,
                "lightingCondition": "D65_noon",
            },
            "roof": {
                "baseColor": [0.30, 0.31, 0.33], "roughness": 0.75,
                "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon",
            },
        },
        "behaviors": {},
    }
    cut_stair_openings(blueprint)
    _cut_core_shaft_openings(blueprint, floor_height)
    return blueprint
