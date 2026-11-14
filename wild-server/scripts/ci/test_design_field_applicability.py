"""回放用户原始图纸；确定性协议处理不消耗额外模型修订。"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.design.contracts import RoofDecision, RoofVolumeOverride


def source_plan():
    return json.loads((Path(__file__).parent / "fixtures/architecture-parameter-draft.json").read_text("utf-8-sig"))


@pytest.mark.parametrize("kind", ["flat", "hip", "dome", "chinese_curved", "chinese_pagoda", "none", "open"])
@pytest.mark.parametrize("axis", [None, "none"])
def test_unused_roof_direction_uses_compatible_default_without_mutating_input(kind, axis):
    source = {"type": kind, "ridge_axis": axis}
    before = deepcopy(source)
    assert RoofDecision.model_validate(source).ridge_axis == "x"
    assert source == before


@pytest.mark.parametrize("source", [
    {"type": "gable", "ridge_axis": "none"},
    {"type": "custom_roof", "ridge_axis": "none"},
    {"type": "flat", "ridge_axis": "none", "volumes": [{"volume": "main", "type": "gable"}]},
    {"type": "flat", "ridge_axis": "none", "volumes": [RoofVolumeOverride(volume="main", type="gable")]},
    {"type": "flat", "ridge_axis": "invalid"},
])
def test_applicable_or_unknown_roof_direction_stays_strict(source):
    with pytest.raises(ValidationError):
        RoofDecision.model_validate(source)


@pytest.mark.parametrize("axis", ["x", "z"])
def test_existing_explicit_axis_is_preserved(axis):
    assert RoofDecision.model_validate({"type": "flat", "ridge_axis": axis}).ridge_axis == axis


@pytest.mark.parametrize("needs_design_choice", [False, True])
def test_original_output_replays_through_actual_architecture_node(monkeypatch, needs_design_choice):
    from app.agent.generation.architecture import workflow, design_workflow
    from app.llm.invocation import LlmResult
    from app.services.agent_service import agent_service

    source = source_plan()
    if needs_design_choice:
        source["roof"]["type"] = "gable"
        source["roof"]["volumes"][0]["type"] = "gable"
    calls, repair_queries = [], []
    def repair_rules(queries, **_kwargs):
        repair_queries.extend(queries)
        return "局部字段契约"
    monkeypatch.setattr(agent_service.spec_loader, "load_many_result", lambda *_a, **_kw: SimpleNamespace(text="", hits=[]))
    monkeypatch.setattr(agent_service.spec_loader, "load_many", repair_rules)
    monkeypatch.setattr(workflow, "get_reasoning_callback", lambda: None)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **_kwargs: object())
    async def reply(_model, messages, **_kwargs):
        calls.append(messages)
        content = source if len(calls) == 1 else {"operations": [{"op": "replace", "path": "/roof/ridge_axis", "value": "x"}]}
        return LlmResult(content=json.dumps(content, ensure_ascii=False))
    monkeypatch.setattr(design_workflow, "invoke_llm", reply)
    result = asyncio.run(workflow.architecture_planner({"user_message": "生成一个别墅", "detail_level": "minimal",
        "intent_profile": "villa", "session_id": "design-replay", "thinking_mode": False}))
    assert result.get("error") is None
    assert result["architecture_diag"]["settled"] is True
    assert result["architecture_diag"]["model_calls"] == len(calls) == (2 if needs_design_choice else 1)
    document = result["design_document"]
    assert document["decisions"]["roof"]["ridge_axis"] == "x"
    assert document["decisions"]["massing"]["width"] == 12
    assert document["decisions"]["massing"]["depth"] == 10
    assert result["resolved_design"]["warnings"], "房间缺少内墙的警告必须保留"
    assert result["architecture_plan"]["components"][0]["placement"]["offset"] == 3.75
    if needs_design_choice:
        assert len(repair_queries) == 1, "字段修订只检索当前字段协议，不重复加载粒度和总体设计流程"
        assert repair_queries[0].metadata_filter == {"entity_name": "architecture_design_expression"}
    else:
        assert repair_queries == []
        changes = [c for t in document["rule_trace"] for c in t["changes"]]
        change = next(c for c in changes if c["path"] == "/decisions/roof/ridge_axis")
        assert change["before"] == "none" and change["after"] == "x"
        assert change["category"] == "protocol" and change["semantic_change"] is False


def test_prompt_uses_shared_roof_field_description():
    from app.agent.prompts.planning import build_architecture_plan_prompt
    prompt = build_architecture_plan_prompt("", "villa", {"level": "minimal"})
    assert RoofDecision.model_fields["ridge_axis"].description in prompt
    assert "审核前" not in prompt and "校验和审核" not in prompt
