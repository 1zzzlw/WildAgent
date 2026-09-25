"""不进入 LangGraph State 的单次运行时上下文。

持久化 checkpointer 只能保存可序列化状态；WebSocket 推送回调与"本条目可用的工具集"
属于当前进程/当前条目的资源，通过 ContextVar 传给处理器，用完即丢。

这也是《动态节点设计规划》§2.8 第 ② 层的落点：单次执行需要的输入是**函数参数或
上下文变量**，不是 state 字段——它们既不需要跨节点，也不需要进 checkpoint。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Awaitable, Callable

ReasoningCallback = Callable[[str, str], Awaitable[None]]

_reasoning_callback: ContextVar[ReasoningCallback | None] = ContextVar(
    "wild_reasoning_callback",
    default=None,
)

#: 当前条目可用的工具集（plan.tool_registry.ToolSpec 元组）。
#: 这里刻意用 ``tuple[Any, ...]``：runtime 是底层模块，不该反向依赖 plan。
_item_tools: ContextVar[tuple[Any, ...] | None] = ContextVar(
    "wild_item_tools",
    default=None,
)


def get_reasoning_callback() -> ReasoningCallback | None:
    return _reasoning_callback.get()


def bind_reasoning_callback(callback: ReasoningCallback | None) -> Token:
    return _reasoning_callback.set(callback)


def reset_reasoning_callback(token: Token) -> None:
    _reasoning_callback.reset(token)


def get_item_tools() -> tuple[Any, ...] | None:
    """当前条目可用的工具集；``None`` 表示这条条目不走工具型处理器。"""

    return _item_tools.get()


def bind_item_tools(specs: tuple[Any, ...] | list[Any] | None) -> Token:
    return _item_tools.set(tuple(specs) if specs else None)


def reset_item_tools(token: Token) -> None:
    _item_tools.reset(token)
