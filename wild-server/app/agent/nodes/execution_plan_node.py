"""Claude 风格计划层：只读研究、结构化计划、审核与白名单执行路由。"""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from langgraph.types import interrupt
from loguru import logger

from app.agent.execution_plan import (
    CAPABILITY_REGISTRY,
    build_execution_plan,
    next_ready_step,
    plan_is_complete,
    reset_plan_from,
    update_plan_step,
    validate_execution_plan,
)
from app.agent.graph_state import GenerationState
from app.agent.runtime_context import (
    get_execution_feedback_poller,
    get_reasoning_callback,
)
from app.spec.loader import SpecQuery


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
            "\n### 计划研究\n正在读取任务目标、当前场景和相关建筑知识；此阶段不会生成或修改三维。\n",
        )
    queries = [
        SpecQuery(user_message, {"doc_type": "building_type"}),
        SpecQuery(user_message, {"doc_type": "recipe"}),
    ]
    if intent == "edit":
        queries = [
            SpecQuery(
                f"{user_message} ScenePatch 修改 约束 引用", {"doc_scope": "editing"}
            ),
            SpecQuery(user_message, {"doc_type": "component"}),
        ]
    error = None
    try:
        context = agent_service.spec_loader.load_many(queries, per_query=2)
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
    return {
        "plan_research_context": context[:6000],
        "plan_research_summary": summary,
        "plan_research_diag": {
            "rag_chars": len(context),
            "rag_error": error,
            "element_count": element_count,
            "component_count": component_count,
            "total_ms": int((time.time() - started) * 1000),
        },
    }


async def execution_planner(state: GenerationState) -> dict:
    """依据分类结果和总体方案生成可审核计划，不允许产生任意节点。"""

    intent = str(state.get("intent") or "generate")
    plan = build_execution_plan(
        request_id=str(state.get("request_id") or "unknown"),
        intent=intent,
        user_message=str(state.get("user_message") or ""),
        architecture_plan=(
            state.get("architecture_plan")
            if isinstance(state.get("architecture_plan"), dict)
            else None
        ),
        research_summary=str(state.get("plan_research_summary") or ""),
        feedback=str(state.get("plan_feedback") or ""),
        previous_plan=(
            state.get("execution_plan")
            if isinstance(state.get("execution_plan"), dict)
            else None
        ),
    )
    callback = get_reasoning_callback()
    if callback:
        await callback(
            "planner:progress",
            f"已生成执行计划 v{plan['version']}，共 {len(plan['steps'])} 步；"
            "计划只引用服务端白名单能力，正在执行确定性校验。\n",
        )
    history = list(state.get("execution_plan_history") or [])
    previous = state.get("execution_plan")
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
        "execution_plan_status": "draft",
        "execution_plan_review_status": "pending",
        "execution_plan_history": history,
        "plan_feedback": "",
        "current_plan_step_id": "",
        "plan_next_node": "",
    }


def execution_plan_validator(state: GenerationState) -> dict:
    """在人工审核前验证白名单、依赖图和建筑必要步骤。"""

    intent = str(state.get("intent") or "generate")
    plan = deepcopy(state.get("execution_plan") or {})
    issues = validate_execution_plan(plan, intent)
    plan["validation_issues"] = issues
    plan["valid"] = not issues
    plan["status"] = "reviewing" if not issues else "failed"
    return {
        "execution_plan": plan,
        "execution_plan_status": plan["status"],
        "execution_plan_validation": issues,
        "error": (
            "执行计划校验失败：" + "；".join(issue["message"] for issue in issues[:6])
            if issues
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
            "plan": plan,
            "version": int(plan.get("version") or 1),
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
            "execution_plan_status": "approved",
            "execution_plan_review_status": "approved",
            "plan_feedback": "",
        }
    if not feedback:
        feedback = "请重新检查计划目标、步骤依赖和验收条件，并生成新版计划。"
    plan["status"] = "revising"
    plan["review_status"] = "revise"
    return {
        "execution_plan": plan,
        "execution_plan_status": "revising",
        "execution_plan_review_status": "revise",
        "plan_feedback": feedback,
    }


def route_execution_plan_review(state: GenerationState) -> str:
    if state.get("execution_plan_review_status") == "approved":
        return "plan_executor"
    if state.get("execution_plan_status") == "failed":
        return "__end__"
    return "architecture" if state.get("intent") == "generate" else "planner"


async def execution_plan_executor(state: GenerationState) -> dict:
    """在节点边界吸收用户意见，并选择下一条依赖已满足的白名单步骤。"""

    plan = deepcopy(state.get("execution_plan") or {})
    poller = get_execution_feedback_poller()
    pending_feedback: list[str] = []
    if poller is not None:
        pending_feedback = [
            str(item).strip() for item in await poller() if str(item).strip()
        ]
    if pending_feedback:
        replan_count = int(state.get("plan_replan_count") or 0)
        max_replans = max(0, int(state.get("max_plan_replans") or 3))
        if replan_count >= max_replans:
            plan["status"] = "failed"
            return {
                "execution_plan": plan,
                "execution_plan_status": "failed",
                "plan_next_node": "__end__",
                "error": f"执行计划已达到最大重规划次数 {max_replans}",
            }
        feedback = "；".join(pending_feedback)
        plan["status"] = "revising"
        return {
            "execution_plan": plan,
            "execution_plan_status": "revising",
            "execution_plan_review_status": "revise",
            "plan_feedback": feedback,
            "plan_replan_count": replan_count + 1,
            "plan_next_node": (
                "architecture" if state.get("intent") == "generate" else "planner"
            ),
            "current_plan_step_id": "",
        }

    if any(
        isinstance(step, dict) and step.get("status") == "failed"
        for step in plan.get("steps", [])
    ):
        plan["status"] = "failed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "failed",
            "plan_next_node": "__end__",
            "error": state.get("error") or "执行计划存在失败步骤",
        }
    if plan_is_complete(plan):
        plan["status"] = "completed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "completed",
            "plan_next_node": "__end__",
            "current_plan_step_id": "",
        }
    step = next_ready_step(plan)
    if step is None:
        plan["status"] = "failed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "failed",
            "plan_next_node": "__end__",
            "error": "执行计划没有可运行步骤，可能存在未满足依赖",
        }
    capability = CAPABILITY_REGISTRY.get(str(step.get("type") or ""))
    if capability is None or str(step.get("node") or "") != capability.node:
        plan["status"] = "failed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "failed",
            "plan_next_node": "__end__",
            "error": "执行计划引用了未注册能力",
        }
    plan = update_plan_step(
        plan,
        capability.type,
        "in_progress",
        detail=f"正在执行：{capability.label}",
    )
    plan["status"] = "executing"
    return {
        "execution_plan": plan,
        "execution_plan_status": "executing",
        "plan_next_node": capability.node,
        "current_plan_step_id": str(step.get("id") or ""),
    }


