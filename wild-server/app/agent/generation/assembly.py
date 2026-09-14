"""蓝图分片装配后的确定性归一化、配额控制与修复。"""

from copy import deepcopy
from math import isfinite

from app.agent.validation.design_constraints import is_finite_vec3


_FIX_MAP = {
    "validate_reference_integrity": "fix_material_references",
    "validate_opening_coords": "fix_opening_coords",
    "validate_opening_fit": "fix_opening_fit",
    "validate_wall_junctions": "fix_wall_junctions",
    "validate_stair_alignment": "fix_stair_alignment",
    "validate_element_dimensions": "fix_element_dimensions",
    "validate_roof_coverage": "fix_roof_coverage",
}


def deduplicate_balcony_representations(blueprint: dict) -> dict:
    """移除与 balcony 组件同 footprint 的手写 floor 及其独立 railing。

    骨架模型偶尔会先用 floor 表达阳台，阳台节点又生成 balcony 组件。后者已经
    内嵌悬挑板和 U 形栏杆；两套同时保留会产生重叠楼板和密集杆件。
    """
    geometry = blueprint.get("geometry", {})
    elements = geometry.get("elements", [])
    components = geometry.get("components", [])
    walls = {
        item.get("id"): item
        for item in elements
        if isinstance(item, dict) and item.get("type") == "wall" and item.get("id")
    }
    wall_points = [
        point
        for wall in walls.values()
        for point in (wall.get("from"), wall.get("to"))
        if is_finite_vec3(point)
    ]
    if not wall_points:
        return {"removed_floor_ids": [], "removed_railing_count": 0}

    building_center = (
        (min(point[0] for point in wall_points) + max(point[0] for point in wall_points)) / 2,
        (min(point[2] for point in wall_points) + max(point[2] for point in wall_points)) / 2,
    )
    expected_footprints = []
    for component in components:
        if not isinstance(component, dict) or component.get("type") != "balcony":
            continue
        footprint = balcony_footprint(component, walls.get(component.get("parentWall")), building_center)
        if footprint:
            expected_footprints.append(footprint)
    if not expected_footprints:
        return {"removed_floor_ids": [], "removed_railing_count": 0}

    removed_floor_ids: set[str] = set()
    for element in elements:
        if not isinstance(element, dict) or element.get("type") != "floor":
            continue
        element_id = element.get("id")
        floor_from = element.get("from")
        floor_to = element.get("to")
        if not element_id or not is_finite_vec3(floor_from) or not is_finite_vec3(floor_to):
            continue
        floor_bounds = (
            min(floor_from[0], floor_to[0]), max(floor_from[0], floor_to[0]),
            min(floor_from[2], floor_to[2]), max(floor_from[2], floor_to[2]),
        )
        floor_y = (floor_from[1] + floor_to[1]) / 2
        if any(
            abs(floor_y - footprint["top_y"]) <= 0.05
            and footprint_iou(floor_bounds, footprint["bounds"]) >= 0.75
            for footprint in expected_footprints
        ):
            removed_floor_ids.add(str(element_id))

    kept_components = []
    removed_railing_count = 0
    for component in components:
        is_duplicate_balcony_railing = False
        if isinstance(component, dict) and component.get("type") == "railing":
            component_id = str(component.get("id") or "").lower()
            is_duplicate_balcony_railing = (
                component.get("parentFloor") in removed_floor_ids
                or "balcony" in component_id
            )
        if is_duplicate_balcony_railing:
            removed_railing_count += 1
            continue
        kept_components.append(component)

    geometry["elements"] = [
        element for element in elements
        if not isinstance(element, dict) or element.get("id") not in removed_floor_ids
    ]
    geometry["components"] = kept_components
    return {
        "removed_floor_ids": sorted(removed_floor_ids),
        "removed_railing_count": removed_railing_count,
    }


