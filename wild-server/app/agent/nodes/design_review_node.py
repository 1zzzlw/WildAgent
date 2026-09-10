"""建筑设计文档人工审核节点。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.agent.graph_state import GenerationState
from app.design.contracts import DesignDocument
from app.design.repository import design_repository
from app.design.resolver import architecture_plan_from_document, resolve_design


def design_review(state: GenerationState) -> dict:
    """在任何骨架或组件生成前暂停，等待用户批准具体建筑方案。"""

    document = DesignDocument.model_validate(state.get("design_document"))
    resolved = resolve_design(document)
    decision = interrupt({
        "type": "design_review",
        "document": document.model_dump(mode="json"),
        "resolved": resolved.model_dump(mode="json"),
        "preview_url": f"/api/designs/{document.session_id}/preview.svg?revision={document.revision}",
    })
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
    if action == "confirm":
        approved, approved_resolved = design_repository.approve(
            document.session_id,
            review_source.revision,
        )
        approved_materials = approved.decisions.materials.resolved_plan
        return {
            "design_document": approved.model_dump(mode="json"),
            "resolved_design": approved_resolved,
            "architecture_plan": architecture_plan_from_document(approved),
            "material_plan": (
                approved_materials.model_dump(mode="json")
                if approved_materials is not None
                else state.get("material_plan")
            ),
            "design_review_status": "approved",
            "design_feedback": "",
        }
    if not feedback:
        feedback = "请根据用户意见调整体量、立面、屋顶或构件选择，并生成新版建筑方案。"
    revision_materials = review_source.decisions.materials.resolved_plan
    return {
        "design_document": review_source.model_dump(mode="json"),
        "resolved_design": resolve_design(review_source).model_dump(mode="json"),
        "architecture_plan": architecture_plan_from_document(review_source),
        "material_plan": (
            revision_materials.model_dump(mode="json")
            if revision_materials is not None
            else state.get("material_plan")
        ),
        "design_review_status": "revise",
        "design_feedback": feedback,
    }


def route_design_review(state: GenerationState) -> str:
    if state.get("design_review_status") == "approved":
        return "plan_executor" if state.get("plan_mode") else "skeleton"
    if state.get("status") == "failed":
        return "__end__"
    return "architecture"
