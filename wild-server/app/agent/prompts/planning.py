"""执行计划、建筑方案与材质计划提示词。"""

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


def _style_preference_section(style_preference: list[str] | None) -> str:
    """把规则预选的候选风格注入早期节点 prompt。

    这里只把分类器推断的候选 id 当作设计方向，避免总体方案与材质方案
    互相冲突，不注入风格包细节。
    """
    if not style_preference:
        return ""
    safe_ids = [str(item) for item in style_preference if str(item).strip()]
    if not safe_ids:
        return ""
    return f"""
# 候选建筑风格（由系统根据需求预选）

总体方案和材质方案应优先服从以下候选的屋顶、体量与色彩倾向：
{", ".join(safe_ids)}。不要虚构候选之外的风格细节。
"""


def build_architecture_plan_prompt(
    spec_text: str,
    profile_id: str,
    complexity_profile: dict | None = None,
    current_plan: dict | None = None,
    revision_feedback: str = "",
    style_preference: list[str] | None = None,
) -> str:
    """首轮交付完整设计；设计方法和专项关系由知识库提供。"""
    import json
    from app.agent.knowledge.component_names import component_reference_prompt
    from app.agent.generation.architecture.profile import resolve_complexity_profile
    from app.agent.generation.material.plan import ROLE_SPECS
    complexity = resolve_complexity_profile((complexity_profile or {}).get("level", "simple"))
    current = json.dumps({k: v for k, v in current_plan.items()
                          if k not in {"component_quota", "required_components"}}, ensure_ascii=False) if current_plan else "无"
    output_fields = {
        "concept": "string：本次设计概念",
        "design_intent": {
            "goals": ["string"], "assumptions": ["string"], "selected_systems": ["string"],
            "spatial_strategy": "string", "composition": "string", "material_strategy": "string",
        },
        "massing": {"shape": "string", "width": "number", "depth": "number",
                    "floors": "integer", "modeled_floors": "integer", "floor_height": "number"},
        "volumes": [{"id": "string", "x": "number", "z": "number", "width": "number",
                     "depth": "number", "start_floor": "integer", "end_floor": "integer",
                     "facades": {}}],
        "structural_grid": {"system": "string", "x_bays": "integer", "z_bays": "integer"},
        "circulation": {"vertical_strategy": "string", "description": "string"},
        "facades": {face: {"bays": "integer", "ground_pattern": ["string"], "upper_pattern": ["string"]}
                    for face in ("front", "back", "left", "right")},
        "roof": {"type": "string", "ridge_axis": "x 或 z", "overhang": "number",
                 "volumes": [{"volume": "体量 id", "type": "string", "overhang": "number"}]},
        "components": [{
            "id": "string", "type": "string", "host": "宿主 id，独立构件可省略",
            "size": {"width": "number", "height": "number", "depth": "number"},
            "form": {}, "description": "string", "placement": {},
            "floor_connections": [{"from_floor": "integer", "to_floor": "integer 或 roof"}],
        }],
        "floor_layouts": [{"floor": "integer", "level": "number",
                           "rooms": [{"id": "string", "name": "string", "void": "boolean（可选，true 表示此层挑空）", "bounds": {
                               "x": "number", "z": "number", "width": "number", "depth": "number"}}],
                           "walls": [{"id": "string", "from": ["number", "number"],
                                      "to": ["number", "number"], "thickness": "number"}]}],
        "envelope": {"system": "string"},
    }
    return f"""
你负责绘制完整建筑设计图纸，发挥建筑知识和审美；后续 plan 拆分任务，execute 研究并实现构件。
本次建筑类型线索：{profile_id}。建筑设计以用户需求为准。
按“需求与形制 → 体量与标高 → 功能交通 → 围护开口 → 屋面附属 → 材料表达”组织本次设计，结合参考中的设计步骤与关系复核，把决定落实到对应字段。
design_intent 简述实际采用的设计选择；庭院、通高、幕墙等已选特征需要对应的空间或构件数据，不能只在文字中命名。
本次用户选择的设计粒度：{complexity['reason']}
用户明确要求优先于默认粒度。需要独立实现的结构、交通及形制构件须写入 components，明确位置、尺寸与连接关系；不能只在概念中提及。
材料与配色写在 description/form。material_role 可选，使用现有角色 {', '.join(ROLE_SPECS)}；同一角色绑定同一种材质，不同材质使用不同角色或独立材质。

只返回一个完整设计 JSON 对象。以下 JSON 是字段结构与类型说明，不是设计取值；number/integer 必须替换为实际数值，string 替换为设计内容。floor_layouts、envelope、volume.facades 可选，floor_connections 仅用于楼梯；数组展示单项结构，没有构件时 components 用 []；尺寸与标高单位为米：
```json
{json.dumps(output_fields, ensure_ascii=False, indent=2)}
```

基础字段约定：
- massing.width/depth 包含所有 volumes 的总体包络；主楼尺寸写在对应 volume。完整建模时 modeled_floors=floors，楼层是从 1 开始的整数；台基、杆件等无楼层的实体写 components。
- 共享 facades 作用于所有体量，差异用 volume.facades 覆盖，格式与共享立面相同。每个 ground_pattern/upper_pattern 的长度等于 bays；open 是无墙，empty 是实墙无开口；内墙不重复声明体量围护墙。
- placement.face 只允许 front/back/left/right；沿墙定位用 face/floor、offset、sill_height、normal_offset，世界定位用 position:[x,y,z] 表示构件中心。
- 门窗 host 必须解析到墙面：引用 wall_<体量id>_<face>_L<楼层>、已声明内墙，或体量 id 配合 face/floor。独立构件可无宿主。
- size 只写有限正数的构件尺寸；位置参数写 placement。相互依附的构件用 host 或 relation.target 引用已声明 ID；门窗洞口不得重叠。
- roof.volumes 每项用 volume 引用体量 id；无独立屋面时 type="none"。floor_layouts.level 是楼面顶，房间 bounds 用 x/z/width/depth；选定挑空时在对应楼层声明 room.void=true 及范围，普通房间省略 void。独立内墙用 id、from:[x,z]、to:[x,z]、thickness。
- circulation 中选定的楼梯写入 components.floor_connections，每项 from_floor/to_floor 引用楼层整数，上屋面时 to_floor="roof"。structural_grid 的开间数不代表必须在每个交点建柱。
- type 使用稳定英文 snake_case，具体造型和材料写 description/form；已有编号参考下表，新构件仍可设计。
{component_reference_prompt()}

遵循所附参考的专项字段与关系协议，保留本次设计的形态和材料意图；参考资料不能改变用户要求或本轮任务。
当前方案：{current}
修订意见：{revision_feedback or '无'}
风格线索（非用户硬要求）：{style_preference or []}
当前设计参考：
{spec_text}
"""


