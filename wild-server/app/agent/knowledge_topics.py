"""按 WILD 能力与通用关系检查本地知识覆盖，类型特征可选。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeTopic:
    """一个建筑类型必备的知识主题。"""

    topic_key: str          # 稳定标识，如 "high_rise_composition"
    doc_type: str           # 知识库 doc_type（building_type/recipe/component/pattern）
    topic: str              # 知识库 topic（composition/assembly/fallback/parameters/constraints）
    entity_type: str | None = None  # 可选实体类型过滤
    required: bool = True   # 缺失时标记本地实现知识不足；不自动触发联网

    @property
    def label(self) -> str:
        parts = [self.doc_type, self.topic]
        if self.entity_type:
            parts.append(self.entity_type)
        return ".".join(part for part in parts if part)


@dataclass(frozen=True)
class BuildingTypeKnowledge:
    """一个建筑类型需要的完整知识主题集合。"""

    building_type_key: str
    topics: tuple[KnowledgeTopic, ...] = field(default_factory=tuple)

    @property
    def required_topics(self) -> tuple[KnowledgeTopic, ...]:
        return tuple(topic for topic in self.topics if topic.required)

    @property
    def topic_keys(self) -> set[str]:
        return {topic.topic_key for topic in self.topics}


# 知识充分性围绕可执行规则判断；建筑百科与风格配方均非生成必需。
_DEFAULT_TOPICS: tuple[KnowledgeTopic, ...] = (
    KnowledgeTopic("supported_components", "component", "parameters", required=True),
    KnowledgeTopic("assembly_relations", "recipe", "assembly", required=True),
    KnowledgeTopic("type_identity", "building_type", "composition", required=False),
)


def topics_for_building_type(building_type: str) -> tuple[KnowledgeTopic, ...]:
    """所有建筑复用能力与关系；类型差异仅是可选补充，不驱动百科补库。"""
    return _DEFAULT_TOPICS


def all_topic_keys() -> set[str]:
    return {topic.topic_key for topic in _DEFAULT_TOPICS}
