"""真实 architecture 节点的无模型冒烟测试。

为什么必须有这个文件：

`tests/agent/test_agent_graph_execution.py` 把每个节点都替换成桩函数，
所以**节点内部的调用错误永远跑不到**；单元测试又习惯直接按位置参调用被调函数，
从不经过节点里的真实调用点。于是下面这类错误可以全绿通过：

    normalize_architecture_plan(raw, ..., profile=profile)   # 签名是 architecture_profile
    → TypeError: got an unexpected keyword argument 'profile'

真实事故：候选机制清理时改写这个调用点，把位置参改成关键字参时用错了名字。
全量导入扫描查不到（不是导入错误）、图编译查不到（只编译不执行）、
单元测试查不到（没走真实调用点），只有用户真正发起一次生成才崩，
且 `normalize_architecture_plan` 在 `try` 之外，异常直接终止整轮生成。

本文件只打桩模型服务和检索，其余全部走真实代码路径：
体量归一化 → DesignDocument 契约 → resolve_design。
"""

import json
from unittest.mock import patch

import pytest

from app.agent.generation.architecture.workflow import architecture_planner
from app.services.agent_service import agent_service


class _FakeSpecLoader:
    """不打桩就会真的去查 Chroma，测试里没必要。"""

    def load_many(self, *_args, **_kwargs) -> str:
        return ""


class _FakeLLMResult:
    def __init__(self, content: str) -> None:
        self.content = content
        self.token_usage = {"input": 1, "output": 1, "total": 2}


_CANNED_RAW_PLAN = {
    "massing": {"floors": 2},
    "roof": {"type": "gable"},
}


async def _fake_invoke_llm(_llm, _messages):
    return _FakeLLMResult(json.dumps(_CANNED_RAW_PLAN, ensure_ascii=False))


def _node_patches():
    return (
        patch.object(agent_service, "spec_loader", _FakeSpecLoader()),
        patch(
            "app.agent.generation.architecture.workflow.create_llm",
            lambda **_kwargs: object(),
        ),
        patch(
            "app.agent.generation.architecture.workflow.invoke_llm",
            _fake_invoke_llm,
        ),
    )


@pytest.mark.asyncio
async def test_architecture_node_completes_without_llm() -> None:
    """节点必须能端到端跑完，并产出一份可用于审核的总体方案。"""

    spec_loader, create_llm, invoke_llm = _node_patches()
    with spec_loader, create_llm, invoke_llm:
        update = await architecture_planner({"user_message": "生成一个两层别墅"})

    assert "architecture_plan" in update, update
    assert update["architecture_plan"]["massing"]["floors"] == 2
    assert update["architecture_plan"]["roof"]["type"] == "gable"
    assert update["design_review_status"] == "pending"
    assert isinstance(update["design_document"], dict) and update["design_document"]
    assert isinstance(update["resolved_design"], dict) and update["resolved_design"]


@pytest.mark.asyncio
async def test_architecture_node_records_profile_diagnostics() -> None:
    """诊断字段必须来自真实 profile，而不是写死的常量。"""

    spec_loader, create_llm, invoke_llm = _node_patches()
    with spec_loader, create_llm, invoke_llm:
        update = await architecture_planner({"user_message": "生成一个两层欧式别墅"})

    diag = update["architecture_diag"]
    assert diag["profile"] == update["architecture_plan"]["profile"]
    assert diag["profile_label"]
    assert diag["used_fallback"] is False