def route_execution_plan_executor(state: GenerationState) -> str:
    return str(state.get("plan_next_node") or "__end__")


def complete_execution_step(
    state: GenerationState,
    step_type: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """把业务节点结果映射回计划状态；建筑结果本身仍由原节点负责。"""

    plan = state.get("execution_plan")
    if not state.get("plan_mode") or not isinstance(plan, dict):
        return {}
    success = not result.get("error") and result.get("status") != "failed"
    detail = "执行完成"
    result_ref = None
    if step_type == "floor_plan_design":
        success = isinstance(result.get("floor_plan"), dict)
        detail = f"已生成平面；{len(result.get('floor_plan_validation', []))} 项待处理"
        result_ref = "floor_plan"
    elif step_type == "floor_plan_review":
        approved = result.get("floor_plan_review_status") == "approved"
        if not approved:
            return {
                "execution_plan": reset_plan_from(plan, "floor_plan_design"),
                "current_plan_step_id": "",
            }
        success = True
        detail = "用户已确认平面"
    elif step_type == "style_review":
        approved = result.get("style_review_status") == "approved"
        if not approved:
            return {
                "execution_plan": reset_plan_from(plan, "style_review"),
                "current_plan_step_id": "",
            }
        success = True
        detail = f"用户已确认风格：{result.get('style_package_id', '')}"
    elif step_type == "skeleton":
        success = result.get("deterministic_body_complete") is True and not result.get(
            "error"
        )
        detail = (
            "确定性主体与 G1-G6 已完成"
            if success
            else str(result.get("error") or "主体装配未完成")
        )
        result_ref = "skeleton_blueprint"
    elif step_type == "decor_assembly":
        detail = (
            "Decor IR 与 G7 已完成"
            if success
            else str(result.get("error") or "装饰装配失败")
        )
        result_ref = "decor_ir"
    elif step_type == "merge":
        success = isinstance(result.get("merged_blueprint"), dict) and not result.get(
            "error"
        )
        detail = (
            "Blueprint 已合并" if success else str(result.get("error") or "合并失败")
        )
        result_ref = "merged_blueprint"
    elif step_type == "final_validate":
        success = (
            result.get("status") == "complete"
            and int(result.get("validation_error_count") or 0) == 0
        )
        detail = (
            "最终校验零错误" if success else str(result.get("error") or "最终校验失败")
        )
        result_ref = "final_blueprint"
    elif step_type == "patch":
        success = isinstance(result.get("scene_patch"), dict) and not result.get(
            "error"
        )
        detail = (
            "ScenePatch 提案已生成，等待用户应用"
            if success
            else str(result.get("error") or "修改提案失败")
        )
        result_ref = "scene_patch"
    elif step_type == "material_plan":
        success = isinstance(result.get("material_plan"), dict) and not result.get(
            "error"
        )
        detail = (
            "材质角色和资产解析完成"
            if success
            else str(result.get("error") or "材质方案失败")
        )
        result_ref = "material_plan"

    updated = update_plan_step(
        plan,
        step_type,
        "completed" if success else "failed",
        detail=detail,
        result_ref=result_ref,
    )
    return {
        "execution_plan": updated,
        "execution_plan_status": "executing" if success else "failed",
        "current_plan_step_id": "",
    }