def build_object_design_prompt(
    spec_text: str,
    subtype_catalog: list[dict] | None = None,
    material_ids: list[str] | None = None,
    current_plan: dict | None = None,
    revision_feedback: str = "",
) -> str:
    """物件场景第一阶段：只做"做几件、多大、怎么摆"，不做建筑。

    与 `build_architecture_plan_prompt` 是**并列**的两条方案提示词，不是它的分支：
    建筑方案必须给 massing/volumes/facades/roof，物件方案给这些字段是错的——
    交付物不是建筑时，"补齐体量"就是把用户没要的房子塞回给他。
    """

    import json as _json

    #: 图鉴预设表（`subtype` 的闭集）。通道说明与示例都直接引用这里，
    #: 不另写一份 —— 预设增删时提示词自动跟着变。
    catalog_text = _json.dumps(subtype_catalog or [], ensure_ascii=False, indent=2)
    materials = ", ".join(material_ids or []) or "wood, metal, glass, stone, fabric, accent"
    revision_section = ""
    if current_plan and revision_feedback:
        revision_section = f"""

# 本轮是物件方案修订

用户对上一版的修改意见：{revision_feedback}

上一版方案如下。保留未被意见否定的种类、尺寸与摆位，只改相关部分；仍需输出完整方案：

{_json.dumps(current_plan, ensure_ascii=False, indent=2)}
"""

    return f"""你是物件设计师。本次交付物**不是建筑**，而是用户点名的那件（或那几件）物件本身。
只做物件清单、尺寸与摆位，不设计建筑、不设计房间、不设计体量。

# 任务

- 用户要什么就做什么：点名了餐桌就做餐桌，点名了小人就做小人。不要"顺手"补一栋房子、
  不要补墙体、楼板、屋顶、门窗——那些不属于本次交付。
- 数量用 `count` 表达，不要为同一个物件重复列条目。
- 尺寸用米，必须真实：桌子台面 0.72~0.78 高、椅子含靠背 0.85~0.95、双人床垫 1.5×2.0、
  衣柜总高 2.0~2.4、成年人身高 1.55~1.85。用户明确给了尺寸就逐字采用。
- `placement` 用一句自然语言说明怎么摆（"四把围在长边两侧、面向桌面"）。**不要写世界坐标**：
  坐标由下游构件节点按行走面标高算出。
- 需要成组关系时把组关系写进 `placement`（围合、靠墙、面向视线、并列成排），
  不要为每件单独编一个坐标。
- 用户没提材质时也要主动给一个材质倾向，不要反问用户逐项提供参数。

# 三种表达通道（`kind` 只能取这三个值）

**先看图鉴，再看几何。判据是"能不能用已有的精确参数表达"，不是"是什么东西"。**

## 1. `kind = "furniture"` —— 图鉴预设（首选）

名字能落进下面的子类型表时用它，几何最精确（引擎有逐子类型的原生 builder）。
必须同时给 `subtype`（只能取表里的值）与 `width`/`depth`/`height`。

{catalog_text}

`height` 的含义逐个类型不同，以上表为准（例如 `table` 是台面顶高，`bed` 是床头板高）。

## 2. `kind = "primitive"` —— 通用几何组合（开放集出口）

**图鉴里没有的东西走这条。** 它不认名字，只认形状：把物件拆成若干基础几何体，
每个几何体给足参数。名字是列不完的（小人、花瓶、路灯、机器人、雕塑…），
但几何方式只有四种，所以这条通道对**任何**物件都成立。

- `parts` 是零件表，每项是一个零件：
  - `shape = "box"` → 必填 `dimensions: [宽, 高, 深]`
  - `shape = "sphere"` → 必填 `radius`
  - `shape = "cylinder"` → 必填 `height`，并且给 `radius`，或给 `radiusTop` + `radiusBottom`（锥台）
  - `shape = "profile_sweep"` → 必填 `path`（至少 2 个点），可选 `profile`（截面点对）
- 每个零件可给 `position`（**必填**，见下）、可选 `rotation`（弧度）、`material`。
-  `position` 是零件中心相对**物件底面中心**的局部坐标：**X/Z 以物件中心为 0，
  Y 以物件落地底面为 0**。所以一个高 0.36m 的圆柱体从地面立起要写 `position: [0, 0.18, 0]`
  （0.18 = 高度的一半）。最低的零件底面必须落在 `y = 0`，不要整体悬空。
- 零件之间要**衔接**：该接触的面贴住、不要互相穿透，也不要出现明显悬空断层。
- 每个零件单独给它自己的 `material`；没写时用整件物件的 `material`。
- 零件数与复杂度要克制：一眼认得出轮廓即可，不要用几十个零件堆细节
  （上限 64 个零件）。

## 3. `kind = "body"` —— 简化人物（仅限人形）

需要一个人物/化身时用这条：头部、躯干、四肢与斗篷由引擎按比例生成，
比用 primitive 拼人更省事。参数放在 `params`：

- `height` 身高（米，0.5~2.5）；`build` 体型 `lean`/`athletic`/`stout`；
  `headShape` 头型 `round`/`oval`/`angular`
- `armLength`、`legLength` 是**比例**（0.5~1.5，1.0 为正常），不是米
- `cloakLength` 斗篷长度（米，0.3~1.5，没有斗篷也要给一个合法值）；
  `hoodUp` 兜帽是否戴上（布尔）
- 它只有"人"这一种造型；机器人、动物、器物一律走 `primitive`

# 不要做的事

- **不要退而求其次套一个相近的预设**：用户要"小人"就不要给 `table`，
  要"花瓶"就不要给 `nightstand`。名字对不上就走 `primitive`，别硬套。
- **不要用别的物件顶替**：既表达不了、又没法用几何组合近似时，
  把它写进 `unsupported_objects` 如实说明，**不要**换成一件你没被要求的东西。
- 不要输出 `massing`、`volumes`、`facades`、`roof`、`wall` 里的任何内容。

# 朝向与落地（写摆位时必须知道）

- 图鉴子类型的**正面统一朝 +Z**：椅/沙发靠背与床床头在 -Z 侧，衣柜门与床头柜抽屉面在 +Z 侧。
- 要改变朝向写 `rotation_y`（弧度，绕物件**底面中心**旋转，不会把物件甩离落点），
  不要靠挪位置凑朝向。默认 0 即可，只在摆位确实需要转向时才给。
- 物件默认落地：没有楼板的独立场景以地面 Y=0 为行走面。不要写抬离地面的高度。

# 材质

只能引用以下材质名（写进 `material`，或零件的 `material`）：{materials}。
`wood` 木、`metal` 金属、`glass` 玻璃、`stone` 石/混凝土、`fabric` 织物、`accent` 点缀色。

# 输出协议

只输出一个 JSON 对象，不要 Markdown、不要解释、不要输出候选方案数组：
{{
  "kind": "object",
  "concept": "一句话说明本次做了哪些物件、按什么关系摆放",
  "objects": [
    {{"kind": "furniture", "name": "餐桌", "subtype": "table", "count": 1,
      "width": 1.4, "depth": 0.8, "height": 0.75,
      "placement": "置于场景中部", "material": "wood", "rotation_y": 0.0,
      "rationale": "用户点名要一张餐桌，命中图鉴预设"}},
    {{"kind": "furniture", "name": "餐椅", "subtype": "chair", "count": 4,
      "width": 0.45, "depth": 0.5, "height": 0.9,
      "placement": "两两分列长边两侧、面向桌面", "material": "wood", "rotation_y": 0.0,
      "rationale": "与餐桌配套成组"}},
    {{"kind": "primitive", "name": "花瓶", "count": 1,
      "width": 0.22, "depth": 0.22, "height": 0.5,
      "placement": "立于餐桌中央", "material": "stone",
      "parts": [
        {{"shape": "cylinder", "radius": 0.09, "height": 0.36, "position": [0, 0.18, 0]}},
        {{"shape": "cylinder", "radiusBottom": 0.09, "radiusTop": 0.05, "height": 0.14,
          "position": [0, 0.43, 0]}}
      ],
      "rationale": "图鉴没有花瓶，用圆柱+锥台拼出瓶身与瓶颈"}},
    {{"kind": "body", "name": "小人", "count": 1, "height": 1.72,
      "placement": "站在场景一侧、面向+Z", "material": "accent",
      "params": {{"height": 1.72, "build": "lean", "headShape": "oval",
                  "armLength": 1.0, "legLength": 1.0, "cloakLength": 0.4, "hoodUp": false}},
      "rationale": "用户点名要一个人物，用引擎的人形元素"}}
  ],
  "unsupported_objects": [],
  "design_rationale": ["说明尺寸与摆位如何满足用户要求"]
}}

- `objects` 每项必须有 `kind`；`furniture` 必须有 `subtype`，`primitive` 必须有 `parts`，
  `body` 必须有 `params`。每项的 `name` 写用户点名的那个词。
- `furniture` 的 `width`/`depth`/`height` 与 `body` 的 `height` 是必填正数（米）；
  `primitive` 的 `width`/`depth`/`height` 是整件物件的包围盒，可从零件算出。
- 实在无法表达某个点名物件时，把它写进 `unsupported_objects`（字符串列表），
  **不要**用其它物件顶上；此时 `objects` 可以为空。
- 所有数值都必须由本次需求推导；不要输出类型说明文字代替数值。
{revision_section}

# 知识库参考

{spec_text}
"""


