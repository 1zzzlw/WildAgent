---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: components_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: components/README.md
keywords:
  - 构件索引
  - components
  - WILD type
---

# 构件知识索引

> 依据：当前 WILD v1.1 Schema、引擎注册表，以及分类后的领域资料。
> 用途：记录“用什么构件、构件有哪些参数和变体”，并区分已实现类型与扩展提案。
> RAG 关键词：WILD 构件、column、beam、floor、wall、roof、opening、door、window、mullion、stair、railing

---
## WILD v1.1 已注册类型

> 完整字段见 `BLUEPRINT-SPEC-FULL.md`；能力状态与降级方式见 `engine-capability-boundaries.md`。

### 结构构件（承重骨架）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 柱子 | `column` | base, height, bottomRadius, topRadius, style | 当前为圆形截面；五种 style |
| 梁 | `beam` | from, to, crossSection, width, height | 截面: rect/circular/i-beam；支持曲线梁 |
| 楼板 | `floor` | from, to/radius, thickness, shape | 形状: rect/circle |

### 围护构件（空间封闭）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 墙体 | `wall` | from, to, thickness, curve | 曲线: line/arc/ellipse/catenary |
| 屋顶 | `roof` | position, span, depth, height, roofType | 类型: gable/hip/dome/flat/chinese_curved/chinese_pagoda |
| 洞口 | `opening` | parentWall, from, width, height, style | 风格: rectangular/arched/gothic/circular |

### 辅助构件（功能附加）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 楼梯 | `stair` | from, to, width, stepCount | 缺省时自动推算踏步 |
| 家具 | `furniture` | position, dimensions, subtype | 子类型: table/chair/bed/lamp/bookshelf/tile |
| 密集体素 | `dense_brick` | resolution, origin, data | experimental |
| 人形 | `body` | height, build, headShape 等 | 简化人物 |
| 通用形体 | `primitive` | shape 与对应几何参数 | box/sphere/cylinder/profile_sweep |

### 顶层复用与排布系统

| 系统 | 所在位置 | 当前边界 |
|---|---|---|
| 组合构件 | `geometry.components` | 支持 door/window/railing/canopy/balcony/ramp/bay_window/cornice/chimney；渲染前展开为 Core 元素 |
| 模板 | `geometry.templates` + `geometry.instances` | 引用模板并应用实例变换 |
| 表面排布 | `geometry.placements` | 当前只解析 gable 屋顶 left/right 表面 |

### 尚未实现的专用类型

`mullion`（作为独立类型）、`truss` 和 `terrain` 仍为 `proposed`，不能写入正式 WILD。9 类组合组件只能写入 `geometry.components`，不能写入 `geometry.elements`。屋顶真实穿透、通用 CSG 和复杂地形仍未实现。

## 当前拆分

| 文件 | 内容 |
|---|---|
| `engine-capability-boundaries.md` | 当前可生成类型、resolver 与门窗等能力边界 |
| `proposed-component-extensions.md` | 未实现专用类型和自动组合机制提案 |
| `structural-components.md` | 柱、梁、楼板和桁架降级方式 |
| `walls.md` | 墙体分类、受力角色、材料、构造方式、模数规格 |
| `doors-supported.md` | 当前受支持的基础静态 door 参数、示例与能力边界 |
| `doors.md` | 基础静态 door 之外的门型领域资料和未来扩展提案 |
| `windows-supported.md` | 当前受支持的基础静态 window 参数、示例与能力边界 |
| `windows.md` | 基础静态 window 之外的窗型与 mullion 图案扩展提案 |
| `railings.md` | 当前受支持的显式路径 railing 参数、示例与能力边界 |
| `composite-components-second-batch.md` | 雨棚、阳台、坡道、凸窗、檐口、烟囱的正式 Schema 与边界 |
| `roofs-and-eaves.md` | 已支持屋顶与檐口、雨棚、烟囱提案边界 |
