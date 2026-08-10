"""
Layer 2 扩展: 回调重试节点

校验失败后，对每个失败组件做精准修正：
  结构化错误 + RAG + 工具数据 → LLM 选择白名单修复工具 → 程序执行并复检

这是 LangGraph 架构中最关键的创新点，详见设计文档 03-回调与重试机制.md。
"""
from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.prompts import build_callback_prompt
from app.agent.model_client import create_llm
from app.agent.component_registry import COMPONENT_REGISTRY
from app.agent.repair_tools import execute_repair_actions, extract_repair_actions
from app.agent.validation_issues import compare_issue_sets, validation_issues_from_results
from app.spec.loader import SpecQuery


# 模块级导入
from app.services.agent_service import agent_service


async def callback_node(state: GenerationState) -> dict:
    """对校验失败的组件进行精确修正重试

    流程:
    1. 从 failed_components 提取失败信息（含 current_params）
    2. 精准 RAG（按错误类型检索）
    3. 运行组件工具获取空间约束数据（tools 提供"具体错在哪里"）
    4. 构建 callback_payload（含骨架上下文 + 当前参数 + 工具建议 + RAG）
    5. LLM 只输出白名单修复动作（支持流式思考）
    6. 程序执行动作并用全量校验比较错误数
    7. 仅在错误数下降时提交到对应 fragments
    """
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
    on_reasoning_delta = state.get("on_reasoning_delta")

    # ── 1. 精准 RAG + 工具数据（按失败组件类型检索）──
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

    spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
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

            # 构建只包含该组件的临时 blueprint
            temp_bp = {
                "meta": skeleton_blueprint.get("meta", {"version": "1.1", "type": "building"}),
                "geometry": {
                    "elements": skeleton_blueprint.get("geometry", {}).get("elements", []).copy(),
                    "components": [fc.get("current_params", {})] if fc.get("current_params") else [],
                },
                "materials": skeleton_blueprint.get("materials", {}),
            }
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
    llm = create_llm(enable_thinking=thinking_mode, streaming=use_streaming)

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
        if use_streaming:
            # 流式调用：实时推送思考内容
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "additional_kwargs"):
                    reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
                    if reasoning_delta:
                        reasoning += reasoning_delta
                        await on_reasoning_delta("callback", reasoning_delta)
                
                if hasattr(chunk, "content") and chunk.content:
                    reply_text += chunk.content
            
            logger.info(f"[callback_node] LLM 流式修正完成: {len(reply_text)} 字符, thinking={len(reasoning)}字符")
        else:
            # 非流式调用
            response = await llm.ainvoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)
            if hasattr(response, "additional_kwargs"):
                reasoning = response.additional_kwargs.get("reasoning_content", "") or ""
            if not reasoning and hasattr(response, "response_metadata"):
                reasoning = response.response_metadata.get("reasoning_content", "") or ""
            logger.info(f"[callback_node] LLM 修正回复: {len(reply_text)} 字符")
    except Exception as e:
        logger.error(f"[callback_node] LLM 调用失败: {e}")
        return {"retry_count": retry_count + 1}

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

    # ── 6. 全量复检；错误没有严格减少就回滚（candidate 尚未写回 state）──
    from app.services.agent_service import _final_errors, run_validation_pipeline

    before_issues = list(state.get("validation_issues", []))
    if not before_issues:
        before_issues = validation_issues_from_results(
            [
                result for result in state.get("validation_results", [])
                if result.get("has_error")
            ],
            state.get("merged_blueprint", {}),
        )
    candidate_results = run_validation_pipeline(candidate)
    candidate_errors = _final_errors(candidate_results)
    after_issues = validation_issues_from_results(candidate_errors, candidate)
    from app.agent.nodes.merge_node import _validate_design_brief_constraints
    after_design_errors = _validate_design_brief_constraints(
        candidate,
        state.get("design_brief"),
    )
    if after_design_errors:
        after_issues.extend(validation_issues_from_results([{
            "name": "validate_design_brief",
            "output": "\n".join(
                f"❌ [design] {message}" for message in after_design_errors
            ),
            "has_error": True,
        }], candidate))
    progress = compare_issue_sets(before_issues, after_issues)
    introduced_issues = progress["introduced_issues"]

    if not progress["accepted"]:
        logger.warning(
            "[callback_node] 修复动作未安全改善错误集合，回滚: "
            f"{len(before_issues)} → {len(after_issues)}, "
            f"新增={introduced_issues}"
        )
        if on_reasoning_delta:
            await on_reasoning_delta(
                "callback",
                f"复检未改善：错误 {len(before_issues)} → {len(after_issues)}，"
                "本轮修改已回滚。\n",
            )
        return {
            "retry_count": retry_count + 1,
            "component_retry_counts": comp_retries,
            "repair_audit": {
                "accepted": False,
                "reason": "复检错误数没有严格下降或引入了新错误，已回滚",
                "before_issue_count": len(before_issues),
                "after_issue_count": len(after_issues),
                "introduced_issues": introduced_issues,
                "actions": action_reports,
            },
        }

    # ── 7. 只把通过复检的实体写回骨架/组件分片，下一轮 merge 会重新提交 ──
    updates = _state_updates_from_candidate(state, candidate, changed_ids)
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
        "repair_audit": {
            "accepted": True,
            "before_issue_count": len(before_issues),
            "after_issue_count": len(after_issues),
            "actions": action_reports,
        },
    }


