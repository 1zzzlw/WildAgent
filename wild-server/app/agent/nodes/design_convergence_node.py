"""设计收敛节点入口。

流程：读取 GenerationState → 在人工审核**之前**把图纸收敛到"确实编得出来"
（物件链穿过、收敛失败不阻断）→ 写回 ``architecture_plan`` / ``design_document``
/ ``design_convergence``。
具体用例位于 ``design_flow.convergence``。
"""

from app.agent.design_flow.convergence import design_convergence

__all__ = ["design_convergence"]
