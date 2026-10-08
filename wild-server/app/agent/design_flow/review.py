"""建筑设计文档的人工审核：``interrupt`` 等批准，confirm 与 revise 两条出路。

它在骨架/组件生成前暂停，让用户看到并批准**具体**方案。三条不变量：

- **批准用的是已完成的草稿**：``material_plan`` 可能保存过更早的草稿，暴露给用户前
  先落库；重放 interrupt 时若已有更新的用户 Patch，**不覆盖它**（按 ``revision`` 判定）。
- **修订只回方案链**：回建筑还是回物件链，只看文档的 ``decisions.kind``，不看意图字段
  （它可能缺失或过期）——否则"把这张桌子改宽一点"会被当成建筑修订、重新产出一栋房子。
- **批准后建筑一律走确定性编译**：图纸一旦批准，结构/门窗/屋顶就是图纸的确定性函数，
  没有理由再让模型重算一遍；唯一例外是物件（编译器只认建筑的体量/立面/屋顶协议）。

节点入口与路由见 ``nodes/design_review_node.py``（薄壳）。
"""

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
        return "compile" if _compiles_deterministically(state) else "skeleton"
    if state.get("status") == "failed":
        return "__end__"
    return _revision_node(state)


def _compiles_deterministically(state: GenerationState) -> bool:
    """批准后是否走确定性编译。

    **建筑一律走编译**（没有开关）——图纸一旦批准，结构/门窗/屋顶/附属构件
    就是图纸的确定性函数，没有理由再让模型重算一遍。

    唯一例外是物件（"生成一张桌子"）：编译器只认建筑的体量/立面/屋顶协议，
    物件没有这些，必须留在 skeleton 上，否则会把一张桌子编译成一栋房子。
    """

    from app.design.resolver import is_object_plan

    plan = state.get("architecture_plan")
    return not is_object_plan(plan if isinstance(plan, dict) else None)


__all__ = ["design_review", "route_design_review"]
