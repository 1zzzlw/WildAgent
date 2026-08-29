"""
Layer -1: 意图分类节点（薄封装）。

共享判定逻辑位于 ``app.agent.intent_classifier``，返回意图、置信度、目标和降级来源。
"""
from app.agent.intent_classifier import classify_intent_decision


def _infer_style_preference(user_message: str) -> list[str]:
    """用规则从用户需求预选候选风格，供早期节点约束设计方向。

    风格包确认发生在主体装配之后（style_review），但总体方案/平面/材质节点
    生成时如果完全不知道风格，可能与最终风格包冲突（如 LLM 画平屋顶、风格包
    要求中式坡屋顶）。这里用风格包的 keywords 做轻量预选，只输出候选 id 列表，
    不调用 LLM；style_review 仍由用户最终确认/改选。
    """
    try:
        from app.agent.plan2build.style_registry import style_registry

        packages = style_registry.recommend(user_message, limit=3)
        return [str(item["id"]) for item in packages]
    except Exception:
        return []


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
    result = {
        "intent": decision.intent,
        "intent_confidence": decision.confidence,
        "intent_target": decision.target,
        "intent_requires_scene": decision.requires_scene,
        "intent_reason": decision.reason,
        "intent_source": decision.source,
    }
    if decision.intent == "generate":
        result["style_preference"] = _infer_style_preference(str(state.get("user_message") or ""))
    return result
