"""LLM 结构化输出失败后的定向恢复提示词。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.generation.components import ComponentConfig


def build_blueprint_recovery_messages(
    *,
    system_prompt: str,
    user_message: str,
    failed_reply: str,
    design_brief: dict | None,
) -> list[dict[str, str]]:
    """构建骨架 Blueprint JSON 恢复消息。"""
    instruction = """

# Blueprint 格式恢复（覆盖前面的输出格式要求）

这是一次失败恢复，不要重新解释设计过程。你只能输出一个严格合法的 JSON 对象：
- 顶层必须直接包含 meta、geometry、materials；
- geometry.elements 必须包含完整建筑骨架；
- geometry.components 必须是空数组；
- 不要输出 `_components`、DESIGN_BRIEF、Markdown 围栏、注释或额外文本；
- 如果上一轮 Blueprint 缺失或 JSON 不完整，根据原始需求和设计清单补全。
"""
    user_content = f"""原始用户需求：
{user_message}

已解析设计清单：
{json.dumps(design_brief or {}, ensure_ascii=False)}

上一轮无效输出（仅供修复，不要照抄其额外说明）：
{failed_reply[:12000]}
"""
    return [
        {"role": "system", "content": system_prompt + instruction},
        {"role": "user", "content": user_content},
    ]


def build_component_recovery_messages(
    *,
    config: ComponentConfig,
    system_prompt: str,
    user_message: str,
    failed_reply: str,
) -> list[dict[str, str]]:
    """构建单类组件 JSON 恢复消息。"""
    output_shape = "一个 JSON 数组" if config.is_list else "单个 JSON 对象"
    instruction = f"""

# 组件格式恢复（覆盖前面的输出格式要求）

这是失败恢复，不要重新解释设计过程。你只能输出 {output_shape}：
- 严格合法的 JSON，不要 Markdown 围栏、注释或额外文本；
- {config.component_type} 必须包含全部必填字段；
- 如果上一轮输出缺失或 JSON 不完整，根据原始需求和设计清单补全。
"""
    user_content = f"""原始用户需求：
{user_message}

上一轮无效输出（仅供修复，不要照抄其额外说明）：
{failed_reply[:6000]}
"""
    return [
        {"role": "system", "content": system_prompt + instruction},
        {"role": "user", "content": user_content},
    ]
