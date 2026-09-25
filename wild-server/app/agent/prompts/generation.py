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
3. 按 `circulation.vertical_strategy` 生成 stair、核心筒或二者；多层建筑不能省略所选竖向交通。核心筒/电梯井是贯通构件，必须收进它跨越的每一层外墙轮廓。
4. 所有 element 的材质引用必须存在于 `materials`；至少定义墙、楼板、门窗框、门扇、屋顶和物理玻璃角色材质，供后续节点引用。
5. ID 使用 `wall_front_1`、`floor_1` 之类可读且唯一的名称。
6. 现代住宅不滥用装饰性外露角柱；但当 structural_grid 为 frame/hybrid 或复杂度目标明确要求时，必须生成承担体量与跨距关系的真实柱梁。
7. 退台交接层必须由下层完整顶板封闭；不得只画上层较小底板而让下层外围空间敞口，也不得叠放两块共面 floor。
8. 贯通多个楼层的竖向构件（核心筒、电梯井、贯通剪力墙、通高柱）必须落在它经过的**每一层**外墙轮廓之内。退台处上层外墙已经退进，贯通构件必须跟着退进；不得按底层轮廓通高到底，否则它会在退台层外凸成一堵独立墙体。判断依据是"逐层外墙的并集轮廓"，不是整栋建筑的外包络。
9. L/U 形等多体量建筑，component_quota.roof 的 min/max 应按体量数设定（每个体量各一块屋顶）；屋顶按其负责体量的轮廓取 span/depth，禁止只给一块屋顶盖住整栋外包络、把内院/天井也盖进去。

# WILD 规范参考

{spec_text}

# 本次材质协议最终覆盖

若旧规范示例仍用 `opacity=0.35` 表达玻璃，以本次已批准材质方案为准：新玻璃必须使用物理透射字段，不得退回旧透明度写法。
"""

    return f"""你是 WILD 骨架生成器。依据用户需求决定本次体量和空间关系，参考知识只提供能力边界与条件规则。

- 只生成 wall、floor、column、beam、stair；geometry.components 留空。
- 层数、尺寸、轮廓和材质来自本次需求；未指定时自行作出有理由的设计决定。
- 共享墙角、楼层标高、楼板覆盖和交通衔接必须有效；开放亭廊不强加四面墙。
- 跨越多个楼层的贯通构件（核心筒、电梯井、贯通剪力墙、通高柱）必须收进它经过的每一层外墙轮廓；退台处上层外墙已退进时，贯通构件必须跟着退进，不得按底层轮廓通高到底。
- L/U 形等多体量建筑按体量分别设定屋顶配额（每体量一块），屋顶按其负责体量的轮廓取值，禁止用单块屋顶盖住内院/天井。
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
    "elevator": "电梯",
    "stair": "楼梯",
    "furniture": "家具",
    "primitive": "通用几何体",
    "body": "简化人物",
}


# ─────────────────────────────────────────────────────────────────────────────
# generate 条目的五段提示词（《动态节点设计规划》§4.3）
#
#   顺序固定为 A → B → C → D → E，不得调换：
#     A 角色定义   跨类型**共用同一份**文本，只用 label / component_type 占位
#     B 任务切片   本条目的槽位、宿主与形态提示（程序从 design_brief / 骨架截取）
#     C 知识       字段、取值范围、单位、宿主关系、编译后产出（RAG 为唯一来源）
#     D 全局约束   材质白名单、配额、立面上限、档位（程序推导）
#     E 输出格式   JSON 骨架
#
# 自检方法：新增一个 kind 时，如果 A 段或 E 段需要改动，说明组装契约已被破坏。
# 这也是"每条条目的提示词不同"的正确实现方式——A/C 段共用，B/D 段随条目数据变化，
# 而**不是**给每个构件类型写一份模板（那是 `_COMPONENT_RULES` 的老路）。
# ─────────────────────────────────────────────────────────────────────────────

