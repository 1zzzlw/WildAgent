"""组件生成节点的**无模型冒烟**，专钉一条曾静默潜伏的 import 缺失。

真实事故（2026-09-22）：`component_workflow.py` 里调用了 `component_rules_source(rag_chars)`
（定义在 `components.py`），但该文件的 import 只带了 `ComponentConfig`，**漏了这个函数**。
后果和 `plan_feedback` 是同型：模块 import 正常、全量导入扫描正常、图编译正常，
只有真跑到那一行才 NameError。它当时被 architecture 节点的更早崩溃挡住了，属于"下一个必炸"。

为什么既有用例没兜住（两个盲区）：
  - `tests/agent/test_plan_chain_e2e.py` 把 `create_component_generator` **整体替换**成桩，
    真实函数体一行都不执行；
  - 全量导入扫描只能证明"模块能 import"，证明不了"函数体能跑"。

所以这条用例只打桩 RAG 与模型，其余走真实代码路径；并**把两个分支都钉住**
（RAG 为空 → `fallback` 注入静态规则；RAG 充足 → `knowledge` 不注入）。
"""

import json
from unittest.mock import patch

import pytest

from app.agent.generation.component_workflow import create_component_generator
from app.agent.generation.components import (
    KNOWLEDGE_SUFFICIENT_CHARS,
    COMPONENT_REGISTRY,
    _COMPONENT_RULES,
)
from app.services.agent_service import agent_service

# `_COMPONENT_RULES["door"]` 的首行片段：只在 fallback 分支才会进 system prompt
_RULE_MARKER = _COMPONENT_RULES["door"].splitlines()[0][:40]

_DOOR_FRAGMENT = [
    {
        "type": "door",
        "id": "door_main",
        "parentWall": "wall_front",
        "from": [1.2, 0.0, 0.0],
        "width": 1.0,
        "height": 2.1,
        "interaction": {"mode": "swing", "hingeSide": "left"},
    }
]


class _FakeSpecLoader:
    """按需返回指定长度的检索文本 —— 用来摆动 `component_rules_source` 的分支。"""

    def __init__(self, text: str = "") -> None:
        self._text = text
        self.last_results: list = []

    def load_many(self, *_args, **_kwargs) -> str:
        return self._text


class _FakeLLMResult:
    def __init__(self, content: str) -> None:
        self.content = content
        self.reasoning = ""
        self.token_usage = {"input": 1, "output": 1, "total": 2}


_CAPTURED_MESSAGES: list[list[dict]] = []


async def _fake_invoke_llm(_llm, messages):
    _CAPTURED_MESSAGES.append(messages)
    return _FakeLLMResult(json.dumps(_DOOR_FRAGMENT, ensure_ascii=False))


def _node_patches(spec_text: str):
    return (
        patch.object(agent_service, "spec_loader", _FakeSpecLoader(spec_text)),
        patch(
            "app.agent.generation.component_workflow.create_llm",
            lambda **_kwargs: object(),
        ),
        patch(
            "app.agent.generation.component_workflow.invoke_llm",
            _fake_invoke_llm,
        ),
    )


def _state() -> dict:
    return {
        "user_message": "在正立面加一樘入户门",
        "skeleton_summary": "单层矩形体量，正立面朝南",
        "architecture_plan": {"massing": {"floors": 1}},
        "design_brief": {"facade_plan": []},
        "plan_item": {"id": "item_door", "kind": "door", "label": "入户门"},
    }


@pytest.mark.asyncio
async def test_component_generator_runs_end_to_end() -> None:
    """节点必须端到端跑完并产出构件分片（这一条就能拦住 `component_rules_source` 的 import 缺失）。"""

    _CAPTURED_MESSAGES.clear()
    spec_loader, create_llm, invoke_llm = _node_patches("")
    node = create_component_generator(COMPONENT_REGISTRY["door"])
    with spec_loader, create_llm, invoke_llm:
        update = await node(_state())

    assert isinstance(update, dict), update
    fragments = update.get("component_fragments")
    assert isinstance(fragments, dict) and fragments.get("door"), update
    assert fragments["door"][0]["id"] == "door_main"


@pytest.mark.asyncio
async def test_component_generator_falls_back_to_static_rules_when_rag_empty() -> None:
    """RAG 为空 → `rules_source == "fallback"`，静态规则必须被注入 system prompt。"""

    _CAPTURED_MESSAGES.clear()
    spec_loader, create_llm, invoke_llm = _node_patches("")
    node = create_component_generator(COMPONENT_REGISTRY["door"])
    with spec_loader, create_llm, invoke_llm:
        await node(_state())

    assert _CAPTURED_MESSAGES, "必须真实调用过一次模型"
    system_prompt = _CAPTURED_MESSAGES[0][0]["content"]
    assert _RULE_MARKER in system_prompt, "RAG 为空时应回退到 _COMPONENT_RULES"


@pytest.mark.asyncio
async def test_component_generator_omits_static_rules_when_rag_sufficient() -> None:
    """RAG 充足 → `rules_source == "knowledge"`，不再注入静态规则（避免两套口径打架）。"""

    _CAPTURED_MESSAGES.clear()
    ample = "知识库构件说明。" * 200
    assert len(ample) >= KNOWLEDGE_SUFFICIENT_CHARS
    spec_loader, create_llm, invoke_llm = _node_patches(ample)
    node = create_component_generator(COMPONENT_REGISTRY["door"])
    with spec_loader, create_llm, invoke_llm:
        await node(_state())

    assert _CAPTURED_MESSAGES, "必须真实调用过一次模型"
    system_prompt = _CAPTURED_MESSAGES[0][0]["content"]
    assert _RULE_MARKER not in system_prompt, "RAG 充足时不应再注入 _COMPONENT_RULES"


@pytest.mark.asyncio
async def test_roof_batch_survives_generation_and_collection():
    from app.agent.generation.assembly_workflow import _collect_fragments

    roofs = [{"type": "roof", "id": f"roof_{i}", "roofType": "gable", "span": 8,
              "depth": 6, "height": 1.5, "thickness": 0.2} for i in range(2)]

    async def invoke(_llm, messages):
        assert "JSON 数组" in messages[0]["content"]
        return _FakeLLMResult(json.dumps(roofs))

    spec_loader, create_llm, _ = _node_patches("")
    with spec_loader, create_llm, patch("app.agent.generation.component_workflow.invoke_llm", invoke):
        result = await create_component_generator(COMPONENT_REGISTRY["roof"])(_state())
    assert result["component_fragments"]["roof"] == roofs
    collected, _ = _collect_fragments(result["component_fragments"])
    assert collected == roofs
    legacy, _ = _collect_fragments({"roof": roofs[0]})
    assert legacy == roofs[:1]
