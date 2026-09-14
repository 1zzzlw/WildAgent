"""建筑骨架生成节点入口。

流程：加载组装知识 → 调用模型 → 解析或恢复 Blueprint → 预检 → 写回骨架。
"""

from app.agent.generation.skeleton_workflow import skeleton_generator

__all__ = ["skeleton_generator"]
