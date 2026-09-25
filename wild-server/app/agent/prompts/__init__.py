"""按 Agent 阶段组织的提示词构建函数。"""

from .common import build_patch_recovery_prompt, build_system_prompt
from .chat import build_chat_system_prompt
from .generation import build_component_prompt, build_component_user_message, build_skeleton_prompt
from .plan import (
    build_plan_strategy_prompt,
    build_plan_strategy_user_message,
    build_replan_prompt,
    build_replan_user_message,
)
from .planning import (
    build_architecture_plan_prompt,
    build_material_optimization_prompt,
    build_material_plan_prompt,
    build_object_design_prompt,
)
from .repair import build_callback_prompt
from .recovery import build_blueprint_recovery_messages, build_component_recovery_messages

__all__ = [
    "build_architecture_plan_prompt",
    "build_callback_prompt",
    "build_chat_system_prompt",
    "build_blueprint_recovery_messages",
    "build_component_prompt",
    "build_component_user_message",
    "build_component_recovery_messages",
    "build_material_optimization_prompt",
    "build_material_plan_prompt",
    "build_object_design_prompt",
    "build_patch_recovery_prompt",
    "build_plan_strategy_prompt",
    "build_plan_strategy_user_message",
    "build_replan_prompt",
    "build_replan_user_message",
    "build_skeleton_prompt",
    "build_system_prompt",
]
