"""Agent 意图与组件派发的关键回归测试。"""

from app.agent.component_registry import resolve_component_suggestions
from langgraph.graph import END

from app.agent.graph import _classifier_dispatch, _dispatch_components, _final_validate_dispatch
from app.agent.intent_classifier import classify_keywords


def test_minimal_complexity_skips_component_dispatch():
    result = _dispatch_components({
        "architecture_plan": {"complexity": {"level": "minimal"}},
        "suggested_components": ["door", "window", "roof"],
        "user_message": "生成一面玻璃幕墙",
    })
    assert result == "merge"


def test_edit_keyword_routes_to_patch_when_scene_exists():
    assert classify_keywords("把正门加宽到 1.2 米", has_current_scene=True) == "edit"
    assert _classifier_dispatch({"intent": "edit"}) == "patch"


def test_generate_routes_to_architecture_plan_first():
    assert _classifier_dispatch({"intent": "generate"}) == "architecture"


def test_edit_like_request_does_not_edit_without_scene():
    assert classify_keywords("把正门加宽到 1.2 米", has_current_scene=False) == "chat"


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