_ROLE_TEMPLATE = """你是 {label} 组件生成专家。本条目只做一件事：产出 {component_type} 片段。\
只生成 {component_type}，不得混入其它构件类型。

定位已经由程序完成——宿主、坐标、数量来自下面的【任务切片】与【全局约束】。\
你只负责字段与形状，不重新做方案选择，也不引入本次任务之外的新构件。"""

_NO_SLOT_HINT = (
    "本类型没有程序解析的精确槽位：数量与位置以【全局约束】的配额与方案为准，"
    "宿主必须取【任务切片】里真实存在的 id。"
)

_OBJECT_SPEC_RULE = (
    "每条输出对应一行规格：`count` 逐字决定条数；`width`/`depth`/`height` 逐字使用，"
    "不得替换成缺省尺寸、也不得为了\"好看\"改成同一规格的阵列；`placement` 是摆位意图，"
    "据此决定朝向与相邻关系（家具正面统一朝 +Z，可绕底面中心旋转）。"
    "规格没给的形态字段才由本节点补充。\n"
    "- 规格带 `parts`（通用几何组合）时：**每个零件输出为一个元素**，"
    "`shape` 与几何参数（`dimensions`/`radius`/`radiusTop`/`radiusBottom`/`height`/"
    "`path`/`profile`）逐字复制，不要改成别的形状、也不要合并零件。\n"
    "  · 零件 `position` 是相对**物件底面中心**的局部坐标（X/Z 以物件中心为 0，"
    "Y 以落地底面为 0），必须平移到世界坐标后再写入："
    "世界坐标 = 物件摆放锚点 + 零件局部坐标；整件物件的最低点落在行走面上。\n"
    "  · 本节点只做「摆放锚点」这一项判断（放哪儿、怎么转），"
    "**不重新设计零件形状**。\n"
    "- 规格带 `params`（简化人物）时：把 `params` 的字段逐字写成元素字段"
    "（`height`/`build`/`headShape`/`armLength`/`legLength`/`cloakLength`/`hoodUp`），"
    "脚底落在行走面上。\n"
    "- 规格只有 `subtype`（图鉴预设）时：按 KB 的家具契约生成对应子类型。"
)

_SLOT_RULE = (
    "每个输出必须对应一个不同槽位，并逐字复制该槽位的 `wall_id`→`parentWall`、`from`、"
    "`width`、`height`。不要自行计算或微调坐标——合并阶段会按同一口径再吸附一次。"
)

_GENERIC_SLOT_RULE = (
    "每个输出必须对应一个不同槽位；逐字复制槽位已经给出的宿主、位置和尺寸字段，"
    "不要自行修改。槽位未提供的形态字段才由本节点补充。"
)

_OUTPUT_TEMPLATE = """# 输出格式

只输出{expect}，不要 Markdown 代码块、不要解释、不要重复骨架内容：

{example}"""


def build_component_prompt(
    spec_text: str,
    component_type: str,
    skeleton_summary: str,
    extra_rules: str = "",
    design_brief: dict | None = None,
    plan_hint: str = "",
    material_ids: list[str] | None = None,
    detail_level: str = "",
) -> str:
    """按 A/B/C/D/E 五段拼装单条 generate 条目的提示词。

    Args:
        spec_text: RAG 检索到的规范文本（C 段主体）。
        component_type: 构件类型（如 "door"、"window"）。
        skeleton_summary: 骨架摘要，提供宿主 id、墙体几何与可用材质（B 段）。
        extra_rules: 字段约束的**兜底**——只在知识检索为空/太薄时传入（C 段尾部）。
        design_brief: 骨架输出的设计清单（facade_plan + component_quota + rag_reference）。
        plan_hint: plan 阶段给出的形态提示（subtype / guidance），只影响形状不影响坐标。
        material_ids: 材质 id 白名单，程序从骨架蓝图推导（D 段）。
        detail_level: 本次生成档位，只读不自证（D 段）。
    """
    label = _COMPONENT_LABELS.get(component_type, component_type)
    brief = design_brief if isinstance(design_brief, dict) else {}

    is_list = _is_list_output(component_type)

    return "\n\n".join(
        part
        for part in (
            # ── A 角色定义 ──
            _ROLE_TEMPLATE.format(label=label, component_type=component_type),
            # ── B 任务切片 ──
            _task_slice(component_type, brief, skeleton_summary, plan_hint),
            # ── C 知识 ──
            _knowledge(component_type, label, spec_text, extra_rules, brief),
            # ── D 全局约束 ──
            _global_constraints(component_type, label, brief, material_ids, detail_level),
            # ── E 输出格式 ──
            _OUTPUT_TEMPLATE.format(
                expect="单个 JSON 对象" if not is_list else "一个 JSON 数组",
                example=(
                    f'[{{"type": "{component_type}", "id": "{component_type}_01", '
                    f'{_host_placeholder(component_type)}...}}]'
                    if is_list
                    else f'{{"type": "{component_type}", "id": "{component_type}_01", ...}}'
                ),
            ),
        )
        if part
    )


