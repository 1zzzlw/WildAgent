"""
Layer 2: 分片合并节点（含校验 + 修复 + 循环）

合并所有 Layer 1 产出的组件分片为完整 Blueprint，
然后执行校验流水线，对检测到的问题使用 fix_* 工具自动修复，
循环直到全部通过或达到最大迭代次数。

每次迭代通过 on_reasoning_delta 发射思考内容，让前端能看到合并推理过程。
"""
import time as _time
from math import isfinite
from copy import deepcopy
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.component_registry import COMPONENT_REGISTRY
from app.agent.diagnostics import blueprint_fingerprint
from app.agent.runtime_context import get_reasoning_callback
from app.utils.fragment_merger import merge_fragments

MAX_MERGE_ITERATIONS = 3

# 错误校验器名 → fix 工具名的映射
_FIX_MAP = {
    "validate_reference_integrity": "fix_material_references",
    "validate_opening_coords": "fix_opening_coords",
    "validate_opening_fit": "fix_opening_fit",
    "validate_wall_junctions": "fix_wall_junctions",
    "validate_stair_alignment": "fix_stair_alignment",
    "validate_element_dimensions": "fix_element_dimensions",
    "validate_roof_coverage": "fix_roof_coverage",
}


async def merge_fragments_node(state: GenerationState) -> dict:
    """合并所有组件分片 —— 校验 → 修复 → 循环"""

    t0 = _time.time()
    on_reasoning_delta = get_reasoning_callback()

    logger.info("[merge] 开始合并分片")

    # ── 发射思考开始 ──
    if on_reasoning_delta:
        await on_reasoning_delta("merge", "正在收集所有组件分片...\n")

    skeleton = state.get("skeleton_blueprint")
    design_brief = state.get("design_brief")  # ← 骨架设计清单
    if not skeleton:
        logger.error("[merge] 骨架缺失，无法合并")
        return {"error": "骨架缺失，无法合并组件", "status": "failed"}

    # ── 1. 收集所有组件分片 ──
    fragments: list[dict] = []
    fragment_summary: list[str] = []
    generic_fragments = state.get("component_fragments", {})

    for comp_type, cfg in COMPONENT_REGISTRY.items():
        if not cfg.implemented:
            continue
        data = generic_fragments.get(comp_type, state.get(cfg.output_key))
        if not data:
            continue
        if cfg.is_list and isinstance(data, list):
            if data:
                fragments.extend(data)
                fragment_summary.append(f"{cfg.label}×{len(data)}")
                logger.info(f"[merge] 收集到 {len(data)} 个 {cfg.label}")
        elif not cfg.is_list and isinstance(data, dict):
            fragments.append(data)
            fragment_summary.append(f"{cfg.label}×1")
            logger.info(f"[merge] 收集到 {cfg.label}")

    summary_text = "、".join(fragment_summary) if fragment_summary else "无组件"
    if on_reasoning_delta:
        await on_reasoning_delta("merge", f"已收集分片: {summary_text}\n")

    # ── 2. 合并 ──
    try:
        merged_blueprint = merge_fragments(skeleton, fragments)
    except Exception as e:
        logger.error(f"[merge] 合并失败: {e}")
        return {"error": f"分片合并失败: {str(e)}", "status": "failed"}

    elements = merged_blueprint.get("geometry", {}).get("elements", [])
    components = merged_blueprint.get("geometry", {}).get("components", [])
    logger.info(f"[merge] 初次合并: {len(elements)} elements, {len(components)} components")

    # ── 2.5 同一阳台只能保留一种表达：balcony 组件拥有自己的楼板和 U 形栏杆 ──
    balcony_cleanup = _deduplicate_balcony_representations(merged_blueprint)
    if balcony_cleanup["removed_floor_ids"]:
        elements = merged_blueprint.get("geometry", {}).get("elements", [])
        components = merged_blueprint.get("geometry", {}).get("components", [])
        logger.info(f"[merge] 阳台重复表达清理: {balcony_cleanup}")

    ground_railing_cleanup = _remove_ground_level_railings(merged_blueprint)
    if ground_railing_cleanup["removed_railing_ids"]:
        components = merged_blueprint.get("geometry", {}).get("components", [])
        logger.info(f"[merge] 地面平台冗余栏杆清理: {ground_railing_cleanup}")

    # ── 2.6 设计配额比对：超额组件按优先级剔除 ──
    quota_pruned = 0
    if design_brief:
        quota = design_brief.get("component_quota", {})
        fplan = design_brief.get("facade_plan", {})
        if quota and components:
            components, quota_pruned = _enforce_component_quota(components, quota, fplan, logger)
            if quota_pruned > 0:
                merged_blueprint["geometry"]["components"] = components
                logger.info(f"[merge] 配额强制: 移除了 {quota_pruned} 个超额组件")

    # ── 2.7 按方案槽位确定性吸附；模型负责风格，程序负责组合关系与安全边界 ──
    opening_layout = {"snapped": 0, "synthesized": 0, "pruned": 0}
    entrance_layout = {"canopy_snapped": 0, "light_snapped": 0}
    balcony_layout = {"snapped": 0, "synthesized": 0, "pruned": 0}
    roof_layout = {"split": 0, "synthesized": 0}
    railing_layout = {"synthesized": 0, "replaced": 0}
    if design_brief:
        from app.agent.architecture_plan import (
            conform_balconies_to_slots,
            conform_entrance_accessories,
            conform_openings_to_slots,
            conform_railings_to_slots,
            conform_roofs_to_slots,
        )

        components, opening_layout = conform_openings_to_slots(
            components,
            design_brief,
            merged_blueprint.get("materials", {}),
        )
        components, entrance_layout = conform_entrance_accessories(
            components,
            design_brief,
            merged_blueprint,
        )
        components, balcony_layout = conform_balconies_to_slots(components, design_brief)
        components, railing_layout = conform_railings_to_slots(components, design_brief)
        elements, roof_layout = conform_roofs_to_slots(elements, design_brief)
        merged_blueprint["geometry"]["elements"] = elements
        merged_blueprint["geometry"]["components"] = components
        if any((*opening_layout.values(), *entrance_layout.values(), *balcony_layout.values(), *roof_layout.values(), *railing_layout.values())):
            logger.info(
                f"[merge] 方案槽位对齐: opening={opening_layout}, entrance={entrance_layout}, "
                f"balcony={balcony_layout}, roof={roof_layout}, railing={railing_layout}"
            )

    design_errors = _validate_design_brief_constraints(merged_blueprint, design_brief)

    if on_reasoning_delta:
        await on_reasoning_delta(
            "merge",
            f"初次合并完成: {len(elements)} 个结构元素, {len(components)} 个组件"
            + (f"（配额比对后剔除 {quota_pruned} 个超额组件）" if quota_pruned else "")
            + (
                f"（清理重复阳台楼板 {len(balcony_cleanup['removed_floor_ids'])}、"
                f"栏杆 {balcony_cleanup['removed_railing_count']}）"
                if balcony_cleanup["removed_floor_ids"] else ""
            )
            + (
                f"（清理地面平台栏杆 {len(ground_railing_cleanup['removed_railing_ids'])}）"
                if ground_railing_cleanup["removed_railing_ids"] else ""
            )
            + (
                f"（槽位吸附 {opening_layout['snapped']}，补齐 {opening_layout['synthesized']}，"
                f"剔除无槽位开口 {opening_layout['pruned']}）"
                if any(opening_layout.values()) else ""
            )
            + (
                f"（阳台对位 {balcony_layout['snapped']}，补齐 {balcony_layout['synthesized']}）"
                if any(balcony_layout.values()) else ""
            )
            + (
                f"（入口雨棚 {entrance_layout['canopy_snapped']}、入口灯 {entrance_layout['light_snapped']} 对齐入口门）"
                if any(entrance_layout.values()) else ""
            )
            + (
                f"（U 形屋顶拆分新增 {roof_layout['split']} 片）"
                if any(roof_layout.values()) else ""
            )
            + (
                f"（退台栏杆补齐 {railing_layout['synthesized']}）"
                if any(railing_layout.values()) else ""
            )
            + (
                f"\n设计约束预检发现 {len(design_errors)} 个问题。"
                if design_errors else "\n设计约束预检通过。"
            )
            + f"\n开始校验→修复循环（最多 {MAX_MERGE_ITERATIONS} 轮）...\n",
        )

    # ── 3. 校验 → 修复 → 循环 ──
    from app.services.agent_delivery import final_validation_results
    from app.services.agent_service import run_validation_pipeline, _final_errors

    merge_diag: dict = {
        "label": "合并",
        "fragment_summary": summary_text,
        "element_count": len(elements),
        "component_count": len(components),
        "opening_layout": opening_layout,
        "entrance_layout": entrance_layout,
        "balcony_layout": balcony_layout,
        "roof_layout": roof_layout,
        "railing_layout": railing_layout,
        "balcony_cleanup": balcony_cleanup,
        "ground_railing_cleanup": ground_railing_cleanup,
        "design_errors": design_errors,
        "iterations": [],
    }

    final_errors: list = []
    pipeline_results: list = []

    for iteration in range(1, MAX_MERGE_ITERATIONS + 1):
        iter_t0 = _time.time()

        # 3a. 执行校验流水线
        pipeline_results = run_validation_pipeline(merged_blueprint)
        final_errors = _final_errors(pipeline_results)
        final_results = final_validation_results(pipeline_results)

        error_count = len(final_errors) + len(design_errors)
        warning_count = sum(
            1 for result in final_results if result.has_warning and not result.has_error
        )
        passed_count = len(final_results) - len(final_errors) - warning_count
        total_steps = len(final_results) + (1 if design_errors else 0)

        iter_ms = int((_time.time() - iter_t0) * 1000)

        iter_info = {
            "iteration": iteration,
            "total_steps": total_steps,
            "passed": passed_count,
            "warnings": warning_count,
            "errors": error_count,
            "design_errors": len(design_errors),
            "ms": iter_ms,
        }
        merge_diag["iterations"].append(iter_info)

        logger.info(
            f"[merge] 第{iteration}轮校验: {passed_count}通过, "
            f"{warning_count}警告, {error_count}错误 ({iter_ms}ms)"
        )

        if on_reasoning_delta:
            error_names = [r.name for r in final_errors] if final_errors else []
            if design_errors:
                error_names.append("validate_design_brief")
            status_line = (
                "全部通过"
                if not final_errors and not design_errors
                else f"{error_count}个错误: {', '.join(error_names)}"
            )
            await on_reasoning_delta(
                "merge",
                f"\n**第{iteration}轮校验**\n"
                f"- 总步骤: {total_steps}, 通过: {passed_count}, "
                f"警告: {warning_count}, 错误: {error_count}\n"
                f"- 状态: {status_line}\n",
            )

        # 3b. 如果无错误，提前退出
        if not final_errors and not design_errors:
            logger.info(f"[merge] 第{iteration}轮校验通过，退出循环")
            if on_reasoning_delta:
                await on_reasoning_delta("merge", "校验全部通过，合并完成。\n")
            break

        if not final_errors and design_errors:
            logger.warning(
                f"[merge] 几何校验通过，但有 {len(design_errors)} 个设计约束错误"
            )
            if on_reasoning_delta:
                await on_reasoning_delta(
                    "merge",
                    "几何关系已通过，但以下设计硬约束未满足，阻止产物下发：\n- "
                    + "\n- ".join(design_errors)
                    + "\n",
                )
            break

        # 3c. 如果是最后一轮，不再修复
        if iteration == MAX_MERGE_ITERATIONS:
            logger.warning(
                f"[merge] 已达最大迭代次数 ({MAX_MERGE_ITERATIONS})，"
                f"仍有 {error_count} 个错误"
            )
            if on_reasoning_delta:
                await on_reasoning_delta(
                    "merge",
                    f"已达最大迭代次数 ({MAX_MERGE_ITERATIONS})，"
                    f"仍有 {error_count} 个错误未修复，交给最终校验节点处理。\n",
                )
            break

        # 3d. 尝试使用 fix_* 工具修复
        if on_reasoning_delta:
            await on_reasoning_delta(
                "merge", f"检测到 {error_count} 个错误，尝试自动修复...\n"
            )

        fix_results = _apply_fixes(merged_blueprint, final_errors)

        if not fix_results:
            logger.warning("[merge] 当前错误没有确定性修复工具，停止无效循环")
            if on_reasoning_delta:
                await on_reasoning_delta(
                    "merge", "当前错误没有确定性修复工具，交给最终校验与回调处理。\n"
                )
            break

        if not any(ok for _, ok in fix_results):
            logger.warning("[merge] 确定性修复未改变蓝图，停止无效循环")
            if on_reasoning_delta:
                await on_reasoning_delta(
                    "merge", "自动修复未能安全消除错误，交给最终校验与回调处理。\n"
                )
            break

        if on_reasoning_delta:
            fix_names = [name for name, ok in fix_results if ok]
            fail_names = [name for name, ok in fix_results if not ok]
            parts = []
            if fix_names:
                parts.append(f"已修复: {', '.join(fix_names)}")
            if fail_names:
                parts.append(f"未能修复: {', '.join(fail_names)}")
            msg = "；".join(parts) if parts else "无可用修复工具"
            await on_reasoning_delta("merge", f"{msg}\n进入下一轮校验...\n")

    # ── 4. 最终统计 ──
    total_ms = int((_time.time() - t0) * 1000)
    elements = merged_blueprint.get("geometry", {}).get("elements", [])
    components = merged_blueprint.get("geometry", {}).get("components", [])

    merge_diag["total_ms"] = total_ms
    merge_diag["element_count"] = len(elements)
    merge_diag["component_count"] = len(components)
    merge_diag["final_errors"] = len(final_errors) + len(design_errors)
    # final_validate 紧接在 merge 之后，蓝图未发生变化时可安全复用这一轮结果；
    # 用蓝图指纹显式判断，避免依赖“final_errors==0”这种隐式条件。
    merge_diag["blueprint_fingerprint"] = blueprint_fingerprint(merged_blueprint)
    merge_diag["validation_results"] = [
        {
            "step": result.step,
            "name": result.name,
            "output": result.output,
            "has_error": result.has_error,
            "has_warning": result.has_warning,
        }
        for result in pipeline_results
    ]

    logger.info(
        f"[merge] 合并完成: {len(elements)} elements, {len(components)} components, "
        f"{len(merge_diag['iterations'])}轮, {total_ms}ms"
    )

    return {
        "merged_blueprint": merged_blueprint,
        "merge_diag": merge_diag,
        "design_brief": design_brief,
    }


