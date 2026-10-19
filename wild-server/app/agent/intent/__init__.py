"""意图分类域：提示词、结果校验、结果契约与模型调用通道。

本包是 ``classifier`` 节点的家——与 ``generation.architecture`` 之于 ``architecture``
节点同构：``nodes/classifier_node.py`` 只是薄壳，实现都在这里。包内模块可以自由
重组，对外只保证 :data:`__all__` 里的这些契约。
"""
from __future__ import annotations

from app.agent.state import IntentName, TargetKind

from .classify import classify_intent_decision
from .decision import IntentDecision, IntentOutputError, normalize_intent_decision
from .prompt import (
    CLASSIFIER_PROMPT,
    EDIT_KEYWORDS,
    GENERATE_KEYWORDS,
    INTENT_LABELS,
    TARGET_KIND_LABELS,
)
from .rules import fast_path_intent, is_explanatory_question
from .workflow import classifier_node

__all__ = [
    "CLASSIFIER_PROMPT",
    "EDIT_KEYWORDS",
    "GENERATE_KEYWORDS",
    "INTENT_LABELS",
    "TARGET_KIND_LABELS",
    "IntentDecision",
    "IntentOutputError",
    "IntentName",
    "TargetKind",
    "classify_intent_decision",
    "classifier_node",
    "fast_path_intent",
    "is_explanatory_question",
    "normalize_intent_decision",
]
