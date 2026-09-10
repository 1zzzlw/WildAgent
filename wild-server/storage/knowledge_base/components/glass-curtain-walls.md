---
applies_to:
  - 幕墙
  - curtain wall
  - curtain_wall
  - 玻璃立面
entity_type: facade
entity_name: glass_curtain_wall_family
topic: assembly
status: experimental
authority: engine
source: wild-web/wild-lang/schema.json; wild-web/src/wild-compiler/components/window.ts; wild-server/app/agent/architecture_plan.py
primary_terms:
  - 玻璃幕墙 WILD 映射
  - curtain wall assembly
  - window grid
  - primitive mullion
synonyms:
  - glass curtain wall
  - glass facade
---

# 玻璃幕墙到当前 WILD 能力的映射

本文只在用户或已批准 `DesignDocument` 明确选择 `curtain_wall` 时适用。它说明当前项目如何表达幕墙，不定义写字楼、住宅或任何风格，也不自动决定幕墙范围、颜色、面板比例和立面节奏。

## 当前表达路径

<!-- rag-meta
entity_type: facade
entity_name: glass_curtain_wall_engine_mapping
topic: assembly
status: experimental
authority: engine
primary_terms:
  - curtain_wall
  - parentWall
  - verticalMullions
  - horizontalMullions
  - primitive box
synonyms: []
-->

当前注册表没有 `curtain_wall`、`mullion` 或 `transom` 类型。业务语义必须落到以下两条路径之一：

| 路径 | WILD 表达 | 使用条件 | 当前边界 |
|---|---|---|---|
| A：宿主墙加网格窗 | 原生 `wall` + `window` 组件 | 规则矩形分格，可接受一个窗口组件生成横竖窗棂 | 窗必须引用真实 `parentWall` 并落在宿主范围内 |
| B：显式骨架加面板 | `primitive.box` 骨架 + 薄 `primitive.box` 玻璃 | 需要可见框深、斜向分段、点件或局部双层 | 只表达视觉几何，元素数量和碰撞风险更高 |

主体结构仍使用 `column`、`beam`、`floor`；入口和可开启扇仍使用 `door`、`window`。幕墙几何不获得荷载、锚固、气密、水密、热工或防火计算能力。

## 路径 A 的最小局部片段

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_window_fragment
topic: schema
status: supported
authority: engine
primary_terms:
  - window fragment
  - glassMaterial
  - verticalMullions
  - horizontalMullions
synonyms: []
-->

以下对象属于 `geometry.components`，并假定 `facade_wall_1` 及材料引用已经存在。数值仅展示字段关系，实际宽高、标高和分格数来自本次立面轴网及宿主范围。

```json
{
  "type": "window",
  "id": "curtain_panel_1",
  "parentWall": "facade_wall_1",
  "from": [1.0, 0.5, 0.0],
  "width": 2.4,
  "height": 2.6,
  "verticalMullions": 1,
  "horizontalMullions": 1,
  "frameMaterial": "curtain_frame",
  "glassMaterial": "curtain_glass"
}
```

## 变体只改变映射参数

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_variant_mapping
topic: assembly
status: experimental
authority: maintainer
primary_terms:
  - 明框
  - 隐框
  - 半隐框
  - 点支式
  - 双层幕墙
  - 曲面幕墙
synonyms: []
-->

- 明框：A 或 B；增加可见骨架深度，并让玻璃沿立面法线后退。
- 隐框或半隐框：使用 B 控制一个或两个方向的框可见度；这只是几何近似。
- 点支式：使用 B，以少量受支持 `primitive` 表示点件；没有连接计算。
- 双层：使用两层分离的玻璃几何表达空腔；没有通风和热工模拟。
- 曲面或斜面：按共同法线分段并设置 `rotation`；没有连续 NURBS 幕墙能力。
- 单元式：按已选网格重复受支持元素或模板实例；模板只能保存基础 `GeometryElement`，不能直接保存 `window` 组件。

没有选择这些变体时，不因“办公楼”“现代”等词自动加入对应几何。

## 材质与禁止项

<!-- rag-meta
entity_type: material
entity_name: curtain_wall_material_and_limits
topic: constraints
status: supported
authority: engine
primary_terms:
  - materialClass glass
  - transmission
  - opacity
  - unsupported type
synonyms: []
-->

玻璃材料必须使用 `materialClass: "glass"`、`transmission > 0` 和有效 `ior`，`opacity` 省略或设为 `1`；框与玻璃使用不同材料引用。当前禁止输出 `type: "curtain_wall"`、`type: "mullion"`、`type: "transom"`、`window.parentOpening`、`window.parentRoof` 或 `wall.height`。

正式组装顺序、网格公式和运行时直接读取的参数块位于 `recipes/glass-curtain-wall-assembly.md`。若所选变体超出当前能力，必须说明近似或能力缺口，不能编造字段。
