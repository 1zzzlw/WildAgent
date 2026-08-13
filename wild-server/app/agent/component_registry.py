"""
组件注册表 —— 所有组件类型的元数据中心

基于 wild-compiler/componentRegistry.ts 的已注册组件。
新增组件只需在此添加一行配置。
所有 11 种组件均已实现（Phase 2 扩展完成）。
"""
from dataclasses import dataclass, field


@dataclass
class ComponentConfig:
    """单个组件类型的完整配置"""

    # ── 标识 ──
    component_type: str                    # "door", "window", ...
    label: str                             # 中文标签："门", "窗", ...

    # ── RAG 配置 ──
    entity_type: str                       # Chroma metadata filter: entity_type
    rag_extra_queries: list[str] = field(default_factory=list)

    # ── 输出配置 ──
    output_key: str = ""                   # state 字段名，如 "door_fragments"
    is_list: bool = True                   # True=输出数组，False=输出单个对象
    is_element: bool = False               # True=写入 elements（如 roof）

    # ── 校验配置 ──
    required_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)

    # ── 触发配置 ──
    skip_keywords: list[str] = field(default_factory=list)
    need_keywords: list[str] = field(default_factory=list)

    # ── Prompt 增强 ──
    extra_rules: str = ""
    output_format_hint: str = ""

    # ── 依赖与优先级 ──
    priority: int = 5
    dependencies: list[str] = field(default_factory=list)

    # ── 状态 ──
    implemented: bool = True


# ── 每个组件的专属规则（来自设计文档 02-节点详细设计.md 3.2 节）──

