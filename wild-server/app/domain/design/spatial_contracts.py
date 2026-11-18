"""设计图纸的轮廓、标高和宿主契约；文件版本仍为 design/1.0。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Positive = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
Point2 = tuple[Number, Number]
Point3 = tuple[Number, Number, Number]


class SpatialContract(BaseModel):
    """空间字段通用约束：拒绝未知字段、非有限数字，序列化保留 from/to 协议名。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
        serialize_by_alias=True,
        populate_by_name=True,
    )


class Identified(SpatialContract):
    """由设计者确定稳定名称，几何修改和内部网格拆分均不应改变这个身份。"""

    id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="本图纸内唯一的稳定ID，供轮廓、宿主、关系和修订引用",
    )


class CoordinateSystem(SpatialContract):
    """程序固定的计量与坐标约定，模型不能为某个构件另选一套坐标系。"""

    length_unit: Literal["m"] = Field(default="m", description="全图长度单位固定为米")
    angle_unit: Literal["rad"] = Field(
        default="rad", description="设计旋转单位固定为弧度；WILD度数字段由程序转换"
    )
    up_axis: Literal["y"] = Field(default="y", description="世界竖直方向固定为+Y")
    plan_axes: tuple[Literal["x"], Literal["z"]] = Field(
        default=("x", "z"), description="二维轮廓点依次表示X、Z"
    )
    handedness: Literal["right"] = Field(
        default="right", description="绕+Y旋转使用右手定则"
    )


class DesignLevel(Identified):
    """全局标高基准；主楼层、屋面和局部夹层共用稳定ID，引用时不重复填写Y。"""

    kind: Literal["storey", "roof", "mezzanine", "platform"] = Field(
        default="storey",
        description="基准用途；roof不是额外一层，mezzanine/platform表示局部夹层或平台",
    )
    index: int | None = Field(
        default=None, ge=1, description="主楼层从1开始的序号；屋面和局部平台可省略"
    )
    elevation: Number = Field(description="该完成面或明确支承面的世界Y标高，单位米")


class ElevationReference(SpatialContract):
    """设计者引用既有标高，程序计算实际Y=levels[level].elevation+offset。"""

    level: str = Field(
        min_length=1, description="引用levels中已声明的标高ID，例如L1、RF或MEZZ"
    )
    offset: Number = Field(
        default=0, description="相对所引用标高的竖向偏移，米；楼面下方板底取负值"
    )


class LineSegment(Identified):
    """轮廓或墙路径中的有向直线，二维点使用所在参考系的[X,Z]。"""

    type: Literal["line"] = "line"
    start: Point2 = Field(
        alias="from", description="有向线段的起点[X,Z]，沿墙距离从此端计量"
    )
    end: Point2 = Field(alias="to", description="有向线段的终点[X,Z]，不得与起点重合")


class ArcSegment(Identified):
    """圆弧的真实参数；程序负责端点、弧长、采样和切线，不由模型手算。"""

    type: Literal["arc"] = "arc"
    center: Point2 = Field(description="圆心在所在参考系中的[X,Z]，米")
    radius: Positive = Field(description="圆弧半径，米")
    start_angle: Number = Field(
        description="起始弧度；点坐标=center+[r*cos(a),-r*sin(a)]，与绕+Y右手方向一致"
    )
    sweep_angle: Number = Field(
        description="从起始角扫过的有符号弧度，绝对值不超过2π且不能为0"
    )


class BezierSegment(Identified):
    """三次Bezier段：依次为起点、两个控制点、终点，均为局部[X,Z]。"""

    type: Literal["cubic_bezier"] = "cubic_bezier"
    points: tuple[Point2, Point2, Point2, Point2] = Field(
        description="四个有序二维控制点；程序据此计算曲线和弧长"
    )


CurveSegment = Annotated[
    LineSegment | ArcSegment | BezierSegment, Field(discriminator="type")
]


class RectangleProfile(Identified):
    """以[0,0]为中心的矩形轮廓；边名固定为front/right/back/left。"""

    type: Literal["rectangle"] = "rectangle"
    width: Positive = Field(description="局部X方向总宽，米；不是世界包围盒宽")
    depth: Positive = Field(description="局部Z方向总深，米")
    holes: list[str] = Field(
        default_factory=list,
        description="内部孔洞的闭合profile ID；不能与外轮廓相切或相交",
    )


