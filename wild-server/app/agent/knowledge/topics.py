"""按 WILD 能力与通用关系检查本地生成知识覆盖。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeTopic:
    """生成链路需要覆盖的一个可执行知识主题。"""

    topic_key: str          # 稳定标识，如 "assembly_relations"
    doc_type: str           # 知识库 doc_type（recipe/component）
    topic: str              # 知识库 topic（composition/assembly/fallback/parameters/constraints）
    entity_type: str | None = None  # 可选实体类型过滤
    required: bool = True   # 缺失时标记本地实现知识不足；不自动触发联网

    @property
    def label(self) -> str:
        parts = [self.doc_type, self.topic]
        if self.entity_type:
            parts.append(self.entity_type)
        return ".".join(part for part in parts if part)


# 知识充分性只围绕可执行规则判断；建筑百科与风格配方不属于生成知识。
_DEFAULT_TOPICS: tuple[KnowledgeTopic, ...] = (
    KnowledgeTopic("supported_components", "component", "parameters", required=True),
    KnowledgeTopic("assembly_relations", "recipe", "assembly", required=True),
)


def generation_knowledge_topics() -> tuple[KnowledgeTopic, ...]:
    """返回所有生成任务复用的能力与关系主题。"""
    return _DEFAULT_TOPICS


def all_topic_keys() -> set[str]:
    return {topic.topic_key for topic in _DEFAULT_TOPICS}
