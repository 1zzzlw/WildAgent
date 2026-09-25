"""生成链的路由与拓扑测试。

对应《动态节点设计规划》§一（拓扑）、§二（plan 是数据）、§五（五重有界终止）。
核心断言只有一句：**图里不再有 ``{ct}_gen`` / ``{ct}_val``，业务顺序在 plan 数据里。**
"""

from __future__ import annotations

import pytest

from app.agent.graph import (
    MAX_NO_PROGRESS_ROUNDS,
    _after_plan,
    _after_replanner,
    build_generation_graph,
    plan_recursion_limit,
)
from app.agent.plan.contracts import PlanDocument, PlanItem


def _plan(items: list[PlanItem], **overrides) -> PlanDocument:
    return PlanDocument(items=items, **overrides)


def _item(item_id: str, op: str = "generate", kind: str = "wall", **kwargs) -> PlanItem:
    return PlanItem(id=item_id, op=op, kind=kind, **kwargs)


def _state(plan: PlanDocument | None) -> dict:
    return {"plan": plan.model_dump() if plan is not None else None}


# ── 拓扑 ──


def test_graph_has_no_per_component_nodes():
    nodes = set(build_generation_graph().get_graph().nodes)

    assert {"classifier", "architecture", "skeleton", "plan", "execute", "replanner",
            "final_validate"} <= nodes
    assert not [name for name in nodes if name.endswith("_gen") or name.endswith("_val")]


#: 图里允许出现的节点全集。加**构件类型**不该改动这个集合——那由 plan 数据表达；
#: 只有加**交付目标类型**（建筑 / 物件）才会多出一个方案节点。
_EXPECTED_NODES = {
    "__start__",
    "__end__",
    "classifier",       # 意图 + 目标类型判定（generate / edit / chat × architecture / object）
    "chat",             # 只读问答
    "patch",            # 既有场景上的定向修改
    "architecture",     # 目标=建筑：体量、立面、屋顶
    "object_design",    # 目标=物件：物件清单（与 architecture 并列，不是它的内部分支）
    "material_plan",    # 以下五步两条链完全复用
    "design_review",
    "skeleton",
    "plan",             # 由模型决定批次与并发，业务顺序在 plan 数据里
    "execute",
    "replanner",
    "final_validate",
}


def test_graph_stays_small():
    """节点集合固定且少：加构件类型不加节点，这是本轮重构的主要收益。

    用全集相等而不是数量上限：数量上限只能发现"变多了"，全集相等还能发现
    "换了个名字"和"悄悄少了一步"。目标类型分叉是本集合唯一的增长理由——
    物件场景的方案契约（ObjectDecisions）与建筑不同，必须有独立方案节点；
    但它的下游完全复用骨架→计划→执行→校验这条链路，一步都不多。
    """

    nodes = set(build_generation_graph().get_graph().nodes)

    assert nodes == _EXPECTED_NODES, sorted(nodes ^ _EXPECTED_NODES)


def test_callback_is_optional():
    assert "callback" not in set(build_generation_graph().get_graph().nodes)
    assert "callback" in set(build_generation_graph(enable_callback=True).get_graph().nodes)


# ── 递归上限 ──


def test_recursion_limit_scales_with_items():
    # 小计划落在 48 的安全下限上，不随条目数变化
    assert plan_recursion_limit(2) == plan_recursion_limit(10) == 48
    assert plan_recursion_limit(40) > plan_recursion_limit(30)
    # 一条条目 = execute + replanner 两步
    assert plan_recursion_limit(30) - plan_recursion_limit(29) == 2
    # 重试额度也计入预算
    assert plan_recursion_limit(30, 5) > plan_recursion_limit(30, 0)


# ── plan → execute / final_validate ──


def test_plan_routes_to_execute_when_something_is_runnable():
    state = _state(_plan([_item("generate_wall_001")]))

    assert _after_plan(state) == "execute"


def test_plan_routes_to_final_validate_when_nothing_to_do():
    state = _state(_plan([_item("generate_wall_001", status="done")]))

    assert _after_plan(state) == "final_validate"


def test_plan_missing_is_not_fatal():
    """计划缺失不炸路由，交给 final_validate 如实报告。"""

    assert _after_plan({}) == "final_validate"
    assert _after_plan({"plan": {"items": "不是列表"}}) == "final_validate"


# ── replanner → execute / final_validate（五重有界终止）──


def test_replanner_loops_while_work_remains():
    state = _state(_plan([_item("generate_wall_001"), _item("validate_wall_002", op="validate")]))

    assert _after_replanner(state) == "execute"


def test_replanner_stops_at_iteration_budget():
    plan = _plan([_item("generate_wall_001")], budget={"iterations": 1}, iterations=1)

    assert _after_replanner(_state(plan)) == "final_validate"


def test_replanner_stops_after_no_progress_rounds():
    plan = _plan([_item("generate_wall_001")],
                 no_progress_rounds=MAX_NO_PROGRESS_ROUNDS)

    assert _after_replanner(_state(plan)) == "final_validate"


def test_give_up_runs_remaining_deterministic_merge_before_final_validate():
    plan = _plan(
        [
            _item("generate_door_001", kind="door", status="skipped"),
            _item(
                "merge_all_001",
                op="merge",
                kind="all",
                status="ready",
                params={"scope": "final"},
            ),
        ],
        give_up=True,
    )

    assert _after_replanner(_state(plan)) == "execute"


def test_replanner_finishes_when_all_terminals():
    plan = _plan([
        _item("generate_wall_001", status="done"),
        _item("generate_door_002", kind="door", status="abandoned"),
        _item("generate_roof_003", kind="roof", status="unsupported"),
    ])

    assert _after_replanner(_state(plan)) == "final_validate"


@pytest.mark.parametrize("intent,expected", [
    ("generate", "architecture"),
    ("edit", "patch"),
    ("chat", "chat"),
    (None, "chat"),
])
def test_classifier_dispatch(intent, expected):
    from app.agent.graph import _classifier_dispatch

    assert _classifier_dispatch({"intent": intent}) == expected


def test_terminal_model_error_ends_the_run():
    from app.agent.graph import _classifier_dispatch

    assert _classifier_dispatch({"intent": "generate", "terminal_model_error": {"code": "x"}}) == "__end__"
