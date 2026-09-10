---
entity_name: factories_and_warehouses
topic: composition
status: supported
authority: maintainer
source: building_types/industrial/factories-and-warehouses.md
building_category: industrial
primary_terms:
  - 工业与仓储建筑
synonyms: []
applies_to:
  - 工业与仓储建筑
---

# 工业与仓储建筑：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 厂房

<!-- rag-meta
entity_type: building
entity_name: factory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 厂房
  - 工业建筑
  - 单层厂房
  - 轻钢厂房
synonyms: []
applies_to:
  - 厂房
  - 工业建筑
  - 单层厂房
  - 轻钢厂房
-->

- 适用条件：用户或已批准方案明确采用厂房；名称本身不决定全部构件。
- 类型特征：生产空间、运输路径、围护与支撑体系之间的联系。
- 条件关系：已指定设备和通行净空不得被柱网占用；跨度、层高与门洞按任务推导；屋盖按真实支点布置。
- WILD 映射与边界：column/beam/primitive 表达骨架，wall/window/door 表达围护；卷帘门只作外观近似，无卷绕机构。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 仓储建筑

<!-- rag-meta
entity_type: building
entity_name: warehouse
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 仓库
  - 仓储
  - 粮仓
  - 冷链仓库
synonyms: []
applies_to:
  - 仓库
  - 仓储
  - 粮仓
  - 冷链仓库
-->

- 适用条件：用户或已批准方案明确采用仓储建筑；名称本身不决定全部构件。
- 类型特征：储存、装卸、交通和围护的联系；储存类型决定是否需要特殊空间。
- 条件关系：选择筒仓才使用圆形围护；选定冷链分区才表达隔层；开窗和门洞依任务而非固定数量。
- WILD 映射与边界：wall 曲线与 floor 圆形可表达圆仓；厚墙和材质名称不证明防潮、保温或承载能力。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 工业上楼

<!-- rag-meta
entity_type: building
entity_name: multistorey_factory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 工业上楼
  - 多层厂房
  - 高层厂房
synonyms: []
applies_to:
  - 工业上楼
  - 多层厂房
  - 高层厂房
-->

- 适用条件：用户或已批准方案明确采用工业上楼；名称本身不决定全部构件。
- 类型特征：竖向叠合生产空间与货运交通的联系。
- 条件关系：楼层模数与上下支撑协调；货运井、通道和设备净空按任务保留；不因高层自动增大构件截面当作验算。
- WILD 映射与边界：floor/wall/column/beam/stair 表达几何；货梯井用 wall 围合，不提供荷载分析或运行货梯。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
