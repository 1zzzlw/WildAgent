"""展示同一图纸并等待审核；建筑批准后展开标记任务，物件进入骨架链。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.agent.state import GenerationState
from app.design.contracts import DesignDocument
from app.design.repository import design_repository
from app.design.resolver import resolve_design, _stable_hash
from app.design.review_outcome import (
    approved_design_fields,
    build_design_review_interrupt,
    revision_design_fields,
)


def design_review(state: GenerationState) -> dict:
    """在任何骨架或组件生成前暂停，等待用户批准具体建筑方案。"""

    document = DesignDocument.model_validate(state.get("design_document"))
    # material_plan saved an earlier draft. Persist completion before exposing approval;
    # on interrupt replay preserve any newer user Patch instead of overwriting it.
    stored = design_repository.get(document.session_id)
    if stored is not None and stored.revision > document.revision:
        document = stored
    elif stored is None or _stable_hash(stored) != _stable_hash(document):
        document, _ = design_repository.save(document)
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
        reviewed = state.get("resolved_design") or {}
        if (reviewed.get("design_hash") != approved_resolved.get("design_hash")
                or reviewed.get("resolver_version") != approved_resolved.get("resolver_version")):
            design_fields.update(
                component_fragments={k: [] for k in (state.get("component_fragments") or {})},
                component_diagnostics={k: {} for k in (state.get("component_diagnostics") or {})},
            )

    else:
        if not feedback:
            feedback = "请根据用户意见调整体量、立面、屋顶或构件选择，并生成新版建筑方案。"
        design_fields = revision_design_fields(
            review_source,
            feedback,
            material_fallback=material_fallback,
        )
    return dict(design_fields)


def _revision_node(state: GenerationState) -> str:
    """用户要求修改时回到哪条方案链。

    判定只看文档的判别字段，不看当前节点名：物件文档必须回物件链，
    否则"把这张桌子改宽一点"会被当成建筑修订，重新产出一栋房子。
    """

    document = state.get("design_document")
    if isinstance(document, dict):
        decisions = document.get("decisions")
        if isinstance(decisions, dict) and str(decisions.get("kind") or "") == "object":
            return "object_design"
    return "architecture"


def route_design_review(state: GenerationState) -> str:
    if state.get("design_review_status") == "approved":
        return "plan" if _is_architecture(state) else "skeleton"
    if state.get("status") == "failed":
        return "__end__"
    return _revision_node(state)


def _is_architecture(state: GenerationState) -> bool:
    """建筑展开图纸任务；物件先准备空骨架。"""

    from app.design.resolver import is_object_plan

    document = state.get("design_document") or {}
    kind = document.get("decisions", {}).get("kind")
    if kind:
        return kind == "architecture"
    plan = state.get("architecture_plan")
    return not is_object_plan(plan if isinstance(plan, dict) else None)


__all__ = ["design_review", "route_design_review"]
