"""组件生成提示词。"""

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
    "column": "柱",
}


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
            _global_constraints(component_type, label, brief, material_ids),
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
        from app.domain.components.registry import COMPONENT_REGISTRY

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
        from app.domain.components.registry import COMPONENT_REGISTRY

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

    from app.domain.components.slots import component_slots

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
        f"## 当前设计意图（落实形态与材料，不改写槽位）\n\n"
        + _json.dumps({"design_intent": design_brief.get("design_intent"),
                      "design_notes": design_brief.get("design_notes") or []}, ensure_ascii=False)
        + "\n"
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
) -> str:
    """D 段：程序推导的全局约束（配额 / 立面上限 / 材质白名单 / 通用规则）。"""

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


#: 工具型条目的检索指令（用户决策 2026-09-29，开放集构件通道配套）：
#: 预取 RAG 可能空手、类型可能没有专属注册配置——必须明确告诉模型
#: "不清楚就先调 search_knowledge，不要凭空编造字段"。
COMPONENT_KNOWLEDGE_HINT = (

    "\n\n# 知识检索工具（本条目可用）\n"
    "- 你可以调用 search_knowledge(query, kind) 检索构件知识库，本条目最多 2 次；\n"
    "  kind 传构件类型（如 \"column\"），query 用一句话描述你要查的契约点。\n"
    "- 当你不确定该构件的字段契约、坐标语义、必填参数或能力边界时，"
    "**必须先检索再输出**，不要凭空编造字段名或坐标语义。\n"
    "- 检索结果与你的记忆冲突时，以知识库为准；检索后仍不确定，"
    "就输出保守、合法的最小实现，并在 JSON 之外用一句话说明不确定点。\n"
    "-  **放弃是最后手段**（用户规则 2026-09-29）：只有当你 ① 对照本提示词里的"
    "蓝图语言规则（字段表、槽位规则、坐标语义）确认没有该构件/字段的契约，"
    "**且** ② 调 search_knowledge 检索知识库也查不到它的描述时，才允许放弃——"
    "此时必须在 JSON 之外用一句话写明放弃原因与两条核查的结论，"
    "**不许静默跳过**，更不许凭印象认定\"做不到\"。"
)
