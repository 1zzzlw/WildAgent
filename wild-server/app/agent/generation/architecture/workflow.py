"""生成路径的建筑方案节点：同一模型先规划，再由后续节点落几何。"""

from __future__ import annotations

import time as _time

from loguru import logger
from pydantic import ValidationError

from app.agent.generation.architecture import (
    detect_architecture_profile,
    normalize_architecture_plan,
    resolve_complexity_profile,
)
from app.agent.generation.architecture.design_workflow import draft_design_blocks
from app.agent.state import GenerationState
from app.agent.prompts import build_architecture_plan_prompt
from app.agent.runtime import get_reasoning_callback
from app.spec.loader import SpecQuery
from app.agent.knowledge.policy import KNOWLEDGE_GUIDANCE


class DesignContractError(RuntimeError):
    """设计方案不满足 DesignDocument 业务不变量时抛出的可读业务错误。"""


def _validation_reason(exc: Exception) -> str:
    """把契约错误压缩成一句可读原因，避免整段 Pydantic 调用栈进入用户提示。"""

    errors = getattr(exc, "errors", None)
    if callable(errors):
        messages = []
        for item in errors():
            message = str(item.get("msg") or "").removeprefix("Value error, ").strip()
            if message:
                messages.append(message)
        if messages:
            return "；".join(messages[:3])
    return " ".join(str(exc).split())[:300]


def build_design_document_or_error(
    plan: dict,
    *,
    session_id: str,
    source_request: str,
    building_type: str,
    style_intent: list[str],
    previous: object,
    revision_feedback: str = "",
):
    """构造设计契约；不满足业务不变量时抛 `DesignContractError`。

    未捕获的 Pydantic 异常会直接终止整轮生成，用户只看到一条 ValidationError。
    这里把它转成受控业务错误，让节点能给出明确原因并走正常失败分支。
    """

    from app.design.resolver import build_design_document

    try:
        return build_design_document(
            plan,
            session_id=session_id,
            source_request=source_request,
            building_type=building_type,
            style_intent=style_intent,
            previous=previous,
            revision_feedback=revision_feedback,
        )
    except (ValidationError, ValueError) as exc:
        raise DesignContractError(_validation_reason(exc)) from exc


