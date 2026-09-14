"""Retrieval Gate：对向量召回证据做可配置的观察或强制门控。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RetrievalGateDecision:
    mode: str
    purpose: str
    decision: str
    reason: str
    threshold: float | None
    best_distance: float | None
    semantic_hit_count: int
    enforced: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RAGRetrievalRejected(RuntimeError):
    """enforce 模式下，知识问答因证据不足而被确定性拒答。"""

    def __init__(self, message: str, decision: RetrievalGateDecision):
        super().__init__(message)
        self.decision = decision


_CHAT_QUERY_MARKERS = (
    "什么", "为什么", "怎么", "如何", "哪些", "多少", "多高",
    "介绍", "解释", "区别", "特点", "规则", "参数", "是否", "吗", "？", "?",
)


def infer_retrieval_purpose(message: str, fast_intent: str | None) -> str:
    """为快速模式选择 Gate 语义；歧义请求优先避免误拒建筑生成。

    明确生成/编辑直接按 generation 处理；明确问句按 chat 处理；仅有建筑名等
    无动词短语无法可靠分类，因此按 generation 降级，让后续 Agent 决定意图。
    """

    if fast_intent in {"generate", "edit"}:
        return "generation"
    if fast_intent == "chat":
        return "chat"
    text = str(message or "").strip()
    if any(marker in text for marker in _CHAT_QUERY_MARKERS):
        return "chat"
    return "generation"


def evaluate_retrieval_gate(
    hits: Iterable[Any],
    *,
    mode: str,
    purpose: str,
    max_distance: float | None,
    min_hits: int = 1,
) -> RetrievalGateDecision:
    """使用原始 distance 判断证据是否足够；相邻补片的 None 不算语义命中。"""

    normalized_mode = str(mode or "off").lower()
    if normalized_mode not in {"off", "observe", "enforce"}:
        normalized_mode = "off"
    distances = [
        float(hit.distance)
        for hit in hits
        if getattr(hit, "distance", None) is not None
    ]
    best_distance = min(distances, default=None)
    semantic_hit_count = len(distances)

    if normalized_mode == "off":
        decision, reason = "pass", "gate_off"
    elif max_distance is None:
        decision, reason = "pass", "threshold_not_calibrated"
    elif semantic_hit_count < max(1, int(min_hits)):
        decision, reason = "reject", "insufficient_hits"
    elif best_distance is None:
        decision, reason = "reject", "missing_distance"
    elif best_distance > float(max_distance):
        decision, reason = "reject", "distance_above_threshold"
    else:
        decision, reason = "pass", "distance_within_threshold"

    return RetrievalGateDecision(
        mode=normalized_mode,
        purpose=purpose,
        decision=decision,
        reason=reason,
        threshold=max_distance,
        best_distance=best_distance,
        semantic_hit_count=semantic_hit_count,
        enforced=normalized_mode == "enforce" and decision == "reject",
    )
