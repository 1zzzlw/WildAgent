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

from app.llm.invocation import invoke_llm
from app.llm.client import create_llm
from app.llm.errors import classify_model_error

IntentName = Literal["generate", "edit", "chat"]

#: 本轮要交付的**对象类型**，与 intent 正交。
#: - ``architecture``：建筑/构筑物/场地，走体量→立面→屋顶的完整方案链；
#: - ``object``：单个物件（家具、器物、陈设），没有体量，直接按构件生成。
#:
#: 为什么不是第四个 intent：``intent`` 回答"要不要现在产出"（generate/edit/chat），
#: ``target_kind`` 回答"产出什么"。两者正交——"改一下这个桌子"是 edit + object，
#: "生成一个别墅"是 generate + architecture；塞进同一个枚举会让每个分支都要再分叉一次。
TargetKind = Literal["architecture", "object"]


@dataclass(frozen=True, slots=True)
class IntentDecision:
    """可观测、可校验的意图分类结果。"""

    intent: IntentName
    confidence: float
    target: str
    requires_scene: bool
    reason: str
    source: Literal["llm", "fallback"]
    target_kind: TargetKind = "architecture"
    model_error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CLASSIFIER_PROMPT = """你是 3D 生成需求分类器。系统能从知识库生成多种 3D 建模产物，
**建筑只是其中最擅长的一类**，不是唯一目标。先判断意图，再判断交付对象类型。

## 第一步：判断意图

**GENERATE** — 用户想要创建/生成/建造/设计/生产一个交付物
  必须是要求系统实际交付产物，而不是讨论系统怎样完成生成。
  关键词：生成、生产、建造、创建、建一个、画一个、搭一个、设计、做一个、来一个
  示例：
  - "生成一个欧式别墅" → GENERATE
  - "生成一个桌子" → GENERATE
  - "帮我设计一个小木屋" → GENERATE

**EDIT** — 已有当前场景，用户要求增加、删除、移动、替换或修改其中的构件/参数
  示例：
  - "把第三根柱子加粗" → EDIT
  - "把这个桌子转 90 度" → EDIT
  - "整体改成现代风格" → EDIT

**CHAT** — 用户想要了解专业知识、询问概念、请教、闲聊（不涉及生成产物）
  关键词：什么是、怎么理解、有什么特点、为什么、介绍一下、什么是XX
  示例：
  - "什么是飞檐？" → CHAT
  - "桌子一般多高合适？" → CHAT
  - "你生成一个建筑的实现思路是什么？" → CHAT
  - "你好" → CHAT

判断完整句子的交付目标，不要因为句子中出现"生成""设计"等词就判为 GENERATE。
只有用户要求现在创建产物时才是 GENERATE；询问生成方法、实现原理、节点流程、
能力边界或原因时均为 CHAT。

## 第二步：判断目标类型 target_kind（只在 GENERATE 时判定）

判据只有一句：**交付物是不是建筑/构筑物/场地**。

- **"architecture"** —— 交付物是建筑、构筑物或场地。只要提到建筑类型（别墅、住宅、
  办公楼、学校、厂房、车站、寺庙、亭子、塔、院落…）、规模（几层、多大）或围护结构
  （墙、屋顶、门窗），就是这一类。
- **"object"** —— 交付物**不是建筑**时的默认答案。包括家具（桌、椅、沙发、床、柜、
  书架）、器物（花瓶、摆件）、人物或角色（小人、机器人）、装置与陈设（路灯、雕塑、
  盆栽、灯具）等一切"单个物件"。判断依据不是"它在不在下面这份例子里"——
  物件名是列不完的，**只要不是建筑就是物件**。
- **同时提到建筑与物件时（如"带家具的别墅"）判 "architecture"**，家具属于建筑的
  内部陈设，由建筑链一并处理。只有当**没有建筑主体**、用户要的就是那个物件本身时，
  才判 "object"。

不要因为"建筑更擅长"就把物件需求归成建筑：那会让用户拿到一个他没要的房子。
也不要因为"没在例子或词表里见过"就把物件需求归成建筑——那和上一条是同一个错误。

只输出以下 JSON，不要 Markdown 或其他文字：
{
  "intent": "generate | edit | chat",
  "confidence": 0.0,
  "target": "本次请求面向的对象或主题",
  "target_kind": "architecture | object",
  "requires_scene": false,
  "reason": "一句话分类依据，不输出思维链"
}

confidence 必须为 0 到 1。EDIT 的 requires_scene 必须为 true；GENERATE 通常为 false。
如果信息不足或只是在询问方法，优先 CHAT，不要启动有副作用的生成或修改。"""

GENERATE_KEYWORDS = [
    "生成", "生产", "建造", "创建", "建一个", "画一个", "搭一个",
    "设计", "做一个", "来一个", "帮我做", "新建",
]

INTENT_LABELS = {
    "generate": "生成",
    "edit": "修改场景",
    "chat": "知识问答",
}

TARGET_KIND_LABELS = {
    "architecture": "建筑方案",
    "object": "构件物件",
}

