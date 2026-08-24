---
knowledge_layer: constraint
entity_type: component
entity_name: engine_capability_boundaries
topic: constraints
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
primary_terms:
  - 引擎能力边界
  - engine capability
  - supported type
  - proposed type
  - resolver
synonyms: []
---

# WILD v1.1 当前引擎构件能力边界

> 依据：`wild-web/wild-lang/schema.json`、`wild-web/src/wild-core/types.ts`、`wild-web/src/wild-core/src/primitive/registry.ts`、`resolver.ts` 与 `expander.ts`。
> 用途：在领域资料与当前实现发生冲突时，以本文列出的类型、状态和降级方式为准。

## 当前可写入 geometry.elements 的类型

<!-- rag-meta
entity_type: schema
entity_name: supported_geometry_element_types
topic: constraints
status: supported
authority: engine
primary_terms:
  - geometry.elements
  - supported type
  - WILD type
  - 构件类型
synonyms: []
-->

| `type` | 引擎状态 | 当前能力摘要 |
|---|---|---|
| `wall` | stable | 直线或曲线路径墙体；配合 `opening` 裁切 |
| `floor` | stable | 矩形或圆形楼板 |
| `column` | partial | 圆形参数化柱；柱式细部仍在补齐 |
| `beam` | partial | `rect`、`circular`、`i-beam` 截面，可带曲线路径 |
| `roof` | partial | `gable`、`hip`、`dome`、`flat`、`chinese_curved`、`chinese_pagoda` |
| `opening` | partial | 墙体洞口与门窗覆盖几何；必须引用 `parentWall` |
| `stair` | stable | 直跑楼梯；缺省踏步数时自动推算 |
| `furniture` | partial | `table`、`chair`、`bookshelf`、`bed`、`lamp`、`tile` |
| `dense_brick` | experimental | 体素细节，等值面提取仍属实验能力 |
| `body` | partial | 简化参数化人物 |
| `primitive` | stable | 通用 `box`、`sphere`、`cylinder`、`profile_sweep` |

`geometry.components`、`geometry.templates`、`geometry.instances` 和 `geometry.placements` 是 `geometry` 下的高级组合或排布系统，不是 `geometry.elements` 中的独立 `type`。所有组合组件和 `placement` 都不能写成元素对象。

## 当前可写入 geometry.components 的类型

<!-- rag-meta
entity_type: component
entity_name: supported_composite_component_types
topic: schema
status: supported
authority: engine
primary_terms:
  - geometry.components
  - component compiler
  - door
  - window
  - railing
  - 组合构件编译器
synonyms: []
-->

当前组合构件编译器支持 10 类组件。它们在进入 wild-core 前展开为 `opening`、`primitive`、`beam` 等基础元素，不会在构件注册表中增加同名 builder。

| `component.type` | 必填字段 | 编译结果摘要 |
|---|---|---|
| `door` | `id`、`parentWall`、`from`、`width`、`height` | `opening` 与三段 `primitive.box` 门框 |
| `window` | `id`、`parentWall`、`from`、`width`、`height` | `opening`、四边窗框和可选窗棂 |
| `railing` | `id`、`path`、`height` | 等距 `primitive.cylinder` 立杆和分段 `beam` 横杆 |
| `canopy` | `id`、`parentWall`、`from`、`width`、`depth`、`thickness` | 雨棚板和可选支柱 |
| `balcony` | `id`、`parentWall`、`from`、`width`、`depth`、`slabThickness` | 悬挑板和 U 形栏杆 |
| `ramp` | `id`、`from`、`to`、`width`、`thickness` | 直线坡面和可选双侧栏杆 |
| `bay_window` | `id`、`parentWall`、`from`、`width`、`height`、`projectionDepth` | 墙洞、窗框和投影窗体 |
| `cornice` | `id`、`path`、`profile` | `primitive.profile_sweep` 檐口 |
| `chimney` | `id`、`position`、`width`、`depth`、`height` | 四面薄壁烟囱和压顶 |
| `light` | `id`、`position`、`fixtureType`、`lightType`、`initiallyOn` | 灯泡/台灯网格、光源参数和右键循环开关 |

基础元素和组合构件共享 ID 命名空间。组合构件源数据保留在 Blueprint 中，渲染时对副本展开；生成后的子元素 ID 由组件 ID 确定性派生。

## 柱、梁、楼板与桁架边界

<!-- rag-meta
entity_type: structural_component
entity_name: structural_engine_boundaries
topic: constraints
status: supported
authority: engine
primary_terms:
  - column
  - beam
  - floor
  - truss
  - crossSection
  - 结构构件
synonyms: []
-->

- `column` 当前必填 `base`、`height`、`bottomRadius`、`topRadius`、`style`；Schema 没有方柱或矩形柱的 `crossSection`、`bottomSide`、`bottomWidth` 等字段。
- `beam` 才使用 `crossSection`、`width` 和 `height`，并允许 `rect`、`circular`、`i-beam`。
- `floor` 支持 `rect` 和 `circle`；当前 Schema 没有 `surfaces` 程序化纹理字段。
- `truss` 不是 WILD v1.1 类型。需要桁架外观时，用多个 `beam` 或 `primitive` 组合近似；不要输出 `type: "truss"`。