async def architecture_planner(state: GenerationState) -> dict:
    """输出唯一最终总体方案。

    失败语义分两类：
      - 模型服务故障 → 返回 `model_failure_result()`（`error` + `terminal_model_error`），终止本轮图运行，不进入建筑修复循环；
      - 模型输出解析不了 → 走 normalize_architecture_plan() 的确定性归一化兜底，不中断。
    """
    from app.services.agent_service import agent_service

    started = _time.time()
    user_message = state["user_message"]
    thinking_mode = state.get("thinking_mode", False)
    # 用户的修正反馈
    revision_feedback = str(state.get("design_feedback") or "").strip()
    # python 中的三元表达式，A if 条件 else B
    design_request = (
        f"{user_message}\n本轮修订意见：{revision_feedback}"
        if revision_feedback else user_message
    )
    # 把修订意见拼进请求串
    previous_plan = state.get("architecture_plan")

    # 修订时沿用上一版复杂度目标；否则固定标准档（粒度分档已下线，2026-09-30）。
    if isinstance(previous_plan, dict) and isinstance(previous_plan.get("complexity"), dict):
        complexity_profile = dict(previous_plan["complexity"])
    else:
        complexity_profile = resolve_complexity_profile(user_message)
        
    on_reasoning_delta = get_reasoning_callback()
    # 给前端的进度提示：正在制定建筑体量、立面轴网和屋顶方案
    if on_reasoning_delta:
        # 如果是修订反馈
        if revision_feedback:
            revision_note = "根据修改意见调整总体方案"
        # 如果是首次生成
        else:
            revision_note = "生成总体方案"
        # 给前端发送进度提示
        await on_reasoning_delta(
            "architecture:progress",
            f"\n### 总体建筑方案\n{revision_note}：正在制定建筑体量、立面轴网和屋顶方案...\n",
        )

    rag_started = _time.time()
    rag_error = None
    try:
        # 知识库检索：前两条是固定契约查询；第三条把用户消息原文带进查询文本。
        # 分类器给出的形制标签（模型自选）一并作为特征词，让"别墅的形制契约"和
        # "塔的形制契约"这类差异大的形制各检索各的。`custom` 是"未定"，不带形制
        # 语义，拼进去只会稀释查询，所以只在非 custom 时追加。
        intent_profile = str(state.get("intent_profile") or "").strip()
        profile_term = (
            f" {intent_profile} 形制" if intent_profile and intent_profile != "custom" else ""
        )
        spec_text = agent_service.spec_loader.load_many([
            SpecQuery("当前引擎已实现的宿主、连接与空间解析关系", {"doc_type": "recipe", "entity_name": "supported_assembly_relations"}),
            SpecQuery("当前 WILD 引擎能力边界", {"doc_type": "component", "knowledge_layer": "wild_schema"}),
            SpecQuery(
                f"{user_message}{profile_term} 建筑形制特征 技法 组装配方 设计层表态",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
        ], per_query=2)
    except Exception as exc:
        spec_text = ""
        rag_error = str(exc)
        logger.warning(f"[architecture] RAG 检索失败，继续使用内置 profile: {exc}")
    rag_ms = int((_time.time() - rag_started) * 1000)
    if on_reasoning_delta:
        await on_reasoning_delta(
            "architecture:progress",
            f"已完成建筑知识检索（{len(spec_text)} 字，{rag_ms}ms），正在生成总体方案...\n",
        )

    previous_profile_id = (
        # 从上轮方案里继承 profile，避免用户没说话就被兜底成 "building"。
        str(previous_plan.get("profile") or "")
        # 如果不是 dict 则说明是首次生成，那么就是空字符串
        if isinstance(previous_plan, dict) else ""
    )
    normalization_request = revision_feedback or user_message

    # 判断建筑形制。id 来自分类器；
    # 修订时优先沿用上一版方案的 profile，否则用户只说"把门改大"也会被重算档位。
    # 物理边界无论如何都来自 custom 档，所以这里换 id 只影响检索与观测，不影响能力。
    profile = detect_architecture_profile(
        normalization_request,
        fallback_profile_id=previous_profile_id or None,
        profile_id=previous_profile_id or state.get("intent_profile"),
    )

    prompt = build_architecture_plan_prompt(
        spec_text,
        profile,
        complexity_profile,
        current_plan=state.get("architecture_plan"),
        revision_feedback=revision_feedback,
        style_preference=state.get("style_preference"),
    )

    prompt += "\n" + KNOWLEDGE_GUIDANCE

    raw_plan = None
    llm_chars = 0
    llm_ms = 0
    error = None
    token_usage = None
    recovery_diag = None
    block_diag: dict = {}
    try:
        # 首次成图：逐块写。
        # 依赖表是常量、后块只看前序定稿内容，所以"host 引用不存在的宿主"这类
        # 悬空引用被结构性地消掉了，而不是等编译报错再回头改。
        # 某块写不出来不阻断：留空交下游归一化兜底，缺口由 `defaulted` 如实报出。
        block_started = _time.time()
        draft, block_diag = await draft_design_blocks(
            base_prompt=prompt,
            user_request=design_request,
            thinking_mode=thinking_mode,
            on_reasoning_delta=on_reasoning_delta,
            # 试算工具要用同一套归一化参数，否则"试算通过、正式编译不通过"
            # 会变成一条查不出来的分叉。
            complexity_profile=complexity_profile,
            architecture_profile=profile,
            current_plan=previous_plan if revision_feedback and isinstance(previous_plan, dict) else None,
        )
        llm_ms = int((_time.time() - block_started) * 1000)
        llm_chars = sum(
            int(item.get("llm_chars") or 0) for item in block_diag.get("blocks", [])
        )
        token_usage = block_diag.get("token_usage")
        # 一块都没定稿 ⇒ 视同"没有方案"（`used_fallback` 要如实为真）。
        raw_plan = (
            {**previous_plan, **draft}
            if revision_feedback and isinstance(previous_plan, dict)
            else draft or None
        )
    except Exception as exc:
        error = str(exc)
        logger.warning(f"[architecture] 模型服务故障，已阻断: {exc}")
        from app.llm.errors import model_failure_result
        return model_failure_result(exc)

    # 模型草稿是不可信输入：归一化对它必须"失败不阻断"（与收敛环
    # convergence.py 的 invalid_revision 同一纪律）。实测曾有一条
    # `ground[entrance_bay - 1]` 越界的 IndexError 从这里穿出去掐掉整轮生成
    # （根因 _clamp_number 不夹 default，已修；这里再兜一层防同类）。
    # 归一化失败 ⇒ 视同"没有可用方案"，走确定性 fallback，如实记账。
    normalization_error: str | None = None
    # 归一化取舍的账本（用户覆盖模型 / 模型写了表外值）。trace 里看不到它，
    # "形状怎么变成这个的"就只能靠猜 —— 2026-10-08 实测过一次。
    normalize_notes: list[str] = []
    normalization_changes: list[dict] = []
    try:
        plan = normalize_architecture_plan(
            raw_plan or {},
            user_message=normalization_request,
            complexity_profile=complexity_profile,
            architecture_profile=profile,
            normalize_notes=normalize_notes,
            normalization_changes=normalization_changes,
            input_source="model",
        )
    except Exception as exc:  # noqa: BLE001 —— 草稿不可信，兜底优先
        normalization_error = f"{type(exc).__name__}: {exc}"
        logger.warning(f"[architecture] 草稿归一化失败，改走确定性 fallback: {normalization_error}")
        plan = normalize_architecture_plan(
            {},
            user_message=normalization_request,
            complexity_profile=complexity_profile,
            architecture_profile=profile,
            normalize_notes=normalize_notes,
            normalization_changes=normalization_changes,
            input_source="model",
        )

    if normalization_error:
        from app.design.normalization import plan_changes
        normalization_changes = plan_changes(raw_plan, plan, source="model")
        for change in normalization_changes:
            change["reason"] += f"；整案降级：{normalization_error}"
    plan["normalization_changes"] = normalization_changes

    # Preserve adopted pre-normalization choices and request constraints independently
    # of normalization (which does not own intent).
    from app.design.completeness import adopted_from_plan
    plan["design_constraints"] = [
        *((raw_plan or {}).get("design_constraints") or []),
        *adopted_from_plan(raw_plan or {}),
    ]

    # 诊断信息：单方案生成，只记录 profile 与是否走了兜底。
    selection_diag = {
        "profile": profile["id"],
        "used_fallback": raw_plan is None or normalization_error is not None,
        "used_local_fallback": any(c["category"] == "default" or c["semantic_change"] for c in normalization_changes),
        "normalization_changes": normalization_changes,
        "normalization_error": normalization_error,
        "normalize_notes": normalize_notes,
        "raw_plan": raw_plan,
        "normalized_plan": plan,
    }

    if on_reasoning_delta:
        rationale = plan.get("design_rationale", [])
        await on_reasoning_delta(
            "architecture:progress",
            "\n### 总体建筑方案\n"
            + "\n".join(f"- {item}" for item in rationale) + "\n"
            + "- 总体方案已确定；下一节点将解析受控材质并生成可审核的设计文档与 SVG。\n",
        )

    total_ms = int((_time.time() - started) * 1000)
    logger.info(f"[architecture] 完成: profile={profile['id']}, {total_ms}ms")
    
    from app.design.resolver import resolve_design

    try:
        design_document = build_design_document_or_error(
            plan,
            session_id=str(state.get("session_id") or state.get("request_id") or "unknown"),
            source_request=user_message,
            building_type=str(plan.get("profile") or state.get("building_type") or "building"),
            style_intent=list(state.get("style_preference") or []),
            previous=state.get("design_document"),
            revision_feedback=revision_feedback,
        )
    except DesignContractError as exc:
        # 体量覆盖、立面完整、槽位与配额一致等业务不变量失败属于可预期的业务失败，
        # 必须走受控失败分支，而不是让未捕获异常终止整轮生成。
        error = f"总体方案不满足设计契约：{exc}"
        logger.error(f"[architecture] {error}")
        return {
            "status": "failed",
            "error": error,
            "architecture_diag": {
                **selection_diag,
                "design_contract_error": True,
                "rag_chars": len(spec_text),
                "rag_ms": rag_ms,
                "rag_error": rag_error,
                "prompt_chars": len(prompt),
                "llm_chars": llm_chars,
                "llm_ms": llm_ms,
                "token_usage": token_usage,
                "recovery": recovery_diag,
                "thinking_enabled": thinking_mode,
                "design_blocks": block_diag,
            },
        }
    resolved_design = resolve_design(design_document).model_dump(mode="json")
    material_feedback_terms = (
        "材质", "材料", "颜色", "配色", "玻璃材质", "幕墙", "金属", "木", "石材",
        "material", "color", "palette", "texture",
    )
    refresh_materials = not isinstance(state.get("design_document"), dict) or any(
        term in revision_feedback.casefold() for term in material_feedback_terms
    )
    return {
        # 设计方案本体
        "architecture_plan": plan,
        # 给用户审核的文档版
        "design_document": design_document.model_dump(mode="json"),
        # 可执行视图
        "resolved_design": resolved_design,
        # 审核状态
        "design_review_status": "pending",
        # 清空修订意见
        "design_feedback": "",
        # 是否需要刷新材质节点
        "design_material_refresh": refresh_materials,
        # 诊断账本（谁定的、花了多少、哪块难写）
        "architecture_diag": {
            **selection_diag,
            "rag_chars": len(spec_text),
            "rag_ms": rag_ms,
            "rag_error": rag_error,
            "prompt_chars": len(prompt),
            "llm_chars": llm_chars,
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "recovery": recovery_diag,
            "error": error,
            "thinking_enabled": thinking_mode,
            "complexity_profile": complexity_profile,
            "total_ms": total_ms,
            # 逐块诊断：哪几块一次过、哪几块试满上限仍未定稿。**不落这一份就等于
            # 把"分块"唯一带来的可观测性丢掉**——出问题时只能看到"图纸不全"。
            "design_blocks": block_diag,
        },
    }
