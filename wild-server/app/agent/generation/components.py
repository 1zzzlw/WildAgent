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


#: 预取知识达到该长度就认为"字段约束已经来自知识库"，不再注入代码里的静态规则
#: （《动态节点设计规划》§2.4：per-type 静态规则必须下沉进知识库）。
#: 代码规则从此是**兜底**：检索为空或命中的知识太薄时才补，并在诊断里如实记录来源。
KNOWLEDGE_SUFFICIENT_CHARS = 600


def component_rules_source(rag_chars: int) -> str:
    """决定本次生成的字段约束来自 kb 还是代码规则。纯函数，可单测。

    "knowledge"：知识库已提供约束（``extra_rules`` 不拼进提示词）；
    "fallback"：检索为空/太薄，用代码里的 ``_COMPONENT_RULES`` 兜底。
    """

    return "knowledge" if int(rag_chars or 0) >= KNOWLEDGE_SUFFICIENT_CHARS else "fallback"


# ── 每个组件的实现规则（**兜底用**）。数量、位置和造型由已批准设计及精确槽位决定。──
_COMPONENT_RULES: dict[str, str] = {
    "door": (
        "- from[0] 是沿墙距离（单位米），范围: 0 ≤ from[0] ≤ 墙长-门宽\n"
        "- from[1] 是底部世界 Y 坐标（通常为 0）\n"
        "- from[2] 是法向偏移（通常为 0）\n"
        '- interaction 必填；mode 三选一: "swing" 绕铰链侧平开（配 hingeSide/openAngle）、'
        '"slide" 沿墙面水平推拉（配 openDistance）、"lift" 整扇向上让开洞口'
        '（车库卷帘门；openDistance 可省略，缺省等于洞口高度而由引擎钳到门头净空，'
        '不必为了"别顶出墙"去写保守值）\n'
        "- leafRows 可选: 门扇横向分节行数 1~8，缺省 2~3；车库门帘片用 4~6，与 doorStyle 正交\n"
        "- width、height 必须为正数并完整落在父墙范围内；有精确槽位时逐字使用槽位尺寸\n"
        "- frameDepth 默认等于父墙 thickness；leafDepth 默认 min(0.04, frameDepth)，通常不必显式填写\n"
        "- 自定义 leafDepth 必须为正数且不大于 frameDepth，门框和门扇必须与父墙厚度范围相交\n"
        "- 数量、宿主墙和位置服从 DesignDocument 解析出的槽位与 component_quota，不自行补门\n"
        "- 编译后产出: opening + primitive.box×3（门框）\n"
    ),
    "window": (
        "- from[0] 是沿墙距离；from[1] 是窗底世界 Y；有精确槽位时逐字使用槽位坐标\n"
        "- verticalMullions 范围 0~32，horizontalMullions 范围 0~32\n"
        "- width、height 必须为正数，边缘留量和开口间距由父墙尺寸及已批准槽位决定\n"
        "- frameMaterial 和 glassMaterial 必须引用骨架 materials 中已有的材质名\n"
        "- frameDepth 默认等于父墙 thickness；glassDepth 默认 min(0.012, frameDepth)，通常不必显式填写\n"
        "- 自定义 glassDepth 必须为正数且不大于 frameDepth，窗框和玻璃必须与父墙厚度范围相交\n"
        "- glassMaterial 指向的材质必须使用 materialClass=glass、transmission>0、有效 ior 的物理玻璃；opacity 必须为 1 或省略\n"
        "- 如果骨架 materials 没有物理玻璃材质，在组件 JSON 外附加提醒（不输出到 JSON）\n"
        "- 数量、宿主墙和位置服从 DesignDocument 解析出的槽位与 component_quota，不自行改成固定对称阵列\n"
        "- 编译后产出: opening + primitive.box×N（窗框+窗棂）\n"
    ),
    "roof": (
        "- roof 是 geometry.elements 原生类型，不是 components\n"
        "- roofType 支持 6 个值: gable/hip/flat/dome/chinese_curved/chinese_pagoda\n"
        "- span 和 depth 按其负责体量的轮廓取值，不是整栋建筑包围盒\n"
        "- L/U 形等多体量必须为每个体量各生成一块 roof，禁止用单块盖住内院/天井\n"
        "- 每块屋顶下方都必须有墙或楼板承托\n"
        "- position 是屋顶中心世界坐标"
    ),
    "railing": (
        "- path 至少 2 个点，定义栏杆走向\n"
        "- 可指定 parentFloor 关联到楼板\n"
        "- 编译后产出: primitive.cylinder×N + beam×M\n"
        "- 栏杆高度通常 0.9~1.1m\n"
        "- 可选栏板填充: infillType=glass|panel（默认无）+ infillThickness(默认0.02) "
        "+ infillTopRatio(默认0.92，栏板顶占栏杆高度比例) + infillMaterial\n"
        "- 玻璃栏板用 infillType=glass + infillMaterial=glass；实心栏板用 panel\n"
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
        "- ⚠️ 雨棚必须有真实的遮蔽对象：只放在**入口门上方**（from[1] 取门高附近，"
        "通常 2.4~2.8m）或露台/阳台门洞上方。禁止在既无门也无窗洞的实墙面" 
        "高处挂装饰雨棚——那种“悬空片”在图上就是漂浮的废构件\n"
        "- 同一面墙上多个雨棚必须有各自的门/窗对应；没有就只保留入口处一个\n"
        "- supportCount>0 时支柱从板底落地到墙底；底层门上方（墙底即地面）才有意义，"
        "高层雨棚请用 supportCount=0 纯悬挑板或对齐阳台板\n"
        "- 编译后产出: primitive.box（板）+ 可选支柱 primitive.box×N"
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
        "- glassMaterial 必须引用 materials 中的 `\"glass\"` 物理玻璃材质，不得用低 opacity 模拟\n"
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
    "elevator": (
        "- position、dimensions{width,depth,height}、floorHeight、floorCount 必填；"
        "initialFloor 可选（默认 0）\n"
        "- position 是**当前停靠层的轿厢地板中心** [x, 该层地面标高, z]；轿厢尺寸必须小于井道净空，"
        "height 必须小于 floorHeight（编译器会自动压缩到 floorHeight-0.15 以内）\n"
        "- floorHeight 与建筑层高一致（如 3.3），floorCount 是井道跨越的层数（含底层）\n"
        "- 井道围合由 wall_core_* 墙体表达（若骨架已有核心筒则复用），本组件不生成井壁；"
        "编译后产出: primitive.box（轿厢，可交互）+ primitive.box×2（导轨）+ primitive.cylinder（呼梯按钮，可交互）\n"
        "- 右键点击轿厢或按钮可呼梯到下一楼层（顶层后循环回 0 层）\n"
        "- 只在多层建筑（≥2 层）且用户提到电梯/升降/垂直交通时生成；单层建筑不要生成"
    ),
    "light": (
        "- initiallyOn 必填\n"
        "- 附带 behaviors.interactive（可交互行为）\n"
        "- 编译后产出: primitive.sphere（灯泡）+ primitive.cylinder（灯座）+ behavior"
    ),
    "furniture": (
        "- furniture 是 geometry.elements 原生类型，不是 components；没有宿主构件，"
        "不需要 parentWall / parentFloor\n"
        "- 局部原点是**底面中心**：X/Z 以占地中心为 0，Y 以底面为 0；"
        "position 是底面锚点，position[1] 即家具底面世界 Y\n"
        "- 底部 Y 必须落在行走面上：有楼板时对齐楼板**顶面**，"
        "无楼板的独立物件场景以地面 Y=0 为基准；悬空超过 0.31m 判警告\n"
        "- rotation 可选，欧拉角**弧度制三维数组** [rx, ry, rz]，缺省 [0,0,0]，"
        "绕**底面中心**旋转，不会把家具甩离落点；只需要改朝向时只写 rotation[1]。"
        "⚠️ 严禁写成度数标量（如 90 或 270）——那是非法格式，会让整件家具从场景里消失；"
        "朝向 +X 写 [0, 1.5708, 0]，朝向 -Z 写 [0, 3.1416, 0]，朝向 -X 写 [0, -1.5708, 0]\n"
        "- 朝向约定：所有子类型的正面统一朝 **+Z**（椅/沙发靠背与床床头在 -Z 侧，"
        "衣柜门与床头柜抽屉面在 +Z 侧）。要面向某个方向时用 rotation[1] 换算，不要靠挪坐标\n"
        "- dimensions 必填 { width, depth, height }，全为正数，含义逐子类型不同：\n"
        "  · table：height 是台面顶高，常用 0.72~0.78\n"
        "  · chair：height 是含靠背的总高，餐椅 0.85~0.95\n"
        "  · sofa：height 是含靠背的总高，0.75~0.90；坐垫恒为 3 块，不随宽度增减\n"
        "  · bed：height 是床头板高 0.90~1.10；width/depth 是床垫尺寸（双人 1.5×2.0）\n"
        "  · wardrobe：height 是柜体总高 2.00~2.40；柜门朝 +Z\n"
        "  · bookshelf：height 是总高；层板恒 2 块（0.33 / 0.66 高度处）\n"
        "  · nightstand：height 是台面顶高 0.50~0.60\n"
        "  · tv_cabinet：height 是台面顶高 0.45~0.60\n"
        "  · lamp：width/depth 是底座与灯罩直径 0.25~0.45，height 是总高\n"
        "  · tile：薄板，height 取 0.02 量级\n"
        "- material 必须引用骨架 materials 中已有的材质名\n"
        "- 数量、子类型与摆位服从设计清单（design_brief 的 component_quota 与槽位），"
        "不自行增减或随意散落\n"
        "- 编译后产出: primitive.box / primitive.cylinder / primitive.sphere 组合，"
        "不产生 opening，也不与墙做布尔运算\n"
        "- ⚠️ subtype 是**闭集**（上列十种）。用户的物件不在其中时不要退而求其次"
        "硬套一个近似的子类型，改由 primitive 组合表达（见 primitive 条目）\n"
    ),
    # primitive / body 是**通用几何通道**：它们不描述业务名词，只描述几何方式。
    # 注册在这里的意义是"模型认不出的物件名也有产出路径"——物件名是开放集，
    # 而几何方式是闭集（box/sphere/cylinder/profile_sweep 四种），
    # 所以「任意物件 → primitive 组合」这条通路对所有名字成立，
    # 不需要为小人/花瓶/路灯各写一条规则。
    "primitive": (
        "- primitive 是 geometry.elements 原生类型，不是 components；没有宿主构件，"
        "不需要 parentWall / parentFloor\n"
        "- 它是**几何语言**，不是业务名词：不要输出\"花瓶\"\"机器人\"这类词，"
        "而是把物件拆成若干 primitive 零件\n"
        "- shape 只有四种：box / sphere / cylinder / profile_sweep\n"
        "- position 是形体的**中心锚点**（与 furniture 的底面中心不同）："
        "box 的 position[1] 是箱体中心高度，落地摆放时 position[1] = height/2\n"
        "- 各 shape 的必填几何参数：\n"
        "  · box → dimensions=[宽, 高, 深]\n"
        "  · sphere → radius（可选 segments/heightSegments）\n"
        "  · cylinder → height，且必须给 radius 或 radiusTop+radiusBottom\n"
        "  · profile_sweep → path（至少 2 个 Vec3 点），可选 profile、closedProfile\n"
        "- rotation 是 [rx, ry, rz] 弧度；scale 默认 [1,1,1]\n"
        "- material 必须引用骨架 materials 中已有的材质名\n"
        "- 一个 primitive 只表达一个形体；复杂物件用多个 primitive 拼装："
        "零件之间靠 position 相对关系衔接，不要互相穿透、也不要有明显悬空断层\n"
        "- 不产生 opening，也不与墙做布尔运算\n"
        "- 编译后产出: 直接就是该形体本身（每个 primitive 一个网格）\n"
    ),
    "body": (
        "- body 是 geometry.elements 原生类型，不是 components；没有宿主构件，"
        "不需要 parentWall / parentFloor\n"
        "- 只表达**简化人物/化身**：头部、躯干、四肢与斗篷由引擎按比例确定性生成，"
        "不接受自定义零件；要自由造型（机器人、动物、器物）改用 primitive 组合\n"
        "- height 必填（米，0.5~2.5），是总身高；脚底落在 position[1]\n"
        "- build 必填：lean（纤瘦）/ athletic（健硕）/ stout（矮壮）\n"
        "- headShape 必填：round / oval / angular\n"
        "- armLength、legLength 是**比例**（0.5~1.5，1.0 为正常），不是米\n"
        "- cloakLength 必填（米，0.3~1.5，没有斗篷也要给一个合法值）；hoodUp 必填（布尔）\n"
        "- position 可选（默认 [0,0,0]）；**rotation 引擎不处理**，不要靠它转向\n"
        "- material 必须引用骨架 materials 中已有的材质名\n"
        "- 编译后产出: primitive.box / primitive.cylinder / primitive.sphere 拼出的人物网格，"
        "不产生 opening\n"
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
        is_list=True,
        required_fields=["type", "id", "parentWall", "from", "width", "height", "interaction"],
        optional_fields=[
            "frameWidth", "frameDepth", "leafDepth", "frameMaterial", "leafMaterial",
            "openingStyle", "doorStyle", "leafRows",
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
        is_list=True,
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
        is_list=True,
        required_fields=["type", "id", "path", "height"],
        optional_fields=[
            "parentFloor", "postSpacing",
            "infillType", "infillThickness", "infillTopRatio", "infillMaterial",
        ],
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
        is_list=True,
        required_fields=["type", "id", "position"],
        optional_fields=["fixtureType", "lightType", "color", "lowIntensity", "highIntensity", "distance", "angle", "initiallyOn"],
        skip_keywords=["不要灯", "没有灯", "不需要灯"],
        need_keywords=["灯", "照明", "光源", "吊灯", "壁灯", "台灯", "灯具",
                       "家具", "装修", "装饰", "室内", "温馨", "明亮"],
        extra_rules=_COMPONENT_RULES["light"],
        priority=3,
    ),
    # ── P3.5: 可交互垂直交通 ──
    # 与其它类型的区别：电梯是**首个带运行时交互的垂直交通组件**——
    # 静态蓝图只存轿厢初始位置，点击呼梯的楼层推进只发生在前端运行时，
    # 与门窗开合同一套「不写回蓝图」原则。
    "elevator": ComponentConfig(
        component_type="elevator",
        label="电梯",
        entity_type="elevator",
        rag_extra_queries=["elevator shaft cabin call button interactive"],
        is_list=True,
        required_fields=["type", "id", "position", "dimensions", "floorHeight", "floorCount"],
        optional_fields=["initialFloor", "material", "frameMaterial"],
        skip_keywords=["不要电梯", "没有电梯", "不需要电梯"],
        need_keywords=["电梯", "升降梯", "垂直交通", "观光梯", "载货梯"],
        extra_rules=_COMPONENT_RULES["elevator"],
        priority=4,
    ),
    # ── P4: 特殊场景 ──
    "ramp": ComponentConfig(
        component_type="ramp",
        label="坡道",
        entity_type="ramp",
        rag_extra_queries=["ramp slope accessibility"],
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
        is_list=True,
        required_fields=["type", "id", "position", "width", "depth", "height"],
        skip_keywords=["不要烟囱", "没有烟囱", "不需要烟囱"],
        need_keywords=["烟囱", "壁炉", "排烟"],
        extra_rules=_COMPONENT_RULES["chimney"],
        priority=5,
    ),
    # ── P6: 独立物件（无宿主，可单独成一个场景）──
    # 与其它 11 类的区别：其余构件都必须挂在某个建筑骨架上（墙/板/屋顶），
    # furniture 是唯一没有宿主、可以就地交付的构件类型。它同时服务两条链：
    # 建筑链里当室内陈设，物件链里当唯一交付物。
    "furniture": ComponentConfig(
        component_type="furniture",
        label="家具",
        entity_type="furniture",
        rag_extra_queries=["furniture subtype dimensions placement rotation"],
        is_list=True,
        is_element=True,
        required_fields=["type", "id", "subtype", "position", "dimensions"],
        optional_fields=["rotation", "style", "material"],
        skip_keywords=["不要家具", "没有家具", "不需要家具"],
        # 注意：不收录"灯具/台灯"这类与 light 组件重叠的词，避免兜底分支同时派发两处。
        need_keywords=[
            "家具", "桌子", "椅子", "沙发", "床", "书柜", "书架",
            "衣柜", "床头柜", "电视柜", "餐桌", "书桌", "茶几",
        ],
        extra_rules=_COMPONENT_RULES["furniture"],
        priority=6,
    ),
    # ── P7: 通用几何通道（物件的开放集出口）──
    # 与其它 12 类的区别：这两个类型**没有 business 词表**，也不靠关键词派发。
    # 它们存在的意义正是"名字不在任何词表里时仍有产出路径" ——
    # 所以 `need_keywords` 必须留空：一旦给了关键词，就又变成"靠名字表判定"，
    # 而名字表永远是开放集。它们只能由**设计清单的配额点名**（min>0）进入派发。
    "primitive": ComponentConfig(
        component_type="primitive",
        label="通用几何体",
        # KB 里 primitive / body 的参数与能力边界写在 `entity_type: component`
        # 的通用分片（component-parameters / capability-boundaries）里，
        # 这两个类型没有各自的专属分片 —— 用 "component" 才能检索到它们；
        # 写成一个不存在的 entity_type 只会让检索空手而归、静默退回代码兜底规则。
        entity_type="component",
        rag_extra_queries=["primitive box sphere cylinder profile_sweep"],
        is_list=True,
        is_element=True,
        required_fields=["type", "id", "shape"],
        optional_fields=[
            "position", "rotation", "scale", "material",
            "dimensions", "radius", "radiusTop", "radiusBottom",
            "height", "segments", "heightSegments", "profile", "path", "closedProfile",
        ],
        skip_keywords=[],
        need_keywords=[],
        extra_rules=_COMPONENT_RULES["primitive"],
        priority=7,
    ),
    "body": ComponentConfig(
        component_type="body",
        label="简化人物",
        entity_type="component",
        rag_extra_queries=["body build headShape cloak hood"],
        is_list=True,
        is_element=True,
        required_fields=[
            "type", "id", "height", "build", "headShape",
            "armLength", "legLength", "cloakLength", "hoodUp",
        ],
        optional_fields=["position", "material"],
        skip_keywords=[],
        need_keywords=[],
        extra_rules=_COMPONENT_RULES["body"],
        priority=7,
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
    *,
    object_scene: bool = False,
) -> list[str]:
    """把模型建议归一化为可安全派发的组件列表。

    - 丢弃未注册或未实现的类型，避免 ``Send`` 派发到不存在的节点。
    - 尊重每个组件的否定关键词。
    - 设计清单中 ``min > 0`` 的组件必须进入派发，避免批准配额无人生成。
    - 当骨架没有给出建议时，保留门、窗、屋顶三个基础组件，并按关键词补充。
    - 阳台编译器已经内嵌栏杆；用户没有单独要求栏杆时避免重复生成。

    ``object_scene=True``（物件链）时**"基础组件"这个概念不成立**：门、窗、屋顶
    都要挂在围护结构上，而物件场景里没有墙可挂。所以那种情况下"没有建议"
    就等于"没有要生成的东西"，绝不能落到 ``["door", "window", "roof"]`` ——
    那会让一个物件场景凭空派发出三扇门和一个屋顶。
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
    if not requested and not object_scene:
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
