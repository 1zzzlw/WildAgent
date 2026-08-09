"""
Layer 2: 校验节点

复用 agent_service.py 的 run_validation_pipeline
"""
from loguru import logger

from app.agent.graph_state import GenerationState


async def validate_node(state: GenerationState) -> dict:
    """对合并后的 Blueprint 执行完整校验流水线"""
    
    merged_blueprint = state.get("merged_blueprint")
    if not merged_blueprint:
        logger.error(f"[validate_node] merged_blueprint 缺失")
        return {
            "error": "merged_blueprint 缺失，无法校验",
            "status": "failed",
        }
    
    logger.info(f"[validate_node] 开始校验 Blueprint")
    
    # 导入并执行校验流水线
    from app.services.agent_service import run_validation_pipeline, _final_errors
    
    try:
        # 执行完整的 15 步校验流水线
        pipeline_results = run_validation_pipeline(merged_blueprint)
        
        # 提取最终错误（修复后的 recheck 覆盖初检错误）
        final_errors = _final_errors(pipeline_results)
        
        # 统计
        total_steps = len(pipeline_results)
        error_steps = len(final_errors)
        warning_steps = sum(1 for r in pipeline_results if r.has_warning and not r.has_error)
        passed_steps = total_steps - error_steps - warning_steps
        
        logger.info(
            f"[validate_node] 校验完成: "
            f"{total_steps} 步，{passed_steps} 通过，{warning_steps} 警告，{error_steps} 错误"
        )
        
        # 如果有错误，追溯到具体组件
        failed_components = []
        if final_errors:
            failed_components = _trace_errors_to_components(final_errors, merged_blueprint)
        
        # 计算通过的组件 ID
        all_component_ids = _get_all_component_ids(merged_blueprint)
        failed_component_ids = {fc["component_id"] for fc in failed_components}
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
        
        return {
            "validation_results": [_step_to_dict(r) for r in pipeline_results],
            "failed_components": failed_components,
            "passed_component_ids": passed_component_ids,
            "status": status,
            "error": error_summary,
            "final_blueprint": merged_blueprint,  # 通过校验后的最终结果
        }
    
    except Exception as e:
        logger.error(f"[validate_node] 校验失败: {e}")
        return {
            "error": f"校验流水线执行失败: {str(e)}",
            "status": "failed",
        }


def _step_to_dict(step_result) -> dict:
    """将 PipelineStepResult 转为 dict"""
    return {
        "step": step_result.step,
        "name": step_result.name,
        "output": step_result.output,
        "has_error": step_result.has_error,
        "has_warning": step_result.has_warning,
    }


def _trace_errors_to_components(errors, blueprint: dict) -> list[dict]:
    """从校验错误信息中追溯到具体组件，提取结构化失败信息

    策略：
    1. 优先用正则匹配 ❌/⚠️ [component_id] 格式（精确）
    2. Fallback：词边界包含匹配（加边界检查避免 "door" 误匹配 "door_frame"）
    3. 附带组件的完整 current_params，供回调节点使用
    """
    import re

    components = blueprint.get("geometry", {}).get("components", [])
    elements = blueprint.get("geometry", {}).get("elements", [])
    all_entities: dict[str, dict] = {}
    for e in elements + components:
        eid = e.get("id")
        if eid:
            all_entities[eid] = e

    # ── 模式1：精确匹配结构化标记 ❌ [id] 或 ⚠️ [id] ──
    marker_pattern = re.compile(r'[❌⚠️]\s*\[(\w+)\]')

    failed: list[dict] = []
    seen_ids: set[str] = set()

    for error_result in errors:
        output = error_result.output

        for match in marker_pattern.finditer(output):
            comp_id = match.group(1)
            if comp_id in seen_ids:
                continue
            seen_ids.add(comp_id)

            entity = all_entities.get(comp_id)
            if entity is None:
                continue

            failed.append({
                "component_id": comp_id,
                "component_type": entity.get("type", "?"),
                "current_params": entity,
                "error_step": error_result.name,
                "error_message": _extract_error_context(output, comp_id),
            })

    # ── 模式2（fallback）：词边界包含匹配 ──
    if not failed:
        for error_result in errors:
            output = error_result.output
            for comp_id, entity in all_entities.items():
                if comp_id in seen_ids:
                    continue
                if re.search(r'\b' + re.escape(comp_id) + r'\b', output):
                    seen_ids.add(comp_id)
                    failed.append({
                        "component_id": comp_id,
                        "component_type": entity.get("type", "?"),
                        "current_params": entity,
                        "error_step": error_result.name,
                        "error_message": _extract_error_context(output, comp_id),
                    })

    return failed


def _extract_error_context(output: str, comp_id: str) -> str:
    """从校验输出中提取与指定组件 ID 相关的错误行（最多300字符）"""
    lines = output.split("\n")
    relevant = [line.strip() for line in lines if comp_id in line]
    if not relevant:
        return output[:300]
    return "\n".join(relevant)[:300]


def _get_all_component_ids(blueprint: dict) -> list[str]:
    """获取所有组件和元素的 ID"""
    ids = []
    
    components = blueprint.get("geometry", {}).get("components", [])
    for comp in components:
        comp_id = comp.get("id")
        if comp_id:
            ids.append(comp_id)
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    for el in elements:
        el_id = el.get("id")
        if el_id:
            ids.append(el_id)
    
    return ids
