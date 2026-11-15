"""图执行的运行时资源与请求上下文，不写入检查点。"""
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

@dataclass
class AgentRuntime:
    spec_loader: Any = None
    llm: Any = None
    thinking_llm: Any = None
    model_factory: Any = None

agent_runtime = AgentRuntime()


def create_llm(*args, **kwargs):
    if agent_runtime.model_factory is None:
        raise RuntimeError("模型资源尚未初始化，请通过应用启动入口执行工作流")
    return agent_runtime.model_factory(*args, **kwargs)


def reload_chat_models() -> None:
    llm = create_llm(enable_thinking=False)
    thinking_llm = create_llm(enable_thinking=True, streaming=True)
    agent_runtime.llm = llm
    agent_runtime.thinking_llm = thinking_llm

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
