---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
building_category: residential
entity_name: housing_dormitory_hotel
topic: assembly
wild_version: "1.1"
status: supported
authority: engine
source: building_types/residential/housing-dormitories-hotels.md
keywords:
  - 普通住宅
  - 宿舍
  - 酒店
  - 宾馆
  - 高层住宅
  - 标准层
---

# 居住建筑：普通住宅 / 宿舍 / 酒店

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 所有 JSON 示例只使用当前引擎支持的字段。

---

## 1. 普通住宅（低层~高层）

<!-- rag-meta
entity_type: building
entity_name: residential_building
topic: assembly
status: supported
authority: engine
keywords: 普通住宅, residential, 多层, 高层, 剪力墙, 框架
-->

### 按层数分级的构件参数

| 构件 | 低层(1~3F) | 多层(4~6F) | 高层(10~33F) |
|---|---|---|---|
| 承重外墙 `wall` | thickness=0.24 | thickness=0.24 | thickness=0.20 |
| 内隔墙 `wall` | thickness=0.12 | thickness=0.12 | thickness=0.10 |
| 框架柱 `column` | 砖混无柱 | style=modern | style=modern, bottomRadius=0.15~0.25 |
| 楼板 `floor` | thickness=0.12 | thickness=0.12~0.15 | thickness=0.15 |
| 梁 `beam` | crossSection=rect, 0.2×0.3m | rect 0.25×0.5m | rect 0.3×0.6m |
| 屋顶 `roof` | roofType=gable | gable/flat | flat |

