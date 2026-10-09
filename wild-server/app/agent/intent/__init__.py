"""意图分类域：提示词、确定性降级规则、结果契约与模型调用通道。

本包是 ``classifier`` 节点的家——与 ``generation.architecture`` 之于 ``architecture``
节点同构：``nodes/classifier_node.py`` 只是薄壳，实现都在这里。包内模块可以自由
重组，对外只保证 :data:`__all__` 里的这些契约。

 测试注入假模型用 ``patch("app.agent.intent.classify.invoke_llm")``（调用缝在
:mod:`.classify`）；改它的模块归属必须同批改桩件路径。
"""
from __future__ import annotations

from app.agent.state import IntentName, TargetKind

from .classify import classify_intent_decision
from .decision import IntentDecision, fallback_decision, normalize_intent_decision
from .prompt import (
    CLASSIFIER_PROMPT,
    EDIT_KEYWORDS,
    GENERATE_KEYWORDS,
    INTENT_LABELS,
    TARGET_KIND_LABELS,
)
from .rules import classify_keywords, fast_path_intent, is_explanatory_question
from .workflow import classifier_node

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
    "classify_keywords",
    "classifier_node",
    "fallback_decision",
    "fast_path_intent",
    "is_explanatory_question",
    "normalize_intent_decision",
]
