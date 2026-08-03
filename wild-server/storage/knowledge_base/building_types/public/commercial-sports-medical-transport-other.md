---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: commercial_sports_medical_transport
topic: assembly
wild_version: "1.1"
status: supported
authority: engine
source: building_types/public/commercial-sports-medical-transport-other.md
keywords:
  - 商业建筑
  - 商场
  - 体育建筑
  - 体育馆
  - 医疗建筑
  - 医院
  - 交通建筑
  - 车站
  - 园林
---

# 公共建筑：商业 / 体育 / 医疗 / 交通 / 园林

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 所有 JSON 示例只使用当前引擎支持的字段。

---

## 1. 商业建筑（商场/商铺）

<!-- rag-meta
entity_type: building
entity_name: commercial_building
topic: assembly
status: supported
authority: engine
keywords: 商业建筑, commercial, 商场, 商铺, 综合体
-->

### 最少可行 Blueprint（社区商铺，8×6m，单层）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "社区商铺" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [8, 0, 6], "thickness": 0.15, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [8, 3.6, 0], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 6], "to": [8, 3.6, 6], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 3.6, 6], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [8, 0, 0], "to": [8, 3.6, 6], "thickness": 0.20, "material": "concrete" },
      { "type": "column", "id": "col_01", "base": [0.5, 0, 0.5], "height": 3.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_02", "base": [7.5, 0, 0.5], "height": 3.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete" },
      { "type": "beam", "id": "beam_front", "from": [0, 3.6, 0], "to": [8, 3.6, 0], "crossSection": "rect", "width": 0.2, "height": 0.4, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "flat", "span": 9, "depth": 7, "height": 0.2, "thickness": 0.15, "material": "concrete", "position": [4, 3.6, 3] }
    ],
    "components": [
      { "type": "door", "id": "door_shop", "parentWall": "wall_front", "from": [3, 0, 0], "width": 2, "height": 2.4, "doorStyle": "double", "frameWidth": 0, "frameMaterial": "metal", "leafMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "window", "id": "win_display", "parentWall": "wall_front", "from": [0.3, 0.6, 0], "width": 2.4, "height": 2, "verticalMullions": 0, "horizontalMullions": 0, "frameMaterial": "metal", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.85, 0.83, 0.80], "roughness": 0.55, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal": { "baseColor": [0.12, 0.12, 0.12], "roughness": 0.3, "metallic": 0.7, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 2. 体育建筑

<!-- rag-meta
entity_type: building
entity_name: sports_building
topic: assembly
status: supported
authority: engine
keywords: 体育建筑, sports, 体育馆, gymnasium, 大跨
-->

体育建筑核心特征：**大跨无柱空间**。用 `beam` crossSection=i-beam 或 rect 大截面 + `roof` gable/arch 大跨 + `column` 仅沿周边布置。

### 构件要点

| 构件 | 参数建议 |
|---|---|
| 周边柱 `column` | style=modern, bottomRadius=0.3~0.5, 间距 6~8m |
| 主梁 `beam` | crossSection=i-beam, width=0.3, height=0.8~1.2（大跨） |
| 屋顶 `roof` | roofType=gable, span 覆盖全宽 + 余量 |
| 楼板 `floor` | 运动地板, thickness=0.15 |

---

## 3. 医疗建筑

<!-- rag-meta
entity_type: building
entity_name: medical_building
topic: assembly
status: supported
authority: engine
keywords: 医疗建筑, hospital, 医院, 社区医院
-->

与办公楼结构相似。差异：走廊宽 ≥2.4m（病床通行），门宽 ≥1.2m（轮椅），层高 3.6~4.2m。使用框架 `column` + `beam` + `floor` 多层 + `wall` 隔墙划分诊室/病房。

---

## 4. 交通建筑（小型客运站）

<!-- rag-meta
entity_type: building
entity_name: transport_building
topic: assembly
status: supported
authority: engine
keywords: 交通建筑, transport, 客运站, 航站楼, station
-->

核心特征：**通高候车大厅**（wall 双层通高 + column 大截面）+ 大面积 `roof` flat/gable + `canopy` 雨棚覆盖上车区。

### 最少可行 Blueprint（小型客运站，候车大厅 12×8m）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "小型客运站" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [12, 0, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [12, 5, 0], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 8], "to": [12, 5, 8], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 5, 8], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [12, 0, 0], "to": [12, 5, 8], "thickness": 0.24, "material": "concrete" },
      { "type": "column", "id": "col_01", "base": [1, 0, 1], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_02", "base": [11, 0, 1], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_03", "base": [1, 0, 7], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_04", "base": [11, 0, 7], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "beam", "id": "beam_main", "from": [0, 5, 1], "to": [12, 5, 1], "crossSection": "i-beam", "width": 0.3, "height": 0.8, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "gable", "span": 13, "depth": 9, "height": 2.5, "thickness": 0.2, "material": "tile", "position": [6, 5, 4] }
    ],
    "components": [
      { "type": "door", "id": "door_entry", "parentWall": "wall_front", "from": [5, 0, 0], "width": 2, "height": 2.7, "doorStyle": "double", "frameWidth": 0, "frameMaterial": "metal", "leafMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "canopy", "id": "canopy_front", "parentWall": "wall_front", "from": [0, 3, 0], "width": 12, "depth": 3, "thickness": 0.15, "supportCount": 4, "material": "metal" }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.85, 0.83, 0.80], "roughness": 0.55, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal": { "baseColor": [0.15, 0.15, 0.15], "roughness": 0.35, "metallic": 0.65, "albedo": 1, "lightingCondition": "D65_noon" },
    "tile": { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 5. 园林建筑（亭/廊/榭）

<!-- rag-meta
entity_type: building
entity_name: garden_structure
topic: assembly
status: supported
authority: engine
keywords: 园林, garden, 亭, pavilion, 廊, 榭, 苏州园林
-->

园林建筑核心是 `column` + `roof` + `beam` 组合，通常没有 wall。可用 `railing` 做美人靠。

| 园林元素 | WILD 表达 |
|---|---|
| 四角亭 | 4 根 `column` + `beam` 连接 + `roof` chinese_curved |
| 游廊 | `column` 双排 + `beam` + `roof` gable 连续 + `railing` 矮栏杆 |
| 水榭 | `column` 挑出水面 + `floor` 悬挑 + `roof` chinese_curved + `railing` |

### 最少可行 Blueprint（四角亭，3×3m）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "四角亭" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_platform", "from": [0, 0, 0], "to": [3, 0.4, 3], "thickness": 0.4, "material": "stone_grey" },
      { "type": "column", "id": "col_01", "base": [0.3, 0.4, 0.3], "height": 3, "bottomRadius": 0.18, "topRadius": 0.15, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_02", "base": [2.7, 0.4, 0.3], "height": 3, "bottomRadius": 0.18, "topRadius": 0.15, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_03", "base": [0.3, 0.4, 2.7], "height": 3, "bottomRadius": 0.18, "topRadius": 0.15, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_04", "base": [2.7, 0.4, 2.7], "height": 3, "bottomRadius": 0.18, "topRadius": 0.15, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "beam", "id": "beam_front", "from": [0.3, 3.4, 0.3], "to": [2.7, 3.4, 0.3], "crossSection": "rect", "width": 0.12, "height": 0.2, "material": "wood_red" },
      { "type": "beam", "id": "beam_back", "from": [0.3, 3.4, 2.7], "to": [2.7, 3.4, 2.7], "crossSection": "rect", "width": 0.12, "height": 0.2, "material": "wood_red" },
      { "type": "beam", "id": "beam_left", "from": [0.3, 3.4, 0.3], "to": [0.3, 3.4, 2.7], "crossSection": "rect", "width": 0.12, "height": 0.2, "material": "wood_red" },
      { "type": "beam", "id": "beam_right", "from": [2.7, 3.4, 0.3], "to": [2.7, 3.4, 2.7], "crossSection": "rect", "width": 0.12, "height": 0.2, "material": "wood_red" },
      { "type": "roof", "id": "roof_main", "roofType": "chinese_curved", "span": 4.5, "depth": 4.5, "height": 1.8, "thickness": 0.15, "eaveCurveHeight": 0.4, "material": "tile_grey", "position": [1.5, 3.4, 1.5] }
    ],
    "components": [
      { "type": "railing", "id": "rail_north", "path": [[0.3, 0.4, 0.3], [2.7, 0.4, 0.3]], "height": 0.5, "postSpacing": 0.6, "material": "wood_red" },
      { "type": "railing", "id": "rail_east", "path": [[2.7, 0.4, 0.3], [2.7, 0.4, 2.7]], "height": 0.5, "postSpacing": 0.6, "material": "wood_red" },
      { "type": "railing", "id": "rail_south", "path": [[0.3, 0.4, 2.7], [2.7, 0.4, 2.7]], "height": 0.5, "postSpacing": 0.6, "material": "wood_red" }
    ]
  },
  "materials": {
    "stone_grey": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "wood_red": { "baseColor": [0.55, 0.22, 0.12], "roughness": 0.65, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "tile_grey": { "baseColor": [0.25, 0.25, 0.27], "roughness": 0.75, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

### 常见字段错误

| 源文档写法 ❌ | WILD Schema ✅ |
|---|---|
| `floor.surfaces: "stone_block"` | 不存在，用 `material` + 材质定义 |
| `window.sashType: "fixed"` | 不存在，用 `interaction.openAngle: 0` |
| `column.crossSection: "square"` | 不存在，用 `style: "modern"` |
| `roof.autoRailing` | 不存在，手动加 `railing` |
