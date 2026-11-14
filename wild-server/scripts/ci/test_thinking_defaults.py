"""思考开关只控制设计；规划和构件实现对所有粒度均关闭。"""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.agent.plan.contracts import PlanItem
from app.agent.plan.handlers import build_execution_context


@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed"])
@pytest.mark.parametrize("choice", [None, False, True])
def test_component_thinking_is_off_even_when_design_thinking_is_on(level, choice):
    state = {"detail_level": level}
    if choice is not None:
        state["thinking_mode"] = choice
    context = build_execution_context(state, PlanItem(id="generate_test", op="generate"))
    assert context["thinking_mode"] is False


@pytest.mark.parametrize("choice", [None, False, True])
def test_classifier_preserves_only_explicit_design_thinking(monkeypatch, choice):
    from app.agent.intent import workflow
    async def classify(*_args, **_kwargs):
        return SimpleNamespace(intent="generate", target="别墅", target_kind="architecture",
                               profile="villa", requires_scene=False, reason="生成", source="llm")
    monkeypatch.setattr(workflow, "classify_intent_decision", classify)
    state = {"user_message": "别墅", "detail_level": "detailed"}
    if choice is not None:
        state["thinking_mode"] = choice
    result = asyncio.run(workflow.classifier_node(state))
    assert result["thinking_mode"] is (choice is True)


@pytest.mark.parametrize("choice", [None, False, True])
def test_architecture_model_uses_the_design_switch(monkeypatch, choice):
    from app.agent.generation.architecture import design_workflow as workflow
    from app.llm.invocation import LlmResult
    settings = []
    monkeypatch.setattr(workflow, "create_llm", lambda **kwargs: settings.append(kwargs) or object())
    async def reply(*_args, **_kwargs):
        return LlmResult(content=json.dumps({"massing": {}, "volumes": []}))
    monkeypatch.setattr(workflow, "invoke_llm", reply)
    asyncio.run(workflow.draft_design(base_prompt="图纸", user_request="别墅", thinking_mode=choice is True))
    assert settings == [{"enable_thinking": choice is True, "streaming": False}]


@pytest.mark.parametrize("choice", [None, False, True, "true"])
def test_object_design_also_uses_only_the_design_switch(monkeypatch, choice):
    from app.agent.generation.objects import workflow
    from app.llm.invocation import LlmResult
    settings = []
    monkeypatch.setattr(workflow, "_furniture_spec", lambda _loader: "")
    monkeypatch.setattr(workflow, "get_reasoning_callback", lambda: None)
    monkeypatch.setattr(workflow, "create_llm", lambda **kwargs: settings.append(kwargs) or object())
    async def reply(*_args, **_kwargs):
        return LlmResult(content=json.dumps({"kind": "object", "concept": "桌子", "objects": [{
            "kind": "furniture", "subtype": "table", "count": 1, "width": 1.2, "depth": .7, "height": .75,
            "material": "wood", "placement": "居中"}]}))
    monkeypatch.setattr(workflow, "invoke_llm", reply)
    result = asyncio.run(workflow.object_planner({"user_message": "一张桌子", "thinking_mode": choice,
                                                 "session_id": "thinking-object"}))
    assert result["design_document"]["decisions"]["kind"] == "object"
    assert result["object_design_diag"]["used_fallback"] is False
    assert settings == [{"enable_thinking": choice is True, "streaming": False}]
