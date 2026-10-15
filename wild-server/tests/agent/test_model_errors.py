"""模型服务故障分类协议的回归测试。"""

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from app.llm.errors import (
    classify_model_error,
    collect_component_model_errors,
)


class _ProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def test_free_quota_error_is_terminal_and_user_friendly():
    result = classify_model_error(_ProviderError(
        "Error code: 403 - {'message': 'Free quota exhausted. add funds'}",
        403,
    ))

    assert result["category"] == "quota_exhausted"
    assert result["retryable"] is False
    assert result["terminal_current_run"] is True
    assert "额度已耗尽" in result["user_message"]
    assert "Free quota" not in result["user_message"]


def test_missing_model_error_points_to_model_configuration():
    result = classify_model_error(_ProviderError("model does not exist", 404))

    assert result["category"] == "model_not_found"
    assert result["retryable"] is False
    assert result["terminal_current_run"] is True
    assert "模型名称" in result["user_message"]


def test_rate_limit_is_retryable_but_still_stops_current_run():
    result = classify_model_error(_ProviderError("Too many requests", 429))

    assert result["category"] == "rate_limited"
    assert result["retryable"] is True
    assert result["terminal_current_run"] is True


@pytest.mark.parametrize("error", [TimeoutError(), APITimeoutError(request=httpx.Request("POST", "https://example.test"))])
def test_response_timeout_does_not_claim_connection_or_quota_failure(error):
    result = classify_model_error(error)
    assert result["category"] == "transport_error" and result["retryable"]
    assert "等待模型响应超时" in result["user_message"]
    assert "额度" not in result["user_message"] and "连接模型服务超时" not in result["user_message"]


def test_connection_failure_is_not_mislabeled_as_response_timeout():
    result = classify_model_error(APIConnectionError(request=httpx.Request("POST", "https://example.test"), message="DNS lookup failed"))
    assert result["category"] == "transport_error" and result["retryable"]
    assert "连接模型服务失败" in result["user_message"]
    assert "超时" not in result["user_message"]


def test_component_failures_are_collected_from_generator_diagnostics():
    quota_error = classify_model_error(_ProviderError("Free quota exhausted", 403))
    failures = collect_component_model_errors({
        "door_gen": {"label": "门生成", "model_error": quota_error},
        "door_val": {"label": "门校验"},
        "window_gen": {"label": "窗生成"},
    })

    assert len(failures) == 1
    assert failures[0]["component_type"] == "door"
    assert failures[0]["label"] == "门生成"


def test_single_attempt_invocation_does_not_retry_transport_failure(monkeypatch):
    from types import SimpleNamespace
    from app.llm.invocation import invoke_llm
    import app.llm.invocation as invocation
    calls = []

    async def unavailable(_messages):
        calls.append("request")
        raise TimeoutError("service unavailable")

    async def immediate_wait(awaitable, **kwargs):
        return await awaitable

    monkeypatch.setattr(invocation.asyncio, "wait_for", immediate_wait)
    monkeypatch.setattr(invocation, "prepare_rag_llm_call", lambda *args: {})
    monkeypatch.setattr(invocation, "record_rag_llm_call", lambda **kwargs: None)
    coroutine = invoke_llm(SimpleNamespace(ainvoke=unavailable), [], max_retries=0)
    with pytest.raises(TimeoutError, match="service unavailable"):
        coroutine.send(None)
    assert calls == ["request"]
