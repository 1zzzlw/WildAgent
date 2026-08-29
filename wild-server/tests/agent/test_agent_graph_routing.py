"""Agent 意图与组件派发的关键回归测试。"""

from types import SimpleNamespace

from app.agent.component_registry import resolve_component_suggestions
from langgraph.graph import END

from app.agent.graph import (
    _classifier_dispatch,
    _dispatch_components,
    _final_validate_dispatch,
    _merge_dispatch,
    generation_recursion_limit,
)
import app.agent.intent_classifier as intent_classifier
from app.agent.intent_classifier import (
    classify_intent,
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


def test_minimal_complexity_skips_component_dispatch():
    result = _dispatch_components({
        "architecture_plan": {"complexity": {"level": "minimal"}},
        "suggested_components": ["door", "window", "roof"],
        "user_message": "生成一面玻璃幕墙",
    })
    assert result == "merge"


def test_completed_deterministic_body_routes_to_second_style_review():
    assert _dispatch_components({
        "deterministic_body_complete": True,
        "suggested_components": [],
    }) == "style_review"


def test_edit_keyword_routes_to_patch_when_scene_exists():
    assert classify_keywords("把正门加宽到 1.2 米", has_current_scene=True) == "edit"
    assert _classifier_dispatch({"intent": "edit"}) == "patch"


def test_generate_routes_to_architecture_plan_first():
    assert _classifier_dispatch({"intent": "generate"}) == "architecture"


def test_invalid_intent_fails_closed_to_read_only_chat():
    assert _classifier_dispatch({"intent": "unknown"}) == "chat"
    assert _classifier_dispatch({}) == "chat"


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

    result = _run_immediate_coroutine(classify_intent(
        "你生成一个建筑的实现思路是什么",
        has_current_scene=False,
        llm=object(),
        recent_messages=[
            {"role": "user", "content": "刚才生成了一座别墅"},
            {"role": "assistant", "content": "方案已完成"},
        ],
        workflow_state="scene_ready",
    ))

    assert result == "chat"
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

    result = _run_immediate_coroutine(classify_intent(
        "生成一个玻璃幕墙商业综合体",
        has_current_scene=False,
        llm=object(),
    ))

    assert result == "generate"
    assert len(calls) == 1


def test_classifier_failure_falls_back_without_generating_meta_question(monkeypatch):
    async def failing_invoke_llm(llm, messages):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(intent_classifier, "invoke_llm", failing_invoke_llm)

    result = _run_immediate_coroutine(classify_intent(
        "你生成一个建筑的实现思路是什么",
        has_current_scene=False,
        llm=object(),
    ))

    assert result == "chat"


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


def test_model_service_failure_never_enters_validation_or_callback():
    state = {
        "status": "failed",
        "terminal_model_error": {"category": "quota_exhausted"},
    }

    assert _merge_dispatch(state) == END
    assert _final_validate_dispatch(state) == END


def test_normal_merge_enters_final_validation():
    assert _merge_dispatch({"status": "validating"}) == "final_validate"


def test_recursion_limit_scales_with_graph_size_and_retry_budget():
    assert generation_recursion_limit(0, 0) == 48
    assert generation_recursion_limit(11, 3) == 50
    assert generation_recursion_limit(0, 0, plan_mode=True) == 88
