"""定向修订共享完整设计上下文，字段权限不产生额外设计循环。"""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.generation.architecture.design_workflow import draft_design_blocks


MODULE = "app.agent.generation.architecture.design_workflow"


def test_roof_only_revision_reads_baseline_but_returns_only_its_fields():
    baseline = {"massing": {"floors": 2}, "volumes": [{"id": "main"}],
                "roof": {"type": "flat"}, "components": [], "material_plan": {"roles": []}}
    original = deepcopy(baseline)
    prompts = []

    async def invoke(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps({"roof": {"type": "gable"}}), token_usage=None)

    with patch(f"{MODULE}.create_llm", return_value=object()), \
         patch(f"{MODULE}.invoke_llm", invoke):
        draft, diag = asyncio.run(draft_design_blocks(
            base_prompt="BASE", user_request="修改屋顶", thinking_mode=False,
            only_blocks=["roof"], current_plan=baseline, allow_design_changes=True,
        ))
    assert json.dumps(baseline, ensure_ascii=False) in prompts[0]
    assert draft == {"roof": {"type": "gable"}}
    assert baseline == original
    assert diag["settled"] is True


def test_multiple_revision_fields_use_one_model_call():
    baseline = {"massing": {"floors": 2}, "volumes": [{"id": "main"}]}
    calls = []
    async def invoke(_llm, messages):
        calls.append(messages)
        return SimpleNamespace(content=json.dumps({"roof": {"type": "flat"},
            "facades": {"front": {"bays": 1, "ground_pattern": ["door"], "upper_pattern": ["window"]}}}), token_usage=None)
    with patch(f"{MODULE}.create_llm", return_value=object()), \
         patch(f"{MODULE}.invoke_llm", invoke):
        draft, diag = asyncio.run(draft_design_blocks(base_prompt="BASE", user_request="修订",
            only_blocks=["facade", "roof"], current_plan=baseline))
    assert set(draft) == {"facades", "roof"}
    assert diag["model_calls"] == len(calls) == 1
