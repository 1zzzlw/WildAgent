"""DesignDocument v1 的唯一后端类型定义。

JSON Schema、REST 校验、LangGraph 状态和前端类型都以这里的字段语义为准。
Blueprint 是编译产物，不反向充当建筑方案。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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


MaterialRoleName = Literal[
    "facade_primary", "structure", "floor", "frame", "door",
    "glass", "roof", "ground", "accent",
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
    decisions: ArchitectureDecisions
    constraints: list[DesignConstraint] = Field(default_factory=list, max_length=100)
    locks: list[str] = Field(default_factory=list, max_length=100)
    rule_trace: list[RuleTrace] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def design_semantics_are_valid(self):
        massing = self.decisions.massing
        if massing.representation_mode == "full" and massing.modeled_floors != massing.floors:
            raise ValueError("full 模式必须让 modeled_floors 等于 floors")
        if massing.modeled_floors > 1 and self.decisions.circulation.vertical_strategy == "none":
            raise ValueError("多层建筑必须选择竖向交通策略")
        if (
            self.decisions.circulation.vertical_strategy == "core_and_stair"
            and min(massing.width, massing.depth) < 4
        ):
            raise ValueError("核心筒策略要求体量宽度和进深均不小于 4m")
        seen: set[str] = set()
        for volume in self.decisions.volumes:
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
            if not any(volume.start_floor <= floor <= volume.end_floor for volume in self.decisions.volumes):
                raise ValueError(f"第 {floor} 建模层没有任何 volume 覆盖")
        required_faces = {"front", "back", "left", "right"}
        if set(self.decisions.facades) != required_faces:
            raise ValueError("facades 必须完整包含 front/back/left/right")
        opening_counts = {"door": 0, "window": 0}
        for facade in self.decisions.facades.values():
            for opening in facade.ground_pattern:
                if opening in opening_counts:
                    opening_counts[opening] += 1
            for opening in facade.upper_pattern:
                if opening in opening_counts:
                    opening_counts[opening] += massing.modeled_floors - 1
        for opening, count in opening_counts.items():
            quota = self.decisions.component_quota.get(opening)
            if quota is not None and not quota.min <= count <= quota.max:
                raise ValueError(
                    f"{opening} 立面槽位数量 {count} 不在配额 {quota.min}~{quota.max} 内"
                )
        required = set(self.decisions.required_components)
        for component, quota in self.decisions.component_quota.items():
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