def _is_list_output(component_type: str) -> bool:
    """输出形态来自注册表，不在这里重新列举类型。"""

    try:
        from app.agent.generation.components import COMPONENT_REGISTRY

        config = COMPONENT_REGISTRY.get(component_type)
        if config is not None:
            return bool(config.is_list)
    except Exception:  # pragma: no cover - 注册表不可用时按数组处理
        pass
    return True


def _host_bound(component_type: str) -> bool:
    """该类型是否有宿主（墙或楼板）。

    判定只取注册表的 `required_fields`，不按类型名硬编码：这样以后新增无宿主
    类型时，示例、通用规则、任务切片会一起跟着变。
    """

    try:
        from app.agent.generation.components import COMPONENT_REGISTRY

        config = COMPONENT_REGISTRY.get(component_type)
        required = list(config.required_fields) if config is not None else []
    except Exception:  # pragma: no cover - 注册表不可用时按有宿主处理
        return True
    return "parentWall" in required or "parentFloor" in required


def _host_placeholder(component_type: str) -> str:
    """E 段示例里的宿主占位串（无宿主的类型返回空串）。

    `parentWall` 不是"字段格式"，是一条**宿主关系**：给它写进示例，模型就会以为
    必须挂在某面墙上。家具（furniture）根本没有墙可挂，示例里出现宿主字段
    只会把模型推去做一件它做不到的事。
    """

    return '"parentWall": "wall_front", ' if _host_bound(component_type) else ""


def _task_slice(
    component_type: str,
    design_brief: dict,
    skeleton_summary: str,
    plan_hint: str,
) -> str:
    """B 段：本条目的槽位 + 宿主几何 + 形态提示。

    槽位切片**对所有 kind 一视同仁**：读取任意 ``*_slots`` 集合，只发本类型相关
    槽位，不发其它类型数据，也不发全量蓝图。
    """

    import json as _json

    from app.agent.generation.slot_utils import component_slots

    slots = component_slots(design_brief, component_type)
    #: 物件场景没有立面槽位，逐件规格由 `object_specs` 承载（见 objects/skeleton.py）。
    object_specs = [
        spec
        for spec in (design_brief.get("object_specs") or [])
        if isinstance(spec, dict) and str(spec.get("kind") or "") == component_type
    ]

    if slots:
        slot_rule = (
            _SLOT_RULE
            if component_type in {"door", "window", "bay_window"}
            else _GENERIC_SLOT_RULE
        )
        slot_block = (
            f"## 本条目的精确组件槽位（最高优先级，共 {len(slots)} 个）\n\n"
            + _json.dumps(slots, ensure_ascii=False, indent=2)
            + f"\n\n{slot_rule}\n"
        )
    elif object_specs:
        slot_block = (
            f"## 本条目的物件规格（最高优先级，共 {len(object_specs)} 行，逐行照做）\n\n"
            + _json.dumps(object_specs, ensure_ascii=False, indent=2)
            + f"\n\n{_OBJECT_SPEC_RULE}\n"
        )
    else:
        slot_block = f"## 本条目的槽位\n\n{_NO_SLOT_HINT}\n"

    hint_block = ""
    if plan_hint:
        hint_block = (
            f"\n## 计划给出的形态提示\n\n{plan_hint}\n"
            "\n这条只决定形态风格；坐标、数量与宿主仍以【全局约束】为准。\n"
        )

    return (
        f"# 任务切片 · 本条目\n\n{slot_block}\n"
        f"## 宿主与场景（只含本次可用的 id 与几何）\n\n{skeleton_summary}\n"
        f"{hint_block}"
    )


