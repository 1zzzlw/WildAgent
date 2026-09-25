"""执行节点入口：每轮执行计划里的一条条目。

实现见 `app/agent/plan/workflow.py`（与其它节点一样，入口只做转发）；
处理器在 `app/agent/plan/handlers.py`，有界工具循环在 `app/agent/plan/tool_loop.py`。
"""

from app.agent.plan.workflow import execute_node

__all__ = ["execute_node"]
