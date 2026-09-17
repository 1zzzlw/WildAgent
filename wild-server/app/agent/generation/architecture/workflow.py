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
from app.agent.state import GenerationState
from app.agent.planning.execution import execution_plan_phase_guidance
from app.agent.planning.requirements import structured_requirement_guidance
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, merge_token_usage, stream_llm
from app.agent.prompts import append_approved_phase_guidance, build_architecture_plan_prompt
from app.agent.runtime import get_reasoning_callback
from app.spec.loader import SpecQuery
from app.agent.knowledge.policy import KNOWLEDGE_GUIDANCE
from app.utils.json_extractor import extract_json_object


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
        )
    except (ValidationError, ValueError) as exc:
        raise DesignContractError(_validation_reason(exc)) from exc


async def architecture_planner(state: GenerationState) -> dict:
    """输出唯一最终总体方案，模型失败时回退到确定性默认方案而不中断生成。"""
    from app.services.agent_service import agent_service

    started = _time.time()
    user_message = state["user_message"]
    thinking_mode = state.get("thinking_mode", False)
    execution_plan = state.get("execution_plan")
    plan_feedback = (
        str(execution_plan.get("feedback") or "")
        if isinstance(execution_plan, dict)
        else ""
    )
    revision_feedback = str(
        state.get("design_feedback") or state.get("plan_feedback") or plan_feedback or ""
    ).strip()
    design_request = (
        f"{user_message}\n本轮修订意见：{revision_feedback}"
        if revision_feedback else user_message
    )
    previous_plan = state.get("architecture_plan")

    complexity_terms = (
        "简单", "简易", "极简", "低复杂度", "复杂", "高细节", "丰富",
        "多体量", "退台", "错落", "simple", "minimal", "complex", "detailed",
    )
    if revision_feedback and any(term in revision_feedback.casefold() for term in complexity_terms):
        complexity_profile = resolve_complexity_profile(
            revision_feedback,
            precision_mode=thinking_mode,
        )
    elif isinstance(previous_plan, dict) and isinstance(previous_plan.get("complexity"), dict):
        complexity_profile = dict(previous_plan["complexity"])
    else:
        complexity_profile = resolve_complexity_profile(
            user_message,
            precision_mode=thinking_mode,
        )
    on_reasoning_delta = get_reasoning_callback()
    if on_reasoning_delta:
        if plan_feedback:
            revision_note = "根据已批准执行计划生成或调整总体方案"
        elif revision_feedback:
            revision_note = "根据计划修改意见调整总体方案"
        else:
            revision_note = "生成总体方案"
        await on_reasoning_delta(
            "architecture",
            f"\n### 总体建筑方案\n{revision_note}：正在制定建筑体量、立面轴网和屋顶方案...\n",
        )

    rag_started = _time.time()
    rag_error = None
    try:
        # 知识库检索
        spec_text = agent_service.spec_loader.load_many([
            SpecQuery("当前引擎已实现的宿主、连接与空间解析关系", {"doc_type": "recipe", "entity_name": "supported_assembly_relations"}),
            SpecQuery("当前 WILD 引擎能力边界", {"doc_type": "component", "knowledge_layer": "wild_schema"}),
        ], per_query=2)
    except Exception as exc:
        spec_text = ""
        rag_error = str(exc)
        logger.warning(f"[architecture] RAG 检索失败，继续使用内置 profile: {exc}")
    rag_ms = int((_time.time() - rag_started) * 1000)
    if on_reasoning_delta:
        await on_reasoning_delta(
            "architecture",
            f"已完成建筑知识检索（{len(spec_text)} 字，{rag_ms}ms），正在生成总体方案...\n",
        )
    previous_profile_id = (
        str(previous_plan.get("profile") or "")
        if isinstance(previous_plan, dict) else ""
    )
    normalization_request = revision_feedback or user_message
    
    # 判断建筑类型 
    profile = detect_architecture_profile(
        normalization_request,
        fallback_profile_id=previous_profile_id or None,
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

    phase_guidance = execution_plan_phase_guidance(execution_plan, "architecture")
    requirement_guidance = structured_requirement_guidance(
        state.get("structured_requirements"),
        "architecture",
    )
    prompt = append_approved_phase_guidance(
        prompt,
        "\n".join(item for item in (phase_guidance, requirement_guidance) if item),
        "这些是已批准任务及后端编译的结构化业务要求。总体方案必须落实它们；"
        "由真实槽位数量与配额一致性在 DesignDocument 契约处校验。",
    )

    raw_plan = None
    llm_chars = 0
    llm_ms = 0
    error = None
    token_usage = None
    recovery_diag = None
    try:
        llm_started = _time.time()
        # 精密模式下流式输出思考内容，避免“卡住很久却没有任何思考文本”。
        use_streaming = thinking_mode and on_reasoning_delta is not None
        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": design_request},
        ]
        if use_streaming:
            async def emit_reasoning(delta: str) -> None:
                assert on_reasoning_delta is not None
                await on_reasoning_delta("architecture", delta)

            llm_result = await stream_llm(llm, messages, on_reasoning_delta=emit_reasoning)
        else:
            llm_result = await invoke_llm(llm, messages)
        llm_ms = int((_time.time() - llm_started) * 1000)
        reply_text = llm_result.content
        llm_chars = len(reply_text)
        raw_plan = extract_json_object(reply_text)
        token_usage = llm_result.token_usage

        # 解析失败时做一次非思考定向格式恢复，避免偶发格式抖动丢弃整份方案。
        if raw_plan is None and on_reasoning_delta is not None:
            await on_reasoning_delta(
                "architecture",
                "\n总体方案结构化输出缺失或格式无效，正在进行一次定向格式恢复...\n",
            )
        if raw_plan is None:
            from app.llm.recovery import recover_single_json

            raw_plan, recovery_diag = await recover_single_json(
                prompt,
                design_request,
                reply_text,
                object_hint="包含 massing、volumes、facades、roof、component_quota 的建筑方案 JSON 对象",
                extra_instruction=(
                    "- 顶层必须直接包含 massing、volumes、facades、roof、component_quota；\n"
                    "- 不要输出候选数组，只输出最终选定的单一方案对象。"
                ),
            )
            token_usage = merge_token_usage(token_usage, (recovery_diag or {}).get("token_usage"))
            if raw_plan is not None:
                logger.warning("[architecture] 总体方案定向格式恢复成功")
    except Exception as exc:
        error = str(exc)
        logger.warning(f"[architecture] 模型服务故障，已阻断: {exc}")
        from app.llm.errors import model_failure_result
        return model_failure_result(exc)

    plan = normalize_architecture_plan(
        raw_plan or {},
        user_message=normalization_request,
        complexity_profile=complexity_profile,
        architecture_profile=profile,
    )

    # 诊断信息：单方案生成，只记录 profile 与是否走了兜底。
    selection_diag = {
        "profile": profile["id"],
        "profile_label": profile["label"],
        "used_fallback": raw_plan is None,
    }

    if on_reasoning_delta:
        rationale = plan.get("design_rationale", [])
        await on_reasoning_delta(
            "architecture",
            "\n### 总体建筑方案\n"
            f"- 复杂度目标：{complexity_profile['level']}；"
            f"至少 {complexity_profile['min_volumes']} 个体量、"
            f"{complexity_profile['min_detail_packages']} 个细部包。\n"
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
        "architecture_plan": plan,
        "design_document": design_document.model_dump(mode="json"),
        "resolved_design": resolved_design,
        "design_review_status": "pending",
        "design_feedback": "",
        "design_material_refresh": refresh_materials,
        "complexity_profile": complexity_profile,
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
        },
    }
