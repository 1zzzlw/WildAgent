原语构件库 v1.0

本文档定义原语语言中所有标准参数化构件的类型、字段和语义。每个构件是一组数学参数集合，由原语引擎编译为三维网格。

---

## 一、wall — 垂直墙体

**语义**：垂直平面，从 `from` 延伸至 `to`，厚度为 `thickness`。墙体的正面为右向量方向（从 `from` 看向 `to` 时，右侧为外）。

**参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"wall"` |
| `id` | string | 是 | 构件唯一标识 |
| `from` | Vec3 | 是 | 墙底起点，局部坐标 |
| `to` | Vec3 | 是 | 墙底终点，局部坐标。Y 应与 `from.y` 一致 |
| `thickness` | number | 是 | 墙体厚度（米），>0 |
| `material` | string | 否 | 引用材质库中的材质名 |
| `curve` | object 或 array | 否 | 路径曲线。不指定时为直线。单段为对象，多段为数组。详见曲线类型定义 |

**曲线类型定义**（`curve` 字段适用于 wall、beam 等线性构件）：

| 类型 | 字段 | 必需 | 说明 |
|------|------|------|------|
| `"line"`（直线，默认） | 无额外参数 | — | `from` 到 `to` 的直线。不指定 curve 时等同于本类型 |
| `"arc"`（圆弧） | `center` | 是 | 圆心，局部坐标 |
| | `sweep` | 是 | 扫过角度（度），正值逆时针 |
| | `segments` | 否 | 分段数，默认 24 |
| `"ellipse"`（椭圆弧） | `center` | 是 | 中心 |
| | `radiusX` | 是 | X 轴半径 |
| | `radiusZ` | 是 | Z 轴半径 |
| | `startAngle` | 否 | 起始角度（度），默认 0 |
| | `sweep` | 否 | 扫过角度，默认 360 |
| | `segments` | 否 | 分段数，默认 32 |
| `"catenary"`（悬链线/拱） | `rise` | 是 | 拱起高度（米） |
| | `segments` | 否 | 分段数，默认 16 |

**多段曲线**：`curve` 为数组时依次连接各段，上一段终点为下一段起点：

```json
{ "curve": [
  { "type": "arc", "center": [0,0,0], "sweep": 90 },
  { "type": "line" },
  { "type": "arc", "center": [5,0,5], "sweep": -90 }
] }
```

**示例**：

```json
{
  "type": "wall",
  "id": "front_wall",
  "from": [0, 0, 0],
  "to": [10, 3, 0],
  "thickness": 0.3,
  "material": "stone"
}
引擎处理说明：

墙体是一个长方体，底面从 from 沿 XZ 平面延伸到 to。

高度 = to.y - from.y。

当指定 `curve` 时，墙体沿曲线路径延伸。`from` 为路径起点，`to` 的 Y 决定墙高。

墙角连接规则参见空间关系解析层设计文档。

曲线墙体示例：

```json
{
  "type": "wall",
  "id": "round_outer_wall",
  "from": [5, 0, 0],
  "to": [5, 3, 0],
  "thickness": 0.3,
  "material": "stone",
  "curve": { "type": "arc", "center": [0, 0, 0], "sweep": 180, "segments": 24 }
}
```

二、floor — 水平地板
语义：水平平板，填充从 from 到 to 的矩形区域，或圆形区域。顶面为可步行表面。

参数：

字段	类型	必需	说明
type	string	是	固定值 "floor"
id	string	是	构件唯一标识
from	Vec3	是	矩形对角线一端，顶面高度；或圆形时，底面中心
to	Vec3	是	矩形对角线另一端，顶面高度。Y 应与 from.y 一致。圆形时忽略
thickness	number	是	楼板厚度（米），>0
shape	string	否	形状，默认 "rect"。可选 "circle"
radius	number	否	圆形半径（米），仅在 shape="circle" 时必需
segments	number	否	圆形分段数，默认 32。仅在 shape="circle" 时生效
material	string	否	引用材质库中的材质名
示例：

json
{
  "type": "floor",
  "id": "base_floor",
  "from": [0, 0, 0],
  "to": [10, 0, 10],
  "thickness": 0.2,
  "material": "wood"
}
引擎处理说明：

地板是一个矩形平板（默认）或圆形平板（shape="circle"），顶面为可步行表面。

顶面高度 = from.y，底面高度 = from.y - thickness。

矩形：XZ 范围 = (min(from.x,to.x), min(from.z,to.z)) 到 (max(from.x,to.x), max(from.z,to.z))。

圆形：以 from 为圆心，radius 为半径生成 segments 边形近似。from.y 为顶面高度。