EDIT_KEYWORDS = [
    "修改", "改成", "改为", "调整", "加宽", "加高", "加粗", "缩小",
    "放大", "移动", "旋转", "删除", "移除", "替换", "换成", "增加",
    "添加", "加一", "再加", "这个", "选中", "第三根", "当前",
    "材质", "纹理", "贴图", "质感", "粗糙度", "金属度", "法线强度",
]

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
    # 判断 text 里面是否包含 EXPLANATORY_QUESTION_MARKERS 中的任意一个标记
    return any(marker in text for marker in EXPLANATORY_QUESTION_MARKERS)


def detect_target_kind(message: str, intent: str = "generate") -> TargetKind:
    """规则判定交付对象类型；只在模型不可用或模型没给该字段时使用。

    判据是**单侧的**：只有"命中了建筑类型闭集"这一个条件判 ``architecture``，
    其余一律 ``object``。反过来做（先枚举物件名、没命中就当建筑）是错的——

    - 建筑类型是有限闭集，"不是建筑" ⟹ "是物件" 这个推理成立；
    - 物件名是开放集，"不是已知物件" ⟹ "是建筑" 这个推理不成立，
      它只会把每个没被列举到的新物件名（小人、花瓶、路灯）都变成一栋房子。

    代价是不再"建筑优先"：像"带家具的别墅"这种同时含物件词的说法，靠的仍是
    闭集里的"别墅"命中，结论不变；而"生成一个书包"这类建筑词一个都没有的句子，
    现在会正确地进物件链，而不是被兜底成住宅。
    """

    if intent != "generate":
        return "architecture"
    from app.agent.generation.architecture import is_architecture_request

    return "architecture" if is_architecture_request(message) else "object"


def has_scene_content(blueprint) -> bool:
    """是否真的存在可编辑场景内容：按 elements/components 判空，而非 blueprint dict 的 truthiness。

    前端在新建/清空场景时可能传一个"空蓝图骨架"（有 meta/geometry/materials 键、
    elements=[]、components=[]），`bool(骨架)` 是 True，会把"没有场景"误判成"有场景"，
    于是空场景下的"生成一个玻璃幕墙"被当成 edit（`normalize_intent_decision` 里
    `edit && !has_current_scene → chat` 的兜底因此不触发）。
    """
    if not isinstance(blueprint, dict):
        return False
    geometry = blueprint.get("geometry")
    if not isinstance(geometry, dict):
        return False
    elements = geometry.get("elements")
    components = geometry.get("components")
    return bool(elements) or bool(components)


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
        target_kind=detect_target_kind(message, intent),
    )


def _json_object(raw: str) -> dict[str, Any] | None:
    # 两个作用：判断非空和清理外层空白，不处理中间内容
    text = str(raw or "").strip()

    # 去除 Markdown 代码块标记，兼容模型输出带 ```json 的情况
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)

    # 尝试解析 JSON 对象，忽略前后多余文本
    # text.find("{") 从开头开始找第一个 {，text.rfind("}") 从结尾开始找最后一个 }
    start, end = text.find("{"), text.rfind("}")
    # 如果找不到 { 或 }，或者 } 在 { 之前，则返回 None
    if start < 0 or end <= start:
        return None
    try:
        # text[start:end+1] 字符串切片，左闭右开，所以当前代码意思是 截取 start 到 end 的子字符串，包括 start 和 end 位置的字符
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

    # 解析 JSON 对象
    payload = _json_object(raw)

    if payload is not None:
        # 解析 JSON 对象中的字段，确保类型正确并提供默认值，字符串字段去除前后空白并转换为小写
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
            # 目标类型只接受闭集内的值；模型给了别的写法就退到规则判定，
            # 不在这里自造类别（下游按这两个值分叉，第三值会让图路由落空）。
            raw_kind = str(payload.get("target_kind") or "").strip().lower()
            target_kind: TargetKind = (
                raw_kind if raw_kind in {"architecture", "object"}  # type: ignore[assignment]
                else detect_target_kind(message, intent)
            )
            if intent != "generate":
                target_kind = "architecture"
            return IntentDecision(
                intent=intent,
                confidence=confidence,
                target=target,
                requires_scene=intent == "edit",
                reason=reason,
                source="llm",
                target_kind=target_kind,
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
        target_kind=detect_target_kind(message, intent),
    )

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
                    ),
                },
            ],
        )
        raw = llm_result.content
    except Exception as exc:
        logger.error(f"[classifier] LLM 调用失败: {exc}")

        fallback = _fallback_decision(
            message,
            has_current_scene,
            f"分类模型不可用: {type(exc).__name__}",
        )

        decision = IntentDecision(
            intent=fallback.intent,
            confidence=fallback.confidence,
            target=fallback.target,
            requires_scene=fallback.requires_scene,
            reason=fallback.reason,
            source=fallback.source,
            model_error=classify_model_error(exc),
        )

        logger.info(
            f"[classifier] 意图: {decision.intent}, 目标类型: {decision.target_kind}, "
            f"confidence={decision.confidence:.2f} (raw=<fallback>)"
        )

        return decision

    # 修正并解析大模型的输出
    decision = normalize_intent_decision(raw, message, has_current_scene)
    logger.info(
        f"[classifier] 意图: {decision.intent}, 目标类型: {decision.target_kind}, "
        f"confidence={decision.confidence:.2f}, "
        f"source={decision.source} (raw={str(raw).strip()[:300]})"
    )
    return decision



