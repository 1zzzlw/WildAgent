---
knowledge_layer: architecture
entity_type: assembly
entity_name: building_assembly_templates
topic: assembly
status: experimental
authority: maintainer
source: recipes/assembly-templates.md
primary_terms:
  - 组装模板
  - assembly
  - 低层建筑
  - 高层建筑
  - 大跨公建
synonyms: []
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
primary_terms:
  - 低层建筑
  - floor
  - wall
  - opening
  - roof
  - stair
synonyms:
  - low rise
-->

适用于别墅、小屋、园林和低层公共建筑的起点：

```
floor(地基/首层板) → column/beam(按需) → wall(围护) → opening(门窗洞口) → stair(按需) → roof
```

标准静态门、窗和路径栏杆优先写入 `geometry.components`，分别使用 `door`、`window`、`railing`；这些名称不能写入 `geometry.elements`。超出编译器边界的装饰细节继续用 `primitive` 或现有结构类型显式组合。

## 多层建筑基线

<!-- rag-meta
entity_type: assembly
entity_name: multi_storey_supported_baseline
topic: assembly
status: experimental
authority: maintainer
primary_terms:
  - 多层建筑
  - column
  - beam
  - floor
  - wall
  - opening
  - stair
synonyms:
  - multi storey
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
primary_terms:
  - 大跨建筑
  - 温室
  - 厂房
  - beam
  - primitive
  - roof
synonyms:
  - long span
-->

```
column(支点) → beam/primitive(显式杆件网络) → roof(基础屋面) → wall(局部围护) → floor(地坪/平台) → opening(通风或出入口)
```

该模板只能生成几何近似，不能把 `truss`、网壳、膜结构、自动栏杆或专业设备当作已实现能力。

## 已支持的基础组合构件

<!-- rag-meta
entity_type: assembly
entity_name: supported_composite_assembly
topic: assembly
status: supported
authority: engine
primary_terms:
  - geometry.components
  - door
  - window
  - railing
  - canopy
  - balcony
  - ramp
  - bay_window
  - cornice
  - chimney
  - light
  - 组合构件
synonyms: []
-->

```text
wall → geometry.components.door/window/bay_window/canopy/balcony
floor or explicit path → geometry.components.railing/ramp
roof or explicit path → geometry.components.cornice/chimney
world position → geometry.components.light
```

门、窗、凸窗、雨棚和阳台必须提供 `parentWall` 与墙体局部 `from`；会形成开口的门、窗和凸窗当前支持直线墙或单段圆弧墙。栏杆和坡道可选 `parentFloor`，檐口和烟囱可选 `parentRoof`。编译器只负责几何展开，不会自动选择建筑规范参数，也不会把烟囱布尔穿透屋顶。

## 仍需降级的专业关系

<!-- rag-meta
entity_type: assembly
entity_name: proposed_professional_relations
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - truss
  - roof penetration
  - 专业构件
  - curtain wall
  - auto railing
synonyms: []
-->

```
column/roof → truss
column/beam → curtain wall system
roof → boolean opening / chimney penetration
stair/floor edge → automatic code-compliant railing
```

这些关系属于建筑专业语义，但当前没有对应专用类型或自动 resolver。默认生成应使用 `beam`/`primitive` 近似桁架；幕墙使用 `wall + window` 或显式 `primitive` 骨架/玻璃，并遵循 `recipes/glass-curtain-wall-assembly.md`；屋顶构件和栏杆需显式布置。`ramp`、`canopy`、`balcony`、`bay_window`、`cornice`、`chimney` 与 `light` 已由组合构件编译器支持，不属于提案类型。
