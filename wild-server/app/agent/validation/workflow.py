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
    step_result_to_dict,
)
from app.agent.validation.component_trace import get_all_entity_ids, trace_errors_to_components
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
    from app.services.agent_service import _final_errors
    
    try:
        t0 = _time.time()
        merge_diag = dict(state.get("merge_diag") or {})
        from app.agent.validation.candidate import evaluate_candidate
        evaluation = evaluate_candidate(
            merged_blueprint, design_document=state.get("design_document"),
            design_brief=state.get("design_brief"), source="final_validate",
        )
        current_fingerprint = evaluation["snapshot"]["blueprint_fingerprint"]
        pipeline_results = evaluation["results"]
        design_errors = evaluation["snapshot"]["design_errors"]
        fulfillment = evaluation["fulfillment"]
        cache_reused = False
        merge_diag["approved_design_changes"] = evaluation["approved_design_changes"]
        merge_diag["design_fulfillment"] = fulfillment

        from app.agent.vision.evaluation import proxy_evaluate
        merge_diag["visual_review"] = {
            "blueprint_fingerprint": current_fingerprint,
            "proxy": proxy_evaluate(merged_blueprint, state.get("design_document")),
            "complete": False,
            "blockedBy": ["render", "human_review"],
            "entrypoint": "python -m app.agent.vision.workflow",
        }

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
            design_hash=evaluation["snapshot"]["design_hash"],
            design_revision=evaluation["snapshot"]["design_revision"],
            design_brief_fingerprint=evaluation["snapshot"]["design_brief_fingerprint"],
            status=status,
            results=serialized_results,
            design_errors=design_errors,
            issues=validation_issues,
            fulfillment=fulfillment,
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
            "design_fulfillment": fulfillment,
            "merge_diag": merge_diag,
            "failed_components": failed_components,
            "passed_component_ids": passed_component_ids,
            "status": status,
            "error": error_summary,
            "final_blueprint": merged_blueprint,  # 通过校验后的最终结果
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 3),
            "repair_audit": ({"accepted": False, "stop_reason": "design_revision_required",
                              "reason": "批准设计本身存在编译阻断，请修订并重新审核"}
                             if evaluation["approved_design_errors"] else state.get("repair_audit")),
        }
    
    except Exception as e:
        logger.error(f"[validate_node] 校验失败: {e}")
        return {
            "error": f"校验流水线执行失败: {str(e)}",
            "status": "failed",
        }


