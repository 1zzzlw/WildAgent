"""按 Agent 阶段组织的提示词构建函数。"""

from .common import build_patch_recovery_prompt, build_system_prompt
from .chat import build_chat_system_prompt
from .generation import build_component_prompt, build_component_user_message, build_skeleton_prompt
from .planning import (
    append_approved_phase_guidance,
    build_architecture_plan_prompt,
    build_execution_plan_prompt,
    build_material_optimization_prompt,
    build_material_plan_prompt,
)
from .repair import build_callback_prompt
from .recovery import build_blueprint_recovery_messages, build_component_recovery_messages
from .research import build_claim_extraction_prompt

__all__ = [
    "append_approved_phase_guidance",
    "build_architecture_plan_prompt",
    "build_callback_prompt",
    "build_chat_system_prompt",
    "build_blueprint_recovery_messages",
    "build_claim_extraction_prompt",
    "build_component_prompt",
    "build_component_user_message",
    "build_component_recovery_messages",
    "build_execution_plan_prompt",
    "build_material_optimization_prompt",
    "build_material_plan_prompt",
    "build_patch_recovery_prompt",
    "build_skeleton_prompt",
    "build_system_prompt",
]
