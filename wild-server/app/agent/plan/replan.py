"""replanner 的异常分支：**只在出问题时**调一次模型，且只能在闭集里选动作。

对应《动态节点设计规划》§5.1/§5.3。两条纪律：

1. **快路径不调模型**：顺利的请求只有真正生成构件时才调用模型。只有出现
   ``failed`` 条目、或依赖被失败的条目卡住时，才会走到这里——循环里每轮都调模型
   会把成本乘以迭代数。
2. **模型只能在五个动作里选**：``add_items`` / ``replace_item`` / ``drop_item`` /
   ``mark_unsupported`` / ``give_up``。动作**由程序校验后写入 plan**：未知 op、未知
   kind、不存在的条目 id、追加次数超限一律拒绝，并把拒绝理由记进 ``replan_diag``。
   模型永远不直接改计划数据。

与"涌现缺口"的关系（§5.3）：能从放置后果确定性推导出来的需求（例如"阳台落地后需要
栏杆"）优先写成确定性派生；只有无法几何推导的场合才交给模型。本模块只做后者。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.agent.generation.components import COMPONENT_REGISTRY, get_implemented_components
from app.agent.plan.contracts import OPS, ItemRun, PlanDocument, PlanHistoryEntry, PlanItem
from app.agent.plan.store import (
    append_items,
    poll_runnable,
    refresh_statuses,
    set_evidence,
    set_status,
)

#: 允许的动作（§5.3 的闭集）。多一个都要先改文档再改这里。
REPLAN_ACTIONS: tuple[str, ...] = (
    "add_items",
    "replace_item",
    "drop_item",
    "mark_unsupported",
    "give_up",
)

#: 追加条目的上限（与 §5.4 的 `revision > 2` 一致）。
MAX_REVISION = 2

#: 同一条目只允许一次策略替换。第二次仍失败说明替换没有解决根因，应带警告收尾。
MAX_REPLACE_PER_ITEM = 1

#: 连续无业务进展达到该值后停止模型工作，但仍执行确定性合并。
MAX_NO_PROGRESS_ROUNDS = 2


@dataclass
class ReplanDecision:
    """模型（或确定性降级）给出的一次决策。"""

    action: str
    item_id: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    source: str = "deterministic"


def plan_needs_replan(plan: PlanDocument) -> bool:
    """快路径判定：本轮有没有值得调模型的异常。

    只有两类情况值得调一次（§5.1）：

    1. 有条目本轮 ``failed``（还没耗尽重试）；
    2. 有条目被**悬空依赖**卡住（依赖的条目根本不存在）——结构异常，自己好不了。

    其余一律返回 False。特别注意：健康流程里的 ``blocked`` 是**暂态**（``merge`` 在
    ``generate`` 成功前就是 blocked），不能被当成异常，否则每轮都会调一次模型，
    §5.1 的成本前提就没了。
    """

    for item in plan.items:
        if item.is_terminal:
            continue
        if item.run.state == "failed":
            return True
        if item.status == "blocked" and any(
            plan.item(dep) is None for dep in item.depends_on
        ):
            return True
    return False


def replan_summary(plan: PlanDocument, state: dict[str, Any]) -> dict[str, Any]:
    """异常摘要：只讲出问题的条目与已经落地的构件，不塞整份计划。"""

    problems = [
        {
            "item_id": item.id,
            "op": item.op,
            "kind": item.kind,
            "label": item.label,
            "status": item.status,
            "run_state": item.run.state,
            "attempts": item.run.attempts,
            "max_attempts": item.run.max_attempts,
            "evidence": item.run.evidence[:300],
            "depends_on": list(item.depends_on),
        }
        for item in plan.items
        if not item.is_terminal and (item.run.state == "failed" or item.status == "blocked")
    ]
    done = [
        {"item_id": item.id, "kind": item.kind, "label": item.label}
        for item in plan.items
        if item.status == "done"
    ]
    return {
        "user_message": str(state.get("user_message") or "")[:500],
        "revision": plan.revision,
        "revision_limit": MAX_REVISION,
        "iterations": plan.iterations,
        "budget_iterations": (plan.budget or {}).get("iterations"),
        "problems": problems,
        "completed": done,
        "available_kinds": [config.component_type for config in get_implemented_components()],
    }


def parse_replan(raw: Any) -> ReplanDecision | None:
    """解析模型输出；动作不在闭集内即视为不可用（交给确定性降级）。"""

    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action") or "").strip()
    if action not in REPLAN_ACTIONS:
        return None
    items = raw.get("items")
    params = raw.get("params")
    return ReplanDecision(
        action=action,
        item_id=str(raw.get("item_id") or "").strip(),
        items=[entry for entry in items if isinstance(entry, dict)] if isinstance(items, list) else [],
        params=dict(params) if isinstance(params, dict) else {},
        reason=str(raw.get("reason") or "").strip()[:500],
        source="llm",
    )


def deterministic_decision(plan: PlanDocument) -> ReplanDecision:
    """降级决策：模型不可用时也不该把整轮判死。

    规则只有一条且必须确定：拿第一条卡住的条目，若还有调整额度就带着失败证据
    做一次定向重试；额度耗尽则放弃该条目。不能在首次失败时直接结束整份计划。
    """

    for item in plan.items:
        if item.is_terminal:
            continue
        dangling = item.status == "blocked" and any(
            plan.item(dep) is None for dep in item.depends_on
        )
        if item.run.state == "failed" or dangling:
            replaced = sum(
                1
                for entry in plan.history
                if entry.action == "replace_item" and item.id in entry.item_ids
            )
            if item.run.attempts >= item.run.max_attempts or replaced >= MAX_REPLACE_PER_ITEM:
                return ReplanDecision(
                    action="drop_item",
                    item_id=item.id,
                    reason=(
                        "同一条目调整后仍失败，停止重复执行并进入交付清单"
                        if replaced >= MAX_REPLACE_PER_ITEM
                        else "重试额度耗尽，进交付清单"
                    ),
                    source="deterministic",
                )
            return ReplanDecision(
                action="replace_item",
                item_id=item.id,
                params={
                    "guidance": (
                        "修正上一轮未产出可交付片段的问题；严格按设计清单中本类型的"
                        "槽位逐项输出，并只返回符合字段契约的结构化结果"
                    )
                },
                reason="仍有一次有界调整额度，依据失败证据定向重试",
                source="deterministic",
            )
    return ReplanDecision(action="give_up", reason="无可处置的异常条目", source="deterministic")


def _replacement_count(plan: PlanDocument, item_id: str) -> int:
    return sum(
        1
        for entry in plan.history
        if entry.action == "replace_item" and item_id in entry.item_ids
    )


def _recoverable_failed_items(plan: PlanDocument) -> list[PlanItem]:
    """仍有一次定向调整机会的失败条目；它们禁止被模型提前 give_up/drop。"""

    return [
        item
        for item in plan.items
        if not item.is_terminal
        and item.run.state == "failed"
        and item.run.attempts < item.run.max_attempts
        and _replacement_count(plan, item.id) < MAX_REPLACE_PER_ITEM
    ]


def enforce_decision_policy(
    plan: PlanDocument,
    decision: ReplanDecision,
) -> tuple[ReplanDecision, str]:
    """程序级动作资格校验：首次失败不能被模型直接放弃。

    只处理"**决策合法但不该被采纳**"这一种情况（例如对仍有额度的一次失败直接 give_up），
    把它换成确定性的有界调整。**畸形决策不在这里改写**：指向不存在条目的
    `replace_item` 属于模型输出错误，交给 `apply_decision` 记 `rejected` 并保持计划不变——
    改写它会让诊断里出现一个模型从未提过的动作，掩盖模型反复给出无效 ID 这件事。
    """

    malformed_target = (
        decision.action in {"replace_item", "drop_item", "mark_unsupported"}
        and plan.item(decision.item_id) is None
    )
    if malformed_target:
        return decision, ""

    recoverable = _recoverable_failed_items(plan)
    if not recoverable:
        return decision, ""
    recoverable_ids = {item.id for item in recoverable}
    if decision.action == "replace_item" and decision.item_id in recoverable_ids:
        effective_params = {
            key: value
            for key, value in decision.params.items()
            if key in {"subtype", "guidance", "reason"} and str(value).strip()
        }
        if effective_params:
            return decision, ""

    fallback = deterministic_decision(plan)
    reason = (
        f"replace_item 未提供有效变化参数；已补充定向调整 {fallback.item_id}"
        if decision.action == "replace_item" and decision.item_id in recoverable_ids
        else (
            f"动作 {decision.action} 不适用于仍有调整额度的首次失败条目；"
            f"已改为定向调整 {fallback.item_id}"
        )
    )
    return fallback, reason


def prepare_finalization(
    plan: PlanDocument,
    *,
    reason: str,
) -> tuple[PlanDocument, list[str]]:
    """停止模型工作，但保留所有确定性 merge，让骨架和已有分片必定形成蓝图。

    已成功生成的条目保留，等待后续 merge 后由对账标记完成；失败或尚未执行的模型
    条目转为 skipped。批次 merge 与收尾 merge 不跳过，因为最终校验的输入只能由它们
    产生。计划内 validate 会跳过，统一交给图末尾的 final_validate 执行一次。
    """

    updated = plan.model_copy(deep=True)
    skipped: list[str] = []
    for item in updated.items:
        if item.is_terminal or item.op == "merge":
            continue
        if item.op == "generate" and item.run.state == "succeeded":
            continue
        item.status = "skipped"
        item.run.evidence = reason[:2000]
        skipped.append(item.id)

    first_finalization = not updated.give_up
    updated.give_up = True
    if first_finalization:
        updated.history.append(
            PlanHistoryEntry(
                revision=updated.revision,
                action="give_up",
                item_ids=skipped,
                reason=reason[:500],
            )
        )
    return refresh_statuses(updated), skipped


def _validate_new_item(raw: dict[str, Any], plan: PlanDocument) -> PlanItem | None:
    """把模型给的"要做什么"翻译成条目；任何一项不合法就整条拒绝。"""

    op = str(raw.get("op") or "generate").strip()
    if op not in OPS:
        return None
    kind = str(raw.get("kind") or "").strip()
    config = COMPONENT_REGISTRY.get(kind)
    if op in {"generate", "repair"} and (config is None or not config.implemented):
        return None
    index = 1 + len([item for item in plan.items if item.origin == "emergent"])
    return PlanItem(
        id=f"emergent_{op}_{kind or 'all'}_{index:02d}",
        op=op,
        kind=kind,
        label=str(raw.get("label") or (config.label if config is not None else kind)),
        target=dict(raw.get("target") or {}),
        params={
            "subtype": str(raw.get("subtype") or ""),
            "guidance": str(raw.get("guidance") or ""),
            "reason": str(raw.get("reason") or "")[:300],
        },
        run=ItemRun(max_attempts=2),
        origin="emergent",
    )


def apply_decision(
    plan: PlanDocument,
    decision: ReplanDecision,
) -> tuple[PlanDocument, dict[str, Any]]:
    """程序校验后写回计划，返回 ``(plan, 结果摘要)``。

    被拒绝的决策不会改变计划——``add_items`` 超预算、``replace_item`` 指向不存在的
    条目、``give_up`` 之外的未知动作，统统只记摘要，让循环继续按确定性的路子走。
    """

    decision, policy_override = enforce_decision_policy(plan, decision)
    outcome: dict[str, Any] = {
        "action": decision.action,
        "source": decision.source,
        "reason": decision.reason,
        "policy_override": policy_override,
        "applied": False,
        "rejected": "",
        "item_ids": [],
    }

    if decision.action == "add_items":
        fresh = [item for item in (_validate_new_item(raw, plan) for raw in decision.items) if item]
        if not fresh:
            outcome["rejected"] = "没有任何合法的可追加条目（op/kind 不在闭集或能力清单内）"
            return plan, outcome
        updated, appended = append_items(
            plan, fresh, reason=decision.reason or "replanner 追加", max_revision=MAX_REVISION
        )
        if not appended:
            outcome["rejected"] = f"追加次数已达上限 revision={plan.revision}/{MAX_REVISION}"
            return plan, outcome
        outcome.update(applied=True, item_ids=[item.id for item in fresh])
        return updated, outcome

    if decision.action in {"replace_item", "drop_item", "mark_unsupported"}:
        item = plan.item(decision.item_id)
        if item is None:
            outcome["rejected"] = f"条目 {decision.item_id!r} 不存在"
            return plan, outcome
        if item.is_terminal:
            outcome["rejected"] = f"条目 {item.id} 已是终态 {item.status}，不再改动"
            return plan, outcome

        if decision.action == "replace_item":
            if item.run.exhausted:
                outcome["rejected"] = f"条目 {item.id} 的尝试额度已耗尽，不能继续替换"
                return plan, outcome
            replaced = sum(
                1
                for entry in plan.history
                if entry.action == "replace_item" and item.id in entry.item_ids
            )
            if replaced >= MAX_REPLACE_PER_ITEM:
                outcome["rejected"] = (
                    f"条目 {item.id} 已调整 {replaced} 次，禁止继续重复 replace_item"
                )
                return plan, outcome
            plan = set_evidence(plan, item.id, decision.reason or "replanner 替换後重试")
            if decision.params:
                # 形态提示是"怎么做"的自由度，允许被替换；宿主机位不在 params 里，改不到。
                updated_item = plan.item(item.id)
                if updated_item is not None:
                    params = dict(updated_item.params)
                    params.update(
                        {
                            key: value
                            for key, value in decision.params.items()
                            if key in {"subtype", "guidance", "reason"}
                        }
                    )
                    updated_item.params = params
            plan = set_status(plan, item.id, "ready")
            plan = _rewrite_run(plan, item.id, evidence=decision.reason or "replanner 替换後重试")
            plan.history.append(
                PlanHistoryEntry(
                    revision=plan.revision,
                    action="replace_item",
                    item_ids=[item.id],
                    reason=(decision.reason or "有界调整后重试")[:500],
                )
            )
            outcome.update(applied=True, item_ids=[item.id])
            return refresh_statuses(plan), outcome

        target_status = "skipped" if decision.action == "drop_item" else "unsupported"
        plan = set_status(plan, item.id, target_status, evidence=decision.reason or "replanner 判定")
        outcome.update(applied=True, item_ids=[item.id])
        return refresh_statuses(plan), outcome

    if decision.action == "give_up":
        plan, skipped = prepare_finalization(
            plan,
            reason=decision.reason or "停止继续生成，进入确定性收尾",
        )
        outcome.update(applied=True, item_ids=skipped)
        return plan, outcome

    outcome["rejected"] = f"未知动作 {decision.action!r}（闭集 {REPLAN_ACTIONS}）"
    return plan, outcome


def _rewrite_run(plan: PlanDocument, item_id: str, *, evidence: str) -> PlanDocument:
    """``replace_item`` 要让条目**真的再跑一次**：清执行态，保留已计尝试数。"""

    updated = plan.model_copy(deep=True)
    item = updated.item(item_id)
    if item is None:
        return updated
    item.run.state = "idle"
    item.run.evidence = evidence[:2000]
    return updated


async def request_replan(
    plan: PlanDocument,
    state: dict[str, Any],
    *,
    llm=None,
) -> tuple[ReplanDecision, dict[str, Any]]:
    """异常时调一次模型；返回 ``(决策, 诊断)``。

    模型调不通/输出不可用 → ``deterministic_decision``。这与 plan 阶段的策略降级是
    同一条政策：**调度想不出来不该让用户拿不到建筑**。
    """

    started = time.perf_counter()
    summary = replan_summary(plan, state)
    prompt = build_prompt(plan)
    diag: dict[str, Any] = {
        "summary": summary,
        "problems": len(summary["problems"]),
        "revision": plan.revision,
        "model_called": False,
    }

    bounded = deterministic_decision(plan)
    failed_item = plan.item(bounded.item_id)
    generated = (state.get("component_diagnostics") or {}).get(
        f"{failed_item.kind}_gen" if failed_item else "", {}
    )
    tool_error = (generated.get("tool_loop") or {}).get("error")
    if bounded.action == "replace_item" and tool_error:
        # 执行故障不能交给建筑策略模型通过减配来“修复”。仍受一次替换上限约束。
        bounded.params = {"guidance": "保留全部已批准槽位、数量和宿主；根据已有知识输出完整结构化结果，避免重复工具查询。"}
        bounded.reason = f"工具执行失败，保持设计约束作一次有界重试：{str(tool_error)[:300]}"
        diag.update(decision_source="deterministic", fallback_reason=bounded.reason)
        return bounded, diag
    if bounded.action != "replace_item":
        diag.update(
            {
                "decision_source": bounded.source,
                "prompt_chars": 0,
                "llm_ms": 0,
                "token_usage": None,
                "error": None,
                "fallback_reason": bounded.reason,
                "total_ms": int((time.perf_counter() - started) * 1000),
            }
        )
        return bounded, diag

    raw = None
    error = None
    token_usage = None
    llm_ms = 0
    from app.agent.prompts import build_replan_user_message

    try:
        from app.llm.client import create_llm
        from app.llm.invocation import invoke_llm
        from app.utils.json_extractor import extract_json_object

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": build_replan_user_message(summary)},
        ]
        llm_t0 = time.perf_counter()
        diag["model_called"] = True
        llm_result = await invoke_llm(
            llm or create_llm(enable_thinking=False, streaming=False), messages
        )
        llm_ms = int((time.perf_counter() - llm_t0) * 1000)
        token_usage = llm_result.token_usage
        raw = extract_json_object(llm_result.content)
    except Exception as exc:
        error = str(exc)
        logger.warning(f"[replanner] 调度模型不可用，使用确定性决策: {exc}")

    decision = parse_replan(raw) if raw is not None else None
    if decision is None:
        decision = deterministic_decision(plan)
        if raw is not None:
            diag["fallback_reason"] = "模型未给出闭集内的动作"
        elif error:
            diag["fallback_reason"] = error
        else:
            diag["fallback_reason"] = "模型输出不可解析"

    decision, policy_override = enforce_decision_policy(plan, decision)
    if policy_override:
        diag["policy_override"] = policy_override
        diag["fallback_reason"] = policy_override

    if decision.action == "replace_item":
        replaced = _replacement_count(plan, decision.item_id)
        if replaced >= MAX_REPLACE_PER_ITEM:
            diag["fallback_reason"] = "同一条目已经调整过一次，不再重复 replace_item"
            decision = deterministic_decision(plan)

    diag.update(
        {
            "decision_source": decision.source,
            "prompt_chars": len(prompt),
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "error": error,
            "total_ms": int((time.perf_counter() - started) * 1000),
        }
    )
    return decision, diag


def build_prompt(plan: PlanDocument) -> str:
    """本模块构建提示词的唯一入口（能力清单与追加预算都从 plan 现状取）。"""

    from app.agent.plan.strategy import capability_catalog
    from app.agent.prompts import build_replan_prompt

    return build_replan_prompt(
        capability_catalog=capability_catalog(),
        revision=plan.revision,
        revision_limit=MAX_REVISION,
    )


def replan(
    plan: PlanDocument,
    state: dict[str, Any],
    decision: ReplanDecision,
) -> tuple[PlanDocument, dict[str, Any]]:
    """应用一次决策并推进无进展计数（供节点与测试直接调用）。"""

    updated, outcome = apply_decision(plan, decision)
    updated = refresh_statuses(updated)
    _ = poll_runnable(updated)  # 保持"应用后必然可判定下一步"的契约
    return updated, outcome


__all__ = [
    "MAX_REVISION",
    "MAX_REPLACE_PER_ITEM",
    "MAX_NO_PROGRESS_ROUNDS",
    "REPLAN_ACTIONS",
    "ReplanDecision",
    "apply_decision",
    "deterministic_decision",
    "enforce_decision_policy",
    "parse_replan",
    "plan_needs_replan",
    "replan",
    "replan_summary",
    "prepare_finalization",
    "request_replan",
]
