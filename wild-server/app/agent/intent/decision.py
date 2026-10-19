"""
意图分类的结果契约与输出归一化。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

from app.agent.state import IntentName, TargetKind

from .rules import is_explanatory_question


class IntentOutputError(ValueError):
    """模型调用成功，但分类结果无法使用。"""

    def __init__(self, detail: str):
        super().__init__(
            f"模型调用成功，但返回的意图分类结果不合法，无法使用：{detail}。"
            "请尝试切换其他模型。"
        )


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: 形制标签只允许 slug 字符；其余一律折成连字符。
_PROFILE_SLUG = re.compile(r"[^a-z0-9_-]+")


def _normalize_profile(raw: object) -> str:
    """把模型给的形制标签清成 slug；缺失/非法时退 ``custom``。"""

    text = str(raw or "").strip().lower()
    text = _PROFILE_SLUG.sub("-", text).strip("-")
    return text[:40] or "custom"


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
        value = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def normalize_intent_decision(
    raw: str,
    message: str,
    has_current_scene: bool,
) -> IntentDecision:
    """解析并校验模型 JSON；非法结果不进入后续节点。"""

    payload = _json_object(raw)

    if payload is None:
        raise IntentOutputError("未返回合法 JSON 对象")
    intent = str(payload.get("intent") or "").strip().lower()
    if intent not in {"generate", "edit", "chat"}:
        raise IntentOutputError(
            f"intent 必须是 generate、edit 或 chat，实际为 {payload.get('intent')!r}"
        )
    if intent != "chat" and is_explanatory_question(message):
        raise IntentOutputError("用户正在询问方法、原理或原因，分类结果却要求变更场景")
    if intent == "edit" and not has_current_scene:
        raise IntentOutputError("分类结果要求修改场景，但当前没有可编辑场景")

    raw_kind = str(payload.get("target_kind") or "").strip().lower()
    if intent == "generate" and raw_kind not in {"architecture", "object"}:
        raise IntentOutputError(
            "生成目标 target_kind 必须是 architecture 或 object，"
            f"实际为 {payload.get('target_kind')!r}"
        )
    target_kind = cast(TargetKind, raw_kind) if intent == "generate" else "architecture"
    for field in ("target", "reason"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise IntentOutputError(f"{field} 必须是非空字符串")
    requires_scene = payload.get("requires_scene")
    if not isinstance(requires_scene, bool) or requires_scene != (intent == "edit"):
        raise IntentOutputError("requires_scene 必须为布尔值，且仅 edit 意图为 true")

    return IntentDecision(
        intent=cast(IntentName, intent),
        target=payload["target"].strip()[:120],
        requires_scene=requires_scene,
        reason=payload["reason"].strip()[:200],
        source="llm",
        target_kind=target_kind,
        profile=_normalize_profile(payload.get("profile")),
    )


__all__ = ["IntentDecision", "IntentOutputError", "normalize_intent_decision"]
