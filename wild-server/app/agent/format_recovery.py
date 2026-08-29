"""计划节点共享的 JSON 定向格式恢复。

计划层节点（总体方案 / 平面 / 材质 / 执行计划）首次解析失败时，用一次
非思考调用要求返回单一 JSON，避免偶发格式抖动把整份 LLM 设计静默丢弃。
skeleton 节点自带同类的 ``_recover_blueprint_json``，这里收敛其余节点的通用路径。
"""
from __future__ import annotations

import time as _time

from loguru import logger

from app.agent.llm_invocation import invoke_llm
from app.agent.model_client import create_llm


async def recover_single_json(
    system_prompt: str,
    user_message: str,
    failed_reply: str,
    *,
    object_hint: str = "JSON 对象",
    extra_instruction: str = "",
    excerpt_limit: int = 8000,
) -> tuple[dict | None, dict]:
    """用一次非思考调用恢复为单一 JSON 对象。

    返回 ``(恢复后的 dict 或 None, 诊断 dict)``。调用失败返回 ``(None, 带 error 的诊断)``。
    """
    from app.utils.json_extractor import extract_json_object

    t0 = _time.time()
    failed_excerpt = failed_reply[:excerpt_limit]
    instruction = f"""

# 格式恢复（覆盖前面的输出格式要求）

这是失败恢复，不要重新解释设计过程。你只能输出一个严格合法的 {object_hint}：
- 不要 Markdown 围栏、注释、多余说明或额外文本；
- 如果上一轮输出缺失或 JSON 不完整，根据原始需求和协议补全。
{extra_instruction}
"""
    try:
        recovery_llm = create_llm(enable_thinking=False, streaming=False)
        result = await invoke_llm(
            recovery_llm,
            [
                {"role": "system", "content": system_prompt + instruction},
                {"role": "user", "content": f"原始用户需求：\n{user_message}\n\n上一轮无效输出（仅供修复，不要照抄其额外说明）：\n{failed_excerpt}"},
            ],
        )
        parsed = extract_json_object(result.content)
        return parsed, {
            "attempted": True,
            "success": parsed is not None,
            "llm_chars": len(result.content),
            "llm_ms": int((_time.time() - t0) * 1000),
            "token_usage": result.token_usage,
            "finish_reason": result.finish_reason,
        }
    except Exception as exc:
        logger.warning(f"[format_recovery] 定向格式恢复调用失败: {exc}")
        return None, {
            "attempted": True,
            "success": False,
            "llm_ms": int((_time.time() - t0) * 1000),
            "error": str(exc),
        }
