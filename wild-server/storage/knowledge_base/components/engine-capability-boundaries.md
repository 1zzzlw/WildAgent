---
doc_type: component
doc_scope: generation
knowledge_layer: constraint
entity_type: component
entity_name: engine_capability_boundaries
topic: constraints
wild_version: "1.1"
status: supported
authority: engine
source: wild-web/src/wild-core/src/primitive/registry.ts
keywords:
  - 引擎能力边界
  - engine capability
  - supported type
  - proposed type
  - resolver
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
keywords: geometry.elements, supported type, WILD type, 构件类型
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

`geometry.templates`、`geometry.instances` 和 `geometry.placements` 是蓝图顶层的复用或排布系统，不是 `geometry.elements` 中的独立 `type`。`placement` 不能写成元素对象。

## 柱、梁、楼板与桁架边界

<!-- rag-meta
entity_type: structural_component
entity_name: structural_engine_boundaries
topic: constraints
status: supported
authority: engine
keywords: column, beam, floor, truss, crossSection, 结构构件
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
keywords: 门, door, opening, primitive, parentWall, 门扇
-->

WILD v1.1 没有 `type: "door"`。门洞使用 `opening`，其 `style` 只能是 `rectangular`、`arched`、`gothic`、`circular`。需要静态门扇外观时，可在洞口位置组合 `primitive`；`leafCount`、`hingeSide`、`openAngle` 和 `parentOpening` 不是当前 `opening` 字段，不能当作已支持能力输出。

## 窗与窗棂的当前表达边界

<!-- rag-meta
entity_type: window
entity_name: window_engine_boundary
topic: constraints
status: supported
authority: engine
keywords: 窗, window, opening, mullion, primitive, parentWall
-->

WILD v1.1 没有 `type: "window"` 或 `type: "mullion"`。窗洞使用 `opening`；静态窗框、玻璃和分格可用 `primitive` 组合近似。`sashType`、`sashCount`、`muntinPattern`、`cols`、`rows` 和 `parentOpening` 均不是当前 `opening` 字段。

`opening` 只能引用 `parentWall`，不能通过 `parentRoof` 在屋顶上开天窗。当前天窗只能用屋顶上方的近似几何表达，不能声称完成屋顶布尔裁切。

## 屋顶、檐口、雨棚与烟囱边界

<!-- rag-meta
entity_type: roof
entity_name: roof_engine_boundary
topic: constraints
status: supported
authority: engine
keywords: roof, cornice, canopy, chimney, profile_sweep, 屋顶, 檐口, 雨棚, 烟囱
-->

- `roof` 是当前类型，六种 `roofType` 由 Schema 支持，但注册表将整体能力标为 partial。
- `cornice`、`canopy`、`chimney` 不是当前类型。静态檐口适合用 `primitive.shape: "profile_sweep"`，雨棚和烟囱可用 `primitive`、`beam`、`column` 组合近似。
- 当前引擎没有 `resolveCornicePath`、`resolveDoorCanopy` 或 `resolveChimneyPenetration`，因此不会自动沿墙挤出檐口，也不会自动生成雨棚或在屋顶上做烟囱布尔裁切。

## 当前实际运行的空间解析机制

<!-- rag-meta
entity_type: assembly
entity_name: implemented_spatial_resolvers
topic: assembly
status: supported
authority: engine
keywords: resolver, resolveWallJoints, resolveOpenings, resolveBeamSupports, expandTemplates, expandPlacements
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
