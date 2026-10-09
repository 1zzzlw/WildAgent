"""建筑设计清单与最终 Blueprint 的一致性校验。

 两类问题分开（用户决策 2026-09-29）：

- **空间/结构状态**（标高缺失、缺楼梯、超墙容量、批准槽位未落实）→
  :func:`validate_design_brief_constraints` 返回的**错误**，阻断交付；
- **配额数量缺口**（"canopy 数量 1 少于设计下限 2"）→ :func:`design_quota_shortfalls`
  返回的**警告**，只标记不阻断。数量缺口是"模型补量"问题，不是"蓝图非法"
  问题——拿数量拦下整张蓝图，等于因为少摆了几根柱子就撕掉全部图纸。
"""

from math import isfinite

def _entity_type_counts(blueprint: dict) -> dict[str, int]:
    """按类型统计蓝图实体数。凸窗占用并替换普通窗槽位，计入 window。"""
    geometry = blueprint.get("geometry", {})
    counts: dict[str, int] = {}
    for entity in [
        *geometry.get("elements", []),
        *geometry.get("components", []),
    ]:
        entity_type = entity.get("type")
        if entity_type:
            counts[entity_type] = counts.get(entity_type, 0) + 1
    counts["window"] = counts.get("window", 0) + counts.get("bay_window", 0)
    return counts


def design_quota_shortfalls(blueprint: dict, design_brief: dict | None) -> list[str]:
    """配额下限缺口清单——**警告，不阻断**。

    文案保持既有格式（``"<type> 数量 N 少于设计下限 M"``）：
    ``issues.py::_MISSING_QUOTA`` 按它分类修复目标。消费方把结果当 warn 面世
    （编译报告 / 校验流水线 warning 步骤），模型通道负责补量。
    """
    if not isinstance(design_brief, dict):
        return []
    counts = _entity_type_counts(blueprint)
    shortfalls: list[str] = []
    for component_type, limits in (design_brief.get("component_quota") or {}).items():
        if not isinstance(limits, dict):
            continue
        actual = counts.get(component_type, 0)
        # balcony 自带 U 形栏杆，可满足 railing 的最低需求；但它已有独立的
        # balcony 配额，不能再占用独立 railing 的数量。
        minimum_actual = (
            actual + counts.get("balcony", 0)
            if component_type == "railing"
            else actual
        )
        minimum = limits.get("min")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and minimum_actual < minimum:
            shortfalls.append(
                f"{component_type} 数量 {minimum_actual} 少于设计下限 {minimum}"
            )
    return shortfalls


