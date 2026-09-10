"""Layer -1: WILD 项目知识问答节点。"""
import time as _time
from loguru import logger

from app.agent.model_client import create_llm
from app.agent.llm_invocation import invoke_llm
from app.agent.rag_citations import validate_answer_citations
from app.agent.rag_gate import RAGRetrievalRejected
from app.agent.rag_trace import (
    get_injected_chunk_ids,
    record_final_answer,
    record_rag_citations,
)
from app.agent.knowledge_policy import chat_knowledge_query_specs

_CHAT_SYSTEM_PROMPT = """你是 WILD 项目知识助手。参考资料只覆盖：

- WILD Blueprint 与 ScenePatch 的字段、坐标和引用协议；
- 当前引擎已经支持的构件、参数与能力边界；
- 已选择构件或系统的宿主、组装和校验关系。

# 回答原则

1. **基于知识库**：只能根据参考资料回答；引用格式必须为 `[引用:chunk_id]`
2. **不补建筑百科**：资料未覆盖的风格、类型学、工程规范或推荐尺寸，明确说明不在当前 WILD 知识范围内
3. **区分事实层级**：引擎支持、视觉近似、未实现能力和局部 JSON 示例不得混淆
4. **使用当前上下文**：涉及蓝图修改时结合调用方提供的当前 Blueprint；不能把文档示例 ID 或数值当作当前对象
5. **简洁准确**：聚焦字段、能力、关系及其限制

# 参考资料

{spec_text}
"""


async def chat_node(state: dict) -> dict:
    """RAG 知识问答：按三类活动知识检索后生成带引用回答。"""
    from app.services.agent_service import agent_service

    # 计算回答总耗时
    t0 = _time.time()

    user_message = state.get("user_message", "")
    logger.info(f"[chat] 知识问答: {user_message[:80]}...")

    # ── 1. 按活动知识角色检索 ──
    rag_t0 = _time.time()

    from app.spec.loader import SpecQuery

    queries = [
        SpecQuery(text, metadata_filter)
        for text, metadata_filter in chat_knowledge_query_specs(user_message)
    ]

    try:
        spec_text = agent_service.spec_loader.load_many(
            queries,
            per_query=3,
            purpose="chat",
        )
    except RAGRetrievalRejected as exc:
        refusal = str(exc)
        record_final_answer(refusal)
        return {
            "chat_reply": refusal,
            "chat_diag": {
                "label": "知识问答",
                "rag_chars": 0,
                "rag_ms": int((_time.time() - rag_t0) * 1000),
                "retrieval_gate": exc.decision.to_dict(),
                "cited_chunk_ids": [],
                "evidence_status": "insufficient",
            },
            "status": "refused",
        }
    rag_ms = int((_time.time() - rag_t0) * 1000)
    rag_chars = len(spec_text)

    logger.info(f"[chat] RAG 检索: {rag_chars} 字符, {rag_ms}ms")

    # ── 2. LLM 生成回答 ──
    system_prompt = _CHAT_SYSTEM_PROMPT.format(spec_text=spec_text)
    llm = create_llm(enable_thinking=False, streaming=False)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    llm_t0 = _time.time()
    reply_text = ""
    token_usage = None

    try:
        llm_result = await invoke_llm(llm, messages)
        reply_text = llm_result.content
        token_usage = llm_result.token_usage

    except Exception as e:
        logger.error(f"[chat] LLM 调用失败: {e}")
        return {
            "chat_reply": f"抱歉，知识库查询暂时不可用：{e}",
            "chat_diag": {"error": str(e), "rag_chars": rag_chars, "rag_ms": rag_ms},
            "status": "failed",
        }

    citation_result = validate_answer_citations(
        reply_text,
        get_injected_chunk_ids(),
    )
    reply_text = citation_result.answer
    record_rag_citations(
        citation_result.cited_chunk_ids,
        citation_result.invalid_chunk_ids,
        citation_result.appended_fallback,
    )
    record_final_answer(reply_text)

    llm_ms = int((_time.time() - llm_t0) * 1000)
    total_ms = int((_time.time() - t0) * 1000)

    logger.info(f"[chat] 回答完成: {len(reply_text)} 字符, LLM {llm_ms}ms, 总计 {total_ms}ms")

    return {
        "chat_reply": reply_text,
        "chat_diag": {
            "label": "知识问答",
            "rag_chars": rag_chars,
            "rag_ms": rag_ms,
            "llm_chars": len(reply_text),
            "llm_ms": llm_ms,
            "token_usage": token_usage,
            "cited_chunk_ids": list(citation_result.cited_chunk_ids),
            "invalid_cited_chunk_ids": list(citation_result.invalid_chunk_ids),
            "evidence_status": (
                "supported" if citation_result.cited_chunk_ids else "none"
            ),
            "total_ms": total_ms,
        },
        "status": "complete",
    }
