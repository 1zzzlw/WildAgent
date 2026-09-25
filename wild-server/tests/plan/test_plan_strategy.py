"""plan 策略层单测：模型定策略、程序归一化、失败降级。

对应《动态节点设计规划》§3.2。四条不变量：

1. 模型说的构件类型必须过能力清单（未知类型被丢弃，不是报错）；
2. 用户否定词与配额下限仍然生效（复用既有构件策略，不另写一套）；
3. 模型的输出**顺序与措辞**不影响条目顺序（展开阶段按注册表排序）；
4. 模型故障 / 返回不可解析 / 返回空 → 降级为确定性策略，且诊断如实记录。
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent.plan.contracts import PlanKindStrategy, PlanStrategy
from app.agent.plan.expand import expand_plan
from app.agent.plan.strategy import (
    capability_catalog,
    deterministic_strategy,
    normalize_kinds,
    parse_strategy,
    request_plan_strategy,
    slot_batch_summary,
    slot_counts,
)

_STATE = {
    "user_message": "生成一个带入户门的单层住宅",
    "design_brief": {
        "component_quota": {"door": {"min": 1, "max": 2}},
        "opening_slots": [{"id": "s1", "type": "door", "wall_id": "w1"}],
    },
    "skeleton_summary": "一层主体",
}


class _FakeLLMResult:
    def __init__(self, content: str, token_usage: dict | None = None):
        self.content = content
        self.token_usage = token_usage or {"input": 10, "output": 5}
        self.reasoning = ""


def _run(coro):
    return asyncio.run(coro)


# ── 归一化 ──


def test_capability_catalog_comes_from_the_registry():
    catalog = capability_catalog()

    assert {"door", "window", "roof"} <= {entry["kind"] for entry in catalog}
    assert all(entry["label"] for entry in catalog)


def test_unknown_kinds_are_dropped_not_raised():
    kinds = normalize_kinds(
        [{"kind": "door"}, {"kind": "spaceship"}, {"kind": "window"}], _STATE
    )

    assert [entry.kind for entry in kinds] == ["door", "window"]


def test_user_negation_still_wins_over_the_model():
    """模型说要窗，但用户说了"不要窗"：以用户为准（复用既有构件策略）。"""

    state = {"user_message": "生成一个没有窗的住宅", "design_brief": {}}

    assert [entry.kind for entry in normalize_kinds([{"kind": "window"}], state)] == []


def test_quota_minimum_is_forced_even_if_model_forgets():
    state = {
        "user_message": "生成一栋住宅",
        "design_brief": {"component_quota": {"door": {"min": 1, "max": 3}}},
    }

    assert "door" in [entry.kind for entry in normalize_kinds([{"kind": "window"}], state)]


def test_duplicate_kinds_collapse_and_keep_first_hint():
    kinds = normalize_kinds(
        [{"kind": "door", "subtype": "入户门"}, {"kind": "door", "subtype": "后门"}], _STATE
    )

    assert len(kinds) == 1
    assert kinds[0].subtype == "入户门"


def test_parallel_group_requires_two_independent_kinds():
    kinds = normalize_kinds(
        [
            {"kind": "door", "execution_mode": "parallel", "parallel_group": "openings"},
            {"kind": "window", "execution_mode": "parallel", "parallel_group": "openings"},
        ],
        _STATE,
    )

    assert {entry.execution_mode for entry in kinds} == {"parallel"}
    assert {entry.parallel_group for entry in kinds} == {"openings"}


def test_single_parallel_item_is_normalized_to_serial():
    kinds = normalize_kinds(
        [{"kind": "door", "execution_mode": "parallel", "parallel_group": "alone"}],
        _STATE,
    )

    assert kinds[0].execution_mode == "serial"
    assert kinds[0].parallel_group == ""


def test_slot_batch_summary_groups_same_size_openings():
    brief = {
        "opening_slots": [
            {"type": "window", "width": 1.5, "height": 1.8},
            {"type": "window", "width": 1.5, "height": 1.8},
            {"type": "window", "width": 2.0, "height": 1.8},
        ]
    }

    summary = slot_batch_summary(brief)

    assert summary["window"]["total"] == 3
    assert [variant["count"] for variant in summary["window"]["variants"]] == [2, 1]


def test_parse_strategy_rejects_empty_kinds():
    assert parse_strategy({"kinds": []}, _STATE) is None
    assert parse_strategy({"kinds": [{"kind": "spaceship"}]}, _STATE) is None
    assert parse_strategy("不是 JSON 对象", _STATE) is None


def test_parse_strategy_keeps_valid_detail_level_only():
    ok = parse_strategy({"kinds": [{"kind": "door"}], "detail_level": "detailed"}, _STATE)
    bad = parse_strategy({"kinds": [{"kind": "door"}], "detail_level": "超级精细"}, _STATE)

    assert ok is not None and ok.detail_level == "detailed"
    assert bad is not None and bad.detail_level is None


# ── 展开：策略进、条目出 ──


def test_expand_uses_strategy_kinds_and_records_history():
    strategy = PlanStrategy(
        kinds=[
            PlanKindStrategy(kind="window", subtype="大玻璃窗", reason="立面需要"),
            PlanKindStrategy(kind="door", subtype="入户门", reason="用户点名"),
        ],
        detail_level="simple",
        notes="单层住宅，重点是入口",
        source="llm",
    )

    plan = expand_plan(_STATE, strategy=strategy)

    # 条目顺序由注册表决定（door 在 window 之前），与模型输出顺序无关
    assert [item.kind for item in plan.items if item.op == "generate"] == ["door", "window"]
    door = plan.item("generate_door_01")
    assert door.params["subtype"] == "入户门"
    assert plan.detail_level == "simple"
    assert plan.history[0].action == "strategy:llm"
    assert plan.history[0].reason == "单层住宅，重点是入口"


def test_expand_stays_deterministic_for_the_same_strategy():
    strategy = PlanStrategy(kinds=[PlanKindStrategy(kind="door")], source="llm")

    first = expand_plan(_STATE, strategy=strategy).model_dump(mode="json")
    second = expand_plan(_STATE, strategy=strategy).model_dump(mode="json")

    assert first == second


@pytest.mark.parametrize(("kind", "count"), [("door", 12), ("window", 32)])
def test_many_same_kind_slots_expand_to_one_batch_item(kind: str, count: int):
    state = {
        **_STATE,
        "design_brief": {
            "component_quota": {kind: {"min": count, "max": count}},
            "opening_slots": [
                {"id": f"{kind}_slot_{index:02d}", "type": kind}
                for index in range(count)
            ],
        },
    }
    strategy = PlanStrategy(
        kinds=[
            PlanKindStrategy(
                kind=kind,
                batch_reason="同类槽位由一个批次生成",
            )
        ],
        source="llm",
    )

    plan = expand_plan(state, strategy=strategy)
    generated = [item for item in plan.items if item.op == "generate"]

    assert len(generated) == 1
    assert generated[0].target["batch_size"] == count
    assert generated[0].params["batch_reason"] == "同类槽位由一个批次生成"


@pytest.mark.parametrize(
    ("collection", "kind"),
    [("balcony_slots", "balcony"), ("roof_slots", "roof"), ("railing_slots", "railing")],
)
def test_named_slot_collections_use_the_same_batch_rule(collection: str, kind: str):
    state = {
        **_STATE,
        "design_brief": {
            "component_quota": {kind: {"min": 2, "max": 2}},
            collection: [{"id": f"{kind}_{index}"} for index in range(2)],
        },
    }

    plan = expand_plan(
        state,
        strategy=PlanStrategy(kinds=[PlanKindStrategy(kind=kind)], source="llm"),
    )
    generated = [item for item in plan.items if item.op == "generate"]

    assert len(generated) == 1
    assert generated[0].target["batch_size"] == 2


def test_named_slot_collection_uses_collection_kind_not_style_type():
    brief = {
        "roof_slots": [
            {"id": "roof_1", "type": "gable"},
            {"id": "roof_2", "type": "hip"},
        ]
    }

    assert slot_counts(brief) == {"roof": 2}


def test_expand_falls_back_to_skeleton_suggestions_without_strategy():
    plan = expand_plan({**_STATE, "suggested_components": ["door"]})

    assert [item.kind for item in plan.items if item.op == "generate"] == ["door"]


# ── 模型调用与降级 ──


def test_model_strategy_path(monkeypatch):
    reply = (
        '{"kinds": [{"kind": "door", "subtype": "入户双开门", "reason": "用户点名"},'
        ' {"kind": "spaceship"}], "detail_level": "standard", "notes": "重点是入口"}'
    )

    async def fake_invoke(_llm, _messages):
        return _FakeLLMResult(reply)

    monkeypatch.setattr("app.agent.plan.strategy.invoke_llm", fake_invoke)
    strategy, diag = _run(request_plan_strategy(_STATE))

    assert strategy.source == "llm"
    assert [entry.kind for entry in strategy.kinds] == ["door"]  # 未知类型被丢弃
    assert strategy.kinds[0].subtype == "入户双开门"
    assert diag["used_fallback"] is False
    assert diag["strategy_source"] == "llm"
    assert diag["kinds"] == ["door"]


def test_model_failure_is_terminal_not_degraded(monkeypatch):
    """模型调不通与其他节点一致阻断本轮，而不是带着降级计划逐个构件撞重试。"""

    async def boom(_llm, _messages):
        raise RuntimeError("AllocationQuota.FreeTierOnly: Free quota exhausted")

    monkeypatch.setattr("app.agent.plan.strategy.invoke_llm", boom)
    _strategy, diag = _run(
        request_plan_strategy({**_STATE, "suggested_components": ["door"]})
    )

    assert diag["terminal_model_error"]["category"] == "quota_exhausted"
    assert diag["used_fallback"] is False


def test_transient_parse_failure_degrades(monkeypatch):
    """模型调通了但没给出可用构件：降级继续，不算模型故障。"""

    async def empty_reply(_llm, _messages):
        return _FakeLLMResult('{"kinds": [], "notes": "我不知道"}')

    monkeypatch.setattr("app.agent.plan.strategy.invoke_llm", empty_reply)
    strategy, diag = _run(
        request_plan_strategy({**_STATE, "suggested_components": ["door"]})
    )

    assert strategy.source == "fallback"
    assert [entry.kind for entry in strategy.kinds] == ["door"]
    assert diag["fallback_reason"] == "模型未给出可用构件"
    assert "terminal_model_error" not in diag


def test_unparsable_reply_falls_back(monkeypatch):
    async def garbage(_llm, _messages):
        return _FakeLLMResult("我不确定该怎么规划，请补充需求。")

    async def failed_recovery(*_args, **_kwargs):
        return None, {"error": "恢复失败"}

    monkeypatch.setattr("app.agent.plan.strategy.invoke_llm", garbage)
    monkeypatch.setattr("app.llm.recovery.recover_single_json", failed_recovery)
    strategy, diag = _run(
        request_plan_strategy({**_STATE, "suggested_components": ["door"]})
    )

    assert strategy.source == "fallback"
    assert diag["fallback_reason"] == "模型返回不可解析"


def test_deterministic_strategy_uses_skeleton_suggestions():
    strategy = deterministic_strategy({**_STATE, "suggested_components": ["door", "window"]})

    assert strategy.source == "deterministic"
    assert {entry.kind for entry in strategy.kinds} == {"door", "window"}
