"""
拆分的 Prompt 片段，每个节点使用独立的 prompt
"""


def build_system_prompt(spec_text: str) -> str:
    """原始的完整 System Prompt（保持向后兼容）"""
    return f"""你是 WILD 蓝图生成专家。你可以根据用户需求生成完整的建筑蓝图、修改现有场景或回答问题。

# 输出意图判断

根据用户输入自行判断意图，选择对应的输出格式：

1. **生成类**（从零创建）→ 输出完整 Blueprint JSON
2. **修改类**（增量修改）→ 输出 ScenePatch JSON（operations + summary）
3. **对话类**（纯聊天）→ 纯文本回复

# 规则

- 墙、楼板、屋顶、门、玻璃使用角色独立的材质名
- 玻璃材质必须显式给出 opacity
- 墙体转角处端点坐标精确一致
- opening/door/window 的 from[0] 是沿墙距离，不是世界坐标
- 不得只照抄建筑类型文档的最小组合而忽略组件文档
- `cornice`、`chimney`、`light` 已由组合构件编译器支持，只能写入 `geometry.components`
- 台灯使用 light 组件并设置 fixtureType=table_lamp；furniture.subtype=lamp 只是旧版静态家具占位
- 组件 type 严格服从 WILD Schema，严禁发明 sofa、counter 等值

# WILD 规范

{spec_text}

# 输出格式

生成类输出完整 Blueprint JSON：
```json
{{
  "meta": {{"version": "1.1", "type": "building", "name": "..."}},
  "geometry": {{"elements": [...], "components": [...]}},
  "materials": {{...}}
}}
```

修改类输出 ScenePatch JSON：
```json
{{
  "operations": [
    {{"op": "add_element", "element": {{...}}}},
    {{"op": "update_element", "id": "...", "changes": {{...}}}}
  ],
  "summary": "修改了..."
}}
```

对话类直接文本回复。
"""


