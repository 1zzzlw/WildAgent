"""自由图纸与局部修订仍保持稳定的字段权限。"""
import json
from types import SimpleNamespace

from app.agent.generation.architecture import design_workflow
from app.agent.generation.architecture.design_blocks import DESIGN_BLOCKS, block_of_field


def test_revision_fields_have_one_owner():
    fields = [f for b in DESIGN_BLOCKS for f in b.fields]
    assert len(fields) == len(set(fields))
    assert block_of_field("roof").name == "roof"


def test_unknown_roof_survives_scoped_revision(monkeypatch):
    prompts = []
    async def model(_llm, messages):
        prompts.append(messages)
        return SimpleNamespace(content=json.dumps({"roof": {"type": "freeform", "description": "曲面屋顶"}}), token_usage=None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    coroutine = design_workflow.draft_design(base_prompt="设计建筑", user_request="改屋顶",
        current_plan={"concept": "保留主体"}, only_blocks=["roof"], allow_design_changes=True)
    try:
        coroutine.send(None)
    except StopIteration as result:
        raw, diag = result.value
    assert raw["roof"]["type"] == "freeform" and diag["model_calls"] == 1
    assert "保留主体" in prompts[0][0]["content"]
