"""设计块表：图纸分块的**常量依赖表**。

为什么要有这张表：让模型一次吐全图，它要在同一个上下文里同时维持
体量、立面、构件、材质四层的一致性——越往后越容易和前文冲突。**分块写、逐块落定、
后块只引用前块**，是唯一可行的解法。

**依赖表是常量，不由模型产出**："先体量后立面"是物理约束，不是设计决策；
让模型产出它只是白烧一次调用（`design_convergence` 与首次成图共用这张表）。

本模块**只描述"有哪些块、谁依赖谁、每块写哪些字段"**，不含任何 IO、不调模型。
"""

from __future__ import annotations

from dataclasses import dataclass

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
    contract: str
    #: 本块专属的知识检索意图。空元组 = 这一块不注入检索文本（只吃基础提示词）。
    knowledge_queries: tuple[KnowledgeQuerySpec, ...] = ()


# 设计块表。顺序即表序；同组按表序，便于诊断复现。
DESIGN_BLOCKS: tuple[DesignBlock, ...] = (
    DesignBlock(
        name="massing",
        fields=("concept", "massing", "volumes", "design_constraints"),
        depends_on=(),
        parallel_group=None,
        contract=(
            "- concept：从**用户需求原文**提炼的方案名（如「四角亭子」「临水茶室」），"
            "不超过 16 字。这是蓝图文件名与图纸标题；不要写风格档位词、"
            "不要写「比例清晰」这类空话，也不要复读整个请求句子。\n"
            "- massing：shape 用 profile 允许值；width/depth/floor_height 为正数；"
            "floors/modeled_floors 为正整数；representation_mode 为 full 或 schematic；"
            "symmetry 为布尔值。\n"
            "- 塔形/退台轮廓用 massing.tiers 表态：从底到顶逐段给 floors、width_ratio、depth_ratio"
            "（比例相对 massing.width/depth，0~1）；各段 floors 之和必须等于 massing.floors。\n"
            "  电视塔、宝塔、阶梯收分的高层**务必**用它表达轮廓收放，不要把整栋楼画成一个矩形体量。\n"
            "- volumes：体量数组，每项含 id、role(primary/secondary)、x、z、width、depth、"
            "start_floor、end_floor。单体也要明确一个完整体量；多层单体不必拆成退台。\n"
            "- 体量之间**不得重叠**，同层投影必须覆盖建筑轮廓（这是硬约束，不是审美）。\n"
            "- complexity 由系统按档位给出，**本块不要写 complexity**。\n"
            "- design_constraints：列出用户明确要求以及本方案采用的关键决定，不能只留在文案中。"
            "每条含 id(稳定标识)、kind(user_hard 或 preference)、target(/decisions/... JSON Pointer)、"
            "expression(简短目标)、source(user_request 或 architecture_draft)、source_quote(用户要求须逐字引用原文)、"
            "expected(目标值)、check(equals/contains/minimum/absent/manual)、adoption(adopted/proposed)。"
            "无法可靠映射的要求仍保留并用 manual，不得自行发明用户硬要求。"
            "列表成员用 contains/absent；屋顶类型指向 /decisions/roof/type；层数指向 /decisions/massing/floors。"
            "不支持的形态保留目标路径和说明，不可偷偷换成支持的形态。"
            "修订时继承已有要求，不能删掉或降低 expected 以消除缺口。用户明确改变要求时才用新 id、supersedes=旧 id，source_quote 引用本次修改原文。"
        ),
        knowledge_queries=(
            KnowledgeQuerySpec(
                "{request} 建筑形制特征 体块构成 组装配方 设计层表态",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
        ),
    ),
    DesignBlock(
        name="structure",
        fields=("structural_grid", "circulation"),
        depends_on=("massing",),
        parallel_group="shell",
        contract=(
            "- structural_grid：轴网开间/进深，必须与 massing 的 width/depth **自洽**"
            "（开间之和 = 对应方向的尺寸）。\n"
            "- circulation：竖向交通策略（如 stair 或 elevator），必须落在体量的公共投影区内。"
        ),
        knowledge_queries=(
            KnowledgeQuerySpec(
                "{request} 竖向交通 楼梯 电梯 楼梯井 开洞 结构",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
        ),
    ),
    DesignBlock(
        name="facade",
        fields=("facades",),
        depends_on=("massing",),
        parallel_group="shell",
        contract=(
            "- facades：front/back/left/right 每面给 bays、ground_pattern、upper_pattern。\n"
            "- 🔴 entrance_bay 与 door 槽位**只在用户要求入口/门、或形制确有门时才写**；"
            "形制 KB 命中开敞建筑（亭/廊/榭等）时四面 pattern 全 empty、"
            "不写 entrance_bay、任何面都不写 door——全空声明会被系统自动豁免主入口强制，"
            "**不要自行发明门（如月洞门）去\"满足\"入口要求**。\n"
            "- 槽位数量必须与 bays 一致；pattern 里每个 door/window 都会成为真实组件。\n"
            "- 每个槽位是一个**开口 token**：`door`／`window`／`empty`，"
            "或 `类型:形态` 显式指定形态（如 `door:slide`、`window:fixed`）。\n"
            "- 形态闭集：门 `swing`(平开)／`slide`(推拉)／`lift`(提升·卷帘)；"
            "窗 `swing`(平开)／`slide`(推拉)／`fixed`(固定)。"
            "**门不许写 fixed（门必须能开），窗不许写 lift**；写错会被忽略、退回纯类型。\n"
            "- 不写 `:` 时形态由系统派生（通常为平开）。**写了就按写的渲染**。\n"
            "- 🔴 某一层的 pattern **全为 empty = 该面在该层开敞无墙**（亭廊、骑楼、"
            "敞廊语义）。要保留实墙的面至少给一个开口槽位；开敞形制（亭/廊）"
            "把不要墙的面全写 empty，结构交给柱。\n"
            "- front 是最小 Z 的主立面，back 是最大 Z，left 是最小 X，right 是最大 X。"
        ),
        knowledge_queries=(
            KnowledgeQuerySpec(
                "{request} 立面 开口 门窗组合 形态 格扇 组装配方",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
            KnowledgeQuerySpec(
                "门窗与墙宿主 深度 frameDepth from 坐标 关系",
                {"doc_type": "recipe", "knowledge_role": "relation"},
            ),
        ),
    ),
    DesignBlock(
        name="roof",
        fields=("roof",),
        depends_on=("massing",),
        parallel_group="shell",
        contract=(
            "- roof：type 用当前六种 roofType 之一；ridge_axis 为 x 或 z；overhang 为非负数。\n"
            "- 多体量（L/U 形）必须按体量分别声明屋顶，**不得**用单块屋顶盖住内院/天井。"
        ),
        knowledge_queries=(
            KnowledgeQuerySpec(
                "{request} 屋顶形制 坡顶 攒尖 锥顶 叠涩檐 组装配方",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
        ),
    ),
    DesignBlock(
        name="components",
        fields=("component_quota", "components"),
        depends_on=("massing", "structure", "facade", "roof"),
        parallel_group=None,
        contract=(
            "- component_quota：按实际组件类型给 min/max 整数及 note。\n"
            "- **不要写 door / window / roof 的上下限**——这三类由系统按立面逐层 pattern 与屋顶\n"
            "  自动派生，你写了也会被覆盖。请把配额写在这三类**之外**真正会落地的构件上，\n"
            "  例如 railing / canopy / cornice / chimney / light / column。\n"
            "- 不给未选择的组件硬配额；能力做不到的类型不要写进来（写了会被归入 `uncompiled`）。"
            "\n- components：具体实例数组，可为空；不要为了通过检查添加装饰。"
            "每项使用 type、host、size、form、material_role，配额不代替实例设计。"
            "\n- 门窗 host 可用已定稿体量的 `<volume_id>_L<floor>_<front/back/left/right>`，"
            "同面第 n 个同类开口追加 `:n`；实际墙由编译器解析，不得猜未来墙 ID。"
            "\n- 门窗已有槽位时位置和主尺寸来自槽位，size 不覆盖槽位；"
            "form 可表达引擎已有的 frameWidth/frameDepth 等形态。"
            "其它构件须使用已提供的真实宿主，无法确定宿主时不编造实例。"
        ),
        knowledge_queries=(
            KnowledgeQuerySpec(
                "{request} 附属构件 配额 railing canopy cornice chimney light column 能力边界",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
            KnowledgeQuerySpec(
                "构件组装关系 宿主 引用 表面挂接",
                {"doc_type": "recipe", "knowledge_role": "relation"},
            ),
        ),
    ),
)

BLOCK_BY_NAME: dict[str, DesignBlock] = {block.name: block for block in DESIGN_BLOCKS}

#: 档位 → 用哪几块。``minimal`` 只要体量与立面；``simple`` 不要求结构轴网；
#: ``standard``/``detailed`` 全用（``detailed`` 的"细节"由 complexity 的
#: ``min_detail_packages`` 表达，**不是**额外的一个块——表里没有"细节块"这个成员）。
_BLOCKS_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "minimal": ("massing", "facade"),
    "simple": ("massing", "facade", "roof", "components"),
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
    ("decisions.massing", "massing"),
    ("decisions.volumes", "massing"),
    ("decisions.facades", "facade"),
    ("decisions.roof", "roof"),
    ("decisions.structural_grid", "structure"),
    ("decisions.circulation", "structure"),
    ("decisions.component_quota", "components"),
    ("decisions.components", "components"),
)

#: 允许出现在 ``decisions.<root>`` 之后的定界符。只认这三种，是为了**不误配前缀**：
#: ``decisions.roofing`` 不该被当成 ``decisions.roof``（多一个字母就是另一件事）。
_DESIGN_FIELD_DELIMITERS = (".", "[", "<")


def block_of_design_field(design_field: str) -> DesignBlock | None:
    """``design_field`` 串 → 该重出哪一块。**认不出返回 ``None``，不猜。**

    🔴 猜错会让收敛环跑去改**另一个块**——那比不定位更糟：同一参数被两处改就会分叉
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
