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


def append_approved_phase_guidance(
    prompt: str,
    phase_guidance: str,
    compliance_note: str,
) -> str:
    """把已批准执行计划中的阶段任务追加到业务提示词。"""
    if not phase_guidance:
        return prompt
    return f"""{prompt}

# 已批准执行计划中的本阶段任务

{phase_guidance}

{compliance_note}
"""


def build_execution_plan_prompt(
    *,
    intent: str,
    user_message: str,
    research_context: str,
    current_scene_summary: str,
    feedback: str = "",
    previous_tasks: list[dict] | None = None,
) -> str:
    """生成任务专属计划；模型只能选择公开阶段，不能选择代码节点。"""
    import json as _json

    allowed_phases = (
        [
            "architecture",
            "material_plan",
            "skeleton",
            "final_validate",
        ]
        if intent == "generate"
        else ["patch"]
    )
    revision_section = ""
    if feedback:
        revision_section = f"""

# 重新规划意见

用户意见：{feedback}

上一版公开任务：
{_json.dumps(previous_tasks or [], ensure_ascii=False, indent=2)}

保留未被意见否定的目标，明确修改相关任务及其验收条件。
"""
    return f"""你是建筑生成 Agent 的计划架构师。先制定本次任务专属的公开执行计划，不生成 Blueprint，不输出坐标，也不展示隐藏思维链。

# 用户任务

{user_message}

# 当前场景

{current_scene_summary}

# 已检索的建筑知识

{research_context[:6000]}
{revision_section}

# 可映射阶段

{_json.dumps(allowed_phases, ensure_ascii=False)}

# 强制规则

1. 生成任务输出 3～8 项，修改任务输出 1～4 项；任务必须针对本次建筑，禁止照抄通用流水线名称。
2. `phase` 只能逐字使用上面的可映射阶段。不得输出 Python 函数、LangGraph 节点、工具名或任意代码。
3. 生成任务必须至少包含 architecture 和 final_validate；涉及高层时必须规划竖向交通，涉及玻璃幕墙时必须规划真实玻璃与框架关系。
4. `objective` 说明要解决的建筑问题；`acceptance` 给出 1～4 条可检查的结果，不写“效果好”等空话。
5. `summary` 用 1～2 句说明本次计划的核心策略。这是给用户看的公开摘要，不要输出逐步推理过程。

只输出一个 JSON 对象，不要 Markdown：
{{
  "summary": "本次计划的公开摘要",
  "tasks": [
    {{
      "title": "任务专属标题",
      "objective": "这一项具体解决什么",
      "phase": "{allowed_phases[0]}",
      "acceptance": ["可验证条件"],
      "basis": "用户需求或知识依据"
    }}
  ]
}}
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
    profile: dict | None = None,
    complexity_profile: dict | None = None,
    current_plan: dict | None = None,
    revision_feedback: str = "",
    style_preference: list[str] | None = None,
) -> str:
    """生成路径第一阶段：只做总体建筑方案，不设计房间平面。"""
    import json as _json
    profile_payload = {key: value for key, value in (profile or {}).items()
                       if key not in {"default_massing", "default_roof"}}
    if isinstance(profile_payload.get("shapes"), set):
        profile_payload["shapes"] = sorted(profile_payload["shapes"])
    profile_text = _json.dumps(profile_payload, ensure_ascii=False)
    complexity_text = _json.dumps(complexity_profile or {}, ensure_ascii=False)
    style_section = _style_preference_section(style_preference)
    revision_section = ""
    if current_plan and revision_feedback:
        revision_section = f"""

# 本轮是建筑方案修订

用户对上一版的修改意见：{revision_feedback}

上一版方案如下。保留未被意见否定的尺寸、风格和设计关系，只修改相关部分；仍需输出两个完整候选，不能只输出差异：

{_json.dumps(current_plan, ensure_ascii=False, indent=2)}
"""
    return f"""你是建筑方案主创建筑师。只做体量、立面轴网和构件配额，不生成 WILD Blueprint，也不设计房间布局。

# 任务

