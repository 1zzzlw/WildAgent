"""组装分类上下文、调用模型并解析结果。"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.llm.client import create_llm
from app.llm.errors import classify_model_error
from app.llm.invocation import invoke_llm

from .decision import IntentDecision, normalize_intent_decision
from .prompt import CLASSIFIER_PROMPT


def _normalized_recent_messages(
    recent_messages: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """只保留最近 4 条 user/assistant 消息，并把 agent 角色归一成 assistant。"""

    normalized: list[dict[str, str]] = []
    for item in (recent_messages or [])[-4:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        if role == "agent":
            role = "assistant"
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if content:
            normalized.append({"role": role, "content": content[:500]})
    return normalized


def _classifier_user_content(
    message: str,
    has_current_scene: bool,
    *,
    recent_messages: list[dict[str, Any]] | None,
    workflow_state: str,
    selection: list[str] | None,
) -> str:
    """拼模型的 user 消息：场景/工作流/选中/近期对话作为判定上下文。"""

    history = _normalized_recent_messages(recent_messages)

    history_text = (
        "\n".join(f"- {item['role']}: {item['content']}" for item in history) or "- 无"
    )
    selected = ", ".join(str(item) for item in (selection or [])[:12]) or "无"
    return (
        f"当前是否存在可编辑场景: {'是' if has_current_scene else '否'}\n"
        f"当前工作流状态: {workflow_state or 'idle'}\n"
        f"当前选中构件: {selected}\n"
        f"最近对话:\n{history_text}\n"
        f"本轮用户输入: {message}"
    )


async def classify_intent_decision(
    message: str,
    has_current_scene: bool = False,
    llm=None,
    *,
    recent_messages: list[dict[str, Any]] | None = None,
    workflow_state: str = "idle",
    selection: list[str] | None = None,
) -> IntentDecision:
    """使用 LLM 分类；模型调用或输出失败时返回终止信息。"""

    try:
        llm = llm or create_llm(enable_thinking=False, streaming=False)
        llm_result = await invoke_llm(
            llm,
            [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {
                    "role": "user",
                    "content": _classifier_user_content(
                        message,
                        has_current_scene,
                        recent_messages=recent_messages,
                        workflow_state=workflow_state,
                        selection=selection,
                    ),
                },
            ],
        )
        raw = llm_result.content
        decision = normalize_intent_decision(raw, message, has_current_scene)
    except Exception as exc:
        logger.error(f"[classifier] 意图分类失败: {exc}")
        model_error = classify_model_error(exc)
        return IntentDecision(
            intent="chat",
            target="user_request",
            requires_scene=False,
            reason=model_error["user_message"],
            source="llm",
            model_error=model_error,
        )

    logger.info(
        f"[classifier] 意图: {decision.intent}, 目标类型: {decision.target_kind}, "
        f"source={decision.source} (raw={str(raw).strip()[:300]})"
    )
    return decision


__all__ = ["classify_intent_decision"]