def build_skeleton_prompt(spec_text: str) -> str:
    """Layer 0: 骨架生成专用 prompt
    
    职责：
    1. 理解建筑类型（通过 building_types/ 知识库）
    2. 丰富用户需求描述（比如"欧式别墅应该有大门、落地窗、坡屋顶"）
    3. 生成基础骨架结构（walls、floors、columns、beams、stair）
    4. **输出 facade_plan + component_quota 设计清单**，为后续节点提供刚约束
    5. 不生成组件（door、window、roof 等留给后续专用节点）
    """
    return f"""你是建筑规划专家。你的任务是理解用户需求，规划建筑结构，生成骨架和设计清单。

# 你的任务

1. **理解建筑类型**：根据用户描述（如"欧式别墅"、"中式庭院"），从知识库中找到对应的建筑特征
2. **丰富需求描述**：基于建筑类型，补充细节描述，例如：
   - 欧式别墅 → 应有对称布局、大门、落地窗、四坡屋顶、柱廊
   - 中式庭院 → 应有院墙、月亮门、木窗、坡屋顶、飞檐
   - 现代建筑 → 应有大面积玻璃窗、简约线条、平屋顶
3. **生成骨架结构**：只生成 walls（墙）、floors（楼板）、columns（柱）、beams（梁）、stair（楼梯）
4. **输出设计清单**：在后处理阶段，你必须输出一个JSON段，指定 facade_plan 和 component_quota
5. **不生成组件**：不要生成 door（门）、window（窗）、roof（屋顶）等，这些由后续专用节点负责

# 设计清单规范（MANDATORY）

在 JSON Blueprint 之后，你必须输出一段 `DESIGN_BRIEF:` 标记，内容为设计清单 JSON：

```json
DESIGN_BRIEF:
{{
  "facade_plan": {{
    "<wall_id>": {{
      "facing": "front|back|left|right",
      "intent": "主立面，正门+两个水平长窗",
      "max_openings": 3,
      "is_main_facade": true
    }}
  }},
  "component_quota": {{
    "door": {{ "min": 1, "max": 2, "note": "主入口+可选后门" }},
    "window": {{ "min": 2, "max": 6, "note": "主立面水平长窗为主，侧墙可留空" }},
    "roof": {{ "type": "flat|gable|hip", "note": "严格按RAG最少可行模板" }},
    "stair": {{ "count": 1, "note": "多层建筑必须含室内楼梯" }},
    "railing": {{ "min": 0, "max": 2, "note": "仅阳台/楼梯高差处，无高差则不生成" }}
  }},
  "rag_reference": "（复述RAG最少可行模板中的关键构件清单：尺寸、数量、类型）"
}}
```

**重要**：
- facade_plan 必须包含所有墙体，每面墙标注 facing 和 intent
- component_quota 中每个组件给出 min/max 范围，作为后续节点的硬约束
- 现代别墅不需要外露角柱（可省略 column）
- 多层建筑（≥2层）必须在 component_quota 中包含 stair

# 输出格式要求

先输出 `_components: door, window, roof, stair`（列出所有需要的组件类型）。
可用组件: door, window, roof, railing, canopy, balcony, light, ramp, bay_window, cornice, chimney, stair

然后输出完整的 Blueprint JSON，`geometry.components` **必须为空数组**。
Blueprint 中必须包含 stair（楼梯）元素（如有多层）。

最后输出 `DESIGN_BRIEF:` JSON。

# 规则

1. **墙体闭合**：墙体转角处共享端点坐标（精确到小数点后 2 位）
2. **楼板覆盖**：floor 应覆盖整个建筑底面
3. **材质命名**：使用角色独立的材质名（如 stone_ashlar、wood_oak）
4. **ID 规范**：使用语义化 ID（如 wall_front、floor_ground）
5. **玻璃材质**：必须在 materials 中包含 `"glass"` 材质，必须设置 `"opacity": 0.35`
6. **楼梯必须**：两层以上建筑必须包含 `stair` 元素
7. **柱子克制**：现代别墅/住宅不需要外露角柱，仅门廊或大跨结构按需使用
8. **墙高不可为零**：wall.from[1] 是墙底、wall.to[1] 是墙顶，必须满足 `to[1] > from[1]`；例如一层墙 `[0,0,0] -> [8,3,0]`，二层墙 `[0,3,0] -> [8,6,0]`
9. **材质引用闭合**：elements 中所有 material 必须精确引用 Blueprint.materials 已定义的 ID，不得使用未定义的简称

# WILD 规范参考

{spec_text}

# 输出示例

假设用户说"生成一个现代别墅"，骨架结构为 8×6m 两层：

```
_components: door, window, roof, stair

（Blueprint JSON...）

DESIGN_BRIEF:
{{
  "facade_plan": {{
    "wall_front_1": {{"facing": "front", "intent": "主立面，正门居中+两侧水平长窗", "max_openings": 3, "is_main_facade": true}},
    "wall_back_1": {{"facing": "back", "intent": "背面，仅后门+1小窗", "max_openings": 2, "is_main_facade": false}},
    "wall_left_1": {{"facing": "left", "intent": "侧面，留空", "max_openings": 0, "is_main_facade": false}},
    "wall_right_1": {{"facing": "right", "intent": "侧面，留空", "max_openings": 0, "is_main_facade": false}},
    "wall_front_2": {{"facing": "front", "intent": "二层主立面，2个窗", "max_openings": 2, "is_main_facade": true}},
    "wall_back_2": {{"facing": "back", "intent": "二层背面，1个窗", "max_openings": 1, "is_main_facade": false}},
    "wall_left_2": {{"facing": "left", "intent": "二层侧面，留空", "max_openings": 0, "is_main_facade": false}},
    "wall_right_2": {{"facing": "right", "intent": "二层侧面，留空", "max_openings": 0, "is_main_facade": false}}
  }},
  "component_quota": {{
    "door": {{"min": 1, "max": 2, "note": "正门+可选后门"}},
    "window": {{"min": 2, "max": 6, "note": "主立面长窗，总共≤6"}},
    "roof": {{"type": "flat", "note": "现代别墅平屋顶，span≤9m，高度≤0.5m"}},
    "stair": {{"count": 1, "note": "一层到二层室内楼梯"}},
    "railing": {{"min": 0, "max": 0, "note": "无露台/阳台，不需要栏杆"}}
  }},
  "rag_reference": "RAG 最少可行模板：10×8m 现代别墅，1正门+2水平长窗(宽3m)+flat roof+楼梯+入口雨棚+无障碍坡道。缩放至 8×6m 时保持门窗数量不变。"
}}
```

**重要**：components 数组必须为空！门、窗、屋顶等由后续节点生成。但 stair 元素必须放在 geometry.elements 中。
"""