- 给出 2 个可实施候选，差异必须体现在体量比例、立面节奏或屋顶上。
- 方案服从用户需求和已批准决定；知识库补充能力与条件关系，不能决定默认造型。复杂度落实为本次所需空间与细节，不靠重复构件凑数。
- 当前规划 profile 是：{profile_text}。profile 描述当前规划器可表达的范围；它不是默认建筑。明确需求超出范围时报告限制，不能静默改写。
- 本次复杂度目标是：{complexity_text}。
- `level=detailed` 时完整落实用户选择的关系并明确 structural_grid；仅当用户要求多体量时满足相应 min_volumes。细部包按功能选择，不强制退台、侧翼或固定套餐。
- `level=simple` 时尊重用户的简化要求，不自动补充非必要细部包。
- 除 simple/minimal 外，两个候选中至少一个应通过非矩形或多体量关系、屋顶层次、或一个有功能依据的进深细部形成真实轮廓与阴影；具体策略由本次需求决定，不套建筑类型默认组件。
- front 是最小 Z 的主立面，back 是最大 Z，left/right 分别是最小/最大 X。
- ground_pattern / upper_pattern 的数组长度必须等于 bays；每项只能是 door、window、empty。
- 门只能出现在 ground_pattern。仅当 profile.require_front_entrance=true 时，front 才必须有且只有一个主门槽位。
- ground_pattern 会在首层执行一次，upper_pattern 会在每个建模上层重复执行；其中每个 door/window 都会成为真实组件。component_quota 必须等于这些逐层 pattern 的实际总数，不能先画密集 pattern 再用较小配额抽样删减。
- 标准和高细节方案至少建立一种可执行的构图关系，例如入口主次、上下层开口对位、成组对称或有理由的非对称、体量转折、屋顶层次、或与功能相符的进深细部。关系由本次需求选择，不绑定固定建筑类型和固定构件套餐。
- required_components 以 profile.base_components 为基础；示例中的门窗屋顶不是所有 profile 的固定要求。
- `floors` 表示建筑语义总层数；复杂高层可用较小的 `modeled_floors` 做示意表达，并把 `representation_mode` 设为 `schematic`。
- 本节点不设计房间坐标和内部隔墙；骨架节点直接依据总体体量、立面和结构约束生成 Blueprint 主体。
{revision_section}
{style_section}

# 输出协议

只输出包含 candidates 数组的 JSON 对象，数组中给出两个完整候选。下列是字段契约，不是可以照抄的建筑：
- concept：本次方案概念字符串。
- massing：shape 使用 profile 允许值；width/depth/floor_height 为正数，floors/modeled_floors 为正整数；representation_mode 为 full 或 schematic；symmetry 为布尔值。
- volumes：按本次方案输出体量数组，每项包含 id、role(primary/secondary)、x、z、width、depth、start_floor、end_floor；单体也需明确一个完整体量，多层单体不必拆成退台。
- structural_grid：system 为 wall_bearing/frame/hybrid/long_span/shell；x_bays/z_bays 为正整数。
- circulation：vertical_strategy 为 none/stair/core_and_stair；核心筒方案必须同时包含楼梯，多层建筑不能为 none。
- detail_packages：实际选用的附属组件名称数组，允许为空；只能用当前支持类型。
- facades：front/back/left/right 每面包含 bays、ground_pattern、upper_pattern；主入口面可给 entrance_bay，槽位数量与 bays 一致。
- roof：type 使用当前六种 roofType；ridge_axis 为 x 或 z；overhang 为非负数。
- component_quota：按实际组件类型提供 min/max 整数及 note；如指定屋型可提供 type，不给未选择的组件硬配额。
- required_components：本次真正需要的组件名称数组。
- design_rationale：说明体量、入口、交通与构件选择如何满足用户要求的字符串数组。
所有数值都必须由本次需求推导；不要输出类型说明文字代替数值。

# 知识库参考

{spec_text}
"""


def build_material_plan_prompt(
    architecture_plan: dict,
    available_assets: list[dict],
    procedural_presets: list[dict] | None = None,
    style_preference: list[str] | None = None,
) -> str:
    """让模型设计材质意图，只能引用可信 PBR 资产或受控程序化材质。"""
    import json as _json
    style_section = _style_preference_section(style_preference)
    return f"""你是建筑材质设计师。为已批准的建筑方案制定克制、统一且可实施的材质方案。

