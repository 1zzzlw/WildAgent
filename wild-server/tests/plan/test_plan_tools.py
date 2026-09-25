"""工具层与能力缺口的回归测试（《动态节点设计规划》§4.7–§4.12、§8.1）。

钉三件事：

1. **工具集是条目数据的函数**：确定性 op 拿不到任何工具，工具型 op 按 ``(op, kind)``
   裁剪，``web_search`` 这类默认关闭的工具永远不进池子。
2. **有界工具循环**：单工具上限与单条目总上限都能挡住第 N 次调用，且给出的是
   可读拒绝文本（让模型收尾），不是异常。
3. **能力缺失只标记不阻断**：命中已知缺口时产出 ``unsupported`` 条目——它们进交付
   清单、不被派发，其余条目照常跑。
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.agent.plan.capability import (
    CAPABILITY_GAPS,
    capability_gap_items,
    detect_capability_gaps,
    requested_presentation_medium,
)
from app.agent.plan.contracts import PlanItem
from app.agent.plan.knowledge_tool import MAX_RESULT_CHARS, search_knowledge_impl
from app.agent.plan.expand import expand_plan
from app.agent.plan.store import poll_runnable, terminal_stats
from app.agent.plan.tool_loop import (
    MAX_TOOL_CALLS,
    TOOL_LOOP_RECURSION_LIMIT,
    _CallBudget,
    _available_tools,
    _wrap_with_budget,
    extract_trace,
    run_tool_loop,
)
from app.agent.plan.tool_registry import (
    TOOL_TYPED_OPS,
    get_tool_registry,
    tool_names_for,
    tools_for,
)


def _item(op: str, kind: str = "") -> PlanItem:
    return PlanItem(id=f"{op}_{kind or 'all'}_01", op=op, kind=kind)


# ── 工具裁剪 ──


def test_deterministic_ops_receive_no_tools():
    """merge / validate / fix 必须完全可复现：工具集恒为空（§4.7）。"""

    for op in ("merge", "validate", "fix"):
        assert tool_names_for(_item(op, "all")) == []
        assert tools_for(_item(op, "door")) == []


def test_tool_typed_ops_are_generate_and_repair_only():
    assert TOOL_TYPED_OPS == ("generate", "repair")
    assert tool_names_for(_item("generate", "door"))
    assert tool_names_for(_item("repair"))


def test_generate_tools_are_trimmed_by_kind():
    """开口类构件拿得到开口校验器，屋顶类拿不到；双方都拿得到通用校验器。"""

    window = tool_names_for(_item("generate", "window"))
    roof = tool_names_for(_item("generate", "roof"))

    assert "validate_opening_fit" in window
    assert "validate_opening_fit" not in roof
    assert "validate_roof_coverage" in roof
    assert "validate_roof_coverage" not in window
    for name in ("validate_blueprint_structure", "validate_reference_integrity"):
        assert name in window and name in roof


def test_generate_never_receives_write_tools():
    """generate 不该自己改既有元素：修复类与白名单动作只属于 repair。"""

    names = tool_names_for(_item("generate", "window"))
    assert not [name for name in names if name.startswith("fix_")]
    assert "repair_actions" not in names


def test_disabled_tools_never_enter_any_pool():
    """默认关闭的能力（在线检索）在任何条目上都不得出现。"""

    for op, kind in (("generate", "window"), ("repair", "")):
        assert "web_search" not in tool_names_for(_item(op, kind))
    assert all(spec.name != "web_search" or not spec.enabled for spec in get_tool_registry())


def test_registry_declares_every_tool_fail_closed():
    """没声明特殊之处 = 会写入、不可并发、只能调一次（buildTool 默认值精神）。"""

    for spec in get_tool_registry():
        if spec.read_only:
            continue
        assert spec.max_calls == 1, spec.name


# ── 有界工具循环 ──


@pytest.mark.parametrize("spec", [s for s in get_tool_registry() if s.tool is not None], ids=lambda s: s.name)
def test_budget_wrapper_preserves_tool_schema(spec):
    wrapped = _wrap_with_budget(spec.tool, _CallBudget({spec.name: 1}, 1))
    assert wrapped.get_input_schema().model_json_schema() == spec.tool.get_input_schema().model_json_schema()


def test_budget_wrapped_search_accepts_query_and_enforces_limit():
    from app.agent.plan.knowledge_tool import search_knowledge

    wrapped = _wrap_with_budget(search_knowledge, _CallBudget({"search_knowledge": 1}, 3))
    with patch("app.agent.plan.knowledge_tool.search_knowledge_impl", return_value="知识结果") as search:
        assert asyncio.run(wrapped.ainvoke({"query": "门洞尺寸", "kind": "door"})) == "知识结果"
        assert "最多调用 1 次" in asyncio.run(wrapped.ainvoke({"query": "窗洞尺寸"}))
    search.assert_called_once_with("门洞尺寸", kind="door")


def test_budget_wrapper_awaits_async_tools_without_mutating_original():
    from langchain_core.tools import StructuredTool

    calls = []

    async def lookup(query: str) -> str:
        calls.append(query)
        return query

    original = StructuredTool.from_function(coroutine=lookup, description="查询")
    wrapped = _wrap_with_budget(original, _CallBudget({original.name: 1}, 3))
    assert asyncio.run(wrapped.ainvoke({"query": "门"})) == "门"
    assert "最多调用 1 次" in asyncio.run(wrapped.ainvoke({"query": "窗"}))
    assert calls == ["门"]
    assert original.coroutine is lookup


def test_total_budget_refuses_extra_calls_with_readable_text():
    budget = _CallBudget({"validate_opening_fit": 99}, MAX_TOOL_CALLS)

    for _ in range(MAX_TOOL_CALLS):
        assert budget.consume("validate_opening_fit") is None

    refusal = budget.consume("validate_opening_fit")
    assert refusal and "预算已用完" in refusal


def test_per_tool_budget_is_independent_of_total_budget():
    budget = _CallBudget({"search_knowledge": 2}, MAX_TOOL_CALLS)

    assert budget.consume("search_knowledge") is None
    assert budget.consume("search_knowledge") is None
    refusal = budget.consume("search_knowledge")
    assert refusal and "最多调用 2 次" in refusal


def test_undeclared_tool_defaults_to_one_call():
    budget = _CallBudget({}, MAX_TOOL_CALLS)
    assert budget.consume("some_new_tool") is None
    assert budget.consume("some_new_tool") is not None


def test_tool_loop_recursion_limit_covers_every_call_plus_finish():
    assert TOOL_LOOP_RECURSION_LIMIT > MAX_TOOL_CALLS * 2 + 1


def test_tools_are_removed_after_requested_call_limits():
    from types import SimpleNamespace

    tools = [SimpleNamespace(name="search"), SimpleNamespace(name="validate")]
    messages = [_Message("ai", tool_calls=[{"name": "search"}, {"name": "search"}])]
    limits = {"search": 2, "validate": 1}
    assert [t.name for t in _available_tools(tools, limits, messages)] == ["validate"]
    messages.append(_Message("ai", tool_calls=[{"name": "unknown"}]))
    assert _available_tools(tools, limits, messages) == []


def test_tool_failure_keeps_completed_calls_and_pending_arguments():
    class Agent:
        async def astream(self, payload, config, stream_mode):
            messages = [
                _Message("ai", tool_calls=[{"name": "search", "id": "a", "args": {"query": "窗"}}]),
                _Message("tool", name="search", tool_call_id="a", content="知识"),
                _Message("ai", content="正在检查", tool_calls=[{"name": "validate", "id": "b", "args": {"blueprint": {}}}]),
            ]
            yield {"messages": messages}
            raise RuntimeError("validation crashed")

    result = asyncio.run(run_tool_loop(system_prompt="规则", user_message="生成窗", tool_specs=[], agent=Agent()))
    assert result.text == ""
    assert result.diag["error"] == "validation crashed"
    assert result.diag["tool_calls"] == 2
    assert result.trace[0]["ok"] is True
    assert result.trace[1]["ok"] is False
    assert result.trace[1]["args"] == {"blueprint": {}}
    assert result.diag["transcript"]["messages"][1]["content"] == "知识"


def test_real_agent_finishes_after_three_tool_rounds():
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from app.agent.plan.tool_loop import build_tool_agent
    from app.agent.plan.tool_registry import tool_spec

    bindings = []

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            bindings.append([t.name for t in tools])
            return self

        def bind(self, **kwargs):
            bindings.append([])
            return super().bind(**kwargs)

    @tool
    def lookup(query: str) -> str:
        """Return knowledge."""
        return query

    model = Model(responses=[
        AIMessage(content="", tool_calls=[{"name": "lookup", "args": {"query": str(i)}, "id": str(i)}])
        for i in range(3)
    ] + [AIMessage(content='[{"type":"window"}]')])
    specs = [tool_spec("lookup", "knowledge_search", lookup, max_calls=3)]
    agent, _ = build_tool_agent(specs, system_prompt="test", create_llm_fn=lambda **kw: model)
    result = asyncio.run(run_tool_loop(system_prompt="test", user_message="test", tool_specs=specs, agent=agent))
    assert "error" not in result.diag
    assert result.text == '[{"type":"window"}]'
    assert result.diag["tool_calls"] == 3
    assert bindings == [["lookup"], ["lookup"], ["lookup"], []]


class _Message:
    def __init__(self, type_: str, **kwargs):
        self.type = type_
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_trace_records_tool_name_and_output_size():
    """没有这条轨迹，就无法区分\"模型没查\"与\"查了但知识里没有\"。"""

    messages = [
        _Message("ai", tool_calls=[{"name": "search_knowledge", "args": {"q": "门窗"}}], content=""),
        _Message("tool", name="search_knowledge", content="墙厚 240mm 的构造做法……"),
        _Message("ai", tool_calls=[{"name": "validate_opening_fit", "args": {}}], content=""),
        _Message("tool", name="validate_opening_fit", content="❌ 门超出宿主墙"),
    ]

    trace = extract_trace(messages)

    assert [entry["tool"] for entry in trace] == ["search_knowledge", "validate_opening_fit"]
    assert trace[0]["ok"] is True and trace[0]["chars"] == len("墙厚 240mm 的构造做法……")
    assert trace[1]["ok"] is False


