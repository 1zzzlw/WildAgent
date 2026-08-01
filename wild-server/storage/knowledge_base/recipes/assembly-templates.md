---
doc_type: recipe
doc_scope: generation
knowledge_layer: architecture
entity_type: assembly
entity_name: building_assembly_templates
topic: assembly
wild_version: "1.1"
status: experimental
authority: maintainer
source: recipes/assembly-templates.md
keywords:
  - 组装模板
  - assembly
  - 低层建筑
  - 高层建筑
  - 大跨公建
---

# WILD v1.1 建筑组装模板

> 依据：当前 Schema 与引擎能力边界；建筑类型顺序属于维护者建议。
> 用途：只使用 WILD v1.1 已注册类型给出可执行的基线流程；专业构件扩展另列为 proposed。
> RAG 关键词：组装模板、低层建筑、高层建筑、大跨公建、温室、养殖、column、floor、wall、opening、roof、primitive

---
## 低层建筑基线

<!-- rag-meta
entity_type: assembly
entity_name: low_rise_supported_baseline
topic: assembly
status: experimental
authority: maintainer
keywords: 低层建筑, low rise, floor, wall, opening, roof, stair
-->

适用于别墅、小屋、园林和低层公共建筑的起点：

```
floor(地基/首层板) → column/beam(按需) → wall(围护) → opening(门窗洞口) → stair(按需) → roof
```

门扇、窗框、栏杆和装饰构件若需要静态外观，用 `primitive` 或现有结构类型显式组合；不要输出不存在的 `door`、`window`、`railing` 类型。

## 多层建筑基线

<!-- rag-meta
entity_type: assembly
entity_name: multi_storey_supported_baseline
topic: assembly
status: experimental
authority: maintainer
keywords: 多层建筑, multi storey, column, beam, floor, wall, opening, stair
-->

```
column/beam(骨架) → floor(本层楼板) → wall(本层围护与分隔) → opening(本层门窗洞口) → stair(连接层间) → 逐层重复 → roof
```

引擎不会自动设计核心筒、避难层或结构体系；层高、标高、构件尺寸和结构安全仍需外部规则或人工校验。

## 大跨与轻型建筑降级基线

<!-- rag-meta
entity_type: assembly
entity_name: long_span_supported_fallback
topic: assembly
status: experimental
authority: maintainer
keywords: 大跨建筑, 温室, 厂房, long span, beam, primitive, roof
-->

```
column(支点) → beam/primitive(显式杆件网络) → roof(基础屋面) → wall(局部围护) → floor(地坪/平台) → opening(通风或出入口)
```

该模板只能生成几何近似，不能把 `truss`、网壳、膜结构、自动栏杆或专业设备当作已实现能力。

## 专业构件增强提案

<!-- rag-meta
entity_type: assembly
entity_name: proposed_professional_assembly
topic: assembly
status: proposed
authority: domain_reference
keywords: truss, railing, door, window, ramp, 专业构件
-->

```
opening → door/window/mullion
stair/floor → railing
column/roof → truss
floor → ramp
```

这些关系来自领域资料和扩展规范，但相应专用类型及自动 resolver 尚未实现，默认生成必须使用前述降级基线。
