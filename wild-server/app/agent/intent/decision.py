"""意图分类的结果契约与输出归一化。

``IntentDecision`` 是分类器唯一对外产出的东西：它把模型的自由文本收敛成闭集内的
``intent`` / ``target_kind``，并记录来源与置信度，便于观测与降级判定。

归一化是**保守**的：认不出的写法一律退到确定性规则，不在这里自造类别——下游按
``intent`` 与 ``target_kind`` 分叉，第三个值会让图路由落空。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

from app.agent.state import IntentName, TargetKind

from .rules import classify_keywords, is_explanatory_question


def _target_kind_of(message: str, intent: str) -> TargetKind:
    """延迟导入 ``generation.architecture``：那个包初始化会拉起 facade/skeleton/planning，
    分类器不该为一次判定付这个成本（沿用迁移前 ``routing.py`` 的做法）。"""

    from app.agent.generation.architecture import detect_target_kind

    return detect_target_kind(message, intent)


@dataclass(frozen=True, slots=True)
class IntentDecision:
    """可观测、可校验的意图分类结果。"""

    intent: IntentName
    confidence: float
    target: str
    requires_scene: bool
    reason: str
    source: Literal["llm", "fallback"]
    target_kind: TargetKind = "architecture"
    model_error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json_object(raw: str) -> dict[str, Any] | None:
    """从模型输出里抠出第一个 JSON 对象；失败返回 None。"""

    # 两个作用：判断非空和清理外层空白，不处理中间内容
    text = str(raw or "").strip()

    # 去除 Markdown 代码块标记，兼容模型输出带 ```json 的情况
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)

    # find 找第一个 {，rfind 找最后一个 }：忽略 JSON 前后的多余文字
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        # 切片左闭右开，end + 1 才能把 } 包进来
        value = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def fallback_decision(
    message: str,
    has_current_scene: bool,
    reason: str,
) -> IntentDecision:
    """模型之外的确定性降级；置信度按"是不是只是元问题"给。"""

    intent = classify_keywords(message, has_current_scene)
    confidence = 0.9 if is_explanatory_question(message) else 0.65
    return IntentDecision(
        intent=intent,
        confidence=confidence,
        target="current_scene" if intent == "edit" else "user_request",
        requires_scene=intent == "edit",
        reason=reason[:200],
        source="fallback",
        target_kind=_target_kind_of(message, intent),
    )


def normalize_intent_decision(
    raw: str,
    message: str,
    has_current_scene: bool,
) -> IntentDecision:
    """解析结构化模型结果，并兼容只返回单个旧标签的模型。"""

    payload = _json_object(raw)

    if payload is not None:
        # 字符串字段统一去空白转小写，类型不对时退默认值
        intent = str(payload.get("intent") or "").strip().lower()

        if intent in {"generate", "edit", "chat"}:
            if intent != "chat" and is_explanatory_question(message):
                return IntentDecision(
                    intent="chat",
                    confidence=0.95,
                    target="requested_explanation",
                    requires_scene=False,
                    reason="用户是在询问方法、原理或原因，不应执行场景变更",
                    source="llm",
                )
            if intent == "edit" and not has_current_scene:
                return IntentDecision(
                    intent="chat",
                    confidence=0.75,
                    target="missing_scene",
                    requires_scene=False,
                    reason="用户要求修改，但当前没有可编辑场景",
                    source="llm",
                )
            try:
                confidence = float(payload.get("confidence", 0.75))
            except (TypeError, ValueError):
                confidence = 0.75
            confidence = max(0.0, min(1.0, confidence))
            target = str(payload.get("target") or "user_request")[:120]
            reason = str(payload.get("reason") or "模型语义分类")[:200]
            # 目标类型只接受闭集内的值；模型给了别的写法就退到规则判定，
            # 不在这里自造类别（下游按这两个值分叉，第三值会让图路由落空）。
            raw_kind = str(payload.get("target_kind") or "").strip().lower()
            target_kind: TargetKind = (
                raw_kind if raw_kind in {"architecture", "object"}  # type: ignore[assignment]
                else _target_kind_of(message, intent)
            )
            if intent != "generate":
                target_kind = "architecture"
            return IntentDecision(
                intent=cast(IntentName, intent),
                confidence=confidence,
                target=target,
                requires_scene=intent == "edit",
                reason=reason,
                source="llm",
                target_kind=target_kind,
            )

    upper = (raw or "").strip().upper()

    matches = re.findall(r"\b(?:GENERATE|EDIT|CHAT)\b", upper)
    label = matches[0] if matches else ""

    if label == "EDIT" and has_current_scene:
        intent: IntentName = "edit"
    elif label == "CHAT":
        intent = "chat"
    elif label == "GENERATE":
        intent = "generate"
    else:
        return fallback_decision(message, has_current_scene, "模型未返回合法意图")

    if intent != "chat" and is_explanatory_question(message):
        return IntentDecision(
            intent="chat",
            confidence=0.95,
            target="requested_explanation",
            requires_scene=False,
            reason="用户是在询问方法、原理或原因，不应执行场景变更",
            source="llm",
        )
    return IntentDecision(
        intent=intent,
        confidence=0.75,
        target="current_scene" if intent == "edit" else "user_request",
        requires_scene=intent == "edit",
        reason="兼容旧版单标签模型输出",
        source="llm",
        target_kind=_target_kind_of(message, intent),
    )


__all__ = ["IntentDecision", "fallback_decision", "normalize_intent_decision"]
