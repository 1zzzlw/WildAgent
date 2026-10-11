"""用户粒度从真实图纸节点传到计划；模型不能覆盖用户选择。"""
import json
from types import SimpleNamespace

import pytest

from app.agent.generation.architecture import design_workflow
from app.agent.generation.architecture.profile import DETAIL_LEVEL_GUIDANCE, resolve_complexity_profile
from app.agent.generation.architecture.workflow import architecture_planner
from app.agent.plan.expand import expand_design_markers
from app.agent.prompts.planning import build_architecture_plan_prompt
from app.utils.json_extractor import extract_json_object


@pytest.mark.asyncio
@pytest.mark.parametrize("level", list(DETAIL_LEVEL_GUIDANCE))
async def test_selected_level_survives_model_output_and_reaches_plan(level, monkeypatch):
    raw = extract_json_object(build_architecture_plan_prompt(""))
    raw["complexity"] = {"level": "detailed"}
    raw["components"] = [{"id": "living_sofa", "type": "furniture", "host": "main",
                          "form": {"description": "三人沙发"}, "placement": {"position": [3, 0.2, 4]}}]
    prompts = []

    async def model(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps(raw), token_usage=None)

    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    result = await architecture_planner({"user_message": "设计别墅，客厅需要三人沙发",
                                         "session_id": "detail_test", "detail_level": level})
    assert not result.get("error"), result
    assert result["design_document"]["decisions"]["complexity"]["level"] == level
    assert DETAIL_LEVEL_GUIDANCE[level] in prompts[0]
    assert "用户明确要求" in prompts[0] and "重复增加门窗数量" in prompts[0]
    plan = expand_design_markers(result)
    assert plan.detail_level == level
    assert any("living_sofa" in item.target["marker_ids"] for item in plan.items)


@pytest.mark.parametrize("value", [None, "", "unknown", [], {}])
def test_invalid_or_absent_selection_defaults_to_medium(value):
    assert resolve_complexity_profile("设计别墅", value)["level"] == "simple"


def test_levels_do_not_change_structural_or_opening_quotas():
    profiles = [resolve_complexity_profile("设计别墅", level) for level in DETAIL_LEVEL_GUIDANCE]
    assert all({k: v for k, v in p.items() if k not in {"level", "reason"}} ==
               {k: v for k, v in profiles[0].items() if k not in {"level", "reason"}} for p in profiles)
    assert "家具逐件或按组合" in profiles[-1]["reason"]
