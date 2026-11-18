"""DesignDocument v1 的唯一后端类型定义。

JSON Schema、REST 校验、LangGraph 状态和前端类型都以这里的字段语义为准。
Blueprint 是编译产物，不反向充当建筑方案。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.design.spatial_contracts import (
    ClearancePath,
    ConstructionSystem,
    CoordinateSystem,
    DesignFloorLayout,
    DesignLevel,
    DesignProfile,
    DesignRelation,
    RequiredConnection,
    DesignRoof,
    DesignSlab,
    DesignVoid,
    DesignWall,
    ElevationReference,
    VolumeGeometry,
    VolumePlacement,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def architecture_output_schema() -> dict:
    """从正式契约导出新方案的输出规则；历史字段只用于读取，不再提示模型生成。"""
    schema = ArchitectureDecisions.model_json_schema()
    hidden = {
        "": {
            "facades",
            "roof",
            "curtain_wall",
            "complexity",
            "component_quota",
            "balcony_access_count",
            "balcony_width",
            "required_components",
            "unsupported_component_types",
        },
        "MassingDecision": {"tiers"},
        "MaterialIntent": {"resolved_plan"},
        "ComponentInstance": {"relation"},
        "VolumeDecision": {
            "x",
            "z",
            "width",
            "depth",
            "start_floor",
            "end_floor",
            "facades",
        },
        "ComponentPlacement": {"face", "floor", "sill_height"},
        "FloorConnection": {"from_floor", "to_floor"},
        "DesignFloorLayout": {"floor", "walls"},
        "DesignRoom": {"bounds", "void"},
    }
    for name, fields in hidden.items():
        node = schema["$defs"][name] if name else schema
        for field in fields:
            node.get("properties", {}).pop(field, None)
        node["required"] = [
            key for key in node.get("required", []) if key not in fields
        ]
    schema["$defs"]["DesignFloorLayout"]["properties"]["level"] = {
        "type": "string",
        "description": "levels中的稳定楼面ID",
    }
    for name, required in (
        ("VolumeDecision", ["id", "placement", "geometry"]),
        ("DesignFloorLayout", ["level", "rooms"]),
        ("DesignRoom", ["id", "region"]),
        ("FloorConnection", ["from_level", "to_level"]),
    ):
        schema["$defs"][name]["required"] = required
    schema["required"] = list(
        dict.fromkeys([*schema["required"], "levels", "profiles"])
    )
    # 删除仅由历史字段引入的定义，避免提示词保留两套空间规则。
    used = set()

    def collect(value):
        if isinstance(value, dict):
            value.pop("title", None)
            reference = value.get("$ref", "")
            if reference.startswith("#/$defs/"):
                name = reference.removeprefix("#/$defs/")
                if name not in used:
                    used.add(name)
                    collect(schema["$defs"][name])
            for key, item in value.items():
                if key != "$defs":
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(schema)
    schema["$defs"] = {
        name: value for name, value in schema["$defs"].items() if name in used
    }
    return schema


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

    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    floors: int = Field(ge=1)
    width_ratio: float = Field(gt=0)
    depth_ratio: float = Field(default=1.0, gt=0)


class MassingDecision(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    shape: str = Field(min_length=1)
    width: float = Field(
        gt=0, description="总体 X 方向尺寸控制上限（米），无世界原点边界"
    )
    depth: float = Field(
        gt=0, description="总体 Z 方向尺寸控制上限（米），实际包络由 volumes 决定"
    )
    floors: int = Field(ge=1)
    modeled_floors: int = Field(ge=1)
    representation_mode: Literal["full", "schematic"] = "full"
    floor_height: float = Field(gt=0)
    symmetry: bool = False
    #: 立面轮廓表态（可选）：从底到顶逐段的收放。电视塔、宝塔、阶梯收分的
    #: 高层用它表达轮廓；不写 = 交给下游从 volumes/shape 派生。
    tiers: list[MassingTierDecision] | None = Field(default=None)

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
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")
    role: str = "primary"
    placement: VolumePlacement | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    geometry: VolumeGeometry | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    x: float | None = Field(
        default=None,
        allow_inf_nan=False,
        exclude_if=lambda value: value is None,
        description="历史矩形体量起点；新图纸使用 placement/geometry",
    )
    z: float | None = Field(
        default=None, allow_inf_nan=False, exclude_if=lambda value: value is None
    )
    width: float | None = Field(
        default=None, gt=0, exclude_if=lambda value: value is None
    )
    depth: float | None = Field(
        default=None, gt=0, exclude_if=lambda value: value is None
    )
    start_floor: int | None = Field(
        default=None, ge=1, exclude_if=lambda value: value is None
    )
    end_floor: int | None = Field(
        default=None, ge=1, exclude_if=lambda value: value is None
    )
    facades: dict[Literal["front", "back", "left", "right"], FacadeDecision] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def floor_range_is_valid(self):
        if self.geometry is not None:
            if self.placement is None:
                raise ValueError("几何体量必须明确 placement")
            if any(
                value is not None
                for value in (
                    self.x,
                    self.z,
                    self.width,
                    self.depth,
                    self.start_floor,
                    self.end_floor,
                )
            ):
                raise ValueError("不能同时声明 geometry 和历史矩形体量字段")
            return self
        if any(
            value is None
            for value in (
                self.x,
                self.z,
                self.width,
                self.depth,
                self.start_floor,
                self.end_floor,
            )
        ):
            raise ValueError("体量必须给出 placement/geometry，或完整历史矩形字段")
        if self.end_floor < self.start_floor:
            raise ValueError("volume.end_floor 不能小于 start_floor")
        return self


class StructuralGridDecision(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    system: str
    x_bays: int = Field(ge=1)
    z_bays: int = Field(ge=1)


#: 立面标记及形式描述，plan 将其转换为 WILD 实体。
OpeningToken = str


class FacadeDecision(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    bays: int = Field(ge=1)
    entrance_bay: int | None = Field(default=None, ge=1)
    ground_pattern: list[OpeningToken]
    upper_pattern: list[OpeningToken]

    @model_validator(mode="after")
    def patterns_match_bays(self):
        if (
            len(self.ground_pattern) != self.bays
            or len(self.upper_pattern) != self.bays
        ):
            raise ValueError(
                f"立面 pattern 长度必须与 bays 相同：bays={self.bays}，"
                f"ground_pattern={len(self.ground_pattern)}，upper_pattern={len(self.upper_pattern)}"
            )
        if self.entrance_bay is not None and self.entrance_bay > self.bays:
            raise ValueError("entrance_bay 不能超出 bays")
        return self


class RoofVolumeOverride(ContractModel):
    """逐体量屋面设计，允许扩展造型参数。"""

    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    volume: str = Field(min_length=1)
    type: str | None = None
    overhang: float | None = Field(default=None, ge=0, le=2)


class RoofDecision(ContractModel):
    """整体屋面意图与逐体量覆盖。"""

    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    type: str
    ridge_axis: Literal["x", "z"] = Field(
        default="x",
        description=(
            "仅双坡（gable）屋顶需要选择屋脊方向；其他已知屋型可省略，由程序保留兼容默认值。"
        ),
    )
    overhang: float = Field(default=0, ge=0, le=2)
    #: 按设计体量引用分配屋面形态，plan 负责实现。
    volumes: list[RoofVolumeOverride] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_unused_axis(cls, value):
        if not isinstance(value, dict) or "ridge_axis" not in value:
            return value
        if value["ridge_axis"] is not None and value["ridge_axis"] != "none":
            return value
        # 不猜测双坡、混合双坡或自定义屋型的方向；仅规范化已知无此自由度的屋型。
        kinds = [value.get("type")]
        if isinstance(value.get("volumes"), list):
            for item in value["volumes"]:
                if isinstance(item, RoofVolumeOverride):
                    kinds.append(item.type or value.get("type"))
                elif isinstance(item, dict):
                    kinds.append(item.get("type") or value.get("type"))
                else:
                    return value
        without_axis = {
            "flat",
            "hip",
            "dome",
            "chinese_curved",
            "chinese_pagoda",
            "none",
            "open",
        }
        if all(isinstance(kind, str) and kind in without_axis for kind in kinds):
            return {**value, "ridge_axis": cls.model_fields["ridge_axis"].default}
        return value


class CurtainWallDecision(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    grid_strategy: str = "floor_and_bay_aligned"


class EnvelopeDecision(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    system: str = "solid_wall"
    curtain_wall: CurtainWallDecision | None = None


class CirculationDecision(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    vertical_strategy: str = ""
    required_connections: list[RequiredConnection] = Field(
        default_factory=list,
        description="本次明确要求的连通关系，引用房间、入口或标高ID",
    )
    clearance_paths: list[ClearancePath] = Field(
        default_factory=list,
        description="本次明确要求的通行净空折线；实体净空需另行验收",
    )


# 材料角色由图纸声明，默认角色及参数仍来自blueprint/materials/plan.py。
MaterialRoleName = str


class ResolvedMaterialRole(ContractModel):
    role: MaterialRoleName = Field(min_length=1, max_length=80)
    materialId: str = Field(min_length=1, max_length=80)
    assetId: str | None = Field(default=None, max_length=200)
    proceduralPresetId: str | None = Field(default=None, max_length=120)
    surfacePresetId: str | None = Field(default=None, max_length=120)
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
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    keywords: list[str] = Field(default_factory=list)
    roles: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="本次材料角色及描述，可用base_role引用默认用途；实际PBR由材料节点落实",
    )
    resolved_plan: ResolvedMaterialPlan | None = None
    #: 区域/构件材质绑定（P5-C）。空列表 ⇒ 全部按类型默认角色，与引入前逐字段一致。
    regions: list[MaterialRegion] = Field(default_factory=list, max_length=20)


class SupportRelation(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    kind: str = "supports"
    target: str = Field(min_length=1, description="关系目标的稳定实例 ID 或实体 ID")
    along_ratio: float = Field(default=0.5, ge=0, le=1)
    depth_ratio: float = Field(default=0.5, ge=0, le=1)


class ComponentPlacement(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    position: list[Annotated[float, Field(strict=True, allow_inf_nan=False)]] | None = (
        Field(
            default=None,
            min_length=3,
            max_length=3,
            exclude_if=lambda value: value is None,
            description="构件世界中心 [x,y,z]；参数表达式必须先展开为三个有限数字",
        )
    )
    face: Literal["front", "back", "left", "right"] | None = None
    floor: int | None = Field(default=None, ge=1)
    offset: float = Field(default=0)
    sill_height: float = Field(
        default=0,
        exclude_if=lambda value: value == 0,
        description="历史定位：相对宿主墙底的高度，新图纸优先使用elevation",
    )
    normal_offset: float = Field(
        default=0, description="沿宿主墙局部法线的偏移；不是世界 X/Z"
    )
    mode: Literal["world", "wall", "anchor", "surface"] | None = Field(
        default=None, description="唯一定位方式；空值仅兼容历史图纸"
    )
    anchor: str | None = Field(
        default=None,
        description="position或墙局部坐标所对应的构件锚点，例如center、bottom_left",
    )
    elevation: ElevationReference | None = Field(
        default=None, description="墙上构件锚点的世界标高引用，与历史sill_height互斥"
    )
    rotation: tuple[float, float, float] = Field(
        default=(0, 0, 0), description="相对定位参考系绕X/Y/Z旋转的弧度"
    )
    mounting: Literal["conform", "tangent_plane"] = Field(
        default="conform", description="曲墙上的贴合方式；切平面安装不等于沿曲墙展开"
    )
    host_anchor: str | None = Field(
        default=None, description="anchor模式引用的宿主锚点名称"
    )
    self_anchor: str | None = Field(
        default=None, description="anchor模式对齐的构件自身锚点名称"
    )
    anchor_offset: tuple[float, float, float] = Field(
        default=(0, 0, 0), description="宿主锚点坐标系内的米制偏移，不是世界坐标"
    )
    chart: str | None = Field(
        default=None, description="surface模式引用的宿主曲面参数域ID"
    )
    uv: (
        tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]]
        | None
    ) = Field(default=None, description="曲面参数域中的归一化二维位置")
    orientation: Literal["surface_frame"] = Field(
        default="surface_frame", description="使用宿主曲面的切向与法向定义朝向"
    )

    @model_validator(mode="before")
    @classmethod
    def anchor_offset_alias(cls, value):
        if (
            isinstance(value, dict)
            and value.get("mode") == "anchor"
            and isinstance(value.get("offset"), (list, tuple))
        ):
            value = dict(value)
            value["anchor_offset"] = value.pop("offset")
        return value

    @model_validator(mode="after")
    def placement_mode_is_unambiguous(self):
        if self.mode == "world" and self.position is None:
            raise ValueError("world 定位必须给 position 和明确 anchor")
        if self.mode in {"wall", "anchor", "surface"} and self.position is not None:
            raise ValueError("不能同时给出世界位置与宿主定位")
        if self.mode is not None and self.mode != "anchor" and not self.anchor:
            raise ValueError("定位模式必须明确 anchor")
        if self.mode == "anchor" and (not self.host_anchor or not self.self_anchor):
            raise ValueError("锚点定位必须给 host_anchor/self_anchor")
        if self.elevation is not None and "sill_height" in self.model_fields_set:
            raise ValueError("elevation 和 sill_height 只能选择一个")
        if self.mode == "surface" and (self.uv is None or not self.chart):
            raise ValueError("曲面定位必须给 chart 和 uv")
        if self.mode == "wall" and self.anchor not in {
            "bottom_left",
            "opening_start_bottom",
            "opening_center_bottom",
            "center",
        }:
            raise ValueError(
                "wall定位anchor必须为bottom_left、opening_start_bottom、opening_center_bottom或center"
            )
        return self


def _dimension_name(value: str) -> str:
    if value in ComponentPlacement.model_fields:
        raise ValueError(f"{value} 是位置参数，应保留原值写在 placement.{value}")
    return value


class FloorConnection(ContractModel):
    from_floor: int | None = Field(
        default=None, ge=1, exclude_if=lambda value: value is None
    )
    to_floor: Annotated[int, Field(ge=1)] | Literal["roof"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    from_level: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="起点楼面levels ID",
    )
    to_level: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="终点楼面或屋面levels ID；标高必须高于起点",
    )

    @model_validator(mode="after")
    def connection_references(self):
        indexed = self.from_floor is not None and self.to_floor is not None
        named = bool(self.from_level and self.to_level)
        if indexed == named:
            raise ValueError(
                "楼层连接必须选择完整的 from_level/to_level 或历史楼层整数"
            )
        return self


class ComponentInstance(ContractModel):
    """保留实例设计及扩展参数，由 plan 实现形态与依附关系。"""

    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    type: str = Field(min_length=1)
    system: str | None = Field(
        default=None, description="systems中与构件type一致的共享系统ID"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="实例对共享构造参数的显式取值"
    )
    material_bindings: dict[str, str] = Field(
        default_factory=dict, description="构件部位名称到materials.roles角色的绑定"
    )
    footprint: str | None = Field(default=None, description="构件占地轮廓的profiles ID")
    opening: str | None = Field(
        default=None, description="构件需要的voids留洞ID，例如楼梯上层洞口"
    )
    access: str | None = Field(
        default=None, description="构件通行或操作净空的profiles ID"
    )
    guarding: dict[str, Any] | None = Field(
        default=None, description="留洞与临空边的防护设计参数；声明不自动生成栏杆"
    )
    id: str | None = Field(default=None, min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    relation: SupportRelation | None = None
    floor_connections: list[FloorConnection] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    #: 设计中的宿主引用；plan 负责转换为真实实体引用。
    host: str | None = Field(
        default="", description="宿主引用 ID；省略、空字符串或 null 表示无宿主"
    )
    description: str = ""
    #: 相对宿主的尺寸（逐类型字段不同）
    placement: ComponentPlacement | None = None
    size: dict[
        Annotated[str, AfterValidator(_dimension_name)],
        Annotated[float, Field(gt=0, allow_inf_nan=False)],
    ] = Field(default_factory=dict)
    #: 开放的设计形式描述，plan 负责转换成 WILD。
    form: dict[str, Any] = Field(default_factory=dict)
    #: 材质角色名
    material_role: str | None = None

    @field_validator("form", mode="before")
    @classmethod
    def descriptive_form(cls, value):
        return {"description": value} if isinstance(value, str) else value

    @model_validator(mode="after")
    def construction_contract(self):
        from app.domain.design.construction_systems import validate_construction

        validate_construction(self.model_dump(mode="json", exclude_none=True))
        return self


class ArchitectureIntent(ContractModel):
    """本次采用的整体设计方向；实际几何由对应设计模块表达。"""

    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )

    goals: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    spatial_strategy: str = Field(default="")
    composition: str = Field(default="")
    material_strategy: str = Field(default="")
    selected_systems: list[str] = Field(default_factory=list)

    @field_validator(
        "spatial_strategy", "composition", "material_strategy", mode="before"
    )
    @classmethod
    def preserve_sectioned_strategy(cls, value: Any) -> Any:
        """兼容模型分项表达；统一存成文本，保留键、内容与嵌套列表。"""
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        return value


class ArchitectureDecisions(ContractModel):
    model_config = ConfigDict(
        extra="allow", validate_assignment=True, allow_inf_nan=False
    )
    #: 判别字段。与 `ObjectDecisions.kind` 一起构成 `decisions` 的带标签联合。
    #: 有默认值是为了让 2026-09-23 之前存档的 DesignDocument（当时只有建筑一种）
    #: 仍然可读——见 `DesignDocument._default_decisions_kind`。
    kind: Literal["architecture"] = "architecture"
    concept: str = Field(default="")
    massing: MassingDecision
    complexity: ComplexityDecision = Field(default_factory=ComplexityDecision)
    coordinate_system: CoordinateSystem = Field(
        default_factory=CoordinateSystem, description="全图统一的单位、轴向与旋转约定"
    )
    levels: list[DesignLevel] = Field(
        default_factory=list, description="楼面与屋面等明确标高，使用稳定ID引用"
    )
    profiles: list[DesignProfile] = Field(
        default_factory=list, description="可复用的闭合轮廓及其有向边，支持曲线和孔洞"
    )
    systems: dict[str, ConstructionSystem] = Field(
        default_factory=dict, description="按系统ID索引的共享构造参数，不包含实例位置"
    )
    walls: list[DesignWall] = Field(
        default_factory=list, description="围护和隔墙的逻辑实体，也是门窗宿主"
    )
    slabs: list[DesignSlab] = Field(
        default_factory=list, description="楼板、平台的实际边界、顶标高与扣洞引用"
    )
    voids: list[DesignVoid] = Field(
        default_factory=list, description="按楼面声明的楼梯孔、中庭等留洞区域"
    )
    roofs: list[DesignRoof] = Field(
        default_factory=list, description="独立屋面清单；没有独立屋面时留空"
    )
    relations: list[DesignRelation] = Field(
        default_factory=list, description="构件间的显式承托、连通与对齐关系"
    )
    floor_layouts: list[DesignFloorLayout] = Field(
        default_factory=list, description="各楼面的功能分区，房间边界不代替实体墙"
    )
    volumes: list[VolumeDecision] = Field(min_length=1)
    structural_grid: StructuralGridDecision | None = None
    envelope: EnvelopeDecision = Field(default_factory=EnvelopeDecision)
    facades: dict[Literal["front", "back", "left", "right"], FacadeDecision] = Field(
        default_factory=dict
    )
    roof: RoofDecision = Field(default_factory=lambda: RoofDecision(type="none"))
    circulation: CirculationDecision = Field(default_factory=CirculationDecision)
    materials: MaterialIntent = Field(default_factory=MaterialIntent)
    detail_packages: list[str] = Field(default_factory=list)
    component_quota: dict[str, Any] = Field(default_factory=dict)
    components: list[ComponentInstance] = Field(default_factory=list)
    balcony_access_count: int = Field(default=0, ge=0)
    balcony_width: float | None = Field(default=None, gt=0)
    required_components: list[str] = Field(default_factory=list)
    unsupported_component_types: list[str] = Field(default_factory=list)
    design_rationale: list[str] = Field(default_factory=list)
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
    kind: Literal[
        "user_hard", "engine_hard", "system_required", "preference", "reference"
    ]
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
    classification: Literal[
        "engine_hard", "conditional", "preference", "reference", "unsupported"
    ]
    applies_when: str = Field(default="", max_length=500)
    schema_targets: list[str] = Field(default_factory=list, max_length=20)
    enforcement: list[
        Literal["schema", "planner", "resolver", "compiler", "validator", "none"]
    ]
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
        if not isinstance(data, dict):
            return data
        if data.get("schema_version") in {"design/1.1", "design/1.2", "design/1.3"}:
            data = {**data, "schema_version": "design/1.0"}
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
        if (
            massing.representation_mode == "full"
            and massing.modeled_floors != massing.floors
        ):
            raise ValueError("full 模式必须让 modeled_floors 等于 floors")
        if any(volume.geometry is not None for volume in decisions.volumes):
            from app.domain.design.spatial import validate_spatial_design

            validate_spatial_design(decisions.model_dump(mode="json"))
            return self
        seen: set[str] = set()
        for volume in decisions.volumes:
            if volume.id in seen:
                raise ValueError(f"重复 volume id: {volume.id}")
            seen.add(volume.id)
            if volume.end_floor > massing.modeled_floors:
                raise ValueError(f"volume {volume.id} 超出 modeled_floors")
        from app.domain.design.coordinates import DesignCoordinateConflict
        from app.domain.design.coordinates import volume_conflicts
        from app.domain.design.coordinates import floor_elevations

        floor_elevations(decisions.model_dump())
        conflicts = volume_conflicts(
            [v.model_dump(mode="json") for v in decisions.volumes],
            massing.model_dump(mode="json"),
        )
        if conflicts:
            raise DesignCoordinateConflict(conflicts)
        for floor in range(1, massing.modeled_floors + 1):
            if not any(
                volume.start_floor <= floor <= volume.end_floor
                for volume in decisions.volumes
            ):
                raise ValueError(f"第 {floor} 建模层没有任何 volume 覆盖")
        required_faces = {"front", "back", "left", "right"}
        if set(decisions.facades) != required_faces:
            raise ValueError("facades 必须完整包含 front/back/left/right")
        instance_ids = [c.id for c in decisions.components if c.id]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("构件实例 id 必须唯一，不能把同一实体用于多条关系")
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
    id: str | None = None
    kind: str = "storey"


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
    component_markers: list[dict[str, Any]] = Field(default_factory=list)
    projection_elements: list[dict[str, Any]] = Field(
        default_factory=list, exclude=True
    )
    design_gaps: list[DesignGap] = Field(default_factory=list)
    compile_blockers: list[dict[str, Any]] = Field(default_factory=list)
    bounds: dict[Literal["width", "depth", "height"], float]
    levels: list[ResolvedLevel]
    volumes: list[VolumeDecision]
    facade_slots: list[ResolvedFacadeSlot]
    component_quantities: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
    geometry_context: dict[str, Any] = Field(
        default_factory=dict,
        description="一次解析得到的真实截面、楼板与标高事实，后续节点直接复用",
    )
    body_geometry: dict[str, Any] = Field(
        default_factory=dict,
        description="可确定计算的WILD主体片段，经现有装配与校验入口采用",
    )
    logical_hosts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="逻辑墙的有向路径、分段截面、厚度与实际空间范围",
    )
    capability_gaps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="图纸可保留但当前执行入口尚未落实的能力，不得隐式降级",
    )