def validate_design_brief_constraints(
    blueprint: dict,
    design_brief: dict | None,
) -> list[str]:
    """验证骨架设计清单中的**空间/结构**硬约束（数量缺口见 quota_shortfalls）。"""
    if not isinstance(design_brief, dict):
        return []

    geometry = blueprint.get("geometry", {})
    counts = _entity_type_counts(blueprint)

    errors: list[str] = []

    realization = design_brief.get("realization")
    if isinstance(realization, dict) and realization.get("representation_mode", "full") == "full":
        try:
            modeled_floors = max(1, int(realization.get("modeled_floors", 1)))
            floor_height = max(0.1, float(realization.get("floor_height", 3.2)))
        except (TypeError, ValueError):
            modeled_floors = 1
            floor_height = 3.2
        if modeled_floors > 1:
            walls = [item for item in geometry.get("elements", []) if item.get("type") == "wall"]
            floors = [item for item in geometry.get("elements", []) if item.get("type") == "floor"]
            wall_levels = {
                round(min(float(item["from"][1]), float(item["to"][1])), 2)
                for item in walls
                if is_finite_vec3(item.get("from")) and is_finite_vec3(item.get("to"))
            }
            floor_levels = {
                round(float(item["from"][1]), 2)
                for item in floors
                if is_finite_vec3(item.get("from"))
            }
            expected_levels = [round(index * floor_height, 2) for index in range(modeled_floors)]
            missing_wall_levels = [
                level for level in expected_levels
                if not any(abs(actual - level) <= 0.25 for actual in wall_levels)
            ]
            missing_floor_levels = [
                level for level in expected_levels
                if not any(abs(actual - level) <= 0.25 for actual in floor_levels)
            ]
            if missing_wall_levels:
                errors.append(
                    f"建筑方案要求 {modeled_floors} 层，但缺少墙体标高 {missing_wall_levels}"
                )
            if missing_floor_levels:
                errors.append(
                    f"建筑方案要求 {modeled_floors} 层，但缺少楼板标高 {missing_floor_levels}"
                )
            if not counts.get("stair"):
                errors.append(f"建筑方案要求 {modeled_floors} 层，但没有 stair 构件")

    quotas = design_brief.get("component_quota", {})
    # 配额数量缺口不再是错误（用户决策 2026-09-29，见 design_quota_shortfalls）；
    # 这里只保留"批准槽位未落实"——它是**空间状态**错误（总数对但立面节奏错位）。
    openings_by_wall: dict[str, int] = {}
    for component in geometry.get("components", []):
        if component.get("type") not in {"door", "window", "bay_window"}:
            continue
        parent_wall = component.get("parentWall")
        if parent_wall:
            openings_by_wall[parent_wall] = openings_by_wall.get(parent_wall, 0) + 1

    for wall_id, plan in design_brief.get("facade_plan", {}).items():
        if not isinstance(plan, dict):
            continue
        maximum = plan.get("max_openings")
        actual = openings_by_wall.get(wall_id, 0)
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and actual > maximum:
            errors.append(
                f"墙 {wall_id} 有 {actual} 个门窗，超过立面上限 {maximum}"
            )

    # 当配额要求完整实现全部已解析槽位时，数量正确仍不够：每个门窗还必须
    # 落在对应墙面和局部坐标上。这样可阻止“总数通过、立面节奏错位”。
    opening_slots = design_brief.get("opening_slots")
    if isinstance(opening_slots, list):
        for opening_type in ("door", "window"):
            slots = [
                slot for slot in opening_slots
                if isinstance(slot, dict) and slot.get("type") == opening_type
            ]
            limits = quotas.get(opening_type, {}) if isinstance(quotas.get(opening_type), dict) else {}
            if not slots or limits.get("min") != len(slots) or limits.get("max") != len(slots):
                continue
            candidates = [
                component for component in geometry.get("components", [])
                if component.get("type") == opening_type
                or (opening_type == "window" and component.get("type") == "bay_window")
            ]
            unmatched = list(candidates)
            missing_slot_ids: list[str] = []
            for slot in slots:
                slot_from = slot.get("from")
                match_index = next((
                    index for index, component in enumerate(unmatched)
                    if component.get("parentWall") == slot.get("wall_id")
                    and _opening_values_match(component.get("from"), slot_from)
                    and _opening_values_match(component.get("width"), slot.get("width"))
                    and _opening_values_match(component.get("height"), slot.get("height"))
                ), None)
                if match_index is None:
                    missing_slot_ids.append(str(slot.get("id") or "?"))
                else:
                    unmatched.pop(match_index)
            if missing_slot_ids:
                preview = ", ".join(missing_slot_ids[:4])
                suffix = "..." if len(missing_slot_ids) > 4 else ""
                errors.append(
                    f"{opening_type} 未落实 {len(missing_slot_ids)} 个批准槽位: {preview}{suffix}"
                )

    return errors


def _opening_values_match(actual: object, expected: object, tolerance: float = 0.01) -> bool:
    """比较门窗槽位标量或向量，容忍序列化产生的微小浮点误差。"""
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= tolerance
    if isinstance(actual, list) and isinstance(expected, list) and len(actual) == len(expected):
        return all(
            _opening_values_match(actual_item, expected_item, tolerance)
            for actual_item, expected_item in zip(actual, expected)
        )
    return actual == expected

def is_finite_vec3(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and isfinite(item)
            for item in value
        )
    )
