"""按 Agent 阶段组织的提示词构建函数。"""

from app.agent.prompts.common import build_patch_recovery_prompt
from app.agent.prompts.common import build_patch_system_prompt
from app.agent.prompts.chat import build_chat_system_prompt
from app.agent.prompts.generation import build_component_prompt
from app.agent.prompts.generation import build_component_user_message
from app.agent.prompts.plan import build_replan_prompt
from app.agent.prompts.plan import build_replan_user_message
from app.agent.prompts.planning import build_architecture_plan_prompt
from app.agent.prompts.planning import build_material_optimization_prompt
from app.agent.prompts.planning import build_material_plan_prompt
from app.agent.prompts.repair import build_callback_prompt
from app.agent.prompts.recovery import build_component_recovery_messages

__all__ = [
    "build_architecture_plan_prompt",
    "build_callback_prompt",
    "build_chat_system_prompt",
    "build_component_prompt",
    "build_component_user_message",
    "build_component_recovery_messages",
    "build_material_optimization_prompt",
    "build_material_plan_prompt",
    "build_patch_recovery_prompt",
    "build_replan_prompt",
    "build_replan_user_message",
    "build_patch_system_prompt",
]
