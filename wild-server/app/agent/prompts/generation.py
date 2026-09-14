"""建筑骨架与组件生成提示词。"""

def build_skeleton_prompt(
    spec_text: str,
    architecture_plan: dict | None = None,
    material_plan: dict | None = None,
) -> str:
    """Layer 0: 骨架生成专用 prompt
    
    职责：
    1. 读取已批准方案与对应的 WILD 能力、组装关系
    2. 保留本次设计决定，不以风格标签补充默认组件
    3. 生成基础骨架结构（walls、floors、columns、beams、stair）
    4. **输出 facade_plan + component_quota 设计清单**，为后续节点提供刚约束
    5. 不生成组件（door、window、roof 等留给后续专用节点）
    """
    import json as _json
    if architecture_plan:
        material_section = ""
        if material_plan:
            material_section = f"""

# 已批准材质方案（硬约束）

{_json.dumps(material_plan, ensure_ascii=False, indent=2)}

- `materials` 必须使用材质方案中的固定材质 ID 和参数，不得新增或改名。
- `assets` 只可包含材质方案 resolvedAssets 中的资产；不得生成 URL 或 assetId。
- 玻璃使用 `materialClass=glass`、`transmission`、`ior` 和 `thickness`，不得退回 opacity=0.35。
"""
        return f"""你是 WILD 建筑结构骨架工程师。把已批准方案落实为可校验的结构骨架。

# 已批准建筑方案（硬约束）

{_json.dumps(architecture_plan, ensure_ascii=False, indent=2)}
{material_section}

# 职责边界

- 严格服从 massing 的尺寸、层数和层高；不得重新做方案选择。
- `volumes` 是必须落实的体量分解：外墙只按该层处于 start_floor..end_floor 范围内的体量生成；每个层间标高的 floor 必须覆盖“下层体量封顶 ∪ 上层体量底板”，退台外露部分必须形成完整露台，且同一标高被大楼板包含的较小楼板不得重复生成。
- `structural_grid` 是结构组织硬约束；frame、hybrid、long_span 应用柱梁表达主要轴网，wall_bearing 也必须让承重墙和跨距与轴网一致。
- `complexity.level=detailed` 时，结构元素数量不得低于 `target_structural_elements`，并且必须能从逐层外墙轮廓识别出至少 `min_volumes` 个体量。复杂度来自退台、错动、主次体量和合理柱梁，不得靠复制重叠墙体凑数。
- `representation_mode=full` 时逐层落实 `modeled_floors`；`schematic` 时不得复制全部高层，只生成基座、完整总高度外壳、代表性楼板和顶部体量，总高度仍按 `floors × floor_height` 表达。
- 只生成 wall、floor、column、beam、stair；door、window、roof 由后续节点生成。
- 如果方案要求 balcony，不得用额外 floor 或 railing 预先模拟阳台；悬挑板和 U 形栏杆由 balcony 节点唯一负责。
- `geometry.components` 必须是空数组。
- 不输出 `_components`、DESIGN_BRIEF、Markdown、解释或多个 JSON。
- 只输出一个顶层直接包含 `meta`、`geometry`、`materials` 的 Blueprint JSON 对象。

# 几何硬规则

1. 每层外墙闭合，共享转角端点；wall.from[1] 是墙底，wall.to[1] 是墙顶且必须更大。
2. 每个 floor 同时使用三维 `from`/`to`，两个 Y 相同并等于该层底标高。
3. 按 `circulation.vertical_strategy` 生成 stair、核心筒或二者；多层建筑不能省略所选竖向交通。
4. 所有 element 的材质引用必须存在于 `materials`；至少定义墙、楼板、门窗框、门扇、屋顶和物理玻璃角色材质，供后续节点引用。
5. ID 使用 `wall_front_1`、`floor_1` 之类可读且唯一的名称。
6. 现代住宅不滥用装饰性外露角柱；但当 structural_grid 为 frame/hybrid 或复杂度目标明确要求时，必须生成承担体量与跨距关系的真实柱梁。
7. 退台交接层必须由下层完整顶板封闭；不得只画上层较小底板而让下层外围空间敞口，也不得叠放两块共面 floor。

# WILD 规范参考

{spec_text}

# 本次材质协议最终覆盖

若旧规范示例仍用 `opacity=0.35` 表达玻璃，以本次已批准材质方案为准：新玻璃必须使用物理透射字段，不得退回旧透明度写法。
"""

    return f"""你是 WILD 骨架生成器。依据用户需求决定本次体量和空间关系，参考知识只提供能力边界与条件规则。

- 只生成 wall、floor、column、beam、stair；geometry.components 留空。
- 层数、尺寸、轮廓和材质来自本次需求；未指定时自行作出有理由的设计决定。
- 共享墙角、楼层标高、楼板覆盖和交通衔接必须有效；开放亭廊不强加四面墙。
- 不照搬任何旧建筑案例、固定配色或门窗数量；附属组件只有功能需要才加入设计清单。
- 输出严格 Blueprint JSON，随后以 DESIGN_BRIEF: 标记输出一个设计清单 JSON。
- 设计清单包含 facade_plan（各立面的 bays、entrance_bay、window_spacing、ground_pattern、upper_pattern）、component_quota（实际需要组件的 min、max、note；屋顶可给 type）、design_notes（设计理由）、rag_reference（实际使用的能力或关系依据）。槽位与本次墙面和门窗数量一致。

# WILD 参考
{spec_text}
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
        rag_section = f"\n# 本次设计使用的能力与关系依据\n\n{design_brief['rag_reference']}\n"

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


def build_component_user_message(config, design_brief: dict | None = None) -> str:
    """构建单类组件节点的用户指令。"""
    quota_note = ""
    if design_brief:
        quota = design_brief.get("component_quota", {}).get(config.component_type, {})
        if quota:
            quota_note = (
                f"，精确数量范围: {quota.get('min', '?')}~{quota.get('max', '?')} 个 "
                f"({quota.get('note', '')})"
            )

    if config.is_list:
        return (
            "用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】和"
            f"【立面开口方案 / 构件配额】生成**合适数量**的 {config.label} 组件{quota_note}。\n\n"
            "重要：请仔细阅读 facade_plan（立面开口方案），严格按照每面墙的 "
            "max_openings 和 intent 生成。max_openings=0 的墙必须留空。\n\n"
            "只输出 JSON 数组，不要其他文字。"
        )
    return (
        "用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】"
        f"生成 {config.label} 构件。\n\n"
        "只输出单个 JSON 对象，不要数组，不要其他文字。"
    )
