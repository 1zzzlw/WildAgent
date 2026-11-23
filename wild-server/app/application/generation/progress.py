"""节点语义、进度标签与思考通道投影。"""

_OUR_NODES = {
    "classifier", "chat", "patch", "architecture",
    "material_plan",
    "compile",
    # plan 驱动链的循环三节点：条目级进度在它们的输出里，不在节点名里
    "plan", "execute", "replanner",
    "final_validate",
}

_NODE_START_DETAILS = {
    "classifier": "分析用户意图",
    "chat": "RAG 检索知识库并生成回答",
    "patch": "分析当前场景并生成修改提案",
    "architecture": "生成并解析结构化设计图纸",
    "material_plan": "解析材质角色并匹配受控 PBR 资产",
    "compile": "装配已落实的图纸标记，检查版本与完整性",
    "plan": "从已批准设计展开构件任务与依赖",
    "execute": "执行当前串行条目或安全并发组",
    "replanner": "对账本轮结果并决定下一轮",
    "final_validate": "执行最终校验流水线",
}

_PROGRESS_SUFFIX = ":progress"

_NODE_LABELS = {
    "classifier": "意图分类",
    "chat": "知识问答",
    "patch": "场景修改",
    "architecture": "设计图纸",
    "material_plan": "材质方案",
    "compile": "最终编译",
    "plan": "执行计划",
    "execute": "执行计划条目",
    "replanner": "计划对账",
    "final_validate": "最终校验",
}


def _thinking_channel(node_name: str) -> str:
    """`"<node>:progress"` → `"progress"`（执行说明）；其余 → `"reasoning"`（模型过程）。"""

    return "progress" if str(node_name).endswith(_PROGRESS_SUFFIX) else "reasoning"


def _public_node_name(node_name: str) -> str:
    """去掉通道后缀，还原它挂在哪一个步骤上。"""

    return str(node_name).removesuffix(_PROGRESS_SUFFIX)


def _node_label(name: str) -> str:
    return _NODE_LABELS.get(name, name)
