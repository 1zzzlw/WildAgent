"""独立平面设计节点：模型生成 FloorPlanIR，程序校验、兜底并生成三维预览。"""

from __future__ import annotations

from copy import deepcopy
import time as _time

from loguru import logger

from app.agent.floor_plan_rules import (
    auto_repair_floor_plan_rules,
    evaluate_floor_plan_rules,
)
from app.agent.graph_state import GenerationState
from app.agent.execution_plan import execution_plan_phase_guidance
from app.agent.llm_invocation import invoke_llm, merge_token_usage, stream_llm
from app.agent.model_client import create_llm
from app.agent.prompts import build_floor_plan_prompt
from app.agent.runtime_context import get_reasoning_callback
from app.agent.spatial_plan import (
    architecture_plan_to_svgs,
    normalize_spatial_plan,
    recover_confirmable_spatial_plan,
    spatial_plan_summary,
    validate_spatial_plan,
)
from app.spec.loader import SpecQuery
from app.utils.json_extractor import extract_json_object


async def floor_plan_designer(state: GenerationState) -> dict:
    """在总体建筑方案范围内独立生成平面；任何几何失败都给出可直接确认的基础方案。"""

    from app.services.agent_service import agent_service

    started = _time.time()
    architecture_plan = deepcopy(state.get("architecture_plan") or {})
    massing = architecture_plan.get("massing") or {}
    volumes = architecture_plan.get("volumes") or []
    facades = architecture_plan.get("facades") or {}
    user_message = str(state.get("user_message") or "")
    current_floor_plan = state.get("floor_plan")
    feedback = str(state.get("floor_plan_feedback") or "").strip()
    revision = int(state.get("floor_plan_revision") or 0)
    thinking_mode = bool(state.get("thinking_mode"))
    on_reasoning_delta = get_reasoning_callback()

    if on_reasoning_delta:
        action = "根据修改意见重新规划" if feedback else "开始规划"
        await on_reasoning_delta(
            "floor_plan_design:progress",
            f"\n### 平面设计版本 {revision + 1}\n{action}：分析房间关系、入口、流线、门窗和跨层空间...\n",
        )

    rag_started = _time.time()
    rag_error = None
    try:
        spec_text = agent_service.spec_loader.load_many([
            SpecQuery(user_message, {"doc_type": "pattern", "entity_type": "building"}),
            SpecQuery(f"{user_message} 平面 功能分区 流线 房间 门窗", {"doc_type": "recipe"}),
            SpecQuery("室内墙 门 窗 楼梯 电梯 中庭 平面关系", {"doc_type": "component"}),
        ], per_query=2)
    except Exception as exc:
        spec_text = ""
        rag_error = str(exc)
        logger.warning(f"[floor_plan_design] RAG 检索失败，继续使用总体方案: {exc}")
    rag_ms = int((_time.time() - rag_started) * 1000)
    if on_reasoning_delta:
        await on_reasoning_delta(
            "floor_plan_design:progress",
            f"已完成平面知识检索（{len(spec_text)} 字，{rag_ms}ms），正在生成 FloorPlanIR...\n",
        )

    prompt = build_floor_plan_prompt(
        architecture_plan,
        spec_text,
        current_floor_plan=current_floor_plan if isinstance(current_floor_plan, dict) else None,
        revision_feedback=feedback,
        style_preference=state.get("style_preference"),
    )
    phase_guidance = execution_plan_phase_guidance(
        state.get("execution_plan"),
        "floor_plan_design",
    )
    if phase_guidance:
        prompt += f"""

# 已批准执行计划中的本阶段任务

{phase_guidance}

平面方案必须落实这些公开任务及验收条件，但不得突破 FloorPlanIR 协议和工程预审规则。
"""
    raw_spatial = None
    error = None
    llm_ms = 0
    llm_result = None
    recovery_diag = None
    try:
        llm_started = _time.time()
        use_streaming = thinking_mode and on_reasoning_delta is not None
        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ]
        if use_streaming:
            async def emit_reasoning(delta: str) -> None:
                assert on_reasoning_delta is not None
                await on_reasoning_delta("floor_plan_design", delta)

            llm_result = await stream_llm(llm, messages, on_reasoning_delta=emit_reasoning)
        else:
            llm_result = await invoke_llm(llm, messages)
        llm_ms = int((_time.time() - llm_started) * 1000)
        parsed = extract_json_object(llm_result.content)
        if isinstance(parsed, dict):
            candidate = parsed.get("spatial_plan", parsed)
            raw_spatial = candidate if isinstance(candidate, dict) else None
        if raw_spatial is None:
            # 解析失败时做一次非思考定向格式恢复，避免偶发格式抖动丢弃整份平面。
            from app.agent.format_recovery import recover_single_json

            recovered, recovery_diag = await recover_single_json(
                prompt,
                user_message,
                llm_result.content,
                object_hint="包含 levels、walls、spaces、openings、vertical_circulation 的 FloorPlanIR JSON 对象",
                extra_instruction=(
                    "- 顶层必须直接包含 levels 数组；\n"
                    "- 不要输出代码围栏或 Markdown。"
                ),
            )
            if isinstance(recovered, dict):
                candidate = recovered.get("spatial_plan", recovered)
                raw_spatial = candidate if isinstance(candidate, dict) else None
            llm_result.token_usage = merge_token_usage(
                llm_result.token_usage,
                (recovery_diag or {}).get("token_usage"),
            )
            if raw_spatial is not None:
                logger.warning("[floor_plan_design] 平面定向格式恢复成功")
    except Exception as exc:
        error = str(exc)
        logger.warning(f"[floor_plan_design] 模型调用失败，使用确定性基础平面: {exc}")

    spatial_plan = normalize_spatial_plan(raw_spatial, massing, volumes, facades)
    floor_plan_notice = ""
    spatial_plan, used_confirmable_recovery = recover_confirmable_spatial_plan(
        raw_spatial,
        spatial_plan,
        massing,
        volumes,
    )
    if recovery_diag and spatial_plan.get("source") == "model":
        recovery_diag["used_recovery"] = True
    if used_confirmable_recovery:
        if error:
            floor_plan_notice = "平面模型调用失败，已生成可直接审核和确认的确定性基础平面。"
        elif raw_spatial is None:
            floor_plan_notice = "平面模型没有返回可解析结果，已生成可直接审核和确认的确定性基础平面。"
        else:
            floor_plan_notice = (
                "模型平面未通过确定性几何校验，已自动生成可直接确认的基础平面；"
                "你仍可在确认前继续提交修改意见。"
            )

    spatial_plan["facades"] = deepcopy(facades)
    spatial_plan, rule_repairs = auto_repair_floor_plan_rules(spatial_plan)
    spatial_plan["rule_review"] = evaluate_floor_plan_rules(spatial_plan)
    architecture_plan["spatial_plan"] = spatial_plan
    spatial_issues = validate_spatial_plan(spatial_plan)
    geometry_issues = validate_spatial_plan(spatial_plan, include_rules=False)
    if rule_repairs and not spatial_issues:
        repair_summary = "；".join(str(item["message"]) for item in rule_repairs)
        repair_notice = f"工程预审发现可确定修复的问题，程序已自动修改并复检通过：{repair_summary}。"
        floor_plan_notice = " ".join(item for item in (floor_plan_notice, repair_notice) if item)
    elif spatial_issues and not geometry_issues and not floor_plan_notice:
        floor_plan_notice = "平面几何可以预览，但工程预审未通过；请按实测问题修改后再确认。"
    floor_plan_svgs = architecture_plan_to_svgs(architecture_plan) if not geometry_issues else {}
    floor_plan_svg = floor_plan_svgs.get("1") or next(iter(floor_plan_svgs.values()), "")
    summary = spatial_plan_summary(spatial_plan)

    if on_reasoning_delta:
        source_label = {
            "model": "模型平面",
            "deterministic_template": "确定性可确认平面",
        }.get(str(spatial_plan.get("source")), "平面方案")
        await on_reasoning_delta(
            "floor_plan_design:progress",
            "\n".join([
                "",
                "**平面设计结果**",
                f"- 来源：{source_label}",
                f"- {summary['level_count']} 层，{summary['space_count']} 个空间，"
                f"{summary['interior_wall_count']} 面内墙，{summary['opening_count']} 个内部洞口",
                f"- 几何校验：{'通过' if not geometry_issues else f'未通过 {len(geometry_issues)} 项'}",
                f"- 工程预审：{'通过' if not spatial_issues else f'仍有 {len(spatial_issues)} 项需处理'}",
                *(
                    [f"- 自动修复：{'；'.join(str(item['message']) for item in rule_repairs)}"]
                    if rule_repairs else []
                ),
                "- SVG 审核图已生成；正式三维场景仍未生成和保存。",
            ]) + "\n",
        )

    total_ms = int((_time.time() - started) * 1000)
    return {
        "architecture_plan": architecture_plan,
        "floor_plan": spatial_plan,
        "floor_plan_svg": floor_plan_svg,
        "floor_plan_svgs": floor_plan_svgs,
        "floor_plan_validation": spatial_issues,
        "floor_plan_notice": floor_plan_notice,
        "floor_plan_review_status": "pending",
        "floor_plan_auto_repairing": False,
        "floor_plan_design_diag": {
            "rag_chars": len(spec_text),
            "rag_ms": rag_ms,
            "rag_error": rag_error,
            "prompt_chars": len(prompt),
            "llm_chars": llm_result.content_chars if llm_result else 0,
            "llm_ms": llm_ms,
            "reasoning_chars": llm_result.reasoning_chars if llm_result else 0,
            "reasoning_preview": llm_result.reasoning[:800] if llm_result else "",
            "token_usage": llm_result.token_usage if llm_result else None,
            "error": error,
            "used_confirmable_recovery": used_confirmable_recovery,
            "recovery": recovery_diag,
            "rule_repairs": rule_repairs,
            "floor_plan": summary,
            "total_ms": total_ms,
        },
    }
