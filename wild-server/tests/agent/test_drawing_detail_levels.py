"""用户粒度从真实图纸节点传到计划；模型不能覆盖用户选择。"""
import json
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import design_workflow
from app.contracts.generation_options import DETAIL_LEVEL_GUIDANCE
from app.agent.generation.architecture.profile import resolve_complexity_profile
from app.agent.generation.architecture.workflow import architecture_planner
from app.agent.plan.expand import expand_design_markers
from app.design.resolver import architecture_plan_from_document
from tests.plan.test_drawing_implementation import drawing


@pytest.mark.asyncio
@pytest.mark.parametrize("level", list(DETAIL_LEVEL_GUIDANCE))
@pytest.mark.parametrize("thinking", [False, True, None])
async def test_selected_level_survives_model_output_and_reaches_plan(level, thinking, monkeypatch):
    raw = architecture_plan_from_document(drawing())
    raw["complexity"] = {"level": "detailed"}
    raw["components"] = [{"id": "living_sofa", "type": "furniture", "host": "main",
                          "form": {"description": "三人沙发"}, "placement": {"position": [3, 0.2, 4]}}]
    prompts, options = [], []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(raw), token_usage=None)

    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: options.append(kwargs))
    state = {"user_message": "设计别墅，客厅需要三人沙发",
             "session_id": "detail_test", "detail_level": level}
    if thinking is not None:
        state["thinking_mode"] = thinking
    result = await architecture_planner(state)
    assert not result.get("error"), result
    assert options[0]["enable_thinking"] is (thinking is not False)
    assert result["design_document"]["decisions"]["complexity"]["level"] == level
    assert DETAIL_LEVEL_GUIDANCE[level] in prompts[0]
    assert "用户明确要求" in prompts[0] and "重复增加门窗数量" in prompts[0]
    plan = expand_design_markers(result)
    assert plan.detail_level == level
    assert any("living_sofa" in item.target["marker_ids"] for item in plan.items)


@pytest.mark.parametrize("value", [None, "", "unknown", [], {}])
def test_invalid_or_absent_selection_defaults_to_minimal(value):
    assert resolve_complexity_profile(value)["level"] == "minimal"


def test_levels_do_not_change_structural_or_opening_quotas():
    profiles = [resolve_complexity_profile(level) for level in DETAIL_LEVEL_GUIDANCE]
    assert all({k: v for k, v in p.items() if k not in {"level", "reason"}} ==
               {k: v for k, v in profiles[0].items() if k not in {"level", "reason"}} for p in profiles)
    assert "家具逐件或按组合" in profiles[-1]["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["生成一个古典柱廊殿宇", "生成一个别墅", "生成一个现代新中式别墅"])
async def test_classifier_does_not_inject_recommended_styles_or_reuse_old_hints(message, monkeypatch):
    from app.agent.intent import workflow

    async def classify(*_args, **_kwargs):
        return SimpleNamespace(intent="generate", target="建筑", target_kind="architecture", profile="custom",
                               requires_scene=False, reason="test", source="test", model_error=None)

    monkeypatch.setattr(workflow, "classify_intent_decision", classify)
    result = await workflow.classifier_node({"user_message": message, "style_preference": ["modern", "chinese"]})
    assert result["style_preference"] == []
    assert result["intent_target_kind"] == "architecture"


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed", "obsolete", None])
@pytest.mark.parametrize("thinking", [False, True, None])
async def test_graph_keeps_node_thinking_independent_of_detail_level(level, thinking, monkeypatch):
    from langgraph.graph import END, START, StateGraph
    from app.agent.intent import workflow
    from app.agent.state import GenerationInput, GenerationState

    async def classify(*_args, **_kwargs):
        return SimpleNamespace(
            intent="generate", target="test", target_kind="object", profile="custom",
            requires_scene=False, reason="test", source="test", model_error=None,
        )

    monkeypatch.setattr(workflow, "classify_intent_decision", classify)
    graph = StateGraph(GenerationState, input_schema=GenerationInput)
    graph.add_node("classifier", workflow.classifier_node)
    graph.add_edge(START, "classifier")
    graph.add_edge("classifier", END)
    state = {"user_message": "设计一个物件", "detail_level": level}
    if thinking is not None:
        state["thinking_mode"] = thinking
    result = await graph.compile().ainvoke(state)
    assert "thinking_mode" in GenerationInput.__annotations__
    assert result["thinking_mode"] is (thinking is not False)
    assert result["detail_level"] == (level if level in DETAIL_LEVEL_GUIDANCE else "minimal")
