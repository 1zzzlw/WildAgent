"""建筑设计字段：先看 ArchitectureDecisions 总表，下方是各类字段的定义。"""
from __future__ import annotations

import json
from typing import Any, Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, field_validator, model_serializer, model_validator

from .base import ContractModel, ExtensibleModel
from .materials import MaterialIntent

# 保留整数和小数的原始表示，避免仅类型转换就改变设计哈希。
Coordinate = Annotated[int | float, Field(allow_inf_nan=False)]
OpeningToken = str


class ArchitectureDecisions(ExtensibleModel):
    """建筑图纸字段总表。先读这里，再按字段类型查看下方定义。

    本类记录设计决定；楼板分片、门窗世界坐标、踏步高度等由解析器推导。
    审核版本在 contracts.DesignDocument，计算结果在 contracts.ResolvedDesign。
    """

    kind: Literal["architecture"] = "architecture"  # 图纸类别
    concept: str = Field(default="")  # 建筑概念
    massing: MassingDecision  # 总层数、层高与整体形态
    complexity: ComplexityDecision  # 沿用的粒度配置，非构件数量要求
    volumes: list[VolumeDecision] = Field(min_length=1)  # 体量起点、宽深与楼层范围
    structural_grid: StructuralGridDecision  # 结构网格
    envelope: EnvelopeDecision  # 围护方式
    facades: dict[Literal["front", "back", "left", "right"], FacadeDecision]  # 共用立面布局
    floor_layouts: list[FloorLayoutDecision] = Field(default_factory=list, exclude_if=lambda v: not v)  # 房间、内墙与标高
    roof: RoofDecision  # 屋面形式及逐体量覆盖
    circulation: CirculationDecision = Field(default_factory=lambda: CirculationDecision())  # 层间交通和水平通路
    materials: MaterialIntent = Field(default_factory=MaterialIntent)  # 材质意图
    components: list[ComponentInstance] = Field(default_factory=list)  # 逐件有位置和尺寸的构件
    design_intent: ArchitectureIntent | None = None  # 空间、造型与材料选择理由
    design_rationale: list[str] = Field(default_factory=list)  # 补充说明

    # 旧生成链仍读取这些字段；数量新设计以 components 和立面标记为依据。
    # 本轮保留存档和消费者兼容，不能仅删除字段而留下仍在读取它们的代码。
    detail_packages: list[str] = Field(default_factory=list)  # 旧细部包
    component_quota: dict[str, Any] = Field(default_factory=dict)  # 旧构件配额
    balcony_access_count: int = Field(default=0, ge=0)  # 旧阳台通行数量
    balcony_width: float | None = Field(default=None, gt=0)  # 旧阳台宽度
    required_components: list[str] = Field(default_factory=list)  # 旧必需构件清单
    unsupported_component_types: list[str] = Field(default_factory=list)  # 已记录的未支持类型


class ComplexityDecision(ContractModel):
    level: Literal["minimal", "simple", "standard", "detailed"] = "standard"
    min_volumes: int = Field(default=1, ge=1, le=8)
    min_detail_packages: int = Field(default=0, ge=0, le=12)
    target_structural_elements: int = Field(default=10, ge=1, le=1000)
    grid_bays: tuple[int, int] = Field(default=(2, 2))
    reason: str = Field(default="", max_length=300)


class MassingTierDecision(ExtensibleModel):
    """可选的分段收放比例；各段层数之和等于总层数。"""

    floors: int = Field(ge=1)
    width_ratio: float = Field(gt=0)
    depth_ratio: float = Field(default=1.0, gt=0)


class MassingDecision(ExtensibleModel):
    shape: str = Field(min_length=1)  # 整体形态说明
    width: float = Field(
        gt=0, description="总体 X 方向尺寸控制上限（米），无世界原点边界"
    )
    depth: float = Field(
        gt=0, description="总体 Z 方向尺寸控制上限（米），实际包络由 volumes 决定"
    )
    floors: int = Field(ge=1)  # 实际总层数
    modeled_floors: int = Field(ge=1)  # 本次建模层数，完整模式由程序补齐
    representation_mode: Literal["full", "schematic"] = "full"  # 完整或示意建模
    floor_height: float = Field(gt=0)  # 默认层高，米
    symmetry: bool = False  # 是否选择对称构图
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


