---
entity_name: courtyards
topic: composition
status: supported
authority: maintainer
source: building_types/catalog/courtyards.md
building_category: mixed_use
primary_terms:
  - 院落
synonyms: []
applies_to:
  - 院落
---

# 院落：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 院落

<!-- rag-meta
entity_type: building
entity_name: courtyard
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 院落
  - 庭院
  - courtyard
synonyms: []
applies_to:
  - 院落
  - 庭院
  - courtyard
-->

- 适用条件：用户或已批准方案明确采用院落；名称本身不决定全部构件。
- 类型特征：建筑、围墙或廊道与院中空地形成关系；不预设四边齐全或固定方位。
- 条件关系：已选围合形式须保留院中空地与通达关系；房屋屋盖不能覆盖整个庭院。
- WILD 映射与边界：多个 floor/wall/roof 体量表达，院墙开口仍需要真实宿主。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 四合院

<!-- rag-meta
entity_type: building
entity_name: northern_courtyard
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 四合院
  - 北方四合院
  - 北京四合院
  - siheyuan
synonyms: []
applies_to:
  - 四合院
  - 北方四合院
  - 北京四合院
  - siheyuan
-->

- 适用条件：用户或已批准方案明确采用四合院；名称本身不决定全部构件。
- 类型特征：保留围院房屋的主次及联系；具体朝向、进数和开间由需求确定。
- 条件关系：选定正房、厢房与廊道后分别表达体量和连接；不得拿一栋正房代替整院。
- WILD 映射与边界：column/beam 表达柱廊；每栋屋盖按自己的支撑边界定位，不使用全院包围盒盖顶。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 地中海庭院

<!-- rag-meta
entity_type: building
entity_name: mediterranean_courtyard
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 地中海庭院
synonyms: []
applies_to:
  - 地中海庭院
-->

- 适用条件：用户或已批准方案明确采用地中海庭院；名称本身不决定全部构件。
- 类型特征：围绕户外空间组织活动与遮蔽；拱廊和抹灰只是可选表达。
- 条件关系：选择拱廊时维持通道连续与支点关系；材质和植物由任务决定。
- WILD 映射与边界：拱形洞口依附墙，廊道用柱梁及屋盖；植物资产不凭空发明 WILD 类型。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