_COMPONENT_RULES: dict[str, str] = {
    "door": (
        "- from[0] 是沿墙距离（单位米），范围: 0 ≤ from[0] ≤ 墙长-门宽\n"
        "- from[1] 是底部世界 Y 坐标（通常为 0）\n"
        "- from[2] 是法向偏移（通常为 0）\n"
        '- interaction 必填: {"mode":"swing","hingeSide":"left"|"right","openAngle":90}\n'
        "- 主入口门宽 0.9~1.2m、门高 2.1~2.4m；不得为了塞进单个立面开间而缩到 0.9m 以下\n"
        "- 用户未指定外观参数时，在上述范围内选择克制的小幅变化；避免所有建筑机械复用完全相同的门参数\n"
        "- 优先让 frameMaterial 与 leafMaterial 形成可读层次（如金属框+木门扇），但不得虚构 materials 中不存在的名称\n"
        "- frameDepth 默认等于父墙 thickness；leafDepth 默认 min(0.04, frameDepth)，通常不必显式填写\n"
        "- 自定义 leafDepth 必须为正数且不大于 frameDepth，门框和门扇必须与父墙厚度范围相交\n"
        "- 编译后产出: opening + primitive.box×3（门框）\n"
        "\n**数量与位置约束（必须遵守）**：\n"
        "- 一栋建筑通常只有 1~2 个门：1 个正门（放在正面墙 wall_front 居中），可选 1 个后门/侧门\n"
        "- 绝对不要每面墙都放门！内墙不要放门\n"
        "- 正门放在正面墙（通常是 wall_front 或最长的面朝道路的墙）的居中位置\n"
        "- 如果建筑有明确的「入口」、「主入口」语义，只生成 1 个门\n"
    ),
    "window": (
        "- from[0] 是沿墙距离；from[1] 是底部世界 Y（父墙底 Y + 通常 0.8~1.0m 的窗台高度）\n"
        "- verticalMullions 范围 0~32，horizontalMullions 范围 0~32\n"
        "- width 建议 0.8~2.0m，height 建议 1.0~2.0m\n"
        "- frameMaterial 和 glassMaterial 必须引用骨架 materials 中已有的材质名\n"
        "- frameDepth 默认等于父墙 thickness；glassDepth 默认 min(0.012, frameDepth)，通常不必显式填写\n"
        "- 自定义 glassDepth 必须为正数且不大于 frameDepth，窗框和玻璃必须与父墙厚度范围相交\n"
        "- glassMaterial 指向的材质必须含 opacity（0.3~0.5 半透明模拟玻璃），否则窗户不透明\n"
        "- 如果骨架 materials 没有半透明玻璃材质，在组件 JSON 外附加提醒（不输出到 JSON）\n"
        "- 编译后产出: opening + primitive.box×N（窗框+窗棂）\n"
        "\n**数量与位置约束（必须遵守）**：\n"
        "- 每面墙最多 2~3 个窗，根据墙长合理分布（墙长 <4m 放 1 个，4~8m 放 2 个，>8m 放 3 个）\n"
        "- 窗户沿墙均匀分布，间距 ≥1.0m，边缘距墙角 ≥0.5m\n"
        "- 正面墙（wall_front）可以多放窗以增加采光，背面/侧面适当减少\n"
        "- 不要在有门的墙上放太多窗（门+窗总数 ≤ 墙长/1.8）\n"
    ),
    "roof": (
        "- roof 是 geometry.elements 原生类型，不是 components\n"
        "- roofType 支持 6 个值: gable/hip/flat/dome/chinese_curved/chinese_pagoda\n"
        "- span 和 depth 应覆盖整个建筑的包围盒\n"
        "- position 是屋顶中心世界坐标"
    ),
    "railing": (
        "- path 至少 2 个点，定义栏杆走向\n"
        "- 可指定 parentFloor 关联到楼板\n"
        "- 编译后产出: primitive.cylinder×N + beam×M\n"
        "- 栏杆高度通常 0.9~1.1m\n"
        "\n**位置约束（必须遵守）**：\n"
        "- 栏杆只放在有高差的地方：阳台边缘、楼梯两侧、露台边缘、二层平台\n"
        "- 如果同轮还会生成 balcony，禁止再为该阳台生成独立 railing；balcony 已内嵌 U 形栏杆\n"
        "- 绝对不要在地面层的外墙位置放栏杆！地面层外墙本身就是围护结构\n"
        "- 如果没有阳台/楼梯/露台等构件，不要生成栏杆\n"
        "- path 坐标必须在对应楼板范围内，不能飘在空中\n"
    ),
    "canopy": (
        "- parentWall 必须存在\n"
        "- depth 和 thickness 必填\n"
        "- 编译后产出: primitive.box（板）+ primitive.cylinder×4（支柱）"
    ),
    "balcony": (
        "- slabThickness 必填\n"
        "- from[1] 是阳台板世界标高，必须 ≥1.8m 并落在父墙竖向范围内；严禁在 Y=0 地面层生成阳台\n"
        "- 优先挂接二层及以上外墙；若建筑没有上层或真实高差，不要生成 balcony\n"
        "- from[2] 通常为 0；depth 表示向建筑外侧的悬挑深度，方向由编译器根据建筑中心确定\n"
        "- balcony 已内嵌悬挑板和 U 形栏杆，禁止同时生成同位置 floor 或独立 railing\n"
        "- 内部自动调用 railing 编译器 → 依赖 railing 先实现\n"
        "- 编译后产出: floor（悬挑板）+ railing（内嵌）"
    ),
    "ramp": (
        "- from/to 必须有高度差\n"
        "- width 和 thickness 必填\n"
        "- 编译后产出: primitive.profile_sweep（坡面）+ 可选 railing"
    ),
    "bay_window": (
        "- projectionDepth 必填\n"
        "- parentWall 必须存在\n"
        "- 凸窗是实际墙洞，必须占用并替换一个普通窗位；严禁与 door、window 或其他 bay_window 重叠\n"
        "- glassMaterial 必须引用 materials 中的 `\"glass\"`（opacity 0.35）\n"
        "- 编译后产出: opening + primitive.box×N（投影+窗框）"
    ),
    "cornice": (
        "- path 至少 2 个点\n"
        "- profile 必填（截面点数组）\n"
        "- 编译后产出: primitive.profile_sweep（飞檐轮廓）"
    ),
    "chimney": (
        "- position、width、depth、height 必填\n"
        "- 编译后产出: primitive.box×4（薄壁筒体）+ primitive.box（压顶），不对屋顶做布尔穿透"
    ),
    "light": (
        "- initiallyOn 必填\n"
        "- 附带 behaviors.interactive（可交互行为）\n"
        "- 编译后产出: primitive.sphere（灯泡）+ primitive.cylinder（灯座）+ behavior"
    ),
}


# ── 注册表：全部组件（均已实现）──