def balcony_footprint(
    component: dict,
    wall: dict | None,
    building_center: tuple[float, float],
) -> dict | None:
    if not isinstance(wall, dict):
        return None
    wall_from = wall.get("from")
    wall_to = wall.get("to")
    component_from = component.get("from")
    if not is_finite_vec3(wall_from) or not is_finite_vec3(wall_to) or not is_finite_vec3(component_from):
        return None
    width = component.get("width")
    depth = component.get("depth")
    if not positive_number(width) or not positive_number(depth):
        return None

    dx = wall_to[0] - wall_from[0]
    dz = wall_to[2] - wall_from[2]
    wall_length = (dx * dx + dz * dz) ** 0.5
    if wall_length <= 1e-6:
        return None
    direction = (dx / wall_length, dz / wall_length)
    normal = (-direction[1], direction[0])
    along, top_y, normal_offset = component_from
    center_along = along + width / 2
    wall_center = (
        wall_from[0] + direction[0] * center_along,
        wall_from[2] + direction[1] * center_along,
    )
    outward_dot = (
        (wall_center[0] - building_center[0]) * normal[0]
        + (wall_center[1] - building_center[1]) * normal[1]
    )
    exterior_sign = 1 if outward_dot > 1e-6 else -1
    start = (
        wall_from[0] + direction[0] * along + normal[0] * normal_offset,
        wall_from[2] + direction[1] * along + normal[1] * normal_offset,
    )
    end = (start[0] + direction[0] * width, start[1] + direction[1] * width)
    outside_start = (
        start[0] + normal[0] * exterior_sign * depth,
        start[1] + normal[1] * exterior_sign * depth,
    )
    outside_end = (
        end[0] + normal[0] * exterior_sign * depth,
        end[1] + normal[1] * exterior_sign * depth,
    )
    points = (start, end, outside_start, outside_end)
    return {
        "top_y": top_y,
        "bounds": (
            min(point[0] for point in points), max(point[0] for point in points),
            min(point[1] for point in points), max(point[1] for point in points),
        ),
    }


def remove_ground_level_railings(blueprint: dict) -> dict:
    """地面标高附近的门廊/平台不存在需要防坠的高差，不生成围挡入口的栏杆。"""
    geometry = blueprint.get("geometry", {})
    elements = geometry.get("elements", [])
    components = geometry.get("components", [])
    floor_tops: dict[str, float] = {}
    for element in elements:
        if not isinstance(element, dict) or element.get("type") != "floor":
            continue
        floor_from = element.get("from")
        floor_to = element.get("to")
        thickness = element.get("thickness", 0)
        if (
            element.get("id")
            and is_finite_vec3(floor_from)
            and is_finite_vec3(floor_to)
            and isinstance(thickness, (int, float))
            and not isinstance(thickness, bool)
            and isfinite(thickness)
        ):
            floor_tops[str(element["id"])] = max(floor_from[1], floor_to[1]) + max(0, thickness)

    removed_ids: list[str] = []
    kept_components = []
    for component in components:
        parent_floor = component.get("parentFloor") if isinstance(component, dict) else None
        floor_top = floor_tops.get(parent_floor)
        if (
            isinstance(component, dict)
            and component.get("type") == "railing"
            and floor_top is not None
            and floor_top <= 0.35
        ):
            removed_ids.append(str(component.get("id", "?")))
            continue
        kept_components.append(component)
    geometry["components"] = kept_components
    return {"removed_railing_ids": removed_ids}


def footprint_iou(first: tuple, second: tuple) -> float:
    ix = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    iz = max(0.0, min(first[3], second[3]) - max(first[2], second[2]))
    intersection = ix * iz
    first_area = max(0.0, first[1] - first[0]) * max(0.0, first[3] - first[2])
    second_area = max(0.0, second[1] - second[0]) * max(0.0, second[3] - second[2])
    union = first_area + second_area - intersection
    return intersection / union if union > 1e-9 else 0.0




def positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value > 0
    )


