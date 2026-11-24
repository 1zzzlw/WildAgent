"""为生成请求起草并解析设计图纸。"""

from __future__ import annotations

import time as _time

from app.agent.workflows.design.drafting import draft_design
from app.agent.state import GenerationState
from app.agent.prompts import build_architecture_plan_prompt
from app.agent.runtime import get_reasoning_callback
from app.agent.workflows.design.react import build_design_request


async def architecture_planner(state: GenerationState) -> dict:
    """建筑和独立物件共用的图纸起草入口。"""
    from app.domain.design.resolver import architecture_plan_from_document
    from app.infrastructure.llm.errors import model_failure_result

    started = _time.time()
    object_scene = state.get("intent_target_kind") == "object"
    profile_id = "object" if object_scene else state["intent_profile"]

    # 获取粒度，默认是 minimal
    detail_level = state.get("detail_level", "minimal")

    callback = get_reasoning_callback()
    if callback:
        label = "独立物件图纸" if object_scene else "建筑图纸"
        await callback("architecture:progress", f"正在设计{label}与构件标记……\n")

    prompt = build_architecture_plan_prompt(
        profile_id,
        detail_level=detail_level,
        style_preference=state.get("style_preference"),
        object_scene=object_scene,
    )
    accounting = {"model_calls": 0}
    knowledge_trace = []

    try:
        document, resolved, diag = await draft_design(
            state=state,
            base_prompt=prompt,
            profile_id=profile_id,
            object_scene=object_scene,
            thinking_mode=state.get("thinking_mode") is True,
            on_reasoning_delta=callback,
            request_draft=build_design_request(accounting, knowledge_trace, callback),
            call_accounting=accounting,
        )
    except Exception as exc:
        return {
            **model_failure_result(exc),
            "architecture_diag": {
                "model_calls": accounting["model_calls"],
                "knowledge_trace": knowledge_trace,
                "last_issue": str(exc),
                "total_ms": int((_time.time() - started) * 1000),
                "settled": False,
            },
        }
    diag.update(
        knowledge_trace=knowledge_trace,
        rag_chars=sum(entry.get("chars", 0) for entry in knowledge_trace),
        detail_level=detail_level,
        total_ms=int((_time.time() - started) * 1000),
        profile=profile_id,
    )
    if document is None:
        return {
            "status": "failed",
            "error": "设计图纸未通过检查：" + diag["last_issue"],
            "architecture_diag": diag,
        }
    return {
        "detail_level": detail_level,
        "architecture_plan": architecture_plan_from_document(document),
        "design_document": document.model_dump(mode="json"),
        "resolved_design": resolved.model_dump(mode="json"),
        "architecture_diag": diag,
        "component_fragments": {
            k: [] for k in (state.get("component_fragments") or {})
        },
        "component_diagnostics": {
            k: {} for k in (state.get("component_diagnostics") or {})
        },
        "merged_blueprint": {},
        "final_blueprint": {},
        "validation_snapshot": {},
        "repair_audit": {},
        "compile_report": {},
        "error": None,
    }
