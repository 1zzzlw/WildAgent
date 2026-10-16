"""计划节点入口：模型定策略 → 程序确定性展开条目。

实现见 `app/agent/plan/workflow.py`（与其它节点一样，入口只做转发）。
"""

from app.agent.plan.workflow import plan_node

__all__ = ["plan_node"]
