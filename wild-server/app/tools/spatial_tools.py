"""
Spatial Validation Tools —— 空间校验 + 自动修正工具

每个工具都是 @tool 装饰的纯函数：
  - 输入：完整的 Blueprint dict
  - 输出：人类可读的校验结果文本
  - 用途：
      1. 注册给 LangChain Agent（LLM 可选调用）
      2. 由 agent_service.run_validation_pipeline() 按固定顺序强制执行

校验流水线顺序（Structure → Schema → Reference → Geometry → Fix → Collision）：
  1. validate_blueprint_structure      — 顶层结构完整性、ID 唯一性
  2. validate_element_required_fields  — 各构件必填字段 + 枚举值合法性
  3. validate_reference_integrity      — 跨构件引用合法性（parentWall、templateId 等）
  4. validate_opening_coords           — 门窗沿墙距离格式检查
  5. validate_wall_junctions           — 墙体转角端点对齐检查
  6. validate_stair_alignment          — 楼梯端点高度对齐检查
  7. validate_roof_coverage            — 屋顶 span/depth 覆盖范围检查
  8. fix_opening_coords                — 自动修正疑似世界坐标的门窗 from[0]
     → 修正后重跑 validate_opening_coords（由流水线调度，非工具自身）
  9. validate_collision                — 构件碰撞/穿插/悬空/重叠检测

扩展方式：新增 def validate_xxx(bp: dict) -> str 并在 agent_service.PIPELINE 中注册。
"""
import math
from langchain.tools import tool

from app.agent.spatial_geometry import point_in_regions, shared_stair_layout


# 门窗洞口必须与父墙中心面保持接近；超过该值通常意味着 LLM 把世界 X/Z
# 误写进了局部法向偏移 from[2]。
MAX_OPENING_NORMAL_OFFSET = 0.25

# 这三类组件都会在父墙上切出真实洞口。校验和修复必须把它们作为同一类
# 空间对象处理，否则凸窗节点可与门窗节点各自“校验通过”，合并后却重复切洞。
WALL_OPENING_COMPONENT_TYPES = {"door", "window", "bay_window"}


def _floor_regions_by_level(elements: list[dict]) -> list[tuple[float, list[list[float]]]]:
    grouped: dict[float, list[list[float]]] = {}
    for item in elements:
        if item.get("type") != "floor":
            continue
        start, end = item.get("from"), item.get("to")
        if not isinstance(start, list) or not isinstance(end, list):
            continue
        if len(start) != 3 or len(end) != 3:
            continue
        try:
            y = round(float(start[1]), 3)
            bounds = [
                min(float(start[0]), float(end[0])),
                min(float(start[2]), float(end[2])),
                max(float(start[0]), float(end[0])),
                max(float(start[2]), float(end[2])),
            ]
        except (TypeError, ValueError):
            continue
        grouped.setdefault(y, []).append(bounds)
    return sorted(grouped.items())


def collect_stair_placement_issues(blueprint: dict) -> list[dict[str, object]]:
    """检查楼梯端点是否落在楼板上，以及相邻梯段是否在同一平台衔接。"""

    elements = _get_elements(blueprint)
    stairs = [item for item in elements if item.get("type") == "stair"]
    floor_levels = _floor_regions_by_level(elements)
    issues: list[dict[str, object]] = []

    def supported(point: tuple[float, float], y: float) -> bool:
        matching = [
            regions for level_y, regions in floor_levels
            if abs(level_y - y) <= 0.25
        ]
        return bool(matching) and any(
            point_in_regions(point, regions)
            for regions in matching
        )

    valid_stairs: list[tuple[dict, list, list]] = []
    for stair in stairs:
        start, end = stair.get("from"), stair.get("to")
        if not isinstance(start, list) or not isinstance(end, list):
            continue
        if len(start) != 3 or len(end) != 3:
            continue
        try:
            start_y, end_y = float(start[1]), float(end[1])
        except (TypeError, ValueError):
            continue
        run_x = float(end[0]) - float(start[0])
        run_z = float(end[2]) - float(start[2])
        run_length = math.hypot(run_x, run_z)
        half_width = max(0.0, float(stair.get("width") or 0.0) / 2)
        if run_length > 0.001:
            offset_x = -run_z / run_length * half_width
            offset_z = run_x / run_length * half_width
        else:
            offset_x, offset_z = half_width, 0.0

        def endpoint_supported(point: list, y: float) -> bool:
            center_x, center_z = float(point[0]), float(point[2])
            return all(
                supported((center_x + factor * offset_x,
                           center_z + factor * offset_z), y)
                for factor in (-1.0, 0.0, 1.0)
            )

        stair_id = str(stair.get("id") or "?")
        if not endpoint_supported(start, start_y):
            issues.append({
                "code": "stair_start_outside_floor",
                "message": f"楼梯 {stair_id} 起点不在 {start_y:g}m 楼板范围内",
                "entity_ids": (stair_id,),
            })
        if not endpoint_supported(end, end_y):
            issues.append({
                "code": "stair_end_outside_floor",
                "message": f"楼梯 {stair_id} 终点不在 {end_y:g}m 楼板范围内",
                "entity_ids": (stair_id,),
            })
        valid_stairs.append((stair, start, end))

    valid_stairs.sort(key=lambda item: float(item[1][1]))
    for previous, current in zip(valid_stairs, valid_stairs[1:]):
        previous_stair, _, previous_end = previous
        current_stair, current_start, _ = current
        if abs(float(previous_end[1]) - float(current_start[1])) > 0.25:
            continue
        horizontal_gap = math.hypot(
            float(previous_end[0]) - float(current_start[0]),
            float(previous_end[2]) - float(current_start[2]),
        )
        if horizontal_gap > 0.35:
            previous_id = str(previous_stair.get("id") or "?")
            current_id = str(current_stair.get("id") or "?")
            issues.append({
                "code": "disconnected_stair_flights",
                "message": (
                    f"相邻梯段 {previous_id} 与 {current_id} 的平台错开 "
                    f"{horizontal_gap:.2f}m"
                ),
                "entity_ids": (previous_id, current_id),
            })
    return issues


# 辅助函数 —— 不对外暴露，只在本模块内复用
def _get_elements(bp: dict) -> list[dict]:
    """安全获取 elements 列表"""
    if not isinstance(bp, dict):
        return []
    return bp.get("geometry", {}).get("elements", [])


def _is_finite_vector3(value: object) -> bool:
    """判断构件坐标是否能被空间工具安全地当作三维向量读取。"""
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(
            isinstance(coordinate, (int, float))
            and not isinstance(coordinate, bool)
            and math.isfinite(coordinate)
            for coordinate in value
        )
    )


def _safe_coords(vec, field_name: str = "") -> list[float]:
    """将坐标或尺寸强制转为 float 列表，非数值元素抛可定位异常。

    若 LLM 输出了字符串坐标（如 ``from: ["3","0","0"]``）
    或嵌套数组（如 ``from: [[1,0],[2,0]]``），此函数抛出包含字段名
    和具体索引的 ValueError，供上层工具将其转为 ❌ 诊断而非 TypeError 崩溃。
    """
    if not isinstance(vec, (list, tuple)):
        raise ValueError(f"期望数组，实际为 {type(vec).__name__}: {vec!r}")
    result: list[float] = []
    prefix = f"{field_name} " if field_name else ""
    for i, v in enumerate(vec):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            result.append(float(v))
        else:
            raise ValueError(
                f"{prefix}坐标[{i}]={v!r}（类型 {type(v).__name__}）不是有效数值"
            )
    return result


def _get_by_id(bp: dict, eid: str) -> dict | None:
    """按 id 查找元素"""
    for el in _get_elements(bp):
        if el.get("id") == eid:
            return el
    return None


def _component_opening_box(component: dict) -> tuple[str, float, float, float, float] | None:
    """返回墙附着组件在父墙局部平面中的二维包围盒。"""
    from_vec = component.get("from")
    if not isinstance(from_vec, (list, tuple)) or len(from_vec) < 2:
        return None
    try:
        wall_id = str(component.get("parentWall", ""))
        along = float(from_vec[0])
        base_y = float(from_vec[1])
        width = float(component.get("width", 0))
        height = float(component.get("height", 0))
    except (TypeError, ValueError):
        return None
    if not wall_id or width <= 0 or height <= 0:
        return None
    return wall_id, along, base_y, width, height


def _wall_openings_overlap(first: dict, second: dict, tolerance: float = 0.05) -> bool:
    """判断两个组件是否在同一父墙的局部二维平面内实际重叠。"""
    first_box = _component_opening_box(first)
    second_box = _component_opening_box(second)
    if first_box is None or second_box is None or first_box[0] != second_box[0]:
        return False
    _, first_x, first_y, first_w, first_h = first_box
    _, second_x, second_y, second_w, second_h = second_box
    horizontal = min(first_x + first_w, second_x + second_w) - max(first_x, second_x)
    vertical = min(first_y + first_h, second_y + second_h) - max(first_y, second_y)
    return horizontal > tolerance and vertical > tolerance


def _resolve_wall_opening_component_conflicts(blueprint: dict) -> dict:
    """按“门 > 凸窗 > 普通窗”的优先级消除墙洞重叠。

    凸窗与门重叠时，优先占用一个安全的普通窗位置；找不到位置才删除凸窗。
    凸窗占位后会替换同位置的普通窗，避免同一处被两套编译器重复切洞。
    """
    geometry = blueprint.get("geometry", {})
    components = geometry.get("components", [])
    if not isinstance(components, list):
        return {
            "relocated_bay_windows": [],
            "replaced_windows": [],
            "pruned_bay_windows": [],
            "relocated_windows": [],
            "pruned_windows": [],
        }

    walls = {
        item.get("id"): item
        for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("type") == "wall" and item.get("id")
    }
    doors = [item for item in components if item.get("type") == "door"]
    windows = [item for item in components if item.get("type") == "window"]
    bay_windows = [item for item in components if item.get("type") == "bay_window"]
    removed_ids: set[int] = set()
    kept_bays: list[dict] = []
    relocated: list[str] = []
    replaced: list[str] = []
    pruned: list[str] = []
    relocated_windows: list[str] = []
    pruned_windows: list[str] = []

    def available_window_candidates(bay: dict) -> list[dict]:
        candidates = [
            window for window in windows
            if id(window) not in removed_ids
            and _component_opening_box(window) is not None
            and not any(_wall_openings_overlap(window, door) for door in doors)
            and not any(_wall_openings_overlap(window, kept) for kept in kept_bays)
        ]
        bay_box = _component_opening_box(bay)
        bay_wall = bay_box[0] if bay_box else ""
        bay_center = bay_box[1] + bay_box[3] / 2 if bay_box else 0.0
        bay_y = bay_box[2] if bay_box else 0.0

        def rank(window: dict) -> tuple[int, float, float, str]:
            box = _component_opening_box(window)
            assert box is not None
            wall_id, along, base_y, width, _ = box
            return (
                0 if wall_id == bay_wall else 1,
                abs(base_y - bay_y),
                abs(along + width / 2 - bay_center),
                str(window.get("id", "")),
            )

        return sorted(candidates, key=rank)

    for bay in bay_windows:
        conflicts_with_priority = any(
            _wall_openings_overlap(bay, other)
            for other in [*doors, *kept_bays]
        )
        if conflicts_with_priority:
            candidates = available_window_candidates(bay)
            if not candidates:
                removed_ids.add(id(bay))
                pruned.append(str(bay.get("id", "?")))
                continue
            target = candidates[0]
            bay["parentWall"] = target.get("parentWall")
            bay["from"] = list(target.get("from", [0, 0, 0]))
            bay["width"] = target.get("width")
            bay["height"] = target.get("height")
            removed_ids.add(id(target))
            relocated.append(str(bay.get("id", "?")))
            replaced.append(str(target.get("id", "?")))

        for window in windows:
            if id(window) in removed_ids:
                continue
            if _wall_openings_overlap(bay, window):
                removed_ids.add(id(window))
                replaced.append(str(window.get("id", "?")))
        kept_bays.append(bay)

    # 普通窗按原有顺序处理；若与先前普通窗冲突，优先在同一父墙寻找最近
    # 的安全位置，短墙确实放不下时才删除后出现的窗。门/凸窗仍沿用上面的
    # 专用优先级逻辑，避免扩大既有自动修复范围。
    kept_windows: list[dict] = []

    def relocate_plain_window(window: dict, blockers: list[dict]) -> bool:
        box = _component_opening_box(window)
        if box is None:
            return False
        wall_id, original_along, _, width, _ = box
        wall = walls.get(wall_id)
        if wall is None:
            return False
        max_along = _wall_length(wall) - width
        if max_along < -1e-6:
            return False

        candidates = [0.1, max(0.0, max_along - 0.1)]
        for blocker in blockers:
            blocker_box = _component_opening_box(blocker)
            if blocker_box is None or blocker_box[0] != wall_id:
                continue
            blocker_along, blocker_width = blocker_box[1], blocker_box[3]
            candidates.extend([
                blocker_along + blocker_width + 0.1,
                blocker_along - width - 0.1,
            ])

        position = window.get("from")
        if not isinstance(position, list) or len(position) != 3:
            return False
        for candidate in sorted(
            {round(value, 3) for value in candidates},
            key=lambda value: (abs(value - original_along), value),
        ):
            if candidate < -1e-6 or candidate > max_along + 1e-6:
                continue
            position[0] = max(0.0, min(max_along, candidate))
            if not any(_wall_openings_overlap(window, blocker) for blocker in blockers):
                return True
        position[0] = original_along
        return False

    for window in windows:
        if id(window) in removed_ids:
            continue
        blockers = list(kept_windows)
        if any(_wall_openings_overlap(window, blocker) for blocker in blockers):
            if relocate_plain_window(window, blockers):
                relocated_windows.append(str(window.get("id", "?")))
                kept_windows.append(window)
            else:
                removed_ids.add(id(window))
                pruned_windows.append(str(window.get("id", "?")))
            continue
        kept_windows.append(window)

    if removed_ids:
        geometry["components"] = [item for item in components if id(item) not in removed_ids]

    return {
        "relocated_bay_windows": relocated,
        "replaced_windows": list(dict.fromkeys(replaced)),
        "pruned_bay_windows": pruned,
        "relocated_windows": relocated_windows,
        "pruned_windows": pruned_windows,
    }

