"""
Layer -1: RAG 知识问答节点

当意图分类为 CHAT 时，全面扫描 RAG 知识库，
用 LLM 生成专业的建筑领域知识回答。

特性：
- 多角度 RAG 检索（建筑类型、构件规则、设计原则）
- 流式输出回复内容到前端
- 不消耗 thinking tokens
"""
import time as _time
from loguru import logger

from app.agent.model_client import create_llm
from app.services.agent_service import agent_service

_CHAT_SYSTEM_PROMPT = """你是 WILD 建筑领域的专业知识助手。你精通以下领域：

- **建筑类型学**：欧式别墅、中式庭院、现代建筑、日式建筑等各类建筑的特征与设计原则
- **建筑构件**：门、窗、屋顶、栏杆、雨棚、阳台、灯具、坡道、凸窗、檐口、烟囱的规格与设计规范
- **空间设计**：墙体布局、楼板规划、柱网布置、开间进深、层高设计
- **材料与美学**：各类建筑材质特性、色彩搭配、风格协调

# 回答原则

1. **基于知识库**：优先结合提供的参考资料回答，明确标注信息来源
2. **专业准确**：使用建筑领域标准术语，数据精确
3. **结构清晰**：分点阐述，必要时给出对比和示例
4. **实用导向**：如果用户问题涉及具体参数（尺寸、间距等），给出推荐值范围
5. **简洁友好**：不要过度展开，聚焦用户的问题核心

# 参考资料

{spec_text}
"""


async def chat_node(state: dict) -> dict:
    """RAG 知识问答：全面扫描知识库 + LLM 生成专业回答"""

    t0 = _time.time()
    user_message = state.get("user_message", "")
    on_reasoning_delta = state.get("on_reasoning_delta")

    logger.info(f"[chat] 知识问答: {user_message[:80]}...")

    # ── 1. 全面 RAG 检索 ──
    rag_t0 = _time.time()

    # 多角度检索：建筑类型 + 构件规则 + 设计原则
    from app.spec.loader import SpecQuery

    queries = [
        SpecQuery(user_message, {}),  # 无过滤，全局搜索
        SpecQuery(f"{user_message} 建筑类型 设计特征 风格", {"doc_type": "component"}),
        SpecQuery(f"{user_message} 构件参数 规格 尺寸 规则", {}),
        SpecQuery(f"{user_message} 设计原则 空间布局 规范", {}),
    ]

    spec_text = agent_service.spec_loader.load_many(queries, per_query=3)
    rag_ms = int((_time.time() - rag_t0) * 1000)
    rag_chars = len(spec_text)

    logger.info(f"[chat] RAG 检索: {rag_chars} 字符, {rag_ms}ms")

    # ── 2. LLM 生成回答 ──
    system_prompt = _CHAT_SYSTEM_PROMPT.format(spec_text=spec_text)
    use_streaming = on_reasoning_delta is not None

    llm = create_llm(enable_thinking=False, streaming=use_streaming)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    llm_t0 = _time.time()
    reply_text = ""
    token_usage = None

    try:
        if use_streaming:
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    delta = chunk.content
                    reply_text += delta
                    # 流式推送给前端（使用 chat_reply 作为 node_name）
                    await on_reasoning_delta("chat", delta)
                # 捕获 token usage
                if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                    usage = chunk.response_metadata.get("usage")
                    if usage:
                        token_usage = {
                            "input": usage.get("prompt_tokens", 0),
                            "output": usage.get("completion_tokens", 0),
                            "total": usage.get("total_tokens", 0),
                        }
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    token_usage = {
                        "input": chunk.usage_metadata.get("input_tokens", 0),
                        "output": chunk.usage_metadata.get("output_tokens", 0),
                        "total": chunk.usage_metadata.get("total_tokens", 0),
                    }
        else:
            response = await llm.ainvoke(messages)
            reply_text = response.content if hasattr(response, "content") else str(response)
            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("token_usage", {})
                if usage:
                    token_usage = {
                        "input": usage.get("prompt_tokens", 0),
                        "output": usage.get("completion_tokens", 0),
                        "total": usage.get("total_tokens", 0),
                    }

    except Exception as e:
        logger.error(f"[chat] LLM 调用失败: {e}")
        return {
            "chat_reply": f"抱歉，知识库查询暂时不可用：{e}",
            "chat_diag": {"error": str(e), "rag_chars": rag_chars, "rag_ms": rag_ms},
            "status": "failed",
        }

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
            "total_ms": total_ms,
        },
        "status": "complete",
    }
