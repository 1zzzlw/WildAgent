"""受限的 RAG 查询计划。

查询计划只负责改善召回，不负责生成建筑事实。实体别名来自知识库 chunk
metadata，因此新增建筑类型不需要修改本模块。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


AliasCatalog = dict[str, dict[str, Any]]

_INDEX_VOCABULARY = {
    "composition", "assembly", "fallback", "example", "definition",
    "parameters", "constraints", "规则", "默认完整构成", "最少可行回退",
    "构件搭接", "宿主", "对齐", "碰撞", "覆盖", "fallback",
}
_INDEX_VOCABULARY_CASEFOLD = {item.casefold() for item in _INDEX_VOCABULARY}


@dataclass(frozen=True)
class QueryPlan:
    raw_query: str
    rewritten_query: str
    intent: str = "knowledge_retrieval"
    aliases: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    metadata_filter: dict[str, Any] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    source: str = "deterministic"
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "rewritten_query": self.rewritten_query,
            "intent": self.intent,
            "aliases": list(self.aliases),
            "topics": list(self.topics),
            "filters": dict(self.metadata_filter),
            "constraints": list(self.constraints),
            "source": self.source,
            "confidence": self.confidence,
        }


def build_alias_catalog(chunks: Iterable[Any]) -> AliasCatalog:
    """从已索引 chunk metadata 建立通用别名目录。"""
    catalog: AliasCatalog = {}
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", chunk if isinstance(chunk, dict) else {}) or {}
        entity_name = str(metadata.get("entity_name") or "").strip()
        if not entity_name:
            continue
        entry = catalog.setdefault(entity_name, {
            "aliases": set(),
            "filters": {},
            "constraints": set(),
        })
        # primary_terms 和 synonyms 都能触发实体匹配；分字段保存是为了便于
        # 审核知识质量，而不是让查询规划器放弃其中一类检索词。
        # keywords 仅用于兼容尚未迁移的外部索引。
        for field_name in ("primary_terms", "synonyms", "entity_aliases", "keywords"):
            raw = metadata.get(field_name, [])
            if isinstance(raw, str):
                values = [item.strip() for item in raw.split(",") if item.strip()]
            elif isinstance(raw, (list, tuple, set)):
                values = [str(item).strip() for item in raw if str(item).strip()]
            else:
                values = []
            entry["aliases"].update(
                value for value in values
                if value.casefold() not in _INDEX_VOCABULARY_CASEFOLD
            )
        entry["aliases"].add(entity_name)
        for key in ("doc_type", "entity_type", "topic"):
            value = metadata.get(key)
            if value and key not in entry["filters"]:
                entry["filters"][key] = value
        raw_constraints = metadata.get("constraint_tags", [])
        if isinstance(raw_constraints, str):
            raw_constraints = [item.strip() for item in raw_constraints.split(",") if item.strip()]
        entry["constraints"].update(str(item) for item in (raw_constraints or []))
    return catalog


def _alias_matches(query: str, alias: str) -> bool:
    alias = alias.strip()
    if not alias:
        return False
    # 单字中文词过于宽泛，只在短查询或显式包含时参与过滤。
    if len(alias) == 1 and len(query.strip()) > 4 and alias not in query:
        return False
    return alias.casefold() in query.casefold()


def build_query_plan(
    raw_query: str,
    metadata_filter: dict[str, Any] | None = None,
    *,
    alias_catalog: AliasCatalog | None = None,
    rewritten_query: str | None = None,
    source: str = "deterministic",
    confidence: float = 1.0,
    include_topic_hints: bool = False,
) -> QueryPlan:
    """从原句构建安全查询计划，并保留调用方显式过滤条件。"""
    raw_query = (raw_query or "").strip()
    catalog = alias_catalog or {}
    matches: list[tuple[str, dict[str, Any]]] = []
    for entity_name, entry in catalog.items():
        aliases = sorted(entry.get("aliases", ()), key=len, reverse=True)
        matched = [alias for alias in aliases if _alias_matches(raw_query, alias)]
        if matched:
            matches.append((entity_name, {**entry, "matched_aliases": matched}))

    aliases: list[str] = []
    filters = dict(metadata_filter or {})
    for _entity_name, entry in matches:
        for alias in sorted(entry.get("aliases", ()), key=str.casefold):
            if alias not in aliases:
                aliases.append(alias)
        # 只有所有命中的实体对同一字段给出相同值时才自动过滤，避免
        # “现代别墅和中式别墅”被静默收敛到其中一个实体。
        for key in ("doc_type", "entity_type", "topic"):
            values = {
                candidate.get("filters", {}).get(key)
                for _, candidate in matches
                if candidate.get("filters", {}).get(key) is not None
            }
            if len(values) == 1 and key not in filters:
                filters[key] = values.pop()

    entity_names = [entity_name for entity_name, _entry in matches]
    # 调用方显式传入的 entity_name 必须保留；仅清理 planner 自行推导的值。
    explicit_entity_name = "entity_name" in filters
    if len(entity_names) == 1 and not explicit_entity_name:
        filters["entity_name"] = entity_names[0]
    elif len(entity_names) != 1 and not explicit_entity_name:
        filters.pop("entity_name", None)

    topics: list[str] = []
    if any(token in raw_query for token in ("生成", "设计", "构成", "默认")):
        topics.append("composition")
    if any(token in raw_query for token in ("组装", "依附", "宿主", "碰撞", "覆盖", "检查")):
        topics.extend(["assembly", "constraints"])
    if any(token in raw_query for token in ("回退", "降级", "失败")):
        topics.append("fallback")
    topics = list(dict.fromkeys(topics))

    rewritten = (rewritten_query or raw_query).strip()
    if include_topic_hints:
        # 主题提示词是给语义 embedding 的额外线索；对字符 bigram 的 hash 向量
        # 是噪声，调用方可按 embedding 类型决定是否启用。
        if aliases:
            rewritten = f"{rewritten}\n检索别名: {', '.join(aliases[:12])}"
        if topics:
            rewritten = f"{rewritten}\n检索主题: {', '.join(topics)}"
    elif aliases:
        # 只做别名改写：把命中的别名/同义词并进查询文本，改善关键词召回，
        # 不引入英文术语噪声。
        rewritten = f"{rewritten} {' '.join(aliases[:12])}".strip()

    constraints: list[str] = []
    for _entity_name, entry in matches:
        for tag in entry.get("constraints", ()):
            if tag not in constraints:
                constraints.append(tag)
    generic_constraints = (
        (("parentWall", "host"), ("宿主", "host")),
        (("楼板", "level"), ("标高", "level")),
        (("覆盖", "coverage"), ("间隙", "coverage")),
        (("碰撞", "collision"),),
    )
    for alternatives in generic_constraints:
        if any(token in raw_query for token, _tag in alternatives):
            for _token, tag in alternatives:
                if tag not in constraints:
                    constraints.append(tag)

    return QueryPlan(
        raw_query=raw_query,
        rewritten_query=rewritten,
        aliases=tuple(aliases),
        topics=tuple(topics),
        metadata_filter=filters,
        constraints=tuple(constraints),
        source=source,
        confidence=max(0.0, min(float(confidence), 1.0)),
    )


def apply_llm_rewrite(
    raw_query: str,
    candidate_query: str,
    metadata_filter: dict[str, Any] | None = None,
) -> QueryPlan:
    """应用 LLM 候选改写；实体解析留给 Loader 的动态 alias catalog。"""
    candidate = (candidate_query or "").strip()
    if not candidate:
        return build_query_plan(raw_query, metadata_filter)
    safe_candidate = f"{raw_query}\n检索改写: {candidate}"
    return build_query_plan(
        raw_query,
        metadata_filter,
        rewritten_query=safe_candidate,
        source="llm+deterministic",
        confidence=0.8,
    )
