"""检索构件知识并保留来源；未知设计类型也可查询构件资料。"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from loguru import logger

from app.agent.knowledge.component_names import resolve_component_name

# 完整首片保留；后续分片按预算加入，避免截断 JSON 示例。
MAX_RESULT_CHARS = 6000


def _entity_type_for(kind: str) -> str:
    return resolve_component_name(kind)["entity_type"] if kind else ""


def search_knowledge_result(
    query: str,
    *,
    kind: str = "",
    doc_type: str = "component",
    per_query: int = 2,
) -> dict[str, Any]:
    """带过滤的知识检索。无已知 entity_type 时按构件资料检索。"""

    query = str(query or "").strip()
    if not query:
        return {"text": "❌ 查询为空：请给出具体的字段、构件或构造问题。", "has_shape_reference": False}

    if kind:
        naming = resolve_component_name(kind)
        prefix = f"{naming['kind']} {naming['label']}"
        if (naming["entity_type"] or naming["kind"] in {"building_body", "assembly"}) and not query.startswith(prefix):
            query = f"{prefix} {query}"

    from app.spec.loader import SpecQuery

    filters: dict[str, Any] = {"doc_type": doc_type or "component"}
    entity_type = _entity_type_for(kind) if kind else ""
    if entity_type:
        filters["entity_type"] = entity_type
    exact_filters = ({"doc_type": doc_type or "component", "entity_name": naming["kind"]}
                     if kind and entity_type and naming["kind"] != entity_type else None)

    try:
        from app.services.agent_service import agent_service
    except Exception as exc:  # pragma: no cover - 基建不可用时不阻断生成
        logger.warning(f"[search_knowledge] 检索不可用: {exc}")
        return {"text": "❌ 知识库当前不可用，请基于已给约束作答。", "has_shape_reference": False}

    try:
        selected_filters = exact_filters or filters
        text = agent_service.spec_loader.load_many([SpecQuery(query, selected_filters)], per_query=per_query, include_base=False)
        if exact_filters and not (text and text.strip()):
            selected_filters = filters
            text = agent_service.spec_loader.load_many([SpecQuery(query, filters)], per_query=per_query, include_base=False)
        filters = selected_filters
    except Exception as exc:
        logger.warning(f"[search_knowledge] 检索失败: {exc}")
        return {"text": "❌ 检索失败，请基于已给约束作答。", "has_shape_reference": False}

    if not text or not text.strip():
        return {"text": "（知识库没有检索到内容：请勿编造字段，改用已给约束并说明缺口。）", "has_shape_reference": False}

    chunks = list(getattr(agent_service.spec_loader, "last_results", []))
    hits = [
        f"{hit.metadata.get('source', '?')} / {hit.metadata.get('heading', '?')}"
        for hit in chunks
    ]
    logger.info(
        f"[search_knowledge] query={query[:120]!r} filters={filters} hits={hits}"
    )
    header = f"# 检索结果（过滤 {filters}，命中 {len(hits)} 条）\n\n"
    selected, documents = [], []
    for hit in chunks:
        document = f"## {hit.metadata.get('source', '?')} / {hit.metadata.get('heading', '?')}\n{hit.document}"
        if documents and len(header + "\n\n".join([*documents, document])) > MAX_RESULT_CHARS:
            break
        selected.append(hit)
        documents.append(document)
    text = header + "\n\n".join(documents) if documents else (header + text)[:MAX_RESULT_CHARS]
    naming = resolve_component_name(kind) if kind else {"kind": "", "entity_type": ""}
    shape = any(
        (hit.metadata.get("topic") == "composition"
         and resolve_component_name(hit.metadata.get("entity_name", ""))["kind"] == naming["kind"])
        or (naming["entity_type"] and hit.metadata.get("entity_type") == naming["entity_type"]
            and "```json" in hit.document)
        for hit in selected
    )
    return {"text": text, "has_shape_reference": bool(shape)}


def search_knowledge_impl(query: str, *, kind: str = "", doc_type: str = "component", per_query: int = 2) -> str:
    return search_knowledge_result(query, kind=kind, doc_type=doc_type, per_query=per_query)["text"]


@tool
def search_knowledge(query: str, kind: str = "") -> str:
    """按需检索 WILD 规范与构件知识。

    Args:
        query: 具体的字段、构件或构造问题（不要只写"生成一个别墅"）。
        kind: 可选的构件类型，例如 door / window / roof；给了就按该类型的知识过滤。
    """

    return search_knowledge_impl(query, kind=kind)


__all__ = ["MAX_RESULT_CHARS", "search_knowledge", "search_knowledge_impl", "search_knowledge_result"]
