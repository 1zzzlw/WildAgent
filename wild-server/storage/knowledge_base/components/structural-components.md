---
doc_type: component
doc_scope: generation
knowledge_layer: architecture
entity_type: structural_component
entity_name: structural_component_family
topic: parameters
wild_version: "1.1"
status: experimental
authority: domain_reference
source: components/structural-components.md
keywords:
  - 结构构件
  - column
  - beam
  - floor
  - truss
---

# 结构构件：柱、梁、楼板、桁架

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理承重骨架构件的 WILD type、核心参数和常见变体。
> RAG 关键词：结构构件、承重骨架、column、beam、floor、truss、柱、梁、楼板、桁架

---
## 结构构件（承重骨架）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 柱子 | `column` | base, height, crossSection, style | 截面: circular/square/rectangular；风格: doric/ionic/corinthian/modern/chinese_wooden |
| 梁 | `beam` | from, to, crossSection, width, height | 截面: rect/circular/i-beam；支持曲线梁 |
| 楼板 | `floor` | from, to, thickness, shape | 形状: rect/circle；支持 surfaces 纹理 |
| 桁架 | `truss` | from, to, height, trussType | 形式: king_post/queen_post/fink/howe/pratt/warren |

## 维护说明

结构构件如果只是风格、尺寸、材料差异，优先维护在本文档；如果是某类建筑的完整构件配方，放入 `building_types/`；如果是跨建筑的组合顺序，放入 `recipes/`。
