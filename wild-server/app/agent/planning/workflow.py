"""可审核计划层：研究、动态任务、结构化约束、审核与阶段验收。"""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from langgraph.types import interrupt
from loguru import logger

from app.agent.planning.execution import (
    build_execution_plan,
    validate_execution_plan,
)
from app.agent.planning.requirements import (
    blocking_acceptance_failures,
    compile_structured_requirements,
    evaluate_acceptance_results,
    initial_execution_progress,
    initialize_acceptance_results,
    update_dynamic_task_statuses,
    update_execution_progress,
    validate_structured_requirements,
)
from app.agent.state import GenerationState
from app.llm.invocation import invoke_llm, merge_token_usage
from app.llm.client import create_llm
from app.agent.prompts import build_execution_plan_prompt
from app.agent.runtime import (
    get_execution_feedback_poller,
    get_reasoning_callback,
)
from app.spec.loader import SpecQuery
from config import config
from app.utils.json_extractor import extract_json_object


async def planning_research(state: GenerationState) -> dict:
    """Plan 模式的只读研究节点；失败时保留可执行的本地能力清单。"""

    from app.services.agent_service import agent_service

    started = time.time()
    intent = str(state.get("intent") or "generate")
    user_message = str(state.get("user_message") or "")
    callback = get_reasoning_callback()
    if callback:
        await callback(
            "planning_research:progress",
            "\n### 计划研究\n正在读取任务目标、当前场景和可执行 WILD 规则；此阶段不会生成或修改三维。\n",
        )
    queries = [
        SpecQuery("当前引擎已实现的宿主、连接与空间解析关系", {"doc_type": "recipe", "entity_name": "supported_assembly_relations"}),
        SpecQuery("WILD 当前构件参数与能力边界", {"doc_type": "component", "topic": "parameters"}),
    ]
    if intent == "edit":
        queries = [
            SpecQuery(
                f"{user_message} ScenePatch 修改 坐标 字段 引用",
                {"doc_type": "blueprint_spec", "knowledge_role": "protocol"},
            ),
            SpecQuery(
                user_message,
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
        ]
    error = None
    coverage_diag = None
    try:
        context = agent_service.spec_loader.load_many(queries, per_query=2)
        # 本地知识覆盖判断：检索分片是否覆盖可执行能力与组装主题。
        # 结果仅记录在诊断中；联网决策由 web_research 分支（若启用）执行。
        from app.agent.knowledge.evidence_gate import evaluate_knowledge_coverage
        coverage_diag = evaluate_knowledge_coverage(
            user_message,
            state.get("building_type"),
            agent_service.spec_loader.last_results,
            coverage_threshold=config.web_research.coverage_threshold,
        ).to_dict()
    except Exception as exc:
        context = ""
        error = str(exc)
        logger.warning(f"[planning_research] RAG 失败，使用本地能力协议继续: {exc}")
    current_blueprint = state.get("current_blueprint")
    geometry = (
        current_blueprint.get("geometry", {})
        if isinstance(current_blueprint, dict)
        else {}
    )
    element_count = (
        len(geometry.get("elements", [])) if isinstance(geometry, dict) else 0
    )
    component_count = (
        len(geometry.get("components", [])) if isinstance(geometry, dict) else 0
    )
    summary = (
        f"知识上下文 {len(context)} 字；当前场景 {element_count} 个结构元素、"
        f"{component_count} 个组件"
    )
    if callback:
        await callback(
            "planning_research:progress",
            f"{summary}。下一步将生成可审核的结构化执行计划。\n",
        )
    # 覆盖不足时，把缺失主题转成研究问题交给 web_research 节点（仅本次 request）。
    research_queries: list[str] = []
    research_missing_topics: list[str] = []
    if coverage_diag and coverage_diag.get("trigger_web_research"):
        research_missing_topics = list(coverage_diag["missing_topics"])
        research_queries = [
            f"建筑 {topic} 完整构成 规范 组装" for topic in research_missing_topics[:3]
        ]

    return {
        "plan_research_context": context[:6000],
        "plan_research_summary": summary,
        "plan_research_diag": {
            "rag_chars": len(context),
            "rag_error": error,
            "element_count": element_count,
            "component_count": component_count,
            "coverage": coverage_diag,
            "total_ms": int((time.time() - started) * 1000),
        },
        "research_queries": research_queries,
        "research_missing_topics": research_missing_topics,
        "web_research_context": "",
        "web_research_diag": None,
    }


async def execution_planner(state: GenerationState) -> dict:
    """让模型规划本次业务任务，再编译为节点可消费和可验收的要求。"""

    intent = str(state.get("intent") or "generate")
    callback = get_reasoning_callback()
    feedback = str(state.get("plan_feedback") or "").strip()
    previous = (
        state.get("execution_plan")
        if isinstance(state.get("execution_plan"), dict)
        else None
    )
    if callback:
        action = "根据用户意见重新制定" if feedback else "开始制定"
        await callback(
            "planner:progress",
            f"\n### 动态执行计划\n{action}本次建筑专属任务、阶段映射与验收条件...\n",
        )

    # 网络研究临时上下文只对本次请求生效；追加到研究上下文，供计划制定参考。
    web_context = str(state.get("web_research_context") or "").strip()
    research_text = str(state.get("plan_research_context") or "")
    if web_context:
        research_text = (
            research_text
            + chr(10) + "# 网络补充知识（临时，来源见链接；仅本次请求参考）" + chr(10) + web_context
        )
    prompt = build_execution_plan_prompt(
        intent=intent,
        user_message=str(state.get("user_message") or ""),
        research_context=research_text,
        current_scene_summary=str(state.get("plan_research_summary") or ""),
        feedback=feedback,
        previous_tasks=(previous or {}).get("dynamic_tasks", []),
    )
    raw_payload: dict[str, Any] | None = None
    planner_error = None
    token_usage = None
    recovery_diag = None
    started = time.time()
    try:
        llm_result = await invoke_llm(
            create_llm(enable_thinking=False, streaming=False),
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": str(state.get("user_message") or "")},
            ],
        )
        parsed = extract_json_object(llm_result.content)
        raw_payload = parsed if isinstance(parsed, dict) else None
        token_usage = llm_result.token_usage
        # 模型有时返回格式不标准的 JSON（缺括号、多余文本）
        if raw_payload is None:
            from app.llm.recovery import recover_single_json

            # 再次调用 LLM，专门修复格式
            recovered, recovery_diag = await recover_single_json(
                prompt,
                str(state.get("user_message") or ""),
                llm_result.content,
                object_hint="包含 tasks 数组的执行计划 JSON 对象",
                extra_instruction=(
                    "- 顶层必须直接包含 tasks 数组；\n"
                    "- 每个 task 必须包含 title、phase、objective。"
                ),
            )
            if isinstance(recovered, dict):
                raw_payload = recovered
            token_usage = merge_token_usage(
                token_usage,
                (recovery_diag or {}).get("token_usage"),
            )
            if raw_payload is not None:
                logger.warning("[execution_planner] 执行计划定向格式恢复成功")
    except Exception as exc:
        planner_error = str(exc)
        logger.warning(f"[execution_planner] 模型计划失败，已阻断: {exc}")
        from app.llm.errors import model_failure_result
        block = model_failure_result(exc)
        return {
            **block,
            "execution_plan_status": "failed",
            "execution_plan_review_status": "rejected",
            "execution_plan_diag": {
                "source": "model_service_failure",
                "task_count": 0,
                "error": planner_error,
                "total_ms": int((time.time() - started) * 1000),
            },
            "plan_feedback_pending": False,
        }

    # 把 LLM 的原始输出（可能不规范）转换成标准的 ExecutionPlan 对象。
    plan = build_execution_plan(
        request_id=str(state.get("request_id") or "unknown"),
        intent=intent,
        user_message=str(state.get("user_message") or ""),
        research_summary=str(state.get("plan_research_summary") or ""),
        feedback=feedback,
        previous_plan=previous,
        planned_tasks=(raw_payload or {}).get("tasks"),
        planner_source="llm",
        planner_summary=str((raw_payload or {}).get("summary") or ""),
    )
    requirements = compile_structured_requirements(plan)
    acceptance_results = initialize_acceptance_results(requirements)
    progress = initial_execution_progress(
        intent,
        str(state.get("plan_research_summary") or ""),
    )
    if plan.get("planner_source") == "fallback" and planner_error is None:
        planner_error = "模型计划缺少必要任务或包含不受支持的阶段"
    if callback:
        source_label = "模型动态规划" if plan["planner_source"] == "llm" else "确定性语义回退"
        task_lines = [
            f"- {task['title']} → {task['phase']}：{task['objective']}"
            for task in plan.get("dynamic_tasks", [])
        ]
        await callback(
            "planner:progress",
            f"已通过{source_label}生成计划 v{plan['version']}，"
            f"包含 {len(plan['dynamic_tasks'])} 项本次任务。\n"
            + "\n".join(task_lines)
            + "\n动态任务已编译为结构化业务要求；固定安全主流程仍由 LangGraph 管理。\n",
        )
    history = list(state.get("execution_plan_history") or [])
    if isinstance(previous, dict):
        history.append(
            {
                "version": previous.get("version"),
                "status": previous.get("status"),
                "feedback": str(state.get("plan_feedback") or ""),
            }
        )
    return {
        "execution_plan": plan,
        "structured_requirements": requirements,
        "acceptance_results": acceptance_results,
        "execution_progress": progress,
        "execution_plan_status": "draft",
        "execution_plan_review_status": "pending",
        "execution_plan_history": history,
        "execution_plan_diag": {
            "source": plan.get("planner_source"),
            "task_count": len(plan.get("dynamic_tasks", [])),
            "prompt_chars": len(prompt),
            "token_usage": token_usage,
            "recovery": recovery_diag,
            "error": planner_error,
            "total_ms": int((time.time() - started) * 1000),
        },
        "plan_feedback": "",
        "plan_feedback_pending": False,
    }


