"""意图分类节点入口。

流程：读取 GenerationState → 判定意图与交付对象类型 → 写回 ``intent_*`` 字段
（建筑目标额外预选风格包，供后续节点约束设计方向）。
具体用例位于 ``agent.intent.workflow``。
"""

from app.agent.intent.workflow import classifier_node

__all__ = ["classifier_node"]
