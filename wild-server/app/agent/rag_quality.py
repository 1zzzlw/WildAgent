"""可复现的 RAG LLM-as-Judge 协议；只作为辅助评分，不参与硬门控。"""

from __future__ import annotations

import json
from typing import Any

from app.utils.json_extractor import extract_json_object


JUDGE_PROMPT_VERSION = "rag-judge-v1"


def build_rag_judge_prompt(question: str, answer: str, contexts: list[str]) -> str:
    evidence = "\n\n---\n\n".join(contexts)
    return f"""你是 RAG 回答质量评审器。只根据参考资料评分，不补充外部知识。

评分范围均为 0 到 1：
- answer_relevance：回答是否直接解决问题；
- faithfulness：回答中的事实是否能由参考资料支持；
- citation_quality：引用是否足以定位支持结论的证据。

输出严格 JSON：
{{"answer_relevance":0.0,"faithfulness":0.0,"citation_quality":0.0,"reason":"简短理由"}}

# 用户问题
{question}

# 回答
{answer}

# 参考资料
{evidence}
"""


async def judge_rag_answer(
    llm: Any,
    *,
    question: str,
    answer: str,
    contexts: list[str],
    model_name: str,
) -> dict[str, Any]:
    """执行一次 Judge，并固定返回模型名和 Prompt 版本以便复现。"""

    from app.agent.llm_invocation import invoke_llm

    prompt = build_rag_judge_prompt(question, answer, contexts)
    result = await invoke_llm(llm, [{"role": "user", "content": prompt}])
    parsed = extract_json_object(result.content)
    if not isinstance(parsed, dict):
        raise ValueError("Judge 未返回可解析 JSON")
    scores = {}
    for key in ("answer_relevance", "faithfulness", "citation_quality"):
        value = float(parsed.get(key, 0.0))
        scores[key] = min(1.0, max(0.0, value))
    return {
        **scores,
        "reason": str(parsed.get("reason") or "")[:1000],
        "model": model_name,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "token_usage": result.token_usage,
    }
