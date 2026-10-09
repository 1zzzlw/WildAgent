"""DesignDocument v1 的唯一后端类型定义。

JSON Schema、REST 校验、LangGraph 状态和前端类型都以这里的字段语义为准。
Blueprint 是编译产物，不反向充当建筑方案。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .openings import OPENING_KINDS, OPEN_SIDE, opening_kind, split_opening


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DesignRequirements(ContractModel):
    source_request: str = Field(min_length=1, max_length=8000)
    building_type: str = Field(default="building", min_length=1, max_length=80)
    profile: str = Field(default="custom", min_length=1, max_length=80)
    style_intent: list[str] = Field(default_factory=list, max_length=12)


class ComplexityDecision(ContractModel):
    level: Literal["minimal", "simple", "standard", "detailed"] = "standard"
    min_volumes: int = Field(default=1, ge=1, le=8)
    min_detail_packages: int = Field(default=0, ge=0, le=12)
    target_structural_elements: int = Field(default=10, ge=1, le=1000)
    grid_bays: tuple[int, int] = Field(default=(2, 2))
    reason: str = Field(default="", max_length=300)


class MassingTierDecision(ContractModel):
    """massing.tiers 的一段：从底到顶逐段的收放比例（塔形/退台的立面轮廓表态）。

    比例相对 massing 的对应向尺寸（width_ratio ↔ width，depth_ratio ↔ depth），
    段与段在立面上居中堆叠。这是**可选**表态——缺省时图纸与编译器从
    volumes 落层或 shape 派生轮廓，与本字段无关。
    """

    floors: int = Field(ge=1, le=200)
    width_ratio: float = Field(gt=0, le=1)
    depth_ratio: float = Field(default=1.0, gt=0, le=1)


class MassingDecision(ContractModel):
    shape: str = Field(min_length=1, max_length=40)
    width: float = Field(gt=0, le=500, description="总体 X 方向尺寸控制上限（米），无世界原点边界")
    depth: float = Field(gt=0, le=500, description="总体 Z 方向尺寸控制上限（米），实际包络由 volumes 决定")
    floors: int = Field(ge=1, le=200)
    modeled_floors: int = Field(ge=1, le=200)
    representation_mode: Literal["full", "schematic"] = "full"
    floor_height: float = Field(gt=0.5, le=20)
    symmetry: bool = False
    #: 立面轮廓表态（可选）：从底到顶逐段的收放。电视塔、宝塔、阶梯收分的
    #: 高层用它表达轮廓；不写 = 交给下游从 volumes/shape 派生。
    tiers: list[MassingTierDecision] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def modeled_floor_count_is_valid(self):
        if self.modeled_floors > self.floors:
            raise ValueError("modeled_floors 不能大于 floors")
        return self

    @model_validator(mode="after")
    def tiers_cover_all_floors(self):
        if self.tiers and sum(tier.floors for tier in self.tiers) != self.floors:
            raise ValueError("massing.tiers 各段 floors 之和必须等于 massing.floors")
        return self


class VolumeDecision(ContractModel):
    id: str = Field(min_length=1, max_length=48, pattern=r"^[A-Za-z0-9_\-]+$")
    role: Literal["primary", "secondary"] = "primary"
    x: float = Field(allow_inf_nan=False, description="体量平面起点的世界 X 坐标（米），不是中心")
    z: float = Field(allow_inf_nan=False, description="体量平面起点的世界 Z 坐标（米），不是中心")
    width: float = Field(gt=0, le=500)
    depth: float = Field(gt=0, le=500)
    start_floor: int = Field(ge=1, le=200)
    end_floor: int = Field(ge=1, le=200)

    @model_validator(mode="after")
    def floor_range_is_valid(self):
        if self.end_floor < self.start_floor:
            raise ValueError("volume.end_floor 不能小于 start_floor")
        return self


class StructuralGridDecision(ContractModel):
    system: Literal["wall_bearing", "frame", "hybrid", "long_span", "shell"]
    x_bays: int = Field(ge=1, le=32)
    z_bays: int = Field(ge=1, le=32)


#: 一个立面槽位的 token：``"window"`` / ``"door:slide"`` / ``"empty"``。
#:
#:  **不再是一段 `Literal`**：形态（§3.3）是"类型 × 形态"的开放组合，写成 Literal 只会
#: 漏取值。取值域是**文法**，唯一定义在 :mod:`app.design.openings`，由下面的
#: `patterns_use_legal_tokens` 就地校验。
OpeningToken = str


class FacadeDecision(ContractModel):
    bays: int = Field(ge=1, le=32)
    entrance_bay: int | None = Field(default=None, ge=1, le=32)
    ground_pattern: list[OpeningToken]
    upper_pattern: list[OpeningToken]

    @field_validator("ground_pattern", "upper_pattern")
    @classmethod
    def patterns_use_legal_tokens(cls, value: list[str]) -> list[str]:
        """只校验**类型**合法；形态名不合法**不在这里拒**。

         两类问题要分开（红线"只标记不阻断"）：类型认不出（``"garage"``）是我们自己不认，
        该拒；**形态名认不出**（``"window:casement"``）是模型用了个别的词，
        归一化会把它降级成纯类型、照常生成——在这里拒等于因为一个形容词拼错就掐掉整轮生成。

        ``empty`` 与 ``open`` 是**两个不同的类型**（P5-B：有墙无洞 / 开敞无墙），
        两者都**不带形态**：``empty:swing`` / ``open:swing`` 一律拒 —— 否则归一化会
        静默把形态丢掉，写的人以为表态了形态、其实没有。
        """

        for token in value:
            # 判据是"**类型部分**逐字合法"，不是"归一化结果 == token"：
            # 形态名不合法要放过（`window:casement` 归一化成 `window`），
            # 但 `empty:swing` / `open:swing` 必须拒 —— 这两类**没有形态**，
            # 归一化会静默把形态丢掉，写的人以为表态了形态其实没有。
            head = str(token).strip().lower().partition(":")[0].strip()
            if head not in OPENING_KINDS:
                raise ValueError(
                    f"立面槽位 {token!r} 不是合法开口：类型只能是 {'/'.join(OPENING_KINDS)}，"
                    "可写成 '<type>' 或 '<type>:<form>'"
                    "（empty=有墙无洞，open=开敞无墙，两者语义不同，别互相替代；"
                    "empty/open 不带形态）"
                )
            if head in {"empty", OPEN_SIDE} and ":" in str(token):
                raise ValueError(
                    f"立面槽位 {token!r} 不合法：{head} 表示"
                    f"{'有墙无洞' if head == 'empty' else '开敞无墙'}，不接受形态后缀"
                )
        if any(opening_kind(token) == OPEN_SIDE for token in value) and not all(opening_kind(token) == OPEN_SIDE for token in value):
            raise ValueError("当前只支持整面开敞：open 不可与门窗或 empty 混用")
        return value

    @model_validator(mode="after")
    def patterns_match_bays(self):
        if len(self.ground_pattern) != self.bays or len(self.upper_pattern) != self.bays:
            raise ValueError("立面 pattern 长度必须与 bays 相同")
        if any(opening_kind(token) == "door" for token in self.upper_pattern):
            raise ValueError("upper_pattern 不允许放置 door")
        if self.entrance_bay is not None and self.entrance_bay > self.bays:
            raise ValueError("entrance_bay 不能超出 bays")
        return self


class RoofVolumeOverride(ContractModel):
    """逐体量的屋顶覆盖（P5-A）。

    🔴 这里只放**引擎真能实现**的差异：屋顶形态与出檐。脊高不是决策项 ——
    它由 :func:`~app.agent.compiler.compile._apply_pitched_heights` 按每块自己的
    跨度算，写死会在多体量下失真。没写到的字段继承 :class:`RoofDecision` 的
    风格模板（默认与覆盖的优先级就写在这里）。
    """

    volume: str = Field(min_length=1, max_length=48, pattern=r"^[A-Za-z0-9_\-]+$")
    type: Literal["flat", "gable", "hip", "dome", "chinese_curved", "chinese_pagoda"] | None = None
    overhang: float | None = Field(default=None, ge=0, le=2)


class RoofDecision(ContractModel):
    """整栋屋顶的**风格模板** + 可选的逐体量覆盖。

    🔴 旧文档迁移等价：``volumes`` 为空 ⇒ 每个体量都用同一套模板，与引入本字段
    **之前**的产物逐字段相同（不凭空改变造型）。
    """

    type: Literal["flat", "gable", "hip", "dome", "chinese_curved", "chinese_pagoda"]
    ridge_axis: Literal["x", "z"] = "x"
    overhang: float = Field(default=0, ge=0, le=2)
    #: 逐体量覆盖。**不校验体量是否存在**：体量 id 的引用完整性由编译器判并记缺陷
    #: （契约层手里没有编译期铸造的命名空间，硬拼白名单必分叉）。
    volumes: list[RoofVolumeOverride] = Field(default_factory=list, max_length=8)


class ComponentQuota(ContractModel):
    min: int = Field(default=0, ge=0, le=10000)
    max: int = Field(default=0, ge=0, le=10000)
    note: str = Field(default="", max_length=300)
    type: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def maximum_is_not_below_minimum(self):
        if self.max < self.min:
            raise ValueError("component quota.max 不能小于 min")
        return self


class CurtainWallDecision(ContractModel):
    grid_strategy: Literal["floor_and_bay_aligned"] = "floor_and_bay_aligned"


class EnvelopeDecision(ContractModel):
    system: Literal["solid_wall", "curtain_wall"] = "solid_wall"
    curtain_wall: CurtainWallDecision | None = None

    @model_validator(mode="after")
    def selected_system_has_parameters(self):
        if self.system == "curtain_wall" and self.curtain_wall is None:
            raise ValueError("curtain_wall 系统必须提供 curtain_wall 参数")
        if self.system == "solid_wall" and self.curtain_wall is not None:
            raise ValueError("solid_wall 不允许携带 curtain_wall 参数")
        return self


class CirculationDecision(ContractModel):
    vertical_strategy: Literal["none", "stair", "core_and_stair"] = "stair"

    @field_validator("vertical_strategy", mode="before")
    @classmethod
    def migrate_core_only_strategy(cls, value: Any) -> Any:
        # 兼容已保存的旧 DesignDocument；核心筒本身不提供层间通行。
        return "core_and_stair" if value == "core" else value


#: 建筑侧材质角色名。与 `agent/generation/material/plan.py::ROLE_SPECS` 的键**一一对应**。
ArchitectureMaterialRoleName = Literal[
    "facade_primary", "structure", "floor", "frame", "door",
    "glass", "roof", "ground", "accent",
]

#: 物件侧材质角色名。与同文件的 `OBJECT_ROLE_SPECS` 的键**一一对应**——物件没有
#: "承重墙/楼板/龙骨"这类建筑语义，所以按材质本身命名（木/金属/玻璃/石/织物）。
#: 注意物件侧用 `metal` 而不是建筑侧的 `frame`（见 `material.plan._METALLIC_ROLES`）。
ObjectMaterialRoleName = Literal["wood", "metal", "glass", "stone", "fabric", "accent"]

#: 两者并集。`ResolvedMaterialPlan` 被建筑与物件**共用**（`decisions` 是带标签联合），
#: 所以角色名必须是并集。2026-09-23 之前这里只写了建筑侧，导致物件材质方案在
#: `resolver.attach_material_plan()` 里 `DesignDocument.model_validate` 直接
#: ValidationError（`wood/metal/stone/fabric` 四项全不认）——桩件测试全绿也照样炸，
#: 因为端到端测试把 `material_planner` 整个替换掉了。
#: 两张角色表的键必须落在这里：`tests/design/test_material_role_names.py` 逐键比对。
MaterialRoleName = Literal[
    "facade_primary", "structure", "floor", "frame", "door",
    "glass", "roof", "ground", "accent",
    "wood", "metal", "stone", "fabric",
]


class ResolvedMaterialRole(ContractModel):
    role: MaterialRoleName
    materialId: str = Field(min_length=1, max_length=80)
    assetId: str | None = Field(default=None, max_length=200)
    proceduralPresetId: str | None = Field(default=None, max_length=120)
    material: dict[str, Any]


class ResolvedMaterialPlan(ContractModel):
    concept: str = Field(default="", max_length=160)
    palette: list[str] = Field(default_factory=list, max_length=5)
    roles: list[ResolvedMaterialRole] = Field(default_factory=list, max_length=20)
    resolvedAssets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rejectedAssetIds: list[str] = Field(default_factory=list)
    rejectedProceduralPresetIds: list[str] = Field(default_factory=list)
    curtainWall: bool = False

    @model_validator(mode="after")
    def material_roles_are_unique(self):
        roles = [item.role for item in self.roles]
        material_ids = [item.materialId for item in self.roles]
        if len(roles) != len(set(roles)):
            raise ValueError("材质方案 role 不能重复")
        if len(material_ids) != len(set(material_ids)):
            raise ValueError("材质方案 materialId 不能重复")
        return self


class MaterialRegion(ContractModel):
    """区域/构件级材质绑定（P5-C）。

    🔴 **只做最小表达**：一条绑定 = "**这一类实体**用这个材质角色"。
    ``type`` 是**目标实体类型**（构件类 ``balcony`` / ``railing`` / ``canopy``…，
    或元素类 ``wall`` / ``floor`` / ``roof`` / ``column``），``role`` 是材质方案里
    的角色名。落点因此是"按类型换引用"，不是"按区域函数/坐标刷"——
    后者是渲染器的事，不是设计决策。

    角色名**不校验**是什么闭集：材质方案（:class:`ResolvedMaterialPlan`）才是闭集，
    引用不存在的角色由编译器记缺陷（只标记不阻断，材质分区写错不该让墙消失）。
    """

    role: str = Field(min_length=1, max_length=60)
    type: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=200)


class MaterialIntent(ContractModel):
    keywords: list[str] = Field(default_factory=list, max_length=20)
    resolved_plan: ResolvedMaterialPlan | None = None
    #: 区域/构件材质绑定（P5-C）。空列表 ⇒ 全部按类型默认角色，与引入前逐字段一致。
    regions: list[MaterialRegion] = Field(default_factory=list, max_length=20)


class SupportRelation(ContractModel):
    kind: Literal["supports"] = "supports"
    target: str = Field(min_length=1, max_length=80, description="目标雨棚的稳定实例 ID 或实体 ID")
    along_ratio: float = Field(ge=0, le=1, description="沿宿主墙方向的雨棚宽度比例")
    depth_ratio: float = Field(ge=0, le=1, description="从墙外表面向外的雨棚出挑比例")


class ComponentInstance(ContractModel):
    """
    统一的实例描述，取代散落的 balcony_access_count / balcony_width 等字段。
    抽象（立面轴网）与显式（实例清单）并存：轴网为主、实例为例外。
    """
    
    type: str = Field(min_length=1, max_length=60)
    id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    relation: SupportRelation | None = None
    #: 宿主语义id：体量(volume_primary) / 墙(wall_front_01) / 槽位(slot_front_02) /
    #: 开口(door_front_01) / 屋面(roof_01、`<volume_id>`)。**不做解析校验**——
    #: 解析唯一的实现在编译器，认不出就记 `dropped`（见 `_validate_component_instances`）。
    host: str = Field(min_length=1, max_length=80)
    #: 相对宿主的尺寸（逐类型字段不同）
    size: dict[str, float] = Field(default_factory=dict)
    #: 形态参数（逐类型闭集，来自schema）
    form: dict[str, Any] = Field(default_factory=dict)
    #: 材质角色名
    material_role: MaterialRoleName | None = None

    @model_validator(mode="after")
    def relation_is_supported(self):
        if self.relation is not None and self.type != "column":
            raise ValueError("当前 supports 关系仅支持 column → canopy")
        return self


class ArchitectureIntent(ContractModel):
    """审核前的整体设计方向；不冒充已编译几何或专业规范结论。"""

    goals: list[str] = Field(default_factory=list, max_length=8)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    spatial_strategy: str = Field(default="", max_length=800)
    composition: str = Field(default="", max_length=800)
    material_strategy: str = Field(default="", max_length=800)
    selected_systems: list[str] = Field(default_factory=list, max_length=12)


class ArchitectureDecisions(ContractModel):
    #: 判别字段。与 `ObjectDecisions.kind` 一起构成 `decisions` 的带标签联合。
    #: 有默认值是为了让 2026-09-23 之前存档的 DesignDocument（当时只有建筑一种）
    #: 仍然可读——见 `DesignDocument._default_decisions_kind`。
    kind: Literal["architecture"] = "architecture"
    concept: str = Field(default="", max_length=240)
    massing: MassingDecision
    complexity: ComplexityDecision
    volumes: list[VolumeDecision] = Field(min_length=1, max_length=8)
    structural_grid: StructuralGridDecision
    envelope: EnvelopeDecision
    facades: dict[Literal["front", "back", "left", "right"], FacadeDecision]
    roof: RoofDecision
    circulation: CirculationDecision = Field(default_factory=CirculationDecision)
    materials: MaterialIntent = Field(default_factory=MaterialIntent)
    detail_packages: list[str] = Field(default_factory=list, max_length=20)
    component_quota: dict[str, ComponentQuota] = Field(default_factory=dict)
    #为空时回退到 component_quota 配额模式。
    components: list[ComponentInstance] = Field(default_factory=list, max_length=100)
    balcony_access_count: int = Field(default=0, ge=0, le=32)
    balcony_width: float | None = Field(default=None, ge=0.8, le=6)
    required_components: list[str] = Field(default_factory=list, max_length=30)
    unsupported_component_types: list[str] = Field(default_factory=list, max_length=30)
    design_rationale: list[str] = Field(default_factory=list, max_length=12)
    design_intent: ArchitectureIntent | None = None


class ComponentObject(ContractModel):
    """物件场景里的一个待生成物件。

    只描述"做几个、多大、怎么摆"，不描述几何——几何由构件生成节点按 KB 契约产出。
    没有 `parentWall` 之类的宿主字段：这类构件本就无宿主（见 KB《家具参数契约》）。

    `kind` 是**表达通道**，取值见 `generation.objects.subtypes.OBJECT_COMPONENT_KINDS`：

    - ``furniture`` —— 图鉴预设：`subtype` 取 `FURNITURE_SUBTYPES` 的 key，引擎有
      逐子类型的原生 builder，几何最精确；
    - ``primitive`` —— 通用几何组合：形状由 `parts` 给出（每项一份 primitive 参数，
      坐标是相对**物件底面中心**的局部坐标）。这是**开放集出口**：任何名字
      （小人、花瓶、路灯、机器人）都从这里产出；
    - ``body`` —— 引擎的简化人物元素：形状参数在 `params`（KB《构件参数》§十）。

    `name` 是用户点名的原始名词，保留它是为了两件事：去重键里区分同通道的不同物件
    （"花瓶"和"路灯"都是 `primitive` 且都没有 subtype），以及让生成节点写出可读的 id。
    """

    kind: str = Field(min_length=1, max_length=60)
    subtype: str = Field(default="", max_length=60)
    #: 用户点名的原始名词（"桌子"/"小人"/"花瓶"）。预设通道可为空。
    name: str = Field(default="", max_length=60)
    count: int = Field(default=1, ge=1, le=64)
    width: float = Field(gt=0, le=50)
    depth: float = Field(gt=0, le=50)
    height: float = Field(gt=0, le=50)
    #: `kind=primitive` 的零件表。每项是一份 WILD `primitive` 参数（shape + 几何参数 +
    #: 局部 position/rotation），**不做业务语义解释**——它就是要交付的几何。
    parts: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    #: `kind` 专属参数（目前只有 `body` 用：build / headShape / armLength / legLength /
    #: cloakLength / hoodUp）。用开放 dict 而不是逐字段建模，是因为新增一条通道时
    #: 不该再改一次契约——但**白名单仍在**：生成节点的 schema 校验会逐字段把关。
    params: dict[str, Any] = Field(default_factory=dict)
    #: 摆位说明（自然语言约束，例如"四把围在长边两侧、面向桌面"）。
    #: 坐标最终由构件生成节点按行走面标高算出，方案层不写死世界坐标。
    placement: str = Field(default="", max_length=300)
    material: str = Field(default="", max_length=80)
    rationale: str = Field(default="", max_length=300)


class ObjectDecisions(ContractModel):
    """物件场景的设计决策：没有体量、没有立面，只有物件清单与材质。

    这是"建筑只是一类目标"在契约层的落地——只要交付物不是建筑，就不该被强行
    塞进 `massing`。它不带 `massing`/`volumes`/`facades`/`roof`，因此**结构上**
    不可能产出住宅替代方案。

    `objects` 可以是空的，但**只有**在 `unsupported_objects` 非空时才成立（见
    `_object_semantics_are_valid`）：那表示"用户点名的东西这次表达不出来"。
    允许这种状态是为了**不静默替换**——把"小人"做成一张桌子比如实报做不了更糟。
    """

    kind: Literal["object"] = "object"
    concept: str = Field(default="", max_length=240)
    objects: list[ComponentObject] = Field(default_factory=list, max_length=24)
    #: 点名了、但本次表达不出可生成几何的物件。
    #: 它进交付清单作为**非阻断**提示。
    unsupported_objects: list[str] = Field(default_factory=list, max_length=24)
    materials: MaterialIntent = Field(default_factory=MaterialIntent)
    design_rationale: list[str] = Field(default_factory=list, max_length=12)


class DesignConstraint(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    kind: Literal["user_hard", "engine_hard", "system_required", "preference", "reference"]
    target: str = Field(min_length=1, max_length=240)
    expression: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="", max_length=500)
    expected: Any = None
    check: Literal["equals", "contains", "minimum", "absent", "manual"] = "manual"
    adoption: Literal["adopted", "proposed", "superseded"] = "adopted"
    source_quote: str = Field(default="", max_length=1000)
    supersedes: str | None = None


class RuleTrace(ContractModel):
    rule_id: str = Field(min_length=1, max_length=160)
    classification: Literal["engine_hard", "conditional", "preference", "reference", "unsupported"]
    applies_when: str = Field(default="", max_length=500)
    schema_targets: list[str] = Field(default_factory=list, max_length=20)
    enforcement: list[Literal["schema", "planner", "resolver", "compiler", "validator", "none"]]
    source: str = Field(default="", max_length=500)
    # Field-level diagnostic evidence, never input for compilation.
    changes: list[dict[str, Any]] = Field(default_factory=list)
    design_revision: int | None = None


#: `decisions` 的带标签联合。标签是两边都有的 `kind`，所以解析不需要猜：
#: 有 `massing` 的那支只能解析成 ArchitectureDecisions，反之亦然。
DesignDecisions = Annotated[
    ArchitectureDecisions | ObjectDecisions,
    Field(discriminator="kind"),
]


class DesignDocument(ContractModel):
    schema_version: Literal["design/1.0", "design/1.1", "design/1.2", "design/1.3"] = "design/1.3"
    design_id: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)
    status: Literal["draft", "approved", "compiled"] = "draft"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    approved_at: str | None = None
    requirements: DesignRequirements
    decisions: DesignDecisions
    constraints: list[DesignConstraint] = Field(default_factory=list, max_length=100)
    locks: list[str] = Field(default_factory=list, max_length=100)
    rule_trace: list[RuleTrace] = Field(default_factory=list, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _default_decisions_kind(cls, data: Any) -> Any:
        """让 2026-09-23 之前存档的设计文档继续可读。

        那时 `decisions` 只可能是建筑方案，但存档里没有 `kind` 字段；带标签联合
        要求标签必须存在，缺了会直接 ValidationError。这里在解析前补上默认标签，
        而不是给联合放宽成"猜类型"——猜错会静默把建筑读成物件，那更糟。
        """

        if not isinstance(data, dict):
            return data
        if data.get("schema_version") == "design/1.0":
            from copy import deepcopy
            data = deepcopy(data)
            migration_changes = []
            decisions = data.get("decisions")
            facades = decisions.get("facades") if isinstance(decisions, dict) else None
            for face, facade in (facades.items() if isinstance(facades, dict) else []):
                if not isinstance(facade, dict):
                    continue
                for key in ("ground_pattern", "upper_pattern"):
                    pattern = facade.get(key)
                    if isinstance(pattern, list) and pattern and all(token == "empty" for token in pattern):
                        facade[key] = ["open"] * len(pattern)
                        migration_changes.append({"path": f"/decisions/facades/{face}/{key}",
                                                  "before": pattern, "after": facade[key],
                                                  "semantic_change": False, "source": "legacy_schema"})
            data["schema_version"] = "design/1.1"
            if migration_changes and isinstance(data.get("rule_trace", []), list):
                data.setdefault("rule_trace", []).append({
                    "rule_id": "schema.facade_open_migration", "classification": "reference",
                    "enforcement": ["schema"], "source": "design/1.0 → design/1.1",
                    "changes": migration_changes, "design_revision": data.get("revision", 1),
                })
        decisions = data.get("decisions")
        if isinstance(decisions, dict) and not decisions.get("kind"):
            return {**data, "decisions": {**decisions, "kind": "architecture"}}
        return data

    @model_validator(mode="after")
    def design_semantics_are_valid(self):
        if isinstance(self.decisions, ObjectDecisions):
            return self._object_semantics_are_valid()
        return self._architecture_semantics_are_valid()

    def _object_semantics_are_valid(self):
        """物件场景的不变量：无体量、无立面，只有物件与材质。"""

        decisions = self.decisions
        assert isinstance(decisions, ObjectDecisions)
        if not decisions.objects and not decisions.unsupported_objects:
            raise ValueError(
                "物件方案必须至少给出一条 objects，或用 unsupported_objects 如实说明"
                "哪些物件本次表达不出来；两者同时为空等于没有方案"
            )
        seen: set[tuple[str, str, str]] = set()
        for item in decisions.objects:
            # 去重键含 name：通用几何与人物通道的 subtype 是空串，
            # 只用 (kind, subtype) 会把"花瓶"和"路灯"折成同一条。
            key = (item.kind, item.subtype, item.name)
            if key in seen:
                raise ValueError(
                    f"重复的物件条目 {item.kind}/{item.subtype or item.name or '-'}；"
                    "同类物件请用 count 表达数量，不要重复列出"
                )
            seen.add(key)
        return self

    def _architecture_semantics_are_valid(self):
        decisions = self.decisions
        assert isinstance(decisions, ArchitectureDecisions)
        massing = decisions.massing
        if massing.representation_mode == "full" and massing.modeled_floors != massing.floors:
            raise ValueError("full 模式必须让 modeled_floors 等于 floors")
        if massing.modeled_floors > 1 and decisions.circulation.vertical_strategy == "none":
            raise ValueError("多层建筑必须选择竖向交通策略")
        if (
            decisions.circulation.vertical_strategy == "core_and_stair"
            and min(massing.width, massing.depth) < 4
        ):
            raise ValueError("核心筒策略要求体量宽度和进深均不小于 4m")
        seen: set[str] = set()
        for volume in decisions.volumes:
            if volume.id in seen:
                raise ValueError(f"重复 volume id: {volume.id}")
            seen.add(volume.id)
            if volume.end_floor > massing.modeled_floors:
                raise ValueError(f"volume {volume.id} 超出 modeled_floors")
        from .coordinates import DesignCoordinateConflict, volume_conflicts
        conflicts = volume_conflicts([v.model_dump(mode="json") for v in decisions.volumes],
                                    massing.model_dump(mode="json"))
        if conflicts:
            raise DesignCoordinateConflict(conflicts)
        for floor in range(1, massing.modeled_floors + 1):
            if not any(volume.start_floor <= floor <= volume.end_floor for volume in decisions.volumes):
                raise ValueError(f"第 {floor} 建模层没有任何 volume 覆盖")
        required_faces = {"front", "back", "left", "right"}
        if set(decisions.facades) != required_faces:
            raise ValueError("facades 必须完整包含 front/back/left/right")
        opening_counts = {"door": 0, "window": 0}
        for facade in decisions.facades.values():
            for opening in facade.ground_pattern:
                kind = opening_kind(opening)
                if kind in opening_counts:
                    opening_counts[kind] += 1
            for opening in facade.upper_pattern:
                kind = opening_kind(opening)
                if kind in opening_counts:
                    opening_counts[kind] += massing.modeled_floors - 1
        for opening, count in opening_counts.items():
            quota = decisions.component_quota.get(opening)
            if quota is not None and count < quota.min:
                raise ValueError(
                    f"{opening} 立面槽位数量 {count} 少于配额下限 {quota.min}"
                )
        required = set(decisions.required_components)
        for component, quota in decisions.component_quota.items():
            if quota.min > 0 and component not in required:
                raise ValueError(f"配额要求的构件 {component} 未列入 required_components")
        
        # 校验构件实例清单（§3.4）
        instance_ids = [c.id for c in decisions.components if c.id]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("构件实例 id 必须唯一，不能把同一实体用于多条关系")
        if decisions.components:
            self._validate_component_instances(decisions)
        
        return self
    
    def _validate_component_instances(self, decisions: ArchitectureDecisions):
        """校验构件实例清单的语义约束。

         **这里不判 host 能否解析**（2026-10-08 事故，第二例）。原先的做法是按
        注释里"假设格式"拼一份 `valid_hosts`，再加一道
        ``["wall_", "volume_", "slot_", "door_", "window_"]`` 前缀白名单。它两个
        方向都不对：

        - **拦不住真正悬空的引用** —— `wall_随便写` 只要带对前缀就放行；
        - **把编译器自铸的合法宿主全拒掉** —— `roof_planned_01`、`roof_01`
          一个前缀都对不上。现场：中式别墅给 `cornice` 写实例、
          host=`main_L2_roof`（体量 `main` 顶层屋面），契约直接抛错 ⇒
          `architecture` 节点 `status=failed` ⇒ **整轮生成中止**；而编译器那边
          只是把这条实例记进 `dropped` 就继续了 —— 契约比编译器严，且严在
          它自己判不了的事情上。

        host 的命名空间有一半是**编译期才铸出来**的（骨架墙 `wall_*`、槽位
        `slot_*`、开口 `door_*`/`window_*`、屋面 `roof_01`/`roof_planned_NN`、
        檐口 `cornice_*`…），契约层手里只有体量/立面，**构造不出**这份名单；
        硬拼一份就必然与编译器分叉。⇒ **解析只有一个实现：编译器**
        （``compiler.compile._compile_from_instances``，宿主解析规则集中在
        :func:`_opening_expression` 与屋顶宿主解析）。它认不出宿主就把实例记进
        `stats.instance_overrides.dropped`、配额点名而零产出的类型另记
        `uncompiled`，两者都进 `compile_report` 交修复环 —— 这才是
        "图纸有问题只标记不阻断"该有的样子。

        契约层只保留**它自己就能判**的东西：尺寸合理性、材质角色落点。
        """

        for idx, instance in enumerate(decisions.components):
            # size必须合理
            if instance.size:
                for key, value in instance.size.items():
                    if not isinstance(value, (int, float)) or value <= 0:
                        raise ValueError(
                            f"构件实例 {idx} 的 size.{key} 必须是正数"
                        )
                    # 尺寸上限检查
                    if value > 100:
                        raise ValueError(
                            f"构件实例 {idx} 的 size.{key}={value} 超出合理范围(0-100m)"
                        )
            
            # material_role 必须在材质方案里有落点。**判据与编译器同源**
            # （`compile._material_name_for_role`）：角色名与方案里的 `materialId` 都算
            # —— 编译器本来就认后者（`if role in known: return role`），只认角色名会造出
            # 一道连编译器都不需要的硬闸。2026-10-08 实测：玻璃幕墙场景模型写 `metal`
            # （材质名）而不是 `frame`（角色名），撞上这道闸即 `ValidationError`。
            if instance.material_role:
                if decisions.materials.resolved_plan:
                    plan_roles = decisions.materials.resolved_plan.roles
                    accepted = {item.role for item in plan_roles} | {
                        item.materialId for item in plan_roles
                    }
                    if instance.material_role not in accepted:
                        raise ValueError(
                            f"构件实例 {idx} 的 material_role '{instance.material_role}' "
                            f"不在材质方案中"
                        )


class DesignPatchOperation(ContractModel):
    op: Literal["add", "replace", "remove"]
    path: str = Field(min_length=1, max_length=500, pattern=r"^/")
    value: Any = None


class DesignPatch(ContractModel):
    type: Literal["design_patch"] = "design_patch"
    patch_id: str = Field(min_length=1, max_length=160)
    base_revision: int = Field(ge=1)
    source: Literal["user", "agent", "system"] = "user"
    operations: list[DesignPatchOperation] = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=500)


class ResolvedLevel(ContractModel):
    index: int = Field(ge=1)
    base_y: float
    top_y: float


class DesignGap(ContractModel):
    id: str
    constraint_id: str
    layer: Literal["design", "implementation", "execution"] = "design"
    status: Literal["satisfied", "open", "needs_review", "unsupported"]
    design_hash: str
    target: str
    expected: Any = None
    actual: Any = None
    evidence: str


class ResolvedFacadeSlot(ContractModel):
    id: str
    facing: Literal["front", "back", "left", "right"]
    floor: int = Field(ge=1)
    bay: int = Field(ge=1)
    type: Literal["door", "window", "bay_window"]
    parent_wall: str = ""
    local_from: list[float] = Field(default_factory=list)
    world_from: list[float] = Field(default_factory=list)
    world_to: list[float] = Field(default_factory=list)
    offset: float
    width: float = Field(gt=0)
    bottom: float = Field(ge=0)
    height: float = Field(gt=0)


class ResolvedDesign(ContractModel):
    schema_version: Literal["resolved-design/1.0"] = "resolved-design/1.0"
    design_id: str
    design_revision: int = Field(ge=1)
    design_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    resolver_version: str = "legacy"
    projection_elements: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    design_gaps: list[DesignGap] = Field(default_factory=list)
    compile_blockers: list[dict[str, Any]] = Field(default_factory=list)
    bounds: dict[Literal["width", "depth", "height"], float]
    levels: list[ResolvedLevel]
    volumes: list[VolumeDecision]
    facade_slots: list[ResolvedFacadeSlot]
    component_quantities: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
