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
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agent.generation.architecture.workflow import architecture_planner
from app.services.agent_service import agent_service


class _FakeSpecLoader:
    """不打桩就会真的去查 Chroma，测试里没必要。"""

    def load_many(self, *_args, **_kwargs) -> str:
        return ""


#: 分块起草（§1.6）后，同一个桩返回体会被**每个块各取一次**它负责的字段。
#: 所以这里必须把块契约要求的字段都写全：
#: `massing` 块要求 `massing` + `volumes` 同时在，只给 `massing` 会被判"缺少字段"。
_CANNED_RAW_PLAN = {
    "massing": {"width": 12, "depth": 10, "floors": 2},
    "volumes": [
        {
            "id": "v1",
            "role": "primary",
            "x": 0,
            "z": 0,
            "width": 12,
            "depth": 10,
            "start_floor": 1,
            "end_floor": 2,
        }
    ],
    "roof": {"type": "gable"},
}


async def _fake_invoke(_llm, _messages):
    from app.agent.generation.architecture import normalize_architecture_plan
    raw = normalize_architecture_plan(_CANNED_RAW_PLAN, user_message="生成一个两层别墅")
    raw.pop("component_quota")
    raw.pop("required_components")
    raw["concept"] = "测试别墅"
    raw["design_intent"] = {"goals": ["居住"], "selected_systems": ["door", "window", "roof"]}
    return SimpleNamespace(content=json.dumps(raw, ensure_ascii=False), token_usage=None)


def _node_patches():
    # 只替换模型输出和检索，其余使用真实节点代码。
    return (
        patch.object(agent_service, "spec_loader", _FakeSpecLoader()),
        patch(
            "app.agent.generation.architecture.design_workflow.invoke_llm",
            _fake_invoke,
        ),
        patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=object()),
    )


@pytest.mark.asyncio
async def test_architecture_node_completes_without_llm() -> None:
    """节点必须能端到端跑完，并产出一份可用于审核的总体方案。"""

    spec_loader, model_output, model_factory = _node_patches()
    with spec_loader, model_output, model_factory:
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

    spec_loader, model_output, model_factory = _node_patches()
    with spec_loader, model_output, model_factory:
        update = await architecture_planner({"user_message": "生成一个两层欧式别墅"})

    diag = update["architecture_diag"]
    assert diag["profile"] == update["architecture_plan"]["profile"]
    # 档位标签已删（用户决策 2026-09-29）：诊断只报 id，不再有 profile_label。
    assert "profile_label" not in diag
    assert diag["settled"] is True


@pytest.mark.asyncio
async def test_architecture_node_with_reasoning_callback() -> None:
    """**绑定 reasoning 回调**时必须能跑完，且提示文案与语义一致。

    为什么单独一条（真实事故 2026-09-22）：节点里有一段进度提示长这样

        on_reasoning_delta = get_reasoning_callback()
        if on_reasoning_delta:
            if plan_feedback:            # ← 计划层退场后此变量已无定义 → NameError
                ...

    `plan_feedback` 的赋值随计划层一起被删掉了，判断却留着。上面两条用例
    **从不绑定 reasoning 回调**，`get_reasoning_callback()` 返回 None，整块被跳过，
    于是 NameError 对它们完全隐身 —— 全量导入扫描、图编译、单测三道都查不到，
    只有线上开了 thinking（有回调）走到这一行才炸，用户看到"意图分类之后直接报错"。

    所以这条用例的价值不在断言业务结果，而在**强制进入那个被 runtime ContextVar 守卫的分支**。
    """

    from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback

    seen: list[tuple[str, str]] = []

    async def _collect(node: str, text: str) -> None:
        seen.append((node, text))

    spec_loader, model_output, model_factory = _node_patches()
    token = bind_reasoning_callback(_collect)
    try:
        with spec_loader, model_output, model_factory:
            update = await architecture_planner({"user_message": "生成一个两层别墅"})
    finally:
        reset_reasoning_callback(token)

    assert "architecture_plan" in update, update
    #  进度叙述必须带 `:progress` 后缀（见 `ws_agent._thinking_channel`）：不带就会被前端
    # 归到「模型过程」，而 `architecture` 的「模型过程」是模型的原始 CoT —— 两种不能混。
    notes = [text for node, text in seen if node == "architecture:progress"]
    assert notes, "绑定回调后节点必须至少推一条 architecture 进度提示（带 :progress 后缀）"
    assert any("形成完整建筑图纸" in note for note in notes), notes


@pytest.mark.asyncio
async def test_architecture_node_with_reasoning_callback_and_feedback() -> None:
    """带 `design_feedback` 时走"调整"文案分支（同样必须绑定回调才进得去）。"""

    from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback

    seen: list[tuple[str, str]] = []

    async def _collect(node: str, text: str) -> None:
        seen.append((node, text))

    spec_loader, model_output, model_factory = _node_patches()
    token = bind_reasoning_callback(_collect)
    try:
        with spec_loader, model_output, model_factory:
            update = await architecture_planner(
                {
                    "user_message": "生成一个两层别墅",
                    "design_feedback": "把屋顶改成四坡",
                }
            )
    finally:
        reset_reasoning_callback(token)

    assert "architecture_plan" in update, update
    notes = [text for node, text in seen if node == "architecture:progress"]
    assert any("形成完整建筑图纸" in note for note in notes), notes
