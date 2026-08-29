"""生成路径的建筑方案节点：同一模型先规划，再由后续节点落几何。"""

from __future__ import annotations

import json
import time as _time

from loguru import logger

from app.agent.architecture_plan import (
    detect_architecture_profile,
    resolve_complexity_profile,
    select_architecture_plan,
)
from app.agent.graph_state import GenerationState
from app.agent.execution_plan import execution_plan_phase_guidance
from app.agent.model_client import create_llm
from app.agent.llm_invocation import invoke_llm, merge_token_usage, stream_llm
from app.agent.prompts import build_architecture_plan_prompt
from app.agent.runtime_context import get_reasoning_callback
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_object


async def architecture_planner(state: GenerationState) -> dict:
    """输出紧凑方案候选，模型失败时回退到确定性默认方案而不中断生成。"""
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
        state.get("plan_feedback") or plan_feedback or state.get("floor_plan_feedback") or ""
    ).strip()
    complexity_profile = resolve_complexity_profile(
        user_message,
        precision_mode=thinking_mode,
    )
    on_reasoning_delta = get_reasoning_callback()
    if on_reasoning_delta:
        if plan_feedback:
            revision_note = "根据已批准执行计划生成或调整总体方案"
        elif revision_feedback:
            revision_note = "根据平面修改意见调整总体方案"
        else:
            revision_note = "生成总体方案"
        await on_reasoning_delta(
            "architecture",
            f"\n### 总体建筑方案\n{revision_note}：正在制定建筑体量、立面轴网和屋顶方案...\n",
        )

    rag_started = _time.time()
    rag_error = None
    try:
        spec_text = agent_service.spec_loader.load_many([
            SpecQuery(user_message, {"doc_type": "building_type"}),
            SpecQuery(user_message, {"doc_type": "recipe"}),
            SpecQuery(
                f"{user_message} 组合体量 退台 结构轴网 立面进深 细部构件",
                {"doc_type": "pattern", "entity_type": "building"},
            ),
        ], per_query=2)
    except Exception as exc:
        spec_text = ""
        rag_error = str(exc)
        logger.warning(f"[architecture] RAG 检索失败，继续使用内置 profile: {exc}")
    rag_ms = int((_time.time() - rag_started) * 1000)
    if on_reasoning_delta:
        await on_reasoning_delta(
            "architecture",
            f"已完成建筑知识检索（{len(spec_text)} 字，{rag_ms}ms），正在生成并比较候选方案...\n",
        )
    profile = detect_architecture_profile(user_message)
    prompt = build_architecture_plan_prompt(
        spec_text,
        profile,
        complexity_profile,
        current_plan=state.get("architecture_plan"),
        revision_feedback=revision_feedback,
        style_preference=state.get("style_preference"),
    )
    phase_guidance = execution_plan_phase_guidance(execution_plan, "architecture")
    if phase_guidance:
        prompt += f"""

# 已批准执行计划中的本阶段任务

{phase_guidance}

这些是公开的任务目标和验收条件。总体方案必须落实它们，但仍须服从本提示中的结构化输出协议和安全约束。
"""
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
            {"role": "user", "content": user_message},
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
            from app.agent.format_recovery import recover_single_json

            raw_plan, recovery_diag = await recover_single_json(
                prompt,
                user_message,
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
        logger.warning(f"[architecture] 方案模型调用失败，使用确定性回退: {exc}")

    plan, selection_diag = select_architecture_plan(
        raw_plan,
        user_message,
        complexity_profile,
    )
    if raw_plan is None:
        selection_diag["used_fallback"] = True
    if on_reasoning_delta:
        massing = plan["massing"]
        comparison_lines = ["\n**建筑方案候选对比**"]
        for candidate in selection_diag.get("candidate_summaries", []):
            candidate_massing = candidate.get("massing", {})
            candidate_roof = candidate.get("roof", {})
            comparison_lines.append(
                f"- 候选 {candidate.get('index', 0) + 1}｜评分 {candidate.get('score', 0)}："
                f"{candidate.get('concept') or '未命名方案'}；"
                f"{candidate_massing.get('width', '?')}×{candidate_massing.get('depth', '?')}m，"
                f"{candidate_massing.get('floors', '?')}层，"
                f"{candidate.get('volume_count', '?')}个体量，"
                f"主立面 {candidate.get('front_bays', '?')} 轴，"
                f"{candidate_roof.get('type', '?')} 屋顶。"
            )
        rationale = plan.get("design_rationale", [])
        comparison_lines.extend([
            "",
            f"**选择结果：候选 {selection_diag['selected_index'] + 1}**",
            f"- 复杂度目标：{complexity_profile['level']}；"
            f"至少 {complexity_profile['min_volumes']} 个体量、"
            f"{complexity_profile['min_detail_packages']} 个细部包。",
            *[f"- {item}" for item in rationale],
            "- 总体方案已确定；下一节点将在这些体量边界内独立设计并校验平面。",
        ])
        if selection_diag.get("used_fallback"):
            comparison_lines.append("- 模型总体方案不可用，本次采用了受 profile 约束的确定性总体方案。")
        await on_reasoning_delta(
            "architecture",
            "\n".join(comparison_lines) + "\n",
        )
    total_ms = int((_time.time() - started) * 1000)
    logger.info(
        f"[architecture] 完成: candidates={selection_diag['candidate_count']}, "
        f"selected={selection_diag['selected_index']}, "
        f"score={selection_diag['candidate_scores'][selection_diag['selected_index']]}, "
        f"{total_ms}ms"
    )
    return {
        "architecture_plan": plan,
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