def build_material_plan_prompt(
    architecture_plan: dict,
    available_assets: list[dict],
    procedural_presets: list[dict] | None = None,
    style_preference: list[str] | None = None,
    *,
    object_scene: bool = False,
) -> str:
    """让模型设计材质意图，只能引用可信 PBR 资产或受控程序化材质。

    ``object_scene=True`` 时角色清单换成物件角色（木/金属/玻璃/石/织物/点缀）：
    建筑角色里的 facade_primary、roof、door 对一张桌子没有意义，硬要求覆盖它们
    只会让模型编出一个不存在的建筑语境。
    """
    import json as _json
    style_section = _style_preference_section(style_preference) if object_scene else ""
    explicit_materials = [{"id": c.get("id"), "role": c["material_role"], "material": c["form"]["material"]}
                          for c in architecture_plan.get("components", []) if c.get("material_role")
                          and isinstance(c.get("form"), dict) and c["form"].get("material")]
    # P6-A：没有资产**不等于**不能做材质设计。合法参数材质（baseColor /
    # roughness / metallic）不依赖任何贴图就能承载设计意图，必须把这句说清楚，
    # 否则空列表会让模型以为自己无事可做，转而去编 assetId。
    _no_asset_note = (
        "\n> **本机当前没有任何可用的 PBR 纹理资产**（上面的列表是空的）。\n"
        "> 这**不影响**你做材质设计：`assetId` 一律填 `null`，改用 `baseColor` /\n"
        "> `roughness` / `metallic` 直接表达材质——颜色、粗糙度、金属度都是**参数**，\n"
        "> 不需要贴图。用户的配色要求此时完全靠这些参数落地。\n"
        "> 严禁编造 assetId 或任何纹理文件名。\n"
        if not available_assets
        else ""
    )
    if object_scene:
        role_requirement = (
            "3. 只从 wood（木）、metal（金属）、glass（玻璃）、stone（石/混凝土）、"
            "fabric（织物）、accent（点缀色）里选择本次实际需要的角色；"
            "不要输出 facade_primary、structure、floor、frame、door、roof、ground——"
            "本次交付物是物件，没有外墙、楼板和屋顶。"
        )
        subject = "你是家具与陈列物件的材质设计师。为已批准的对象方案制定克制、统一且可实施的材质方案。"
        plan_heading = "# 已批准的物件方案"
        motivate = "用户即使只说“生成一个桌子”，你也必须结合对象方案主动补齐主材、辅材与整体色板；"
        rule_11 = (
            "在 `assetId`、`proceduralPresetId` 和普通无图片材质中三选一。"
            "天然木纹、石材或织物纹理等扫描质感优先 PBR；"
            "二者都不合适时使用普通材质。"
        )
        rule_13 = (
            "只在物件材质叙事确实支持某种程序化预设时选择它；"
            "不确定就用普通材质，不得为了使用 Shader 强行改成不相关的题材。"
        )
        example_roles = _json.dumps([
            {"role": "wood", "assetId": None, "proceduralPresetId": None,
             "shaderAdjustments": {}, "baseColor": [0.42, 0.26, 0.14],
             "roughness": 0.62, "metallic": 0},
            {"role": "metal", "assetId": None, "proceduralPresetId": None,
             "shaderAdjustments": {}, "baseColor": [0.16, 0.17, 0.18],
             "roughness": 0.32, "metallic": 0.8},
            {"role": "fabric", "assetId": None, "proceduralPresetId": None,
             "shaderAdjustments": {}, "baseColor": [0.46, 0.44, 0.42],
             "roughness": 0.92, "metallic": 0},
        ], ensure_ascii=False, indent=4)
    else:
        role_requirement = (
            "3. 必须覆盖 facade_primary、structure、floor、frame、door、glass、roof；"
            "ground 和 accent 可选。"
        )
        subject = "你是建筑材质设计师。落实当前建筑设计意图中的材料层次与色彩；方案尚待用户审核，不能另选风格或改动几何。"
        plan_heading = "# 当前建筑方案（design_intent 是材料方向，design_rationale 是设计依据）"
        motivate = (
            "用户即使只说“生成一个别墅”，你也必须结合建筑方案主动补齐主材、辅材、点缀、"
            "表面新旧程度和整体色板；"
        )
        rule_11 = (
            "对 facade_primary 在 `assetId`、`proceduralPresetId` 和普通无图片材质中三选一。"
            "天然纹理、扫描质感或高匹配资产优先 PBR；规则砖墙、明确无贴图或需要可控老化时"
            "可选择程序化预设；二者都不合适时使用普通材质。"
        )
        rule_13 = (
            "只在建筑类型、风格、环境或材质叙事确实支持砖材时选择红砖预设；"
            "现代玻璃幕墙、木屋或石材立面不得为了使用 Shader 强行改成红砖。"
        )
        example_roles = _json.dumps([
            {"role": "facade_primary", "assetId": None, "proceduralPresetId": None,
             "shaderAdjustments": {}, "baseColor": [0.82, 0.8, 0.76],
             "roughness": 0.72, "metallic": 0},
            {"role": "structure", "assetId": None, "baseColor": [0.65, 0.66, 0.67],
             "roughness": 0.76, "metallic": 0},
            {"role": "floor", "assetId": None, "baseColor": [0.5, 0.5, 0.5],
             "roughness": 0.8, "metallic": 0},
            {"role": "frame", "assetId": None, "baseColor": [0.12, 0.13, 0.14],
             "roughness": 0.3, "metallic": 0.8},
            {"role": "door", "assetId": None, "baseColor": [0.35, 0.2, 0.1],
             "roughness": 0.62, "metallic": 0},
            {"role": "glass", "assetId": None, "baseColor": [0.72, 0.88, 0.96],
             "roughness": 0.08, "metallic": 0},
            {"role": "roof", "assetId": None, "baseColor": [0.25, 0.26, 0.28],
             "roughness": 0.76, "metallic": 0},
        ], ensure_ascii=False, indent=4)

    return f"""{subject}

{plan_heading}

{_json.dumps(architecture_plan, ensure_ascii=False, indent=2)}
{style_section}

# 本次构件绑定的显式材质

{_json.dumps(explicit_materials, ensure_ascii=False, indent=2)}
这些绑定决定对应角色的实际材质。未绑定角色的构件使用自己的局部材质；下方示例中的颜色和金属度不代替本次材料要求。

# AVAILABLE_PBR_ASSETS（唯一允许引用的纹理资产）

{_json.dumps(available_assets, ensure_ascii=False, indent=2)}

{_no_asset_note if not available_assets else ""}
# AVAILABLE_PROCEDURAL_PRESETS（唯一允许选择的程序化配方）

{_json.dumps(procedural_presets or [], ensure_ascii=False, indent=2)}

# 强制规则

1. 你只设计材质意图，不生成纹理、不输出 URL、不修改灯光、曝光或阴影。
2. `assetId` 只能逐字引用 AVAILABLE_PBR_ASSETS 中存在的值（**列表为空就一律填 null**，不得猜测或编造任何 ID）；`proceduralPresetId` 只能逐字引用 AVAILABLE_PROCEDURAL_PRESETS 中存在的值；没有合适候选必须使用 null，严禁猜测 ID。
{role_requirement}
4. 单个角色最多选择一个资产，总体保持主材、辅材、点缀的层级，不制造随机拼贴。
5. stone/concrete/brick/wood/plaster/tile 的 metallic 不得超过 0.15；metal 的 metallic 应为 0.5–1。
6. glass 不选择纹理资产，不设置 opacity；系统会应用受控物理玻璃预设。
7. 若资产声明 recommendedRoles，只能用于其中列出的角色。
8. baseColor 是 3 个 0–1 数值；roughness、metallic 是 0–1 数值。
9. {motivate}“用户没说材质”不等于“不做材质设计”。不得反问用户逐项提供 Shader 参数。
10. PBR 入库现在只要求一张 Base Color；`channels` 只有 `baseColor` 的资产也是完整合法候选。Normal/Roughness 等可选通道只表示增强质量，不能因为缺少它们就忽略该资产。
11. {rule_11}
12. `shaderAdjustments` 只允许 AVAILABLE_PROCEDURAL_PRESETS 声明的字段。强度只输出 `none/subtle/moderate/strong`；`mortarDepth` 只输出 `shallow/standard/deep`；`tone` 只输出 `default/light/dark/warm`；`cleanliness` 只输出 `clean/natural`。不要输出具体 uniform、GLSL、Shader 源码或未知字段。
13. {rule_13}
14. 逐项核对 components 的 material_role 与 description/form。每个角色的参数会应用到所有绑定构件，必须兑现它们共同的材料和颜色；概念文字写“木质”而角色参数仍取石灰色，不算落实意图。不同材料使用各自角色或独立材质，不按“都属于装饰”合并。

# 输出协议

只输出一个 JSON 对象，不要 Markdown：
{{
  "concept": "一句话材质概念",
  "palette": ["主色", "辅色", "点缀色"],
  "roles": {example_roles}
}}
"""
