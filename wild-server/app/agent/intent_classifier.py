"""共享意图分类器：快速与精密模式使用同一套判定逻辑，避免同一输入分流不一致。

正式路由由 ``classifier_node`` 调用大模型完成；关键词只用于模型不可用时降级，
以及在 RAG 检索前提供不改变正式路由结果的高置信提示。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from loguru import logger

from app.agent.llm_invocation import invoke_llm
from app.agent.model_client import create_llm

IntentName = Literal["generate", "edit", "chat"]


@dataclass(frozen=True, slots=True)
class IntentDecision:
    """可观测、可校验的意图分类结果。"""

    intent: IntentName
    confidence: float
    target: str
    requires_scene: bool
    reason: str
    source: Literal["llm", "fallback"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CLASSIFIER_PROMPT = """你是建筑领域意图分类器。判断用户输入属于哪一类：

**GENERATE** — 用户想要创建/生成/建造/设计/生产一个建筑或场景
  必须是要求系统实际交付建筑或场景，而不是讨论系统怎样完成生成。
  关键词：生成、生产、建造、创建、建一个、画一个、搭一个、设计、做一个、来一个
  示例：
  - "生成一个欧式别墅" → GENERATE
  - "生产一个中式庭院" → GENERATE
  - "建一个中式庭院" → GENERATE
  - "帮我设计一个小木屋" → GENERATE

**EDIT** — 已有当前场景，用户要求增加、删除、移动、替换或修改其中的构件/参数
  示例：
  - "把第三根柱子加粗" → EDIT
  - "在正门旁边加一扇窗" → EDIT
  - "删除屋顶上的烟囱" → EDIT
  - "整体改成现代风格" → EDIT

**CHAT** — 用户想要了解专业知识、询问概念、请教、闲聊（不涉及生成建筑）
  关键词：什么是、怎么理解、有什么特点、为什么、介绍一下、什么是XX
  示例：
  - "什么是飞檐？" → CHAT
  - "欧式别墅有什么特点" → CHAT
  - "栏杆一般多高合适？" → CHAT
  - "你生成一个建筑的实现思路是什么？" → CHAT
  - "这个 Agent 是怎么一步步生成建筑的？" → CHAT
  - "你好" → CHAT

判断完整句子的交付目标，不要因为句子中出现“生成”“设计”等词就判为 GENERATE。
只有用户要求现在创建产物时才是 GENERATE；询问生成方法、实现原理、节点流程、
能力边界或原因时均为 CHAT。

只输出以下 JSON，不要 Markdown 或其他文字：
{
  "intent": "generate | edit | chat",
  "confidence": 0.0,
  "target": "本次请求面向的对象或主题",
  "requires_scene": false,
  "reason": "一句话分类依据，不输出思维链"
}

