"""replanner 异常分支的回归测试（《动态节点设计规划》§5.1、§5.3、§5.4）。

钉三件事：

1. **快路径不调模型**：计划健康时 ``plan_needs_replan`` 为假，循环里一次模型调用都不多。
2. **动作是闭集**：模型只能在五个动作里选；未知 op / 未知 kind / 不存在的条目 id /
   追加次数超限一律被程序拒绝，且**被拒绝的决策不改变计划**。
3. **终止条件有界**：``give_up`` 带警告交付；模型调用预算能真的叫停循环。
"""

from __future__ import annotations

import pytest

from app.agent.plan.contracts import ItemRun, PlanDocument, PlanItem
from app.agent.plan.replan import (
    MAX_REPLACE_PER_ITEM,
    MAX_REVISION,
    REPLAN_ACTIONS,
    ReplanDecision,
    apply_decision,
    deterministic_decision,
    enforce_decision_policy,
    parse_replan,
    plan_needs_replan,
    prepare_finalization,
    replan_summary,
)
from app.agent.plan.store import new_plan, poll_runnable


def _plan(*items: PlanItem) -> PlanDocument:
    return new_plan(list(items) or [PlanItem(id="validate_all_01", op="validate", kind="all")])


def _failed(item_id: str = "generate_door_01", *, attempts: int = 1, max_attempts: int = 3):
    item = PlanItem(
        id=item_id,
        op="generate",
        kind="door",
        label="生成门",
        run=ItemRun(state="failed", attempts=attempts, max_attempts=max_attempts),
    )
    return item


# ── 快路径 ──


def test_healthy_plan_never_reaches_the_model():
    plan = _plan(PlanItem(id="generate_door_01", op="generate", kind="door"))

    assert plan_needs_replan(plan) is False


def test_failed_item_needs_replan():
    assert plan_needs_replan(_plan(_failed())) is True


def test_transient_blocked_is_not_an_exception():
    """健康流程里 merge 在 generate 成功前就是 blocked：这是暂态，不能每轮都调模型。"""

    plan = _plan(
        PlanItem(id="generate_door_01", op="generate", kind="door"),
        PlanItem(
            id="merge_all_01",
            op="merge",
            kind="all",
            depends_on=["generate_door_01"],
            status="blocked",
        ),
    )

    assert plan_needs_replan(plan) is False


def test_dangling_dependency_needs_replan():
    """依赖一个不存在的条目：自己好不了的结构异常，值得让调度看一眼。"""

    plan = _plan(
        PlanItem(id="generate_door_01", op="generate", kind="door"),
        PlanItem(
            id="merge_all_01", op="merge", kind="all", depends_on=["ghost_99"], status="blocked"
        ),
    )

    assert plan_needs_replan(plan) is True


def test_terminal_items_alone_do_not_trigger_replan():
    plan = _plan(
        PlanItem(id="generate_door_01", op="generate", kind="door", status="done"),
        PlanItem(id="validate_all_01", op="validate", kind="all", status="done"),
    )

    assert plan_needs_replan(plan) is False


# ── 解析 ──


def test_only_closed_set_actions_parse():
    for action in REPLAN_ACTIONS:
        decision = parse_replan({"action": action, "reason": "r"})
        assert decision is not None and decision.action == action
        assert decision.source == "llm"

    assert parse_replan({"action": "rewrite_everything"}) is None
    assert parse_replan("add_items") is None
    assert parse_replan({"reason": "缺 action"}) is None


# ── 应用（程序校验后写回）──


def test_add_items_is_translated_into_deterministic_emergent_items():
    plan = _plan(PlanItem(id="generate_door_01", op="generate", kind="door", status="done"))
    decision = ReplanDecision(
        action="add_items",
        items=[
            {"op": "generate", "kind": "railing", "reason": "阳台落地后需要栏杆"},
            {"op": "generate", "kind": "teleporter", "reason": "不在能力清单里"},
        ],
        reason="补齐缺失构件",
    )

    updated, outcome = apply_decision(plan, decision)

    assert outcome["applied"] is True
    assert outcome["item_ids"] == ["emergent_generate_railing_01"]
    added = updated.item("emergent_generate_railing_01")
    assert added is not None and added.origin == "emergent" and added.status == "ready"
    assert updated.revision == 2
    assert updated.history[-1].action == "append_items"


def test_add_items_is_rejected_when_nothing_is_legal():
    plan = _plan(PlanItem(id="generate_door_01", op="generate", kind="door"))

    updated, outcome = apply_decision(
        plan,
        ReplanDecision(action="add_items", items=[{"op": "teleport", "kind": "door"}]),
    )

    assert outcome["applied"] is False
    assert "合法的可追加条目" in outcome["rejected"]
    assert updated.revision == plan.revision
    assert len(updated.items) == len(plan.items)


