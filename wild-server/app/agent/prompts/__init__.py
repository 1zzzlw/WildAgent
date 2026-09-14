"""按 Agent 阶段组织的提示词构建函数。"""

from .common import build_patch_recovery_prompt, build_system_prompt
from .generation import build_component_prompt, build_skeleton_prompt
from .planning import (
    build_architecture_plan_prompt,
    build_execution_plan_prompt,
    build_material_optimization_prompt,
    build_material_plan_prompt,
)
from .repair import build_callback_prompt

__all__ = [
    "build_architecture_plan_prompt",
    "build_callback_prompt",
    "build_component_prompt",
    "build_execution_plan_prompt",
    "build_material_optimization_prompt",
    "build_material_plan_prompt",
    "build_patch_recovery_prompt",
    "build_skeleton_prompt",
    "build_system_prompt",
]
