"""LangGraph 增量修改节点。

复用当前已经过 Blueprint 预检和完整校验流水线验证的统一 Agent 入口，
但只接受 ScenePatch 结果。这样精密模式和快速模式拥有一致的编辑语义，
同时保持 Patch 必须由前端确认后才能应用。
"""

import time as _time

from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.runtime_context import get_reasoning_callback


async def patch_node(state: GenerationState) -> dict:
    """根据当前 Blueprint 生成通过验证的 ScenePatch。"""
    current_blueprint = state.get("current_blueprint")
    if not current_blueprint:
        return {
            "error": "当前场景为空，无法执行增量修改",
            "status": "failed",
            "patch_diag": {"error": "current_blueprint missing"},
        }

    from app.services.agent_service import agent_service

    started_at = _time.time()
    on_reasoning_delta = get_reasoning_callback()

    async def emit_reasoning(delta: str) -> None:
        if on_reasoning_delta is not None:
            await on_reasoning_delta("patch", delta)

    try:
        result = await agent_service.query_structured(
            state.get("user_message", ""),
            current_blueprint,
            selection=state.get("selection", []),
            thinking_mode=state.get("thinking_mode", False),
            on_reasoning_delta=emit_reasoning if on_reasoning_delta else None,
            expected_output="patch",
            resolved_intent="edit",
        )
    except Exception as exc:
        logger.exception(f"[patch] 增量修改失败: {exc}")
        return {
            "error": f"增量修改失败: {exc}",
            "status": "failed",
            "patch_diag": {"error": str(exc)},
        }

    elapsed_ms = int((_time.time() - started_at) * 1000)
    if result.error:
        return {
            "error": result.error,
            "status": "failed",
            "patch_reply": result.text,
            "patch_diag": {
                "error": result.error,
                "validation_steps": len(result.pipeline_results),
                "structured_source": result.structured_source,
                "structured_recovery_used": result.structured_recovery_used,
                "total_ms": elapsed_ms,
            },
        }

    if result.patch is None:
        return {
            "error": "模型未返回 ScenePatch，未对当前场景执行任何修改",
            "status": "failed",
            "patch_reply": result.text,
            "patch_diag": {
                "error": "scene_patch missing",
                "structured_source": result.structured_source,
                "structured_recovery_used": result.structured_recovery_used,
                "total_ms": elapsed_ms,
            },
        }

    operations = result.patch.get("operations", [])
    return {
        "scene_patch": result.patch,
        "patch_reply": result.text,
        "status": "complete",
        "error": None,
        "patch_diag": {
            "operation_count": len(operations),
            "validation_steps": len(result.pipeline_results),
            "structured_source": result.structured_source,
            "structured_recovery_used": result.structured_recovery_used,
            "total_ms": elapsed_ms,
        },
    }
