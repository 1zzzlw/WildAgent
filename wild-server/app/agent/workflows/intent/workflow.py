"""
意图分类节点入口。
"""

import asyncio
from langchain_core.runnables import RunnableConfig

from app.domain.design.architecture import resolve_complexity_profile
from app.domain.blueprint.query import has_scene_content

from app.agent.workflows.intent.classify import classify_intent_decision


async def classifier_node(state: dict, config: RunnableConfig | None = None) -> dict:
    """意图分类：判断用户想生成什么目标、修改场景还是知识问答。"""

    decision = await classify_intent_decision(
        state.get("user_message", ""),
        has_scene_content(state.get("current_blueprint")),
        recent_messages=state.get("recent_messages"),
        workflow_state=str(state.get("workflow_state") or "idle"),
        selection=state.get("selection"),
    )
    account_id = (config or {}).get("configurable", {}).get("account_id")
    if account_id:
        from app.infrastructure.persistence.repositories.activity import (
            charge_ai_request,
        )

        await asyncio.to_thread(
            charge_ai_request,
            account_id,
            state["request_id"],
            state["session_id"],
            decision.intent,
        )
    detail_level = resolve_complexity_profile(state.get("detail_level", "minimal"))[
        "level"
    ]
    result = {
        "detail_level": detail_level,
        "thinking_mode": state.get("thinking_mode") is True,
        "style_preference": [],
        "intent": decision.intent,
        "intent_target": decision.target,
        "intent_target_kind": decision.target_kind,
        "intent_profile": decision.profile,
        "intent_requires_scene": decision.requires_scene,
        "intent_reason": decision.reason,
        "intent_source": decision.source,
    }
    return result


__all__ = ["classifier_node"]
