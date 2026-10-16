"""现有 Blueprint 增量修改节点入口。

流程：读取 GenerationState 的 ``current_blueprint`` → 走统一 Agent 入口但只接受
ScenePatch 结果 → 写回 ``scene_patch`` / ``patch_reply`` / ``patch_diag``（仍需前端确认后才应用）。
具体用例位于 ``patch.workflow``。
"""

from app.agent.patch.workflow import patch_node

__all__ = ["patch_node"]
