---
knowledge_layer: wild_schema
entity_type: roof
entity_name: roof_and_eaves_family
topic: parameters
status: supported
authority: schema
source: wild-web/wild-lang/schema.json
primary_terms:
  - 屋顶
  - 屋檐
  - roof
  - canopy
  - roofType
  - cornice
synonyms: []
---

# 屋顶、屋檐与顶部围护构件

> 依据：当前 WILD v1.1 Schema、构件注册表，以及用户提供的《WILD蓝图构件与组合方式完整规范(1)》。
> 用途：区分已支持的 roof 与尚未实现的 cornice、canopy、chimney。
> RAG 关键词：roof、cornice、canopy、屋顶、屋檐、檐口、雨棚、gable、hip、dome、flat、chinese_curved、chinese_pagoda

---
## 当前支持的 roof

<!-- rag-meta
entity_type: roof
entity_name: supported_roof_type
topic: parameters
status: supported
authority: schema
primary_terms:
  - roof
  - roofType
  - gable
  - hip
  - dome
  - flat
  - chinese_curved
  - chinese_pagoda
synonyms: []
-->

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 屋顶 | `roof` | id, roofType, span, depth, height, thickness | 类型: gable/hip/dome/flat/chinese_curved/chinese_pagoda |

`position` 可选；缺失且场景至少有三面墙时，引擎可根据有效墙体边界补位置，并只扩大不足的 `span`、`depth`。当前注册表将 `roof` 整体标为 partial，因此复杂中式曲面和重檐仍应通过实际渲染验证。

## 5.4 屋顶类型速查

<!-- rag-meta
entity_type: roof
entity_name: roof_type_reference
topic: classification
status: experimental
authority: domain_reference
primary_terms:
  - roofType
  - 屋顶选型
  - gable
  - hip
  - dome
  - flat
  - chinese_curved
  - chinese_pagoda
synonyms: []
-->

| 屋顶类型 | roofType | 适用建筑 |
|:---:|:---:|:---|
| 人字坡顶 | `gable` | 木屋、现代别墅、新中式别墅、厂房、平房仓 |
| 四坡顶 | `hip` | 欧式庄园、新中式别墅 |
| 穹顶 | `dome` | 祈年殿宝顶、教堂、筒仓顶 |
| 平顶 | `flat` | 现代别墅(架空层)、住宅高层、办公、商业 |
| 中式曲面 | `chinese_curved` | 中式传统别墅(四合院)、庙宇单檐、园林建筑 |
| 中式重檐 | `chinese_pagoda` | 祈年殿、塔（tiers=2~3） |

类型枚举由 Schema 支持；“适用建筑”属于领域建议，不代表每种复杂建筑细节都能由单个 `roof` 自动完成。

## 檐口、雨棚和烟囱提案

<!-- rag-meta
entity_type: roof
entity_name: proposed_roof_accessories
topic: constraints
status: proposed
authority: domain_reference
primary_terms:
  - cornice
  - canopy
  - chimney
  - 檐口
  - 雨棚
  - 烟囱
synonyms: []
-->

`cornice`、`canopy`、`chimney` 目前不是独立 WILD 类型。静态檐口可用 `primitive.profile_sweep`，雨棚和烟囱外观可用 `primitive`、`beam`、`column` 组合；当前没有自动沿墙挤出、门头雨棚注入或屋顶穿孔机制。

## 维护说明

- 单个屋顶构件参数和 `roofType` 适配放在本文档，并保持 Schema 依据。
- 某类建筑的完整屋顶做法，例如体育场膜屋面、温室采光顶、中式重檐，放在对应 `building_types/` 文档。
- 跨建筑复用的屋顶组装顺序放在 `recipes/`。
