"""物件方案节点入口。

流程：读取 GenerationState → 生成物件清单方案 → 落成 ObjectDecisions 设计文档。
具体用例位于 ``generation.objects.workflow``。
"""

from app.agent.generation.objects.workflow import object_planner

__all__ = ["object_planner"]
