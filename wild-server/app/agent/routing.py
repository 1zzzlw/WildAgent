"""过渡层：意图分类已迁往 ``app.agent.intent``。

本文件保留同名 re-export，**只为不改动既有调用点**（``api/ws_agent.py:58``、
``services/agent_service.py:1334`` 与若干测试）。不要再往这里加任何东西——
新代码请直接从真正的主人处导入：

- 意图分类（提示词 / 规则 / 契约 / 模型通道）→ ``app.agent.intent``
- 交付对象类型判定（``detect_target_kind`` / ``TargetKind``）→ ``app.agent.generation.architecture``
- 蓝图场景判空（``has_scene_content``）→ ``app.utils.blueprint_query``

下一轮会删除本文件：届时同步删 ``tests/agent/test_agent_module_boundaries.py``
根目录白名单里的 ``"routing.py"``，并把上面那些调用点改为直接导入。
"""
from __future__ import annotations

from app.agent.generation.architecture import TargetKind, detect_target_kind
from app.agent.intent import (
    CLASSIFIER_PROMPT,
    EDIT_KEYWORDS,
    GENERATE_KEYWORDS,
    INTENT_LABELS,
    TARGET_KIND_LABELS,
    IntentDecision,
    IntentName,
    classify_intent_decision,
    classify_keywords,
    fast_path_intent,
    is_explanatory_question,
    normalize_intent_decision,
)
from app.utils.blueprint_query import has_scene_content

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
    "detect_target_kind",
    "fast_path_intent",
    "has_scene_content",
    "is_explanatory_question",
    "normalize_intent_decision",
]
