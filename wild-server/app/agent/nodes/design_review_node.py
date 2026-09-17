"""建筑设计文档人工审核节点。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.agent.state import GenerationState
from app.agent.planning.requirements import update_execution_progress
from app.design.contracts import DesignDocument
from app.design.repository import design_repository
from app.design.resolver import resolve_design
from app.design.review_outcome import (
    approved_design_fields,
    build_design_review_interrupt,
    revision_design_fields,
)


def _plan_scope(state: GenerationState) -> dict:
    """设计审核不改变已批准的业务要求，计划层字段原样透传。"""

    return {
        "execution_plan": state.get("execution_plan"),
        "structured_requirements": state.get("structured_requirements") or [],
        "acceptance_results": state.get("acceptance_results") or {},
    }


def design_review(state: GenerationState) -> dict:
    """在任何骨架或组件生成前暂停，等待用户批准具体建筑方案。"""

    document = DesignDocument.model_validate(state.get("design_document"))
    decision = interrupt(build_design_review_interrupt(document, resolve_design(document)))
    action = str(decision.get("action") if isinstance(decision, dict) else "").lower()
    feedback = str(decision.get("feedback") if isinstance(decision, dict) else "").strip()
    incoming = decision.get("document") if isinstance(decision, dict) else None
    review_source = (
        DesignDocument.model_validate(incoming)
        if isinstance(incoming, dict)
        else design_repository.get(document.session_id) or document
    )
    if action not in {"confirm", "revise"}:
        raise ValueError("建筑设计审核 action 只能是 confirm 或 revise")
    if review_source.session_id != document.session_id:
        raise ValueError("审核文档与当前会话不一致")

    material_fallback = state.get("material_plan")
    if action == "confirm":
        approved, approved_resolved = design_repository.approve(
            document.session_id,
            review_source.revision,
        )
        design_fields = approved_design_fields(
            approved,
            approved_resolved,
            material_fallback=material_fallback,
        )
        progress = update_execution_progress(
            state.get("execution_progress"),
            "design_review",
            "completed",
            result_ref="design_document",
            detail="建筑设计已由用户批准",
        )
    else:
        if not feedback:
            feedback = "请根据用户意见调整体量、立面、屋顶或构件选择，并生成新版建筑方案。"
        design_fields = revision_design_fields(
            review_source,
            feedback,
            material_fallback=material_fallback,
        )
        progress = update_execution_progress(
            state.get("execution_progress"),
            "design_review",
            "pending",
            detail="用户要求修改建筑设计",
        )
    return {
        **_plan_scope(state),
        **design_fields,
        "execution_progress": progress,
    }


def route_design_review(state: GenerationState) -> str:
    if state.get("design_review_status") == "approved":
        return "skeleton"
    if state.get("status") == "failed":
        return "__end__"
    return "architecture"