def enforce_component_quota(
    components: list[dict],
    quota: dict,
    fplan: dict,
    logger,
) -> tuple[list[dict], int]:
    """根据 design_brief.component_quota 剔除超额组件
    
    策略：按墙面优先级保留。主立面(max_openings多的)优先保留，侧墙/背面多余额外剔除。
    返回 (filtered_components, pruned_count)
    """
    # 按类型统计
    by_type: dict[str, list[int]] = {}
    for idx, comp in enumerate(components):
        ct = comp.get("type", "")
        if ct not in by_type:
            by_type[ct] = []
        by_type[ct].append(idx)
    
    pruned_indices: set[int] = set()
    
    for comp_type, max_quota in quota.items():
        if comp_type not in by_type:
            continue
        indices = by_type[comp_type]
        max_n = max_quota.get("max")
        if max_n is None or len(indices) <= max_n:
            continue
        
        logger.info(f"[merge] [{comp_type}] 超额: 当前 {len(indices)} 个, 配额最大 {max_n} 个")
        
        # ── 按优先级排序（主立面 > 非主立面）──
        def _priority(idx: int) -> int:
            comp = components[idx]
            parent_wall = comp.get("parentWall", "")
            wall_plan = fplan.get(parent_wall, {})
            if wall_plan.get("is_main_facade"):
                return 0  # 主立面，最高优先
            return 1 + (10 - wall_plan.get("max_openings", 0))  # 非主立面，max_openings 小的先剃
        
        # 按优先级排序，高优先在前
        sorted_indices = sorted(indices, key=_priority)
        # 保留前 max_n 个，剃除后面的
        to_prune = sorted_indices[max_n:]
        pruned_indices.update(to_prune)
        
        for idx in to_prune:
            comp = components[idx]
            logger.info(
                f"[merge] 剃除超额组件: [{comp_type}] id={comp.get('id', '?')}, "
                f"parentWall={comp.get('parentWall', '?')}"
            )
    
    if not pruned_indices:
        return components, 0
    
    filtered = [c for i, c in enumerate(components) if i not in pruned_indices]
    return filtered, len(pruned_indices)


def apply_fixes(blueprint: dict, errors: list) -> list[tuple[str, bool]]:
    """根据校验错误，调用对应的 fix_* 工具修复

    Args:
        blueprint: 待修复的 Blueprint（原地修改）
        errors: _final_errors 返回的错误列表

    Returns:
        [(fix_name, success), ...] 列表
    """
    from app.services.agent_service import _run_tool
    from app.tools import spatial_tools
    from loguru import logger

    applied: list[tuple[str, bool]] = []

    for error_result in errors:
        error_name = error_result.name.replace(" [recheck]", "")
        fix_name = _FIX_MAP.get(error_name)

        if not fix_name:
            logger.debug(f"[merge] {error_name} 无对应修复工具，跳过")
            continue

        fix_fn = getattr(spatial_tools, fix_name, None)
        if fix_fn is None:
            logger.warning(f"[merge] spatial_tools.{fix_name} 不存在")
            applied.append((fix_name, False))
            continue

        try:
            before_fix = deepcopy(blueprint)
            fix_output = _run_tool(fix_fn, blueprint)
            success = "❌" not in fix_output and blueprint != before_fix
            if not success:
                # 工具报告失败或没有产生有效变化时，不允许残留半完成修改。
                blueprint.clear()
                blueprint.update(before_fix)
            applied.append((fix_name, success))
            logger.info(f"[merge] 执行 {fix_name}: {'成功' if success else '仍有问题'}")
        except Exception as e:
            if 'before_fix' in locals():
                blueprint.clear()
                blueprint.update(before_fix)
            logger.error(f"[merge] 执行 {fix_name} 失败: {e}")
            applied.append((fix_name, False))

    return applied


def collect_json_parse_failures(component_diagnostics: object) -> list[tuple[str, str]]:
    """从并行组件诊断中收集 JSON 解析失败（非服务故障）条目。

    返回 ``[(component_type, label), ...]``，供 merge 决定是否生成配额级错误。
    """
    if not isinstance(component_diagnostics, dict):
        return []
    failures: list[tuple[str, str]] = []
    for diag_key, diag in component_diagnostics.items():
        if not str(diag_key).endswith("_gen_diag") or not isinstance(diag, dict):
            continue
        if diag.get("json_parse_failed") is not True:
            continue
        component_type = str(diag_key)[:-9]
        failures.append((component_type, str(diag.get("label") or component_type)))
    return failures
