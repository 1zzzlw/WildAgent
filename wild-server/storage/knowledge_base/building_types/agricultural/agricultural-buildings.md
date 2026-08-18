---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
building_category: agricultural
entity_name: agricultural_building
topic: assembly
wild_version: "1.1"
status: supported
authority: engine
source: building_types/agricultural/agricultural-buildings.md
keywords:
  - 农业建筑
  - 温室
  - 养殖场
  - 粮仓
  - 农机站
---

# 农业建筑：温室 / 养殖 / 粮仓 / 农机

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 所有 JSON 示例只使用当前引擎支持的字段。

---

## 1. 日光温室（10×6m，单栋）

<!-- rag-meta
entity_type: building
entity_name: greenhouse
topic: assembly
status: supported
authority: engine
keywords: 温室, greenhouse, solar, 日光温室, 连栋温室
-->

### 最少可行 Blueprint

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "日光温室" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_ground", "from": [0, 0, 0], "to": [10, 0, 6], "thickness": 0.12, "material": "soil" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 0], "to": [10, 2.5, 0], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 2.5, 6], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_right", "from": [10, 0, 0], "to": [10, 2.5, 6], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_front_low", "from": [0, 0, 6], "to": [10, 0.8, 6], "thickness": 0.24, "material": "brick" },
      { "type": "beam", "id": "beam_ridge", "from": [0, 2.5, 0], "to": [5, 2.5, 3], "crossSection": "rect", "width": 0.1, "height": 0.15, "material": "steel" },
      { "type": "beam", "id": "beam_ridge_r", "from": [5, 2.5, 3], "to": [10, 2.5, 0], "crossSection": "rect", "width": 0.1, "height": 0.15, "material": "steel" },
      { "type": "beam", "id": "beam_slope", "from": [5, 2.5, 3], "to": [5, 0.8, 6], "crossSection": "rect", "width": 0.1, "height": 0.15, "material": "steel" },
      { "type": "roof", "id": "roof_cover", "roofType": "gable", "span": 11, "depth": 7, "height": 0.1, "thickness": 0.05, "material": "plastic_film", "position": [5, 1.65, 3] }
    ],
    "components": [
      { "type": "door", "id": "door_entry", "parentWall": "wall_left", "from": [2.5, 0, 0], "width": 1.2, "height": 2.2, "frameMaterial": "steel", "leafMaterial": "plastic_film", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } }
    ]
  },
  "materials": {
    "soil": { "baseColor": [0.35, 0.25, 0.15], "roughness": 0.95, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "brick": { "baseColor": [0.65, 0.40, 0.25], "roughness": 0.8, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "steel": { "baseColor": [0.25, 0.25, 0.28], "roughness": 0.35, "metallic": 0.85, "albedo": 1, "lightingCondition": "D65_noon" },
    "plastic_film": { "baseColor": [0.85, 0.90, 0.88], "roughness": 0.2, "metallic": 0, "albedo": 1, "opacity": 0.5, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

> `plastic_film` 材质用半透明 `opacity: 0.5` 模拟温室覆膜效果。

---

## 2. 畜禽饲养场（鸡舍，12×8m）

<!-- rag-meta
entity_type: building
entity_name: livestock_barn
topic: assembly
status: supported
authority: engine
keywords: 养殖场, livestock, 鸡舍, poultry, 猪舍, 牛舍
-->

与单厂结构相似，低矮宽大。差异：
- wall 低矮，height=2.5~3m
- wall 两侧下部用短 wall（围栏）替代全高墙
- roof=gable，大 span 低 height
- door 宽 2m+（机械进出）

### 最少可行 Blueprint

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "鸡舍" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [12, 0, 8], "thickness": 0.12, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [12, 2.5, 0], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 8], "to": [12, 2.5, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_left_half", "from": [0, 0, 0], "to": [0, 1.2, 3], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_right_half", "from": [12, 0, 0], "to": [12, 1.2, 3], "thickness": 0.2, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "gable", "span": 13, "depth": 9, "height": 2, "thickness": 0.15, "material": "metal_panel", "position": [6, 2.5, 4] }
    ],
    "components": [
      { "type": "door", "id": "door_front", "parentWall": "wall_front", "from": [5, 0, 0], "width": 2, "height": 2.2, "doorStyle": "double", "frameWidth": 0, "frameMaterial": "steel", "leafMaterial": "metal_panel", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.80, 0.78, 0.75], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "steel": { "baseColor": [0.25, 0.25, 0.28], "roughness": 0.35, "metallic": 0.85, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal_panel": { "baseColor": [0.55, 0.55, 0.58], "roughness": 0.4, "metallic": 0.7, "albedo": 1, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 3. 粮仓（圆形平房仓，d=8m）

<!-- rag-meta
entity_type: building
entity_name: granary
topic: assembly
status: supported
authority: engine
keywords: 粮仓, granary, 筒仓, silo, 圆形
-->

圆形粮仓 = 弧形 `wall`（`curve={type:"arc", sweep:360}`）+ `floor` 圆形 + `roof` dome。

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "圆形粮仓" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [-4, 0, -4], "to": [4, 0, 4], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_silo", "from": [4, 0, 0], "to": [4, 6, 0], "thickness": 0.24, "material": "concrete", "curve": [{ "type": "arc", "center": [0, 0, 0], "sweep": 360, "segments": 32 }] },
      { "type": "roof", "id": "roof_dome", "roofType": "dome", "span": 9, "depth": 9, "height": 2, "thickness": 0.2, "material": "metal_panel", "position": [0, 6, 0] }
    ],
    "components": [
      { "type": "door", "id": "door_granary", "parentWall": "wall_silo", "from": [0, 0, 0], "width": 1.2, "height": 2.2, "frameMaterial": "steel", "leafMaterial": "metal_panel", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.80, 0.78, 0.75], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "steel": { "baseColor": [0.25, 0.25, 0.28], "roughness": 0.35, "metallic": 0.85, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal_panel": { "baseColor": [0.55, 0.55, 0.58], "roughness": 0.4, "metallic": 0.7, "albedo": 1, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 4. 农机站（单层框架，15×8m）

与单层厂结构相似。差异：层高 4~5m（农机高度），door 宽 4m+（拖拉机通行）。使用 `column` + `beam` 框架 + `wall` 围护 + `roof` gable。

### 常见字段错误

| 源文档写法 ❌ | WILD Schema ✅ |
|---|---|
| `wall.curve: "arc"` 字符串 | `curve: [{"type":"arc","center":[...],"sweep":360}]` 数组 |
| `roof.roofType: "arch"` | 用 `"gable"` 或 `"dome"` |
