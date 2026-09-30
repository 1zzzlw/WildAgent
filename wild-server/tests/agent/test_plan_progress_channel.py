"""plan/execute/replanner 的进度播报必须走 `:progress` 通道（守卫测试）。

真实事故（用户报告 2026-09-29）：execute 阶段"进度不实时"——排查结论是
``plan/workflow.py`` 的 4 处 callback 全用**裸节点名**（"plan"/"execute"/"replanner"），
被 ``ws_agent._thinking_channel`` 判成 ``reasoning``（「模型过程」，前端默认折叠），
没有一条走「执行说明」通道 ⇒ 用户看到 execute 步骤条长时间不动。

约定见 ``ws_agent.py:565``：代码写的中文进度句必须带 `":progress"` 后缀。
architecture 节点已有同款守卫（``test_architecture_node_smoke``），本文件把
plan / execute 两个节点补齐，外加一条源码级 tripwire 防止新写的 callback 再漏后缀。
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

import pytest

from app.agent.plan.contracts import PlanItem, PlanKindStrategy, PlanStrategy
from app.agent.plan.workflow import execute_node, plan_node
from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback


def _plan_state() -> dict:
    """最小可展开状态：design_brief 点名一扇门，骨架为空。"""

    return {
        "user_message": "生成一个两层别墅",
        "design_brief": {
            "component_quota": {"door": {"min": 1, "max": 2, "note": "主入口"}},
        },
        "architecture_plan": {"profile": {"id": "custom"}},
        "skeleton_blueprint": {},
    }


async def _collect_progress(seen: list[tuple[str, str]], coro):
    """绑定 reasoning 回调执行节点，返回更新字典。"""

    async def _collect(node: str, text: str) -> None:
        seen.append((node, text))

    token = bind_reasoning_callback(_collect)
    try:
        return await coro
    finally:
        reset_reasoning_callback(token)


def _assert_no_bare_progress_node(seen: list[tuple[str, str]]) -> None:
    bare = [node for node, _text in seen if node in {"plan", "execute", "replanner"}]
    assert not bare, (
        f"进度句用了裸节点名 {bare} → 会被判成 reasoning 通道（前端默认折叠）。"
        "必须带 ':progress' 后缀（ws_agent._thinking_channel 约定）"
    )


@pytest.mark.asyncio
async def test_plan_node_progress_uses_progress_channel() -> None:
    """plan 节点的两条中文进度句都必须带 `:progress` 后缀。"""

    async def _fake_strategy(state, **_kwargs):
        # 模型策略路径不补配额条目，必须显式点名 door 才会派 generate 条目。
        return (
            PlanStrategy(
                kinds=[PlanKindStrategy(kind="door", reason="配额下限要求")],
                source="deterministic",
            ),
            {"strategy_source": "deterministic"},
        )

    seen: list[tuple[str, str]] = []
    with patch("app.agent.plan.workflow.request_plan_strategy", _fake_strategy):
        update = await _collect_progress(
            seen, plan_node(_plan_state())
        )

    assert update.get("plan"), update
    _assert_no_bare_progress_node(seen)
    notes = [text for node, text in seen if node == "plan:progress"]
    assert any("正在把已批准方案拆成可执行的工作条目" in note for note in notes), notes
    assert any("计划已展开" in note for note in notes), notes


@pytest.mark.asyncio
async def test_execute_node_progress_uses_progress_channel() -> None:
    """execute 节点"开始执行 / 逐条完成"两条进度都必须带 `:progress` 后缀。"""

    from app.agent.plan import workflow as plan_workflow

    # 先展开一份真实计划（拿到合法的条目依赖结构），再执行它的 generate 条目。
    seen_plan: list[tuple[str, str]] = []

    async def _fake_strategy(state, **_kwargs):
        # 模型策略路径不补配额条目，必须显式点名 door 才会派 generate 条目。
        return (
            PlanStrategy(
                kinds=[PlanKindStrategy(kind="door", reason="配额下限要求")],
                source="deterministic",
            ),
            {},
        )

    with patch("app.agent.plan.workflow.request_plan_strategy", _fake_strategy):
        plan_update = await _collect_progress(seen_plan, plan_node(_plan_state()))

    state = {**_plan_state(), "plan": plan_update["plan"]}

    async def _fake_execute_one(state, item):
        return (item, {}, "succeeded", [f"{item.id}_artifact"], "产出 1 个片段", [], 5)

    def _fake_reconcile(plan, state):
        return plan, []

    def _fake_consistency(plan, state):
        return plan

    seen: list[tuple[str, str]] = []
    with (
        patch.object(plan_workflow, "_execute_one", _fake_execute_one),
        patch.object(plan_workflow, "reconcile", _fake_reconcile),
        patch.object(plan_workflow, "ensure_artifact_consistency", _fake_consistency),
    ):
        update = await _collect_progress(seen, execute_node(state))

    assert update.get("execute_diag", {}).get("item_ids"), update
    _assert_no_bare_progress_node(seen)
    notes = [text for node, text in seen if node == "execute:progress"]
    assert any("正在执行" in note for note in notes), notes
    assert any("succeeded" in note for note in notes), notes


def test_workflow_source_has_no_bare_progress_callbacks() -> None:
    """源码级 tripwire：workflow.py 里 callback 的第一个字面量节点名必须带 `:progress`。

    拦住"新增的进度提示忘了写后缀"——这是本次事故的根因形态。
    """

    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "app" / "agent" / "plan" / "workflow.py"
    ).read_text(encoding="utf-8")
    bare_calls = re.findall(r'callback\(\s*"(plan|execute|replanner)"', source)
    assert not bare_calls, (
        f"workflow.py 还有 {len(bare_calls)} 处裸节点名 callback：{bare_calls}。"
        "中文进度句必须用 '<node>:progress'（否则前端归入默认折叠的「模型过程」）"
    )
    suffixed = re.findall(r'callback\(\s*"(plan|execute|replanner):progress"', source)
    assert len(suffixed) >= 5, f"进度 callback 数量异常：{suffixed}"


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
