"""意图分类与构件策略的关键回归测试。

图级路由（plan → execute ⇄ replanner）在 `tests/agent/test_plan_graph.py`；
本文件只管两件事：**意图别判错**（误判会走错分支）与**构件策略别放水**
（`resolve_component_suggestions` 既是旧派发链的入口，也是新 plan 策略的安全边界）。
"""

from types import SimpleNamespace

import pytest

from app.agent.generation.component.registry import resolve_component_suggestions
from langgraph.graph import END

from app.agent.graph import (
    _after_material_plan,
    _classifier_dispatch,
    _final_validate_dispatch,
)
import app.agent.intent.classify as intent_classifier
from app.agent.intent.workflow import classifier_node
from app.agent.intent.classify import classify_intent_decision


def _run_immediate_coroutine(coroutine):
    """运行内部 await 会立即完成的测试协程，不依赖事件循环插件。"""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return stopped.value
    raise AssertionError("测试协程没有同步完成")


# ── 图级意图路由 ──


def test_edit_routes_to_patch_when_scene_exists():
    assert _classifier_dispatch({"intent": "edit"}) == "patch"


def test_generate_routes_to_architecture_plan_first():
    assert _classifier_dispatch({"intent": "generate"}) == "architecture"


def test_generate_with_object_target_routes_to_object_chain():
    """`intent` 只决定"要不要现在产出"，`target_kind` 才决定产出什么。

    缺失 `target_kind` 时必须回落到建筑（旧语料与旧状态都没有这个字段），
    否则一次字段缺失就会把建筑需求送进只做物件的链路。
    """

    assert _classifier_dispatch(
        {"intent": "generate", "intent_target_kind": "object"}
    ) == "object_design"
    assert _classifier_dispatch(
        {"intent": "generate", "intent_target_kind": "architecture"}
    ) == "architecture"
    assert _classifier_dispatch({"intent": "generate"}) == "architecture"


def test_target_kind_is_ignored_for_non_generate_intents():
    """改场景/问答不走方案链：它们不需要重出一份方案。"""

    assert _classifier_dispatch({"intent": "edit", "intent_target_kind": "object"}) == "patch"
    assert _classifier_dispatch({"intent": "chat", "intent_target_kind": "object"}) == "chat"


def test_design_review_returns_to_the_chain_that_produced_the_document():
    """审图打回时必须回到产出该方案的链路，否则物件方案会被当作建筑方案重算。

    判定依据刻意取**文档自身的判别字段**而不是意图字段：修订轮次的意图字段可能
    缺失或过期，而"这份文档是谁产出的"永远写在 `decisions.kind` 里。
    """

    from app.agent.nodes.design_review_node import route_design_review

    def state(kind: str) -> dict:
        return {
            "design_review_status": "revise",
            "design_document": {"decisions": {"kind": kind}},
        }

    assert route_design_review(state("object")) == "object_design"
    assert route_design_review(state("architecture")) == "architecture"
    # 没有文档时（例如审图节点尚未写回）回落到建筑链，与 `_classifier_dispatch` 同一默认。
    assert route_design_review({"design_review_status": "revise"}) == "architecture"
    # 建筑批准后展开标记任务；物件批准后留在 skeleton。
    assert route_design_review({"design_review_status": "approved"}) == "plan"
    assert route_design_review({
        "design_review_status": "approved",
        "architecture_plan": {"target_kind": "object"},
    }) == "skeleton"
    assert route_design_review({"design_review_status": "revise", "status": "failed"}) == "__end__"


def test_material_plan_hands_the_design_directly_to_review():
    assert _after_material_plan({}) == "design_review"
    assert _after_material_plan({"status": "failed"}) == "__end__"


def test_invalid_intent_fails_closed_to_read_only_chat():
    assert _classifier_dispatch({"intent": "unknown"}) == "chat"
    assert _classifier_dispatch({}) == "chat"


def test_model_service_failure_never_enters_validation_or_callback():
    state = {
        "status": "failed",
        "terminal_model_error": {"category": "quota_exhausted"},
    }

    assert _final_validate_dispatch(state) == END


def test_retry_budget_is_per_target_not_a_global_round_cutoff():
    state = {
        "status": "partial",
        "retry_count": 3,
        "max_retries": 3,
        "component_retry_counts": {"old_window": 3},
        "failed_components": [{"component_id": "new_roof"}],
    }

    assert _final_validate_dispatch(state) == "callback"

    state["component_retry_counts"]["new_roof"] = 3
    assert _final_validate_dispatch(state) == END


# ── 意图分类与模型故障 ──