class CircleProfile(Identified):
    """局部原点为圆心；perimeter是连续边界ID，闭合曲线需要固定参数起点。"""

    type: Literal["circle"] = "circle"
    radius: Positive = Field(description="圆半径，米")
    seam_angle: Number = Field(
        default=0, description="沿墙距离零点的弧度；0在局部+X，正向绕+Y右手旋转"
    )
    holes: list[str] = Field(
        default_factory=list, description="圆内部孔洞的profile ID列表"
    )


class EllipseProfile(Identified):
    """以[0,0]为中心的椭圆；沿墙距离使用程序计算的弧长，不能使用弦长。"""

    type: Literal["ellipse"] = "ellipse"
    radius_x: Positive = Field(description="局部X方向半轴长度，米")
    radius_z: Positive = Field(description="局部Z方向半轴长度，米")
    seam_angle: Number = Field(
        default=0, description="椭圆参数的起始弧度，固定perimeter的距离零点"
    )
    holes: list[str] = Field(
        default_factory=list, description="椭圆内部孔洞的profile ID列表"
    )


class ProfileVertex(Identified):
    """多边形顶点身份与位置分离；移动点保留ID，不让相邻墙引用失效。"""

    point: Point2 = Field(description="顶点局部[X,Z]，米")


class ProfileEdge(Identified):
    """有向边引用顶点ID；边ID也是外墙的稳定定位依据。"""

    start: str = Field(alias="from", min_length=1, description="起点vertex ID")
    end: str = Field(alias="to", min_length=1, description="终点vertex ID")


class PolygonProfile(Identified):
    """带稳定顶点/边名称的闭合多边形，不以宽深包围盒代替实际形状。"""

    type: Literal["polygon"] = "polygon"
    vertices: list[ProfileVertex] = Field(
        min_length=3, description="局部二维顶点及稳定ID"
    )
    edges: list[ProfileEdge] = Field(
        min_length=3, description="首尾连续闭合的有向边，禁止自交与重复边ID"
    )
    holes: list[str] = Field(
        default_factory=list, description="内部孔洞引用的profile ID列表"
    )


class CurveProfile(Identified):
    """由直线、圆弧和Bezier组成的闭合轮廓，各段ID供曲墙及附件引用。"""

    type: Literal["curve_loop"] = "curve_loop"
    segments: list[CurveSegment] = Field(
        min_length=1, description="按顺序衔接并闭合的曲线段，采样由程序负责"
    )
    holes: list[str] = Field(
        default_factory=list, description="内部孔洞引用的profile ID列表"
    )


DesignProfile = Annotated[
    RectangleProfile | CircleProfile | EllipseProfile | PolygonProfile | CurveProfile,
    Field(discriminator="type"),
]


class VolumePlacement(SpatialContract):
    """轮廓局部原点到世界平面的变换；竖向标高另由levels定义。"""

    origin_xz: Point2 = Field(
        default=(0, 0), description="局部原点对应的世界[X,Z]，米；矩形轮廓原点是中心"
    )
    yaw: Number = Field(
        default=0, description="绕世界+Y的右手旋转弧度，沿用WILD旋转约定"
    )


class ExtrusionGeometry(SpatialContract):
    """在两个标高之间采用同一轮廓；可表达圆、多边形、曲线及带孔主体。"""

    type: Literal["extrusion"] = "extrusion"
    profile: str = Field(min_length=1, description="引用profiles中的闭合截面ID")
    bottom: ElevationReference = Field(description="体量底部的世界标高引用")
    top: ElevationReference = Field(
        description="体量顶部的世界标高引用，必须高于bottom"
    )


class LoftSection(SpatialContract):
    """某一高度的截面决定；缩放→旋转→偏移，再应用体量placement。"""

    at: ElevationReference = Field(description="该截面的世界Y标高引用")
    profile: str = Field(
        min_length=1, description="截面轮廓ID；相邻截面须能按稳定边名匹配"
    )
    offset_xz: Point2 = Field(
        default=(0, 0), description="体量局部平面的截面偏移，随高度变化可表达倾斜"
    )
    yaw: Number = Field(
        default=0, description="截面绕局部+Y的右手旋转弧度，随高度变化可表达扭转"
    )
    scale: tuple[Positive, Positive] = Field(
        default=(1, 1), description="截面局部X/Z正比例缩放，随高度变化可表达收分"
    )