confidence 必须为 0 到 1。EDIT 的 requires_scene 必须为 true；GENERATE 通常为 false。
如果信息不足或只是在询问方法，优先 CHAT，不要启动有副作用的生成或修改。"""

GENERATE_KEYWORDS = [
    "生成", "生产", "建造", "创建", "建一个", "画一个", "搭一个",
    "设计", "做一个", "来一个", "帮我做", "新建",
]

EDIT_KEYWORDS = [
    "修改", "改成", "改为", "调整", "加宽", "加高", "加粗", "缩小",
    "放大", "移动", "旋转", "删除", "移除", "替换", "换成", "增加",
    "添加", "加一", "再加", "这个", "选中", "第三根", "当前",
    "材质", "纹理", "贴图", "质感", "粗糙度", "金属度", "法线强度",
]

INTENT_LABELS = {
    "generate": "生成建筑",
    "edit": "修改场景",
    "chat": "知识问答",
}

META_QUESTION_MARKERS = (
    "实现思路", "实现原理", "工作原理", "实现方式", "实现方法",
    "实现流程", "生成流程", "设计流程", "技术方案", "节点流程",
    "怎么实现", "如何实现", "怎么生成", "如何生成", "为什么生成",
    "为什么会生成", "能力边界",
)

EXPLANATORY_QUESTION_MARKERS = (
    *META_QUESTION_MARKERS,
    "为什么", "是什么", "什么是", "怎么理解", "如何理解",
    "介绍一下", "解释一下", "有什么特点", "有什么区别", "原理是什么",
)


def _is_explanatory_question(message: str) -> bool:
    text = str(message or "").strip()
    return any(marker in text for marker in EXPLANATORY_QUESTION_MARKERS)


def classify_keywords(message: str, has_current_scene: bool = False) -> str:
    """模型不可用时的保守降级；元问题优先避免误启动生成。"""
    if _is_explanatory_question(message):
        return "chat"
    if has_current_scene and any(keyword in message for keyword in EDIT_KEYWORDS):
        return "edit"
    if any(keyword in message for keyword in GENERATE_KEYWORDS):
        return "generate"
    return "chat"


def fast_path_intent(message: str, has_current_scene: bool = False) -> str | None:
    """为 RAG 预检提供高置信提示，不参与正式意图路由。

    元问题、生成与编辑关键词并存、或完全没有关键词时返回 None，交给完整语义
    判断。调用方不得把这个提示当成最终 intent。
    """
    if _is_explanatory_question(message):
        return None
    has_generate = any(keyword in message for keyword in GENERATE_KEYWORDS)
    has_edit = has_current_scene and any(keyword in message for keyword in EDIT_KEYWORDS)
    if has_edit and not has_generate:
        return "edit"
    if has_generate and not has_edit:
        return "generate"
    return None


def _fallback_decision(
    message: str,
    has_current_scene: bool,
    reason: str,
) -> IntentDecision:
    intent = classify_keywords(message, has_current_scene)
    confidence = 0.9 if _is_explanatory_question(message) else 0.65
    return IntentDecision(
        intent=intent,
        confidence=confidence,
        target="current_scene" if intent == "edit" else "user_request",
        requires_scene=intent == "edit",
        reason=reason[:200],
        source="fallback",
    )


def _json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def normalize_intent_decision(
    raw: str,
    message: str,
    has_current_scene: bool,
) -> IntentDecision:
    """解析结构化模型结果，并兼容只返回单个旧标签的模型。"""
    payload = _json_object(raw)
    if payload is not None:
        intent = str(payload.get("intent") or "").strip().lower()
        if intent in {"generate", "edit", "chat"}:
            if intent != "chat" and _is_explanatory_question(message):
                return IntentDecision(
                    intent="chat",
                    confidence=0.95,
                    target="requested_explanation",
                    requires_scene=False,
                    reason="用户是在询问方法、原理或原因，不应执行场景变更",
                    source="llm",
                )
            if intent == "edit" and not has_current_scene:
                return IntentDecision(
                    intent="chat",
                    confidence=0.75,
                    target="missing_scene",
                    requires_scene=False,
                    reason="用户要求修改，但当前没有可编辑场景",
                    source="llm",
                )
            try:
                confidence = float(payload.get("confidence", 0.75))
            except (TypeError, ValueError):
                confidence = 0.75
            confidence = max(0.0, min(1.0, confidence))
            target = str(payload.get("target") or "user_request")[:120]
            reason = str(payload.get("reason") or "模型语义分类")[:200]
            return IntentDecision(
                intent=intent,
                confidence=confidence,
                target=target,
                requires_scene=intent == "edit",
                reason=reason,
                source="llm",
            )

    upper = (raw or "").strip().upper()
    matches = re.findall(r"\b(?:GENERATE|EDIT|CHAT)\b", upper)
    label = matches[0] if matches else ""
    if label == "EDIT" and has_current_scene:
        intent: IntentName = "edit"
    elif label == "CHAT":
        intent = "chat"
    elif label == "GENERATE":
        intent = "generate"
    else:
        return _fallback_decision(message, has_current_scene, "模型未返回合法意图")
    if intent != "chat" and _is_explanatory_question(message):
        return IntentDecision(
            intent="chat",
            confidence=0.95,
            target="requested_explanation",
            requires_scene=False,
            reason="用户是在询问方法、原理或原因，不应执行场景变更",
            source="llm",
        )
    return IntentDecision(
        intent=intent,
        confidence=0.75,
        target="current_scene" if intent == "edit" else "user_request",
        requires_scene=intent == "edit",
        reason="兼容旧版单标签模型输出",
        source="llm",
    )


def normalize_intent(raw: str, message: str, has_current_scene: bool) -> str:
    """兼容旧调用：只返回结构化决策中的 intent。"""
    return normalize_intent_decision(raw, message, has_current_scene).intent


def _normalized_recent_messages(
    recent_messages: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in (recent_messages or [])[-4:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        if role == "agent":
            role = "assistant"
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if content:
            normalized.append({"role": role, "content": content[:500]})
    return normalized


def _classifier_user_content(
    message: str,
    has_current_scene: bool,
    *,
    recent_messages: list[dict[str, Any]] | None,
    workflow_state: str,
    selection: list[str] | None,
    plan_mode: bool,
) -> str:
    history = _normalized_recent_messages(recent_messages)
    history_text = "\n".join(
        f"- {item['role']}: {item['content']}"
        for item in history
    ) or "- 无"
    selected = ", ".join(str(item) for item in (selection or [])[:12]) or "无"
    return (
        f"当前是否存在可编辑场景: {'是' if has_current_scene else '否'}\n"
        f"当前工作流状态: {workflow_state or 'idle'}\n"
        f"是否启用计划模式: {'是' if plan_mode else '否'}\n"
        f"当前选中构件: {selected}\n"
        f"最近对话:\n{history_text}\n"
        f"本轮用户输入: {message}"
    )


async def classify_intent_decision(
    message: str,
    has_current_scene: bool = False,
    llm=None,
    *,
    recent_messages: list[dict[str, Any]] | None = None,
    workflow_state: str = "idle",
    selection: list[str] | None = None,
    plan_mode: bool = False,
) -> IntentDecision:
    """始终使用 LLM 分类，并返回置信度、目标和安全降级来源。"""
    try:
        llm = llm or create_llm(enable_thinking=False, streaming=False)
        llm_result = await invoke_llm(
            llm,
            [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {
                    "role": "user",
                    "content": _classifier_user_content(
                        message,
                        has_current_scene,
                        recent_messages=recent_messages,
                        workflow_state=workflow_state,
                        selection=selection,
                        plan_mode=plan_mode,
                    ),
                },
            ],
        )
        raw = llm_result.content
    except Exception as exc:
        logger.error(f"[classifier] LLM 调用失败: {exc}")
        decision = _fallback_decision(
            message,
            has_current_scene,
            f"分类模型不可用: {type(exc).__name__}",
        )
        logger.info(
            f"[classifier] 意图: {decision.intent}, "
            f"confidence={decision.confidence:.2f} (raw=<fallback>)"
        )
        return decision

    decision = normalize_intent_decision(raw, message, has_current_scene)
    logger.info(
        f"[classifier] 意图: {decision.intent}, confidence={decision.confidence:.2f}, "
        f"source={decision.source} (raw={str(raw).strip()[:300]})"
    )
    return decision


async def classify_intent(
    message: str,
    has_current_scene: bool = False,
    llm=None,
    **context: Any,
) -> str:
    """兼容旧调用：执行结构化分类，但仅返回 intent 字符串。"""
    decision = await classify_intent_decision(
        message,
        has_current_scene,
        llm,
        **context,
    )
    return decision.intent
