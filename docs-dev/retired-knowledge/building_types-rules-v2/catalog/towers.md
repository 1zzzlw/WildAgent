---
entity_name: towers
topic: composition
status: supported
authority: maintainer
source: building_types/catalog/towers.md
building_category: mixed_use
primary_terms:
  - 塔楼
synonyms: []
applies_to:
  - 塔楼
---

# 塔楼：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 塔楼

<!-- rag-meta
entity_type: building
entity_name: tower
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 塔楼
  - 石塔
  - 中世纪石塔
  - tower
synonyms: []
applies_to:
  - 塔楼
  - 石塔
  - 中世纪石塔
  - tower
-->

- 适用条件：用户或已批准方案明确采用塔楼；名称本身不决定全部构件。
- 类型特征：竖向体量与跨层交通的联系；城垛、尖顶与防御构件按需求选择。
- 条件关系：重复楼层保持交通连续；圆塔、方塔各自推导围护与屋盖边界。
- WILD 映射与边界：wall/floor/stair/roof 表达主体；城垛用 primitive 显式布置，不固定层数和窗列。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
