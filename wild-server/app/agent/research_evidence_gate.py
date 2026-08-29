"""知识覆盖判断：本地 RAG 检索对本次建筑需求的覆盖是否充分。

这是 Plan 模式"受控网络研究"的确定性闸门：只判断"本地知识够不够"，不决定
搜索内容。输出一个结构化的覆盖决策（覆盖比、缺失主题、是否触发联网）。

安全边界：本模块是确定性代码，不调用 LLM，不做任何写操作。联网与入库由
下游节点/人工批准决定。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.knowledge_topics import (
    KnowledgeTopic,
    topics_for_building_type,
)


# 覆盖比阈值：低于该值触发联网；可通过 config 覆盖。
DEFAULT_COVERAGE_THRESHOLD = 0.8


@dataclass(frozen=True)
class CoverageDecision:
    """本地知识覆盖决策。"""

    sufficient: bool
    coverage_ratio: float
    missing_topics: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    hit_topics: list[str] = field(default_factory=list)
    trigger_web_research: bool = False
    reason: str = ""
    building_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _chunk_topic(chunk: Any) -> str | None:
    """从检索分片提取主题标识 (doc_type.topic[.entity_type])。

    兼容 dict 和 RetrievedSpecChunk 对象。
    """
    metadata = chunk.metadata if hasattr(chunk, "metadata") else (
        chunk.get("metadata") if isinstance(chunk, dict) else None
    )
    if not isinstance(metadata, dict):
        return None
    doc_type = str(metadata.get("doc_type") or "").strip()
    topic = str(metadata.get("topic") or "").strip()
    if not doc_type or not topic:
        return None
    entity_type = str(metadata.get("entity_type") or "").strip()
    if entity_type and entity_type not in {"general", "index"}:
        return f"{doc_type}.{topic}.{entity_type}"
    return f"{doc_type}.{topic}"


def _topic_label(topic: KnowledgeTopic) -> str:
    return topic.label


def evaluate_knowledge_coverage(
    user_message: str,
    building_type: str | None,
    retrieved_chunks: list[Any] | None,
    *,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> CoverageDecision:
    """判断本地 RAG 分片对建筑需求的知识覆盖是否充分。

    Args:
        user_message: 用户建筑需求（用于诊断原因）。
        building_type: 建筑类型 key（来自 _detect_building_type 或图谱）。
        retrieved_chunks: 本地 RAG 检索结果（RetrievedSpecChunk 列表）。
        coverage_threshold: 覆盖比阈值（0~1），低于则触发联网。

    Returns:
        CoverageDecision：充分性、覆盖比、缺失主题、是否触发联网。
    """
    # 1. 确定该建筑类型应有的知识主题。
    topics = topics_for_building_type(building_type or "")
    if not topics:
        return CoverageDecision(
            sufficient=True,
            coverage_ratio=1.0,
            trigger_web_research=False,
            reason="未知建筑类型，无覆盖标准，不触发联网",
            building_type=building_type or "",
        )

    # 2. 从检索分片提取命中主题集合。
    hit_labels: set[str] = set()
    for chunk in retrieved_chunks or []:
        label = _chunk_topic(chunk)
        if label:
            hit_labels.add(label)

    # 3. 逐主题判定命中：匹配 doc_type + topic（+ entity_type，若有）。
    hit_topics: list[str] = []
    missing_topics: list[str] = []
    missing_required: list[str] = []
    for topic in topics:
        label = _topic_label(topic)
        matched = False
        if topic.entity_type:
            matched = label in hit_labels
        else:
            # 无 entity_type 过滤时，匹配同 doc_type + topic 的任意实体分片。
            prefix = f"{topic.doc_type}.{topic.topic}"
            matched = any(hit.startswith(prefix) for hit in hit_labels)
        if matched:
            hit_topics.append(label)
        else:
            missing_topics.append(label)
            if topic.required:
                missing_required.append(label)

    # 4. 计算覆盖比：命中主题数 / 应有主题数。
    total = len(topics)
    hit_count = len(hit_topics)
    coverage_ratio = round(hit_count / total, 3) if total else 1.0

    # 5. 决策：低于阈值或任一 required 主题缺失 → 触发联网。
    below_threshold = coverage_ratio < coverage_threshold
    trigger = below_threshold or bool(missing_required)
    sufficient = not trigger

    if sufficient:
        reason = f"本地知识覆盖充分（{coverage_ratio:.0%}，{hit_count}/{total} 主题）"
    elif missing_required:
        reason = (
            f"缺少核心知识主题（{', '.join(missing_required[:4])}）；"
            f"覆盖 {coverage_ratio:.0%}"
        )
    else:
        reason = f"本地知识覆盖不足（{coverage_ratio:.0%}，低于阈值 {coverage_threshold:.0%}）"

    return CoverageDecision(
        sufficient=sufficient,
        coverage_ratio=coverage_ratio,
        missing_topics=missing_topics,
        missing_required=missing_required,
        hit_topics=hit_topics,
        trigger_web_research=trigger,
        reason=reason,
        building_type=building_type or "",
    )
