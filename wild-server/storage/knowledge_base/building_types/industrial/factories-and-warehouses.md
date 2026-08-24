---
building_category: industrial
entity_name: industrial_building
topic: assembly
status: supported
authority: engine
source: building_types/industrial/factories-and-warehouses.md
primary_terms:
  - 工业建筑
  - 厂房
  - 仓储
  - 单层厂房
  - 工业上楼
  - 仓库
synonyms: []
---

# 工业建筑：厂房 / 仓储

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 所有 JSON 示例只使用当前引擎支持的字段。

---

## 1. 单层轻钢厂（12×24m）

<!-- rag-meta
entity_type: building
entity_name: steel_factory
topic: assembly
status: supported
authority: engine
primary_terms:
  - 厂房
  - 轻钢
  - steel
  - 单层
  - 工业
synonyms:
  - factory
-->

### 构件清单

| 构件 | WILD type | 参数 |
|---|---|---|
| 地基楼板 | `floor` | shape=rect, thickness=0.2, 全场地 |
| 钢柱 | `column` | style=modern, bottomRadius=0.15, topRadius=0.12, height=8 |
| 屋面梁 | `beam` | crossSection=i-beam, width=0.2, height=0.6 |
| 墙檩 | `beam` | crossSection=rect, 水平间距 1.5m |
| 外墙板 | `wall` | thickness=0.15, height=8 |
| 屋顶 | `roof` | roofType=gable, span=13, depth=25 |
| 卷帘门 | `door` 组件 | width=3, height=4, interaction.slide |
| 高窗 | `window` 组件 | 墙顶带状窗 |

### 最少可行 Blueprint

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "轻钢厂" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [12, 0, 24], "thickness": 0.2, "material": "concrete" },
      { "type": "column", "id": "col_a1", "base": [0.5, 0, 0.5], "height": 8, "bottomRadius": 0.15, "topRadius": 0.12, "style": "modern", "material": "steel" },
      { "type": "column", "id": "col_a2", "base": [6, 0, 0.5], "height": 8, "bottomRadius": 0.15, "topRadius": 0.12, "style": "modern", "material": "steel" },
      { "type": "column", "id": "col_a3", "base": [11.5, 0, 0.5], "height": 8, "bottomRadius": 0.15, "topRadius": 0.12, "style": "modern", "material": "steel" },
      { "type": "column", "id": "col_b1", "base": [0.5, 0, 23.5], "height": 8, "bottomRadius": 0.15, "topRadius": 0.12, "style": "modern", "material": "steel" },
      { "type": "column", "id": "col_b2", "base": [6, 0, 23.5], "height": 8, "bottomRadius": 0.15, "topRadius": 0.12, "style": "modern", "material": "steel" },
      { "type": "column", "id": "col_b3", "base": [11.5, 0, 23.5], "height": 8, "bottomRadius": 0.15, "topRadius": 0.12, "style": "modern", "material": "steel" },
      { "type": "beam", "id": "beam_roof_01", "from": [0.5, 8, 0.5], "to": [0.5, 8, 23.5], "crossSection": "i-beam", "width": 0.2, "height": 0.6, "material": "steel" },
      { "type": "beam", "id": "beam_roof_02", "from": [6, 8, 0.5], "to": [6, 8, 23.5], "crossSection": "i-beam", "width": 0.2, "height": 0.6, "material": "steel" },
      { "type": "beam", "id": "beam_roof_03", "from": [11.5, 8, 0.5], "to": [11.5, 8, 23.5], "crossSection": "i-beam", "width": 0.2, "height": 0.6, "material": "steel" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [12, 8, 0], "thickness": 0.15, "material": "metal_panel" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 24], "to": [12, 8, 24], "thickness": 0.15, "material": "metal_panel" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 8, 24], "thickness": 0.15, "material": "metal_panel" },
      { "type": "wall", "id": "wall_right", "from": [12, 0, 0], "to": [12, 8, 24], "thickness": 0.15, "material": "metal_panel" },
      { "type": "roof", "id": "roof_main", "roofType": "gable", "span": 13, "depth": 25, "height": 3, "thickness": 0.15, "material": "metal_panel", "position": [6, 8, 12] }
    ],
    "components": [
      { "type": "door", "id": "door_roller", "parentWall": "wall_front", "from": [4, 0, 0], "width": 4, "height": 4.5, "frameMaterial": "steel", "leafMaterial": "metal_panel", "interaction": { "mode": "slide", "hingeSide": "right", "openDistance": 4 } },
      { "type": "window", "id": "win_high_01", "parentWall": "wall_left", "from": [3, 5, 0], "width": 2, "height": 1.5, "verticalMullions": 0, "horizontalMullions": 0, "frameMaterial": "steel", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_high_02", "parentWall": "wall_right", "from": [3, 5, 0], "width": 2, "height": 1.5, "verticalMullions": 0, "horizontalMullions": 0, "frameMaterial": "steel", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.78, 0.76, 0.74], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "steel": { "baseColor": [0.25, 0.25, 0.28], "roughness": 0.35, "metallic": 0.85, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal_panel": { "baseColor": [0.55, 0.55, 0.58], "roughness": 0.4, "metallic": 0.7, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 2. 仓储建筑

<!-- rag-meta
entity_type: building
entity_name: warehouse
topic: assembly
status: supported
authority: engine
primary_terms:
  - 仓储
  - 平房仓
  - 筒仓
  - 冷链
synonyms:
  - warehouse
-->

仓储建筑与单层厂结构相似，差异：
- 平房仓：减少 window（防潮），门更宽（叉车通行 ≥3m）
- 筒仓：用 `wall` 弧形围合（`curve={type:"arc"}`）+ `roof` dome
- 冷链仓库：wall thickness=0.24（保温），增加 inner wall 隔层

---

## 3. 工业上楼（4F+ 高层厂房）

多层的厂房，每层荷载大。构件参数上调：
- `column` bottomRadius=0.25~0.35（大截面柱）
- `beam` crossSection=rect, width=0.3, height=0.7
- `floor` thickness=0.2（重载楼板）
- `stair` width=1.8 + 货梯井（wall 围合）

其他结构与办公楼相似，逐层重复。

### 常见字段错误

| 源文档写法 ❌ | WILD Schema ✅ |
|---|---|
| `column.crossSection: "square"` | 不存在，用 `style: "modern"` |
| `floor.surfaces: "hardener"` | 不存在，用 `material` |
| `wall.curve: "line"` | 不写 curve 默认直线，弧形用 `{type:"arc",...}` |
| `beam.crossSection: "h-beam"` | 用 `"i-beam"`（H 型钢的 WILD 名称） |
| `roof.autoRailing` | 不存在 |
