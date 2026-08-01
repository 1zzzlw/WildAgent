---
doc_type: component
doc_scope: generation
knowledge_layer: architecture
entity_type: component
entity_name: proposed_component_extensions
topic: constraints
wild_version: "1.1"
status: proposed
authority: domain_reference
source: WILD蓝图构件与组合方式完整规范(1).md
keywords:
  - 构件扩展提案
  - proposed component
  - door
  - window
  - truss
  - railing
---

# WILD 构件扩展提案分类

> 来源：用户提供的《WILD蓝图构件与组合方式完整规范(1)》v2.0。
> 状态：本文只保存需求分类和设计意图；下列类型尚未进入当前 WILD v1.1 Schema 或构件注册表，不参与正式蓝图生成。

## 结构与交通扩展提案

<!-- rag-meta
entity_type: structural_component
entity_name: proposed_structural_transport_types
topic: definition
status: proposed
authority: domain_reference
keywords: ramp, railing, truss, 坡道, 栏杆, 桁架
-->

| 提议类型 | 原文设计意图 | 当前可用降级方式 |
|---|---|---|
| `ramp` | 连续倾斜板、可选中间平台与表面类型 | 用 `primitive.box` 旋转，平台另用 `floor` 或 `primitive.box` |
| `railing` | 沿路径生成立杆、扶手和填充 | 用 `column`、`beam` 或 `primitive` 组合 |
| `truss` | 生成多种桁架杆件网络 | 用多个 `beam` 或 `primitive` 明确列出杆件 |

## 门窗与装饰扩展提案

<!-- rag-meta
entity_type: opening
entity_name: proposed_opening_related_types
topic: definition
status: proposed
authority: domain_reference
keywords: door, window, mullion, cornice, canopy, 门, 窗, 窗棂, 檐口, 雨棚
-->

| 提议类型 | 原文设计意图 | 当前可用降级方式 |
|---|---|---|
| `door` | 引用洞口生成门框、门扇与铰链 | `opening` 负责洞口，静态门扇用 `primitive` |
| `window` | 引用洞口生成窗框、玻璃和开启扇 | `opening` 负责洞口，窗框和玻璃用 `primitive` |
| `mullion` | 在洞口内按图案生成分格条 | 用多个细 `primitive.box` 组合 |
| `cornice` | 沿墙路径挤出二维线脚截面 | 用 `primitive.profile_sweep` 显式给出路径 |
| `canopy` | 从墙面或门上方生成挑板与支撑 | 用 `primitive.box`、`beam`、`column` 组合 |

## 场地与屋顶附属扩展提案

<!-- rag-meta
entity_type: site_component
entity_name: proposed_site_roof_accessory_types
topic: definition
status: proposed
authority: domain_reference
keywords: terrain, chimney, 地形, 烟囱, roof penetration
-->

| 提议类型 | 原文设计意图 | 当前可用降级方式 |
|---|---|---|
| `terrain` | 高度图地表与按高度分区材质 | 简单场地用 `floor` 或 `primitive`；复杂地形暂不表达 |
| `chimney` | 烟囱外壳、烟道、顶帽和屋顶穿孔 | 外观用 `primitive` 组合；不支持自动屋顶裁切 |

## 提议的自动组合机制

原文中的 `resolveDoorPlacement`、`resolveWindowPlacement`、`resolveMullionLayout`、`resolveStairRailing`、`resolveFloorRailing`、`resolveCornicePath`、`resolveRoofTruss`、`resolveRampConnection`、`resolveChimneyPenetration`、`resolveDoorCanopy`、`resolveTerrainSnap` 和 `resolveMemberSupports` 均属于实现提案。只有在 Schema、构件注册表、resolver 实现和回归测试同时落地后，才能把对应块升级为 `experimental` 或 `supported`。
