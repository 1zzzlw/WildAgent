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
- 新增或更新材质统一使用 `upsert_material`，不存在 `add_material` 操作
- 只优化已有纹理质感时使用 `tune_material`；该操作只克隆当前材质并调整受控数值，严禁修改图片 URL、`textureSet` 或资产清单

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


def build_patch_recovery_prompt(
    user_message: str,
    scene_summary: str,
    previous_reply: str,
) -> str:
    """首次增量编辑回复未形成 ScenePatch 时的单次格式恢复提示。"""
    return f"""上一次回复没有提供可解析的 ScenePatch。请根据同一请求重新输出。

# 当前场景（只读参考）

{scene_summary}

# 用户请求

{user_message}

# 上一次回复（仅用于恢复原意）

{previous_reply[:6000]}

# 强制输出协议

只输出一个 JSON 对象，不要输出 Markdown、解释、完整 Blueprint 或工具调用。
必须包含非空 `operations` 数组和 `summary`。
允许的操作只有：

- `add_element`: `{{"op":"add_element","element":{{...完整基础构件...}}}}`
- `update_element`: `{{"op":"update_element","id":"现有ID","changes":{{...}}}}`
- `remove_element`: `{{"op":"remove_element","id":"现有ID"}}`
- `add_component`: `{{"op":"add_component","component":{{...完整组合构件...}}}}`
- `update_component`: `{{"op":"update_component","id":"现有ID","changes":{{...}}}}`
- `remove_component`: `{{"op":"remove_component","id":"现有ID"}}`
- `upsert_material`: `{{"op":"upsert_material","name":"材质ID","material":{{...}}}}`
- `tune_material`: `{{"op":"tune_material","id":"选中构件ID","material_field":"material","new_name":"唯一材质ID","changes":{{"roughness":0.8,"normalScale":1.2,"uvScale":[2,2]}},"rationale":"调整理由"}}`

在原建筑旁边新增对象时只使用 add 操作，不要顺带修改原建筑。所有新增 ID 必须唯一。
"""


def build_material_optimization_prompt(selection: list[str]) -> str:
    """限制文本模型只优化已有材质参数，不接触图片或几何。"""
    selected = ", ".join(selection)
    return f"""

# 本次任务：现有纹理的材质质感优化（强制）

当前选中构件：{selected}

只允许输出 `tune_material` 操作。每项操作必须满足：

- `id` 必须是上述选中构件之一；不要修改任何未选中构件。
- `material_field` 必须是场景摘要中该构件已有的材质字段。
- `new_name` 必须是未使用的语义化材质 ID；系统会克隆原材质，避免影响共享同一材质的其他构件。
- `changes` 只能包含 `baseColor`、`roughness`、`metallic`、`albedo`、`emissive`、`opacity`、`normalScale`、`uvScale`。
- 0–1 参数必须在范围内；`normalScale` 为 0–4；`uvScale` 为两个 0–64 的正数。
- 只有场景摘要的 `maps` 或 `textureChannels` 明确包含 `normal` 时才能调整 `normalScale`；不要输出与当前值完全相同的参数。
- 只根据材料语义调整渲染参数。不得声称提高了图片分辨率、修复了接缝或生成了新纹理。
- 严禁输出 `upsert_asset`、`upsert_material`、`update_element`、`update_component`，严禁修改几何、图片 URL、Base64、纹理通道或 `textureSet`。
- `rationale` 用一句中文说明参数调整依据。

只输出一个 ScenePatch JSON 对象，包含非空 `operations` 和准确的 `summary`。
"""


