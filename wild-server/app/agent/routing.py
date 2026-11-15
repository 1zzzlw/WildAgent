"""过渡层：意图分类已迁往 ``app.agent.workflows.intent``。

本文件保留同名 re-export，供 WebSocket 等既有调用点使用。不要再往这里加任何东西——
新代码请直接从真正的主人处导入：

- 意图分类（提示词 / 规则 / 契约 / 模型通道）→ ``app.agent.workflows.intent``
- 交付对象类型判定（``detect_target_kind`` / ``TargetKind``）→ ``app.domain.design.architecture``
- 蓝图场景判空（``has_scene_content``）→ ``app.domain.blueprint.query``

"""
from __future__ import annotations

from app.domain.design.architecture import TargetKind
from app.domain.design.architecture import detect_target_kind
from app.agent.workflows.intent import CLASSIFIER_PROMPT
from app.agent.workflows.intent import EDIT_KEYWORDS
from app.agent.workflows.intent import GENERATE_KEYWORDS
from app.agent.workflows.intent import INTENT_LABELS
from app.agent.workflows.intent import TARGET_KIND_LABELS
from app.agent.workflows.intent import IntentDecision
from app.agent.workflows.intent import IntentName
from app.agent.workflows.intent import classify_intent_decision
from app.agent.workflows.intent import fast_path_intent
from app.agent.workflows.intent import is_explanatory_question
from app.agent.workflows.intent import normalize_intent_decision
from app.domain.blueprint.query import has_scene_content

__all__ = [
    "CLASSIFIER_PROMPT",
    "EDIT_KEYWORDS",
    "GENERATE_KEYWORDS",
    "INTENT_LABELS",
    "TARGET_KIND_LABELS",
    "IntentDecision",
    "IntentName",
    "TargetKind",
    "classify_intent_decision",
    "detect_target_kind",
    "fast_path_intent",
    "has_scene_content",
    "is_explanatory_question",
    "normalize_intent_decision",
]
