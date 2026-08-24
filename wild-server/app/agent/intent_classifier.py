"""共享意图分类器：快速与精密模式使用同一套判定逻辑，避免同一输入分流不一致。

精密模式的 ``classifier_node`` 直接调用 ``classify_intent``；快速模式后续接入时也复用
同一份关键词表与归一化规则，从而消除两套意图判定在边界输入上的分歧。
"""
from __future__ import annotations

from loguru import logger

from app.agent.llm_invocation import invoke_llm
from app.agent.model_client import create_llm

CLASSIFIER_PROMPT = """你是建筑领域意图分类器。判断用户输入属于哪一类：

**GENERATE** — 用户想要创建/生成/建造/设计/生产一个建筑或场景
  "生成"与"生产"等近义表达均视为生成意图。
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
  - "你好" → CHAT

只回复 GENERATE、EDIT 或 CHAT，不要任何其他文字。"""

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


def classify_keywords(message: str, has_current_scene: bool = False) -> str:
    """确定性关键词降级，不依赖 LLM。返回小写 intent。"""
    if has_current_scene and any(keyword in message for keyword in EDIT_KEYWORDS):
        return "edit"
    if any(keyword in message for keyword in GENERATE_KEYWORDS):
        return "generate"
    return "chat"


def fast_path_intent(message: str, has_current_scene: bool = False) -> str | None:
    """高置信关键词短路：明显生成/编辑直接返回，歧义返回 None 由调用方走 LLM。

    只在“证据单向”时才短路——生成关键词与编辑关键词同时出现、或完全没有
    关键词时，宁可多花一次 LLM 往返也不误判。
    """
    has_generate = any(keyword in message for keyword in GENERATE_KEYWORDS)
    has_edit = has_current_scene and any(keyword in message for keyword in EDIT_KEYWORDS)
    if has_edit and not has_generate:
        return "edit"
    if has_generate and not has_edit:
        return "generate"
    return None


def normalize_intent(raw: str, message: str, has_current_scene: bool) -> str:
    """把模型原始回复归一化为小写 intent，无法判定时退回关键词降级。"""
    upper = (raw or "").strip().upper()
    if "EDIT" in upper and has_current_scene:
        return "edit"
    if "CHAT" in upper:
        return "chat"
    if "GENERATE" in upper:
        return "generate"
    return classify_keywords(message, has_current_scene)


async def classify_intent(
    message: str,
    has_current_scene: bool = False,
    llm=None,
) -> str:
    """LLM 分类 + 关键词降级。高置信关键词先短路，避免为明显意图付出 LLM 往返。"""
    fast = fast_path_intent(message, has_current_scene)
    if fast is not None:
        logger.info(f"[classifier] 意图: {fast} (raw=<keyword-fast-path>)")
        return fast

    llm = llm or create_llm(enable_thinking=False, streaming=False)

    try:
        llm_result = await invoke_llm(
            llm,
            [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"当前是否存在可编辑场景: {'是' if has_current_scene else '否'}\n"
                        f"用户输入: {message}"
                    ),
                },
            ],
        )
        raw = llm_result.content
    except Exception as exc:
        logger.error(f"[classifier] LLM 调用失败: {exc}")
        intent = classify_keywords(message, has_current_scene)
        logger.info(f"[classifier] 意图: {intent} (raw=<fallback>)")
        return intent

    intent = normalize_intent(raw, message, has_current_scene)
    logger.info(f"[classifier] 意图: {intent} (raw={str(raw).strip()})")
    return intent