## 门的当前表达边界

<!-- rag-meta
entity_type: door
entity_name: door_engine_boundary
topic: constraints
status: supported
authority: engine
primary_terms:
  - 门
  - door
  - opening
  - primitive
  - parentWall
  - 门扇
synonyms: []
-->

`geometry.elements` 仍然没有 `type: "door"`。标准门应在 `geometry.components` 中写 `type: "door"`；编译器生成矩形 `opening` 和三段门框。`from` 固定为 `[沿父墙弧长距离, 底部世界Y, 墙体法向偏移]`，支持直线墙和单段曲线墙。

门组件可选 `interaction`，支持 `swing` 或 `slide`、左右方向、最大开角/位移和初始开启状态。前端左键仍负责选择高亮，右键命中门面执行开合；运行时动画进度不写回 Blueprint。当前仍不支持多门扇、碰撞或独立厚门扇。

## 窗与窗棂的当前表达边界

<!-- rag-meta
entity_type: window
entity_name: window_engine_boundary
topic: constraints
status: supported
authority: engine
primary_terms:
  - 窗
  - window
  - opening
  - mullion
  - primitive
  - parentWall
synonyms: []
-->

`geometry.elements` 没有 `type: "window"` 或 `type: "mullion"`。标准静态窗应写入 `geometry.components`，其中 `verticalMullions` 和 `horizontalMullions` 控制横竖窗棂数量；窗棂不是独立组件类型。

窗组件可依附直线墙或单段曲线墙，并可选与门相同的 `interaction` 右键开合配置。当前仍不支持多窗扇独立状态、复杂窗格图案、碰撞或 `parentOpening`；玻璃由 `opening` 覆盖面表达。

`opening` 只能引用 `parentWall`，不能通过 `parentRoof` 在屋顶上开天窗。当前天窗只能用屋顶上方的近似几何表达，不能声称完成屋顶布尔裁切。

## 栏杆组合构件的当前边界

<!-- rag-meta
entity_type: railing
entity_name: railing_component_boundary
topic: constraints
status: supported
authority: engine
primary_terms:
  - railing
  - geometry.components
  - path
  - postSpacing
  - railLevels
  - 栏杆
synonyms: []
-->

标准静态栏杆可以写入 `geometry.components`。默认 `path` 使用世界坐标；指定 `parentFloor` 后，路径相对父楼板左下角顶面。`height` 是每个路径点上方的栏杆高度；`postSpacing` 控制立杆最大间距，`railLevels` 使用 `(0, 1]` 比例定义横杆高度。

当前栏杆不会自动读取 stair、floor 或 ramp 边界，也不执行建筑规范校核。需要楼梯栏杆时，调用方必须显式提供随楼梯升高的路径。

## 屋顶、檐口、雨棚与烟囱边界

<!-- rag-meta
entity_type: roof
entity_name: roof_engine_boundary
topic: constraints
status: supported
authority: engine
primary_terms:
  - roof
  - canopy
  - chimney
  - cornice
  - profile_sweep
  - 屋顶
  - 檐口
  - 雨棚
  - 烟囱
synonyms: []
-->

- `roof` 是当前类型，六种 `roofType` 由 Schema 支持，但注册表将整体能力标为 partial。
- `cornice`、`canopy`、`chimney` 已是 `geometry.components` 支持类型；分别展开为 `profile_sweep`、板/柱和薄壁筒体。
- `cornice` 与 `chimney` 可依附 `flat`、`gable`、`hip` 屋顶的局部坐标。烟囱只完成贴合定位和外观，尚不执行屋顶布尔裁切。

## 当前实际运行的空间解析机制

<!-- rag-meta
entity_type: assembly
entity_name: implemented_spatial_resolvers
topic: assembly
status: supported
authority: engine
primary_terms:
  - resolver
  - resolveWallJoints
  - resolveOpenings
  - resolveBeamSupports
  - expandTemplates
  - expandPlacements
synonyms: []
-->

`resolveSpatialRelations()` 当前依次运行：

1. `resolveWallJoints`：在 0.01m 的 XZ 容差内闭合墙角；
2. `resolveBeamSupports`：将接近柱顶的梁端吸附到柱顶；
3. `resolveRoofBoundary`：根据有效墙体边界补足屋顶跨度、进深和缺省位置；
4. `resolveFloorRegions`：完全没有楼板且墙体不少于三面时补一个矩形楼板；
5. `resolveStairSteps`：缺省步数时根据总升高和水平长度推算；
6. `resolveColumnOffsets`：把已嵌入墙厚范围的柱心对齐到墙中心线；
7. `resolveOpenings`：解析 `opening.parentWall`、墙体切口和开口世界位置。

另外，`expandTemplates` 展开模板实例；`expandPlacements` 目前只支持 `gable` 屋顶的 `left`、`right` 表面。资料中出现但不在上述清单内的 `resolve*` 名称，不应当作当前实现。
