"""意图分类的确定性规则：无模型参与的降级路径。

这里的三条规则**都不参与正式路由**（正式路由由 :func:`.classify.classify_intent_decision`
调模型完成）：

- :func:`classify_keywords` 只在模型不可用时保底；
- :func:`fast_path_intent` 只给 RAG 预检一个高置信提示，调用方不得把它当最终 intent；
- :func:`is_explanatory_question` 是上面两条共用的元问题识别，避免误启动有副作用的生成。
"""
from __future__ import annotations

from app.agent.state import IntentName

from .prompt import EDIT_KEYWORDS, EXPLANATORY_QUESTION_MARKERS, GENERATE_KEYWORDS


def is_explanatory_question(message: str) -> bool:
    """这句是不是在问"怎么做/为什么/是什么"，而不是在要产物。"""

    text = str(message or "").strip()
    return any(marker in text for marker in EXPLANATORY_QUESTION_MARKERS)


def classify_keywords(message: str, has_current_scene: bool = False) -> IntentName:
    """模型不可用时的保守降级；元问题优先，避免误启动生成。"""

    if is_explanatory_question(message):
        return "chat"
    if has_current_scene and any(keyword in message for keyword in EDIT_KEYWORDS):
        return "edit"
    if any(keyword in message for keyword in GENERATE_KEYWORDS):
        return "generate"
    return "chat"


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


__all__ = ["classify_keywords", "fast_path_intent", "is_explanatory_question"]
