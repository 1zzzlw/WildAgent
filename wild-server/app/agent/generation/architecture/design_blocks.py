"""设计块表：图纸分块的**常量依赖表**。

为什么要有这张表：让模型一次吐全图，它要在同一个上下文里同时维持
体量、立面、构件、材质四层的一致性——越往后越容易和前文冲突。先明确整体设计意图，再分块表达；局部修订以当前完整设计为基准，沿依赖核对。

**依赖表是常量，不由模型产出**："先体量后立面"是物理约束，不是设计决策；
让模型产出它只是白烧一次调用（`design_convergence` 与首次成图共用这张表）。

本模块**只描述"有哪些块、谁依赖谁、每块写哪些字段"**，不含任何 IO、不调模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from app.agent.knowledge.policy import plan_knowledge_query

#: 档位名闭集，与 ``plan.expand.DETAIL_BUDGET`` 的语义保持一致（单调递增）。
_DETAIL_LEVELS = ("minimal", "simple", "standard", "detailed")


@dataclass(frozen=True)
class KnowledgeQuerySpec:
    """一个块级知识检索意图（"RAG 换位置"的设计期落点）。

    每条意图 = "带过滤的 SpecQuery"。执行器（``design_workflow``）在起草本块
    **之前**逐条检索，把命中分片注入**本块的提示词**——而不是像旧行为那样
    整轮共用一份静态 ``spec_text``。检索失败不阻断（返回空文本）。
    """

    #: 检索查询文本。``{request}`` 占位符会被替换为用户请求原文；
    #: 其余文本是稳定措辞，保证同一块每轮检索可复现。
    text: str
    #: Chroma metadata 过滤（``doc_type`` / ``knowledge_role`` / ``entity_type``）。
    #: 检索必须带过滤（与 ``knowledge_tool.py`` 同一安全要求）：
    #: 给模型一个能查全库的口子，"它没查到"和"知识里真没有"就永远分不清。
    metadata_filter: dict[str, str]


@dataclass(frozen=True)
class DesignBlock:
    """一个设计块。"""

    name: str
    #: 该块负责写进图纸的顶层字段。**块与字段是多对一/一对多都允许**，
    #: 但同一个字段只能属于一个块——否则两处都会写它，必然分叉。
    fields: tuple[str, ...]
    #: 必须先定稿的块。这些块落定后，本块才能"只引用、不编造"。
    depends_on: tuple[str, ...]
    #: 同组内的块互不依赖，可并发。``None`` = 必须串行。
    parallel_group: str | None
    #: 该块的字段契约（直接拼进提示词）。写"什么是合法的"，不写造型偏好。
    #: 契约里可以留 ``{...}`` 占位符（如 ``{material_roles}``），由
    #: `design_workflow.render_block_contract` 在拼提示词时用**唯一来源**填上——
    #: 这样"词表"不必在本表里再抄一份（抄两份迟早一处改了另一处没改）。
    contract: str
    #: 本块专属的知识检索意图。空元组 = 这一块不注入检索文本（只吃基础提示词）。
    knowledge_queries: tuple[KnowledgeQuerySpec, ...] = ()


def block_knowledge_query_specs(
    block: DesignBlock, user_request: str, design_context: dict | None = None,
) -> list[KnowledgeQuerySpec]:
    """按本轮表达任务与当前设计生成受控查询，不从建筑用途补造型关键词。"""
    request = plan_knowledge_query(user_request, design_context)
    queries = [KnowledgeQuerySpec(spec.text.replace("{request}", request), dict(spec.metadata_filter))
               for spec in block.knowledge_queries]
    if block.name == "components":
        context = design_context or {}
        systems = list((context.get("design_intent") or {}).get("selected_systems", []))
        systems.extend(item.get("type") for item in context.get("components", []) if isinstance(item, dict))
        for system in list(dict.fromkeys(s for s in systems if s))[:3]:
            queries.append(KnowledgeQuerySpec(
                f"{system} 当前设计字段 宿主 形态 可选参数",
                {"doc_type": "component", "knowledge_role": "capability"},
            ))
    return queries


# 先形成整体设计，再分别表达；字段归属唯一，局部修订沿依赖联动。
DESIGN_BLOCKS: tuple[DesignBlock, ...] = (
    DesignBlock(
        name="intent",
        fields=("concept", "design_intent"),
        depends_on=(),
        parallel_group=None,
        contract=(
            "- concept：简短方案名称，体现本次设计主张。\n"
            "- design_intent：整体设计对象，包含 goals（设计目标字符串数组）、"
            "assumptions（未由用户给出的假设数组）、spatial_strategy（用途、到达、交通与内外关系）、"
            "composition（体量、立面与屋面怎样共同组织）、material_strategy（主辅材与构造层次）、"
            "selected_systems（准备采用的系统或构件名称数组）。\n"
            "系统名称优先使用当前设计表达参考中的名称，以便后续按选择检索；"
            "选择仍可在表达能力核对后调整，不能把选择写成已落地。\n"
            "从本次需求形成一致的设计方向，不先套一组尺寸或构件。"
            "未指定场地和朝向时标为假设；空间关系是方案意图，当前不生成房间坐标或室内平面图。"
        ),
        knowledge_queries=(KnowledgeQuerySpec(
            "建筑方案当前可表达的体量 立面 屋面 交通与实例关系",
            {"doc_type": "component", "entity_name": "architecture_design_expression"},
        ),),
    ),
    DesignBlock(
        name="massing",
        fields=("massing", "volumes", "design_constraints"),
        depends_on=("intent",),
        parallel_group=None,
        contract=(
            "- massing：shape 可选 {shape_enum}；{shape_volume_members} 有确定性体量派生，"
            "其它形态需要 volumes 具体表达。width/depth 为总体尺寸控制上限（米），"
            "floor_height 为正数，floors/modeled_floors 为正整数，modeled_floors 不大于 floors；"
            "representation_mode 为 full/schematic，symmetry 为布尔值。\n"
            "- volumes：数组，每项给 id、role(primary/secondary)、x、z、width、depth、"
            "start_floor、end_floor。x/z 是世界平面起点，不是中心，可负值或整体平移；"
            "体量并集跨度不超过总体控制值，逐层覆盖实际轮廓。单体同样声明完整体量。\n"
            "- massing.tiers 可按需要表达逐段收放，每段给 floors、width_ratio、depth_ratio，"
            "各段层数之和等于总层数；不需要收放时不添加。\n"
            "- complexity 由程序管理，不作为设计造型任务。\n"
            "- design_constraints：保留用户明确条件和需要逐项核对的设计选择。每条给 id、"
            "kind(user_hard/preference)、target(/decisions/...路径)、expression、source、expected、"
            "check(equals/contains/minimum/absent/manual)、adoption、source_quote。"
            "user_hard 的引用必须来自用户原文；自行选择的尺寸属于 architecture_draft。"
            "equals 比较同类型值，不能拿体量数组与体量数量比较；列表成员用 contains，"
            "无法表达的计数或审美目标用 manual。用户明确修订时用新 id 和 supersedes，保留来源。"
        ),
        knowledge_queries=(KnowledgeQuerySpec(
            "{request} 当前设计体量起点 包络 逐层轮廓 多体量屋面表达边界",
            {"doc_type": "component", "entity_name": "massing_composition_rules"},
        ),),
    ),
    DesignBlock(
        name="structure",
        fields=("structural_grid", "circulation"),
        depends_on=("massing",),
        parallel_group="shell",
        contract=(
            "- structural_grid：system 为 wall_bearing/frame/hybrid/long_span/shell，"
            "x_bays/z_bays 为正整数。按整体空间与体量关系选择，不用柱梁数量代替设计。\n"
            "- circulation：vertical_strategy 为 none/stair/core_and_stair；多层选择可落实的交通。"
            "贯通竖向构件需要位于其跨越各层的共同轮廓内。"
        ),
        knowledge_queries=(KnowledgeQuerySpec(
            "{request} 设计交通与贯通构件 逐层体量宿主 楼层标高",
            {"doc_type": "component", "entity_name": "architecture_design_expression"},
        ),),
    ),
    DesignBlock(
        name="facade",
        fields=("facades",),
        depends_on=("massing",),
        parallel_group="shell",
        contract=(
            "- facades：front/back/left/right 各给 bays、ground_pattern、upper_pattern；"
            "数组长度等于 bays。front/back 是最小/最大 Z，left/right 是最小/最大 X。\n"
            "- pattern 用 door/window/empty/open，可给 door:swing/slide/lift 或 "
            "window:swing/slide/fixed；empty 为实墙无洞，open 为开敞无墙，仅支持整面 open。\n"
            "- entrance_bay 如有入口则给 1 开始的开间序号；门放在 ground_pattern，"
            "当前 upper_pattern 不支持门。ground 在首层执行，upper 在各建模上层重复。"
            "需要逐层不同立面或上层交通门时保留表达限制，不宣称已经设计出来。\n"
            "- 开口由整体入口、采光与实虚关系组织。不要四面机械复用同一种排列；"
            "对称或重复可以采用，但应服务于本次设计。"
        ),
        knowledge_queries=(KnowledgeQuerySpec(
            "{request} 立面设计 开口节奏 实墙 开敞面 上层表达限制",
            {"doc_type": "component", "entity_name": "architecture_design_expression"},
        ),),
    ),
    DesignBlock(
        name="roof",
        fields=("roof",),
        depends_on=("massing",),
        parallel_group="shell",
        contract=(
            "- roof 是对象：type 为 flat/gable/hip/dome/chinese_curved/chinese_pagoda，"
            "ridge_axis 为 x/z（仅控制 gable 屋脊），overhang 为 0—2 米。"
            "不写元素级 id/span/depth/position。\n"
            "- 可选 volumes 数组，每项给 volume（已有体量 id）、type、overhang；"
            "未列出的体量继承整体模板。当前多体量分段仅支持 flat/gable/hip；"
            "上层部分覆盖下层的剩余局部屋面尚未支持，不承诺自动生成完整露台。\n"
            "- 屋面与已选整体构图协调，不因为检索出现某种屋顶就更换设计方向。"
        ),
        knowledge_queries=(KnowledgeQuerySpec(
            "{request} 已选屋面 屋脊方向 出檐 逐体量覆盖与附属件",
            {"doc_type": "component", "entity_name": "architecture_design_expression"},
        ),),
    ),
    DesignBlock(
        name="components",
        fields=("component_quota", "components", "materials", "design_rationale"),
        depends_on=("structure", "facade", "roof"),
        parallel_group=None,
        contract=(
            "- component_quota：按实际选用类型给 min/max/note；门窗数量从立面确定性派生。"
            "附属件来自设计需要，不作为完成设计的固定套餐。\n"
            "- components 可选实例数组，每项给 type、host、size、form、material_role，"
            "可给稳定 id。material_role 从 {material_roles} 选择；form 必须是对象，键为真实引擎字段，不能写形态名字符串。\n"
            "墙挂构件 host 用 <volume_id>_<front/back/left/right>_<楼层>；"
            "cornice/chimney 的屋面宿主用体量 id 或 <volume_id>_L<顶层>_roof，"
            "当前设计编译器只为 flat/gable/hip 派生这两类附属件。"
            "cornice.form.profile 是至少三个二维数字点，不是预设名。\n"
            "柱可用 relation={kind:supports,target:目标实例id,along_ratio:0到1,depth_ratio:0到1}"
            "表达雨棚支撑；柱底及位置由目标宿主解算，size.height 与材料由设计声明。"
            "其它实例核对真实宿主；门窗 size 不覆盖已定槽位。\n"
            "- materials 可选，regions 每项为 role（{material_roles}）、type（目标实体类型）。"
            "材料方向由 design_intent 给出，具体材质参数交后续材质节点落实。\n"
            "- design_rationale：简短结论数组，核对实际参数如何实现整体意图，"
            "说明入口、体量、开口、屋面与材料之间的联系；未表达的内容明确写为限制，"
            "不得用重复 design_intent 文案替代核对，不输出内部思考过程。"
        ),
        knowledge_queries=(KnowledgeQuerySpec(
            "{request} 已选附属件 设计实例宿主 屋面附着 材料角色表达限制",
            {"doc_type": "component", "entity_name": "architecture_design_expression"},
        ), KnowledgeQuerySpec(
            "当前设计实例的宿主连接 屋面附件 雨棚支撑 材料绑定",
            {"doc_type": "recipe", "entity_name": "supported_assembly_relations"},
        )),
    ),
)

BLOCK_BY_NAME: dict[str, DesignBlock] = {block.name: block for block in DESIGN_BLOCKS}

#: 档位 → 用哪几块。``minimal`` 只要体量与立面；``simple`` 不要求结构轴网；
#: ``standard``/``detailed`` 全用（``detailed`` 的"细节"由 complexity 的
#: ``min_detail_packages`` 表达，**不是**额外的一个块——表里没有"细节块"这个成员）。
_BLOCKS_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "minimal": ("intent", "massing", "facade"),
    "simple": ("intent", "massing", "facade", "roof", "components"),
    "standard": tuple(block.name for block in DESIGN_BLOCKS),
    "detailed": tuple(block.name for block in DESIGN_BLOCKS),
}


def blocks_for_level(level: str) -> tuple[str, ...]:
    """该档位要写哪几块。认不出的档位按 ``standard`` 处理（**宁可多写不可少写**：

    少写一块会让下游归一化去兜底填默认值，而默认值是"没人表态"的结果——
    这正是 `defaulted` 报出来的东西，不该由档位解析的容错来制造）。
    """

    return _BLOCKS_BY_LEVEL.get(str(level or "").strip().lower(), _BLOCKS_BY_LEVEL["standard"])


def ordered_blocks(level: str) -> tuple[DesignBlock, ...]:
    """按依赖做拓扑序；同 ``parallel_group`` 的表序相邻，便于外部并发执行。

    本函数只保证"依赖在前"，**不替调用方决定并发**——并发与否是执行器的事。
    """

    selected = set(blocks_for_level(level))
    ordered: list[DesignBlock] = []
    emitted: set[str] = set()
    remaining = [block for block in DESIGN_BLOCKS if block.name in selected]
    while remaining:
        progressed = False
        for block in list(remaining):
            if all(dep in emitted or dep not in selected for dep in block.depends_on):
                ordered.append(block)
                emitted.add(block.name)
                remaining.remove(block)
                progressed = True
        if not progressed:  # 表里有环 —— 表是常量，这属于写错了，直接暴露
            names = [block.name for block in remaining]
            raise ValueError(f"设计块表存在循环依赖: {names}")
    return tuple(ordered)


def block_of_field(field: str) -> DesignBlock | None:
    """字段 → 它属于哪个块。`design_convergence` 靠它把缺陷映射回"该重出哪一块"。"""

    for block in DESIGN_BLOCKS:
        if field in block.fields:
            return block
    return None


#: ``compile_design`` 的 ``design_field`` 串 → 该重出哪一块。
#:
#: 采用**前缀**匹配而不是精确匹配：``compile.py`` 产出的是
#: ``decisions.facades.front.ground_pattern`` 这种带下标的路径，
#: 精确匹配会把它们全判成"认不出"。
_DESIGN_FIELD_ROOTS: tuple[tuple[str, str], ...] = (
    ("decisions.design_intent", "intent"),
    ("decisions.concept", "intent"),
    ("decisions.design_rationale", "components"),
    ("decisions.massing", "massing"),
    ("decisions.volumes", "massing"),
    ("decisions.facades", "facade"),
    ("decisions.roof", "roof"),
    ("decisions.structural_grid", "structure"),
    ("decisions.circulation", "structure"),
    ("decisions.component_quota", "components"),
    ("decisions.components", "components"),
    ("decisions.materials", "components"),
)

#: 允许出现在 ``decisions.<root>`` 之后的定界符。只认这三种，是为了**不误配前缀**：
#: ``decisions.roofing`` 不该被当成 ``decisions.roof``（多一个字母就是另一件事）。
_DESIGN_FIELD_DELIMITERS = (".", "[", "<")


def block_of_design_field(design_field: str) -> DesignBlock | None:
    """``design_field`` 串 → 该重出哪一块。**认不出返回 ``None``，不猜。**

     猜错会让收敛环跑去改**另一个块**——那比不定位更糟：同一参数被两处改就会分叉
    （`MEMORY.md` 里"同一参数被两处夹取就分叉"那条）。认不出时调用方应当停下来如实记账，
    而不是"随便挑一块重出"。
    """

    field = str(design_field or "").strip()
    if not field:
        return None
    for root, name in _DESIGN_FIELD_ROOTS:
        if field == root:
            return BLOCK_BY_NAME.get(name)
        if field.startswith(root) and field[len(root) : len(root) + 1] in _DESIGN_FIELD_DELIMITERS:
            return BLOCK_BY_NAME.get(name)
    # 兼容裸字段名（``facades`` / ``massing``）——手工构造缺陷时会用到。
    return block_of_field(field)