def test_add_items_is_rejected_after_revision_limit():
    plan = _plan(PlanItem(id="generate_door_01", op="generate", kind="door"))
    plan.revision = MAX_REVISION

    updated, outcome = apply_decision(
        plan, ReplanDecision(action="add_items", items=[{"op": "generate", "kind": "railing"}])
    )

    assert outcome["applied"] is False
    assert "上限" in outcome["rejected"]
    assert len(updated.items) == len(plan.items)


def test_replace_item_makes_it_runnable_again_without_touching_geometry():
    plan = _plan(_failed())
    decision = ReplanDecision(
        action="replace_item",
        item_id="generate_door_01",
        params={"subtype": "单开门", "x": 999},  # x 不是允许替换的字段
        reason="换一种门型再试",
    )

    updated, outcome = apply_decision(plan, decision)

    item = updated.item("generate_door_01")
    assert outcome["applied"] is True
    assert item.status == "ready" and item.run.state == "idle"
    assert item.run.attempts == 1  # 已计的尝试数不清零，重试预算仍然有界
    assert item.params["subtype"] == "单开门"
    assert "x" not in item.params
    assert updated.history[-1].action == "replace_item"


def test_same_item_cannot_be_replaced_repeatedly():
    plan = _plan(_failed())
    once, first = apply_decision(
        plan,
        ReplanDecision(
            action="replace_item",
            item_id="generate_door_01",
            params={"subtype": "单开门"},
            reason="第一次调整",
        ),
    )
    once.item("generate_door_01").run.state = "failed"
    twice, second = apply_decision(
        once,
        ReplanDecision(
            action="replace_item",
            item_id="generate_door_01",
            params={"subtype": "双开门"},
            reason="第二次调整",
        ),
    )

    assert MAX_REPLACE_PER_ITEM == 1
    assert first["applied"] is True
    assert second["applied"] is False
    assert "禁止继续重复" in second["rejected"]
    assert twice.item("generate_door_01").params["subtype"] == "单开门"


def test_drop_item_and_mark_unsupported_are_terminal():
    # 前提是这两条已**耗尽重试额度**：策略明文规定"仍有调整额度的失败条目禁止被模型
    # 提前 give_up/drop"，所以可恢复条目上的 drop_item 会被替换成一次有界重试。
    # 本用例钉的是终态语义，因此先用不可恢复的失败条目隔离掉那条策略。
    plan = _plan(
        _failed("generate_door_01", attempts=3, max_attempts=3),
        _failed("generate_window_01", attempts=3, max_attempts=3),
    )

    dropped, drop_outcome = apply_decision(
        plan, ReplanDecision(action="drop_item", item_id="generate_door_01", reason="宿主墙不足")
    )
    assert drop_outcome["applied"] is True
    assert dropped.item("generate_door_01").status == "skipped"

    marked, mark_outcome = apply_decision(
        plan,
        ReplanDecision(
            action="mark_unsupported", item_id="generate_window_01", reason="能力缺失"
        ),
    )
    assert mark_outcome["applied"] is True
    assert marked.item("generate_window_01").status == "unsupported"


def test_recoverable_failure_cannot_be_dropped_by_the_model():
    """一次失败且有额度时，模型不能把它 drop 掉——必须走完那一次有界重试。"""

    plan = _plan(_failed())

    dropped, outcome = apply_decision(
        plan, ReplanDecision(action="drop_item", item_id="generate_door_01", reason="模型想放弃")
    )

    assert outcome["policy_override"]
    assert "不适用于仍有调整额度的首次失败条目" in outcome["policy_override"]
    assert dropped.item("generate_door_01").status != "skipped"


def test_decisions_on_unknown_or_terminal_items_are_rejected():
    plan = _plan(PlanItem(id="generate_door_01", op="generate", kind="door", status="done"))

    _, unknown = apply_decision(plan, ReplanDecision(action="drop_item", item_id="nope_01"))
    assert unknown["applied"] is False and "不存在" in unknown["rejected"]

    _, terminal = apply_decision(
        plan, ReplanDecision(action="drop_item", item_id="generate_door_01")
    )
    assert terminal["applied"] is False and "终态" in terminal["rejected"]


def test_first_failure_cannot_give_up_before_one_bounded_adjustment():
    plan = _plan(_failed())
    updated, outcome = apply_decision(
        plan, ReplanDecision(action="give_up", reason="首次失败就停止")
    )

    assert outcome["applied"] is True
    assert outcome["action"] == "replace_item"
    assert outcome["policy_override"]
    assert updated.give_up is False
    assert updated.item("generate_door_01").run.state == "idle"


