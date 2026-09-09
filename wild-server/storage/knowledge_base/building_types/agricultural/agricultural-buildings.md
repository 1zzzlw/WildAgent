---
entity_name: agricultural_buildings
topic: composition
status: supported
authority: maintainer
source: building_types/agricultural/agricultural-buildings.md
building_category: agricultural
primary_terms:
  - 农业建筑
synonyms: []
applies_to:
  - 农业建筑
---

# 农业建筑：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 温室

<!-- rag-meta
entity_type: building
entity_name: greenhouse
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 温室
  - 日光温室
  - 农业建筑
synonyms: []
applies_to:
  - 温室
  - 日光温室
  - 农业建筑
-->

- 适用条件：用户或已批准方案明确采用温室；名称本身不决定全部构件。
- 类型特征：种植空间、采光围护、通风与骨架的联系。
- 条件关系：选择透光覆盖时分清透明面板和支撑，保持净空；通风口及设备按任务选取。
- WILD 映射与边界：roof/wall/primitive 可表达覆盖；框架用 beam/column；覆膜透明度是视觉参数，不能证明种植环境性能。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 畜禽饲养场

<!-- rag-meta
entity_type: building
entity_name: livestock
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 畜禽饲养场
  - 养殖场
  - 鸡舍
  - 畜舍
synonyms: []
applies_to:
  - 畜禽饲养场
  - 养殖场
  - 鸡舍
  - 畜舍
-->

- 适用条件：用户或已批准方案明确采用畜禽饲养场；名称本身不决定全部构件。
- 类型特征：饲养空间、通道、通风开口及围护的联系。
- 条件关系：开放围护或封闭围护由饲养任务决定；围栏、出入口与设备路径协调，不固定低墙高度。
- WILD 映射与边界：wall/door/window 与骨架表达几何；栏杆参数不等于专业养殖围栏或防疫性能。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 粮仓

<!-- rag-meta
entity_type: building
entity_name: granary
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 粮仓
  - 圆形粮仓
  - 筒仓
synonyms: []
applies_to:
  - 粮仓
  - 圆形粮仓
  - 筒仓
-->

- 适用条件：用户或已批准方案明确采用粮仓；名称本身不决定全部构件。
- 类型特征：储粮空间与装卸口、围护的联系；平房仓和圆仓分别设计。
- 条件关系：选用圆仓时圆墙、楼板和顶部围护共享中心与边界；通行开口需有效墙段宿主。
- WILD 映射与边界：圆楼板用 floor.circle，圆墙按受支持 arc 路径；整圆墙开口需验证路径，必要时拆成单段弧墙；不推断储粮性能。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 农机站

<!-- rag-meta
entity_type: building
entity_name: farm_machinery
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 农机站
  - 农机库
synonyms: []
applies_to:
  - 农机站
  - 农机库
-->

- 适用条件：用户或已批准方案明确采用农机站；名称本身不决定全部构件。
- 类型特征：农机停放维修、通行与屋盖支撑的联系。
- 条件关系：入口和内部净空根据本次农机尺寸确定；柱梁避免妨碍已指定的通行路径。
- WILD 映射与边界：floor/column/beam/wall/roof 与门表达几何；机械设备用支持的 primitive 近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
