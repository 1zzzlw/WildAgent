"""Blueprint 校验失败后的定向修复提示词。"""

def build_callback_prompt(
    spec_text: str,
    skeleton_summary: str,
    failed_components: list[dict],
    passed_component_ids: list[str],
) -> str:
    """回调修正专用 prompt

    Args:
        spec_text: 回调时精准 RAG 检索到的规范文本
        skeleton_summary: 当前骨架摘要
        failed_components: 需要修正的组件列表（含 error_message、current_params、tool_data）
        passed_component_ids: 已通过校验的组件 ID（LLM 不得修改）
    """
    import json as _json
    from app.agent.repair.tools import REPAIR_TOOL_SPECS

    failed_text = ""
    for fc in failed_components:
        comp_id = fc.get("component_id", "?")
        comp_type = fc.get("component_type", "?")
        error_msg = fc.get("error_message", "?")
        current_params = fc.get("current_params", {})
        tool_data = fc.get("tool_data", "")
        issues = fc.get("issues", [])
        suggested_tools = fc.get("suggested_tools", [])

        # 格式化当前参数（排除大型嵌套，只保留关键字段）
        params_display = _json.dumps(current_params, ensure_ascii=False, indent=2) if current_params else "（无）"

        failed_text += f"\n### {comp_id} ({comp_type})\n"
        failed_text += f"- 错误: {error_msg}\n"
        if issues:
            failed_text += "- 结构化问题:\n```json\n"
            failed_text += _json.dumps(issues, ensure_ascii=False, indent=2)
            failed_text += "\n```\n"
        if suggested_tools:
            failed_text += f"- 建议工具: {', '.join(suggested_tools)}\n"
        related_entity_ids = fc.get("related_entity_ids", [])
        if related_entity_ids:
            failed_text += (
                "- 允许修改的关联实体: "
                + ", ".join(related_entity_ids)
                + "\n"
            )
            related_entities = fc.get("related_entities", [])
            if related_entities:
                failed_text += "- 关联实体当前参数:\n```json\n"
                failed_text += _json.dumps(
                    related_entities,
                    ensure_ascii=False,
                    indent=2,
                )
                failed_text += "\n```\n"
        failed_text += f"- 当前参数:\n```json\n{params_display}\n```\n"

        if tool_data:
            # 工具数据截断到 500 字符防止 prompt 膨胀
            tool_short = tool_data[:500] + ("..." if len(tool_data) > 500 else "")
            failed_text += f"- 工具校验数据:\n```\n{tool_short}\n```\n"

    passed_text = ", ".join(passed_component_ids) if passed_component_ids else "无"
    tool_specs = _json.dumps(REPAIR_TOOL_SPECS, ensure_ascii=False, indent=2)

    return f"""你是 WILD 蓝图修正专家。以下是上一轮生成的组件校验错误，请逐一修正。

## 场景骨架（只读）

{skeleton_summary}

## 需要修正的组件

{failed_text}

## 已通过校验（不要修改）

{passed_text}

## 相关规范知识

{spec_text}

## 可用修复工具

```json
{tool_specs}
```

## 规则

1. 只允许调用上面列出的修复工具，只修正明确失败的组件
2. 使用骨架信息中列出的真实 wall/floor id 作为 parentWall/parentFloor
3. 利用「当前参数」作为起点，只提交解决错误所需的最小动作
4. 参考「工具校验数据」中的空间约束（墙长、有效范围等）确定正确值
5. 不要输出完整组件或完整 Blueprint，不得修改 id/type
6. 门窗 from[1] 是底部世界 Y：门使用父墙底 Y，窗使用父墙底 Y + 窗台高度；不是相对楼层的局部高度
7. 每个动作必须含 tool、arguments 和简短 reason；普通动作的 arguments.entity_id 必须来自失败组件或该问题列出的「允许修改的关联实体」
8. 只有出现 `design:<type>` 缺失配额目标时才能调用 add_entity；repair_target 必须原样使用该目标，entity 使用新的唯一 id
9. `remove_entity` 仅用于删除明确列出的关联超额实体；删除后仍必须满足全局最小配额和其他立面约束

## 输出格式

```json
[
  {{
    "tool": "move_opening",
    "arguments": {{"entity_id": "door_front", "along": 3.0, "elevation": 0.0}},
    "reason": "将门移动到父墙有效范围内"
  }},
  {{
    "tool": "resize_opening",
    "arguments": {{"entity_id": "window_right", "width": 1.2}},
    "reason": "缩小宽度以消除与相邻窗的重叠"
  }}
]
```
"""
