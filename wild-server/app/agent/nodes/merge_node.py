"""Blueprint 分片合并节点入口。

流程：收集分片 → 确定性对齐与清理 → 校验修复循环 → 写回合并结果。
"""

from app.agent.generation.assembly_workflow import merge_fragments_node

__all__ = ["merge_fragments_node"]
