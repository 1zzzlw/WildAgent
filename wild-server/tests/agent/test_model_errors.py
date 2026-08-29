"""模型服务故障分类协议的回归测试。"""

from app.agent.model_errors import (
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


def test_rate_limit_is_retryable_but_still_stops_current_run():
    result = classify_model_error(_ProviderError("Too many requests", 429))

    assert result["category"] == "rate_limited"
    assert result["retryable"] is True
    assert result["terminal_current_run"] is True


def test_component_failures_are_collected_from_generator_diagnostics():
    quota_error = classify_model_error(_ProviderError("Free quota exhausted", 403))
    failures = collect_component_model_errors({
        "door_gen_diag": {"label": "门生成", "model_error": quota_error},
        "door_val_diag": {"label": "门校验"},
        "window_gen_diag": {"label": "窗生成"},
    })

    assert len(failures) == 1
    assert failures[0]["component_type"] == "door"
    assert failures[0]["label"] == "门生成"