COMPONENT_REGISTRY: dict[str, ComponentConfig] = {
    # ── P0: 建筑三要素 ──
    "door": ComponentConfig(
        component_type="door",
        label="门",
        entity_type="door",
        rag_extra_queries=["door interaction opening"],
        output_key="door_fragments",
        is_list=True,
        required_fields=["type", "id", "parentWall", "from", "width", "height", "interaction"],
        optional_fields=[
            "frameWidth", "frameDepth", "leafDepth", "frameMaterial", "leafMaterial",
            "openingStyle", "doorStyle",
        ],
        skip_keywords=["不要门", "没有门", "无门", "不需要门"],
        extra_rules=_COMPONENT_RULES["door"],
        priority=0,
    ),
    "window": ComponentConfig(
        component_type="window",
        label="窗",
        entity_type="window",
        rag_extra_queries=["window lighting ventilation"],
        output_key="window_fragments",
        is_list=True,
        required_fields=["type", "id", "parentWall", "from", "width", "height"],
        optional_fields=[
            "frameWidth", "frameDepth", "glassDepth", "verticalMullions",
            "horizontalMullions", "frameMaterial", "glassMaterial",
        ],
        skip_keywords=["不要窗", "没有窗", "无窗", "不需要窗"],
        extra_rules=_COMPONENT_RULES["window"],
        priority=0,
    ),
    "roof": ComponentConfig(
        component_type="roof",
        label="屋顶",
        entity_type="roof",
        rag_extra_queries=["roof coverage gable hip"],
        output_key="roof_fragment",
        is_list=False,
        is_element=True,
        required_fields=["type", "id", "roofType", "span", "depth", "height", "thickness"],
        optional_fields=["material", "position"],
        skip_keywords=["不要屋顶", "没有屋顶", "无屋顶", "不需要屋顶"],
        extra_rules=_COMPONENT_RULES["roof"],
        priority=0,
    ),
    # ── P1: 常见附属（被 balcony 依赖）──
    "railing": ComponentConfig(
        component_type="railing",
        label="栏杆",
        entity_type="railing",
        rag_extra_queries=["railing balcony stair path"],
        output_key="railing_fragments",
        is_list=True,
        required_fields=["type", "id", "path", "height"],
        optional_fields=["parentFloor", "postSpacing"],
        skip_keywords=["不要栏杆", "没有栏杆", "无栏杆", "不需要栏杆"],
        need_keywords=["栏杆", "护栏", "扶手", "阳台", "楼梯"],
        extra_rules=_COMPONENT_RULES["railing"],
        priority=1,
    ),
    # ── P2: 装饰型 ──
    "canopy": ComponentConfig(
        component_type="canopy",
        label="雨棚",
        entity_type="canopy",
        rag_extra_queries=["canopy awning entrance"],
        output_key="canopy_fragments",
        is_list=True,
        required_fields=["type", "id", "parentWall", "from", "width", "depth", "thickness"],
        skip_keywords=["不要雨棚", "没有雨棚", "不需要雨棚"],
        need_keywords=["雨棚", "雨篷", "遮阳", "入口遮"],
        extra_rules=_COMPONENT_RULES["canopy"],
        priority=2,
    ),
    "balcony": ComponentConfig(
        component_type="balcony",
        label="阳台",
        entity_type="balcony",
        rag_extra_queries=["balcony slab railing"],
        output_key="balcony_fragments",
        is_list=True,
        required_fields=["type", "id", "parentWall", "from", "width", "depth", "slabThickness"],
        skip_keywords=["不要阳台", "没有阳台", "不需要阳台"],
        need_keywords=["阳台", "露台", "挑台"],
        extra_rules=_COMPONENT_RULES["balcony"],
        priority=2,
        dependencies=["railing"],
    ),
    # ── P3: 交互型 ──
    "light": ComponentConfig(
        component_type="light",
        label="灯具",
        entity_type="light",
        rag_extra_queries=["light behavior interactive"],
        output_key="light_fragments",
        is_list=True,
        required_fields=["type", "id", "position"],
        optional_fields=["fixtureType", "lightType", "color", "lowIntensity", "highIntensity", "distance", "angle", "initiallyOn"],
        skip_keywords=["不要灯", "没有灯", "不需要灯"],
        need_keywords=["灯", "照明", "光源", "吊灯", "壁灯", "台灯", "灯具",
                       "家具", "装修", "装饰", "室内", "温馨", "明亮"],
        extra_rules=_COMPONENT_RULES["light"],
        priority=3,
    ),
    # ── P4: 特殊场景 ──
    "ramp": ComponentConfig(
        component_type="ramp",
        label="坡道",
        entity_type="ramp",
        rag_extra_queries=["ramp slope accessibility"],
        output_key="ramp_fragments",
        is_list=True,
        required_fields=["type", "id", "from", "to", "width", "thickness"],
        skip_keywords=["不要坡道", "没有坡道", "不需要坡道"],
        need_keywords=["坡道", "斜坡", "无障碍", "车道"],
        extra_rules=_COMPONENT_RULES["ramp"],
        priority=4,
        dependencies=["railing"],
    ),
    "bay_window": ComponentConfig(
        component_type="bay_window",
        label="凸窗",
        entity_type="bay_window",
        rag_extra_queries=["bay window projection"],
        output_key="bay_window_fragments",
        is_list=True,
        required_fields=["type", "id", "parentWall", "from", "width", "height", "projectionDepth"],
        skip_keywords=["不要凸窗", "没有凸窗", "不需要凸窗"],
        need_keywords=["凸窗", "飘窗", "bay window"],
        extra_rules=_COMPONENT_RULES["bay_window"],
        priority=4,
    ),
    # ── P5: 中式建筑特有 ──
    "cornice": ComponentConfig(
        component_type="cornice",
        label="檐口",
        entity_type="cornice",
        rag_extra_queries=["cornice eave traditional"],
        output_key="cornice_fragments",
        is_list=True,
        required_fields=["type", "id", "path", "profile"],
        skip_keywords=["不要檐口", "没有檐口", "不需要檐口"],
        need_keywords=["檐口", "飞檐", "挑檐"],
        extra_rules=_COMPONENT_RULES["cornice"],
        priority=5,
    ),
    "chimney": ComponentConfig(
        component_type="chimney",
        label="烟囱",
        entity_type="chimney",
        rag_extra_queries=["chimney flue"],
        output_key="chimney_fragments",
        is_list=True,
        required_fields=["type", "id", "position", "width", "depth", "height"],
        skip_keywords=["不要烟囱", "没有烟囱", "不需要烟囱"],
        need_keywords=["烟囱", "壁炉", "排烟"],
        extra_rules=_COMPONENT_RULES["chimney"],
        priority=5,
    ),
}