def test_classifier_uses_llm_for_generation_meta_question(monkeypatch):
    calls = []

    async def fake_invoke_llm(llm, messages):
        calls.append((llm, messages))
        return SimpleNamespace(content='''{
          "intent":"chat",
          "target":"agent implementation",
          "requires_scene":false,
          "reason":"asks for implementation approach"
        }''')

    monkeypatch.setattr(intent_classifier, "invoke_llm", fake_invoke_llm)

    result = _run_immediate_coroutine(classify_intent_decision(
        "你生成一个建筑的实现思路是什么",
        has_current_scene=False,
        llm=object(),
        recent_messages=[
            {"role": "user", "content": "刚才生成了一座别墅"},
            {"role": "assistant", "content": "方案已完成"},
        ],
        workflow_state="scene_ready",
    ))

    assert result.intent == "chat"
    assert len(calls) == 1
    classifier_input = calls[0][1][1]["content"]
    assert "刚才生成了一座别墅" in classifier_input
    assert "scene_ready" in classifier_input


def test_classifier_still_uses_llm_for_clear_generation_request(monkeypatch):
    calls = []

    async def fake_invoke_llm(llm, messages):
        calls.append((llm, messages))
        return SimpleNamespace(content='{"intent":"generate","target_kind":"architecture"}')

    monkeypatch.setattr(intent_classifier, "invoke_llm", fake_invoke_llm)

    result = _run_immediate_coroutine(classify_intent_decision(
        "生成一个玻璃幕墙商业综合体",
        has_current_scene=False,
        llm=object(),
    ))

    assert result.intent == "generate"
    assert len(calls) == 1


def test_classifier_failure_stops_without_generating_meta_question(monkeypatch):
    async def failing_invoke_llm(llm, messages):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(intent_classifier, "invoke_llm", failing_invoke_llm)

    result = _run_immediate_coroutine(classify_intent_decision(
        "你生成一个建筑的实现思路是什么",
        has_current_scene=False,
        llm=object(),
    ))

    assert result.intent == "chat"
    assert result.model_error["terminal_current_run"] is True
    assert result.source == "llm"


@pytest.mark.parametrize("raw", [
    "GENERATE", "EDIT", "CHAT", "", "not json", "{}",
    '{"intent":"unknown","reason":"GENERATE"}',
])
def test_invalid_classifier_output_stops_before_downstream_nodes(raw, monkeypatch):
    calls = []

    async def fake_invoke_llm(llm, messages):
        calls.append(messages)
        return SimpleNamespace(content=raw)

    monkeypatch.setattr(intent_classifier, "create_llm", lambda **kwargs: object())
    monkeypatch.setattr(intent_classifier, "invoke_llm", fake_invoke_llm)

    result = _run_immediate_coroutine(classifier_node({"user_message": "生成一个别墅"}))

    assert len(calls) == 1
    assert result["status"] == "failed"
    assert result["terminal_model_error"]["terminal_current_run"] is True
    assert result["error"]
    assert _classifier_dispatch(result) == END


@pytest.mark.parametrize("failure, category", [
    (RuntimeError("Free quota exhausted"), "quota_exhausted"),
    (RuntimeError("Error code: 401 - invalid api key"), "authentication"),
    (TimeoutError(), "transport_error"),
])
def test_classifier_service_failure_stops_without_keyword_fallback(failure, category, monkeypatch):
    calls = []

    async def failing_invoke_llm(llm, messages):
        calls.append(messages)
        raise failure

    monkeypatch.setattr(intent_classifier, "create_llm", lambda **kwargs: object())
    monkeypatch.setattr(intent_classifier, "invoke_llm", failing_invoke_llm)

    result = _run_immediate_coroutine(classifier_node({"user_message": "生成一个别墅"}))

    assert len(calls) == 1
    assert result["intent"] == "chat"
    assert result["intent_source"] == "llm"
    assert result["status"] == "failed"
    assert result["terminal_model_error"]["category"] == category
    assert result["error"]
    assert _classifier_dispatch(result) == END


# ── 构件策略（旧派发链与新 plan 策略共用的安全边界）──


def test_component_suggestions_keep_unknown_and_drop_negated_types():
    """开放集（2026-09-29）：未知类型保留（generic 通道尝试），否定词照常生效。"""
    assert resolve_component_suggestions(
        ["door", "window", "unknown", "door"],
        "生成一个没有窗的小屋",
    ) == ["door", "unknown"]


def test_empty_suggestions_keep_base_components_and_explicit_extras():
    assert resolve_component_suggestions([], "生成一个带烟囱的房子") == [
        "door",
        "window",
        "roof",
        "chimney",
    ]


def test_approved_minimum_quota_is_always_dispatched():
    assert resolve_component_suggestions(
        ["door", "window", "roof"],
        "生成一栋高层住宅塔楼",
        {
            "door": {"min": 1, "max": 4},
            "light": {"min": 2, "max": 8},
            "chimney": {"min": 0, "max": 1},
        },
    ) == ["door", "window", "roof", "light"]


def test_balcony_does_not_duplicate_embedded_railing():
    assert resolve_component_suggestions(
        ["balcony", "railing"],
        "生成一个带阳台的房子",
    ) == ["balcony"]
    assert resolve_component_suggestions(
        ["balcony", "railing"],
        "生成一个带阳台和独立护栏的房子",
    ) == ["balcony", "railing"]