def _knowledge(
    component_type: str,
    label: str,
    spec_text: str,
    extra_rules: str,
    design_brief: dict,
) -> str:
    """C 段：字段级约束的**唯一来源**。

    优先知识库（`spec_text` 与 `rag_reference`），`extra_rules` 只在检索为空/太薄时
    由调用方传入，作为兜底而不是默认。
    """

    fallback = ""
    if extra_rules:
        fallback = (
            f"\n# {label} 专属规则（兜底：本次知识检索未提供足够字段约束）\n\n{extra_rules}\n"
        )

    rag_reference = design_brief.get("rag_reference")
    reference = (
        f"\n## 本次设计使用的能力与关系依据\n\n{rag_reference}\n" if rag_reference else ""
    )

    return (
        f"# 知识 · 字段与约束\n\n"
        f"字段名、取值范围、单位、宿主关系与编译后产出**只能来自本节**；"
        f"没有出现的字段不要凭空添加。\n\n"
        f"## WILD 规范（检索命中）\n\n{spec_text or '（本次检索未命中规范文本）'}\n"
        f"{reference}{fallback}"
    )


def _global_constraints(
    component_type: str,
    label: str,
    design_brief: dict,
    material_ids: list[str] | None,
    detail_level: str,
) -> str:
    """D 段：程序推导的全局约束（配额 / 立面上限 / 材质白名单 / 档位 / 通用规则）。"""

    sections: list[str] = []

    quota = design_brief.get("component_quota") or {}
    comp_quota = quota.get(component_type) if isinstance(quota, dict) else None
    if isinstance(comp_quota, dict) and comp_quota:
        min_n = comp_quota.get("min", "")
        max_n = comp_quota.get("max", "")
        # 物件场景里 quota 的 note 是"多行规格被压成的一行"，逐件信息在 B 段
        # `object_specs`；两者同时出现会让模型读到互相矛盾的两份清单，故此处只留总数。
        has_object_specs = any(
            isinstance(spec, dict) and str(spec.get("kind") or "") == component_type
            for spec in (design_brief.get("object_specs") or [])
        )
        note = "" if has_object_specs else comp_quota.get("note", "")
        sections.append(
            f"## 数量配额（来自骨架设计清单，必须遵守）\n\n"
            f"{label}总数: {min_n}~{max_n} 个\n{note}\n"
            "**必须严格遵守此数量范围，不要超出、也不要用固定对称阵列凑数。**"
        )

    facade_plan = design_brief.get("facade_plan") or {}
    if isinstance(facade_plan, dict) and facade_plan:
        lines = []
        for wall_id, plan in facade_plan.items():
            if not isinstance(plan, dict):
                continue
            facing = plan.get("facing", "?")
            intent = plan.get("intent", "")
            max_openings = plan.get("max_openings", 0)
            is_main = "主立面" if plan.get("is_main_facade") else "非主立面"
            lines.append(
                f"  - [{wall_id}] ({facing}, {is_main}): {intent}, 最多 {max_openings} 个开口"
            )
        if lines:
            sections.append(
                "## 各墙面开口上限（来自骨架设计清单）\n\n"
                + "\n".join(lines)
                + "\n\n`max_openings=0` 的墙必须留空；只在 intent 要求开口的墙上放置构件。"
            )

    if material_ids:
        sections.append(
            "## 材质 id 白名单\n\n"
            + ", ".join(sorted(material_ids))
            + "\n\n`material` / `frameMaterial` / `leafMaterial` / `glassMaterial` "
            "只能引用以上 id，不得创造新材质名。"
        )

    if detail_level:
        sections.append(
            f"## 本次生成档位\n\n{detail_level}"
            "（档位只决定细节丰富程度，不放宽数量与坐标约束）"
        )

    host_rule = (
        "2. **宿主必须真实存在**：`parentWall` / `parentFloor` 只能取【任务切片】里出现过的 id。\n"
        if _host_bound(component_type)
        else "2. **本类型没有宿主**：不要输出 `parentWall` / `parentFloor`——"
             "家具等无宿主构件靠自身 `position` 落位，不存在可挂的墙或楼板。\n"
    )
    sections.append(
        "## 通用规则\n\n"
        f"1. **只生成 {component_type}**，不要生成其它类型的构件。\n"
        f"{host_rule}"
        f"3. **id 前缀统一为 `{component_type}_`**，避免与骨架元素冲突。\n"
        "4. **写入位置以注册表为准**：构件写入 `geometry.components`，"
        "被声明为 element 的类型写入 `geometry.elements`（roof 等）。\n"
        "5. **材质引用必须存在**：只能使用白名单或骨架摘要列出的材质 id。\n"
        "6. **数量严格受限**：有配额时严格落在 min/max 区间内。"
    )

    return "# 全局约束 · 程序推导\n\n" + "\n\n".join(sections)



