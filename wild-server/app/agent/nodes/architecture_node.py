"""总体建筑方案节点入口。

流程：读取 GenerationState → 生成并选择候选方案 → 写回 architecture_plan。
具体用例位于 ``generation.architecture.workflow``。
"""

from app.agent.generation.architecture.workflow import architecture_planner

__all__ = ["architecture_planner"]