圆形地板示例：

json
{
  "type": "floor",
  "id": "round_platform",
  "from": [0, 0, 0],
  "thickness": 0.3,
  "shape": "circle",
  "radius": 5,
  "segments": 32,
  "material": "stone"
}

三、column — 柱式
语义：垂直柱体，底面中心位于 base，向上延伸 height 米。可配置截面形状、收分、卷杀和侧脚。

参数：

字段	类型	必需	说明
type	string	是	固定值 "column"
id	string	是	构件唯一标识
base	Vec3	是	柱底中心，局部坐标
height	number	是	柱高（米），>0
bottomRadius	number	是	底部半径（米），>0
topRadius	number	是	顶部半径（米），>0
style	string	是	柱式风格，见下方枚举
flutes	number	否	凹槽数，仅适用特定风格
entasis	number	否	卷杀弧度（米），0 为无。仅 chinese_wooden 支持
inclination	number	否	侧脚比例（无单位，相对于柱高），0 为垂直。例如 0.01 表示柱顶向中心偏移柱高 × 1%。仅 chinese_wooden 支持
material	string	否	引用材质库中的材质名
style 枚举：

值	说明
"doric"	多立克柱式，粗壮，底部半径约为高度的 1/6
"ionic"	爱奥尼柱式，修长，有卷涡柱头
"corinthian"	科林斯柱式，最修长，柱头有茛苕叶雕饰
"modern"	现代简约柱式，平滑锥形
"chinese_wooden"	中式木柱，支持 entasis（卷杀）和 inclination（侧脚）
示例：

json
{
  "type": "column",
  "id": "main_column",
  "base": [0, 0, 0],
  "height": 4,
  "bottomRadius": 0.2,
  "topRadius": 0.15,
  "style": "chinese_wooden",
  "entasis": 0.02,
  "inclination": 0.015,
  "material": "red_lacquer"
}
引擎处理说明：

柱体是一个截锥体（底面圆 → 顶面圆），由 bottomRadius 和 topRadius 控制收分。

entasis 在柱身中部微微鼓起，生成卷杀曲线。

inclination 使柱子向中心微微倾斜，偏移量 = inclination × height。

柱子的包围盒宽度 = 2 × max(bottomRadius, topRadius)。

四、beam — 横梁
语义：水平或倾斜的梁，从 from 延伸至 to。截面为矩形、圆形或工字型。

参数：

字段	类型	必需	说明
type	string	是	固定值 "beam"
id	string	是	构件唯一标识
from	Vec3	是	梁底起点，局部坐标
to	Vec3	是	梁底终点，局部坐标
crossSection	string	是	截面形状："rect" / "circular" / "i-beam"
width	number	是	截面宽度（米）。对圆形为直径
height	number	是	截面高度（米）。对圆形为直径，应与 width 相同
curve	object 或 array	否	路径曲线。同 wall 的 curve 定义。不指定时为直线。可用于拱形梁（斗拱）
material	string	否	引用材质库中的材质名
示例：

json
{
  "type": "beam",
  "id": "roof_beam",
  "from": [0, 3, 0],
  "to": [10, 3.5, 0],
  "crossSection": "rect",
  "width": 0.15,
  "height": 0.3,
  "material": "wood"
}
引擎处理说明：

矩形梁：底面宽度 width，高度 height，沿 from→to 方向延伸。

梁的包围盒长度 = from 到 to 的直线距离，宽度 = width，高度 = height。

五、roof — 屋顶
语义：覆盖闭合墙体的顶部结构。支持多种屋顶类型。

参数：

字段	类型	必需	说明
type	string	是	固定值 "roof"
id	string	是	构件唯一标识
roofType	string	是	屋顶类型，见下方枚举
span	number	是	跨度（米），XZ 平面的主要覆盖宽度
depth	number	是	进深（米），XZ 平面的另一方向
height	number	是	屋顶垂直高度（米）
thickness	number	是	屋面厚度（米）
eaveCurveHeight	number	否	飞檐翘起高度（米），仅 chinese_curved 支持
curveProfile	string	否	举折曲线轮廓，仅 chinese_curved 支持
tiers	number	否	重檐层数（仅 chinese_pagoda）。≥1，默认 3
baseSpan	number	否	底层跨度（米），仅 chinese_pagoda。默认等于 span
baseDepth	number	否	底层进深（米），仅 chinese_pagoda。默认等于 depth
tierHeight	number	否	每层垂直高度（米），仅 chinese_pagoda。默认等于 height / tiers
eaveOutset	number	否	每层出檐外挑量（米），仅 chinese_pagoda。默认 0.5
shrinkFactor	number	否	每层缩比，0-1。0.7 表示每层为上一层的 70%，仅 chinese_pagoda。默认 0.7
material	string	否	引用材质库中的材质名
roofType 枚举：

