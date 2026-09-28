"""把模型 token 回调里的 ``reasoning_content`` 转成有界的增量事件。

**为什么单独成模块**：这条规则有两个消费者，而且它们在仓库的两层里——

- `app/services/agent_service.py`：最终回答 agent 的 ``ainvoke(config={"callbacks": [...]})``；
- `app/agent/plan/tool_loop.py`：条目/设计块的工具循环 agent。

把它留在 ``agent_service`` 里，agent 层就只能"从服务层导一个私有类"（方向反了）；
抄第二份则必然与第一份在"攒多久发一次"上分叉（`MEMORY.md`：唯一规则函数）。
所以它是 `app/llm/` 的公共件，服务层反过来导入并把旧私有名保留为别名。

**攒批的判据**（沿用既有行为，别顺手改）：累计 ≥24 字符，或刚好以换行/句末标点收尾。
逐 token 直发会把前端的 SSE 打爆；攒太久则"思考过程"看起来像卡住了。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain_core.callbacks import AsyncCallbackHandler

#: 攒够这么多字符就发一次。
FLUSH_CHARS = 24

#: 见到这些收尾字符就立刻发（否则短句会一直压在缓冲里）。
FLUSH_SUFFIXES = ("\n", "。", "！", "？")


class ReasoningDeltaCallback(AsyncCallbackHandler):
    """从模型 token 回调中提取并适度合并真实 ``reasoning_content``。"""

    def __init__(self, emit: Callable[[str], Awaitable[None]]):
        self._emit = emit
        self._buffer = ""

    async def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Any = None,
        **kwargs: Any,
    ) -> None:
        message = getattr(chunk, "message", None)
        additional_kwargs = getattr(message, "additional_kwargs", {})
        reasoning_delta = additional_kwargs.get("reasoning_content", "")
        if not reasoning_delta:
            return

        self._buffer += reasoning_delta
        if len(self._buffer) >= FLUSH_CHARS or self._buffer.endswith(FLUSH_SUFFIXES):
            await self.flush()

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        delta = self._buffer
        self._buffer = ""
        await self._emit(delta)


__all__ = ["FLUSH_CHARS", "FLUSH_SUFFIXES", "ReasoningDeltaCallback"]
