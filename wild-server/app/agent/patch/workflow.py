"""Blueprint 增量修改："patch" 节点实现。

直接调用模型生成 ScenePatch，并执行操作预检和完整校验。
Patch 必须由前端确认后才能应用。

 与 ``repair/`` 的分工（两者不共用通道）：
- **本模块** = 用户要的修改：编辑意图 → ScenePatch，落库前等前端确认。
- ``repair/`` = 校验失败的定向修复：结构化错误 → 白名单修复动作 → 复检。

节点入口见 ``nodes/patch_node.py``（薄壳），路由见 ``agent.graph``。
"""

import time as _time

from loguru import logger

from app.agent.state import GenerationState
from app.agent.runtime import get_reasoning_callback


async def patch_node(state: GenerationState) -> dict:
    """生成可应用的 ScenePatch；草稿校验问题随提案展示，不阻止继续编辑。"""
    current_blueprint = state.get("current_blueprint")
    if not current_blueprint:
        return {
            "error": "当前场景为空，无法执行增量修改",
            "status": "failed",
            "patch_diag": {"error": "current_blueprint missing"},
        }

    from app.services.agent_service import agent_service, _final_errors

    started_at = _time.time()
    on_reasoning_delta = get_reasoning_callback()

    async def emit_reasoning(delta: str) -> None:
        if on_reasoning_delta is not None:
            await on_reasoning_delta("patch", delta)

    try:
        result = await agent_service.query_patch(
            state.get("user_message", ""),
            current_blueprint,
            selection=state.get("selection", []),
            thinking_mode=state.get("thinking_mode", False),
            on_reasoning_delta=emit_reasoning if on_reasoning_delta else None,
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

    validation_errors = _final_errors(result.pipeline_results)
    scene_patch = dict(result.patch)
    if validation_errors:
        scene_patch["summary"] = (str(scene_patch.get("summary") or "修改场景")
            + "\n\n修改后草稿仍有校验错误，可确认后继续编辑：\n"
            + "\n".join(f"{error.name}: {error.output}" for error in validation_errors))
    operations = scene_patch.get("operations", [])
    return {
        "scene_patch": scene_patch,
        "patch_reply": result.text,
        "status": "complete",
        "error": None,
        "patch_diag": {
            "operation_count": len(operations),
            "validation_steps": len(result.pipeline_results),
            "validation_passed": not validation_errors,
            "structured_source": result.structured_source,
            "structured_recovery_used": result.structured_recovery_used,
            "total_ms": elapsed_ms,
        },
    }


__all__ = ["patch_node"]
