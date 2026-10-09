"""
Layer 2 扩展: 回调重试节点

校验失败后，对每个失败组件做精准修正：
  结构化错误 + RAG + 工具数据 → LLM 选择白名单修复工具 → 程序执行并复检

这是 LangGraph 架构中最关键的创新点，详见设计文档 03-回调与重试机制.md。
"""
from loguru import logger

from app.agent.validation.diagnostics import blueprint_fingerprint
from app.agent.validation.candidate import evaluate_candidate
from app.agent.state import GenerationState
from app.agent.prompts import build_callback_prompt
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, stream_llm
from app.llm.errors import classify_model_error
from app.agent.runtime import get_reasoning_callback
from app.agent.repair.tools import execute_repair_actions, extract_repair_actions
from app.agent.repair.state_updates import state_updates_from_candidate
from app.agent.validation.issues import compare_issue_sets
from app.spec.loader import SpecQuery


async def callback_node(state: GenerationState) -> dict:
    """对校验失败的组件进行精确修正重试

    流程:
    1. 从 failed_components 提取失败信息（含 current_params）
    2. 精准 RAG（按错误类型检索）
    3. 运行组件工具获取空间约束数据（tools 提供"具体错在哪里"）
    4. 构建 callback_payload（含骨架上下文 + 当前参数 + 工具建议 + RAG）
    5. LLM 只输出白名单修复动作（支持流式思考）
    6. 程序在副本执行动作，用与最终门禁相同的完整入口验收
    7. 只有完整通过且保持已履约项时提交；其余候选回滚
    """
    source_blueprint = state.get("merged_blueprint") or {}
    before = evaluate_candidate(source_blueprint, design_document=state.get("design_document"),
                                design_brief=state.get("design_brief"), source="callback_before")
    prior_audit = state.get("repair_audit") or {}
    source_fingerprint = blueprint_fingerprint(source_blueprint)
    if before["approved_design_errors"]:
        return {"repair_audit": {"accepted": False, "stop_reason": "design_revision_required",
                "source_fingerprint": source_fingerprint,
                "reason": "批准版本本身几何无效，局部改值不能同时满足几何与批准门禁；请修订后重新审核"}}
    if (prior_audit.get("source_fingerprint") == source_fingerprint
            and prior_audit.get("accepted") is False):
        return {"repair_audit": {**prior_audit, "stop_reason": "repeated_candidate"}}
    failed_components = state.get("failed_components", [])
    if not failed_components:
        logger.info("[callback_node] 无失败组件，跳过")
        return {"retry_count": state.get("retry_count", 0) + 1}

    # ── 0. per-component 重试过滤 ──
    max_retries = state.get("max_retries", 3)
    comp_retries = dict(state.get("component_retry_counts", {}))
    retryable: list[dict] = []
    skipped_exhausted: list[str] = []

    for fc in failed_components:
        comp_id = fc.get("component_id", "")
        current = comp_retries.get(comp_id, 0)
        if current >= max_retries:
            skipped_exhausted.append(comp_id)
            logger.warning(f"[callback_node] {comp_id} 已达 per-component 重试上限 ({current}/{max_retries}), 跳过")
        else:
            comp_retries[comp_id] = current + 1
            retryable.append(fc)

    if skipped_exhausted:
        logger.info(f"[callback_node] 跳过 {len(skipped_exhausted)} 个耗尽重试的组件: {skipped_exhausted}")

    if not retryable:
        logger.info("[callback_node] 所有失败组件均已耗尽重试")
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "component_retry_counts": comp_retries,
        }

    logger.info(f"[callback_node] 开始修正 {len(retryable)} 个失败组件 (已跳过 {len(skipped_exhausted)} 个)")

    skeleton_summary = state.get("skeleton_summary", "")
    skeleton_blueprint = state.get("skeleton_blueprint", {})
    passed_ids = state.get("passed_component_ids", [])
    retry_count = state.get("retry_count", 0)
    thinking_mode = state.get("thinking_mode", False)
    on_reasoning_delta = get_reasoning_callback()

    # ── 1. 精准 RAG + 工具数据（按失败组件类型检索）──
    from app.services.agent_service import agent_service

    failed_types = list({fc.get("component_type", "") for fc in retryable})
    queries = []
    for ftype in failed_types:
        if ftype:
            queries.append(SpecQuery(
                f"{ftype} component specification rules",
                {"entity_type": ftype}
            ))

    if not queries:
        queries = [SpecQuery("component rules specification", {})]

    try:
        spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
    except Exception as exc:
        spec_text = ""
        logger.warning(f"[callback_node] RAG 检索失败，继续使用校验上下文: {exc}")
    logger.info(f"[callback_node] RAG 上下文: {len(spec_text)} 字符")

    # ── 2. 运行组件工具，获取空间约束数据 ──
    # 为每个可重试的失败组件构建临时 blueprint 并跑 validate 工具
    enriched_failed = []
    for fc in retryable:
        enriched = dict(fc)  # 拷贝原始失败信息
        comp_type = fc.get("component_type", "")

        # 尝试运行组件校验工具获取精确空间数据
        tool_context = ""
        try:
            from app.tools.component_tools import validate_component

            # 宿主校验依赖同墙门窗，必须使用当前完整场景；校验器只读其副本。
            from copy import deepcopy
            temp_bp = deepcopy(state.get("merged_blueprint") or skeleton_blueprint)
            geometry = temp_bp.get("geometry") or {}
            entities = [*geometry.get("elements", []), *geometry.get("components", [])]
            target = next((item for item in entities if item.get("id") == fc.get("component_id")),
                          fc.get("current_params") or {})
            host = target.get("parentWall") or target.get("parentRoof") or target.get("parentFloor")
            enriched["context_entities"] = [item for item in entities
                if item.get("id") == host or (host and item.get("parentWall") == host
                    and item.get("type") in {"door", "window", "bay_window"})]
            tool_context = validate_component(comp_type, temp_bp)
            if tool_context:
                logger.info(f"[callback_node] 工具数据 ({comp_type}): {len(tool_context)} 字符")
        except Exception as e:
            logger.warning(f"[callback_node] 工具调用失败 ({comp_type}): {e}")

        enriched["tool_data"] = tool_context
        enriched_failed.append(enriched)

    # ── 3. 构建 callback prompt ──
    system_prompt = build_callback_prompt(
        spec_text=spec_text,
        skeleton_summary=skeleton_summary,
        failed_components=enriched_failed,
        passed_component_ids=passed_ids,
    )

    # ── 4. LLM 修正（支持流式思考）──
    use_streaming = thinking_mode and on_reasoning_delta is not None

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请修正以下 {len(enriched_failed)} 个失败组件。"
                f"只输出 JSON 数组，包含需要执行的修复工具动作。"
            ),
        },
    ]

    reply_text = ""
    reasoning = ""
    
    try:
        llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)
        if use_streaming:
            llm_result = await stream_llm(
                llm,
                messages,
                on_reasoning_delta=lambda delta: on_reasoning_delta("callback", delta),
            )
        else:
            llm_result = await invoke_llm(llm, messages)
        reply_text = llm_result.content
        reasoning = llm_result.reasoning
        logger.info(
            f"[callback_node] LLM 修正回复: {len(reply_text)} 字符, thinking={len(reasoning)}字符"
        )
    except Exception as e:
        logger.error(f"[callback_node] LLM 调用失败: {e}")
        model_error = classify_model_error(e)
        return {
            "retry_count": retry_count + 1,
            "component_retry_counts": comp_retries,
            "terminal_model_error": model_error,
            "error": model_error["user_message"],
            "status": "failed",
            "repair_audit": {
                "accepted": False,
                "reason": "模型服务故障，当前修复流程已终止",
                "model_error": model_error,
            },
        }

    # ── 5. 提取并执行修复工具动作 ──
    repair_actions = extract_repair_actions(reply_text)
    if not repair_actions and reasoning:
        repair_actions = extract_repair_actions(reasoning)
    if not repair_actions:
        logger.warning("[callback_node] 未能从 LLM 回复中提取修复工具动作")
        return {
            "retry_count": retry_count + 1,
            "component_retry_counts": comp_retries,
            "repair_audit": {
                "accepted": False,
                "reason": "模型未返回可解析的修复动作",
                "stop_reason": "no_action",
                "source_fingerprint": source_fingerprint,
            },
        }

    allowed_ids = {
        item.get("component_id") for item in enriched_failed
        if item.get("component_id") and not item.get("is_design_target")
    }
    related_ids = {
        related_id
        for item in enriched_failed
        for related_id in item.get("related_entity_ids", [])
        if related_id
    }
    allowed_ids.update(related_ids)
    allowed_add_types = {
        item.get("component_type") for item in enriched_failed
        if item.get("is_design_target") and item.get("component_type")
    }
    candidate, action_reports = execute_repair_actions(
        state.get("merged_blueprint", {}),
        repair_actions,
        allowed_entity_ids=allowed_ids,
        allowed_add_types=allowed_add_types,
        allowed_remove_ids=related_ids,
    )
    changed_ids = {
        report["entity_id"] for report in action_reports
        if report.get("success") and report.get("entity_id")
    }
    if not changed_ids:
        logger.warning("[callback_node] 模型动作均未通过修复工具白名单校验")
        if on_reasoning_delta:
            await on_reasoning_delta(
                "callback",
                f"\n没有可执行的定向修复动作，"
                f"{len(action_reports)} 个动作均被白名单拒绝。\n",
            )
        return {
            "retry_count": retry_count + 1,
            "component_retry_counts": comp_retries,
            "repair_audit": {
                "accepted": False,
                "reason": "没有成功执行的修复动作",
                "stop_reason": "no_change",
                "source_fingerprint": source_fingerprint,
                "actions": action_reports,
            },
        }
    if on_reasoning_delta:
        succeeded = [
            f"{report.get('tool')}({report.get('entity_id')})"
            for report in action_reports if report.get("success")
        ]
        rejected = sum(1 for report in action_reports if not report.get("success"))
        await on_reasoning_delta(
            "callback",
            "\n**定向修复工具执行**\n"
            f"- 已执行: {', '.join(succeeded)}\n"
            f"- 被白名单拒绝: {rejected}\n"
            "- 正在进行修复后全量复检...\n",
        )

    # before/after 使用完全相同的批准版本与完整只读门禁。
    after = evaluate_candidate(candidate, design_document=state.get("design_document"),
                               design_brief=state.get("design_brief"), source="callback")
    before_issues, after_issues = before["issues"], after["issues"]
    progress = compare_issue_sets(before_issues, after_issues)
    introduced_issues = progress["introduced_issues"]
    before_satisfied = set((before["fulfillment"] or {}).get("satisfied_ids") or [])
    after_satisfied = set((after["fulfillment"] or {}).get("satisfied_ids") or [])
    progress["accepted"] = (progress["accepted"] and not after_issues and not after["errors"]
                            and before_satisfied <= after_satisfied
                            and blueprint_fingerprint(candidate) != source_fingerprint)

    if not progress["accepted"]:
        logger.warning(
            "[callback_node] 修复动作未安全改善错误集合，回滚: "
            f"{len(before_issues)} → {len(after_issues)}, "
            f"新增={introduced_issues}"
        )
        if on_reasoning_delta:
            await on_reasoning_delta(
                "callback",
                f"完整门禁未通过：错误 {len(before_issues)} → {len(after_issues)}，"
                "本轮修改已回滚。\n",
            )
        return {
            "retry_count": retry_count + 1,
            "component_retry_counts": comp_retries,
            "repair_audit": {
                "accepted": False,
                "reason": "完整验收未通过或已满足项退化，候选已回滚",
                "stop_reason": "incomplete_candidate",
                "source_fingerprint": source_fingerprint,
                "candidate_fingerprint": blueprint_fingerprint(candidate),
                "before_issue_count": len(before_issues),
                "after_issue_count": len(after_issues),
                "introduced_issues": introduced_issues,
                "actions": action_reports,
            },
        }

    # ── 7. 把通过复检的完整候选蓝图与实体分片一起提交 ──
    updates = state_updates_from_candidate(state, candidate, changed_ids)
    if on_reasoning_delta:
        await on_reasoning_delta(
            "callback",
            f"复检通过：错误 {len(before_issues)} → {len(after_issues)}，"
            "本轮局部修改已提交。\n",
        )

    new_retry_count = retry_count + 1
    logger.info(
        f"[callback_node] 修正完成 ({new_retry_count}/{state.get('max_retries', 3)}): "
        f"执行了 {len(changed_ids)} 个实体的定向修复，"
        f"错误 {len(before_issues)} → {len(after_issues)}"
    )

    return {
        **updates,
        "retry_count": new_retry_count,
        "component_retry_counts": comp_retries,
        "validation_snapshot": after["snapshot"],
        "final_blueprint": candidate,
        "validation_results": after["snapshot"]["results"],
        "validation_issues": after_issues,
        "validation_error_count": after["snapshot"]["error_count"],
        "design_fulfillment": after["fulfillment"],
        "repair_audit": {
            "accepted": True,
            "source_fingerprint": source_fingerprint,
            "candidate_fingerprint": blueprint_fingerprint(candidate),
            "before_issue_count": len(before_issues),
            "after_issue_count": len(after_issues),
            "actions": action_reports,
        },
    }


