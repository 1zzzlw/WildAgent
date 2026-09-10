---
entity_name: housing_dormitories_hotels
topic: composition
status: supported
authority: maintainer
source: building_types/residential/housing-dormitories-hotels.md
building_category: residential
primary_terms:
  - 住宅、宿舍与酒店
synonyms: []
applies_to:
  - 住宅、宿舍与酒店
---

# 住宅、宿舍与酒店：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 普通住宅

<!-- rag-meta
entity_type: building
entity_name: housing
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 普通住宅
  - 住宅
  - 高层住宅
synonyms: []
applies_to:
  - 普通住宅
  - 住宅
  - 高层住宅
-->

- 适用条件：用户或已批准方案明确采用普通住宅；名称本身不决定全部构件。
- 类型特征：居住单元、公共交通和外围护的关系；产权或居住人数不是几何字段。
- 条件关系：多层按实际楼层标高组织楼板和交通；采用标准层才重复相应模数，立面与单元宿主一致。
- WILD 映射与边界：floor/wall/stair 构成空间；电梯井可用墙围合，但不生成运行电梯。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 宿舍

<!-- rag-meta
entity_type: building
entity_name: dormitory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 宿舍
synonyms: []
applies_to:
  - 宿舍
-->

- 适用条件：用户或已批准方案明确采用宿舍；名称本身不决定全部构件。
- 类型特征：居住单元与共享交通、公共空间的组织关系；不默认两端楼梯或固定人数。
- 条件关系：走廊式方案中房门连接走廊；外廊有临空边时安排栏杆；交通数量由任务确定。
- WILD 映射与边界：隔墙、floor、door/window、stair 表达几何；卫生设备和住宿指标不能由外观证明。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 酒店

<!-- rag-meta
entity_type: building
entity_name: hotel
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 酒店
  - 宾馆
  - 酒店标准层
synonyms: []
applies_to:
  - 酒店
  - 宾馆
  - 酒店标准层
-->

- 适用条件：用户或已批准方案明确采用酒店；名称本身不决定全部构件。
- 类型特征：客房、公共交通及服务空间的分工；星级不直接推导开间和装修套餐。
- 条件关系：重复客房应共享本次选定模数；通高大堂不被标准层楼板填满；服务空间按任务选择。
- WILD 映射与边界：墙、楼板、门窗及楼梯表达主体；幕墙采用 wall+window 或显式骨架玻璃，设备用受支持几何近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