def build_architecture_plan_prompt(spec_text: str, profile: dict | None = None) -> str:
    """生成路径第一阶段：只做建筑方案，不写 Blueprint 坐标。"""
    import json as _json
    profile_payload = dict(profile or {})
    if isinstance(profile_payload.get("shapes"), set):
        profile_payload["shapes"] = sorted(profile_payload["shapes"])
    profile_text = _json.dumps(profile_payload, ensure_ascii=False)
    return f"""你是建筑方案主创建筑师。先做体量、立面轴网和构件配额，不生成 WILD Blueprint。

# 任务

- 给出 2 个可实施候选，差异必须体现在体量比例、立面节奏或屋顶上。
- 方案要忠于用户层数、风格、功能和知识库；不要为了复杂而堆构件。
- 当前规划 profile 是：{profile_text}。尺寸、层数、形状和基础组件必须服从该 profile。
- front 是最小 Z 的主立面，back 是最大 Z，left/right 分别是最小/最大 X。
- ground_pattern / upper_pattern 的数组长度必须等于 bays；每项只能是 door、window、empty。
- 门只能出现在 ground_pattern。仅当 profile.require_front_entrance=true 时，front 才必须有且只有一个主门槽位。
- component_quota 必须与立面 pattern 能容纳的数量一致。
- required_components 以 profile.base_components 为基础；示例中的门窗屋顶不是所有 profile 的固定要求。
- `floors` 表示建筑语义总层数；复杂高层可用较小的 `modeled_floors` 做示意表达，并把 `representation_mode` 设为 `schematic`。

# 输出协议

只输出一个 JSON 对象，不要 Markdown 或解释：
{{
  "candidates": [
    {{
      "concept": "方案概念",
      "massing": {{"shape":"profile允许值","width":12,"depth":9,"floors":2,"modeled_floors":2,"representation_mode":"full|schematic","floor_height":3.2,"symmetry":true}},
      "facades": {{
        "front": {{"bays":5,"entrance_bay":3,"ground_pattern":["window","empty","door","empty","window"],"upper_pattern":["window","empty","window","empty","window"]}},
        "back":  {{"bays":4,"ground_pattern":["window","empty","empty","window"],"upper_pattern":["window","empty","empty","window"]}},
        "left":  {{"bays":3,"ground_pattern":["empty","window","empty"],"upper_pattern":["empty","window","empty"]}},
        "right": {{"bays":3,"ground_pattern":["empty","window","empty"],"upper_pattern":["empty","window","empty"]}}
      }},
      "roof": {{"type":"flat|gable|hip|dome|chinese_curved|chinese_pagoda","ridge_axis":"x|z","overhang":0.55}},
      "component_quota": {{
        "door": {{"min":1,"max":2,"note":"..."}},
        "window": {{"min":6,"max":14,"note":"..."}},
        "roof": {{"min":1,"max":1,"type":"hip","note":"..."}}
      }},
      "required_components": ["door","window","roof"],
      "design_rationale": ["入口与轴网关系", "上下层对齐关系", "屋顶与体量关系"]
    }}
  ]
}}

# 知识库参考

{spec_text}
"""


