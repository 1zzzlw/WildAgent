"""把模型供应商异常转换为稳定、可展示的错误协议。

模型服务故障（额度、鉴权、限流、超时等）不是 Blueprint 几何错误，
不能进入 callback 的建筑修复循环。本模块只做错误分类，不依赖具体供应商 SDK。
"""
from __future__ import annotations

import re
from typing import Any


def classify_model_error(exc: Exception) -> dict[str, Any]:
    """返回可写入节点诊断的模型错误信息。

    ``retryable`` 表示用户稍后重新发起请求是否可能成功；无论该值如何，
    当前图运行都应停止，避免把服务故障误交给建筑修复节点。
    """
    raw_message = str(exc)
    lowered = raw_message.lower()
    status_code = _extract_status_code(exc, lowered)

    if _contains_any(
        lowered,
        (
            "free quota exhausted",
            "quota exhausted",
            "insufficient_quota",
            "allocationquota",
            "billing quota",
            "余额不足",
            "额度耗尽",
            "免费额度",
        ),
    ):
        category = "quota_exhausted"
        retryable = False
        user_message = "模型服务额度已耗尽，请充值、关闭仅使用免费额度限制，或更换可用模型后重新生成。"
    elif status_code == 401 or _contains_any(
        lowered,
        ("invalid api key", "authentication failed", "unauthorized", "鉴权失败"),
    ):
        category = "authentication"
        retryable = False
        user_message = "模型服务鉴权失败，请检查 API Key 和模型服务配置。"
    elif status_code == 403 or _contains_any(lowered, ("permission denied", "forbidden")):
        category = "access_denied"
        retryable = False
        user_message = "模型服务拒绝访问，请检查模型权限、账号额度和服务配置。"
    elif status_code == 429 or _contains_any(lowered, ("rate limit", "too many requests", "限流")):
        category = "rate_limited"
        retryable = True
        user_message = "模型服务请求过于频繁，本次生成已停止，请稍后重新生成。"
    elif status_code == 400:
        category = "invalid_request"
        retryable = False
        user_message = "模型服务拒绝了请求，请检查模型名称、参数和上下文长度配置。"
    elif (status_code is not None and status_code >= 500) or _contains_any(
        lowered,
        ("service unavailable", "bad gateway", "gateway timeout"),
    ):
        category = "provider_unavailable"
        retryable = True
        user_message = "模型服务暂时不可用，本次生成已停止，请稍后重新生成。"
    elif _contains_any(lowered, ("timeout", "timed out", "connection error", "连接超时")):
        category = "transport_error"
        retryable = True
        user_message = "连接模型服务失败，本次生成已停止，请检查网络后重新生成。"
    else:
        category = "model_error"
        retryable = False
        user_message = "模型服务调用失败，本次生成已停止，请检查服务配置和后台日志。"

    return {
        "category": category,
        "status_code": status_code,
        "retryable": retryable,
        "terminal_current_run": True,
        "user_message": user_message,
    }


def collect_component_model_errors(component_diagnostics: object) -> list[dict[str, Any]]:
    """从并行组件诊断中收集模型故障，供 merge 统一终止当前运行。"""
    if not isinstance(component_diagnostics, dict):
        return []

    failures: list[dict[str, Any]] = []
    for diag_key, diag in component_diagnostics.items():
        if not str(diag_key).endswith("_gen_diag") or not isinstance(diag, dict):
            continue
        model_error = diag.get("model_error")
        if not isinstance(model_error, dict) or not model_error.get("terminal_current_run"):
            continue
        failures.append({
            **model_error,
            "component_type": str(diag_key)[:-9],
            "label": diag.get("label", str(diag_key)[:-9]),
        })
    return failures


def _extract_status_code(exc: Exception, lowered_message: str) -> int | None:
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    ):
        if isinstance(candidate, int):
            return candidate

    match = re.search(r"(?:error code|status(?: code)?)\s*[:=]?\s*(\d{3})", lowered_message)
    return int(match.group(1)) if match else None


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
