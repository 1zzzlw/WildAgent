"""意图分类结果与模型输出解析；非法输出交给调用层终止请求。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from app.agent.state import IntentName, TargetKind

from .rules import is_explanatory_question
from .target_kind import detect_target_kind


@dataclass(frozen=True, slots=True)
class IntentDecision:
    """可观测、可校验的意图分类结果。"""

    intent: IntentName
    target: str
    requires_scene: bool
    reason: str
    source: Literal["llm"]
    target_kind: TargetKind = "architecture"
    profile: str = "custom"
    model_error: dict[str, Any] | None = None

_PROFILE_SLUG = re.compile(r"[^a-z0-9_-]+")


def _normalize_profile(raw: object) -> str:
    """清理形制标签；缺失或清理后为空时使用 custom。"""
    text = str(raw or "").strip().lower()
    text = _PROFILE_SLUG.sub("-", text).strip("-")
    return text[:40] or "custom"


def _json_object(raw: str) -> dict[str, Any] | None:
    """从模型输出里抠出第一个 JSON 对象；失败返回 None。"""

    text = str(raw or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)

    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def normalize_intent_decision(
    raw: str,
    message: str,
    has_current_scene: bool,
) -> IntentDecision:
    """解析结构化模型结果；缺少 JSON 对象或合法意图时抛错。"""

    payload = _json_object(raw)

    if payload is None:
        raise ValueError("意图分类模型未返回 JSON 对象")

    intent = str(payload.get("intent") or "").strip().lower()
    if intent not in {"generate", "edit", "chat"}:
        raise ValueError("意图分类模型未返回合法意图")

    if intent != "chat" and is_explanatory_question(message):
        return IntentDecision(
            intent="chat",
            target="requested_explanation",
            requires_scene=False,
            reason="用户是在询问方法、原理或原因，不应执行场景变更",
            source="llm",
        )
    if intent == "edit" and not has_current_scene:
        return IntentDecision(
            intent="chat",
            target="missing_scene",
            requires_scene=False,
            reason="用户要求修改，但当前没有可编辑场景",
            source="llm",
        )
    target = str(payload.get("target") or "user_request")[:120]
    reason = str(payload.get("reason") or "模型语义分类")[:200]

    raw_kind = str(payload.get("target_kind") or "").strip().lower()
    target_kind: TargetKind = (
        cast(TargetKind, raw_kind)
        if raw_kind in {"architecture", "object"}
        else detect_target_kind(message, intent)
    )

    # 非生成请求不需要用目标类型选择生成流程，因此统一填一个默认值。
    if intent != "generate":
        target_kind = "architecture"
    return IntentDecision(
        intent=cast(IntentName, intent),
        target=target,
        requires_scene=intent == "edit",
        reason=reason,
        source="llm",
        target_kind=target_kind,
        profile=_normalize_profile(payload.get("profile")),
    )


__all__ = ["IntentDecision", "normalize_intent_decision"]