def test_give_up_keeps_deterministic_merges_runnable_for_delivery():
    plan = _plan(
        _failed(attempts=3, max_attempts=3),
        PlanItem(
            id="merge_door_01",
            op="merge",
            kind="door",
            depends_on=["generate_door_01"],
            params={"scope": "batch"},
        ),
        PlanItem(
            id="merge_all_01",
            op="merge",
            kind="all",
            depends_on=["merge_door_01"],
            params={"scope": "final"},
        ),
        PlanItem(
            id="validate_all_01",
            op="validate",
            kind="all",
            depends_on=["merge_all_01"],
        ),
    )

    updated, outcome = apply_decision(
        plan, ReplanDecision(action="give_up", reason="调整额度已经耗尽")
    )

    assert outcome["action"] == "give_up"
    assert updated.give_up is True
    assert updated.item("generate_door_01").status == "skipped"
    assert updated.item("validate_all_01").status == "skipped"
    assert poll_runnable(updated).id == "merge_door_01"


# ── 确定性降级 ──


def test_deterministic_decision_prefers_retry_then_gives_up():
    with_budget = deterministic_decision(_plan(_failed(attempts=1, max_attempts=3)))
    assert with_budget.action == "replace_item"
    assert with_budget.source == "deterministic"

    exhausted = deterministic_decision(_plan(_failed(attempts=3, max_attempts=3)))
    assert exhausted.action == "drop_item"

    replaced, _ = apply_decision(
        _plan(_failed()),
        ReplanDecision(action="replace_item", item_id="generate_door_01"),
    )
    replaced.item("generate_door_01").run.state = "failed"
    assert deterministic_decision(replaced).action == "drop_item"


def test_summary_only_lists_problems_and_completed_work():
    plan = _plan(
        PlanItem(id="generate_door_01", op="generate", kind="door", status="done"),
        _failed(),
    )

    summary = replan_summary(plan, {"user_message": "生成两层住宅"})

    assert [entry["item_id"] for entry in summary["problems"]] == ["generate_door_01"]
    assert [entry["item_id"] for entry in summary["completed"]] == ["generate_door_01"]
    assert "door" in summary["available_kinds"]


# ── 预算（§5.4）──


def test_llm_budget_is_counted_on_the_plan_and_can_stop_the_loop():
    plan = _plan(PlanItem(id="generate_door_01", op="generate", kind="door"))
    plan.budget = {"llm_calls": 2}

    plan.add_llm_calls(1)
    assert plan.llm_budget_exhausted() is False
    plan.add_llm_calls(1)
    assert plan.llm_budget_exhausted() is True


def test_prepare_finalization_keeps_successful_generation_for_merge_reconciliation():
    generated = PlanItem(id="generate_door_01", op="generate", kind="door")
    generated.run.state = "succeeded"
    plan = _plan(
        generated,
        PlanItem(
            id="merge_all_01",
            op="merge",
            kind="all",
            depends_on=["generate_door_01"],
            params={"scope": "final"},
        ),
    )

    updated, skipped = prepare_finalization(plan, reason="预算结束")

    assert skipped == []
    assert updated.item("generate_door_01").status == "ready"
    assert updated.item("generate_door_01").run.state == "succeeded"
    assert poll_runnable(updated).id == "merge_all_01"


@pytest.mark.parametrize("action", REPLAN_ACTIONS)
def test_every_action_is_reachable_from_a_real_plan(action):
    failed = _failed(
        attempts=3 if action in {"drop_item", "mark_unsupported", "give_up"} else 1,
        max_attempts=3,
    )
    if action == "add_items":
        failed.run.state = "idle"
    plan = _plan(PlanItem(id="generate_window_01", op="generate", kind="window"), failed)

    updated, outcome = apply_decision(
        plan,
        ReplanDecision(
            action=action,
            item_id="generate_door_01",
            items=[{"op": "generate", "kind": "railing"}] if action == "add_items" else [],
            reason="回归",
        ),
    )

    assert outcome["action"] == action
    assert isinstance(updated, PlanDocument)


def test_policy_accepts_replace_for_a_recoverable_failed_item():
    plan = _plan(_failed())
    decision = ReplanDecision(
        action="replace_item",
        item_id="generate_door_01",
        params={"guidance": "严格按失败证据修正"},
    )

    normalized, reason = enforce_decision_policy(plan, decision)

    assert normalized is decision
    assert reason == ""


def test_tool_execution_error_cannot_reduce_design_quota():
    import asyncio
    from app.agent.plan.replan import request_replan

    plan = _plan(_failed())
    item = plan.item("generate_door_01")
    item.target = {"batch_size": 15, "source_slots": [str(i) for i in range(15)]}
    state = {"component_diagnostics": {"door_gen": {"tool_loop": {"error": "Recursion limit of 7 reached"}}}}
    decision, diag = asyncio.run(request_replan(plan, state))
    assert diag["model_called"] is False
    assert decision.action == "replace_item"
    assert "保留全部" in decision.params["guidance"]
    updated, _ = apply_decision(plan, decision)
    assert updated.item(item.id).target == item.target
