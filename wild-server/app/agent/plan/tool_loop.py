"""工具型处理器的有界工具循环（《动态节点设计规划》§4.7–§4.12）。

为什么需要它：`generate` / `repair` 这类条目的字段约束可能超出程序预取的知识，
允许模型自己补检索、补自查是有价值的；但**"把 19 个工具交给模型、指望它自己校验"
这个项目已经试过一次并失败了**（`create_agent` 对流程控制力弱，模型会忘记调用校验
工具）。所以这里的边界是：

- 工具循环只在**条目内部**，它是 `execute` 的实现细节，不是图节点——否则图步数会
  变成"条目数 × 工具调用数"，`recursion_limit` 立刻失去意义；
- 工具集按 `(op, kind)` 裁剪（`tools_for`），不是把全部工具塞给每次调用；
- 调用次数**硬上限**：单条目 `MAX_TOOL_CALLS`，单工具还要受它自己的 `max_calls`
  约束，超限时返回可读错误让模型收尾，而不是继续烧 token；
- 关键校验不依赖模型自觉：它仍由 plan 里显式的 `validate` 条目保证。

调用形状照抄现有 `agent_service._create_agent` + `query_structured`（不另写模型客户端），
只把返回的 messages 拿来提取工具轨迹供审计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

from loguru import logger

from app.llm.client import content_as_text

#: 单条目内允许的工具调用总数。3 次足够"补一次检索 + 自查一次"，再多就是模型在绕圈。
MAX_TOOL_CALLS = 3

#: 三轮工具交互之后撤下工具，预留收尾调用和图调度步。
TOOL_LOOP_RECURSION_LIMIT = MAX_TOOL_CALLS * 2 + 4


def _available_tools(tools: list[Any], limits: dict[str, int], messages: list[Any]) -> list[Any]:
    """按模型实际请求的次数撤下工具，错误和被拒绝的调用也消耗轮次。"""
    calls = [call for message in messages for call in getattr(message, "tool_calls", None) or []]
    if len(calls) >= MAX_TOOL_CALLS:
        return []
    return [tool for tool in tools if sum(call.get("name") == tool.name for call in calls) < limits[tool.name]]


@dataclass
class ToolRunResult:
    """一次工具型调用的结果：文本 + 工具轨迹 + 诊断。"""

    text: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)
    diag: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_calls(self) -> list[str]:
        return [str(entry.get("tool")) for entry in self.trace]


class _CallBudget:
    """单条目内的调用预算：总量与单工具两个维度一起卡。"""

    def __init__(self, limits: dict[str, int], total: int):
        self._limits = dict(limits)
        self._used: dict[str, int] = {}
        self._total = 0
        self._total_limit = total

    def consume(self, name: str) -> str | None:
        """返回 None 表示放行；否则返回给模型看的拒绝理由。"""

        if self._total >= self._total_limit:
            return (
                f"工具调用预算已用完（本条目最多 {self._total_limit} 次）。"
                "请直接基于已有信息输出最终结果。"
            )
        limit = self._limits.get(name, 1)
        if self._used.get(name, 0) >= limit:
            return f"工具 {name} 本次最多调用 {limit} 次，已用完。请改用其它信息或直接输出结果。"
        self._used[name] = self._used.get(name, 0) + 1
        self._total += 1
        return None


def _wrap_with_budget(tool_obj: Any, budget: _CallBudget) -> Any:
    """把预算检查包在工具外层：超限时返回提示文本，而不是抛异常打断整轮。"""

    name = getattr(tool_obj, "name", getattr(tool_obj, "__name__", "tool"))
    from langchain_core.tools import StructuredTool

    if not isinstance(tool_obj, StructuredTool):
        raise TypeError(f"工具 {name} 必须提供 StructuredTool 参数契约")

    updates: dict[str, Any] = {}
    if tool_obj.func is not None:
        @wraps(tool_obj.func)
        def _guard(*args, **kwargs):
            refusal = budget.consume(name)
            if refusal is not None:
                return refusal
            return tool_obj.func(*args, **kwargs)

        updates["func"] = _guard
    if tool_obj.coroutine is not None:
        @wraps(tool_obj.coroutine)
        async def _async_guard(*args, **kwargs):
            refusal = budget.consume(name)
            if refusal is not None:
                return refusal
            return await tool_obj.coroutine(*args, **kwargs)

        updates["coroutine"] = _async_guard
    # 保留原 schema、参数校验和工具配置，不能从 *args/**kwargs 重新推断契约。
    return tool_obj.model_copy(update=updates)


def build_tool_agent(
    tool_specs: list[Any],
    *,
    system_prompt: str,
    thinking_mode: bool = False,
    create_llm_fn: Callable[..., Any] | None = None,
) -> tuple[Any, dict[str, int]]:
    """按条目工具集创建一个无会话状态的 Agent，返回 ``(agent, 每工具预算)``。"""

    from langchain.agents import create_agent
    from langchain.agents.middleware import wrap_model_call

    from app.llm.client import create_llm

    budget = _CallBudget(
        {spec.name: spec.max_calls for spec in tool_specs},
        MAX_TOOL_CALLS,
    )
    tools = [
        _wrap_with_budget(spec.tool, budget)
        for spec in tool_specs
        if getattr(spec, "tool", None) is not None
    ]
    llm_factory = create_llm_fn or create_llm
    limits = {spec.name: spec.max_calls for spec in tool_specs}

    @wrap_model_call
    async def enforce_tool_budget(request, handler):
        available = _available_tools(request.tools, limits, request.state.get("messages", []))
        return await handler(request.override(tools=available))

    agent = create_agent(
        model=llm_factory(enable_thinking=thinking_mode, streaming=False),
        tools=tools,
        system_prompt=system_prompt,
        middleware=[enforce_tool_budget],
    )
    return agent, {spec.name: spec.max_calls for spec in tool_specs}


def extract_trace(messages: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    """从 agent 的 messages 里提取工具轨迹（工具名 + 是否出错 + 输出长度）。"""

    trace: list[dict[str, Any]] = []
    for message in messages if isinstance(messages, list) else []:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                trace.append({"tool": str(name), "ok": False, "chars": 0,
                              "args": call.get("args") if isinstance(call, dict) else None,
                              "call_id": call.get("id") if isinstance(call, dict) else None})
        role = getattr(message, "type", "")
        if role == "tool":
            name = str(getattr(message, "name", "") or "tool")
            content = str(getattr(message, "content", "") or "")
            for entry in reversed(trace):
                if entry["tool"] == name and entry["chars"] == 0 and (
                    not entry.get("call_id") or entry["call_id"] == getattr(message, "tool_call_id", None)
                ):
                    entry["chars"] = len(content)
                    entry["ok"] = getattr(message, "status", "") != "error" and not content.startswith(("❌", "error", "Error", "工具调用预算", "工具 "))
                    break
            else:
                trace.append(
                    {
                        "tool": name,
                        "ok": not content.startswith(("❌", "error", "Error")),
                        "chars": len(content),
                    }
                )
    return trace[-limit:]


async def run_tool_loop(
    *,
    system_prompt: str,
    user_message: str,
    tool_specs: list[Any],
    thinking_mode: bool = False,
    agent: Any = None,
) -> ToolRunResult:
    """执行有界工具循环，返回模型最终文本与工具轨迹。

    超限不抛异常：预算是给模型的**约束**，不是给系统的故障。真正的失败判定交给
    处理器（拿不到可解析产物才算这一轮失败）。
    """

    if agent is None:
        agent, budgets = build_tool_agent(
            tool_specs, system_prompt=system_prompt, thinking_mode=thinking_mode
        )
    else:  # 测试注入：直接用现成 agent，预算仍按声明生效
        budgets = {spec.name: spec.max_calls for spec in tool_specs}

    messages: list[Any] = []
    error = None
    try:
        payload = {"messages": [{"role": "user", "content": user_message}]}
        config = {"recursion_limit": TOOL_LOOP_RECURSION_LIMIT}
        if hasattr(agent, "astream"):
            async for snapshot in agent.astream(payload, config=config, stream_mode="values"):
                messages = snapshot.get("messages", messages)
        else:  # 兼容注入的轻量测试 Agent。
            result = await agent.ainvoke(payload, config=config)
            messages = result.get("messages", [])
    except Exception as exc:
        logger.warning(f"[tool_loop] 工具型调用失败: {exc}")
        error = str(exc)

    trace = extract_trace(messages)
    text = ""
    for message in reversed(messages or []):
        content = getattr(message, "content", "")
        if not error and getattr(message, "type", "") == "ai" and content and not getattr(message, "tool_calls", None):
            text = content_as_text(content)
            if text:
                break
    return ToolRunResult(
        text=text,
        trace=trace,
        diag={
            "tool_calls": len(trace), "budgets": budgets,
            **({"error": error} if error else {}),
            "transcript": {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "messages": [
                    {"type": getattr(message, "type", ""),
                     "content": getattr(message, "content", ""),
                     "tool_calls": getattr(message, "tool_calls", None),
                     "tool_call_id": getattr(message, "tool_call_id", None),
                     "name": getattr(message, "name", None)}
                    for message in messages
                ],
            },
        },
    )
