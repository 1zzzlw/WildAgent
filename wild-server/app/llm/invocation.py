"""统一 LLM 调用结果收集层。

消除生成节点里重复的 reasoning_content / token_usage / finish_reason 提取样板。
所有节点的流式与非流式调用都收敛到这里的 ``LlmResult`` 与 ``invoke_llm`` / ``stream_llm``。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.llm.client import message_texts
from app.rag.trace import record_rag_llm_call
from config import config

# 可重试模型错误的退避重试：仅对限流(429)/服务端 5xx/超时等瞬态故障重试，
# 额度/鉴权等永久错误不重试。重试次数计入诊断，避免静默放大延迟。
_LLM_RETRY_MAX = 2
_LLM_RETRY_BASE_DELAY_S = 1.0
_LLM_RETRY_JITTER_S = 0.5


async def _sleep_with_jitter(attempt: int) -> None:
    delay = _LLM_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)) + (_LLM_RETRY_JITTER_S * attempt)
    await asyncio.sleep(min(delay, 8.0))


@dataclass
class LlmResult:
    """一次 LLM 调用的归一化结果，与具体供应商无关。"""

    content: str = ""
    reasoning: str = ""
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None
    retry_count: int = 0

    @property
    def content_chars(self) -> int:
        return len(self.content)

    @property
    def reasoning_chars(self) -> int:
        return len(self.reasoning)


def _normalize_usage(usage: Any) -> dict[str, int] | None:
    """把两种键名（prompt_tokens 与 input_tokens）统一为 input/output/total。"""
    if not isinstance(usage, dict) or not usage:
        return None
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    total_tokens = usage.get("total_tokens")
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    input_value = int(input_tokens or 0)
    output_value = int(output_tokens or 0)
    total_value = int(total_tokens or 0) or input_value + output_value
    return {"input": input_value, "output": output_value, "total": total_value}


def merge_token_usage(*usages: dict[str, int] | None) -> dict[str, int] | None:
    """合并多次调用（如首次生成 + 格式恢复）的 token 统计。"""
    present = [usage for usage in usages if usage]
    if not present:
        return None
    merged = {"input": 0, "output": 0, "total": 0}
    for usage in present:
        for key in ("input", "output", "total"):
            merged[key] += int(usage.get(key, 0) or 0)
    return merged


def collect_response(response: Any) -> LlmResult:
    """从一次已完成的非流式响应收集 content / reasoning / usage / finish_reason。"""
    content, reasoning = message_texts(response)
    result = LlmResult(content=content, reasoning=reasoning)

    metadata = getattr(response, "response_metadata", None) or {}
    if isinstance(metadata, dict):
        result.finish_reason = metadata.get("finish_reason") or metadata.get("stop_reason")
        usage = metadata.get("token_usage") or metadata.get("usage")
        normalized = _normalize_usage(usage)
        if normalized:
            result.token_usage = normalized

    if result.token_usage is None:
        usage_metadata = getattr(response, "usage_metadata", None) or {}
        result.token_usage = _normalize_usage(usage_metadata)
    return result


async def invoke_llm(llm, messages, *, on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None) -> LlmResult:
    """统一非流式调用（``on_reasoning_delta`` 兼容签名，但非流式不会逐字回调）。

    对限流/服务端 5xx/超时等瞬态故障做有限指数退避重试；永久错误（额度、
    鉴权、参数错误）直接抛出。重试次数通过 ``on_reasoning_delta`` 的
    ``_retry`` 通道由调用方诊断（兼容现有回调签名，忽略即无副作用）。
    """
    started = time.perf_counter()
    last_exc: Exception | None = None
    llm_timeout = float(config.chat.timeout)
    for attempt in range(_LLM_RETRY_MAX + 1):
        try:
            if llm_timeout > 0:
                response = await asyncio.wait_for(
                    llm.ainvoke(messages), timeout=llm_timeout,
                )
            else:
                response = await llm.ainvoke(messages)
        except asyncio.CancelledError:
            record_rag_llm_call(
                mode="invoke",
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                token_usage=None,
                error_type="CancelledError",
                retry_count=attempt,
            )
            raise
        except Exception as exc:
            from app.llm.errors import classify_model_error

            retryable = bool(classify_model_error(exc).get("retryable"))
            if not retryable or attempt >= _LLM_RETRY_MAX:
                record_rag_llm_call(
                    mode="invoke",
                    elapsed_ms=round((time.perf_counter() - started) * 1000),
                    token_usage=None,
                    error_type=type(exc).__name__,
                    retry_count=attempt,
                )
                raise
            last_exc = exc
            try:
                await _sleep_with_jitter(attempt + 1)
            except asyncio.CancelledError:
                record_rag_llm_call(
                    mode="invoke",
                    elapsed_ms=round((time.perf_counter() - started) * 1000),
                    token_usage=None,
                    error_type="CancelledError",
                    retry_count=attempt,
                )
                raise
            continue
        result = collect_response(response)
        record_rag_llm_call(
            mode="invoke",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            token_usage=result.token_usage,
            retry_count=result.retry_count,
            response_content=result.content,
            reasoning_content=result.reasoning,
        )
        if last_exc is not None:
            result.retry_count = attempt
        return result
    raise last_exc if last_exc is not None else RuntimeError("invoke_llm 未返回结果")


async def stream_llm(llm, messages, *, on_reasoning_delta=None) -> LlmResult:
    """统一流式调用：逐字收集 reasoning，末尾收集 content / usage / finish_reason。

    配置超时限制等待正文或思考新数据的时间；持续输出时更新截止时间。
    异常沿节点 except 进入模型服务故障阻断路径。
    """
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None

    started = time.perf_counter()
    llm_timeout = float(config.chat.timeout)
    _stream = None
    try:
        _stream = llm.astream(messages)
        async with asyncio.timeout(llm_timeout if llm_timeout > 0 else None) as deadline:
            async for chunk in _stream:
                text, delta = message_texts(chunk)
                if llm_timeout > 0 and (text or delta):
                    deadline.reschedule(asyncio.get_running_loop().time() + llm_timeout)
                if text:
                    content_parts.append(text)
                if delta:
                    reasoning_parts.append(delta)
                    if on_reasoning_delta is not None:
                        await on_reasoning_delta(delta)

                metadata = getattr(chunk, "response_metadata", None) or {}
                if isinstance(metadata, dict):
                    finish_reason = finish_reason or metadata.get("finish_reason") or metadata.get("stop_reason")
                    usage = _normalize_usage(metadata.get("usage"))
                    if usage:
                        token_usage = usage

                usage_metadata = getattr(chunk, "usage_metadata", None) or {}
                normalized = _normalize_usage(usage_metadata)
                if normalized:
                    token_usage = normalized
    except (Exception, asyncio.CancelledError) as exc:
        record_rag_llm_call(
            mode="stream",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            token_usage=token_usage,
            error_type=type(exc).__name__,
            response_content="".join(content_parts),
            reasoning_content="".join(reasoning_parts),
        )
        raise
    finally:
        close = getattr(_stream, "aclose", None)
        if close is not None:
            await close()

    result = LlmResult(
        content="".join(content_parts),
        reasoning="".join(reasoning_parts),
        token_usage=token_usage,
        finish_reason=finish_reason,
    )
    record_rag_llm_call(
        mode="stream",
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        token_usage=result.token_usage,
        response_content=result.content,
        reasoning_content=result.reasoning,
    )
    return result