# 已批准建筑方案

{_json.dumps(architecture_plan, ensure_ascii=False, indent=2)}
{style_section}

# AVAILABLE_PBR_ASSETS（唯一允许引用的纹理资产）

{_json.dumps(available_assets, ensure_ascii=False, indent=2)}

# AVAILABLE_PROCEDURAL_PRESETS（唯一允许选择的程序化配方）

{_json.dumps(procedural_presets or [], ensure_ascii=False, indent=2)}

# 强制规则

1. 你只设计材质意图，不生成纹理、不输出 URL、不修改灯光、曝光或阴影。
2. `assetId` 只能逐字引用 AVAILABLE_PBR_ASSETS 中存在的值；`proceduralPresetId` 只能逐字引用 AVAILABLE_PROCEDURAL_PRESETS 中存在的值；没有合适候选必须使用 null，严禁猜测 ID。
3. 必须覆盖 facade_primary、structure、floor、frame、door、glass、roof；ground 和 accent 可选。
4. 单个角色最多选择一个资产，总体保持主材、辅材、点缀的层级，不制造随机拼贴。
5. stone/concrete/brick/wood/plaster/tile 的 metallic 不得超过 0.15；metal 的 metallic 应为 0.5–1。
6. glass 不选择纹理资产，不设置 opacity；系统会应用受控物理玻璃预设。
7. 若资产声明 recommendedRoles，只能用于其中列出的角色。
8. baseColor 是 3 个 0–1 数值；roughness、metallic 是 0–1 数值。
9. 用户即使只说“生成一个别墅”，你也必须结合建筑方案主动补齐主材、辅材、点缀、表面新旧程度和整体色板；“用户没说材质”不等于“不做材质设计”。不得反问用户逐项提供 Shader 参数。
10. PBR 入库现在只要求一张 Base Color；`channels` 只有 `baseColor` 的资产也是完整合法候选。Normal/Roughness 等可选通道只表示增强质量，不能因为缺少它们就忽略该资产。
11. 对 facade_primary 在 `assetId`、`proceduralPresetId` 和普通无图片材质中三选一。天然纹理、扫描质感或高匹配资产优先 PBR；规则砖墙、明确无贴图或需要可控老化时可选择程序化预设；二者都不合适时使用普通材质。
12. `shaderAdjustments` 只允许 AVAILABLE_PROCEDURAL_PRESETS 声明的字段。强度只输出 `none/subtle/moderate/strong`；`mortarDepth` 只输出 `shallow/standard/deep`；`tone` 只输出 `default/light/dark/warm`；`cleanliness` 只输出 `clean/natural`。不要输出具体 uniform、GLSL、Shader 源码或未知字段。
13. 只在建筑类型、风格、环境或材质叙事确实支持砖材时选择红砖预设；现代玻璃幕墙、木屋或石材立面不得为了使用 Shader 强行改成红砖。

# 输出协议

只输出一个 JSON 对象，不要 Markdown：
{{
  "concept": "一句话材质概念",
  "palette": ["主色", "辅色", "点缀色"],
  "roles": [
    {{"role":"facade_primary","assetId":null,"proceduralPresetId":null,"shaderAdjustments":{{}},"baseColor":[0.82,0.8,0.76],"roughness":0.72,"metallic":0}},
    {{"role":"structure","assetId":null,"baseColor":[0.65,0.66,0.67],"roughness":0.76,"metallic":0}},
    {{"role":"floor","assetId":null,"baseColor":[0.5,0.5,0.5],"roughness":0.8,"metallic":0}},
    {{"role":"frame","assetId":null,"baseColor":[0.12,0.13,0.14],"roughness":0.3,"metallic":0.8}},
    {{"role":"door","assetId":null,"baseColor":[0.35,0.2,0.1],"roughness":0.62,"metallic":0}},
    {{"role":"glass","assetId":null,"baseColor":[0.72,0.88,0.96],"roughness":0.08,"metallic":0}},
    {{"role":"roof","assetId":null,"baseColor":[0.25,0.26,0.28],"roughness":0.76,"metallic":0}}
  ]
}}
"""

