---
doc_type: component
doc_scope: generation
knowledge_layer: wild_schema
entity_type: structural_component
entity_name: structural_component_family
topic: parameters
wild_version: "1.1"
status: supported
authority: schema
source: wild-web/wild-lang/schema.json
keywords:
  - 结构构件
  - column
  - beam
  - floor
  - truss
---

# 结构构件：柱、梁与楼板

> 依据：`wild-web/wild-lang/schema.json` 与当前构件注册表。
> 用途：提供可直接写入 WILD v1.1 的结构构件速查，并隔离尚未实现的桁架提案。
> RAG 关键词：结构构件、承重骨架、column、beam、floor、truss、柱、梁、楼板、桁架

---
## 当前支持的结构构件

<!-- rag-meta
entity_type: structural_component
entity_name: supported_structural_component_types
topic: parameters
status: supported
authority: schema
keywords: column, beam, floor, primitive, 柱, 梁, 楼板
-->

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 柱子 | `column` | base, height, bottomRadius, topRadius, style | 当前为圆形截面；风格: doric/ionic/corinthian/modern/chinese_wooden |
| 梁 | `beam` | from, to, crossSection, width, height | 截面: rect/circular/i-beam；支持曲线梁 |
| 楼板 | `floor` | from, to, thickness, shape | 形状: rect/circle；圆形使用 radius |
| 通用杆件或节点 | `primitive` | shape, position, dimensions/radius/path | box/sphere/cylinder/profile_sweep |

`column.crossSection`、`bottomSide`、`bottomWidth` 和 `floor.surfaces` 不在当前 Schema 中，不得作为已支持字段生成。

## 桁架的当前降级方式

<!-- rag-meta
entity_type: structural_component
entity_name: truss_fallback
topic: constraints
status: supported
authority: engine
keywords: truss, beam, primitive, 桁架, 降级
-->

当前没有 `type: "truss"`。需要桁架外观时，显式使用多根 `beam` 或 `primitive` 表达上弦、下弦和腹杆；引擎不会根据 `trussType`、`panelCount` 自动生成杆件网络。

## 专用 truss 类型提案

<!-- rag-meta
entity_type: structural_component
entity_name: proposed_truss_type
topic: definition
status: proposed
authority: domain_reference
keywords: trussType, king_post, queen_post, fink, howe, pratt, warren
-->

用户提供的完整规范提出 `truss` 类型以及 king_post、queen_post、fink、howe、pratt、warren 六种形式。该设计尚未进入 WILD v1.1 Schema、构件注册表或 resolver，只保留为扩展需求。

## 维护说明

结构类型与字段以 Schema 为准；某类建筑的结构选型放入 `building_types/`，跨构件组合顺序放入 `recipes/`，尚未实现的专用类型必须标为 `proposed`。