def _wall_length(wall: dict) -> float:
    """计算墙体在 XZ 平面上的长度（沿墙距离）"""
    f = wall.get("from", [0, 0, 0])
    t = wall.get("to", [0, 0, 0])
    if wall.get("curve"):
        from app.agent.spatial_geometry import curve_points, path_length

        return path_length(curve_points(
            [float(f[0]), float(f[2])],
            [float(t[0]), float(t[2])],
            wall["curve"],
        ))
    dx = t[0] - f[0]
    dz = t[2] - f[2]
    return math.sqrt(dx * dx + dz * dz)


def _wall_vertical_range(wall: dict) -> tuple[float, float]:
    """返回墙体世界坐标中的底部和顶部 Y。"""
    start = wall.get("from", [0, 0, 0])
    end = wall.get("to", [0, 0, 0])
    bottom = min(float(start[1]), float(end[1]))
    height = wall.get("height")
    if isinstance(height, (int, float)) and not isinstance(height, bool) and height > 0:
        return bottom, bottom + float(height)
    return bottom, max(float(start[1]), float(end[1]))


def _infer_story_height(elements: list[dict]) -> float:
    """从楼板标高和已有墙高中推断常用层高；信息不足时使用 3m。"""
    candidates: list[float] = []
    floor_levels = sorted({
        float(coord[1])
        for element in elements
        if element.get("type") == "floor"
        for coord in (element.get("from"), element.get("to"))
        if _is_finite_vector3(coord)
    })
    candidates.extend(
        upper - lower
        for lower, upper in zip(floor_levels, floor_levels[1:])
        if 1.8 <= upper - lower <= 6.0
    )
    for element in elements:
        if element.get("type") != "wall":
            continue
        start = element.get("from")
        end = element.get("to")
        if not _is_finite_vector3(start) or not _is_finite_vector3(end):
            continue
        height = abs(float(end[1]) - float(start[1]))
        if 1.8 <= height <= 6.0:
            candidates.append(height)
    if not candidates:
        return 3.0
    candidates.sort()
    return candidates[len(candidates) // 2]


def _infer_wall_top(elements: list[dict], bottom: float) -> float:
    """优先对齐上一层楼板；顶层墙则沿用推断出的常用层高。"""
    upper_floors = sorted({
        float(coord[1])
        for element in elements
        if element.get("type") == "floor"
        for coord in (element.get("from"), element.get("to"))
        if _is_finite_vector3(coord) and 0.1 < float(coord[1]) - bottom <= 50.0
    })
    return upper_floors[0] if upper_floors else bottom + _infer_story_height(elements)


def _is_structural_wall(wall: dict) -> bool:
    """低矮、纤细的 wall 通常用于栏杆或装饰，不参与结构墙闭合检查。"""
    bottom, top = _wall_vertical_range(wall)
    return (
        top - bottom >= 1.8
        and float(wall.get("thickness", 0)) >= 0.1
    )

def _wall_direction_xz(wall: dict) -> tuple[float, float]:
    """返回墙体在 XZ 平面上的单位方向向量"""
    f = wall.get("from", [0, 0, 0])
    t = wall.get("to", [0, 0, 0])
    dx = t[0] - f[0]
    dz = t[2] - f[2]
    length = math.sqrt(dx * dx + dz * dz)
    if length < 1e-6:
        return (0.0, 0.0)
    return (dx / length, dz / length)


# 检测类 Tool —— 只查不改，返回问题列表

@tool
def validate_blueprint_structure(blueprint: dict) -> str:
    """
    检查 Blueprint 顶层结构是否完整。
    验证 meta、geometry、elements 等必需字段是否存在。

    参数 blueprint: 完整的 Blueprint dict
    """
    issues: list[str] = []

    if "meta" not in blueprint:
        issues.append("❌ 缺少顶层字段 'meta'")
    else:
        meta = blueprint["meta"]
        if "version" not in meta:
            issues.append("❌ meta.version 缺失（当前支持 '1.0' / '1.1'）")
        elif meta["version"] not in {"1.0", "1.1"}:
            issues.append(f"❌ meta.version='{meta['version']}' 不受支持")
        if "type" not in meta:
            issues.append("❌ meta.type 缺失（应为 building / avatar / asset / scene）")
        elif meta["type"] not in {"building", "avatar", "asset", "scene"}:
            issues.append(f"❌ meta.type='{meta['type']}' 不受支持")
        if "name" not in meta:
            issues.append("⚠️  meta.name 缺失（建议填写建筑名称）")

    if "geometry" not in blueprint:
        issues.append("❌ 缺少顶层字段 'geometry'")
    else:
        geo = blueprint["geometry"]
        if "elements" not in geo:
            issues.append("❌ geometry.elements 缺失")
        else:
            elements = geo["elements"]
            components = geo.get("components", [])
            if not isinstance(elements, list):
                issues.append(f"❌ geometry.elements 应为数组，实际为 {type(elements).__name__}")
                elements = []
            if not isinstance(components, list):
                issues.append(f"❌ geometry.components 应为数组，实际为 {type(components).__name__}")
                components = []
            if len(elements) == 0 and len(components) == 0:
                issues.append("⚠️  geometry.elements 与 geometry.components 同时为空")
            else:
                # 检查 ID 唯一性
                all_items = [
                    item for item in [*elements, *components]
                    if isinstance(item, dict)
                ]
                ids = [item.get("id", "") for item in all_items]
                dupes = {eid for eid in ids if eid and ids.count(eid) > 1}
                if dupes:
                    issues.append(f"❌ 重复的构件 ID: {dupes}")

                # 检查每个元素是否有 type
                for el in elements:
                    if "type" not in el:
                        issues.append(f"❌ 元素缺少 'type' 字段: id={el.get('id', '?')}")
                    if "id" not in el:
                        issues.append("❌ 元素缺少 'id' 字段")
                for component in components:
                    if not isinstance(component, dict):
                        issues.append("❌ geometry.components 中的项目必须是对象")
                        continue
                    if component.get("type") not in {
                        "door", "window", "railing", "canopy", "balcony", "ramp",
                        "bay_window", "cornice", "chimney", "light",
                    }:
                        issues.append(
                            f"❌ 组合构件类型无效: {component.get('type', '?')}"
                        )
                    if not component.get("id"):
                        issues.append("❌ 组合构件缺少非空 'id' 字段")

    if not issues:
        elements_count = len(_get_elements(blueprint))
        types = set(el.get("type", "?") for el in _get_elements(blueprint))
        return f"✅ 结构完整（{elements_count} 个构件，类型: {types}）"
    return "\n".join(issues)


@tool
def validate_opening_coords(blueprint: dict) -> str:
    """
    检查所有 opening（门窗洞口）的 from 字段是否正确使用了沿墙距离格式。

    正确格式：from = [沿墙距离, 底部世界Y, 法向偏移]
      沿墙距离：从 parentWall.from 点开始，沿墙体方向的偏移量（米）
      底部世界Y：门窗底边在场景中的世界高度（米）
      法向偏移：垂直于墙面的偏移，默认 0

    错误格式：from = [世界坐标X, 高度Y, 世界坐标Z]

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]
    components = blueprint.get("geometry", {}).get("components", [])
    door_windows = [
        component
        for component in components
        if component.get("type") in {"door", "window"}
    ]

    if not openings and not door_windows:
        return "✅ 没有 opening/门窗组件，跳过检查。"

    issues: list[str] = []
    for op in openings + door_windows:
        oid = op.get("id", "?")
        prefix = "component:" if op.get("type") in {"door", "window"} else ""
        parent_id = op.get("parentWall", "")
        from_vec = op.get("from", [0, 0, 0])

        if not parent_id:
            issues.append(f"❌ [{prefix}{oid}] 缺少 parentWall 字段")
            continue

        parent = walls.get(parent_id)
        if not parent:
            issues.append(f"❌ [{prefix}{oid}] parentWall='{parent_id}' 不存在于 elements 中")
            continue

        wl = _wall_length(parent)
        # 类型保护：将 from_vec 安全转为 float 列表，捕获 LLM 输出的非数值坐标
        try:
            coords = _safe_coords(from_vec, f"[{prefix}{oid}] from")
            if len(coords) != 3:
                raise ValueError(f"必须包含 3 个坐标，实际为 {len(coords)} 个")
            along_dist = coords[0] if len(coords) >= 1 else 0.0
            normal_offset = coords[2] if len(coords) >= 3 else 0.0
        except ValueError as e:
            issues.append(f"❌ [{prefix}{oid}] from 字段格式错误: {e}")
            continue

        # 沿墙距离检查
        if along_dist < -0.3 or along_dist > wl + 0.3:
            issues.append(
                f"❌ [{prefix}{oid}] from[0]={along_dist} 超出墙体长度 [0, {wl:.1f}]。"
                f"可能使用了世界坐标而非沿墙距离。"
                f"parentWall='{parent_id}' 从 {parent['from']} 到 {parent['to']}。"
            )

        # 法向偏移检查
        if abs(normal_offset) > MAX_OPENING_NORMAL_OFFSET:
            issues.append(
                f"❌ [{prefix}{oid}] from[2]={normal_offset} 法向偏移超出 "
                f"±{MAX_OPENING_NORMAL_OFFSET}m；该字段是局部法向偏移，不是父墙世界 X/Z，"
                "门窗通常应为 0"
            )

    if not issues:
        return "✅ 所有 opening 的 from 字段格式正确。"
    return "\n".join(issues)


def _plan_point_on_wall_segment(
    x: float,
    z: float,
    wall: dict,
    tolerance: float = 0.15,
) -> bool:
    """判断 XZ 点是否落在另一面墙的线段上，用于识别合法 T 形连接。"""
    start = wall.get("from", [0, 0, 0])
    end = wall.get("to", [0, 0, 0])
    dx = float(end[0]) - float(start[0])
    dz = float(end[2]) - float(start[2])
    length_sq = dx * dx + dz * dz
    if length_sq <= 1e-9:
        return False
    projection = ((x - float(start[0])) * dx + (z - float(start[2])) * dz) / length_sq
    if projection < -0.01 or projection > 1.01:
        return False
    nearest_x = float(start[0]) + projection * dx
    nearest_z = float(start[2]) + projection * dz
    return math.hypot(x - nearest_x, z - nearest_z) < tolerance


@tool
def validate_wall_junctions(blueprint: dict) -> str:
    """
    检查相邻墙体在转角处是否对齐（端点共享，无缝隙）。

    判断标准：两堵不同墙体的端点之间在 XZ 平面距离 < 0.15m 即为"已连接"。
    所有不满足此条件的端点视为"孤立端点"，可能造成墙体缝隙。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = [
        el for el in elements
        if el.get("type") == "wall" and _is_structural_wall(el)
    ]

    if len(walls) < 2:
        return "✅ 少于 2 面墙，跳过连接检查。"

    # 收集所有端点；除共享端点外，端点落在另一墙线段上的 T 形连接也合法。
    endpoints: list[dict] = []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to", [0, 0, 0])
        endpoints.append({
            "wall_id": w.get("id", "?"),
            "wall": w,
            "which": "from",
            "x": float(f[0]),
            "z": float(f[2]),
        })
        endpoints.append({
            "wall_id": w.get("id", "?"),
            "wall": w,
            "which": "to",
            "x": float(t[0]),
            "z": float(t[2]),
        })

    TOLERANCE = 0.15  # 15cm 容差
    isolated: list[str] = []
    for ep in endpoints:
        has_neighbor = False
        source_wall = ep["wall"]
        source_bottom, source_top = _wall_vertical_range(source_wall)
        for other_wall in walls:
            if other_wall is source_wall:
                continue
            other_bottom, other_top = _wall_vertical_range(other_wall)
            same_level = min(source_top, other_top) - max(source_bottom, other_bottom) > 0.15
            if same_level and _plan_point_on_wall_segment(
                ep["x"], ep["z"], other_wall, TOLERANCE,
            ):
                has_neighbor = True
                break
        if not has_neighbor:
            isolated.append(
                f"  - {ep['wall_id']}.{ep['which']} ({ep['x']:.2f}, {ep['z']:.2f})"
            )

    if not isolated:
        return "✅ 所有墙体端点都有相邻连接，墙体闭合良好。"
    return (
        f"⚠️  发现 {len(isolated)} 个孤立端点（可能造成缝隙）：\n"
        + "\n".join(isolated)
        + "\n\n建议：确保相邻墙体端点坐标精确一致。"
    )


def get_roof_support_bounds(
    walls: list[dict],
    roof: dict | None = None,
) -> dict[str, float]:
    """返回屋顶所在标高实际承托墙体的 XZ 包围盒，而不是整栋建筑首层外包框。"""
    if not walls:
        return {
            "min_x": 0.0, "max_x": 0.0, "min_z": 0.0, "max_z": 0.0,
            "span": 0.0, "depth": 0.0, "center_x": 0.0, "center_z": 0.0,
            "support_y": 0.0,
        }
    wall_tops = [(_wall_vertical_range(wall)[1], wall) for wall in walls]
    position = (roof or {}).get("position")
    roof_y = (
        float(position[1])
        if isinstance(position, list) and len(position) >= 3
        and isinstance(position[1], (int, float))
        else max(top for top, _ in wall_tops)
    )
    support_y = min((top for top, _ in wall_tops), key=lambda top: abs(top - roof_y))
    support_walls = [wall for top, wall in wall_tops if abs(top - support_y) <= 0.15]
    roof_span = (roof or {}).get("span")
    roof_depth = (roof or {}).get("depth")
    roof_footprint = None
    if (
        isinstance(position, list) and len(position) >= 3
        and isinstance(position[0], (int, float))
        and isinstance(position[2], (int, float))
        and isinstance(roof_span, (int, float)) and roof_span > 0
        and isinstance(roof_depth, (int, float)) and roof_depth > 0
    ):
        roof_footprint = (
            float(position[0]) - float(roof_span) / 2,
            float(position[0]) + float(roof_span) / 2,
            float(position[2]) - float(roof_depth) / 2,
            float(position[2]) + float(roof_depth) / 2,
        )
    all_x: list[float] = []
    all_z: list[float] = []
    for wall in support_walls:
        start = wall.get("from", [0, 0, 0])
        end = wall.get("to", [0, 0, 0])
        x0, x1 = sorted((float(start[0]), float(end[0])))
        z0, z1 = sorted((float(start[2]), float(end[2])))
        if roof_footprint:
            roof_x0, roof_x1, roof_z0, roof_z1 = roof_footprint
            if x1 - x0 >= z1 - z0:
                wall_z = (z0 + z1) / 2
                clipped_x0 = max(x0, roof_x0)
                clipped_x1 = min(x1, roof_x1)
                if clipped_x1 >= clipped_x0 and roof_z0 - 0.15 <= wall_z <= roof_z1 + 0.15:
                    all_x.extend([clipped_x0, clipped_x1])
                    all_z.extend([wall_z, wall_z])
            else:
                wall_x = (x0 + x1) / 2
                clipped_z0 = max(z0, roof_z0)
                clipped_z1 = min(z1, roof_z1)
                if clipped_z1 >= clipped_z0 and roof_x0 - 0.15 <= wall_x <= roof_x1 + 0.15:
                    all_x.extend([wall_x, wall_x])
                    all_z.extend([clipped_z0, clipped_z1])
            continue
        all_x.extend([x0, x1])
        all_z.extend([z0, z1])
    if not all_x or not all_z:
        for wall in support_walls:
            start = wall.get("from", [0, 0, 0])
            end = wall.get("to", [0, 0, 0])
            all_x.extend([float(start[0]), float(end[0])])
            all_z.extend([float(start[2]), float(end[2])])
    min_x, max_x = min(all_x), max(all_x)
    min_z, max_z = min(all_z), max(all_z)
    return {
        "min_x": min_x, "max_x": max_x,
        "min_z": min_z, "max_z": max_z,
        "span": max_x - min_x, "depth": max_z - min_z,
        "center_x": (min_x + max_x) / 2,
        "center_z": (min_z + max_z) / 2,
        "support_y": support_y,
    }


@tool
def validate_roof_coverage(blueprint: dict) -> str:
    """
    检查屋顶 span/depth 是否合理覆盖了墙体范围。

    规则：
      - span 应接近墙体 X 方向跨度（允许 1m 出檐）
      - depth 应接近墙体 Z 方向跨度（允许 1m 出檐）
      - 过大或过小都会产生警告

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    roofs = [el for el in elements if el.get("type") == "roof"]
    walls = [el for el in elements if el.get("type") == "wall"]

    if not roofs:
        return "✅ 没有 roof 构件，跳过检查。"
    if not walls:
        return "⚠️  有屋顶但没有墙体，无法判断覆盖范围。请确认设计意图。"

    issues: list[str] = []
    last_bounds: dict[str, float] | None = None
    for r in roofs:
        rid = r.get("id", "?")
        span = r.get("span", 0)
        depth = r.get("depth", 0)
        bounds = get_roof_support_bounds(walls, r)
        last_bounds = bounds
        wall_span = bounds["span"]
        wall_depth = bounds["depth"]

        # 合理范围：墙体范围 + 0~2m 出檐空间
        if span < wall_span * 0.5:
            issues.append(
                f"❌ [{rid}] span={span:.1f} 远小于墙体宽度={wall_span:.1f}，"
                f"屋顶完全无法覆盖墙体"
            )
        elif span < wall_span - 0.5:
            issues.append(
                f"⚠️  [{rid}] span={span:.1f} 略小于墙体宽度={wall_span:.1f}，"
                f"出檐不足"
            )
        elif span > wall_span + 4.0:
            issues.append(
                f"⚠️  [{rid}] span={span:.1f} 远大于墙体宽度={wall_span:.1f}，"
                f"屋顶悬空过多"
            )

        if depth < wall_depth * 0.5:
            issues.append(
                f"❌ [{rid}] depth={depth:.1f} 远小于墙体进深={wall_depth:.1f}，"
                f"屋顶完全无法覆盖墙体"
            )
        elif depth < wall_depth - 0.5:
            issues.append(
                f"⚠️  [{rid}] depth={depth:.1f} 略小于墙体进深={wall_depth:.1f}，"
                f"出檐不足"
            )
        elif depth > wall_depth + 4.0:
            issues.append(
                f"⚠️  [{rid}] depth={depth:.1f} 远大于墙体进深={wall_depth:.1f}，"
                f"屋顶悬空过多"
            )

    if not issues:
        bounds = last_bounds or get_roof_support_bounds(walls)
        return (
            f"✅ 屋顶尺寸合理。"
            f"（承托墙宽度={bounds['span']:.1f}, 进深={bounds['depth']:.1f}）"
        )
    return "\n".join(issues)


@tool
def validate_stair_alignment(blueprint: dict) -> str:
    """
    检查楼梯 from/to 端点高度是否与地板或墙体高度对齐。

    规则：
      - from.y 应对齐下层地板顶面或地面（y=0）
      - to.y 应对齐上层地板顶面或墙体顶部高度
      - 允许 ±0.2m 容差

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    stairs = [el for el in elements if el.get("type") == "stair"]

    if not stairs:
        return "✅ 没有 stair 构件，跳过检查。"

    # 收集参考高度：地板顶面 + 墙体顶部 + 地面
    floors = [el for el in elements if el.get("type") == "floor"]
    walls = [el for el in elements if el.get("type") == "wall"]

    floor_heights: list[float] = []
    for f in floors:
        fy = f.get("from", [0, 0, 0])[1]
        thickness = f.get("thickness", 0.0)
        if isinstance(fy, (int, float)):
            floor_heights.append(float(fy) + float(thickness))

    wall_top_heights: list[float] = []
    for w in walls:
        ty = w.get("to", [0, 0, 0])[1]
        if isinstance(ty, (int, float)):
            wall_top_heights.append(float(ty))

    all_ref_heights = sorted(set([0.0] + floor_heights + wall_top_heights))

    issues: list[str] = []
    for s in stairs:
        sid = s.get("id", "?")
        f = s.get("from", [0, 0, 0])
        t = s.get("to", [0, 0, 0])

        fy = float(f[1]) if len(f) > 1 else 0.0
        ty = float(t[1]) if len(t) > 1 else 0.0

        # 检查 from.y
        from_diffs = [abs(fy - h) for h in all_ref_heights]
        if from_diffs and min(from_diffs) > 0.2:
            nearest = all_ref_heights[from_diffs.index(min(from_diffs))]
            issues.append(
                f"⚠️  [{sid}] from.y={fy:.2f} 不匹配任何参考高度。"
                f"最近: {nearest}（差 {abs(fy - nearest):.2f}m）"
            )

        # 检查 to.y
        to_diffs = [abs(ty - h) for h in all_ref_heights]
        if to_diffs and min(to_diffs) > 0.2:
            nearest = all_ref_heights[to_diffs.index(min(to_diffs))]
            issues.append(
                f"⚠️  [{sid}] to.y={ty:.2f} 不匹配任何参考高度。"
                f"最近: {nearest}（差 {abs(ty - nearest):.2f}m）"
            )

        # 检查 from.y < to.y（楼梯应该向上）
        if fy >= ty:
            issues.append(
                f"❌ [{sid}] from.y={fy:.2f} >= to.y={ty:.2f}，"
                f"楼梯应该向上攀升"
            )

    for placement_issue in collect_stair_placement_issues(blueprint):
        entity_ids = ", ".join(
            str(entity_id)
            for entity_id in placement_issue.get("entity_ids", ())
        )
        issues.append(
            f"❌ [{entity_ids}] {placement_issue.get('message', '楼梯位置无效')}"
        )

    if not issues:
        ref_str = ", ".join(f"{h:.1f}m" for h in all_ref_heights)
        return f"✅ 楼梯端点与参考高度对齐。参考高度: [{ref_str}]"
    return "\n".join(issues)


# 字段校验与修正 Tool —— 以下函数先检查渲染必需字段，再进入原地修正步骤

@tool
def validate_element_required_fields(blueprint: dict) -> str:
    """
    检查每个构件是否包含其类型所需的必填字段。
    这是渲染前的最后一道防线——缺少必填字段会导致 wild-core 重建崩溃。

    各构件类型的必填字段：
      wall:    from, to, thickness
      floor:   from, thickness；矩形需要 to，圆形需要 radius
      column:  base, height, bottomRadius, topRadius, style
      beam:    from, to, crossSection, width, height
      roof:    roofType, span, depth, height, thickness
      opening: parentWall, from, width, height, style
      stair:   from, to, width
      furniture: subtype, position, dimensions { width, depth, height }
      primitive: shape，以及对应 shape 的几何参数

    参数 blueprint: 完整的 Blueprint dict
    """
    REQUIRED = {
        "wall":      ["from", "to", "thickness"],
        "floor":     ["from", "thickness"],
        "column":    ["base", "height", "bottomRadius", "topRadius", "style"],
        "beam":      ["from", "to", "crossSection", "width", "height"],
        "roof":      ["roofType", "span", "depth", "height", "thickness"],
        "opening":   ["parentWall", "from", "width", "height", "style"],
        "stair":     ["from", "to", "width"],
        "furniture": ["subtype", "position", "dimensions"],
        "dense_brick": ["resolution", "origin", "data"],
        "body":      ["height", "build", "headShape", "armLength", "legLength", "cloakLength", "hoodUp"],
        "primitive": ["shape"],
    }

    # 合法枚举值
    VALID_FURNITURE_SUBTYPES = {"table", "chair", "bookshelf", "bed", "lamp", "tile"}
    VALID_ROOF_TYPES = {"gable", "hip", "dome", "flat", "chinese_curved", "chinese_pagoda"}
    VALID_COLUMN_STYLES = {"doric", "ionic", "corinthian", "modern", "chinese_wooden"}
    VALID_OPENING_STYLES = {"rectangular", "arched", "gothic", "circular"}
    VALID_PRIMITIVE_SHAPES = {"box", "sphere", "cylinder", "profile_sweep"}

    # 蓝图顶层只允许这些 key
    VALID_ROOT_KEYS = {"meta", "geometry", "materials", "assets", "behaviors", "editor"}
    # geometry 内部只允许这些 key
    VALID_GEOMETRY_KEYS = {"elements", "components", "templates", "instances", "placements"}

    issues: list[str] = []

    # === 检查根级别多余的 key ===
    extra_root = set(blueprint.keys()) - VALID_ROOT_KEYS
    if extra_root:
        issues.append(f"❌ 蓝图根级别出现非法字段: {extra_root}。只允许: {VALID_ROOT_KEYS}")

    # === 检查 geometry 内部多余的 key ===
    geo = blueprint.get("geometry", {})
    if isinstance(geo, dict):
        extra_geo = set(geo.keys()) - VALID_GEOMETRY_KEYS
        if extra_geo:
            issues.append(f"❌ geometry 内部出现非法字段: {extra_geo}。只允许: {VALID_GEOMETRY_KEYS}")

    elements = _get_elements(blueprint)
    components = geo.get("components", []) if isinstance(geo, dict) else []
    if not elements and not components:
        if not issues:
            return "✅ 没有基础构件或组合构件，跳过必填字段检查。"
        return "\n".join(issues)

    for el in elements:
        etype = el.get("type", "")
        eid = el.get("id", "?")
        required = REQUIRED.get(etype, [])
        if not required:
            issues.append(f"❌ [{eid}] 未知构件类型 '{etype}'")
            continue
        for field in required:
            if field not in el or el[field] is None:
                issues.append(f"❌ [{eid}] (type={etype}) 缺少必填字段 '{field}'")

        # furniture 特殊检查
        if etype == "furniture":
            # subtype 合法性
            subtype = el.get("subtype", "")
            if subtype and subtype not in VALID_FURNITURE_SUBTYPES:
                issues.append(
                    f"❌ [{eid}] furniture subtype='{subtype}' 无效。"
                    f"合法值: {VALID_FURNITURE_SUBTYPES}"
                )
            # dimensions 结构化检查
            if "dimensions" in el:
                dims = el["dimensions"]
                if isinstance(dims, dict):
                    for dfield in ["width", "depth", "height"]:
                        if dfield not in dims or dims[dfield] is None:
                            issues.append(
                                f"❌ [{eid}] (type=furniture) dimensions 缺少 '{dfield}'"
                            )
                else:
                    issues.append(
                        f"❌ [{eid}] (type=furniture) dimensions 必须是对象，实际为 {type(dims).__name__}"
                    )

        if etype == "floor":
            shape = el.get("shape", "rect")
            if shape == "circle":
                if "radius" not in el:
                    issues.append(f"❌ [{eid}] 圆形 floor 缺少 radius")
            elif "to" not in el:
                issues.append(f"❌ [{eid}] 矩形 floor 缺少 to")

        if etype == "primitive":
            shape = el.get("shape", "")
            if shape and shape not in VALID_PRIMITIVE_SHAPES:
                issues.append(
                    f"❌ [{eid}] primitive shape='{shape}' 无效。"
                    f"合法值: {VALID_PRIMITIVE_SHAPES}"
                )
            if shape == "box":
                dimensions = el.get("dimensions")
                valid_dimensions = (
                    _is_finite_vector3(dimensions)
                    and all(value > 0 for value in dimensions)
                )
                if not valid_dimensions:
                    issues.append(
                        f"❌ [{eid}] primitive box 的 dimensions 必须是 "
                        "[width, height, depth] 三个正有限数字"
                    )
            if shape == "sphere" and "radius" not in el:
                issues.append(f"❌ [{eid}] primitive sphere 缺少 radius")
            if shape == "cylinder":
                if "height" not in el:
                    issues.append(f"❌ [{eid}] primitive cylinder 缺少 height")
                if "radius" not in el and not (
                    "radiusTop" in el and "radiusBottom" in el
                ):
                    issues.append(
                        f"❌ [{eid}] primitive cylinder 需要 radius，或同时提供 radiusTop/radiusBottom"
                    )
            if shape == "profile_sweep" and "path" not in el:
                issues.append(f"❌ [{eid}] primitive profile_sweep 缺少 path")

    component_required = {
        "door": ["parentWall", "from", "width", "height", "interaction"],
        "window": ["parentWall", "from", "width", "height"],
        "railing": ["path", "height"],
        "canopy": ["parentWall", "from", "width", "depth", "thickness"],
        "balcony": ["parentWall", "from", "width", "depth", "slabThickness"],
        "ramp": ["from", "to", "width", "thickness"],
        "bay_window": ["parentWall", "from", "width", "height", "projectionDepth"],
        "cornice": ["path", "profile"],
        "chimney": ["position", "width", "depth", "height"],
        "light": ["position"],
    }
    for component in components:
        if not isinstance(component, dict):
            issues.append("❌ geometry.components 中的项目必须是对象")
            continue
        component_id = component.get("id", "?")
        component_type = component.get("type", "")
        required = component_required.get(component_type)
        if required is None:
            issues.append(f"❌ [{component_id}] 未知组合构件类型 '{component_type}'")
            continue
        for field in required:
            if field not in component or component[field] is None:
                issues.append(
                    f"❌ [{component_id}] (component={component_type}) 缺少必填字段 '{field}'"
                )
        if component_type in {"door", "window", "canopy", "balcony", "bay_window"}:
            if not _is_finite_vector3(component.get("from")):
                issues.append(f"❌ [{component_id}] from 必须是三维有限坐标")
            numeric_fields = [
                field for field in required
                if field not in {"parentWall", "from"}
            ]
            for field in numeric_fields:
                value = component.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                    issues.append(f"❌ [{component_id}] {field} 必须是正数")
        elif component_type in {"railing", "cornice"}:
            path = component.get("path")
            if (
                not isinstance(path, list)
                or len(path) < 2
                or not all(_is_finite_vector3(point) for point in path)
            ):
                issues.append(f"❌ [{component_id}] path 至少需要两个三维有限坐标")
        elif component_type == "ramp":
            for field in ("from", "to"):
                if not _is_finite_vector3(component.get(field)):
                    issues.append(f"❌ [{component_id}] {field} 必须是三维有限坐标")
            for field in ("width", "thickness"):
                value = component.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                    issues.append(f"❌ [{component_id}] {field} 必须是正数")
        elif component_type in {"chimney", "light"}:
            if not _is_finite_vector3(component.get("position")):
                issues.append(f"❌ [{component_id}] position 必须是三维有限坐标")
            for field in required:
                if field == "position":
                    continue
                value = component.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                    issues.append(f"❌ [{component_id}] {field} 必须是正数")

    if not issues:
        types_found = set(el.get("type", "?") for el in elements)
        component_types = set(item.get("type", "?") for item in components)
        return (
            f"✅ 所有 {len(elements)} 个基础构件和 {len(components)} 个组合构件"
            f"的必填字段完整（基础类型: {types_found}，组合类型: {component_types}）"
        )
    return "\n".join(issues)

@tool
def fix_opening_coords(blueprint: dict) -> str:
    """
    自动检测并修正 opening 的坐标问题。
    如果 from[0] 疑似世界坐标（值超出墙体长度范围），则尝试换算为沿墙距离。

    原理：
      - 对于主要沿 X 方向的墙（|dx| > |dz|）：沿墙距离 = from[0] - wall.from[0]
      - 对于主要沿 Z 方向的墙（|dz| > |dx|）：沿墙距离 = from[2] - wall.from[2]

    注意：此工具会直接修改传入的 Blueprint dict。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]
    components = blueprint.get("geometry", {}).get("components", [])
    door_windows = [
        component
        for component in components
        if component.get("type") in {"door", "window"}
    ]

    if not openings and not door_windows:
        return "✅ 没有 opening/门窗组件需要修正。"

    fixes: list[str] = []
    for op in openings + door_windows:
        oid = op.get("id", "?")
        prefix = "component:" if op.get("type") in {"door", "window"} else ""
        parent_id = op.get("parentWall", "")
        from_vec = op.get("from", [0, 0, 0])

        parent = walls.get(parent_id)
        if not parent:
            continue

        try:
            coords = _safe_coords(from_vec, f"[{prefix}{oid}] from")
            if len(coords) != 3:
                continue
        except ValueError:
            continue

        # 统一为可原地修改的三元列表，避免外部调用传入 tuple 时修复失败。
        op["from"] = list(coords)

        wl = _wall_length(parent)
        along_dist = coords[0]
        normal_offset = coords[2]
        wf = parent.get("from", [0, 0, 0])
        dx, dz = _wall_direction_xz(parent)
        changes: list[str] = []

        # from[2] 明显偏大时，整组坐标很可能是世界 [X,Y,Z]。先将世界点
        # 投影到父墙，恢复正确的沿墙距离，再把局部法向偏移归零。
        if abs(normal_offset) > MAX_OPENING_NORMAL_OFFSET:
            projected_along = (
                (coords[0] - float(wf[0])) * dx
                + (coords[2] - float(wf[2])) * dz
            )
            if -0.3 <= projected_along <= wl + 0.3:
                new_along = max(0.0, min(projected_along, wl))
                if abs(new_along - along_dist) > 1e-6:
                    op["from"][0] = round(new_along, 2)
                    changes.append(f"from[0] {along_dist:.2f} → {new_along:.2f}（世界坐标投影）")
                    along_dist = new_along
            op["from"][2] = 0.0
            changes.append(f"from[2] {normal_offset:.2f} → 0（贴合父墙中心面）")

        # 沿墙距离本身越界时，也按世界点到父墙方向的投影尝试恢复。
        if along_dist < -0.3 or along_dist > wl + 0.3:
            projected_along = (
                (coords[0] - float(wf[0])) * dx
                + (coords[2] - float(wf[2])) * dz
            )
            new_along = max(0.1, min(projected_along, wl - 0.1))
            op["from"][0] = round(new_along, 2)
            changes.append(f"from[0] {along_dist:.2f} → {new_along:.2f}（沿墙距离）")

        if changes:
            fixes.append(
                f"🔧 [{prefix}{oid}]: " + "; ".join(changes)
                + f"；parentWall='{parent_id}' 墙长={wl:.1f}m"
            )

    if not fixes:
        return "✅ 所有 opening/门窗组件坐标已在合理范围，无需修正。"
    return "已自动修正以下 opening/门窗组件坐标：\n" + "\n".join(fixes)


# 引用完整性校验 —— Step 3 in pipeline

@tool
def validate_reference_integrity(blueprint: dict) -> str:
    """
    校验构件之间的引用关系是否合法。

    检查项：
      1. opening.parentWall 必须存在且 type == 'wall'
      2. geometry.instances[*].ref 必须存在于 geometry.templates
      3. behaviors.physics.constraints[*].target 必须是已存在的构件 id
      4. 不允许循环引用（template 引用自身）
      5. 构件声明的材质 ID 必须存在于 Blueprint.materials

    参数 blueprint: 完整的 Blueprint dict
    """
    issues: list[str] = []
    elements = _get_elements(blueprint)
    element_ids = {el.get("id") for el in elements if el.get("id")}
    wall_ids = {el.get("id") for el in elements if el.get("type") == "wall"}
    components = blueprint.get("geometry", {}).get("components", []) or []

    # --- 1. opening.parentWall 校验 ---
    for el in elements:
        if el.get("type") != "opening":
            continue
        eid = el.get("id", "?")
        parent = el.get("parentWall", "")
        if not parent:
            issues.append(f"❌ [{eid}] opening 缺少 parentWall 字段")
        elif parent not in element_ids:
            issues.append(f"❌ [{eid}] parentWall='{parent}' 引用的构件不存在")
        elif parent not in wall_ids:
            issues.append(
                f"❌ [{eid}] parentWall='{parent}' 引用的构件不是 wall 类型"
            )

    # --- 1b. door/window 组合构件的 parentWall 校验 ---
    for component in components:
        if component.get("type") not in {"door", "window"}:
            continue
        component_id = component.get("id", "?")
        parent = component.get("parentWall", "")
        if not parent:
            issues.append(f"❌ [component:{component_id}] 缺少 parentWall 字段")
            continue
        if parent not in element_ids:
            issues.append(
                f"❌ [component:{component_id}] parentWall='{parent}' 引用的构件不存在"
            )
            continue
        if parent not in wall_ids:
            issues.append(
                f"❌ [component:{component_id}] parentWall='{parent}' 不是 wall 类型"
            )

    # --- 1c. 元素与组合构件的材质引用必须存在 ---
    materials = blueprint.get("materials", {}) or {}
    material_ids = set(materials) if isinstance(materials, dict) else set()
    material_fields = ("material", "frameMaterial", "leafMaterial", "glassMaterial")
    for entity in elements:
        entity_id = entity.get("id", "?")
        for field in material_fields:
            material_id = entity.get(field)
            if not material_id:
                continue
            if not isinstance(material_id, str) or material_id not in material_ids:
                issues.append(
                    f"❌ [{entity_id}] {field}='{material_id}' "
                    "未在 Blueprint.materials 中定义"
                )
    for entity in components:
        entity_id = entity.get("id", "?")
        for field in material_fields:
            material_id = entity.get(field)
            if not material_id:
                continue
            if not isinstance(material_id, str) or material_id not in material_ids:
                issues.append(
                    f"❌ [component:{entity_id}] {field}='{material_id}' "
                    "未在 Blueprint.materials 中定义"
                )

    # --- 2. instances.ref 校验（兼容早期 templateId）---
    geo = blueprint.get("geometry", {})
    templates = geo.get("templates", {}) or {}
    instances = geo.get("instances", []) or []
    for inst in instances:
        iid = inst.get("id", "?")
        tid = inst.get("ref") or inst.get("templateId", "")
        if not tid:
            issues.append(f"❌ [instance:{iid}] 缺少 ref 字段")
        elif tid not in templates:
            issues.append(
                f"❌ [instance:{iid}] ref='{tid}' 在 geometry.templates 中不存在"
            )

    # --- 3. behaviors.physics.constraints.target 校验 ---
    physics = blueprint.get("behaviors", {}).get("physics", {})
    for c in physics.get("constraints", []):
        target = c.get("target", "")
        if target and target not in element_ids:
            issues.append(
                f"❌ [behavior.constraint] target='{target}' 引用的构件不存在"
            )

    # --- 4. template 自引用检测 ---
    for tname, tdef in templates.items():
        sub_elements = tdef.get("elements", []) if isinstance(tdef, dict) else []
        for sub in sub_elements:
            ref = sub.get("templateId", "")
            if ref == tname:
                issues.append(
                    f"❌ [template:{tname}] 存在自引用（templateId 指向自身），会导致无限递归"
                )

    if not issues:
        return (
            f"✅ 引用完整性通过。"
            f"（{len(elements)} 个基础构件，{len(components)} 个组合构件，"
            f"{len(templates)} 个模板，{len(instances)} 个实例）"
        )
    return "\n".join(issues)


@tool
def fix_material_references(blueprint: dict) -> str:
    """修正唯一可判定的材质别名，例如 wood -> wood_oak。"""
    materials = blueprint.get("materials", {}) or {}
    if not isinstance(materials, dict) or not materials:
        return "⚠️ Blueprint.materials 为空，没有可用于修正引用的材质"

    material_ids = list(materials)
    fields = ("material", "frameMaterial", "leafMaterial", "glassMaterial")
    geometry = blueprint.get("geometry", {})
    entities = [
        *(geometry.get("elements", []) or []),
        *(geometry.get("components", []) or []),
    ]
    fixes: list[str] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get("id", "?")
        for field in fields:
            reference = entity.get(field)
            if not isinstance(reference, str) or reference in materials:
                continue
            normalized = reference.lower()
            candidates = [
                material_id
                for material_id in material_ids
                if material_id.lower() == normalized
                or material_id.lower().startswith(normalized + "_")
                or normalized.startswith(material_id.lower() + "_")
            ]
            if field == "glassMaterial" and "glass" in materials:
                candidates = ["glass"]
            candidates = list(dict.fromkeys(candidates))
            if len(candidates) != 1:
                continue
            entity[field] = candidates[0]
            fixes.append(
                f"🔧 [{entity_id}] {field}: '{reference}' → '{candidates[0]}'"
            )

    if not fixes:
        return "✅ 没有可唯一判定的材质别名需要修正。"
    return "已修正以下材质引用：\n" + "\n".join(fixes)


# 碰撞 / 空间冲突检测 —— Step 9 in pipeline

def _aabb(el: dict) -> tuple[float, float, float, float, float, float] | None:
    """
    计算元素的轴对齐包围盒 (minX, maxX, minY, maxY, minZ, maxZ)。
    只处理有明确坐标的构件，无法计算的返回 None。
    Y 轴：wall/floor/beam 用 from[1]/to[1]，column 用 base[1] ~ base[1]+height。
    """
    t = el.get("type", "")

    if t == "wall":
        f = el.get("from", [])
        to = el.get("to", [])
        if len(f) < 3 or len(to) < 3:
            return None
        thickness = el.get("thickness", 0.2)
        half_t = thickness / 2.0
        min_y, max_y = _wall_vertical_range(el)
        min_x = min(f[0], to[0]) - half_t
        max_x = max(f[0], to[0]) + half_t
        min_z = min(f[2], to[2]) - half_t
        max_z = max(f[2], to[2]) + half_t
        return (min_x, max_x, min_y, max_y, min_z, max_z)

    if t == "floor":
        f = el.get("from", [])
        to = el.get("to", [])
        if len(f) < 3 or len(to) < 3:
            return None
        thickness = float(el.get("thickness", 0))
        return (
            min(f[0], to[0]), max(f[0], to[0]),
            float(f[1]), float(f[1]) + thickness,
            min(f[2], to[2]), max(f[2], to[2]),
        )

    if t == "beam":
        f = el.get("from", [])
        to = el.get("to", [])
        if len(f) < 3 or len(to) < 3:
            return None
        half_width = float(el.get("width", 0.2)) / 2.0
        beam_height = float(el.get("height", 0.2))
        return (
            min(f[0], to[0]) - half_width,
            max(f[0], to[0]) + half_width,
            min(f[1], to[1]) - beam_height / 2.0,
            max(f[1], to[1]) + beam_height / 2.0,
            min(f[2], to[2]) - half_width,
            max(f[2], to[2]) + half_width,
        )

    if t == "column":
        base = el.get("base", [])
        height = el.get("height", 0)
        r = max(el.get("bottomRadius", 0.1), el.get("topRadius", 0.1))
        if len(base) < 3:
            return None
        return (
            base[0] - r, base[0] + r,
            base[1], base[1] + height,
            base[2] - r, base[2] + r,
        )

    if t == "stair":
        f = el.get("from", [])
        to = el.get("to", [])
        w = el.get("width", 1.0) / 2.0
        if len(f) < 3 or len(to) < 3:
            return None
        return (
            min(f[0], to[0]) - w, max(f[0], to[0]) + w,
            min(f[1], to[1]), max(f[1], to[1]),
            min(f[2], to[2]) - w, max(f[2], to[2]) + w,
        )

    if t == "furniture":
        pos = el.get("position", [])
        dims = el.get("dimensions", {})
        if len(pos) < 3 or not isinstance(dims, dict):
            return None
        hw = dims.get("width", 0.5) / 2.0
        hd = dims.get("depth", 0.5) / 2.0
        h = dims.get("height", 0.5)
        return (
            pos[0] - hw, pos[0] + hw,
            pos[1], pos[1] + h,
            pos[2] - hd, pos[2] + hd,
        )

    return None


def _aabb_overlap(
    a: tuple[float, float, float, float, float, float],
    b: tuple[float, float, float, float, float, float],
    margin: float = 0.05,
) -> bool:
    """判断两个 AABB 是否重叠（margin 为最小穿插深度阈值，避免贴面误报）"""
    return (
        a[0] < b[1] - margin and a[1] > b[0] + margin and  # X
        a[2] < b[3] - margin and a[3] > b[2] + margin and  # Y
        a[4] < b[5] - margin and a[5] > b[4] + margin      # Z
    )


def _floor_reference_ys(blueprint: dict) -> tuple[list[float], list[float]]:
    """返回楼板底面/顶面标高，并展开 floor 模板实例。

    示意高层用 ``templates + instances`` 表达标准楼板。旧校验只读取显式
    elements，因而会把正确落在 24m、56m 等楼板上的分段柱判为悬空，随后
    修复器又把它们全拉到同一标高，制造真正的重叠柱。
    """

    geometry = blueprint.get("geometry", {}) if isinstance(blueprint, dict) else {}
    base_ys: list[float] = [0.0]
    top_ys: list[float] = [0.0]

    def append_floor(item: dict, offset_y: float = 0.0) -> None:
        start = item.get("from")
        if not isinstance(start, list) or len(start) != 3:
            return
        try:
            base_y = offset_y + float(start[1])
            thickness = float(item.get("thickness") or 0.0)
        except (TypeError, ValueError):
            return
        base_ys.append(base_y)
        top_ys.append(base_y + thickness)

    for item in geometry.get("elements", []):
        if isinstance(item, dict) and item.get("type") == "floor":
            append_floor(item)
    templates = geometry.get("templates")
    template_map = templates if isinstance(templates, dict) else {}
    for instance in geometry.get("instances", []):
        if not isinstance(instance, dict):
            continue
        template = template_map.get(str(instance.get("ref") or ""))
        position = instance.get("position")
        if (
            isinstance(template, dict)
            and template.get("type") == "floor"
            and isinstance(position, list)
            and len(position) == 3
        ):
            try:
                append_floor(template, float(position[1]))
            except (TypeError, ValueError):
                continue
    return (
        sorted({round(value, 6) for value in base_ys}),
        sorted({round(value, 6) for value in top_ys}),
    )


@tool
def validate_model_quality(blueprint: dict) -> str:
    """拦截会产生闪烁或虚假复杂度的重复墙体与重叠柱。"""
    elements = _get_elements(blueprint)
    issues: list[str] = []

    wall_groups: dict[tuple, list[str]] = {}
    for wall in (item for item in elements if item.get("type") == "wall"):
        start = wall.get("from")
        end = wall.get("to")
        if not _is_finite_vector3(start) or not _is_finite_vector3(end):
            continue
        endpoints = sorted((
            (round(float(start[0]), 3), round(float(start[2]), 3)),
            (round(float(end[0]), 3), round(float(end[2]), 3)),
        ))
        key = (
            endpoints[0],
            endpoints[1],
            round(min(float(start[1]), float(end[1])), 3),
            round(max(float(start[1]), float(end[1])), 3),
        )
        wall_groups.setdefault(key, []).append(str(wall.get("id", "?")))
    for ids in wall_groups.values():
        if len(ids) > 1:
            issues.append(f"❌ 重复墙体共用同一中心线与标高: {', '.join(ids)}")

    columns: list[tuple[str, list[float], float, float]] = []
    for column in (item for item in elements if item.get("type") == "column"):
        base = column.get("base")
        if not _is_finite_vector3(base):
            continue
        try:
            height = float(column.get("height", 0))
            radius = max(
                float(column.get("bottomRadius", 0)),
                float(column.get("topRadius", 0)),
                float(column.get("radius", 0)),
                float(column.get("width", 0)) / 2,
                float(column.get("depth", 0)) / 2,
                0.01,
            )
        except (TypeError, ValueError):
            continue
        columns.append((str(column.get("id", "?")), base, height, radius))

    for index, first in enumerate(columns):
        for second in columns[index + 1:]:
            first_top = float(first[1][1]) + first[2]
            second_top = float(second[1][1]) + second[2]
            vertical_overlap = min(first_top, second_top) - max(
                float(first[1][1]), float(second[1][1])
            )
            horizontal_distance = math.hypot(
                float(first[1][0]) - float(second[1][0]),
                float(first[1][2]) - float(second[1][2]),
            )
            if vertical_overlap > 0.05 and horizontal_distance < first[3] + second[3] - 0.02:
                issues.append(
                    f"❌ 重叠柱应合并为一个轴网节点: {first[0]} / {second[0]} "
                    f"(中心距 {horizontal_distance:.2f}m)"
                )

    if not issues:
        return "✅ 模型质量检查通过：无重复墙体或重叠柱。"
    visible = issues[:12]
    if len(issues) > len(visible):
        visible.append(f"❌ 另有 {len(issues) - len(visible)} 处重复骨架未展开")
    return f"发现 {len(issues)} 处会造成重影/虚假复杂度的重复骨架：\n" + "\n".join(visible)


@tool
def validate_collision(blueprint: dict) -> str:
    """
    检测构件之间是否存在碰撞、穿插、悬空或不合理重叠。

    检查项：
      1. 同类型构件之间不应有实质性重叠（如两根柱子、两段楼梯）
      2. opening 不应与其他 opening 重叠（同一面墙上）
      3. furniture / stair 不应穿插进 wall 内部（结构柱嵌入墙体属于合法节点）
      4. column / stair / furniture 底部 Y 不应悬空
         （base[1] 或 from[1] 应 >= 最近楼板顶面，容差 0.3m）

    说明：
      - 使用轴对齐包围盒（AABB）近似，不做精确几何求交
      - opening 本身嵌入墙体是合法的，不参与碰撞检测
      - wall 之间的端点相交是正常建筑连接，不报告

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    issues: list[str] = []

    # 按 type 分组
    by_type: dict[str, list[dict]] = {}
    for el in elements:
        t = el.get("type", "")
        by_type.setdefault(t, []).append(el)

    # --- 1. 同类型非 wall 构件之间重叠检测 ---
    CHECK_SELF_COLLISION = ("column", "stair", "furniture", "floor")
    for t in CHECK_SELF_COLLISION:
        group = by_type.get(t, [])
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                ba = _aabb(a)
                bb = _aabb(b)
                if ba and bb and _aabb_overlap(ba, bb):
                    issues.append(
                        f"⚠️  [{a.get('id','?')}] 与 [{b.get('id','?')}]"
                        f"（均为 {t}）存在重叠/穿插，请检查坐标"
                    )

    # 梁的端部相接、T 形连接和十字相交都是合法结构节点；只报告同轴的实质重叠。
    beams = by_type.get("beam", [])
    for index, beam_a in enumerate(beams):
        for beam_b in beams[index + 1:]:
            start_a, end_a = beam_a.get("from", []), beam_a.get("to", [])
            start_b, end_b = beam_b.get("from", []), beam_b.get("to", [])
            if any(len(point) < 3 for point in (start_a, end_a, start_b, end_b)):
                continue
            axis_a = "x" if abs(end_a[0] - start_a[0]) >= abs(end_a[2] - start_a[2]) else "z"
            axis_b = "x" if abs(end_b[0] - start_b[0]) >= abs(end_b[2] - start_b[2]) else "z"
            if axis_a != axis_b or abs(float(start_a[1]) - float(start_b[1])) > 0.15:
                continue
            cross_a = float(start_a[2] if axis_a == "x" else start_a[0])
            cross_b = float(start_b[2] if axis_b == "x" else start_b[0])
            if abs(cross_a - cross_b) > 0.15:
                continue
            interval_a = sorted((float(start_a[0 if axis_a == "x" else 2]), float(end_a[0 if axis_a == "x" else 2])))
            interval_b = sorted((float(start_b[0 if axis_b == "x" else 2]), float(end_b[0 if axis_b == "x" else 2])))
            overlap = min(interval_a[1], interval_b[1]) - max(interval_a[0], interval_b[0])
            if overlap > 0.15:
                issues.append(
                    f"⚠️  [{beam_a.get('id','?')}] 与 [{beam_b.get('id','?')}]"
                    f"（均为 beam）同轴重叠 {overlap:.2f}m，请检查是否重复生成"
                )

    # --- 2. 同一面墙上的 opening 重叠检测 ---
    openings = by_type.get("opening", [])
    # 按 parentWall 分组
    wall_openings: dict[str, list[dict]] = {}
    for op in openings:
        pw = op.get("parentWall", "")
        wall_openings.setdefault(pw, []).append(op)

    for wall_id, ops in wall_openings.items():
        for i in range(len(ops)):
            for j in range(i + 1, len(ops)):
                a, b = ops[i], ops[j]
                a_from = a.get("from", [0, 0, 0])
                b_from = b.get("from", [0, 0, 0])
                a_w = a.get("width", 1.0)
                b_w = b.get("width", 1.0)
                a_h = a.get("height", 1.0)
                b_h = b.get("height", 1.0)

                # 沿墙方向区间重叠 + 高度区间重叠
                a_along_min = a_from[0]
                a_along_max = a_from[0] + a_w
                b_along_min = b_from[0]
                b_along_max = b_from[0] + b_w

                a_y_min = a_from[1]
                a_y_max = a_from[1] + a_h
                b_y_min = b_from[1]
                b_y_max = b_from[1] + b_h

                along_overlap = a_along_min < b_along_max and a_along_max > b_along_min
                y_overlap = a_y_min < b_y_max and a_y_max > b_y_min

                if along_overlap and y_overlap:
                    issues.append(
                        f"❌ [{a.get('id','?')}] 与 [{b.get('id','?')}]"
                        f" 在墙 '{wall_id}' 上发生开口重叠，"
                        f"沿墙区间 [{a_along_min:.2f},{a_along_max:.2f}] ∩ [{b_along_min:.2f},{b_along_max:.2f}]"
                    )

    # --- 3. stair / furniture 不应穿插入 wall 内部 ---
    # 允许贴靠（margin 收紧到 0.15m，避免合理贴墙被误报）
    walls = by_type.get("wall", [])
    INTRUDE_TYPES = ("stair", "furniture")
    for t in INTRUDE_TYPES:
        for el in by_type.get(t, []):
            el_bb = _aabb(el)
            if not el_bb:
                continue
            for wall in walls:
                w_bb = _aabb(wall)
                if not w_bb:
                    continue
                if _aabb_overlap(el_bb, w_bb, margin=0.15):
                    issues.append(
                        f"⚠️  [{el.get('id','?')}]（{t}）与墙 [{wall.get('id','?')}] "
                        f"存在穿插，请确认是否为贴墙摆放（可忽略）或实际穿墙（需修正）"
                    )

    # --- 4. 悬空检测：column / stair / furniture 底部 Y 应不低于地板 ---
    # 注意：floor 顶面 = from[1] + thickness（floor.from[1] 是底面 Y，不是顶面 Y）
    floor_base_ys, floor_top_ys = _floor_reference_ys(blueprint)

    FLOATING_TYPES = {
        "column": lambda el: el.get("base", [0, 0, 0])[1],
        "stair":  lambda el: el.get("from", [0, 0, 0])[1],
        "furniture": lambda el: el.get("position", [0, 0, 0])[1],
    }
    for t, get_bottom_y in FLOATING_TYPES.items():
        for el in by_type.get(t, []):
            bottom_y = float(get_bottom_y(el))
            references = floor_top_ys if t == "furniture" else floor_base_ys
            # 找最近的楼板高度
            nearest_floor = min(references, key=lambda fy: abs(fy - bottom_y))
            gap = bottom_y - nearest_floor
            if gap > 0.31:  # 0.31 留出浮点误差余量，与 fix_element_elevations 的阈值对齐
                issues.append(
                    f"⚠️  [{el.get('id','?')}]（{t}）底部 Y={bottom_y:.2f}，"
                    f"距最近楼板 Y={nearest_floor:.2f} 相差 {gap:.2f}m，可能悬空"
                )
            elif gap < -0.1:
                issues.append(
                    f"⚠️  [{el.get('id','?')}]（{t}）底部 Y={bottom_y:.2f}，"
                    f"低于最近楼板 Y={nearest_floor:.2f}，可能穿入地板"
                )

    if not issues:
        checked = sum(len(by_type.get(t, [])) for t in (*CHECK_SELF_COLLISION, "beam", "opening"))
        return f"✅ 碰撞检测通过，共检查 {checked} 个构件，未发现空间冲突。"
    return f"发现 {len(issues)} 处空间冲突：\n" + "\n".join(issues)


# ============================================================
# P0：开口越界检查 —— 顶点爆炸根源
# ============================================================

@tool
def validate_opening_fit(blueprint: dict) -> str:
    """
    检查每个 opening 是否完全在 parentWall 的尺寸范围内。

    规则：
      - 沿墙方向：from[0] >= 0 且 from[0] + width <= 墙长
      - 高度方向：from[1] >= 墙底Y 且 from[1] + height <= 墙顶Y

    超出墙体范围的 opening 会导致 wild-core 切孔算法产生异常几何（顶点数爆炸）。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]
    components = blueprint.get("geometry", {}).get("components", [])
    door_windows = [
        c for c in components
        if c.get("type") in WALL_OPENING_COMPONENT_TYPES
    ]

    if not openings and not door_windows:
        return "✅ 没有 opening/门窗组件，跳过检查。"

    issues: list[str] = []
    for op in openings:
        oid = op.get("id", "?")
        parent_id = op.get("parentWall", "")
        from_vec = op.get("from", [0, 0, 0])
        width = op.get("width", 0)
        height = op.get("height", 0)

        parent = walls.get(parent_id)
        if not parent:
            continue  # 已由 validate_reference_integrity 覆盖

        wl = _wall_length(parent)
        wall_bottom_y, wall_top_y = _wall_vertical_range(parent)
        wall_height   = wall_top_y - wall_bottom_y

        along = float(from_vec[0])
        base_y = float(from_vec[1]) if len(from_vec) > 1 else wall_bottom_y

        # 沿墙方向越界
        if along < -0.05:
            issues.append(
                f"❌ [{oid}] 沿墙起点 {along:.2f} < 0，开口超出墙体左端"
            )
        if along + width > wl + 0.05:
            issues.append(
                f"❌ [{oid}] 沿墙终点 {along + width:.2f} > 墙长 {wl:.2f}，开口超出墙体右端"
            )

        # 高度方向越界（相对世界坐标）
        rel_bottom = base_y - wall_bottom_y
        rel_top    = rel_bottom + height
        if rel_bottom < -0.05:
            issues.append(
                f"❌ [{oid}] 开口底部 Y={base_y:.2f} 低于墙底 Y={wall_bottom_y:.2f}"
            )
        if rel_top > wall_height + 0.05:
            issues.append(
                f"❌ [{oid}] 开口顶部 Y={base_y + height:.2f} 超出墙顶 Y={wall_top_y:.2f}"
            )

        # 尺寸为零或负值
        if width <= 0:
            issues.append(f"❌ [{oid}] width={width} 无效，必须 > 0")
        if height <= 0:
            issues.append(f"❌ [{oid}] height={height} 无效，必须 > 0")

    # ── 同样检查 door/window/bay_window 组合构件 ──
    for comp in door_windows:
        cid = comp.get("id", "?")
        parent_id = comp.get("parentWall", "")
        from_vec = comp.get("from", [0, 0, 0])
        width = comp.get("width", 0)
        height = comp.get("height", 0)

        parent = walls.get(parent_id)
        if not parent:
            continue  # 已由 validate_reference_integrity 覆盖

        wl = _wall_length(parent)
        wall_bottom_y, wall_top_y = _wall_vertical_range(parent)
        wall_height = wall_top_y - wall_bottom_y

        along = float(from_vec[0])
        base_y = float(from_vec[1]) if len(from_vec) > 1 else wall_bottom_y

        if along < -0.05:
            issues.append(
                f"❌ [component:{cid}] 沿墙起点 {along:.2f} < 0，超出父墙左端"
            )
        if along + width > wl + 0.05:
            issues.append(
                f"❌ [component:{cid}] 沿墙终点 {along+width:.2f} > 墙长 {wl:.2f}，超出父墙右端"
            )

        if base_y < wall_bottom_y - 0.05:
            issues.append(
                f"❌ [component:{cid}] 底部 Y={base_y:.2f} 低于墙底 Y={wall_bottom_y:.2f}"
            )
        if height > 0 and base_y + height > wall_top_y + 0.05:
            issues.append(
                f"❌ [component:{cid}] 顶部 Y={base_y+height:.2f} 超出墙顶 Y={wall_top_y:.2f}"
            )

        if width <= 0:
            issues.append(f"❌ [component:{cid}] width={width} 无效")
        if height <= 0:
            issues.append(f"❌ [component:{cid}] height={height} 无效")

    # 同一父墙上的开口不能占用相同的二维区域。只比较沿墙方向和高度方向
    # 都有实际交叠的对象，允许高窗位于门的正上方。
    opening_boxes: list[tuple[str, str, float, float, float, float]] = []
    for op in openings:
        from_vec = op.get("from", [])
        if len(from_vec) < 2:
            continue
        opening_boxes.append((
            str(op.get("id", "?")),
            str(op.get("parentWall", "")),
            float(from_vec[0]),
            float(from_vec[1]),
            float(op.get("width", 0)),
            float(op.get("height", 0)),
        ))
    for comp in door_windows:
        from_vec = comp.get("from", [])
        if len(from_vec) < 2:
            continue
        opening_boxes.append((
            f"component:{comp.get('id', '?')}",
            str(comp.get("parentWall", "")),
            float(from_vec[0]),
            float(from_vec[1]),
            float(comp.get("width", 0)),
            float(comp.get("height", 0)),
        ))

    for index, first in enumerate(opening_boxes):
        first_id, first_wall, first_x, first_y, first_w, first_h = first
        if not first_wall or first_w <= 0 or first_h <= 0:
            continue
        for second in opening_boxes[index + 1:]:
            second_id, second_wall, second_x, second_y, second_w, second_h = second
            if first_wall != second_wall or second_w <= 0 or second_h <= 0:
                continue
            horizontal_overlap = min(first_x + first_w, second_x + second_w) - max(first_x, second_x)
            vertical_overlap = min(first_y + first_h, second_y + second_h) - max(first_y, second_y)
            if horizontal_overlap > 0.05 and vertical_overlap > 0.05:
                issues.append(
                    f"❌ [{first_id}] 与 ❌ [{second_id}] 在父墙 [{first_wall}] 上重叠 "
                    f"({horizontal_overlap:.2f}m × {vertical_overlap:.2f}m)"
                )

    total = len(openings) + len(door_windows)
    if not issues:
        return f"✅ 所有 {total} 个 opening/门窗组件均在 parentWall 范围内。"
    return "\n".join(issues)


# ============================================================
# P1：构件尺寸合理性检查
# ============================================================

@tool
def validate_element_dimensions(blueprint: dict) -> str:
    """
    检查各构件尺寸是否在合理范围内。

    规则（单位：米）：
      wall:    长度 0.1~500，高度 0.1~50，厚度 0.01~5
      floor:   单边 0.1~500，厚度 0.01~5
      column:  高度 0.1~50，半径 0.01~5
      beam:    长度 0.1~200，宽/高截面 0.01~5
      roof:    span/depth 0.5~500，高度 0.1~100
      opening: 宽 0.1~20，高 0.1~20
      stair:   高差 0.1~50，水平距离 0.1~100

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    issues: list[str] = []

    for el in elements:
        t   = el.get("type", "")
        eid = el.get("id", "?")

        if t in {"wall", "floor", "beam", "stair"}:
            invalid_fields = [
                field
                for field in ("from", "to")
                if not _is_finite_vector3(el.get(field))
            ]
            if invalid_fields:
                issues.extend(
                    f"❌ [{eid}.{field}] 必须是包含 3 个有限数字的数组"
                    for field in invalid_fields
                )
                continue

        if t == "wall":
            length = _wall_length(el)
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            endpoint_height = abs(to[1] - f[1])
            h = el.get("height", endpoint_height)
            th = el.get("thickness", 0)
            if not (0.1 <= length <= 500):
                issues.append(f"⚠️  [{eid}] wall 长度={length:.1f}m，建议在 0.1~500m")
            if h <= 0.01:
                issues.append(
                    f"❌ [{eid}] wall 高度={h:.1f}m；from[1] 必须是墙底、to[1] 必须是墙顶"
                )
            elif not (0.1 <= h <= 50):
                issues.append(f"⚠️  [{eid}] wall 高度={h:.1f}m，建议在 0.1~50m")
            if (
                endpoint_height > 0.01
                and isinstance(el.get("height"), (int, float))
                and not isinstance(el.get("height"), bool)
                and abs(float(el["height"]) - endpoint_height)
                > max(0.05, endpoint_height * 0.01)
            ):
                issues.append(
                    f"❌ [{eid}] wall height={float(el['height']):.1f}m 与 "
                    f"from/to 竖向范围={endpoint_height:.1f}m 不一致"
                )
            if th > 0 and not (0.01 <= th <= 5):
                issues.append(f"⚠️  [{eid}] wall thickness={th}m，建议在 0.01~5m")

        elif t == "floor":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            sx = abs(to[0] - f[0])
            sz = abs(to[2] - f[2])
            th = el.get("thickness", 0)
            for dim, val in [("X跨度", sx), ("Z跨度", sz)]:
                if val > 0 and not (0.1 <= val <= 500):
                    issues.append(f"⚠️  [{eid}] floor {dim}={val:.1f}m，建议在 0.1~500m")
            if th > 0 and not (0.01 <= th <= 5):
                issues.append(f"⚠️  [{eid}] floor thickness={th}m，建议在 0.01~5m")

        elif t == "column":
            h  = el.get("height", 0)
            br = el.get("bottomRadius", 0)
            tr = el.get("topRadius", 0)
            if h > 0 and not (0.1 <= h <= 50):
                issues.append(f"⚠️  [{eid}] column height={h}m，建议在 0.1~50m")
            for rname, rv in [("bottomRadius", br), ("topRadius", tr)]:
                if rv > 0 and not (0.01 <= rv <= 5):
                    issues.append(f"⚠️  [{eid}] column {rname}={rv}m，建议在 0.01~5m")

        elif t == "beam":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            dx = to[0]-f[0]; dy = to[1]-f[1]; dz = to[2]-f[2]
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            w = el.get("width", 0)
            h = el.get("height", 0)
            if length > 0 and not (0.1 <= length <= 200):
                issues.append(
                    f"❌ [{eid}] beam 长度={length:.1f}m，超出合理范围 0.1~200m，"
                    f"可能坐标错误"
                )
            for fname, fv in [("width", w), ("height", h)]:
                if fv > 0 and not (0.01 <= fv <= 5):
                    issues.append(f"⚠️  [{eid}] beam {fname}={fv}m，建议在 0.01~5m")

        elif t == "roof":
            span  = el.get("span", 0)
            depth = el.get("depth", 0)
            rh    = el.get("height", 0)
            for fname, fv, lo, hi in [
                ("span",  span,  0.5, 500),
                ("depth", depth, 0.5, 500),
                ("height",rh,    0.1, 100),
            ]:
                if fv > 0 and not (lo <= fv <= hi):
                    issues.append(f"⚠️  [{eid}] roof {fname}={fv}m，建议在 {lo}~{hi}m")

        elif t == "opening":
            w = el.get("width", 0)
            h = el.get("height", 0)
            for fname, fv in [("width", w), ("height", h)]:
                if fv > 0 and not (0.1 <= fv <= 20):
                    issues.append(f"⚠️  [{eid}] opening {fname}={fv}m，建议在 0.1~20m")

        elif t == "stair":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            dh = abs(to[1] - f[1])
            dx = to[0]-f[0]; dz = to[2]-f[2]
            horiz = math.sqrt(dx*dx + dz*dz)
            if dh > 0 and not (0.1 <= dh <= 50):
                issues.append(f"⚠️  [{eid}] stair 高差={dh:.1f}m，建议在 0.1~50m")
            if horiz > 0 and not (0.1 <= horiz <= 100):
                issues.append(f"⚠️  [{eid}] stair 水平距离={horiz:.1f}m，建议在 0.1~100m")

    if not issues:
        return f"✅ 所有 {len(elements)} 个构件尺寸合理。"
    return "\n".join(issues)


# ============================================================
# 查询类 Tool —— 不修改 Blueprint，只返回场景信息供 LLM 参考
# ============================================================

def compute_wall_bounding_box(blueprint: dict) -> dict:
    """返回结构墙体的机器可读包围盒，供状态图和组件节点共享。"""
    walls = [
        element
        for element in _get_elements(blueprint)
        if isinstance(element, dict)
        and element.get("type") == "wall"
        and _is_structural_wall(element)
    ]
    points: list[list[float]] = []
    for wall in walls:
        for field in ("from", "to"):
            value = wall.get(field)
            if not isinstance(value, list) or len(value) != 3:
                continue
            try:
                point = [float(value[0]), float(value[1]), float(value[2])]
            except (TypeError, ValueError):
                continue
            if all(number == number and abs(number) != float("inf") for number in point):
                points.append(point)

    if not points:
        return {}

    minimum = [min(point[index] for point in points) for index in range(3)]
    maximum = [max(point[index] for point in points) for index in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "center": [(minimum[index] + maximum[index]) / 2 for index in range(3)],
        "size": [maximum[index] - minimum[index] for index in range(3)],
        "wall_count": len(walls),
    }


@tool
def get_wall_bounding_box(blueprint: dict) -> str:
    """
    查询所有墙体的 XZ 平面包围盒信息。

    返回墙体覆盖范围（宽度/进深）、中心点坐标、墙高范围，
    用于在生成 roof / floor 等覆盖类构件前获取正确的目标尺寸。

    重要：生成 roof 前必须先调用此工具！roof 的 span/depth 必须 >= 墙体包围盒。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = [
        el for el in elements
        if el.get("type") == "wall" and _is_structural_wall(el)
    ]

    if not walls:
        return "⚠️  场景中没有墙体，无法计算包围盒。"

    all_x, all_z = [], []
    all_y_min, all_y_max = [], []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to", [0, 0, 0])
        all_x.extend([f[0], t[0]])
        all_z.extend([f[2], t[2]])
        all_y_min.append(min(f[1], t[1]))
        all_y_max.append(max(f[1], t[1]))

    min_x, max_x = min(all_x), max(all_x)
    min_z, max_z = min(all_z), max(all_z)
    span = max_x - min_x
    depth = max_z - min_z
    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2
    min_y = min(all_y_min)
    max_y = max(all_y_max)

    EAVE = 1.0  # 建议出檐

    return (
        f"📐 墙体 XZ 包围盒信息：\n"
        f"  - X 方向（宽度/面阔）：{span:.1f}m（从 {min_x:.1f} 到 {max_x:.1f}，中心={center_x:.1f}）\n"
        f"  - Z 方向（进深）：{depth:.1f}m（从 {min_z:.1f} 到 {max_z:.1f}，中心={center_z:.1f}）\n"
        f"  - Y 方向（高度）范围：{min_y:.1f}m ~ {max_y:.1f}m（最大墙高={max_y:.1f}m）\n"
        f"  - 墙体数量：{len(walls)} 面\n"
        f"\n"
        f"💡 屋顶生成建议：\n"
        f"  - roof.span 应设为 {span + EAVE * 2:.1f}m（墙体宽度 + {EAVE * 2:.1f}m 出檐）\n"
        f"  - roof.depth 应设为 {depth + EAVE * 2:.1f}m（墙体进深 + {EAVE * 2:.1f}m 出檐）\n"
        f"  - roof.position = [{center_x:.1f}, {max_y:.1f}, {center_z:.1f}]（墙顶中心）\n"
        f"  - 如果是多屋顶设计，请根据各自的覆盖范围分别设置"
    )


# P0：屋顶自动修正

@tool
def fix_roof_coverage(blueprint: dict) -> str:
    """
    自动修正屋顶的 span/depth/position，使其合理覆盖屋顶标高处的承托墙体。

    修正逻辑：
      1. 按 roof.position.y 选择同标高的承托墙体
      2. span/depth = 承托墙跨度 + 出檐（默认 0.6m 每侧）
      4. position.x = wall X 中心
      5. position.z = wall Z 中心
      6. position.y 保持不变（由 LLM 生成，通常是墙顶高度）

    仅修正 span/depth 明显不匹配的屋顶（差值 > 2m）。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls  = [el for el in elements if el.get("type") == "wall"]
    roofs  = [el for el in elements if el.get("type") == "roof"]

    if not roofs:
        return "✅ 没有 roof 构件，跳过修正。"
    if not walls:
        return "⚠️  没有 wall 构件，无法计算屋顶目标尺寸。"

    EAVE = 0.6
    fixes: list[str] = []
    for r in roofs:
        rid   = r.get("id", "?")
        span  = r.get("span",  0)
        depth = r.get("depth", 0)
        bounds = get_roof_support_bounds(walls, r)
        wall_span = bounds["span"]
        wall_depth = bounds["depth"]
        center_x = bounds["center_x"]
        center_z = bounds["center_z"]
        target_span = round(wall_span + EAVE * 2, 2)
        target_depth = round(wall_depth + EAVE * 2, 2)
        pos = r.get("position", [center_x, bounds["support_y"], center_z])

        changed: list[str] = []

        # span 差值 > 2m 才修正
        if abs(span - target_span) > 2.0:
            r["span"] = target_span
            changed.append(f"span {span} → {target_span}")

        # depth 差值 > 2m 才修正
        if abs(depth - target_depth) > 2.0:
            r["depth"] = target_depth
            changed.append(f"depth {depth} → {target_depth}")

        # 退台建筑的顶层中心可能与首层相差数米，中心偏差超过 0.25m 即修正。
        if isinstance(pos, list) and len(pos) >= 3:
            if abs(pos[0] - center_x) > 0.25:
                changed.append(f"position.x {pos[0]} → {center_x:.2f}")
                pos[0] = round(center_x, 2)
            if abs(pos[2] - center_z) > 0.25:
                changed.append(f"position.z {pos[2]} → {center_z:.2f}")
                pos[2] = round(center_z, 2)
            r["position"] = pos

        if changed:
            fixes.append(f"🔧 [{rid}]: " + ", ".join(changed))

    if not fixes:
        return "✅ 所有屋顶均已匹配各自标高处的承托墙体，无需修正。"
    return "已按屋顶标高处的承托墙体修正覆盖范围：\n" + "\n".join(fixes)


# P1：墙体端点自动对齐

def _segment_is_floor_boundary(
    start: tuple[float, float],
    end: tuple[float, float],
    base_y: float,
    floors: list[dict],
) -> bool:
    """判断一条轴对齐线段是否位于同层矩形楼板并集的外边界。"""
    level_floors = [
        floor for floor in floors
        if abs(float(floor.get("from", [0, 0, 0])[1]) - base_y) <= 0.25
    ]
    if not level_floors:
        return False
    x1, z1 = start
    x2, z2 = end
    if abs(x1 - x2) > 0.15 and abs(z1 - z2) > 0.15:
        return False

    def covered(x: float, z: float) -> bool:
        for floor in level_floors:
            floor_from = floor.get("from", [0, 0, 0])
            floor_to = floor.get("to", [0, 0, 0])
            min_x, max_x = sorted((float(floor_from[0]), float(floor_to[0])))
            min_z, max_z = sorted((float(floor_from[2]), float(floor_to[2])))
            if min_x - 0.01 <= x <= max_x + 0.01 and min_z - 0.01 <= z <= max_z + 0.01:
                return True
        return False

    mid_x, mid_z = (x1 + x2) / 2, (z1 + z2) / 2
    offset = 0.05
    if abs(x1 - x2) <= 0.15:
        side_a = covered(mid_x - offset, mid_z)
        side_b = covered(mid_x + offset, mid_z)
    else:
        side_a = covered(mid_x, mid_z - offset)
        side_b = covered(mid_x, mid_z + offset)
    return side_a != side_b


@tool
def fix_wall_junctions(blueprint: dict) -> str:
    """
    自动对齐孤立的墙体端点，消除墙体转角缝隙。

    修正逻辑：
      1. 对近距离孤立端点执行吸附；
      2. 合法 T 形连接不修改；
      3. 若剩余孤立端点之间的轴对齐缺口位于楼板并集外边界，补建缺失墙段。
      若距离在 (TOLERANCE, MAX_SNAP] 范围内，则把孤立端点坐标对齐到目标端点。
      - TOLERANCE = 0.15m（已在容差内的不处理）
      - MAX_SNAP   = 0.5m（超过此距离不自动对齐，避免误操作）

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = [
        el for el in elements
        if el.get("type") == "wall" and _is_structural_wall(el)
    ]
    floors = [el for el in elements if el.get("type") == "floor"]

    if len(walls) < 2:
        return "✅ 少于 2 面墙，跳过端点对齐。"

    TOLERANCE = 0.15
    MAX_SNAP  = 0.5

    # 收集所有端点
    endpoints: list[dict] = []
    for w in walls:
        f = w.get("from", [0, 0, 0])
        t = w.get("to",   [0, 0, 0])
        bottom, top = _wall_vertical_range(w)
        endpoints.append({
            "wall": w, "which": "from", "x": float(f[0]), "z": float(f[2]),
            "bottom": bottom, "top": top,
        })
        endpoints.append({
            "wall": w, "which": "to", "x": float(t[0]), "z": float(t[2]),
            "bottom": bottom, "top": top,
        })

    fixes: list[str] = []

    for ep in endpoints:
        # 检查是否已有邻居
        has_neighbor = any(
            other_wall is not ep["wall"]
            and min(ep["top"], _wall_vertical_range(other_wall)[1])
            - max(ep["bottom"], _wall_vertical_range(other_wall)[0]) > 0.15
            and _plan_point_on_wall_segment(ep["x"], ep["z"], other_wall, TOLERANCE)
            for other_wall in walls
        )
        if has_neighbor:
            continue

        # 找最近的其他墙端点
        candidates = [
            (math.sqrt((ep["x"]-o["x"])**2 + (ep["z"]-o["z"])**2), o)
            for o in endpoints
            if o["wall"] is not ep["wall"]
        ]
        if not candidates:
            continue
        dist, nearest = min(candidates, key=lambda x: x[0])

        if TOLERANCE < dist <= MAX_SNAP:
            wall  = ep["wall"]
            which = ep["which"]
            old_x, old_z = ep["x"], ep["z"]
            new_x, new_z = nearest["x"], nearest["z"]

            # 修改 blueprint dict
            coord = wall[which]  # list [x, y, z]
            coord[0] = new_x
            coord[2] = new_z
            ep["x"] = new_x
            ep["z"] = new_z

            fixes.append(
                f"🔧 [{wall.get('id','?')}.{which}]: "
                f"({old_x:.2f}, {old_z:.2f}) → ({new_x:.2f}, {new_z:.2f})  "
                f"dist={dist:.3f}m"
            )

    # 吸附后重新识别孤立端点，只对楼板外边界上的轴对齐缺口补墙。
    isolated = []
    for ep in endpoints:
        connected = any(
            other_wall is not ep["wall"]
            and min(ep["top"], _wall_vertical_range(other_wall)[1])
            - max(ep["bottom"], _wall_vertical_range(other_wall)[0]) > 0.15
            and _plan_point_on_wall_segment(ep["x"], ep["z"], other_wall, TOLERANCE)
            for other_wall in walls
        )
        if not connected:
            isolated.append(ep)

    used_ids = {str(element.get("id")) for element in elements}
    for ep in isolated:
        candidates: list[tuple[float, dict]] = []
        for other in endpoints:
            if other["wall"] is ep["wall"]:
                continue
            same_level = abs(ep["bottom"] - other["bottom"]) <= 0.15
            aligned = abs(ep["x"] - other["x"]) <= 0.15 or abs(ep["z"] - other["z"]) <= 0.15
            distance = math.hypot(ep["x"] - other["x"], ep["z"] - other["z"])
            if same_level and aligned and distance > TOLERANCE:
                candidates.append((distance, other))
        for distance, other in sorted(candidates, key=lambda item: item[0]):
            if not _segment_is_floor_boundary(
                (ep["x"], ep["z"]),
                (other["x"], other["z"]),
                ep["bottom"],
                floors,
            ):
                continue
            repair_index = 1
            repair_id = f"wall_repair_{repair_index}"
            while repair_id in used_ids:
                repair_index += 1
                repair_id = f"wall_repair_{repair_index}"
            new_wall = {
                "type": "wall",
                "id": repair_id,
                "from": [round(ep["x"], 3), ep["bottom"], round(ep["z"], 3)],
                "to": [round(other["x"], 3), ep["top"], round(other["z"], 3)],
                "thickness": float(ep["wall"].get("thickness", 0.24)),
                "material": ep["wall"].get("material", "wall_finish"),
            }
            elements.append(new_wall)
            walls.append(new_wall)
            used_ids.add(repair_id)
            fixes.append(
                f"🔧 [{repair_id}] 补齐楼板外边界墙段: "
                f"({ep['x']:.2f}, {ep['z']:.2f}) → ({other['x']:.2f}, {other['z']:.2f})"
            )
            break

    if not fixes:
        return "✅ 所有墙体端点及合法 T 形连接均已闭合，无需修正。"
    return "已自动修复墙体连接：\n" + "\n".join(fixes)


# P1：开口越界自动修正（继 validate_opening_fit）

@tool
def fix_opening_fit(blueprint: dict) -> str:
    """
    自动修正超出 parentWall 范围的 opening。

    修正策略：
      - 沿墙方向越界：将 from[0] 钳位到 [0, 墙长 - width]，width 超出墙长时等比例缩小
      - 高度方向越界：将 from[1] 钳位到 [墙底Y, 墙顶Y - height]，height 超出墙高时等比例缩小

    仅对严重越界（超出 0.5m）的 opening 进行修正，轻微偏差保留原样。

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    walls = {el["id"]: el for el in elements if el.get("type") == "wall"}
    openings = [el for el in elements if el.get("type") == "opening"]
    components = blueprint.get("geometry", {}).get("components", [])
    door_windows = [
        c for c in components
        if c.get("type") in WALL_OPENING_COMPONENT_TYPES
    ]

    if not openings and not door_windows:
        return "✅ 没有 opening/门窗组件，跳过修正。"

    THRESHOLD = 0.5  # 只修正超出 0.5m 的情况，避免过度干扰用户设计意图

    fixes: list[str] = []
    for op in openings:
        oid = op.get("id", "?")
        parent_id = op.get("parentWall", "")
        parent = walls.get(parent_id)
        if not parent:
            continue

        wl = _wall_length(parent)
        wall_bottom_y, wall_top_y = _wall_vertical_range(parent)
        wall_height   = wall_top_y - wall_bottom_y

        along = op.get("from", [0, 0, 0])[0]
        base_y = op.get("from", [0, 0, 0])[1] if len(op["from"]) > 1 else wall_bottom_y
        width  = op.get("width", 1.0)
        height = op.get("height", 1.0)

        changed: list[str] = []

        # 1. 沿墙方向修正
        left_margin  = max(0.0, 0.0 - along)
        right_margin = max(0.0, (along + width) - wl)

        if left_margin > THRESHOLD:
            # 左端越界 → 向右移动，保持 width
            new_along = 0.1  # 留 0.1m 余量
            op["from"][0] = new_along
            changed.append(f"沿墙距离 {along:.2f} → {new_along:.2f}（左端越界 {left_margin:.2f}m）")
        elif right_margin > THRESHOLD:
            # 右端越界 → 向左移动，若 width 超过墙长则等比例缩小
            max_width = wl - 0.1
            if width > max_width:
                op["width"] = max_width
                changed.append(f"宽度 {width:.2f} → {max_width:.2f}（超出墙体 {right_margin:.2f}m）")
            # 移动起点
            new_along = max(0.1, wl - op["width"] - 0.1)
            op["from"][0] = new_along
            changed.append(f"沿墙距离 {along:.2f} → {new_along:.2f}（右端越界）")

        # 2. 高度方向修正
        bottom_margin = max(0.0, wall_bottom_y - base_y)
        top_margin    = max(0.0, (base_y + height) - wall_top_y)

        if bottom_margin > THRESHOLD:
            # 底部低于墙底 → 上移到墙底 + 余量
            new_base_y = wall_bottom_y + 0.1
            op["from"][1] = new_base_y
            changed.append(f"底部Y {base_y:.2f} → {new_base_y:.2f}（低于墙底 {bottom_margin:.2f}m）")
        elif top_margin > THRESHOLD:
            # 顶部高于墙顶 → 等比例缩小或下移
            max_height = wall_height - 0.1
            if height > max_height:
                op["height"] = max_height
                changed.append(f"高度 {height:.2f} → {max_height:.2f}（超出墙体 {top_margin:.2f}m）")
            # 下移到底部
            new_base_y = wall_top_y - op["height"] - 0.1
            op["from"][1] = new_base_y
            changed.append(f"底部Y {base_y:.2f} → {new_base_y:.2f}（超出墙顶）")

        # 3. 防止尺寸为零或负值
        if op.get("width", 1.0) <= 0.01:
            op["width"] = 0.1
            changed.append(f"宽度修正为 0.1m（原值为 {width}）")
        if op.get("height", 1.0) <= 0.01:
            op["height"] = 0.1
            changed.append(f"高度修正为 0.1m（原值为 {height}）")

        if changed:
            fixes.append(f"🔧 [{oid}]: " + "; ".join(changed))

    # ── 同样修正 door/window/bay_window 组合构件（components，非 elements）──
    for comp in door_windows:
        cid = comp.get("id", "?")
        parent_id = comp.get("parentWall", "")
        parent = walls.get(parent_id)
        if not parent:
            continue

        wl = _wall_length(parent)
        wall_bottom_y, wall_top_y = _wall_vertical_range(parent)

        along = comp.get("from", [0, 0, 0])[0]
        base_y = comp.get("from", [0, 0, 0])[1] if len(comp["from"]) > 1 else wall_bottom_y
        width  = comp.get("width", 1.0)
        height = comp.get("height", 1.0)

        changed: list[str] = []

        # 沿墙方向修正
        if along < -THRESHOLD:
            comp["from"][0] = 0.0
            changed.append(f"from[0] {along:.2f} → 0（左越界）")
        
        # 修复右越界：先钳位 along，再钳位 width
        if along + width > wl + THRESHOLD:
            # 先确保 along 不超出墙长
            clamped_along = min(along, wl - 0.1)
            if along > clamped_along:
                comp["from"][0] = round(clamped_along, 2)
                changed.append(f"from[0] {along:.2f} → {clamped_along:.2f}（起点超出墙长）")
                along = clamped_along
            
            # 再钳位 width
            max_width = wl - along
            if max_width < 0.1:
                max_width = 0.1
            
            if width > max_width:
                comp["width"] = round(max_width, 2)
                changed.append(f"宽度 {width:.2f} → {max_width:.2f}（超出墙体）")

        # 高度方向修正
        if height > 0 and base_y + height > wall_top_y + THRESHOLD:
            max_height = wall_top_y - max(base_y, wall_bottom_y)
            if max_height > 0.1:
                comp["height"] = round(max_height, 2)
                changed.append(f"高度 {height:.2f} → {max_height:.2f}（超出墙顶）")

        if changed:
            fixes.append(f"🔧 [component:{cid}]: " + "; ".join(changed))

    conflict_stats = _resolve_wall_opening_component_conflicts(blueprint)
    relocated = conflict_stats["relocated_bay_windows"]
    replaced = conflict_stats["replaced_windows"]
    pruned = conflict_stats["pruned_bay_windows"]
    relocated_windows = conflict_stats["relocated_windows"]
    pruned_windows = conflict_stats["pruned_windows"]
    if relocated:
        fixes.append("🔧 凸窗移至安全窗位: " + ", ".join(relocated))
    if replaced:
        fixes.append("🔧 移除被门/凸窗替换的普通窗: " + ", ".join(replaced))
    if pruned:
        fixes.append("🔧 无安全窗位，移除冲突凸窗: " + ", ".join(pruned))
    if relocated_windows:
        fixes.append("🔧 普通窗移至同墙安全位置: " + ", ".join(relocated_windows))
    if pruned_windows:
        fixes.append("🔧 同墙无安全位置，移除重叠普通窗: " + ", ".join(pruned_windows))

    if not fixes:
        return "✅ 所有 opening/门窗组件均在 parentWall 合理范围内，无需修正。"
    return "已自动修正以下 opening/门窗组件越界问题：\n" + "\n".join(fixes)


# P1：楼梯端点高度自动对齐

@tool
def fix_stair_alignment(blueprint: dict) -> str:
    """
    自动修正楼梯端点高度，使其对齐到最近的地板或墙体高度。

    修正逻辑：
      - 收集所有可用参考高度（地板顶面Y、墙体顶部Y、地面Y=0）
      - 将 stair.from.y 对齐到最近的参考高度（偏差超过 0.2m 才修正）
      - 将 stair.to.y 对齐到下一个更高的参考高度
      - 确保 from.y < to.y（楼梯向上）

    参数 blueprint: 完整的 Blueprint dict
    """
    elements = _get_elements(blueprint)
    stairs = [el for el in elements if el.get("type") == "stair"]
    if not stairs:
        return "✅ 没有 stair 构件，跳过修正。"

    # 收集参考高度
    ref_ys: list[float] = [0.0]
    for el in elements:
        if el.get("type") == "floor":
            fy = el.get("from", [0, 0, 0])[1]
            thickness = el.get("thickness", 0.0)
            if isinstance(fy, (int, float)):
                ref_ys.append(float(fy) + float(thickness))  # 楼板顶面
        elif el.get("type") == "wall":
            ty = el.get("to", [0, 0, 0])[1]
            if isinstance(ty, (int, float)):
                ref_ys.append(float(ty))
    ref_ys = sorted(set(ref_ys))

    TOL = 0.2  # 20cm 容差，小于此值时视为已对齐

    fixes: list[str] = []
    for s in stairs:
        sid = s.get("id", "?")
        f = s.get("from", [0, 0, 0])
        t = s.get("to",   [0, 0, 0])
        fy = float(f[1]) if len(f) > 1 else 0.0
        ty = float(t[1]) if len(t) > 1 else 0.0

        changed: list[str] = []

        # 对齐 from.y
        if ref_ys:
            best_ref = min(ref_ys, key=lambda h: abs(h - fy))
            if abs(fy - best_ref) > TOL:
                f[1] = best_ref
                changed.append(f"from.y {fy:.2f} → {best_ref:.2f}")

        # 对齐 to.y（找比当前 from.y 更高的最近参考高度）
        from_y = f[1]
        higher_refs = [h for h in ref_ys if h > from_y]
        if higher_refs:
            best_to = min(higher_refs, key=lambda h: abs(h - ty))
            if abs(ty - best_to) > TOL:
                t[1] = best_to
                changed.append(f"to.y {ty:.2f} → {best_to:.2f}")
        else:
            # 没有更高参考，设为 from.y + 0.3m（标准踏步高度）
            new_to_y = from_y + 0.3
            if abs(ty - new_to_y) > TOL:
                t[1] = new_to_y
                changed.append(f"to.y {ty:.2f} → {new_to_y:.2f}（默认踏步高度）")

        # 检查 from.y < to.y，若不成立则交换
        if f[1] >= t[1]:
            f[1], t[1] = t[1], f[1]
            changed.append("from/to Y 互换（确保楼梯向上）")

        if changed:
            fixes.append(f"🔧 [{sid}]: " + ", ".join(changed))

    placement_issues = collect_stair_placement_issues(blueprint)

    def is_generated_stair_id(item: dict) -> bool:
        parts = str(item.get("id") or "").split("_")
        return (
            len(parts) == 3
            and parts[0] == "stair"
            and parts[1].isdigit()
            and parts[2].isdigit()
        )

    floor_levels = _floor_regions_by_level(elements)
    floor_gaps = [
        next_y - current_y
        for (current_y, _), (next_y, _) in zip(floor_levels, floor_levels[1:])
        if next_y - current_y > 0.2
    ]
    if (
        placement_issues
        and stairs
        and all(is_generated_stair_id(item) for item in stairs)
        and floor_gaps
    ):
        preferred_widths = [
            float(item.get("width"))
            for item in stairs
            if isinstance(item.get("width"), (int, float))
        ]
        layout = shared_stair_layout(
            [regions for _, regions in floor_levels],
            min(floor_gaps),
            min(preferred_widths, default=1.8),
        )
        if layout:
            start = layout["start"]
            end = layout["end"]
            ordered_stairs = sorted(
                stairs,
                key=lambda item: float((item.get("from") or [0, 0, 0])[1]),
            )
            for index, stair in enumerate(ordered_stairs):
                lower, upper = (start, end) if index % 2 == 0 else (end, start)
                stair["from"][0] = lower[0]
                stair["from"][2] = lower[1]
                stair["to"][0] = upper[0]
                stair["to"][2] = upper[1]
                stair["width"] = layout["width"]
            fixes.append(
                "🔧 楼梯栈移全楼共同有效区域，"
                "并交替梯段方向使相邻平台连续"
            )

    if not fixes:
        return "✅ 所有 stair 端点高度已合理对齐，无需修正。"
    return "已自动修正以下 stair 高度对齐：\n" + "\n".join(fixes)


# P1：构件尺寸自动修正（继 validate_element_dimensions）

@tool
def fix_element_dimensions(blueprint: dict) -> str:
    """
    自动修正严重异常的构件尺寸。

    修正策略：
      - 超出上限 2 倍以上的尺寸才修正（防止过度干预合理设计）
      - 按合理范围上限的 0.9 倍收缩
      - 保留组件比例（如 wall 的厚度与高度比例）
      - wall/column 的建议高度上限只产生警告，不改写合法的高层建筑总高度
      - wall 的 from/to 是 WILD 1.1 高度事实源，移除与其重复或冲突的 height

    参数 blueprint: 完整的 Blueprint dict
    """
    RULES = {
        "wall":      {"length": (0.1, 500), "height": (0.1, 50),  "thickness": (0.01, 5)},
        "floor":     {"span":   (0.1, 500), "thickness": (0.01, 5)},
        "column":    {"height": (0.1, 50),  "radius": (0.01, 5)},
        "beam":      {"length": (0.1, 200), "width": (0.01, 5),   "height": (0.01, 5)},
        "roof":      {"span":   (0.5, 500), "depth": (0.5, 500),  "height": (0.1, 100)},
        "opening":   {"width":  (0.1, 20),  "height": (0.1, 20)},
        "stair":     {"rise":   (0.1, 50),  "run": (0.1, 100)},
    }

    elements = _get_elements(blueprint)
    fixes: list[str] = []

    for el in elements:
        t = el.get("type", "")
        eid = el.get("id", "?")
        if t not in RULES:
            continue

        changed: list[str] = []

        # wall 特殊处理
        if t == "wall":
            length = _wall_length(el)
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            endpoint_height = abs(to[1] - f[1])
            declared_height = el.get("height")
            has_declared_height = (
                isinstance(declared_height, (int, float))
                and not isinstance(declared_height, bool)
                and math.isfinite(float(declared_height))
                and float(declared_height) > 0
            )
            thickness = el.get("thickness", 0)

            lo, hi = RULES[t]["length"]
            if length > hi * 2:  # 超过上限 2 倍才修
                # 保持墙体方向，等比缩短到 hi * 0.9
                scale = hi * 0.9 / length
                el["to"][0] = f[0] + (to[0] - f[0]) * scale
                el["to"][2] = f[2] + (to[2] - f[2]) * scale
                changed.append(f"长度 {length:.1f} → {length*scale:.1f}m")

            if endpoint_height <= 0.01 and has_declared_height:
                bottom = min(float(f[1]), float(to[1]))
                el["from"][1] = bottom
                el["to"][1] = round(bottom + float(declared_height), 2)
                el.pop("height", None)
                changed.append(
                    f"将 height={float(declared_height):.1f}m 统一为 from/to 竖向范围"
                )
            elif endpoint_height <= 0.01:
                bottom = min(float(f[1]), float(to[1]))
                new_top = _infer_wall_top(elements, bottom)
                el["from"][1] = bottom
                el["to"][1] = round(new_top, 2)
                changed.append(
                    f"高度 {endpoint_height:.1f} → {new_top - bottom:.1f}m（按楼板标高/常用层高补全）"
                )
            elif has_declared_height:
                # WILD 1.1 使用 from/to 表达墙高。保留端点意味着既不会把百米外壳
                # 静默压矮，也不会留下 height 与端点范围互相冲突的双重事实源。
                el.pop("height", None)
                changed.append(
                    f"移除重复 height={float(declared_height):.1f}m，"
                    f"保留 from/to 竖向范围={endpoint_height:.1f}m"
                )

            lo, hi = RULES[t]["thickness"]
            if thickness > hi * 2:
                el["thickness"] = hi * 0.9
                changed.append(f"厚度 {thickness:.1f} → {el['thickness']:.1f}m")

        # beam 特殊处理（长度）
        elif t == "beam":
            f, to = el.get("from", [0,0,0]), el.get("to", [0,0,0])
            dx, dy, dz = to[0]-f[0], to[1]-f[1], to[2]-f[2]
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            lo, hi = RULES[t]["length"]
            if length > hi * 2:
                scale = hi * 0.9 / length
                el["to"][0] = f[0] + dx * scale
                el["to"][1] = f[1] + dy * scale
                el["to"][2] = f[2] + dz * scale
                changed.append(f"长度 {length:.1f} → {length*scale:.1f}m")

        # 楼板 / 楼梯：通用字段修正
        elif t in ("floor", "stair"):
            for field, (lo, hi) in RULES[t].items():
                val = el.get(field)
                if val is not None and isinstance(val, (int, float)) and val > hi * 2:
                    el[field] = hi * 0.9
                    changed.append(f"{field} {val:.1f} → {el[field]:.1f}m")

        # 屋顶修正（已在 fix_roof_coverage 中处理，这里只兜底极端值）
        elif t == "roof":
            for field, (lo, hi) in [("span", RULES[t]["span"]),
                                     ("depth", RULES[t]["depth"]),
                                     ("height", RULES[t]["height"])]:
                if field in el:
                    val = el[field]
                    if val > hi * 3:  # 极端异常才修
                        el[field] = hi * 0.9
                        changed.append(f"{field} {val:.1f} → {el[field]:.1f}m")

        # 柱高超过建议范围只产生警告。高层建筑的全高柱是合法表达，不能在这里
        # 静默压成 45m；如需分段，应由标准层模板或明确的结构编译规则负责。
        elif t == "column":
            pass

        # 其余类型（opening 等）：通用字段兜底修正
        else:
            for field, (lo, hi) in RULES[t].items():
                val = el.get(field)
                if val is not None and isinstance(val, (int, float)) and val > hi * 2:
                    el[field] = hi * 0.9
                    changed.append(f"{field} {val:.1f} → {el[field]:.1f}m")

        if changed:
            fixes.append(f"🔧 [{eid}]: " + "; ".join(changed))

    if not fixes:
        return "✅ 所有构件尺寸在合理范围内，无需修正。"
    return "已自动修正以下构件尺寸异常：\n" + "\n".join(fixes)


# P1：竖向构件高程自动修正（继 validate_collision 悬空检测）

@tool
def fix_element_elevations(blueprint: dict) -> str:
    """
    自动修正竖向构件底部 Y 坐标，使其对齐到最近的楼板顶面（含地面 Y=0）。

    修正对象：
      - column：base[1]（柱子底面 Y）
      - stair：from[1]（楼梯起点 Y）
      - furniture：position[1]（家具底面 Y）

    修正阈值：
      - gap > 0.3m（悬空超过容差）→ 修正到最近楼板 Y
      - gap < -0.1m（穿入楼板）    → 修正到最近楼板 Y

    仅修改底部锚点 Y 坐标，不触碰其他任何字段。

    参数 blueprint: 完整的 Blueprint dict（直接修改，原地更新）
    """
    elements = _get_elements(blueprint)

    floor_base_ys, floor_top_ys = _floor_reference_ys(blueprint)

    FLOAT_THRESH = 0.31  # 悬空超过 0.31m 才修正（略大于 validate_collision 的 0.3m 容差，避免浮点误差边界触发）
    EMBED_THRESH = 0.1   # 穿入超过 0.1m 才修正

    # 各类型的底部 Y 获取/设置方式
    TYPE_CONFIG = {
        "column":    ("base",     1),
        "stair":     ("from",     1),
        "furniture": ("position", 1),
    }

    fixes: list[str] = []

    for el in elements:
        t = el.get("type", "")
        if t not in TYPE_CONFIG:
            continue

        field, idx = TYPE_CONFIG[t]
        coord = el.get(field)
        if not coord or len(coord) <= idx:
            continue  # 坐标缺失，跳过

        bottom_y = float(coord[idx])
        ref_ys = floor_top_ys if t == "furniture" else floor_base_ys
        nearest_floor = min(ref_ys, key=lambda h: abs(h - bottom_y))
        gap = bottom_y - nearest_floor

        if gap > FLOAT_THRESH or gap < -EMBED_THRESH:
            eid = el.get("id", "?")
            coord[idx] = nearest_floor
            fixes.append(
                f"🔧 [{eid}]（{t}）底部 Y: {bottom_y:.3f} → {nearest_floor:.3f}"
                f"（{'悬空' if gap > 0 else '穿入'} {abs(gap):.3f}m，对齐到楼板 Y={nearest_floor:.3f}）"
            )

    if not fixes:
        ref_str = ", ".join(f"{h:.2f}" for h in floor_base_ys)
        return f"✅ 所有竖向构件底部 Y 均已对齐楼板，无需修正。（参考高度: [{ref_str}]）"
    return (
        f"已自动修正 {len(fixes)} 个竖向构件的高程：\n"
        + "\n".join(fixes)
    )
