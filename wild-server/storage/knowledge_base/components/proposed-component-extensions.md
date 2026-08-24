---
knowledge_layer: architecture
entity_type: component
entity_name: proposed_component_extensions
topic: constraints
status: proposed
authority: domain_reference
source: WILD蓝图构件与组合方式完整规范(1).md
primary_terms:
  - 构件扩展提案
  - proposed component
  - truss
synonyms: []
---

# WILD 构件扩展提案分类

> 来源：用户提供的《WILD蓝图构件与组合方式完整规范(1)》v2.0。
> 状态：本文只保存仍未实现的需求分类和设计意图；已进入 `geometry.components` 的 9 类组合构件不再列为未实现类型。

## 结构与交通扩展提案

<!-- rag-meta
entity_type: structural_component
entity_name: proposed_structural_transport_types
topic: definition
status: proposed
authority: domain_reference
primary_terms:
  - truss
  - 桁架
synonyms: []
-->

| 提议类型 | 原文设计意图 | 当前可用降级方式 |
|---|---|---|
| `truss` | 生成多种桁架杆件网络 | 用多个 `beam` 或 `primitive` 明确列出杆件 |

## 门窗与装饰扩展提案

<!-- rag-meta
entity_type: opening
entity_name: proposed_opening_related_types
topic: definition
status: proposed
authority: domain_reference
primary_terms:
  - mullion
  - 窗棂
synonyms: []
-->

| 提议类型 | 原文设计意图 | 当前可用降级方式 |
|---|---|---|
| `mullion` | 在洞口内按图案生成分格条 | 用多个细 `primitive.box` 组合 |

## 场地与屋顶附属扩展提案

<!-- rag-meta
entity_type: site_component
entity_name: proposed_site_roof_accessory_types
topic: definition
status: proposed
authority: domain_reference
primary_terms:
  - terrain
  - 地形
  - roof penetration
  - CSG
synonyms: []
-->

| 提议类型 | 原文设计意图 | 当前可用降级方式 |
|---|---|---|
| `terrain` | 高度图地表与按高度分区材质 | 简单场地用 `floor` 或 `primitive`；复杂地形暂不表达 |

## 提议的自动组合机制

仍未实现的自动机制包括复杂窗格布局、桁架网络、坡道中间平台、烟囱/天窗屋顶真实穿透、地形贴合和通用构件约束求解。当前墙体、楼板、路径和基础屋顶局部依附已经由组合编译器负责，但不能等同于通用布尔/CSG 或结构安全求解。
