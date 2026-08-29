"""
Layer -1: 意图分类节点（薄封装）。

共享判定逻辑位于 ``app.agent.intent_classifier``，返回意图、置信度、目标和降级来源。
"""
from app.agent.intent_classifier import classify_intent_decision


async def classifier_node(state: dict) -> dict:
    """意图分类：判断用户是想生成建筑、修改场景还是知识问答。"""
    decision = await classify_intent_decision(
        state.get("user_message", ""),
        bool(state.get("current_blueprint")),
        recent_messages=state.get("recent_messages"),
        workflow_state=str(state.get("workflow_state") or "idle"),
        selection=state.get("selection"),
        plan_mode=bool(state.get("plan_mode")),
    )
    return {
        "intent": decision.intent,
        "intent_confidence": decision.confidence,
        "intent_target": decision.target,
        "intent_requires_scene": decision.requires_scene,
        "intent_reason": decision.reason,
        "intent_source": decision.source,
    }
