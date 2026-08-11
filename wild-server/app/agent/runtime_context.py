"""不进入 LangGraph State 的单次运行时上下文。

持久化 checkpointer 只能保存可序列化状态；WebSocket 推送回调属于当前进程资源，
通过 ContextVar 传给并行节点，服务重启后由新的任务重新绑定。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Awaitable, Callable


ReasoningCallback = Callable[[str, str], Awaitable[None]]

_reasoning_callback: ContextVar[ReasoningCallback | None] = ContextVar(
    "wild_reasoning_callback",
    default=None,
)


def get_reasoning_callback() -> ReasoningCallback | None:
    return _reasoning_callback.get()


def bind_reasoning_callback(callback: ReasoningCallback | None) -> Token:
    return _reasoning_callback.set(callback)


def reset_reasoning_callback(token: Token) -> None:
    _reasoning_callback.reset(token)
