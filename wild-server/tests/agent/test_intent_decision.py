"""意图输出解析与字段约定；不加载模型或工作流运行时。"""

from dataclasses import asdict

import pytest

from app.agent.intent.decision import _normalize_profile, normalize_intent_decision


def test_edit_like_request_does_not_edit_without_scene():
    decision = normalize_intent_decision(
        '{"intent":"edit"}', "把正门加宽到 1.2 米", has_current_scene=False,
    )
    assert decision.intent == "chat"
    assert decision.target == "missing_scene"


def test_structured_intent_decision_is_normalized():
    decision = normalize_intent_decision(
        '''{
          "intent": "chat",
          "target": "agent implementation",
          "requires_scene": false,
          "reason": "asks how generation works"
        }''',
        "生成建筑的实现思路是什么",
        has_current_scene=True,
    )

    assert decision.intent == "chat"
    assert "confidence" not in asdict(decision)
    assert decision.source == "llm"


def test_explanatory_question_fails_closed_even_if_model_says_generate():
    structured = normalize_intent_decision(
        '{"intent":"generate","reason":"contains generate"}',
        "你生成一个建筑的的实现思路是什么",
        has_current_scene=True,
    )
    assert structured.intent == "chat"


def test_profile_label_is_an_open_set_not_a_code_whitelist():
    """防回归（2026-10-08 用户决策："不要写成白名单，全部由 LLM 控制"）。

    代码只负责把模型给的标签清成 slug，**不校验词表**：认不出的值原样透传，
    只有缺失/非法才退 custom。
    """

    assert _normalize_profile("Ziggurat") == "ziggurat"
    assert _normalize_profile("villa 大宅") == "villa"
    assert _normalize_profile("") == "custom"
    assert _normalize_profile(None) == "custom"
    assert _normalize_profile("x" * 99) == "x" * 40


@pytest.mark.parametrize("raw", [
    "GENERATE", "EDIT", "CHAT", "", "not json", "{}",
    '{"intent":"unknown","reason":"GENERATE"}',
])
def test_invalid_output_is_rejected(raw):
    with pytest.raises(ValueError):
        normalize_intent_decision(raw, "生成一个别墅", False)
