"""校验失败后的定向修复节点入口。

流程：选择可重试问题 → 生成白名单修复动作 → 复检 → 接受或拒绝候选。
"""

from app.agent.repair.workflow import callback_node

__all__ = ["callback_node"]
