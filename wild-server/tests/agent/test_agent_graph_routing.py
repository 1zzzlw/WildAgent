"""意图分类与构件策略的关键回归测试。

图级路由（plan → execute ⇄ replanner）在 `tests/agent/test_plan_graph.py`；
本文件只管两件事：**意图别判错**（误判会走错分支）与**构件策略别放水**
（`resolve_component_suggestions` 既是旧派发链的入口，也是新 plan 策略的安全边界）。
"""

from types import SimpleNamespace

from app.agent.generation.components import resolve_component_suggestions
from langgraph.graph import END

from app.agent.graph import _classifier_dispatch, _final_validate_dispatch, _after_material_plan
import app.agent.routing as intent_classifier
from app.agent.routing import (
    classify_intent_decision,
    classify_keywords,
    fast_path_intent,
    normalize_intent_decision,
)


def _run_immediate_coroutine(coroutine):
    """运行内部 await 会立即完成的测试协程，不依赖事件循环插件。"""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return stopped.value
    raise AssertionError("测试协程没有同步完成")


# ── 图级意图路由 ──


def test_edit_keyword_routes_to_patch_when_scene_exists():
    assert classify_keywords("把正门加宽到 1.2 米", has_current_scene=True) == "edit"
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
    assert route_design_review({"design_review_status": "approved"}) == "skeleton"
    assert route_design_review({"design_review_status": "revise", "status": "failed"}) == "__end__"


def test_material_plan_waits_for_concrete_design_review():
    assert _after_material_plan({}) == "design_review"


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


# ── 意图分类：关键词与快速路径 ──


def test_edit_like_request_does_not_edit_without_scene():
    assert classify_keywords("把正门加宽到 1.2 米", has_current_scene=False) == "chat"


def test_fast_path_short_circuits_clear_generate():
    assert fast_path_intent("生成一个欧式别墅", has_current_scene=False) == "generate"
    assert fast_path_intent("帮我设计一个小木屋", has_current_scene=False) == "generate"


def test_fast_path_short_circuits_clear_edit():
    assert fast_path_intent("把正门加宽到 1.2 米", has_current_scene=True) == "edit"


def test_fast_path_defers_ambiguous_inputs_to_llm():
    # 无关键词 → 交给 LLM（可能是聊天）
    assert fast_path_intent("你好", has_current_scene=False) is None
    # 生成 + 编辑关键词同时出现 → 交给 LLM
    assert fast_path_intent("把材质改成石材，再生成一栋楼", has_current_scene=True) is None
    # 编辑词但当前没有场景 → 不构成编辑证据，交给 LLM
    assert fast_path_intent("把屋顶改成红色", has_current_scene=False) is None


def test_generation_meta_question_never_enters_keyword_generate_path():
    message = "你生成一个建筑的实现思路是什么"

    assert fast_path_intent(message, has_current_scene=False) is None
    assert classify_keywords(message, has_current_scene=False) == "chat"
    assert classify_keywords("当前建筑为什么这样设计", has_current_scene=True) == "chat"


def test_structured_intent_decision_is_normalized_and_clamped():
    decision = normalize_intent_decision(
        '''{
          "intent": "chat",
          "confidence": 1.4,
          "target": "agent implementation",
          "requires_scene": false,
          "reason": "asks how generation works"
        }''',
        "生成建筑的实现思路是什么",
        has_current_scene=True,
    )

    assert decision.intent == "chat"
    assert decision.confidence == 1.0
    assert decision.source == "llm"


def test_explanatory_question_fails_closed_even_if_model_says_generate():
    structured = normalize_intent_decision(
        '{"intent":"generate","confidence":0.99,"reason":"contains generate"}',
        "你生成一个建筑的的实现思路是什么",
        has_current_scene=True,
    )
    legacy = normalize_intent_decision(
        "GENERATE",
        "当前建筑为什么这样设计",
        has_current_scene=True,
    )

    assert structured.intent == "chat"
    assert legacy.intent == "chat"


def test_classifier_uses_llm_for_generation_meta_question(monkeypatch):
    calls = []

    async def fake_invoke_llm(llm, messages):
        calls.append((llm, messages))
        return SimpleNamespace(content='''{
          "intent":"chat",
          "confidence":0.96,
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
        return SimpleNamespace(content="GENERATE")

    monkeypatch.setattr(intent_classifier, "invoke_llm", fake_invoke_llm)

    result = _run_immediate_coroutine(classify_intent_decision(
        "生成一个玻璃幕墙商业综合体",
        has_current_scene=False,
        llm=object(),
    ))

    assert result.intent == "generate"
    assert len(calls) == 1


def test_classifier_failure_falls_back_without_generating_meta_question(monkeypatch):
    async def failing_invoke_llm(llm, messages):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(intent_classifier, "invoke_llm", failing_invoke_llm)

    result = _run_immediate_coroutine(classify_intent_decision(
        "你生成一个建筑的实现思路是什么",
        has_current_scene=False,
        llm=object(),
    ))

    assert result.intent == "chat"


# ── 构件策略（旧派发链与新 plan 策略共用的安全边界）──


def test_component_suggestions_filter_unknown_and_negated_types():
    assert resolve_component_suggestions(
        ["door", "window", "unknown", "door"],
        "生成一个没有窗的小屋",
    ) == ["door"]


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