def _validate_design_brief_constraints(
    blueprint: dict,
    design_brief: dict | None,
) -> list[str]:
    """验证骨架设计清单中的数量与立面开口硬约束。"""
    if not isinstance(design_brief, dict):
        return []

    geometry = blueprint.get("geometry", {})
    entities = [
        *geometry.get("elements", []),
        *geometry.get("components", []),
    ]
    counts: dict[str, int] = {}
    for entity in entities:
        entity_type = entity.get("type")
        if entity_type:
            counts[entity_type] = counts.get(entity_type, 0) + 1
    # 凸窗会占用并替换一个普通窗槽位，因此也满足立面窗数量要求。
    counts["window"] = counts.get("window", 0) + counts.get("bay_window", 0)

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
            stairs = [item for item in entities if item.get("type") == "stair"]
            wall_levels = {
                round(min(float(item["from"][1]), float(item["to"][1])), 2)
                for item in walls
                if _finite_vec3(item.get("from")) and _finite_vec3(item.get("to"))
            }
            floor_levels = {
                round(float(item["from"][1]), 2)
                for item in floors
                if _finite_vec3(item.get("from"))
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
            if not stairs:
                errors.append(f"建筑方案要求 {modeled_floors} 层，但没有 stair 构件")

    for component_type, limits in design_brief.get("component_quota", {}).items():
        if not isinstance(limits, dict):
            continue
        actual = counts.get(component_type, 0)
        # balcony 自带 U 形栏杆，可满足 railing 的最低需求；但它已有独立的
        # balcony 配额，不能再占用独立 railing 的数量上限。
        minimum_actual = (
            actual + counts.get("balcony", 0)
            if component_type == "railing"
            else actual
        )
        minimum = limits.get("min")
        maximum = limits.get("max")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and minimum_actual < minimum:
            errors.append(
                f"{component_type} 数量 {minimum_actual} 少于设计下限 {minimum}"
            )
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and actual > maximum:
            errors.append(
                f"{component_type} 数量 {actual} 超过设计上限 {maximum}"
            )

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

    return errors


def _deduplicate_balcony_representations(blueprint: dict) -> dict:
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
        if _finite_vec3(point)
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
        footprint = _balcony_footprint(component, walls.get(component.get("parentWall")), building_center)
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
        if not element_id or not _finite_vec3(floor_from) or not _finite_vec3(floor_to):
            continue
        floor_bounds = (
            min(floor_from[0], floor_to[0]), max(floor_from[0], floor_to[0]),
            min(floor_from[2], floor_to[2]), max(floor_from[2], floor_to[2]),
        )
        floor_y = (floor_from[1] + floor_to[1]) / 2
        if any(
            abs(floor_y - footprint["top_y"]) <= 0.05
            and _footprint_iou(floor_bounds, footprint["bounds"]) >= 0.75
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


def _balcony_footprint(
    component: dict,
    wall: dict | None,
    building_center: tuple[float, float],
) -> dict | None:
    if not isinstance(wall, dict):
        return None
    wall_from = wall.get("from")
    wall_to = wall.get("to")
    component_from = component.get("from")
    if not _finite_vec3(wall_from) or not _finite_vec3(wall_to) or not _finite_vec3(component_from):
        return None
    width = component.get("width")
    depth = component.get("depth")
    if not _positive_number(width) or not _positive_number(depth):
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


def _remove_ground_level_railings(blueprint: dict) -> dict:
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
            and _finite_vec3(floor_from)
            and _finite_vec3(floor_to)
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


def _footprint_iou(first: tuple, second: tuple) -> float:
    ix = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    iz = max(0.0, min(first[3], second[3]) - max(first[2], second[2]))
    intersection = ix * iz
    first_area = max(0.0, first[1] - first[0]) * max(0.0, first[3] - first[2])
    second_area = max(0.0, second[1] - second[0]) * max(0.0, second[3] - second[2])
    union = first_area + second_area - intersection
    return intersection / union if union > 1e-9 else 0.0


def _finite_vec3(value: object) -> bool:
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


def _positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value > 0
    )


def _enforce_component_quota(
    components: list[dict],
    quota: dict,
    fplan: dict,
    logger,
) -> tuple[list[dict], int]:
    """根据 design_brief.component_quota 剔除超额组件
    
    策略：按墙面优先级保留。主立面(max_openings多的)优先保留，侧墙/背面多余额外剔除。
    返回 (filtered_components, pruned_count)
    """
    import json as _json
    
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


def _apply_fixes(blueprint: dict, errors: list) -> list[tuple[str, bool]]:
    """根据校验错误，调用对应的 fix_* 工具修复

    Args:
        blueprint: 待修复的 Blueprint（原地修改）
        errors: _final_errors 返回的错误列表

    Returns:
        [(fix_name, success), ...] 列表
    """
    from app.services.agent_service import _run_tool
    from app.tools import spatial_tools

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