值	说明
"gable"	人字顶，三角山墙。默认有屋脊
"hip"	四坡顶，四面倾斜
"dome"	穹顶或圆顶
"flat"	平顶
"chinese_curved"	中式曲面屋顶，举折屋面 + 飞檐翘角。需配合 eaveCurveHeight 和 curveProfile
"chinese_pagoda"	中式重檐屋顶，多层叠加。需配合 tiers、shrinkFactor 等参数。适用于圆形或矩形平面
示例：

json
{
  "type": "roof",
  "id": "main_roof",
  "roofType": "chinese_curved",
  "span": 12,
  "depth": 8,
  "height": 4,
  "thickness": 0.3,
  "eaveCurveHeight": 0.8,
  "material": "tile"
}
引擎处理说明：

屋顶的底面中心位于其覆盖矩形区域的中心上方。

chinese_curved 屋顶的檐口曲面由 eaveCurveHeight 控制翘起量，curveProfile 控制举折曲线形态。

chinese_pagoda 示例：

```json
{
  "type": "roof",
  "id": "temple_roof",
  "roofType": "chinese_pagoda",
  "span": 10,
  "depth": 10,
  "height": 6,
  "tiers": 3,
  "tierHeight": 2,
  "eaveOutset": 0.8,
  "shrinkFactor": 0.7,
  "thickness": 0.2,
  "material": "tile"
}
```

引擎处理说明：

chinese_pagoda 从底层到顶层按 tiers 层递减收缩。每层为一个独立坡面 + 檐口底面。底层跨度由 baseSpan/depth 或 span/depth 确定，上层按 shrinkFactor 逐层缩小。tierHeight 为各层层高。eaveOutset 控制檐口外挑宽度。

六、opening — 门窗洞口
语义：在指定墙体上穿透一个洞口，用于放置门或窗。洞口底面中点位于 from，方向沿父墙体的法向。

参数：

字段	类型	必需	说明
type	string	是	固定值 "opening"
id	string	是	构件唯一标识
parentWall	string	是	父墙体 ID
from	Vec3	是	洞口底面中点的局部坐标
width	number	是	洞口宽度（米）
height	number	是	洞口高度（米）
style	string	是	洞口样式，见下方枚举
material	string	否	引用材质库中的材质名（用于门扇/窗扇）
style 枚举：

值	说明
"rectangular"	矩形洞口
"arched"	拱形洞口（半圆拱）
"gothic"	哥特式尖拱洞口
"circular"	圆形洞口（如圆窗）
示例：

json
{
  "type": "opening",
  "id": "main_door",
  "parentWall": "front_wall",
  "from": [4.5, 0, 0],
  "width": 1.2,
  "height": 2.4,
  "style": "arched",
  "material": "oak_door"
}
引擎处理说明：

洞口从父墙体网格中减去对应区域。

若指定 material，引擎自动生成门扇或窗扇覆盖洞口。

七、stair — 楼梯
语义：从起点 from 上升至终点 to 的阶梯序列。楼梯宽度为 width。

参数：

字段	类型	必需	说明
type	string	是	固定值 "stair"
id	string	是	构件唯一标识
from	Vec3	是	起步点，局部坐标
to	Vec3	是	到达点，局部坐标
stepCount	number	否	步数。若为 0 或不设置，引擎根据人体工学自动计算
stepDepth	number	否	踏面深度（米）。不设置则自动计算
stepHeight	number	否	踏步高度（米）。不设置则自动计算
width	number	是	楼梯宽度（米）
material	string	否	引用材质库中的材质名
示例：

json
{
  "type": "stair",
  "id": "main_stair",
  "from": [0, 0, 0],
  "to": [5, 3, 0],
  "width": 1.2,
  "material": "stair_wood"
}
引擎处理说明：

自动计算：水平距离 = |to.x - from.x| + |to.z - from.z|，高差 = to.y - from.y。

人体工学范围：踏步高 0.15–0.20m，踏面深 0.26–0.35m。引擎在此范围内搜索最优整数步数。

若指定 stepCount 但 stepHeight 与总高差不匹配，微调 stepHeight 以适应精确高差。

八、furniture — 参数化家具
语义：可放置于建筑内部的可复用家具。由 subtype 决定具体形态。

参数：

