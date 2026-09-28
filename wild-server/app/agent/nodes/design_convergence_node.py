"""设计收敛节点：把图纸跑到"确实编得出来"，再交给人工审核（设计文档 §1.3 / §1.6）。

它插在 ``material_plan`` 与 ``design_review`` **之间**。为什么必须插在这里：全链
**唯一的确定性可行性校验**原先排在人工审核之后（`skeleton` 的四道预检，不过就硬失败），
于是刚批准的设计可以被编译器一票否决、**且没有修订通道**。本节点把
`compile_design(dry_run)` 驱动的图纸修订跑在审核之前，人工看到的才是一份确定编得出来的图纸。

算法本身在 `generation/architecture/convergence.py`（纯环 + 有界终止），本节点只做
状态读写与三条边界：物件链穿过、收敛失败不阻断（用户红线）、没改就不重建 DesignDocument。
"""

from __future__ import annotations

from loguru import logger

from app.agent.generation.architecture.convergence import converge_design
from app.agent.runtime import get_reasoning_callback
from app.agent.state import GenerationState
from app.design.resolver import is_object_plan, resolve_design


def _profile_for(plan: dict, user_message: str) -> dict | None:
    """重建建筑类型 profile。

    用确定性的 `detect_architecture_profile` 重算，而不是把它塞进 state——它本来就是
    能从需求串推出来的纯函数结果，多存一份就多一个会漂移的副本。
    """

    from app.agent.generation.architecture import detect_architecture_profile

    fallback = str(plan.get("profile") or "").strip() or None
    return detect_architecture_profile(user_message, fallback_profile_id=fallback)


async def design_convergence(state: GenerationState) -> dict:
    """收敛环节点。返回空 dict 表示"图纸没动"（物件链，或一次就收敛）。"""

    plan = state.get("architecture_plan")
    if not isinstance(plan, dict) or not plan:
        return {}
    if is_object_plan(plan):
        # 编译器只认建筑的体量/立面/屋顶协议，物件链不适用；判据与方案/材质/骨架层共用同一个。
        return {}

    user_message = state.get("user_message", "")
    diag_state = state.get("architecture_diag")
    diag_state = diag_state if isinstance(diag_state, dict) else {}
    complexity_profile = diag_state.get("complexity_profile")
    complexity_profile = complexity_profile if isinstance(complexity_profile, dict) else None
    raw_plan = diag_state.get("raw_plan")
    material_plan = state.get("material_plan")

    outcome = await converge_design(
        plan=plan,
        raw_plan=raw_plan if isinstance(raw_plan, dict) else None,
        user_message=user_message,
        level=str((complexity_profile or {}).get("level") or "standard"),
        complexity_profile=complexity_profile,
        architecture_profile=_profile_for(plan, user_message),
        thinking_mode=bool(state.get("thinking_mode")),
        material_plan=material_plan if isinstance(material_plan, dict) else None,
        on_reasoning_delta=get_reasoning_callback(),
    )
    diag = dict(outcome.diag)
    if not outcome.changed:
        return {"design_convergence": diag}

    from app.agent.generation.architecture.workflow import build_design_document_or_error

    try:
        document = build_design_document_or_error(
            outcome.plan,
            session_id=str(state.get("session_id") or state.get("request_id") or "unknown"),
            source_request=user_message,
            building_type=str(
                outcome.plan.get("profile") or state.get("building_type") or "building"
            ),
            style_intent=list(state.get("style_preference") or []),
            previous=state.get("design_document"),
        )
    except Exception as exc:
        # 收敛把图纸改坏了（业务不变量不过）⇒ **保留原图纸**。让"可选优化"覆盖掉一份本来
        # 合法的图纸，等于把优化变成必踩的坑。如实记账，照常进人工审核。
        logger.error(f"[convergence] 收敛后的图纸不满足设计契约，已回退原图纸: {exc}")
        return {"design_convergence": {**diag, "document_error": str(exc), "reverted": True}}

    logger.info(
        f"[convergence] {diag['stop_reason']}："
        f"{diag['initial_defects']} → {diag['final_defects']} 条 error 缺陷，"
        f"修订 {diag['revisions']} 轮"
    )
    return {
        "architecture_plan": outcome.plan,
        "design_document": document.model_dump(mode="json"),
        "resolved_design": resolve_design(document).model_dump(mode="json"),
        "design_convergence": diag,
    }


__all__ = ["design_convergence"]
