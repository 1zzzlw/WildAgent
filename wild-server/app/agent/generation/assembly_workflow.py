"""
Layer 2: 分片合并节点（含校验 + 修复 + 循环）

合并所有 Layer 1 产出的组件分片为完整 Blueprint，
然后执行校验流水线，对检测到的问题使用 fix_* 工具自动修复，
循环直到全部通过或达到最大迭代次数。

每次迭代通过 on_reasoning_delta 发射思考内容，让前端能看到合并推理过程。
"""
import time as _time
from loguru import logger

from app.agent.state import GenerationState
from app.agent.generation.assembly import (
    apply_fixes,
    collect_json_parse_failures,
    deduplicate_balcony_representations,
    enforce_component_quota,
    remove_ground_level_railings,
)
from app.agent.generation.components import COMPONENT_REGISTRY
from app.agent.validation.diagnostics import blueprint_fingerprint
from app.agent.validation.design_constraints import validate_design_brief_constraints
from app.llm.errors import collect_component_model_errors
from app.agent.runtime import get_reasoning_callback
from app.utils.fragment_merger import merge_fragments

MAX_MERGE_ITERATIONS = 3


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

    # 模型服务故障不是几何问题。只要任一并行组件节点调用模型失败，
    # 就停止本次生成，避免用空分片合并后再误入 callback 修复循环。
    model_failures = collect_component_model_errors(
        state.get("component_diagnostics", {})
    )
    if model_failures:
        labels = list(dict.fromkeys(item["label"] for item in model_failures))
        primary = model_failures[0]
        error_message = primary["user_message"]
        logger.error(
            f"[merge] 检测到 {len(model_failures)} 个组件模型故障，停止当前生成: "
            f"{', '.join(labels)}"
        )
        if on_reasoning_delta:
            await on_reasoning_delta(
                "merge",
                f"检测到模型服务故障，已停止合并和自动修复。受影响组件：{', '.join(labels)}。\n",
            )
        terminal_error = {
            **primary,
            "affected_count": len(model_failures),
            "affected_components": [item["component_type"] for item in model_failures],
        }
        return {
            "terminal_model_error": terminal_error,
            "error": error_message,
            "status": "failed",
            "merge_diag": {
                "label": "合并",
                "model_failures": model_failures,
                "final_errors": len(model_failures),
                "iterations": [],
            },
        }

    # JSON 提取失败不是服务故障（不设 terminal），但也不应静默消失：组件配额
    # min>0 时生成设计配额级错误交给回调 add_entity，否则记诊断告警。格式故障
    # 与几何问题区分开，避免误判修复对象。
    json_parse_failures = collect_json_parse_failures(
        state.get("component_diagnostics", {})
    )
    json_parse_quota_errors: list[str] = []
    json_parse_dropped: list[str] = []
    if json_parse_failures:
        quota = design_brief.get("component_quota", {}) if design_brief else {}
        for component_type, label in json_parse_failures:
            minimum = 0
            if isinstance(quota.get(component_type), dict):
                raw_min = quota[component_type].get("min", 0)
                minimum = int(raw_min) if isinstance(raw_min, (int, float)) and not isinstance(raw_min, bool) else 0
            if minimum > 0:
                json_parse_quota_errors.append(
                    f"{label}({component_type}) 结构化输出解析失败，且设计配额下限为 {minimum}"
                )
            else:
                json_parse_dropped.append(f"{label}({component_type})")
        if json_parse_quota_errors:
            logger.warning(f"[merge] JSON 解析失败但配额要求存在: {json_parse_quota_errors}")
        if json_parse_dropped:
            logger.warning(f"[merge] JSON 解析失败且无配额下限，组件被丢弃: {json_parse_dropped}")

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
    balcony_cleanup = deduplicate_balcony_representations(merged_blueprint)
    if balcony_cleanup["removed_floor_ids"]:
        elements = merged_blueprint.get("geometry", {}).get("elements", [])
        components = merged_blueprint.get("geometry", {}).get("components", [])
        logger.info(f"[merge] 阳台重复表达清理: {balcony_cleanup}")

    ground_railing_cleanup = remove_ground_level_railings(merged_blueprint)
    if ground_railing_cleanup["removed_railing_ids"]:
        components = merged_blueprint.get("geometry", {}).get("components", [])
        logger.info(f"[merge] 地面平台冗余栏杆清理: {ground_railing_cleanup}")

    # ── 2.6 设计配额比对：超额组件按优先级剔除 ──
    quota_pruned = 0
    if design_brief:
        quota = design_brief.get("component_quota", {})
        fplan = design_brief.get("facade_plan", {})
        if quota and components:
            components, quota_pruned = enforce_component_quota(components, quota, fplan, logger)
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
        from app.agent.generation.architecture import (
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

    design_errors = validate_design_brief_constraints(merged_blueprint, design_brief)
    # JSON 提取失败且有配额下限的组件，视同配额缺失错误交给回调 add_entity；
    # 与几何问题区分（repair_target 为 design:<type>，走既有设计配额修复路径）。
    if json_parse_quota_errors:
        design_errors = [*json_parse_quota_errors, *design_errors]

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

        fix_results = apply_fixes(merged_blueprint, final_errors)

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
    design_document = state.get("design_document") or {}
    resolved_design = state.get("resolved_design") or {}
    if isinstance(design_document, dict):
        meta = merged_blueprint.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["designRevision"] = design_document.get("revision")
            meta["designHash"] = resolved_design.get("design_hash")
            meta["designSchemaVersion"] = design_document.get("schema_version")
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

    # ── 5. 归一化蓝图用于交付 ──
    from app.utils.blueprint_normalizer import normalize_blueprint_for_delivery
    
    merged_blueprint, norm_report = normalize_blueprint_for_delivery(merged_blueprint)
    logger.info(f"[merge] 归一化修复: {norm_report.summary()}")
    
    if on_reasoning_delta:
        if norm_report.stripped_fields or norm_report.repaired_fields or norm_report.dropped_components:
            await on_reasoning_delta(
                "merge",
                f"\n**归一化修复**\n"
                f"- {norm_report.summary()}\n"
            )

    return {
        "merged_blueprint": merged_blueprint,
        "merge_diag": merge_diag,
        "design_brief": design_brief,
    }

