---
entity_type: door
entity_name: door_variant_mappings
topic: assembly
status: supported
authority: maintainer
source: wild-web/src/wild-compiler/components/door.ts
primary_terms:
  - 门型映射
  - door variant
synonyms: []
---

# 门型语义到 WILD 的条件映射

## 共性边界

门型名称只帮助解释用户意图，不决定建筑风格、数量、比例或材质。基础字段统一使用 `door` 能力契约；下列映射只在用户或批准设计明确选择对应门型时使用。

## 单扇、双扇与推拉门

<!-- rag-meta
applies_to:
  - 单扇门
  - 双扇门
  - 双开门
  - 推拉门
  - sliding door
entity_name: supported_door_variants
topic: assembly
primary_terms:
  - doorStyle
  - interaction
synonyms: []
-->

- 单扇门：`doorStyle: "single"`，需要开合时配置 `interaction`。
- 双扇门：一个 `door` 使用 `doorStyle: "double"`；`width` 表示完整门洞宽度。
- 推拉门：使用 `interaction.mode: "slide"`；几何仍是当前门扇近似，不自动生成轨道或多扇联动。

## 拱形门

<!-- rag-meta
applies_to:
  - 拱形门
  - 拱形大门
  - arched door
entity_name: arched_door_mapping
topic: assembly
primary_terms:
  - openingStyle
  - arched
synonyms: []
-->

使用 `openingStyle: "arched"`。尖拱、复杂券拱与雕刻轮廓超出该枚举时，只能在用户接受近似的前提下添加显式 `primitive` 装饰。

## 亮子与侧亮

<!-- rag-meta
applies_to:
  - 门亮子
  - 横披窗
  - 侧亮
  - transom
  - sidelight
entity_name: door_glazing_companions
topic: assembly
primary_terms:
  - door window
  - parentWall
synonyms: []
-->

亮子和侧亮使用独立 `window`，与门引用同一原生墙体。它们的位置由门洞范围推导并避免重叠；不能使用 `parentOpening`。

## 专业门名与未实现性能

<!-- rag-meta
applies_to:
  - 自动感应门
  - 卷帘门
  - 气密门
  - 防火门
  - 旋转门
  - 折叠门
entity_name: unsupported_door_performance
topic: constraints
primary_terms:
  - unsupported door performance
synonyms: []
-->

自动感应、卷绕、气密、防火、旋转和折叠不属于当前门组件能力。可以按批准设计表达矩形或拱形门洞、材质与已有平开/推拉交互，但不得把名称当成已实现性能。

## 装饰性门型

<!-- rag-meta
applies_to:
  - 实榻门
  - 隔扇门
  - 嵌板门
  - 平板门
  - 法式门
  - 荷兰门
entity_name: decorative_door_mapping
topic: assembly
primary_terms:
  - decorative door
  - primitive
synonyms: []
-->

这些名称使用标准 `door` 表达门洞和门扇。只有批准设计要求可见格栅、面板或线脚时才增加 `primitive`，并保持其与门扇共面关系；名称本身不触发固定装饰套餐。