def _state_updates_from_candidate(
    state: GenerationState,
    candidate: dict,
    changed_ids: set[str],
) -> dict:
    """把候选蓝图中通过复检的实体同步回下一轮 merge 的源分片。"""
    from copy import deepcopy

    geometry = candidate.get("geometry", {})
    candidate_entities = {
        entity["id"]: entity
        for entity in [
            *geometry.get("elements", []),
            *geometry.get("components", []),
        ]
        if isinstance(entity, dict) and entity.get("id") in changed_ids
    }
    updates: dict = {}

    skeleton = deepcopy(state.get("skeleton_blueprint", {}))
    skeleton_changed = False
    skeleton_geometry = skeleton.get("geometry", {})
    for bucket in ("elements", "components"):
        items = skeleton_geometry.get(bucket, [])
        new_items = []
        for item in items:
            entity_id = item.get("id") if isinstance(item, dict) else None
            if entity_id in candidate_entities:
                new_items.append(deepcopy(candidate_entities[entity_id]))
                skeleton_changed = True
            elif entity_id in changed_ids:
                # changed_ids 中不存在于 candidate 的实体已被受限 remove_entity 删除。
                skeleton_changed = True
            else:
                new_items.append(item)
        if skeleton_changed:
            skeleton_geometry[bucket] = new_items
    existing_skeleton_ids = {
        item.get("id")
        for bucket in ("elements", "components")
        for item in skeleton_geometry.get(bucket, [])
        if isinstance(item, dict) and item.get("id")
    }
    candidate_element_ids = {
        item.get("id")
        for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }
    registered_types = {
        config.component_type for config in COMPONENT_REGISTRY.values()
        if config.implemented
    }
    for entity_id in changed_ids & candidate_element_ids:
        entity = candidate_entities[entity_id]
        if entity_id not in existing_skeleton_ids and entity.get("type") not in registered_types:
            skeleton_geometry.setdefault("elements", []).append(
                deepcopy(entity)
            )
            skeleton_changed = True
    if skeleton_changed:
        updates["skeleton_blueprint"] = skeleton

    for config in COMPONENT_REGISTRY.values():
        if not config.implemented:
            continue
        old_value = state.get(config.output_key)
        matching_entities = [
            entity for entity in candidate_entities.values()
            if entity.get("type") == config.component_type
        ]
        if config.is_list:
            old_list = old_value if isinstance(old_value, list) else []
            new_value = []
            changed = False
            old_ids = {
                fragment.get("id") for fragment in old_list
                if isinstance(fragment, dict) and fragment.get("id")
            }
            for fragment in old_list:
                entity_id = fragment.get("id") if isinstance(fragment, dict) else None
                if entity_id in candidate_entities:
                    new_value.append(deepcopy(candidate_entities[entity_id]))
                    changed = True
                elif entity_id in changed_ids:
                    changed = True
                else:
                    new_value.append(fragment)
            for entity in matching_entities:
                if entity.get("id") not in old_ids:
                    new_value.append(deepcopy(entity))
                    changed = True
            if changed:
                updates[config.output_key] = new_value
        elif not config.is_list:
            if isinstance(old_value, dict) and old_value.get("id") in candidate_entities:
                updates[config.output_key] = deepcopy(candidate_entities[old_value["id"]])
            elif isinstance(old_value, dict) and old_value.get("id") in changed_ids:
                updates[config.output_key] = None
            elif matching_entities:
                updates[config.output_key] = deepcopy(matching_entities[0])

    return updates