def execution_plan_validator(state: GenerationState) -> dict:
    """在人工审核前验证任务结构及其编译后的业务要求。"""

    terminal = state.get("terminal_model_error")
    if terminal:
        return {
            "terminal_model_error": terminal,
            "execution_plan_status": "failed",
            "execution_plan_validation": [{
                "code": "model_service_error",
                "message": str(terminal.get("user_message") or "模型服务不可用"),
            }],
            "error": str(terminal.get("user_message") or "模型服务不可用"),
        }

    intent = str(state.get("intent") or "generate")
    plan = deepcopy(state.get("execution_plan") or {})
    issues = validate_execution_plan(plan, intent)
    issues.extend(
        validate_structured_requirements(state.get("structured_requirements"))
    )
    # 只有 error 级问题才阻断整轮生成；warning 级问题（例如"要一张 2D 平面图"
    # 这类表现层差异、主观验收条件）挂到审核面板由人工裁决，不再终结流程。
    blocking = [issue for issue in issues if str(issue.get("severity") or "error") != "warning"]
    plan["valid"] = not blocking
    plan["status"] = "reviewing" if not blocking else "failed"
    return {
        "execution_plan": plan,
        "structured_requirements": state.get("structured_requirements") or [],
        "acceptance_results": state.get("acceptance_results") or {},
        "execution_progress": state.get("execution_progress") or {},
        "execution_plan_status": plan["status"],
        "execution_plan_validation": issues,
        "error": (
            "执行计划校验失败：" + "；".join(issue["message"] for issue in blocking[:6])
            if blocking
            else None
        ),
    }


