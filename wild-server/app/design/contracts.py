"""DesignDocument v1 的唯一后端类型定义。

JSON Schema、REST 校验、LangGraph 状态和前端类型都以这里的字段语义为准。
Blueprint 是编译产物，不反向充当建筑方案。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DesignRequirements(ContractModel):
    source_request: str = Field(min_length=1, max_length=8000)
    building_type: str = Field(default="building", min_length=1, max_length=80)
    profile: str = Field(default="residential_lowrise", min_length=1, max_length=80)
    style_intent: list[str] = Field(default_factory=list, max_length=12)


class ComplexityDecision(ContractModel):
    level: Literal["minimal", "simple", "standard", "detailed"] = "standard"
    min_volumes: int = Field(default=1, ge=1, le=8)
    min_detail_packages: int = Field(default=0, ge=0, le=12)
    target_structural_elements: int = Field(default=10, ge=1, le=1000)
    grid_bays: tuple[int, int] = Field(default=(2, 2))
    reason: str = Field(default="", max_length=300)


class MassingDecision(ContractModel):
    shape: str = Field(min_length=1, max_length=40)
    width: float = Field(gt=0, le=500)
    depth: float = Field(gt=0, le=500)
    floors: int = Field(ge=1, le=200)
    modeled_floors: int = Field(ge=1, le=200)
    representation_mode: Literal["full", "schematic"] = "full"
    floor_height: float = Field(gt=0.5, le=20)
    symmetry: bool = False

    @model_validator(mode="after")
    def modeled_floor_count_is_valid(self):
        if self.modeled_floors > self.floors:
            raise ValueError("modeled_floors 不能大于 floors")
        return self


class VolumeDecision(ContractModel):
    id: str = Field(min_length=1, max_length=48, pattern=r"^[A-Za-z0-9_\-]+$")
    role: Literal["primary", "secondary"] = "primary"
    x: float = Field(ge=0, le=500)
    z: float = Field(ge=0, le=500)
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


OpeningKind = Literal["door", "window", "empty"]


class FacadeDecision(ContractModel):
    bays: int = Field(ge=1, le=32)
    entrance_bay: int | None = Field(default=None, ge=1, le=32)
    ground_pattern: list[OpeningKind]
    upper_pattern: list[OpeningKind]

    @model_validator(mode="after")
    def patterns_match_bays(self):
        if len(self.ground_pattern) != self.bays or len(self.upper_pattern) != self.bays:
            raise ValueError("立面 pattern 长度必须与 bays 相同")
        if "door" in self.upper_pattern:
            raise ValueError("upper_pattern 不允许放置 door")
        if self.entrance_bay is not None and self.entrance_bay > self.bays:
            raise ValueError("entrance_bay 不能超出 bays")
        return self


class RoofDecision(ContractModel):
    type: Literal["flat", "gable", "hip", "dome", "chinese_curved", "chinese_pagoda"]
    ridge_axis: Literal["x", "z"] = "x"
    overhang: float = Field(default=0, ge=0, le=2)


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


#: 建筑侧材质角色名。与 `agent/generation/material_plan.py::ROLE_SPECS` 的键**一一对应**。
ArchitectureMaterialRoleName = Literal[
    "facade_primary", "structure", "floor", "frame", "door",
    "glass", "roof", "ground", "accent",
]

#: 物件侧材质角色名。与同文件的 `OBJECT_ROLE_SPECS` 的键**一一对应**——物件没有
#: "承重墙/楼板/龙骨"这类建筑语义，所以按材质本身命名（木/金属/玻璃/石/织物）。
#: 注意物件侧用 `metal` 而不是建筑侧的 `frame`（见 `material_plan._METALLIC_ROLES`）。
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


class MaterialIntent(ContractModel):
    keywords: list[str] = Field(default_factory=list, max_length=20)
    resolved_plan: ResolvedMaterialPlan | None = None


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
    balcony_access_count: int = Field(default=0, ge=0, le=32)
    balcony_width: float | None = Field(default=None, ge=0.8, le=6)
    required_components: list[str] = Field(default_factory=list, max_length=30)
    unsupported_component_types: list[str] = Field(default_factory=list, max_length=30)
    design_rationale: list[str] = Field(default_factory=list, max_length=12)


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
    #: 点名了、但本次表达不出可生成几何的物件（用需求原文片段表示）。
    #: 它进交付清单作为**非阻断**提示（与《动态节点设计规划》§8.1 同口径）。
    unsupported_objects: list[str] = Field(default_factory=list, max_length=24)
    materials: MaterialIntent = Field(default_factory=MaterialIntent)
    design_rationale: list[str] = Field(default_factory=list, max_length=12)


class DesignConstraint(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    kind: Literal["user_hard", "engine_hard", "system_required", "preference", "reference"]
    target: str = Field(min_length=1, max_length=240)
    expression: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="", max_length=500)


class RuleTrace(ContractModel):
    rule_id: str = Field(min_length=1, max_length=160)
    classification: Literal["engine_hard", "conditional", "preference", "reference", "unsupported"]
    applies_when: str = Field(default="", max_length=500)
    schema_targets: list[str] = Field(default_factory=list, max_length=20)
    enforcement: list[Literal["schema", "planner", "resolver", "compiler", "validator", "none"]]
    source: str = Field(default="", max_length=500)


#: `decisions` 的带标签联合。标签是两边都有的 `kind`，所以解析不需要猜：
#: 有 `massing` 的那支只能解析成 ArchitectureDecisions，反之亦然。
DesignDecisions = Annotated[
    ArchitectureDecisions | ObjectDecisions,
    Field(discriminator="kind"),
]


class DesignDocument(ContractModel):
    schema_version: Literal["design/1.0"] = "design/1.0"
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
            if volume.x + volume.width > massing.width + 1e-6:
                raise ValueError(f"volume {volume.id} 超出 massing.width")
            if volume.z + volume.depth > massing.depth + 1e-6:
                raise ValueError(f"volume {volume.id} 超出 massing.depth")
            if volume.end_floor > massing.modeled_floors:
                raise ValueError(f"volume {volume.id} 超出 modeled_floors")
        for floor in range(1, massing.modeled_floors + 1):
            if not any(volume.start_floor <= floor <= volume.end_floor for volume in decisions.volumes):
                raise ValueError(f"第 {floor} 建模层没有任何 volume 覆盖")
        required_faces = {"front", "back", "left", "right"}
        if set(decisions.facades) != required_faces:
            raise ValueError("facades 必须完整包含 front/back/left/right")
        opening_counts = {"door": 0, "window": 0}
        for facade in decisions.facades.values():
            for opening in facade.ground_pattern:
                if opening in opening_counts:
                    opening_counts[opening] += 1
            for opening in facade.upper_pattern:
                if opening in opening_counts:
                    opening_counts[opening] += massing.modeled_floors - 1
        for opening, count in opening_counts.items():
            quota = decisions.component_quota.get(opening)
            if quota is not None and not quota.min <= count <= quota.max:
                raise ValueError(
                    f"{opening} 立面槽位数量 {count} 不在配额 {quota.min}~{quota.max} 内"
                )
        required = set(decisions.required_components)
        for component, quota in decisions.component_quota.items():
            if quota.min > 0 and component not in required:
                raise ValueError(f"配额要求的构件 {component} 未列入 required_components")
        return self


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


class ResolvedFacadeSlot(ContractModel):
    id: str
    facing: Literal["front", "back", "left", "right"]
    floor: int = Field(ge=1)
    bay: int = Field(ge=1)
    type: Literal["door", "window"]
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    bottom: float = Field(ge=0)
    height: float = Field(gt=0)


class ResolvedDesign(ContractModel):
    schema_version: Literal["resolved-design/1.0"] = "resolved-design/1.0"
    design_id: str
    design_revision: int = Field(ge=1)
    design_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    bounds: dict[Literal["width", "depth", "height"], float]
    levels: list[ResolvedLevel]
    volumes: list[VolumeDecision]
    facade_slots: list[ResolvedFacadeSlot]
    component_quantities: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
