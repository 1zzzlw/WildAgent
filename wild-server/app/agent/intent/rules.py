"""解释类问题识别。"""

_EXPLANATORY_QUESTION_MARKERS = (
    "实现思路",
    "实现原理",
    "工作原理",
    "实现方式",
    "实现方法",
    "实现流程",
    "生成流程",
    "设计流程",
    "技术方案",
    "节点流程",
    "怎么实现",
    "如何实现",
    "怎么生成",
    "如何生成",
    "为什么生成",
    "为什么会生成",
    "能力边界",
    "为什么",
    "是什么",
    "什么是",
    "怎么理解",
    "如何理解",
    "介绍一下",
    "解释一下",
    "有什么特点",
    "有什么区别",
    "原理是什么",
)


def is_explanatory_question(message: str) -> bool:
    """这句是不是在问"怎么做/为什么/是什么"，而不是在要产物。"""

    text = str(message or "").strip()
    return any(marker in text for marker in _EXPLANATORY_QUESTION_MARKERS)
