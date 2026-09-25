"""
Layer -1: 意图分类节点（薄封装）。

共享判定逻辑位于 ``app.agent.routing``，返回意图、置信度、目标和降级来源。
"""
from app.agent.routing import classify_intent_decision, has_scene_content


def _infer_style_preference(user_message: str) -> list[str]:
    """用规则从用户需求预选候选风格，供早期节点约束设计方向。

    总体方案和材质节点需要提前知道设计方向，否则两个阶段可能互相冲突。
    这里用风格包的 keywords 做轻量预选，只输出候选 id 列表，不调用 LLM，
    也不引入额外审核节点。
    """
    try:
        from app.agent.generation.styles import style_registry

        packages = style_registry.recommend(user_message, limit=3)
        return [str(item["id"]) for item in packages]
    except Exception:
        return []


async def classifier_node(state: dict) -> dict:
    """意图分类：判断用户想生成什么目标、修改场景还是知识问答。"""
    decision = await classify_intent_decision(
        state.get("user_message", ""),
        has_scene_content(state.get("current_blueprint")),
        recent_messages=state.get("recent_messages"),
        workflow_state=str(state.get("workflow_state") or "idle"),
        selection=state.get("selection"),

    )
    result = {
        "intent": decision.intent,
        "intent_confidence": decision.confidence,
        "intent_target": decision.target,
        "intent_target_kind": decision.target_kind,
        "intent_requires_scene": decision.requires_scene,
        "intent_reason": decision.reason,
        "intent_source": decision.source,
    }
    if decision.model_error:
        result.update({
            "terminal_model_error": decision.model_error,
            "error": decision.model_error["user_message"],
            "status": "failed",
        })
        return result
    # 风格包是建筑/立面风格（如"新中式""现代"），物件链没有立面可套，
    # 因此只在建筑目标上预选，避免给一张桌子塞进"欧式别墅"的风格约束。
    if decision.intent == "generate" and decision.target_kind == "architecture":
        result["style_preference"] = _infer_style_preference(str(state.get("user_message") or ""))
    return result