class LoftGeometry(SpatialContract):
    """对应截面点的分段线性放样；不把包围盒当实际围护，也不填满室内。"""

    type: Literal["section_loft"] = "section_loft"
    interpolation: Literal["linear"] = "linear"
    sections: list[LoftSection] = Field(
        min_length=2, description="按实际Y严格递增的截面，截面拓扑必须一致"
    )


class AdvancedGeometry(SpatialContract):
    """保留明确的高级设计输入；实现边界由解析器报告，不能降级为包围盒。"""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    type: Literal["sweep", "revolve", "surface_patches", "boolean"]


VolumeGeometry = Annotated[
    ExtrusionGeometry | LoftGeometry | AdvancedGeometry, Field(discriminator="type")
]


class BoundaryWallGeometry(SpatialContract):
    """从真实体量的指定边界提取墙面，可随截面收分/扭转，不限四个方向。"""

    type: Literal["volume_boundary"] = "volume_boundary"
    volume: str = Field(min_length=1, description="墙面所属体量的稳定ID")
    edge: str = Field(
        min_length=1, description="轮廓边/曲线段ID；圆和椭圆的连续边界使用perimeter"
    )
    bottom: ElevationReference = Field(
        description="本逻辑墙底部的世界标高引用，也是sill_height默认基准"
    )
    top: ElevationReference = Field(description="本逻辑墙顶部标高，通常接上层楼板底")


class PathWallGeometry(SpatialContract):
    """独立内墙或自由曲墙；不与体量围护重复声明，from/to为二维路径。"""

    type: Literal["path"] = "path"
    frame: str = Field(
        default="world", description="world表示世界X/Z；体量ID表示其placement局部平面"
    )
    segments: list[CurveSegment] = Field(
        min_length=1, description="连续有向墙路径；不要求闭合，长度必须大于0"
    )
    bottom: ElevationReference = Field(description="墙底标高引用")
    top: ElevationReference = Field(description="墙顶标高引用")


class DesignWall(Identified):
    """门窗可引用的逻辑宿主；程序内部拆网格时保留ID到实际片段的映射。"""

    role: Literal["exterior", "interior", "curtain_wall"] = Field(
        default="exterior", description="墙用途；幕墙仍需明确构造与几何"
    )
    system: str = Field(
        min_length=1, description="systems中的wall系统ID，提供墙厚和材质角色"
    )
    geometry: Annotated[
        BoundaryWallGeometry | PathWallGeometry, Field(discriminator="type")
    ] = Field(description="墙的唯一几何来源：体量边界或独立路径")


class ProfileRegion(SpatialContract):
    """房间、楼板局部片区或留洞的平面区域，不再局限矩形bounds。"""

    type: Literal["profile_region"] = "profile_region"
    profile: str = Field(min_length=1, description="区域的闭合轮廓ID")
    frame: str = Field(
        default="world",
        description="world或体量ID；先应用区域变换，再应用体量placement",
    )
    origin_xz: Point2 = Field(
        default=(0, 0), description="轮廓原点在所选frame中的[X,Z]，米"
    )
    yaw: Number = Field(default=0, description="区域轮廓在frame内绕+Y旋转的弧度")


class VolumeRegion(SpatialContract):
    """程序在指定世界标高切取多个体量并求平面并集，保留真实外形和孔洞。"""

    type: Literal["volume_union_section"] = "volume_union_section"
    volumes: list[str] = Field(min_length=1, description="参与截面并集的体量ID列表")
    level: str = Field(min_length=1, description="切片平面的levels ID")


DesignRegion = Annotated[ProfileRegion | VolumeRegion, Field(discriminator="type")]


class DesignRoom(Identified):
    """房间是功能区域；区域边界不会隐式生成墙或楼板。"""

    name: str = Field(default="", description="房间的功能名称")
    region: DesignRegion | None = Field(
        default=None, description="新图纸必填的真实平面范围"
    )
    bounds: dict[str, float] | None = Field(
        default=None, description="仅兼容历史矩形房间范围"
    )
    void: bool = Field(
        default=False, description="仅兼容历史挑空标记；新图纸使用voids及slab.holes"
    )