字段	类型	必需	说明
type	string	是	固定值 "furniture"
id	string	是	构件唯一标识
subtype	string	是	家具类型，见下方枚举
position	Vec3	是	底面中心，局部坐标
style	string	否	风格标签（如 "rustic_wooden"）
dimensions	object	是	{ "width": 2, "depth": 1.2, "height": 0.75 }
material	string	否	引用材质库中的材质名
subtype 枚举：

值	说明
"table"	桌
"chair"	椅
"bookshelf"	书柜/架
"bed"	床
"lamp"	灯具（自带发光材质）
"tile"	瓦片/砖块。适用于 placement 批量生成。引擎生成一个长方体盒体，根据 dimensions.width（宽）、depth（深/长）、height（厚）决定尺寸
示例：

json
{
  "type": "furniture",
  "id": "dining_table",
  "subtype": "table",
  "position": [0, 0, 0],
  "style": "rustic_wooden",
  "dimensions": { "width": 2, "depth": 1.2, "height": 0.75 },
  "material": "oak"
}
引擎处理说明：

每种 subtype 有预设的比例模板。dimensions 在模板基础上缩放。

灯具（"lamp"）需包含发光部分，发光颜色和强度由材质的 emissive 字段控制。

九、dense_brick — 高分辨率体积砖块
语义：由三维体素网格组成的雕刻细节。通过等值面提取算法重建为三角网格。

参数：

字段	类型	必需	说明
type	string	是	固定值 "dense_brick"
id	string	是	构件唯一标识
resolution	[number,number,number]	是	[x体素数, y体素数, z体素数]，各维 ≥ 8
origin	Vec3	是	体素数据最小角，局部坐标
data	string	是	base64+gzip 编码的体素数据（RLE 或八叉树）
material	string	否	引用材质库中的材质名
method	string	否	"marching_cubes"（平滑）或 "dual_contouring"（锐边）。不指定时自动选择
attachment	object	否	{ "parent": "构件ID", "mapping": "cylindrical" }。将体素网格附着到父构件表面。mapping 可选值："planar"（平面映射）、"cylindrical"（圆柱映射）、"spherical"（球面映射）
示例：

json
{
  "type": "dense_brick",
  "id": "dragon_motif",
  "resolution": [128, 256, 128],
  "origin": [0, 0.5, 0],
  "data": "<base64_gzip_voxel_data>",
  "material": "gold_paint",
  "attachment": { "parent": "carved_column", "mapping": "cylindrical" }
}
引擎处理说明：

体素数据先解压，再根据 method 进行等值面提取。

若 attachment 指定，体素坐标映射到父构件表面（"cylindrical" 映射：体素绕圆柱表面卷曲；"planar" 映射：平贴到表面指定区域；"spherical" 映射：体素绕球面分布）。

若体素包含 RGBA 通道，material 可省略，颜色直接来自体素数据。

十、body — 骨架变形（化身专用）
语义：定义化身身体的比例和形态。由原语引擎编译为化身的完整网格。

参数：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"body"` |
| `id` | string | 是 | 构件唯一标识 |
| `height` | number | 是 | 身高（米），范围 0.5–2.5 |
| `build` | string | 是 | 体型："lean"（纤瘦）、"athletic"（健硕）、"stout"（矮壮） |
| `headShape` | string | 是 | 头型："round"、"oval"、"angular" |
| `armLength` | number | 是 | 臂长比例，0.5–1.5，1.0 为正常 |
| `legLength` | number | 是 | 腿长比例，0.5–1.5，1.0 为正常 |
| `cloakLength` | number | 是 | 斗篷长度（米），0.3–1.5 |
| `hoodUp` | boolean | 是 | 兜帽是否戴上 |
| `material` | string | 否 | 引用材质库中的材质名（默认 "avatar_skin"） |
示例：

json
{
  "type": "body",
  "id": "avatar_body",
  "height": 1.72,
  "build": "lean",
  "headShape": "oval",
  "armLength": 0.65,
  "legLength": 0.7,
  "cloakLength": 1.0,
  "hoodUp": false,
  "material": "avatar_skin"
}
引擎处理说明：

引擎根据骨架参数生成头部、躯干、四肢和斗篷的几何体。

所有化身使用相同的确定性生成算法，相同参数输出相同网格。

具体身体比例生成规则参见 wild-core 引擎参考实现。

版本兼容
本文件定义的所有构件类型均为 v1.0 标准。未来版本可能增加新的构件类型、新字段或新的 style/subtype 枚举值，但不会删除或修改任何已有定义。

许可
本构件库定义以 MIT 协议开源。任何原语引擎实现可自由引用本文档定义的构件参数和语义。