"""生成路径的建筑方案节点：同一模型先规划，再由后续节点落几何。"""

from __future__ import annotations

import json
import time as _time

from loguru import logger

from app.agent.architecture_plan import detect_architecture_profile, select_architecture_plan
from app.agent.graph_state import GenerationState
from app.agent.model_client import create_llm
from app.agent.prompts import build_architecture_plan_prompt
from app.agent.runtime_context import get_reasoning_callback
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_object


async def architecture_planner(state: GenerationState) -> dict:
    """输出紧凑方案候选，模型失败时回退到确定性默认方案而不中断生成。"""
    from app.services.agent_service import agent_service

    started = _time.time()
    user_message = state["user_message"]
    on_reasoning_delta = get_reasoning_callback()
    if on_reasoning_delta:
        await on_reasoning_delta("architecture", "正在制定建筑体量、立面轴网和屋顶方案...\n")

    rag_started = _time.time()
    rag_error = None
    try:
        spec_text = agent_service.spec_loader.load_many([
            SpecQuery(user_message, {"doc_type": "building_type"}),
            SpecQuery(user_message, {"doc_type": "recipe"}),
        ], per_query=2)
    except Exception as exc:
        spec_text = ""
        rag_error = str(exc)
        logger.warning(f"[architecture] RAG 检索失败，继续使用内置 profile: {exc}")
    rag_ms = int((_time.time() - rag_started) * 1000)
    profile = detect_architecture_profile(user_message)
    prompt = build_architecture_plan_prompt(spec_text, profile)
    raw_plan = None
    llm_chars = 0
    llm_ms = 0
    error = None
    token_usage = None
    try:
        llm_started = _time.time()
        response = await create_llm(enable_thinking=False, streaming=False).ainvoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ])
        llm_ms = int((_time.time() - llm_started) * 1000)
        reply_text = response.content if hasattr(response, "content") else str(response)
        llm_chars = len(reply_text)
        raw_plan = extract_json_object(reply_text)
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
        if usage:
            token_usage = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
    except Exception as exc:
        error = str(exc)
        logger.warning(f"[architecture] 方案模型调用失败，使用确定性回退: {exc}")

    plan, selection_diag = select_architecture_plan(raw_plan, user_message)
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
                f"主立面 {candidate.get('front_bays', '?')} 轴，"
                f"{candidate_roof.get('type', '?')} 屋顶。"
            )
        rationale = plan.get("design_rationale", [])
        comparison_lines.extend([
            "",
            f"**选择结果：候选 {selection_diag['selected_index'] + 1}**",
            *[f"- {item}" for item in rationale],
            "- 下一步由骨架节点落实结构，门窗坐标随后由程序按真实墙体和立面轴网计算。",
        ])
        if selection_diag.get("used_fallback"):
            comparison_lines.append("- 模型方案不可用，本次采用了受范围约束的安全回退方案。")
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
        "architecture_diag": {
            **selection_diag,
            "rag_chars": len(spec_text),
            "rag_ms": rag_ms,
            "rag_error": rag_error,
            "prompt_chars": len(prompt),
            "llm_chars": llm_chars,
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "error": error,
            "total_ms": total_ms,
        },
    }