def execution_plan_review(state: GenerationState) -> dict:
    """持久化暂停；批准前所有 mutate 能力都不可执行。"""

    plan = deepcopy(state.get("execution_plan") or {})
    if not plan.get("valid"):
        return {
            "execution_plan_status": "failed",
            "execution_plan_review_status": "rejected",
            "error": state.get("error") or "执行计划未通过校验",
        }
    decision = interrupt(
        {
            "type": "execution_plan_review",
            "question": "请审核动态执行计划，然后在恢复输入中批准或提出修改意见。",
            "plan": plan,
            "structured_requirements": state.get("structured_requirements") or [],
            "acceptance_results": state.get("acceptance_results") or {},
            "execution_progress": state.get("execution_progress") or {},
            "version": int(plan.get("version") or 1),
            "resume_examples": {
                "confirm": {"action": "confirm"},
                "revise": {
                    "action": "revise",
                    "feedback": "请填写需要修改的计划内容",
                },
            },
        }
    )
    action = str(decision.get("action") if isinstance(decision, dict) else "").lower()
    feedback = str(
        decision.get("feedback") if isinstance(decision, dict) else ""
    ).strip()
    if action == "confirm":
        plan["status"] = "approved"
        plan["review_status"] = "approved"
        return {
            "execution_plan": plan,
            "structured_requirements": state.get("structured_requirements") or [],
            "acceptance_results": state.get("acceptance_results") or {},
            "execution_progress": state.get("execution_progress") or {},
            "execution_plan_status": "approved",
            "execution_plan_review_status": "approved",
            "plan_feedback": "",
            "plan_feedback_pending": False,
        }
    if not feedback:
        feedback = "请重新检查计划目标、步骤依赖和验收条件，并生成新版计划。"
    plan["status"] = "revising"
    plan["review_status"] = "revise"
    return {
        "execution_plan": plan,
        "structured_requirements": state.get("structured_requirements") or [],
        "acceptance_results": state.get("acceptance_results") or {},
        "execution_progress": state.get("execution_progress") or {},
        "execution_plan_status": "revising",
        "execution_plan_review_status": "revise",
        "plan_feedback": feedback,
    }


def route_execution_plan_review(state: GenerationState) -> str:
    if state.get("execution_plan_review_status") == "approved":
        # 生成分支直达 architecture；编辑分支由 patch 节点产出可审核的 ScenePatch。
        return "patch" if state.get("intent") == "edit" else "architecture"
    if state.get("execution_plan_status") == "failed":
        return "__end__"
    return "planner"