def get_implemented_components() -> list[ComponentConfig]:
    """获取所有已实现的组件配置"""
    return [c for c in COMPONENT_REGISTRY.values() if c.implemented]


def get_component_config(component_type: str) -> ComponentConfig | None:
    """获取指定类型的组件配置"""
    return COMPONENT_REGISTRY.get(component_type)


def resolve_component_suggestions(
    suggested: list[str],
    user_message: str,
    component_quota: dict | None = None,
) -> list[str]:
    """把模型建议归一化为可安全派发的组件列表。

    - 丢弃未注册或未实现的类型，避免 ``Send`` 派发到不存在的节点。
    - 尊重每个组件的否定关键词。
    - 设计清单中 ``min > 0`` 的组件必须进入派发，避免批准配额无人生成。
    - 当骨架没有给出建议时，保留门、窗、屋顶三个基础组件，并按关键词补充。
    - 阳台编译器已经内嵌栏杆；用户没有单独要求栏杆时避免重复生成。
    """
    requested = [item for item in suggested if isinstance(item, str)]
    for component_type, limits in (component_quota or {}).items():
        minimum = limits.get("min", 0) if isinstance(limits, dict) else 0
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and minimum > 0
            and component_type not in requested
        ):
            requested.append(component_type)
    if not requested:
        requested = ["door", "window", "roof"]
        requested.extend(
            config.component_type
            for config in get_implemented_components()
            if any(keyword in user_message for keyword in config.need_keywords)
        )

    resolved: list[str] = []
    for component_type in requested:
        config = COMPONENT_REGISTRY.get(component_type)
        if config is None or not config.implemented:
            continue
        if any(keyword in user_message for keyword in config.skip_keywords):
            continue
        if component_type not in resolved:
            resolved.append(component_type)

    # “阳台/楼梯”会触发栏杆的自动建议，但不代表用户要求再生成一个独立栏杆。
    # balcony 编译器已有内嵌栏杆，只有明确提到栏杆语义时才保留两者。
    railing_explicitly_requested = any(
        keyword in user_message for keyword in ("栏杆", "护栏", "扶手")
    )
    if "balcony" in resolved and "railing" in resolved and not railing_explicitly_requested:
        resolved.remove("railing")

    return resolved
