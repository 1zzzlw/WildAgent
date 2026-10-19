"""RAG 预检提示与分类结果的元问题约束；不替代模型生成分类结果。"""
from __future__ import annotations

from app.agent.state import IntentName

from .prompt import EDIT_KEYWORDS, EXPLANATORY_QUESTION_MARKERS, GENERATE_KEYWORDS


def is_explanatory_question(message: str) -> bool:
    """这句是不是在问"怎么做/为什么/是什么"，而不是在要产物。"""

    text = str(message or "").strip()
    return any(marker in text for marker in EXPLANATORY_QUESTION_MARKERS)


def fast_path_intent(message: str, has_current_scene: bool = False) -> IntentName | None:
    """为 RAG 预检提供高置信提示，不参与正式意图路由。

    元问题、生成与编辑关键词并存、或完全没有关键词时返回 None，交给完整语义
    判断。调用方不得把这个提示当成最终 intent。
    """

    if is_explanatory_question(message):
        return None
    has_generate = any(keyword in message for keyword in GENERATE_KEYWORDS)
    has_edit = has_current_scene and any(keyword in message for keyword in EDIT_KEYWORDS)
    if has_edit and not has_generate:
        return "edit"
    if has_generate and not has_edit:
        return "generate"
    return None


__all__ = ["fast_path_intent", "is_explanatory_question"]
