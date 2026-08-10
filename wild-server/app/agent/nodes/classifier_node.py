"""
Layer -1: 意图分类节点

快速判断用户输入意图：
- GENERATE: 用户想创建/生成/建造新建筑 → 路由到 skeleton
- EDIT: 用户想修改当前建筑 → 路由到 patch 节点
- CHAT: 用户询问专业知识/闲聊 → 路由到 chat 节点

使用极简 prompt + 轻量 LLM 调用，不消耗思考 tokens。
"""
from loguru import logger
from app.agent.model_client import create_llm

_CLASSIFIER_PROMPT = """你是建筑领域意图分类器。判断用户输入属于哪一类：

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


async def classifier_node(state: dict) -> dict:
    """意图分类：判断用户是想生成建筑还是知识问答"""

    user_message = state.get("user_message", "")
    logger.info(f"[classifier] 分类用户输入: {user_message[:80]}...")

    llm = create_llm(enable_thinking=False, streaming=False)

    try:
        has_current_scene = bool(state.get("current_blueprint"))
        response = await llm.ainvoke([
            {"role": "system", "content": _CLASSIFIER_PROMPT},
            {
                "role": "user",
                "content": (
                    f"当前是否存在可编辑场景: {'是' if has_current_scene else '否'}\n"
                    f"用户输入: {user_message}"
                ),
            },
        ])
        # upper() 将字母全部转换为大写
        # hasattr(response, "content") 检查 response 这个对象是否拥有名为 content 的属性。是 python 内置函数
        raw = (response.content if hasattr(response, "content") else str(response)).strip().upper()
    except Exception as e:
        logger.error(f"[classifier] LLM 调用失败: {e}")
        # 降级：用关键词判断
        raw = _keyword_classify(user_message, bool(state.get("current_blueprint")))

    # 归一化
    if "EDIT" in raw and state.get("current_blueprint"):
        intent = "edit"
    elif "CHAT" in raw:
        intent = "chat"
    elif "GENERATE" in raw:
        intent = "generate"
    else:
        # 兜底：含生成关键词 → generate，否则 chat
        intent = _keyword_classify(
            user_message,
            bool(state.get("current_blueprint")),
        ).lower()

    logger.info(f"[classifier] 意图: {intent} (raw={raw})")

    return {"intent": intent}


# ── 关键词降级分类 ──

_GENERATE_KEYWORDS = [
    "生成", "生产", "建造", "创建", "建一个", "画一个", "搭一个",
    "设计", "做一个", "来一个", "帮我做", "新建"
]

_EDIT_KEYWORDS = [
    "修改", "改成", "改为", "调整", "加宽", "加高", "加粗", "缩小",
    "放大", "移动", "旋转", "删除", "移除", "替换", "换成", "增加",
    "添加", "加一", "再加", "这个", "选中", "第三根", "当前",
    "材质", "纹理", "贴图", "质感", "粗糙度", "金属度", "法线强度",
]

def _has_generate_keywords(msg: str) -> bool:
    return any(kw in msg for kw in _GENERATE_KEYWORDS)


def _keyword_classify(msg: str, has_current_scene: bool = False) -> str:
    """LLM 不可用时的关键词降级"""
    if has_current_scene and any(kw in msg for kw in _EDIT_KEYWORDS):
        return "EDIT"
    if _has_generate_keywords(msg):
        return "GENERATE"
    return "CHAT"
