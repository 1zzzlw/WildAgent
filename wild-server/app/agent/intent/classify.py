"""意图分类的模型调用通道：组装输入、调用模型、归一化输出。

 本模块的 ``invoke_llm`` 是**被桩件替换的调用缝**：测试通过
``monkeypatch.setattr(app.agent.intent.classify, "invoke_llm", …)`` 或
``patch("app.agent.intent.classify.invoke_llm")`` 注入假模型。挪动它所在的模块
必须同批改桩件路径——桩件不生效会真连模型并挂住。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from app.llm.client import create_llm
from app.llm.errors import classify_model_error
from app.llm.invocation import invoke_llm

from .decision import IntentDecision, fallback_decision, normalize_intent_decision
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
    history_text = "\n".join(
        f"- {item['role']}: {item['content']}"
        for item in history
    ) or "- 无"
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
    """始终使用 LLM 分类，并返回置信度、目标和安全降级来源。"""

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
    except Exception as exc:
        logger.error(f"[classifier] LLM 调用失败: {exc}")

        fallback = fallback_decision(
            message,
            has_current_scene,
            f"分类模型不可用: {type(exc).__name__}",
        )

        # ⚠️ 这里刻意**没有**透传 fallback.target_kind，重建后回落到默认值
        # "architecture"。当前 model_error 会让图立刻 END（``graph._classifier_dispatch``
        # 判 ``_terminal``），该字段不被任何下游消费，所以无实际影响；但若将来允许
        # "降级继续生成"，必须补上，否则模型故障时"生成一个桌子"会被当成建筑需求。
        decision = IntentDecision(
            intent=fallback.intent,
            confidence=fallback.confidence,
            target=fallback.target,
            requires_scene=fallback.requires_scene,
            reason=fallback.reason,
            source=fallback.source,
            model_error=classify_model_error(exc),
        )

        logger.info(
            f"[classifier] 意图: {decision.intent}, 目标类型: {decision.target_kind}, "
            f"confidence={decision.confidence:.2f} (raw=<fallback>)"
        )

        return decision

    # 修正并解析大模型的输出
    decision = normalize_intent_decision(raw, message, has_current_scene)
    logger.info(
        f"[classifier] 意图: {decision.intent}, 目标类型: {decision.target_kind}, "
        f"confidence={decision.confidence:.2f}, "
        f"source={decision.source} (raw={str(raw).strip()[:300]})"
    )
    return decision


__all__ = ["classify_intent_decision"]