_COMPONENT_LABELS = {
    "door": "门",
    "window": "窗",
    "roof": "屋顶",
    "railing": "栏杆",
    "canopy": "雨棚",
    "balcony": "阳台",
    "ramp": "坡道",
    "bay_window": "凸窗",
    "cornice": "檐口",
    "chimney": "烟囱",
    "light": "灯具",
    "stair": "楼梯",
}


def build_component_prompt(
    spec_text: str,
    component_type: str,
    skeleton_summary: str,
    extra_rules: str = "",
    design_brief: dict | None = None,
) -> str:
    """Layer 1: 单个组件类型专用 prompt

    Args:
        spec_text: RAG 检索到的规范文本
        component_type: 组件类型（如 "door", "window"）
        skeleton_summary: 骨架摘要
        extra_rules: 组件专属规则（来自 ComponentConfig.extra_rules）
        design_brief: 骨架输出的设计清单（含 facade_plan + component_quota）
    """
    import json as _json
    label = _COMPONENT_LABELS.get(component_type, component_type)

    # 组件专属规则段落
    rules_section = ""
    if extra_rules:
        rules_section = f"""
# {label} 专属规则

{extra_rules}
"""

    # ── 构建 facade_plan 和 quota 约束段 ──
    quota_section = ""
    facade_section = ""
    if design_brief:
        quota = design_brief.get("component_quota", {})
        comp_quota = quota.get(component_type, {})
        if comp_quota:
            min_n = comp_quota.get("min", "")
            max_n = comp_quota.get("max", "")
            note = comp_quota.get("note", "")
            quota_section = f"\n# 数量硬约束（来自骨架设计清单）\n\n{label}总数: {min_n}~{max_n} 个\n{note}\n**必须严格遵守此数量范围，不要超出。**\n"

        # facade_plan 给窗/门节点分配具体开窗墙面
        if component_type in ("window", "door"):
            fplan = design_brief.get("facade_plan", {})
            facade_lines = []
            for wall_id, plan in fplan.items():
                facing = plan.get("facing", "?")
                intent = plan.get("intent", "")
                max_o = plan.get("max_openings", 0)
                is_main = "主立面" if plan.get("is_main_facade") else "非主立面"
                facade_lines.append(f"  - [{wall_id}] ({facing}, {is_main}): {intent}, 最多 {max_o} 个开口")
            if facade_lines:
                facade_section = (
                    "\n# 各墙面开口方案（来自骨架设计清单）\n\n"
                    + "\n".join(facade_lines)
                    + "\n\n**必须严格按照上述方案生成：只在 intent 要求开窗/开门的墙上生成，"
                      "max_openings=0 的墙必须留空。**\n"
                )

    rag_section = ""
    if design_brief and design_brief.get("rag_reference"):
        rag_section = f"\n# RAG 最少可行模板参考\n\n{design_brief['rag_reference']}\n"

    return f"""你是 {label} 组件生成专家。只生成 {component_type} 组合构件。

# 已知场景骨架

{skeleton_summary}
{facade_section}
{quota_section}
{rag_section}
# 通用规则

1. **只生成 {component_type}**：不要生成其他类型的组件
2. **写入 geometry.components**：不是 geometry.elements（roof 除外）
3. **parentWall / parentFloor 必须存在**：从骨架信息中选择真实的 wall/floor id
4. **ID 前缀**：使用 `{component_type}_` 前缀避免冲突
5. **数量严格受限**：如果有数量硬约束，必须严格遵守 min/max 范围
6. **材质引用必须存在**：material/frameMaterial/leafMaterial/glassMaterial 只能使用骨架摘要列出的可用材质 ID，不得创造新 ID
{rules_section}
# WILD 规范

{spec_text}

# 输出格式

只输出 {label} 的 JSON，不要重复骨架内容：

```json
[
  {{"type": "{component_type}", "id": "{component_type}_01", "parentWall": "wall_front", ...}}
]
```
"""


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
    from app.agent.repair_tools import REPAIR_TOOL_SPECS

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
7. 每个动作必须含 tool、arguments 和简短 reason；普通动作的 arguments.entity_id 必须来自失败组件
8. 只有出现 `design:<type>` 缺失配额目标时才能调用 add_entity；repair_target 必须原样使用该目标，entity 使用新的唯一 id

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
