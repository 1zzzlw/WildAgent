"""确定性编译节点入口。

流程：读取 GenerationState → 把已批准的设计图纸**确定性**编译成蓝图（零模型调用）
→ 写回 ``skeleton_blueprint`` / ``skeleton_summary`` / ``compile_report``。
具体用例位于 ``design_flow.compile``。
"""

from app.agent.design_flow.compile import compile_node

__all__ = ["compile_node"]