class VolumeDecision(ExtensibleModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_\-]+$")  # 稳定的体量 ID
    role: str = "primary"  # 主体、侧翼等用途说明
    x: float = Field(
        allow_inf_nan=False, description="体量平面起点的世界 X 坐标（米），不是中心"
    )
    z: float = Field(
        allow_inf_nan=False, description="体量平面起点的世界 Z 坐标（米），不是中心"
    )
    width: float = Field(gt=0)  # 世界 X 方向宽度
    depth: float = Field(gt=0)  # 世界 Z 方向深度
    start_floor: int = Field(ge=1)  # 起始层，包含本层
    end_floor: int = Field(ge=1)  # 结束层，包含本层
    facades: dict[Literal["front", "back", "left", "right"], FacadeDecision] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def floor_range_is_valid(self):
        if self.end_floor < self.start_floor:
            raise ValueError("volume.end_floor 不能小于 start_floor")
        return self


class StructuralGridDecision(ExtensibleModel):
    system: str
    x_bays: int = Field(ge=1)
    z_bays: int = Field(ge=1)


class FacadeDecision(ExtensibleModel):
    bays: int = Field(ge=1)  # 开间数，由模型输入的 layout 长度计算
    entrance_bay: int | None = Field(default=None, ge=1)  # 可选的入口开间编号
    ground_pattern: list[OpeningToken]  # 首层逐开间布局，由 layout 展开
    upper_pattern: list[OpeningToken]  # 上层逐开间布局，由 layout 展开

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


class RoofVolumeOverride(ExtensibleModel):
    """逐体量屋面设计，允许扩展造型参数。"""

    volume: str = Field(min_length=1)
    type: str | None = None
    overhang: float | None = Field(default=None, ge=0, le=2)


class RoofDecision(ExtensibleModel):
    """整体屋面意图与逐体量覆盖。"""

    type: str
    ridge_axis: Literal["x", "z"] = "x"
    overhang: float = Field(default=0, ge=0, le=2)
    #: 按设计体量引用分配屋面形态，plan 负责实现。
    volumes: list[RoofVolumeOverride] = Field(default_factory=list)


class CurtainWallDecision(ExtensibleModel):
    grid_strategy: str = "floor_and_bay_aligned"


class EnvelopeDecision(ExtensibleModel):
    system: str = "solid_wall"
    curtain_wall: CurtainWallDecision | None = None


class CirculationPath(ContractModel):
    """设计选择的水平净空，非默认建筑规范；points 为世界 X/Z 折线。"""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=80)
    floor: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    points: list[tuple[float, float]] = Field(min_length=2, max_length=64)

    @model_validator(mode="after")
    def distinct_segments(self):
        if any(a == b for a, b in zip(self.points, self.points[1:])):
            raise ValueError("通行路径的相邻点不能相同")
        return self


class CirculationDecision(ExtensibleModel):
    vertical_strategy: str = "stair"
    paths: list[CirculationPath] = Field(
        default_factory=list, max_length=32, exclude_if=lambda value: not value
    )


class SupportRelation(ExtensibleModel):
    kind: str = "supports"
    target: str = Field(min_length=1, description="关系目标的稳定实例 ID 或实体 ID")
    along_ratio: float = Field(default=0.5, ge=0, le=1)
    depth_ratio: float = Field(default=0.5, ge=0, le=1)


class ComponentPlacement(ExtensibleModel):
    face: Literal["front", "back", "left", "right"] | None = None
    floor: int | None = Field(default=None, ge=1)
    offset: float = Field(default=0)
    sill_height: float = Field(default=0)
    normal_offset: float = Field(
        default=0, description="沿宿主墙局部法线的偏移；不是世界 X/Z"
    )
    center_xz: tuple[float, float] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="等高楼梯的平面中心；竖向中心由楼面连接推导",
    )


