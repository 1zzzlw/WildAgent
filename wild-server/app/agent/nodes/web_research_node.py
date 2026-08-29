"""受控网络研究节点：本地知识不足时，经闸门批准后搜索并整理临时知识。

安全边界：
- 只调用 search_client（客户端层已做 SSRF/协议/长度防护）。
- 搜索结果只进本次 request 的临时上下文（state["web_research_context"]），
  不写任何知识库、不落盘。
- LLM 只负责把网页内容整理成结构化声明；能力映射由 knowledge_claims 确定性完成。
- 未配置 API key 时返回空上下文，Plan 模式回退纯本地（不报错）。
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

from app.agent.graph_state import GenerationState
from app.agent.llm_invocation import invoke_llm
from app.agent.model_client import create_llm
from app.agent.runtime_context import get_reasoning_callback
from app.agent.web import SearchQuery, create_search_client, WebResult
from app.agent.web.knowledge_claims import KnowledgeClaim, map_claim_to_capability
from app.utils.json_extractor import extract_json_array
from config import config


async def web_research_node(state: GenerationState) -> dict:
    """对缺失主题执行受控网络搜索，整理为临时知识上下文。

    输入：state["research_queries"]（缺失主题生成的研究问题）
    输出：state["web_research_context"]（本次请求临时上下文）
         state["web_research_diag"]（来源/命中/丢弃诊断）
    """
    started = time.time()
    queries: list[str] = state.get("research_queries") or []
    missing_topics: list[str] = state.get("research_missing_topics") or []
    callback = get_reasoning_callback()

    # 1. 客户端可用性检查：未配置 key -> 优雅降级，Plan 模式继续。
    client = create_search_client(
        enabled=config.web_research.enabled,
        provider=config.web_research.provider,
        api_key=config.web_research.api_key,
        base_url=config.web_research.base_url,
        max_content_chars=config.web_research.max_content_chars,
        timeout_ms=config.web_research.timeout_ms,
    )
    if client is None:
        logger.info(
            "[web_research] 网络研究未启用（缺 WEB_RESEARCH__API_KEY），"
            + f"缺失主题 {missing_topics[:3]} 走本地回退"
        )
        return {
            "web_research_context": "",
            "web_research_diag": {
                "enabled": False,
                "reason": "web_research 未配置 api_key",
                "missing_topics": missing_topics,
                "claims": [],
                "usable_count": 0,
                "dropped_count": 0,
                "total_ms": int((time.time() - started) * 1000),
            },
        }

    if callback:
        await callback(
            "web_research:progress",
            "\n### 网络研究\n本地知识对 "
            + str(len(missing_topics))
            + " 个主题覆盖不足，正在检索外部资料（仅本次请求临时使用，不会写入正式知识库）...\n",
        )

    # 2. 搜索缺失主题。
    effective_queries = queries or [f"建筑 {topic} 完整构成 规范" for topic in missing_topics[:3]]
    effective_queries = effective_queries[: config.web_research.max_queries]

    results: list[WebResult] = []
    seen_urls: set[str] = set()
    for raw_query in effective_queries:
        try:
            found = await client.search(
                SearchQuery(raw_query, max_results=config.web_research.max_pages)
            )
        except Exception as exc:
            logger.warning(f"[web_research] 搜索失败: {exc}")
            found = []
        for result in found:
            if result.url in seen_urls:
                continue
            seen_urls.add(result.url)
            results.append(result)

    # 3. 抓取前几个网页正文（受限并发）。
    if results:
        semaphore = asyncio.Semaphore(2)

        async def fetch_one(result: WebResult) -> WebResult:
            async with semaphore:
                try:
                    content = await client.fetch_page(result.url)
                    return result.with_content(content, time.time())
                except Exception as exc:
                    logger.warning(f"[web_research] 抓取失败 {result.url[:80]}: {exc}")
                    return result.with_content("", time.time())

        fetched = await asyncio.gather(
            *(fetch_one(r) for r in results[: config.web_research.max_pages])
        )
        results = [r for r in fetched if r.content]

    if not results:
        if callback:
            await callback(
                "web_research:progress",
                "未检索到可用外部资料，使用本地知识继续。\n",
            )
        return {
            "web_research_context": "",
            "web_research_diag": {
                "enabled": True,
                "reason": "no_results",
                "missing_topics": missing_topics,
                "claims": [],
                "usable_count": 0,
                "dropped_count": 0,
                "total_ms": int((time.time() - started) * 1000),
            },
        }

    # 4. LLM 把网页内容整理成结构化声明（非思考调用）。
    claims, llm_diag = await _summarize_to_claims(results, missing_topics)
    usable, dropped = _split_and_map(claims)

    # 5. 组装临时上下文（只含可用声明 + 来源）。
    context_parts: list[str] = []
    for claim in usable:
        source = f"（来源 {claim.source_url[:80]}）" if claim.source_url else ""
        mapping = ""
        if claim.degraded_to:
            mapping = " [能力映射: " + "; ".join(claim.degraded_to[:3]) + "]"
        context_parts.append(f"- {claim.claim}{mapping}{source}")
    web_context = "\n".join(context_parts) if context_parts else ""

    if callback:
        await callback(
            "web_research:progress",
            "网络研究完成：检索 "
            + str(len(results))
            + " 条，可用声明 "
            + str(len(usable))
            + " 条，丢弃 "
            + str(len(dropped))
            + " 条。结果仅用于本次生成，未写入知识库。\n",
        )

    return {
        "web_research_context": web_context[:6000],
        "web_research_diag": {
            "enabled": True,
            "reason": "ok" if web_context else "no_usable_claims",
            "missing_topics": missing_topics,
            "search_count": len(results),
            "claims": [claim.to_dict() for claim in claims],
            "usable_count": len(usable),
            "dropped_count": len(dropped),
            "source_urls": [r.url for r in results],
            "llm": llm_diag,
            "total_ms": int((time.time() - started) * 1000),
        },
    }


def _split_and_map(claims: list[KnowledgeClaim]):
    """能力映射 + 分组可用/丢弃。"""
    usable: list[KnowledgeClaim] = []
    dropped: list[KnowledgeClaim] = []
    for claim in claims:
        mapped = map_claim_to_capability(claim)
        if mapped.usable:
            usable.append(mapped)
        else:
            dropped.append(mapped)
    return usable, dropped


async def _summarize_to_claims(
    results: list[WebResult],
    missing_topics: list[str],
) -> tuple[list[KnowledgeClaim], dict]:
    """LLM 把网页正文整理成结构化声明数组。失败时返回空列表（不阻塞）。"""
    if not results:
        return [], {"llm_ms": 0, "error": "no_results"}

    t0 = time.time()
    payloads = []
    for result in results[:4]:
        payloads.append(
            f"### {result.title}\nURL: {result.url}\n来源: {result.source}"
            f"\n正文:\n{result.content[:2500]}"
        )
    web_text = "\n\n".join(payloads)
    prompt = f"""你是建筑知识整理助手。把下面网页资料整理成结构化知识声明，供本次建筑生成参考。

