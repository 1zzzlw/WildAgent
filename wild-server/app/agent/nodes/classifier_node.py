"""
Layer -1: 意图分类节点

快速判断用户输入意图：
- GENERATE: 用户想创建/生成/建造建筑 → 路由到 skeleton
- CHAT: 用户询问专业知识/闲聊 → 路由到 chat 节点

使用极简 prompt + 轻量 LLM 调用，不消耗思考 tokens。
"""
from loguru import logger
from app.agent.model_client import create_llm

_CLASSIFIER_PROMPT = """你是建筑领域意图分类器。判断用户输入属于哪一类：

**GENERATE** — 用户想要创建/生成/建造/设计一个建筑或场景
  关键词：生成、建造、创建、建一个、画一个、搭一个、设计、做一个、来一个
  示例：
  - "生成一个欧式别墅" → GENERATE
  - "建一个中式庭院" → GENERATE
  - "帮我设计一个小木屋" → GENERATE

**CHAT** — 用户想要了解专业知识、询问概念、请教、闲聊（不涉及生成建筑）
  关键词：什么是、怎么理解、有什么特点、为什么、介绍一下、什么是XX
  示例：
  - "什么是飞檐？" → CHAT
  - "欧式别墅有什么特点" → CHAT
  - "栏杆一般多高合适？" → CHAT
  - "你好" → CHAT

只回复 GENERATE 或 CHAT，不要任何其他文字。"""


async def classifier_node(state: dict) -> dict:
    """意图分类：判断用户是想生成建筑还是知识问答"""

    user_message = state.get("user_message", "")
    logger.info(f"[classifier] 分类用户输入: {user_message[:80]}...")

    llm = create_llm(enable_thinking=False, streaming=False)

    try:
        response = await llm.ainvoke([
            {"role": "system", "content": _CLASSIFIER_PROMPT},
            {"role": "user", "content": user_message},
        ])
        raw = (response.content if hasattr(response, "content") else str(response)).strip().upper()
    except Exception as e:
        logger.error(f"[classifier] LLM 调用失败: {e}")
        # 降级：用关键词判断
        raw = _keyword_classify(user_message)

    # 归一化
    if "CHAT" in raw:
        intent = "chat"
    elif "GENERATE" in raw:
        intent = "generate"
    else:
        # 兜底：含生成关键词 → generate，否则 chat
        intent = "generate" if _has_generate_keywords(user_message) else "chat"

    logger.info(f"[classifier] 意图: {intent} (raw={raw})")

    return {"intent": intent}


# ── 关键词降级分类 ──

_GENERATE_KEYWORDS = [
    "生成", "建造", "创建", "建一个", "画一个", "搭一个",
    "设计", "做一个", "来一个", "帮我做", "新建"
]

_CHAT_KEYWORDS = [
    "什么是", "怎么", "如何", "为什么", "介绍一下",
    "有什么", "特点", "区别", "比较", "哪种", "哪个好"
]


def _has_generate_keywords(msg: str) -> bool:
    return any(kw in msg for kw in _GENERATE_KEYWORDS)


def _keyword_classify(msg: str) -> str:
    """LLM 不可用时的关键词降级"""
    if _has_generate_keywords(msg):
        return "GENERATE"
    return "CHAT"