def test_tool_loop_extracts_text_from_openai_content_blocks():
    class _Agent:
        async def ainvoke(self, payload, config):
            return {
                "messages": [
                    _Message(
                        "ai",
                        content=[
                            {
                                "type": "text",
                                "text": '[{"id":"door_1","type":"door"}]',
                            }
                        ],
                    )
                ]
            }

    result = asyncio.run(
        run_tool_loop(
            system_prompt="test",
            user_message="test",
            tool_specs=[],
            agent=_Agent(),
        )
    )

    assert result.text == '[{"id":"door_1","type":"door"}]'


# ── 检索工具：必须带过滤对 ──


class _Loader:
    def __init__(self):
        self.queries: list[tuple[str, dict]] = []
        self.last_results: list[object] = []

    def load_many(self, queries, per_query=2):
        for query in queries:
            self.queries.append((query.text, dict(query.metadata_filter or {})))
        return "宿主墙厚 240mm；洞口需留过梁。"


class _Service:
    def __init__(self, loader):
        self.spec_loader = loader


def test_search_tool_always_sends_a_metadata_filter():
    """不给模型能查全库的口子：无过滤的 query 不得发出（§4.10）。"""

    loader = _Loader()
    with patch("app.services.agent_service.agent_service", _Service(loader)):
        text = search_knowledge_impl("门洞尺寸要求", kind="door")

    assert loader.queries, "检索没有发出"
    text_query, filters = loader.queries[0]
    assert text_query == "门洞尺寸要求"
    assert filters.get("doc_type")
    assert filters.get("entity_type") == "door"
    assert "检索结果" in text