# 任务
- 每条声明必须是对建筑构成、构件组合、规范数值或降级建议的事实断言。
- 不要输出设计过程、营销话术或无法落地的抽象描述。
- 目标建筑类型：{", ".join(missing_topics) or "通用"}。

# 输出协议
只输出 JSON 数组，每个元素:
{{"claim": "事实断言", "topic": "主题", "applicable_building_types": ["建筑类型"],
  "region": "地区或留空", "year": "年份或留空", "norm_code": "规范号或留空",
  "source_url": "来源URL", "source_org": "来源机构", "confidence": "high|medium|low"}}

# 网页资料
{web_text}
"""
    try:
        llm = create_llm(enable_thinking=False, streaming=False)
        result = await invoke_llm(
            llm,
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"整理 {len(results)} 个网页资料中的建筑知识声明。"},
            ],
        )
        parsed = extract_json_array(result.content)
        claims: list[KnowledgeClaim] = []
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
                    continue
                claims.append(KnowledgeClaim(
                    claim=str(item["claim"]).strip(),
                    topic=str(item.get("topic") or "general"),
                    applicable_building_types=[
                        str(t) for t in (item.get("applicable_building_types") or [])
                    ],
                    region=str(item.get("region") or ""),
                    year=str(item.get("year") or ""),
                    norm_code=str(item.get("norm_code") or ""),
                    source_url=str(item.get("source_url") or ""),
                    source_org=str(item.get("source_org") or ""),
                    confidence=str(item.get("confidence") or "unknown"),
                ))
        return claims, {
            "llm_ms": int((time.time() - t0) * 1000),
            "claim_count": len(claims),
            "token_usage": result.token_usage,
        }
    except Exception as exc:
        logger.warning(f"[web_research] 声明整理失败: {exc}")
        return [], {"llm_ms": int((time.time() - t0) * 1000), "error": str(exc)}
