"""
Layer -1: 意图分类节点（薄封装）。

共享判定逻辑位于 ``app.agent.intent_classifier``，快速与精密模式复用同一套分类器，
避免边界输入在两套模式下分流不一致。
"""
from app.agent.intent_classifier import classify_intent


async def classifier_node(state: dict) -> dict:
    """意图分类：判断用户是想生成建筑、修改场景还是知识问答。"""
    intent = await classify_intent(
        state.get("user_message", ""),
        bool(state.get("current_blueprint")),
    )
    return {"intent": intent}