_STAGE_RESULTS = {
    "architecture": ("architecture_plan", "总体体量、功能层次与立面意图已确定"),
    "material_plan": ("material_plan", "材质角色和资产解析完成"),
    "design_review": ("design_document", "建筑设计已批准"),
    "skeleton": ("skeleton_blueprint", "主体骨架与组件建议已完成"),
    "merge": ("merged_blueprint", "Blueprint 已合并"),
    "final_validate": ("final_blueprint", "最终校验零错误"),
    "patch": ("scene_patch", "ScenePatch 提案已生成，等待用户应用"),
}


async def _poll_execution_feedback(state: GenerationState) -> dict[str, Any]:
    """在业务阶段边界吸收追加意见，但不再承担业务节点调度。"""

    poller = get_execution_feedback_poller()
    if poller is None:
        return {"plan_feedback_pending": False}
    pending = [str(item).strip() for item in await poller() if str(item).strip()]
    if not pending:
        return {"plan_feedback_pending": False}

    replan_count = int(state.get("plan_replan_count") or 0)
    max_replans = max(0, int(state.get("max_plan_replans") or 3))
    if replan_count >= max_replans:
        return {
            "plan_feedback_pending": False,
            "execution_plan_status": "failed",
            "status": "failed",
            "error": f"执行计划已达到最大重规划次数 {max_replans}",
        }
    return {
        "plan_feedback_pending": True,
        "execution_plan_status": "revising",
        "execution_plan_review_status": "revise",
        "plan_feedback": "；".join(pending),
        "plan_replan_count": replan_count + 1,
    }


async def complete_execution_stage(
    state: GenerationState,
    stage: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """记录固定阶段进度并执行逐条业务验收；返回值不决定正常节点顺序。"""

    plan = state.get("execution_plan")
    if not state.get("plan_mode") or not isinstance(plan, dict):
        return {}

    result_ref, success_detail = _STAGE_RESULTS.get(stage, (None, "执行完成"))
    success = not result.get("error") and result.get("status") != "failed"
    if result_ref:
        success = success and isinstance(result.get(result_ref), dict)
    if stage == "final_validate":
        success = (
            success
            and result.get("status") == "complete"
            and int(result.get("validation_error_count") or 0) == 0
        )

    detail = success_detail if success else str(result.get("error") or f"{stage} 执行失败")

    # 更新节点进度
    progress = update_execution_progress(
        state.get("execution_progress"),
        stage,
        "completed" if success else "failed",
        result_ref=result_ref if success else None,
        detail=detail,
    )
    if stage == "merge":
        progress = update_execution_progress(
            progress,
            "component_generation",
            "completed" if success else "failed",
            result_ref="component_fragments" if success else None,
            detail="动态组件已生成并参与合并" if success else "动态组件生成或合并失败",
        )

    acceptance_results = evaluate_acceptance_results(
        state=state,
        result=result,
        phase=stage,
    )
    updated_plan = update_dynamic_task_statuses(
        plan,
        acceptance_results,
        progress,
        state.get("structured_requirements"),
    )
    updated_plan["status"] = "executing" if success else "failed"
    payload: dict[str, Any] = {
        "execution_plan": updated_plan,
        "structured_requirements": state.get("structured_requirements") or [],
        "execution_plan_status": updated_plan["status"],
        "acceptance_results": acceptance_results,
        "execution_progress": progress,
        "plan_feedback_pending": False,
    }

    if stage in {"final_validate", "patch"} and success:
        failures = blocking_acceptance_failures(
            state.get("structured_requirements"),
            acceptance_results,
        )
        if failures:
            message = "；".join(str(item.get("message") or item.get("acceptance_id")) for item in failures[:6])
            updated_plan["status"] = "failed"
            payload.update({
                "execution_plan": updated_plan,
                "execution_plan_status": "failed",
                "error": "业务验收未通过：" + message,
                "status": "failed",
            })
            if stage == "final_validate":
                payload["final_blueprint"] = None
            return payload
        updated_plan["status"] = "completed"
        payload.update(
            {
                "execution_plan": updated_plan,
                "execution_plan_status": "completed",
            }
        )

    if not success:
        return payload

    feedback_update = await _poll_execution_feedback(state)
    if feedback_update.get("execution_plan_status") == "failed":
        updated_plan["status"] = "failed"
        feedback_update["execution_plan"] = updated_plan
    elif feedback_update.get("plan_feedback_pending"):
        updated_plan["status"] = "revising"
        feedback_update["execution_plan"] = updated_plan
    payload.update(feedback_update)
    return payload
