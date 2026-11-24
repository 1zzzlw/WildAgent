"""设计与构件执行共用的知识检索工具。"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain.tools import tool
from loguru import logger

from agent.utils.components.names import resolve_component_name

# 完整首片保留；后续分片按预算加入，避免截断 JSON 示例。
MAX_RESULT_CHARS = 6000


def _entity_type_for(kind: str) -> str:
    return resolve_component_name(kind)["entity_type"] if kind else ""


def search_knowledge_result(
    query: str,
    *,
    kind: str = "",
    doc_type: str | None = "component",
    per_query: int = 2,
) -> dict[str, Any]:
    """检索知识并保留来源。doc_type 为 None 时可跨文档类型查询。"""

    query = str(query or "").strip()
    if not query:
        return {
            "text": "❌ 查询为空：请给出具体的字段、构件或构造问题。",
            "has_shape_reference": False,
            "status": "invalid_query",
        }

    if kind:
        naming = resolve_component_name(kind)
        prefix = f"{naming['kind']} {naming['label']}"
        if (
            naming["entity_type"] or naming["kind"] in {"building_body", "assembly"}
        ) and not query.startswith(prefix):
            query = f"{prefix} {query}"

    from agent.rag.loader import SpecQuery

    filters: dict[str, Any] = (
        {"doc_type": doc_type or "component"} if doc_type is not None else {}
    )
    entity_type = _entity_type_for(kind) if kind else ""
    if entity_type:
        filters["entity_type"] = entity_type
    exact_filters = (
        {**filters, "entity_name": naming["kind"]}
        if kind and entity_type and naming["kind"] != entity_type
        else None
    )

    from agent.runtime import agent_runtime

    try:
        selected_filters = exact_filters or filters or None
        # 自然语言设计问题可能同时涉及规则和构件，避免别名推断把检索收窄。
        search_query = SpecQuery(query, selected_filters) if selected_filters else query
        result = agent_runtime.spec_loader.load_many_result(
            [search_query],
            per_query=per_query,
            include_base=False,
        )
        if (
            exact_filters
            and not result.text.strip()
            and not getattr(result, "error_type", None)
        ):
            selected_filters = filters
            result = agent_runtime.spec_loader.load_many_result(
                [SpecQuery(query, filters)], per_query=per_query, include_base=False
            )
        filters = selected_filters
    except Exception as exc:
        logger.warning(f"[search_knowledge] 检索失败: {exc}")
        return {
            "text": "❌ 检索失败，请基于已给约束作答。",
            "has_shape_reference": False,
            "status": "error",
            "error_type": type(exc).__name__,
        }

    if getattr(result, "error_type", None):
        return {
            "text": f"⚠️ 检索服务调用失败（{result.error_type}），未取得参考资料；"
            "请依据当前任务提供的字段协议继续。",
            "has_shape_reference": False,
            "chunk_ids": [],
            "status": "error",
            "error_type": result.error_type,
        }
    if not result.hits:
        return {
            "text": "（知识库没有检索到内容：请勿编造字段，改用已给约束并说明缺口。）",
            "has_shape_reference": False,
            "status": "no_match",
        }

    chunks = result.hits
    hits = [
        f"{hit.metadata.get('source', '?')} / {hit.metadata.get('heading', '?')}"
        for hit in chunks
    ]
    logger.info(
        f"[search_knowledge] query={query[:120]!r} filters={filters} hits={hits}"
    )
    header = f"# 检索结果（命中 {len(hits)} 条）\n\n"
    selected, documents = [], []
    for hit in chunks:
        document = f"## {hit.metadata.get('source', '?')} / {hit.metadata.get('heading', '?')}\n{hit.document}"
        if (
            documents
            and len(header + "\n\n".join([*documents, document])) > MAX_RESULT_CHARS
        ):
            break
        selected.append(hit)
        documents.append(document)
    text = (
        header + "\n\n".join(documents)
        if documents
        else (header + result.text)[:MAX_RESULT_CHARS]
    )
    from agent.utils.observability.trace import record_rag_context

    chunk_ids = [hit.id for hit in selected if getattr(hit, "id", None)]
    record_rag_context(
        operation="search_knowledge",
        base_chars=len(header),
        retrieved_chars=sum(len(hit.document) for hit in selected),
        context_chars=len(text),
        retrieved_count=len(selected),
        injected_chunk_ids=chunk_ids,
    )
    naming = resolve_component_name(kind) if kind else {"kind": "", "entity_type": ""}
    shape = any(
        (
            hit.metadata.get("topic") == "composition"
            and resolve_component_name(hit.metadata.get("entity_name", ""))["kind"]
            == naming["kind"]
        )
        or (
            naming["entity_type"]
            and hit.metadata.get("entity_type") == naming["entity_type"]
            and "```json" in hit.document
        )
        for hit in selected
    )
    return {
        "text": text,
        "has_shape_reference": bool(shape),
        "chunk_ids": chunk_ids,
        "status": "matched",
    }


def search_knowledge_impl(
    query: str, *, kind: str = "", doc_type: str = "component", per_query: int = 2
) -> str:
    return search_knowledge_result(
        query, kind=kind, doc_type=doc_type, per_query=per_query
    )["text"]


@tool
def search_knowledge(query: str, kind: str = "") -> str:
    """按需检索 WILD 规范与构件知识。

    Args:
        query: 具体的字段、构件或构造问题（不要只写"生成一个别墅"）。
        kind: 可选的构件类型，例如 door / window / roof；给了就按该类型的知识过滤。
    """

    return search_knowledge_impl(query, kind=kind)


@tool(response_format="content_and_artifact")
async def search_design_knowledge(query: str) -> tuple[str, dict[str, Any]]:
    """查阅 WILD 图纸字段、空间关系和构造示例。

    Args:
        query: 当前需要解决的一个具体问题，写出相关字段或构件。
    """
    query = query.strip()[:500]
    result = await asyncio.to_thread(search_knowledge_result, query, doc_type=None)
    evidence = {
        "query": query,
        "status": result["status"],
        "chunk_ids": result.get("chunk_ids", []),
    }
    if result.get("error_type"):
        evidence["error_type"] = result["error_type"]
    return result["text"], evidence


__all__ = [
    "MAX_RESULT_CHARS",
    "search_design_knowledge",
    "search_knowledge",
    "search_knowledge_impl",
    "search_knowledge_result",
]