### 最少可行 Blueprint（6×8m 两层住宅）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "两层住宅" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_ground", "from": [0, 0, 0], "to": [6, 0, 8], "thickness": 0.15, "material": "concrete" },
      { "type": "floor", "id": "floor_upper", "from": [0, 3, 0], "to": [6, 3, 8], "thickness": 0.15, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [6, 6, 0], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 8], "to": [6, 6, 8], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 6, 8], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_right", "from": [6, 0, 0], "to": [6, 6, 8], "thickness": 0.24, "material": "brick" },
      { "type": "wall", "id": "wall_inner", "from": [3, 0, 0], "to": [3, 6, 8], "thickness": 0.12, "material": "brick" },
      { "type": "stair", "id": "stair_main", "from": [4, 0, 3], "to": [4, 3, 6], "width": 0.9, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "gable", "span": 7, "depth": 9, "height": 2, "thickness": 0.2, "material": "tile", "position": [3, 6, 4] }
    ],
    "components": [
      { "type": "door", "id": "door_entry", "parentWall": "wall_front", "from": [2.5, 0, 0], "width": 1, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "window", "id": "win_left", "parentWall": "wall_front", "from": [0.5, 0.9, 0], "width": 1.5, "height": 1.5, "verticalMullions": 1, "horizontalMullions": 0, "frameMaterial": "wood", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_right", "parentWall": "wall_front", "from": [4, 0.9, 0], "width": 1.5, "height": 1.5, "verticalMullions": 1, "horizontalMullions": 0, "frameMaterial": "wood", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.82, 0.80, 0.78], "roughness": 0.65, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "brick": { "baseColor": [0.65, 0.40, 0.25], "roughness": 0.8, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "wood": { "baseColor": [0.45, 0.25, 0.10], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "tile": { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 2. 宿舍（≤9F）

<!-- rag-meta
entity_type: building
entity_name: dormitory
topic: assembly
status: supported
authority: engine
keywords: 宿舍, dormitory, 走廊式, 公共卫生间
-->

### 最少可行 Blueprint（单层走廊式，12×8m）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "走廊式宿舍" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [12, 0, 8], "thickness": 0.15, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [12, 3, 0], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 8], "to": [12, 3, 8], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 3, 8], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [12, 0, 0], "to": [12, 3, 8], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_corridor_n", "from": [0, 0, 2.5], "to": [12, 3, 2.5], "thickness": 0.12, "material": "concrete" },
      { "type": "wall", "id": "wall_corridor_s", "from": [0, 0, 5.5], "to": [12, 3, 5.5], "thickness": 0.12, "material": "concrete" },
      { "type": "stair", "id": "stair_west", "from": [0.5, 0, 2.5], "to": [0.5, 3, 5.5], "width": 1.4, "material": "concrete" },
      { "type": "stair", "id": "stair_east", "from": [11.5, 0, 2.5], "to": [11.5, 3, 5.5], "width": 1.4, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "flat", "span": 13, "depth": 9, "height": 0.2, "thickness": 0.15, "material": "concrete", "position": [6, 3, 4] }
    ],
    "components": [
      { "type": "door", "id": "door_01", "parentWall": "wall_corridor_n", "from": [1, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_02", "parentWall": "wall_corridor_n", "from": [4.6, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_03", "parentWall": "wall_corridor_s", "from": [1, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "right", "openAngle": 90 } },
      { "type": "door", "id": "door_04", "parentWall": "wall_corridor_s", "from": [4.6, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "right", "openAngle": 90 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.82, 0.80, 0.78], "roughness": 0.65, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "wood": { "baseColor": [0.45, 0.25, 0.10], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 3. 酒店标准层

<!-- rag-meta
entity_type: building
entity_name: hotel_floor
topic: assembly
status: supported
authority: engine
keywords: 酒店, hotel, 标准层, 客房, 走廊
-->

### 客房标准尺寸参考

| 酒店类型 | 开间 | 进深 | 层高 |
|---|---|---|---|
| 快捷酒店 | 3.2~3.8m | 6.0~6.2m | 3.0m |
| 商务酒店 | 3.7~4.2m | 7.2~8.4m | 3.0~3.9m |
| 五星级酒店 | 4.5~4.8m | 9.0~9.8m | 3.9~4.2m |

### 最少可行 Blueprint（快捷酒店标准层，20×16m）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "快捷酒店标准层" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [20, 0, 16], "thickness": 0.15, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [20, 3, 0], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 16], "to": [20, 3, 16], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 3, 16], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [20, 0, 0], "to": [20, 3, 16], "thickness": 0.20, "material": "concrete" },
      { "type": "wall", "id": "wall_corridor", "from": [0, 0, 8], "to": [20, 3, 8], "thickness": 0.12, "material": "concrete" },
      { "type": "column", "id": "col_lobby_01", "base": [9, 0, 7], "height": 3, "bottomRadius": 0.25, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_lobby_02", "base": [11, 0, 7], "height": 3, "bottomRadius": 0.25, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "stair", "id": "stair_fire", "from": [18, 0, 1], "to": [18, 3, 6], "width": 1.2, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "flat", "span": 21, "depth": 17, "height": 0.2, "thickness": 0.15, "material": "concrete", "position": [10, 3, 8] }
    ],
    "components": [
      { "type": "door", "id": "door_lobby", "parentWall": "wall_corridor", "from": [9.5, 0, 0], "width": 1.5, "height": 2.4, "doorStyle": "double", "frameWidth": 0, "frameMaterial": "metal", "leafMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_n01", "parentWall": "wall_front", "from": [1, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_n02", "parentWall": "wall_front", "from": [4.6, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_s01", "parentWall": "wall_back", "from": [1, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "right", "openAngle": 90 } },
      { "type": "door", "id": "door_s02", "parentWall": "wall_back", "from": [4.6, 0, 0], "width": 0.9, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "right", "openAngle": 90 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.85, 0.83, 0.80], "roughness": 0.55, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal": { "baseColor": [0.15, 0.15, 0.15], "roughness": 0.35, "metallic": 0.65, "albedo": 1, "lightingCondition": "D65_noon" },
    "wood": { "baseColor": [0.45, 0.25, 0.10], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

### 当前不支持的能力

| 需求 | 降级方案 |
|---|---|
| 电梯井 | 4 面 `wall` 围合竖井 |
| 玻璃幕墙 | `wall` + `material=glass`（近似，非 true curtain wall） |
| `stair.autoRailing` | 不存在，手动加 `railing` 组件 |
| `floor.autoRailing`（阳台） | 不存在，手动加 `railing` |
| `window.sashType`, `sashCount` | 不存在，用 `verticalMullions` + `interaction.mode` |
| `door.style: "panel"/"flush"/"glass"` | 不存在，用 `leafMaterial` + `openingStyle` |

### 常见字段错误

| 源文档写法 ❌ | WILD Schema ✅ |
|---|---|
| `column.crossSection: "square"` | column 用 `style: "modern"`（无 crossSection 字段） |
| `window.sashType: "sliding"` | 用 `interaction.mode: "slide"` |
| `window.glassOpacity` | 不存在，材质中设 `opacity` |
| `stair.autoRailing: true` | 手动加 `railing` 组件 |
| `door.style: "panel"` | 用 `leafMaterial` 控制外观 |
