"""知识覆盖图谱：建筑类型 → 必备知识主题清单。

用于 Plan 模式的知识覆盖判断：给定用户建筑需求，判断本地 RAG 检索是否覆盖了
该建筑类型"完整构成"所需的知识主题。只记录"哪些主题缺失"，不决定是否联网
（联网决策由 research_evidence_gate 负责）。

主题用 (doc_type, topic) 二元组标识，与知识库 metadata 体系一致：
- (building_type, composition)  建筑类型构成
- (recipe, assembly)            跨构件组装模板
- (recipe, fallback)            引擎可用降级映射
- (component, parameters)       构件参数
- (component, constraints)      构件约束
- (pattern, composition)        项目模式/案例

每个主题带 required 标记：required 主题缺失会直接触发联网；optional 主题缺失
只降低覆盖比，不强制联网。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeTopic:
    """一个建筑类型必备的知识主题。"""

    topic_key: str          # 稳定标识，如 "high_rise_composition"
    doc_type: str           # 知识库 doc_type（building_type/recipe/component/pattern）
    topic: str              # 知识库 topic（composition/assembly/fallback/parameters/constraints）
    entity_type: str | None = None  # 可选实体类型过滤
    required: bool = True   # 缺失时是否强制触发联网

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


# ── 建筑类型 → 必备知识主题图谱 ──
# 判断"本地知识覆盖是否充分"的依据：一个建筑类型要正确生成，至少需要命中
# 构成 + 组装 + 降级映射三类知识。key 用建筑类型语义标识，映射由 building_type
# 检测在运行时确定。

_BUILDING_TYPE_TOPICS: dict[str, tuple[KnowledgeTopic, ...]] = {
    "high_rise": (
        KnowledgeTopic("high_rise_composition", "building_type", "composition", required=True),
        KnowledgeTopic("vertical_circulation", "recipe", "assembly", "stair", required=True),
        KnowledgeTopic("core_shaft", "component", "parameters", "wall", required=True),
        KnowledgeTopic("curtain_wall_recipe", "recipe", "assembly", required=True),
        KnowledgeTopic("podium_tower_assembly", "recipe", "assembly", required=False),
        KnowledgeTopic("high_rise_fallback", "recipe", "fallback", required=False),
    ),
    "curtain_wall": (
        KnowledgeTopic("curtain_wall_composition", "building_type", "composition", required=True),
        KnowledgeTopic("curtain_wall_recipe", "recipe", "assembly", required=True),
        KnowledgeTopic("curtain_mullion_capability", "recipe", "fallback", required=True),
        KnowledgeTopic("glass_material", "component", "parameters", "window", required=False),
    ),
    "villa": (
        KnowledgeTopic("villa_composition", "building_type", "composition", required=True),
        KnowledgeTopic("residential_assembly", "recipe", "assembly", required=True),
        KnowledgeTopic("door_window_recipe", "recipe", "assembly", required=False),
        KnowledgeTopic("roof_recipe", "recipe", "assembly", "roof", required=False),
    ),
    "chinese_courtyard": (
        KnowledgeTopic("courtyard_composition", "building_type", "composition", required=True),
        KnowledgeTopic("courtyard_assembly", "recipe", "assembly", required=True),
        KnowledgeTopic("chinese_roof_fallback", "recipe", "fallback", required=True),
        KnowledgeTopic("cornice_capability", "recipe", "fallback", required=False),
    ),
    "cabin": (
        KnowledgeTopic("cabin_composition", "building_type", "composition", required=True),
        KnowledgeTopic("cabin_assembly", "recipe", "assembly", required=True),
        KnowledgeTopic("simple_roof_recipe", "recipe", "assembly", "roof", required=False),
    ),
    "tower": (
        KnowledgeTopic("tower_composition", "building_type", "composition", required=True),
        KnowledgeTopic("tower_assembly", "recipe", "assembly", required=True),
        KnowledgeTopic("vertical_circulation", "recipe", "assembly", "stair", required=True),
    ),
    "industrial": (
        KnowledgeTopic("industrial_composition", "building_type", "composition", required=True),
        KnowledgeTopic("industrial_assembly", "recipe", "assembly", required=True),
        KnowledgeTopic("long_span_fallback", "recipe", "fallback", required=True),
    ),
    "public": (
        KnowledgeTopic("public_composition", "building_type", "composition", required=True),
        KnowledgeTopic("public_assembly", "recipe", "assembly", required=True),
        KnowledgeTopic("egress_circulation", "recipe", "assembly", "stair", required=True),
        KnowledgeTopic("public_fallback", "recipe", "fallback", required=False),
    ),
}

# 默认建筑类型的必备主题：覆盖不到具体类型时的兜底，至少要求构成 + 组装 + 降级。
_DEFAULT_TOPICS: tuple[KnowledgeTopic, ...] = (
    KnowledgeTopic("default_composition", "building_type", "composition", required=True),
    KnowledgeTopic("default_assembly", "recipe", "assembly", required=True),
    KnowledgeTopic("default_fallback", "recipe", "fallback", required=False),
)


def topics_for_building_type(building_type: str) -> tuple[KnowledgeTopic, ...]:
    """返回指定建筑类型的必备知识主题；未知类型返回默认主题集。"""
    normalized = str(building_type or "").strip().lower()
    if normalized in _BUILDING_TYPE_TOPICS:
        return _BUILDING_TYPE_TOPICS[normalized]
    return _DEFAULT_TOPICS


def all_topic_keys() -> set[str]:
    """返回所有图谱中出现的主题标识（用于测试/诊断）。"""
    keys: set[str] = set()
    for topics in _BUILDING_TYPE_TOPICS.values():
        keys.update(topic.topic_key for topic in topics)
    keys.update(topic.topic_key for topic in _DEFAULT_TOPICS)
    return keys
