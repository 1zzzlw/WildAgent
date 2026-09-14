"""
Layer 2: 校验节点

复用 agent_service.py 的 run_validation_pipeline
"""
import time as _time
from dataclasses import asdict

from loguru import logger

from app.agent.validation.diagnostics import (
    VALIDATOR_VERSION,
    ValidationSnapshot,
    blueprint_fingerprint,
    step_result_to_dict,
)
from app.agent.validation.component_trace import get_all_entity_ids, trace_errors_to_components
from app.agent.validation.design_constraints import validate_design_brief_constraints
from app.agent.state import GenerationState
from app.agent.validation.issues import validation_issues_from_results


async def validate_node(state: GenerationState) -> dict:
    """对合并后的 Blueprint 执行完整校验流水线"""

    terminal_model_error = state.get("terminal_model_error")
    if terminal_model_error:
        error_message = terminal_model_error.get(
            "user_message",
            "模型服务调用失败，本次生成已停止。",
        )
        logger.error(f"[validate_node] 模型服务故障，跳过建筑校验: {error_message}")
        return {
            "terminal_model_error": terminal_model_error,
            "error": error_message,
            "status": "failed",
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 3),
            "component_retry_counts": state.get("component_retry_counts", {}),
        }
    
    merged_blueprint = state.get("merged_blueprint")
    if not merged_blueprint:
        logger.error("[validate_node] merged_blueprint 缺失")
        return {
            "error": "merged_blueprint 缺失，无法校验",
            "status": "failed",
        }
    
    logger.info("[validate_node] 开始校验 Blueprint")
    
    # 导入并执行校验流水线
    from app.services.agent_delivery import final_validation_results
    from app.services.agent_service import PipelineStepResult, run_validation_pipeline, _final_errors
    
    try:
        t0 = _time.time()
        merge_diag = state.get("merge_diag", {})
        current_fingerprint = blueprint_fingerprint(merged_blueprint)

        # 1. 优先复用 callback 携带的、指纹一致的校验快照（callback 已做过全量复检）。
        prior_snapshot = state.get("validation_snapshot") or {}
        snapshot_reusable = (
            prior_snapshot.get("blueprint_fingerprint") == current_fingerprint
            and prior_snapshot.get("validator_version") == VALIDATOR_VERSION
            and bool(prior_snapshot.get("results"))
        )
        if snapshot_reusable:
            pipeline_results = [
                PipelineStepResult(**result) for result in prior_snapshot.get("results", [])
            ]
            design_errors = list(prior_snapshot.get("design_errors", []))
            cache_reused = True
            logger.info("[validate_node] 复用 callback 校验快照（指纹一致）")
        else:
            cached_results = merge_diag.get("validation_results", [])
            cache_reused = (
                bool(cached_results)
                and merge_diag.get("blueprint_fingerprint") == current_fingerprint
            )
            if cache_reused:
                pipeline_results = [PipelineStepResult(**result) for result in cached_results]
                logger.info("[validate_node] 复用 merge 节点最后一轮校验结果")
            else:
                pipeline_results = run_validation_pipeline(merged_blueprint)

            # merge_diag 记录的是合并当时的快照；设计配额必须对当前 Blueprint 重算。
            design_errors = validate_design_brief_constraints(
                merged_blueprint,
                state.get("design_brief"),
            )
            if design_errors:
                pipeline_results.append(PipelineStepResult(
                    step="design",
                    name="validate_design_brief",
                    output="\n".join(f"❌ [design] {message}" for message in design_errors),
                    has_error=True,
                    has_warning=False,
                ))

        # 提取最终错误（修复后的 recheck 覆盖初检错误）
        final_errors = _final_errors(pipeline_results)
        
        # 统计
        final_results = final_validation_results(pipeline_results)
        total_steps = len(final_results)
        error_steps = len(final_errors)
        warning_steps = sum(
            1 for result in final_results if result.has_warning and not result.has_error
        )
        passed_steps = total_steps - error_steps - warning_steps
        
        logger.info(
            f"[validate_node] 校验完成: "
            f"{total_steps} 步，{passed_steps} 通过，{warning_steps} 警告，{error_steps} 错误"
        )
        
        # 将自然语言错误拆成逐实体、逐问题的稳定协议，供回调节点选择修复工具。
        validation_issues = validation_issues_from_results(final_errors, merged_blueprint)

        # 如果有错误，追溯到具体组件
        failed_components = []
        if final_errors:
            failed_components = trace_errors_to_components(
                final_errors,
                merged_blueprint,
                validation_issues=validation_issues,
            )
        
        # 计算通过的组件 ID
        all_component_ids = get_all_entity_ids(merged_blueprint)
        failed_component_ids = {fc["component_id"] for fc in failed_components}
        failed_component_ids.update(
            related_id
            for failed in failed_components
            for related_id in failed.get("related_entity_ids", [])
        )
        passed_component_ids = [cid for cid in all_component_ids if cid not in failed_component_ids]
        
        # 决定状态
        if final_errors:
            status = "partial"  # 部分通过
            error_summary = f"校验发现 {len(final_errors)} 个错误: " + "; ".join(
                f"{r.name}" for r in final_errors
            )
        else:
            status = "complete"
            error_summary = None
        
        serialized_results = [step_result_to_dict(r) for r in pipeline_results]
        snapshot = ValidationSnapshot(
            blueprint_fingerprint=current_fingerprint,
            validator_version=VALIDATOR_VERSION,
            status=status,
            results=serialized_results,
            design_errors=design_errors,
            issues=validation_issues,
            error_count=error_steps,
            warning_count=warning_steps,
            elapsed_ms=int((_time.time() - t0) * 1000),
            source="final_validate",
        )
        return {
            "validation_results": serialized_results,
            "validation_error_count": error_steps,
            "validation_warning_count": warning_steps,
            "validation_cache_reused": cache_reused,
            "validation_issues": validation_issues,
            "validation_snapshot": asdict(snapshot),
            "failed_components": failed_components,
            "passed_component_ids": passed_component_ids,
            "status": status,
            "error": error_summary,
            "final_blueprint": merged_blueprint,  # 通过校验后的最终结果
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 3),
        }
    
    except Exception as e:
        logger.error(f"[validate_node] 校验失败: {e}")
        return {
            "error": f"校验流水线执行失败: {str(e)}",
            "status": "failed",
        }


