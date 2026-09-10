---
entity_name: education_office_culture
topic: composition
status: supported
authority: maintainer
source: building_types/public/education-office-culture.md
building_category: public
primary_terms:
  - 教育、办公与文化建筑
synonyms: []
applies_to:
  - 教育、办公与文化建筑
---

# 教育、办公与文化建筑：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 教育建筑

<!-- rag-meta
entity_type: building
entity_name: education
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 教育建筑
  - 学校
  - 教学楼
synonyms: []
applies_to:
  - 教育建筑
  - 学校
  - 教学楼
-->

- 适用条件：用户或已批准方案明确采用教育建筑；名称本身不决定全部构件。
- 类型特征：教学空间与交通、共享空间的联系；不固定教室数量和走廊形式。
- 条件关系：选择重复教室时保持门、窗、隔墙与模数一致；选择通高空间时楼板避让；外廊边界按实际高差处理。
- WILD 映射与边界：wall/floor/door/window/stair 表达空间；采光、防眩光和疏散性能不是几何校验结论。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 办公建筑

<!-- rag-meta
entity_type: building
entity_name: office
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 办公建筑
  - 办公楼
  - 写字楼
synonyms: []
applies_to:
  - 办公建筑
  - 办公楼
  - 写字楼
-->

- 适用条件：用户或已批准方案明确采用办公建筑；名称本身不决定全部构件。
- 类型特征：工作空间、公共交通及入口联系；玻璃幕墙、中庭和塔冠均需任务触发。
- 条件关系：采用核心筒则保持跨层连续；采用幕墙则协调楼层、框架与面板；不直接修改学校示例生成办公楼。
- WILD 映射与边界：核心筒用 wall；幕墙按专门组装关系；真实电梯和结构分析不在当前模型内。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 文化建筑

<!-- rag-meta
entity_type: building
entity_name: culture
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 文化建筑
  - 博物馆
  - 剧院
  - 图书馆
synonyms: []
applies_to:
  - 文化建筑
  - 博物馆
  - 剧院
  - 图书馆
-->

- 适用条件：用户或已批准方案明确采用文化建筑；名称本身不决定全部构件。
- 类型特征：保留所选展览、演出或阅读功能的空间关系，不能把不同功能套成同一大盒子。
- 条件关系：展厅按展览动线组织；剧院保留舞台与观众区联系；图书馆区分阅览与书库，是否通高由方案决定。
- WILD 映射与边界：大跨屋盖用 roof 加显式 beam/primitive；家具使用现有 subtype；声学、藏品环境和荷载不由渲染证明。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
