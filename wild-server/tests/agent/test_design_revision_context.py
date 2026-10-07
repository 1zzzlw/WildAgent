"""局部修订的真实调用上下文与并行块隔离。模型与检索使用受控替身。"""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
from app.agent.generation.architecture.design_workflow import build_block_prompt, draft_design_blocks
from app.agent.generation.architecture.convergence import converge_design
from app.agent.compiler import CompileDefect


MODULE = "app.agent.generation.architecture.design_workflow"
CONVERGENCE = "app.agent.generation.architecture.convergence"


def prompt_context(prompt):
    return json.loads(prompt.split("```json\n", 1)[1].split("\n```", 1)[0])


def test_large_context_remains_valid_json_including_last_host():
    plan = {"volumes": [{"id": "last_host", "note": "x" * 5000}], "roof": {"type": "flat"}}
    prompt = build_block_prompt("BASE", BLOCK_BY_NAME["roof"], plan)
    assert prompt_context(prompt) == plan


def test_roof_only_revision_reads_baseline_but_returns_only_its_fields():
    baseline = {"massing": {"floors": 2}, "volumes": [{"id": "main"}],
                "roof": {"type": "flat"}, "components": [], "material_plan": {"roles": []}}
    original = deepcopy(baseline)
    prompts = []

    async def invoke(_llm, messages):
        prompts.append(messages[0]["content"])
        return SimpleNamespace(content=json.dumps({"roof": {"type": "gable"}, "volumes": []}), token_usage=None)

    async def knowledge(*_args):
        return "", {}

    with patch(f"{MODULE}.retrieve_block_knowledge", knowledge), \
         patch(f"{MODULE}.create_llm", return_value=object()), \
         patch(f"{MODULE}.invoke_llm", invoke):
        draft, diag = asyncio.run(draft_design_blocks(
            base_prompt="BASE", user_request="修改屋顶", thinking_mode=False,
            only_blocks=["roof"], current_plan=baseline, allow_probe=False,
        ))
    assert prompt_context(prompts[0]) == baseline
    assert draft == {"roof": {"type": "gable"}}
    assert baseline == original
    assert diag["unsettled_blocks"] == []


def test_parallel_blocks_read_snapshot_even_when_knowledge_returns_late():
    baseline = {"massing": {"floors": 2}, "volumes": [{"id": "main"}]}

    async def run():
        facade_finished = asyncio.Event()
        seen = {}

        async def knowledge(block, _request):
            if block.name == "roof":
                await facade_finished.wait()
            return "KB", {}

        async def invoke(_llm, messages):
            prompt = messages[0]["content"]
            name = "roof" if "`roof` 块" in prompt else "facade"
            seen[name] = prompt_context(prompt)
            if name == "facade":
                facade_finished.set()
                output = {"facades": {"front": {"bays": 1, "ground_pattern": ["door"], "upper_pattern": ["window"]}}}
            else:
                output = {"roof": {"type": "flat"}}
            return SimpleNamespace(content=json.dumps(output), token_usage=None)

        with patch(f"{MODULE}.retrieve_block_knowledge", knowledge), \
             patch(f"{MODULE}.create_llm", return_value=object()), \
             patch(f"{MODULE}.invoke_llm", invoke):
            draft, _ = await draft_design_blocks(
                base_prompt="BASE", user_request="修订", thinking_mode=False,
                only_blocks=["facade", "roof"], current_plan=baseline, allow_probe=False,
            )
        assert seen["facade"] == seen["roof"] == baseline
        assert set(draft) == {"facades", "roof"}

    asyncio.run(run())


def test_second_revision_uses_previous_accepted_plan_without_raw_plan():
    initial = {"massing": {"floors": 2}, "roof": {"type": "flat"}, "facades": {"kept": True}}
    calls = []
    defect = CompileDefect(code="test", severity="error", target="roof", evidence="roof", design_field="decisions.roof")
    remaining = [[defect], [defect], []]

    def compile_plan(_plan, **_kwargs):
        return SimpleNamespace(defects=remaining.pop(0))

    async def draft(**kwargs):
        calls.append(deepcopy(kwargs["current_plan"]))
        return {"roof": {"type": "gable" if len(calls) == 1 else "hip"}}, {}

    with patch(f"{CONVERGENCE}.compile_design", compile_plan), \
         patch(f"{CONVERGENCE}.draft_design_blocks", draft), \
         patch("app.agent.generation.architecture.normalize_architecture_plan", side_effect=lambda value, **kw: deepcopy(value)):
        outcome = asyncio.run(converge_design(
            plan=initial, raw_plan=None, user_message="修改屋顶", complexity_profile=None,
            architecture_profile=None, thinking_mode=False,
        ))
    assert calls[0]["massing"] == initial["massing"]
    assert calls[1]["roof"] == {"type": "gable"}
    assert outcome.plan["facades"] == initial["facades"]
    assert initial["roof"] == {"type": "flat"}