def build_skeleton_prompt(spec_text: str, architecture_plan: dict | None = None) -> str:
    """Layer 0: 骨架生成专用 prompt
    
    职责：
    1. 理解建筑类型（通过 building_types/ 知识库）
    2. 丰富用户需求描述（比如"欧式别墅应该有大门、落地窗、坡屋顶"）
    3. 生成基础骨架结构（walls、floors、columns、beams、stair）
    4. **输出 facade_plan + component_quota 设计清单**，为后续节点提供刚约束
    5. 不生成组件（door、window、roof 等留给后续专用节点）
    """
    import json as _json
    if architecture_plan:
        return f"""你是 WILD 建筑结构骨架工程师。把已批准方案落实为可校验的结构骨架。

# 已批准建筑方案（硬约束）

{_json.dumps(architecture_plan, ensure_ascii=False, indent=2)}

# 职责边界

- 严格服从 massing 的尺寸、层数和层高；不得重新做方案选择。
- `representation_mode=full` 时逐层落实 `modeled_floors`；`schematic` 时不得复制全部高层，只生成基座、完整总高度外壳、代表性楼板和顶部体量，总高度仍按 `floors × floor_height` 表达。
- 只生成 wall、floor、column、beam、stair；door、window、roof 由后续节点生成。
- 如果方案要求 balcony，不得用额外 floor 或 railing 预先模拟阳台；悬挑板和 U 形栏杆由 balcony 节点唯一负责。
- `geometry.components` 必须是空数组。
- 不输出 `_components`、DESIGN_BRIEF、Markdown、解释或多个 JSON。
- 只输出一个顶层直接包含 `meta`、`geometry`、`materials` 的 Blueprint JSON 对象。

# 几何硬规则

1. 每层外墙闭合，共享转角端点；wall.from[1] 是墙底，wall.to[1] 是墙顶且必须更大。
2. 每个 floor 同时使用三维 `from`/`to`，两个 Y 相同并等于该层底标高。
3. `full` 模式两层以上必须包含至少一个 stair 元素；`schematic` 高层不要求用一部长楼梯跨越全部高度。
4. 所有 element 的材质引用必须存在于 `materials`；至少定义墙、楼板、门窗框、门扇、屋顶和 opacity=0.35 的玻璃角色材质，供后续节点引用。
5. ID 使用 `wall_front_1`、`floor_1` 之类可读且唯一的名称。
6. 现代住宅不滥用外露角柱；只在方案或真实门廊/大跨需要时增加柱梁。

# WILD 规范参考

{spec_text}
"""

    plan_section = ""
    brief_instruction = "4. **输出设计清单**：在后处理阶段，你必须输出一个JSON段，指定 facade_plan 和 component_quota"
    output_tail = "最后输出 `DESIGN_BRIEF:` JSON。"
    final_override = ""

    return f"""你是建筑结构骨架专家。你的任务是把已批准方案落实为稳定的 WILD 骨架。
{plan_section}

# 你的任务

1. **理解建筑类型**：根据用户描述（如"欧式别墅"、"中式庭院"），从知识库中找到对应的建筑特征
2. **丰富需求描述**：基于建筑类型，补充细节描述，例如：
   - 欧式别墅 → 应有对称布局、大门、落地窗、四坡屋顶、柱廊
   - 中式庭院 → 应有院墙、月亮门、木窗、坡屋顶、飞檐
   - 现代建筑 → 应有大面积玻璃窗、简约线条、平屋顶
3. **生成骨架结构**：只生成 walls（墙）、floors（楼板）、columns（柱）、beams（梁）、stair（楼梯）
{brief_instruction}
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

{output_tail}

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
10. **楼板坐标格式**：每个 floor 必须同时包含三维数组 `from` 和 `to`，Y 值相同并表示楼板底标高；例如一层楼板 `"from":[0,0,0], "to":[8,0,6]`，二层楼板 `"from":[0,3,0], "to":[8,3,6]`。禁止用 position、size、polygon 或二维坐标替代
11. **阳台单一表达**：需要 balcony 时，不得再用 `floor_balcony` 或独立 railing 重复表达同一阳台

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
{final_override}
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
    slot_section = ""
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
            exact_slots = [
                slot for slot in design_brief.get("opening_slots", [])
                if isinstance(slot, dict) and slot.get("type") == component_type
            ]
            if exact_slots:
                slot_section = (
                    "\n# 程序解析的精确开口槽位（最高优先级）\n\n"
                    + _json.dumps(exact_slots, ensure_ascii=False, indent=2)
                    + "\n\n每个输出必须选择一个不同槽位，并逐字复制该槽位的 wall_id→parentWall、"
                      "from、width、height。不要自行计算或微调坐标；合并阶段会再次吸附。\n"
                )

    rag_section = ""
    if design_brief and design_brief.get("rag_reference"):
        rag_section = f"\n# RAG 最少可行模板参考\n\n{design_brief['rag_reference']}\n"

    return f"""你是 {label} 组件生成专家。只生成 {component_type} 组合构件。

# 已知场景骨架

{skeleton_summary}
{facade_section}
{slot_section}
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