class DesignFloorLayout(SpatialContract):
    """楼面上的功能分区；楼面标高和几何分别引用levels、rooms.region。"""

    level: str | Number | None = Field(
        default=None, description="新图纸引用levels ID；数字或省略仅兼容历史楼面标高"
    )
    rooms: list[DesignRoom] = Field(
        default_factory=list, description="本楼面的功能区域清单"
    )
    floor: int | None = Field(default=None, description="仅兼容历史楼层序号")
    walls: list[dict] = Field(
        default_factory=list, description="仅兼容历史内墙；新图纸统一使用walls"
    )


class RequiredConnection(SpatialContract):
    """要求连通的两个已声明实体；via可指定采用的楼梯或通行构件。"""

    start: str = Field(alias="from", description="起点房间、入口构件或标高ID")
    end: str = Field(alias="to", description="终点房间、入口构件或标高ID")
    via: str | None = Field(
        default=None, description="明确经由的构件ID，省略不代表程序自动补构件"
    )


class ClearancePath(Identified):
    """本次要求保留的通行净空；路径定义不等于已通过实体或专业安全验收。"""

    level: str = Field(description="路径所属levels ID")
    points: list[Point2] = Field(min_length=2, description="世界XZ折线，至少两个不同点")
    width: Positive = Field(description="本次选择的通行净宽，米")
    height: Positive = Field(description="本次选择的通行净高，米")


class DesignSlab(Identified):
    """楼板或平台；top表示完成面，板底=top减系统厚度，孔洞共用void引用。"""

    system: str = Field(
        min_length=1, description="systems中的slab系统ID，提供厚度与材质角色"
    )
    top: ElevationReference = Field(
        description="板顶完成面的标高引用，不能填写板底标高"
    )
    region: DesignRegion = Field(description="真实平面范围，可来自轮廓或体量截面并集")
    holes: list[str] = Field(
        default_factory=list, description="voids中的留洞ID列表；程序扣除实际相交区域"
    )


class DesignVoid(Identified):
    """显式缺板区域；楼梯孔、中庭共用此边界，声明本身不会自动生成防护。"""

    purpose: str = Field(
        default="opening", description="设计用途，例如stair_opening或atrium"
    )
    level: str = Field(min_length=1, description="留洞所属楼面标高ID")
    region: DesignRegion = Field(description="留洞真实平面轮廓及参考系")


class ConstructionSystem(SpatialContract):
    """本次选用的可复用构造参数；实例只引用系统并明确必要差异。"""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    kind: str = Field(
        min_length=1, description="系统适用类型，例如wall、slab、window或door"
    )
    thickness: Positive | None = Field(
        default=None, description="墙厚或板厚，米；wall/slab必须明确"
    )
    reference: Literal["centerline"] = Field(
        default="centerline",
        description="墙路径以厚度中心面为基准；定位偏移不能换成外皮距离",
    )
    material_role: str | None = Field(
        default=None, description="引用materials.roles的稳定角色，不直接复制另一份PBR"
    )
    construction: dict[str, Any] | None = Field(
        default=None,
        description="现有构造入口的结构化参数，例如framed_opening；由对应能力校验",
    )

    @model_validator(mode="after")
    def physical_thickness(self):
        if self.kind in {"wall", "slab"} and self.thickness is None:
            raise ValueError("墙和楼板构造必须明确 thickness")
        return self


class DesignRoof(Identified):
    """一片独立屋面；区分支承/檐口标高、rise及实际覆盖，不使用体量包围盒兜底。"""

    host: str = Field(min_length=1, description="负责覆盖的体量或明确支承实体ID")
    support: ElevationReference = Field(description="屋面支承或檐口基准的世界标高引用")
    geometry: dict[str, Any] = Field(
        description="明确屋型、真实outline、overhang、rise、thickness；未知几何报告能力缺口"
    )
    material_role: str | None = Field(default=None, description="屋面材料角色ID")


class DesignRelation(Identified):
    """跨实体的设计约束；坐标宿主、支承与通行分别表达，不共用parentId。"""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    type: Literal["supported_by", "connects_spaces", "aligned"] = Field(
        description="被支承、连通空间或对齐；引用由程序校验，实体关系另行验收"
    )
    subject: str = Field(
        min_length=1, description="发起关系的稳定实体ID，例如阳台、门或窗"
    )
    targets: list[str] = Field(
        default_factory=list, description="关联实体ID列表，例如承托柱或门两侧房间"
    )
    target: str | None = Field(default=None, description="对齐等单目标关系的目标实体ID")