def _dimension_name(value: str) -> str:
    if value in ComponentPlacement.model_fields:
        raise ValueError(f"{value} 是位置参数，应保留原值写在 placement.{value}")
    return value


class FloorConnection(ContractModel):
    from_floor: int = Field(ge=1)  # 起始楼层
    to_floor: Annotated[int, Field(ge=1)] | Literal["roof"]  # 到达楼层或屋面


class StairStepDesign(ContractModel):
    """已选等高分跑的踏步设计依据；实际级数、步高由楼面连接推导。"""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    flights: int = Field(ge=1)  # 已选择的等高梯段数
    max_riser_height: float | None = Field(default=None, gt=0)  # 设计步高上限，与下项二选一
    steps_per_flight: int | None = Field(default=None, ge=1)  # 明确指定的每跑级数

    @model_validator(mode="after")
    def one_step_basis(self):
        if (self.max_riser_height is None) == (self.steps_per_flight is None):
            raise ValueError(
                "max_riser_height 与 steps_per_flight 必须且只能选择一个设计依据"
            )
        return self


class ComponentInstance(ExtensibleModel):
    """保留实例设计及扩展参数，由 plan 实现形态与依附关系。"""

    type: str = Field(min_length=1)
    id: str | None = Field(default=None, min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    relation: SupportRelation | None = None
    floor_connections: list[FloorConnection] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    step_design: StairStepDesign | None = Field(
        default=None, exclude_if=lambda value: value is None
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


class ArchitectureIntent(ExtensibleModel):
    """空间、造型、材料及所选系统的设计说明。"""


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


class FloorBounds(ContractModel):
    """房间或挑空的世界 X/Z 矩形范围；宽深必须为正。"""

    x: Coordinate
    z: Coordinate
    width: Coordinate = Field(gt=0)
    depth: Coordinate = Field(gt=0)


class LegacyFloorBounds(ContractModel):
    """只兼容旧图纸的端点格式；保持原字段，不擅自转成新的房间几何。"""

    x_start: Coordinate
    x_end: Coordinate
    z_start: Coordinate
    z_end: Coordinate


class FloorRoomDecision(ExtensibleModel):
    """房间用途与边界；void=true 表示该层挑空。旧文本说明保留为扩展字段。"""

    id: str | None = Field(default=None, min_length=1, max_length=120)  # 可选的房间 ID
    name: str = Field(default="", max_length=200)  # 房间用途
    bounds: FloorBounds | LegacyFloorBounds | None = None  # 世界平面边界
    void: bool = False  # 是否在本层楼板挑空


    @model_serializer(mode="wrap")
    def preserve_supplied_fields(self, handler):
        """保留原图纸的字段存在性，避免补默认值导致旧哈希变化。"""
        return {key: value for key, value in handler(self).items()
                if key in self.model_fields_set or key in (self.model_extra or {})}


class FloorWallDecision(ContractModel):
    """独立内墙：世界 X/Z 端点与厚度；高度由楼层标高推导。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    id: str = Field(min_length=1, max_length=120)
    from_: list[Coordinate] = Field(alias="from", min_length=2, max_length=2)
    to_: list[Coordinate] = Field(alias="to", min_length=2, max_length=2)
    thickness: Coordinate = Field(gt=0)


class FloorLayoutDecision(ExtensibleModel):
    """一层的房间、内墙及可选标高；未填写的字段不写回旧图纸。"""

    floor: int = Field(ge=1)  # 从 1 开始的楼层编号
    level: Coordinate | None = None  # 可选的楼面顶标高，省略时按层高计算
    description: str = Field(default="", max_length=500)  # 本层说明
    rooms: list[FloorRoomDecision] = Field(default_factory=list)  # 房间与挑空
    walls: list[FloorWallDecision] = Field(default_factory=list)  # 内墙端点和厚度


    @model_serializer(mode="wrap")
    def preserve_supplied_fields(self, handler):
        """保留原图纸的字段存在性，避免补默认值导致旧哈希变化。"""
        return {key: value for key, value in handler(self).items()
                if key in self.model_fields_set or key in (self.model_extra or {})}


VolumeDecision.model_rebuild()
ArchitectureDecisions.model_rebuild()