#: 真正吃"立面开口方案"的构件类型。其它类型（家具、栏杆、烟囱…）没有
#: max_openings 可讲，把这段塞给它们等于要求模型遵守一条不存在的约束。
_FACADE_BOUND_TYPES = frozenset({"door", "window", "bay_window"})


def build_component_user_message(config, design_brief: dict | None = None) -> str:
    """构建单类组件节点的用户指令。"""

    def _specs(kind: str) -> list[dict]:
        return [
            spec
            for spec in ((design_brief or {}).get("object_specs") or [])
            if isinstance(spec, dict) and str(spec.get("kind") or "") == kind
        ]

    quota_note = ""
    if design_brief:
        quota = design_brief.get("component_quota", {}).get(config.component_type, {})
        if quota:
            quota_note = (
                f"，精确数量范围: {quota.get('min', '?')}~{quota.get('max', '?')} 个 "
                f"({quota.get('note', '')})"
            )

    has_specs = bool(_specs(config.component_type))
    facade_note = (
        "\n\n重要：请仔细阅读 facade_plan（立面开口方案），严格按照每面墙的 "
        "max_openings 和 intent 生成。max_openings=0 的墙必须留空。"
        if config.component_type in _FACADE_BOUND_TYPES else ""
    )
    specs_note = (
        "\n\n重要：逐行照做上面的【物件规格】，`count` 与三个尺寸都逐字使用，"
        "不要合并、不要补齐成对称阵列。"
        if has_specs else ""
    )

    # 依据来源要按场景点明：物件场景没有立面，说"依据立面开口方案"等于指了一份
    # 不存在的清单；而"物件规格"是他真正要照做的那份。
    if has_specs:
        source_note = "【物件规格 / 构件配额】"
    elif config.component_type in _FACADE_BOUND_TYPES:
        source_note = "【立面开口方案 / 构件配额】"
    else:
        source_note = "【构件配额】"

    if config.is_list:
        return (
            "用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】和"
            f"{source_note}生成**合适数量**的 {config.label} 组件{quota_note}。"
            f"{facade_note}{specs_note}\n\n"
            "只输出 JSON 数组，不要其他文字。"
        )
    return (
        "用户需求已经由骨架节点分析和结构化。请依据上面【已知场景骨架】"
        f"生成 {config.label} 构件。\n\n"
        "只输出单个 JSON 对象，不要数组，不要其他文字。"
    )
