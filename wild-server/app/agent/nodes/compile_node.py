"""最终装配节点入口。

装配已有分片，必要时集中调用模型修复一次，写回蓝图和编译诊断。
具体用例位于 ``design_flow.compile``。
"""

from app.agent.design_flow.compile import compile_node

__all__ = ["compile_node"]