def test_search_tool_refuses_unknown_kind_without_querying():
    loader = _Loader()
    with patch("app.services.agent_service.agent_service", _Service(loader)):
        text = search_knowledge_impl("怎么做", kind="teleporter")

    assert "未知构件类型" in text
    assert loader.queries == []


def test_search_tool_result_is_bounded():
    loader = _Loader()
    loader.load_many = lambda queries, per_query=2: "构" * (MAX_RESULT_CHARS * 2)
    with patch("app.services.agent_service.agent_service", _Service(loader)):
        text = search_knowledge_impl("门窗做法", kind="window")

    assert len(text) <= MAX_RESULT_CHARS


# ── 能力缺口 ──


@pytest.mark.parametrize(
    ("message", "gap_id"),
    [
        ("生成两层住宅，内部隔墙怎么做", "floor_plan"),
        # 家具本身能生成（引擎有十个原生子类型），缺的是"哪一间房"——
        # 所以这条要落到 floor_plan，而不是一条并不存在的"家具缺失"。
        ("房间里放点家具", "floor_plan"),
        ("想要一个带后院的房子", "site_semantics"),
        ("build a house with a garage", "site_semantics"),
    ],
)
def test_known_gaps_are_detected(message, gap_id):
    assert gap_id in {gap.id for gap in detect_capability_gaps(message)}


def test_furniture_is_not_a_capability_gap():
    """家具是已实现能力：报"做不到"会让模型改写成建筑替代方案。"""

    assert "furniture" not in {gap.id for gap in CAPABILITY_GAPS}
    assert detect_capability_gaps("生成一个桌子") == []
    assert detect_capability_gaps("生成一套餐桌椅") == []


def test_unrelated_request_has_no_gaps():
    assert detect_capability_gaps("生成两层住宅，前后立面各两个窗") == []


def test_presentation_medium_is_not_a_capability_gap():
    """要平面图只是交付媒介不同：记提示，不判能力缺失。"""

    assert requested_presentation_medium("顺便出一张平面图") == "平面图"
    assert detect_capability_gaps("顺便出一张平面图") == []


def test_gap_items_are_terminal_and_carry_a_user_readable_notice():
    for item in capability_gap_items("要房间布局，再放点家具"):
        assert item.status == "unsupported"
        assert item.is_terminal
        assert item.params["notice"]
        assert item.kind in {gap.id for gap in CAPABILITY_GAPS}


def test_gap_items_are_never_dispatched_but_land_in_delivery_counts():
    plan = expand_plan(
        {
            "user_message": "生成两层住宅，要房间布局",
            "design_brief": {"component_quota": {"door": {"min": 1, "max": 1}}},
            "suggested_components": ["door"],
        }
    )

    stats = terminal_stats(plan)
    assert stats["unsupported"] == 1
    assert plan.item("unsupported_floor_plan_01") is not None
    # 缺口不阻断：门窗条目照常可执行，循环不会因为缺它而多转一圈
    assert [item.op for item in plan.items if item.id.startswith("unsupported_")] == ["validate"]
    runnable = poll_runnable(plan)
    assert runnable is not None and runnable.op == "generate"
    assert all(
        not item.id.startswith("unsupported_")
        for item in plan.items
        if item.status in {"ready", "pending", "blocked"}
    )
