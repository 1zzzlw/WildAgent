---
entity_name: villas
topic: composition
status: supported
authority: maintainer
source: building_types/residential/villas.md
building_category: residential
primary_terms:
  - 别墅
synonyms: []
applies_to:
  - 别墅
---

# 别墅：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 别墅

<!-- rag-meta
entity_type: building
entity_name: villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 别墅
  - villa
synonyms: []
applies_to:
  - 别墅
  - villa
-->

- 适用条件：用户或已批准方案明确采用别墅；名称本身不决定全部构件。
- 类型特征：独立居住单元；庭院、门廊、车库和阳台是否出现由任务决定。
- 条件关系：存在多层时明确层间交通；有室外平台时区分地面庭院、楼板露台与墙挂阳台。
- WILD 映射与边界：主体用 floor、wall、roof；门窗绑定实际墙；柱梁只在所选体系需要时生成。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 现代别墅

<!-- rag-meta
entity_type: building
entity_name: modern_villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 现代别墅
  - modern villa
synonyms: []
applies_to:
  - 现代别墅
  - modern villa
-->

- 适用条件：用户或已批准方案明确采用现代别墅；名称本身不决定全部构件。
- 类型特征：现代语汇允许多种体量和开窗策略，架空层、水平长窗与平顶是可选方案。
- 条件关系：选择架空层才安排相应支撑；选择带状窗才推导沿墙窗格；退台平台按实际轮廓覆盖。
- WILD 映射与边界：column/beam 表达支撑，window 表达开窗；balcony 已包含板和栏杆，不重复叠加。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 中式传统别墅

<!-- rag-meta
entity_type: building
entity_name: chinese_traditional_villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 中式传统别墅
  - 中式别墅
synonyms: []
applies_to:
  - 中式传统别墅
  - 中式别墅
-->

- 适用条件：用户或已批准方案明确采用中式传统别墅；名称本身不决定全部构件。
- 类型特征：按需求保留院落、柱廊、屋盖和门窗语汇之间的联系，四合院与江南民居不互相套用。
- 条件关系：采用院落才组织房屋与院中空地；采用柱廊才确定柱梁与檐口衔接；门窗必须有墙体宿主。
- WILD 映射与边界：木构外观用 column/beam；复杂斗拱用 primitive 近似；door/window 的 parentWall 不能引用梁。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 新中式别墅

<!-- rag-meta
entity_type: building
entity_name: new_chinese_villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 新中式别墅
synonyms: []
applies_to:
  - 新中式别墅
-->

- 适用条件：用户或已批准方案明确采用新中式别墅；名称本身不决定全部构件。
- 类型特征：现代空间需求与选定传统特征结合；白墙、灰瓦、对称或双坡顶均非必选项。
- 条件关系：选定庭院、檐廊、格栅等特征后，分别落实空地、支撑、宿主与搭接关系。
- WILD 映射与边界：传统语汇映射为受支持屋顶、门窗及 primitive；不发明 new_chinese 类型或材质枚举。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 欧式别墅

<!-- rag-meta
entity_type: building
entity_name: european_villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 欧式别墅
  - 欧式庄园
synonyms: []
applies_to:
  - 欧式别墅
  - 欧式庄园
-->

- 适用条件：用户或已批准方案明确采用欧式别墅；名称本身不决定全部构件。
- 类型特征：按指定流派选择门廊、屋盖、开窗和线脚；不借用中式蓝图作为默认底稿。
- 条件关系：选择拱门或多扇入口时保留真实墙体与分段开口；选定线脚后才安排檐口路径。
- WILD 映射与边界：door/window/cornice 表达局部特征；装饰方柱用 primitive，原生 column 的截面边界不变。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
