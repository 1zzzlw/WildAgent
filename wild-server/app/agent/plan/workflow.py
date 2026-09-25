"""plan 驱动链的三个业务节点：plan / execute / replanner。

与既有节点同一套写法（对照 ``generation/material_workflow.py``、``validation/workflow.py``）：

- 节点先通过 ``get_reasoning_callback()`` 播报"正在做什么"，前端才有思考流可看；
- 节点写回 ``<node>_diag`` 诊断（耗时 / 模型调用 / 关键计数），供审计与回归断言；
- ``plan`` 用一次模型调用决定批次与并发策略，程序确定性展开；其余模型调用只发生在
  ``execute`` 的 generate/repair 条目，以及 ``replanner`` 首次异常调整（§5.1）。

关于 ``plan_diag`` / ``execute_diag`` / ``replanner_diag``：它们是**旁路观测**（§2.8 第 ③ 层），
由 ``ws_agent`` 从流式节点输出读取并交给 `record_node_call` / `all_diags`。它们**故意不**
声明在 ``GenerationState`` 里，所以 LangGraph 不会把它们写进 checkpoint——
权威事实只有 ``plan`` / ``plan_events`` / ``current_item_id`` / ``tool_trace`` 四项。

``nodes/*.py`` 里对应的是薄入口，真正的逻辑在本模块。
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from loguru import logger

from app.agent.plan.contracts import PlanDocument, PlanItem
from app.agent.plan.expand import expand_plan
from app.agent.plan.handlers import HANDLERS
from app.agent.plan.reconcile import ensure_artifact_consistency, reconcile
from app.agent.plan.replan import (
    MAX_NO_PROGRESS_ROUNDS,
    plan_needs_replan,
    prepare_finalization,
    request_replan,
    replan,
)
from app.agent.plan.store import (
    mark_running,
    poll_runnable,
    record_result,
    refresh_statuses,
    terminal_stats,
)
from app.agent.plan.strategy import request_plan_strategy
from app.agent.runtime import get_reasoning_callback

#: 哪些 op 的处理器会真的调模型（用于 §5.4 的模型调用预算统计）。
_MODEL_OPS: frozenset[str] = frozenset({"generate", "repair"})
_MAX_PARALLEL_ITEMS = 3


def _model_tool_rounds(trace: Any) -> int:
    """只数**模型自己发起**的工具轮次。

    预取检索与确定性校验也会进审计轨迹（它们带 ``mode`` 字段），但那些不产生模型
    调用；把它们也算进预算会让"检索充足"的请求提前触发预算终止。
    """

    return len(
        [entry for entry in trace or [] if isinstance(entry, dict) and not entry.get("mode")]
    )


def _plan_of(state: dict[str, Any]) -> PlanDocument:
    return PlanDocument.model_validate(state.get("plan") or {})


def _events_for(plan: PlanDocument) -> list[dict[str, Any]]:
    return [
        {
            "item_id": item.id,
            "label": item.label,
            "op": item.op,
            "kind": item.kind,
            "status": item.status,
            "evidence": item.run.evidence,
            "elapsed_ms": item.run.elapsed_ms,
        }
        for item in plan.items
    ]


def _runnable_batch(plan: PlanDocument) -> list[PlanItem]:
    """返回本轮可安全并发的生成条目；否则只返回声明顺序中的第一条。"""

    first = poll_runnable(plan)
    if first is None:
        return []
    group = str(first.params.get("parallel_group") or "")
    if (
        first.op != "generate"
        or first.params.get("execution_mode") != "parallel"
        or not group
    ):
        return [first]
    selected = [
        item
        for item in plan.items
        if item.status == "ready"
        and item.run.state != "succeeded"
        and item.op == "generate"
        and item.params.get("execution_mode") == "parallel"
        and item.params.get("parallel_group") == group
    ]
    return selected[:_MAX_PARALLEL_ITEMS] or [first]


def _merge_parallel_updates(results: list[dict[str, Any]]) -> dict[str, Any]:
    """合并互不依赖生成批次的局部 state 更新。"""

    merged: dict[str, Any] = {}
    for updates in results:
        for key, value in updates.items():
            if key in {"component_fragments", "component_diagnostics"}:
                current = merged.setdefault(key, {})
                if isinstance(current, dict) and isinstance(value, dict):
                    current.update(value)
            elif key not in merged:
                merged[key] = value
    return merged


async def _execute_one(state: dict[str, Any], item: PlanItem):
    handler = HANDLERS.get(item.op)
    handler_started = time.perf_counter()
    try:
        if handler is None:
            outcome = ({}, "failed", [], f"op {item.op!r} 没有执行器（见 §2.3 闭集）", [])
        else:
            outcome = handler(state, item)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        updates, run_state, artifacts, evidence, trace = outcome
    except Exception as exc:
        logger.error(f"[execute] {item.id} 执行异常: {exc}")
        updates, run_state, artifacts, evidence, trace = (
            {}, "failed", [], f"执行异常: {exc}", []
        )
    return (
        item,
        updates,
        run_state,
        artifacts,
        evidence,
        trace,
        int((time.perf_counter() - handler_started) * 1000),
    )


async def plan_node(state: dict[str, Any]) -> dict[str, Any]:
    """让模型根据批准方案决定分组策略，再由程序确定性展开条目。"""

    started = time.time()
    callback = get_reasoning_callback()
    if callback:
        await callback("plan", "正在把已批准方案拆成可执行的工作条目……\n")

    strategy, diag = await request_plan_strategy(state)

    if isinstance(diag.get("terminal_model_error"), dict):
        logger.warning("[plan] 策略模型不可用，终止本轮生成")
        return {
            "plan_diag": {**diag, "total_ms": int((time.time() - started) * 1000)},
            "terminal_model_error": diag["terminal_model_error"],
            "error": diag["terminal_model_error"].get("user_message")
            or diag.get("error")
            or "模型服务不可用",
            "status": "failed",
        }

    plan = expand_plan(state, strategy=strategy).add_llm_calls(1)
    stats = terminal_stats(plan)
    first = poll_runnable(plan)

    logger.info(
        f"[plan] 策略来源 {strategy.source}（{len(strategy.kinds)} 类构件）→ "
        f"展开 {stats['total']} 条条目（档位 {plan.detail_level}）："
        f"{[item.label for item in plan.items[:6]]}" + ("..." if stats["total"] > 6 else "")
    )
    if callback:
        unsupported = stats["unsupported"]
        parallel_groups = {
            entry.parallel_group
            for entry in strategy.kinds
            if entry.execution_mode == "parallel" and entry.parallel_group
        }
        batch_notes = [
            f"{entry.kind}：{entry.batch_reason}"
            for entry in strategy.kinds
            if entry.batch_reason
        ]
        await callback(
            "plan",
            f"计划已展开：{stats['total']} 条工作条目"
            + (f"，{len(parallel_groups)} 个安全并发组" if parallel_groups else "，其余按依赖串行")
            + (f"，其中 {unsupported} 条因能力缺失标记为不支持" if unsupported else "")
            + "。\n"
            + ("批次依据：" + "；".join(batch_notes) + "。\n" if batch_notes else ""),
        )

    return {
        "plan": plan.model_dump(mode="json"),
        "plan_events": _events_for(plan),
        "plan_diag": {
            **diag,
            "items": stats["total"],
            "terminal_stats": stats,
            "model_calls": 1,
            "total_ms": int((time.time() - started) * 1000),
        },
        "current_item_id": first.id if first is not None else None,
    }


async def execute_node(state: dict[str, Any]) -> dict[str, Any]:
    """执行一条串行任务，或执行一个由 plan 决定的安全并发组。"""

    started = time.time()
    plan = _plan_of(state)
    items = _runnable_batch(plan)
    if not items:
        logger.info("[execute] 没有可执行条目，交回 replanner")
        return {
            "current_item_id": None,
            "execute_diag": {"item_id": None, "reason": "无可执行条目"},
        }

    for item in items:
        plan, _running = mark_running(plan, item.id)
    logger.info(
        f"[execute] 本轮 {len(items)} 条："
        + ", ".join(f"{item.id}({item.kind})" for item in items)
    )

    callback = get_reasoning_callback()
    if callback and any(item.op in _MODEL_OPS for item in items):
        if len(items) > 1:
            await callback(
                "execute",
                "正在并发执行批次：" + "、".join(item.label for item in items) + "……\n",
            )
        else:
            await callback("execute", f"正在执行{items[0].label}（{items[0].id}）……\n")

    results = await asyncio.gather(*(_execute_one(state, item) for item in items))
    updates = _merge_parallel_updates([result[1] for result in results])
    tool_trace = dict(state.get("tool_trace") or {})
    item_results = []
    model_calls = 0
    for item, _item_updates, run_state, artifacts, evidence, trace, elapsed_ms in results:
        plan = record_result(
            plan,
            item.id,
            state=run_state,
            artifacts=artifacts,
            evidence=evidence,
            elapsed_ms=elapsed_ms,
            count_attempt=(run_state == "failed"),
        )
        calls = (1 + _model_tool_rounds(trace)) if item.op in _MODEL_OPS else 0
        model_calls += calls
        tool_trace[item.id] = trace
        item_results.append(
            {
                "item_id": item.id,
                "kind": item.kind,
                "run_state": run_state,
                "elapsed_ms": elapsed_ms,
                "evidence": evidence,
            }
        )
        logger.info(f"[execute] {item.id} → {run_state}（{elapsed_ms}ms）：{evidence}")
        if callback and item.op in _MODEL_OPS:
            await callback("execute", f"{item.label}：{run_state}（{evidence}）\n")
    plan.add_llm_calls(model_calls)

    first = items[0]
    total_tool_calls = sum(len(result[5]) for result in results)
    run_state = "succeeded" if all(result[2] == "succeeded" for result in results) else "mixed"

    return {
        **updates,
        "plan": plan.model_dump(mode="json"),
        "current_item_id": first.id,
        "tool_trace": tool_trace,
        "execute_diag": {
            "item_id": first.id,
            "item_ids": [item.id for item in items],
            "op": first.op,
            "kind": first.kind,
            "run_state": run_state,
            "elapsed_ms": max(result[6] for result in results),
            "tool_calls": total_tool_calls,
            "model_calls": model_calls,
            "parallel_count": len(items),
            "item_results": item_results,
            "llm_calls_total": plan.llm_calls,
            "total_ms": int((time.time() - started) * 1000),
        },
    }


async def replanner_node(state: dict[str, Any]) -> dict[str, Any]:
    """唯一的循环控制点：先确定性对账，只有异常才调一次模型（§5.1）。"""

    started = time.time()
    plan = _plan_of(state)

    plan, events = reconcile(plan, state)
    # 交付前必须重新对账：配额强制、阳台去重、fix_* 都会删改元素，漂移是静默的。
    plan = ensure_artifact_consistency(plan, state)

    diag: dict[str, Any] = {"reconciled_events": len(events)}

    # ── 异常分支：只有 failed / 永久 blocked 时才调模型，且只能在五个动作里选 ──
    if not plan.give_up and plan_needs_replan(plan):
        callback = get_reasoning_callback()
        problem = next(
            (
                item for item in plan.items
                if not item.is_terminal
                and (
                    item.run.state == "failed"
                    or (
                        item.status == "blocked"
                        and any(plan.item(dep) is None for dep in item.depends_on)
                    )
                )
            ),
            None,
        )
        if callback:
            if problem is not None:
                await callback(
                    "replanner",
                    f"条目 {problem.label or problem.id}（{problem.id}）执行失败 "
                    f"{problem.run.attempts}/{problem.run.max_attempts}："
                    f"{problem.run.evidence or '未提供失败证据'}。正在选择一次有界调整……\n",
                )
            else:
                await callback("replanner", "检测到计划结构异常，正在选择一次有界调整……\n")
        decision, replan_diag = await request_replan(plan, state)
        plan, outcome = replan(plan, state, decision)
        if replan_diag.get("model_called"):
            plan.add_llm_calls(1)
        diag["replan"] = {**replan_diag, "outcome": outcome}
        applied_action = str(outcome.get("action") or decision.action)
        applied_reason = str(outcome.get("reason") or decision.reason)
        logger.info(
            f"[replanner] 决策 {applied_action}（来源 {outcome.get('source') or decision.source}）："
            f"{outcome.get('rejected') or applied_reason}"
        )
        if callback:
            affected = outcome.get("item_ids") or []
            target = "、".join(str(item_id) for item_id in affected) or decision.item_id or "整份计划"
            changes = ", ".join(
                f"{key}={value}" for key, value in decision.params.items()
                if key in {"subtype", "guidance", "reason"}
            )
            detail = (
                outcome.get("rejected")
                or outcome.get("policy_override")
                or applied_reason
                or "未提供原因"
            )
            await callback(
                "replanner",
                f"计划调整：{applied_action}；目标：{target}；依据：{detail}"
                + (f"；变化：{changes}" if changes else "")
                + "。\n",
            )

    signature = plan.progress_signature()
    if signature == plan.last_progress_signature:
        plan.no_progress_rounds += 1
    else:
        plan.no_progress_rounds = 0
    plan.last_progress_signature = signature
    plan.iterations += 1
    plan = refresh_statuses(plan)

    # 到达任一停止条件时，只停止后续模型工作；批次 merge 与收尾 merge 必须继续，
    # 否则 final_validate 没有 merged_blueprint，只会把“有界退出”变成必现异常。
    budget = plan.budget or {}
    finalization_reason = ""
    if plan.give_up:
        finalization_reason = "replanner 已停止继续生成，转入确定性收尾"
    elif plan.iterations >= int(budget.get("iterations", 5)):
        finalization_reason = f"达到计划迭代上限 {plan.iterations}"
    elif plan.no_progress_rounds >= MAX_NO_PROGRESS_ROUNDS:
        finalization_reason = f"连续 {plan.no_progress_rounds} 轮无业务进展"
    elif plan.llm_budget_exhausted():
        finalization_reason = f"模型调用预算已用尽（{plan.llm_calls} 次）"
    if finalization_reason:
        plan, skipped = prepare_finalization(plan, reason=finalization_reason)
        diag["finalization"] = {
            "reason": finalization_reason,
            "skipped_item_ids": skipped,
            "merge_required": any(
                item.op == "merge" and not item.is_terminal for item in plan.items
            ),
        }

    stats = terminal_stats(plan)
    next_item = poll_runnable(plan)
    logger.info(
        f"[replanner] 第 {plan.iterations}/{budget.get('iterations', '?')} 轮，"
        f"完成 {stats['done']}/{stats['total']}，待办 {stats['unfinished']}，"
        f"无进展 {plan.no_progress_rounds} 轮，模型调用 {plan.llm_calls}"
        + (f"，下一条 {next_item.id}" if next_item is not None else "，队列已空")
        + ("，已判定 give_up" if plan.give_up else "")
    )

    return {
        "plan": plan.model_dump(mode="json"),
        "plan_events": events,
        "replanner_diag": {
            **diag,
            "iterations": plan.iterations,
            "no_progress_rounds": plan.no_progress_rounds,
            "give_up": plan.give_up,
            "llm_calls_total": plan.llm_calls,
            "llm_budget_exhausted": plan.llm_budget_exhausted(),
            "terminal_stats": stats,
            "next_item_id": next_item.id if next_item is not None else None,
            "total_ms": int((time.time() - started) * 1000),
        },
    }


__all__ = ["execute_node", "plan_node", "replanner_node"]
