"""条目可以在执行中自己发起的知识检索（《动态节点设计规划》§4.10）。

**预取是主力，按需是补充**：处理器先用程序拼好的 query 预取一次（可复现），模型只在
发现"缺字段知识"时再补检索，且上限由 `tools_for` 声明（默认 2 次）。

两条安全要求不可放松：

1. 检索**必须带 metadata 过滤**（`doc_type` / `entity_type`），走既有的
   `SpecQuery` + `app/rag/security.py` 安全层——不给模型一个能查全库的口子，
   否则"它没查到"和"知识里真没有"永远分不清；
2. 命中结果**进上下文也进审计**：返回文本自带来源标题，审计侧记录查询与命中数。
"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from loguru import logger

from app.agent.generation.components import COMPONENT_REGISTRY

#: 单次工具调用返回的字符上限：工具输出会进上下文，必须有界。
MAX_RESULT_CHARS = 3000


def _entity_type_for(kind: str) -> str:
    config = COMPONENT_REGISTRY.get(kind)
    return config.entity_type if config is not None else ""


def search_knowledge_impl(
    query: str,
    *,
    kind: str = "",
    doc_type: str = "component",
    per_query: int = 2,
) -> str:
    """带过滤的知识检索。无 `kind` 时按基础元素检索，不放开全库。"""

    query = str(query or "").strip()
    if not query:
        return "❌ 查询为空：请给出具体的字段、构件或构造问题。"

    from app.agent.generation.components import get_implemented_components
    from app.spec.loader import SpecQuery

    filters: dict[str, Any] = {"doc_type": doc_type or "component"}
    entity_type = _entity_type_for(kind) if kind else ""
    if entity_type:
        filters["entity_type"] = entity_type
    elif kind and kind not in COMPONENT_REGISTRY:
        implemented = ", ".join(config.component_type for config in get_implemented_components())
        return f"❌ 未知构件类型 {kind!r}；当前支持：{implemented}"

    try:
        from app.services.agent_service import agent_service
    except Exception as exc:  # pragma: no cover - 基建不可用时不阻断生成
        logger.warning(f"[search_knowledge] 检索不可用: {exc}")
        return "❌ 知识库当前不可用，请基于已给约束作答。"

    try:
        text = agent_service.spec_loader.load_many(
            [SpecQuery(query, filters)], per_query=per_query
        )
    except Exception as exc:
        logger.warning(f"[search_knowledge] 检索失败: {exc}")
        return "❌ 检索失败，请基于已给约束作答。"

    if not text or not text.strip():
        return "（知识库没有检索到内容：请勿编造字段，改用已给约束并说明缺口。）"

    hits = [
        f"{hit.metadata.get('source', '?')} / {hit.metadata.get('heading', '?')}"
        for hit in getattr(agent_service.spec_loader, "last_results", [])
    ]
    logger.info(f"[search_knowledge] query={query[:120]!r} filters={filters} hits={hits}")
    header = f"# 检索结果（过滤 {filters}，命中 {len(hits)} 条）\n\n"
    return (header + text)[:MAX_RESULT_CHARS]


@tool
def search_knowledge(query: str, kind: str = "") -> str:
    """按需检索 WILD 规范与构件知识。

    Args:
        query: 具体的字段、构件或构造问题（不要只写"生成一个别墅"）。
        kind: 可选的构件类型，例如 door / window / roof；给了就按该类型的知识过滤。
    """

    return search_knowledge_impl(query, kind=kind)


__all__ = ["MAX_RESULT_CHARS", "search_knowledge", "search_knowledge_impl"]
