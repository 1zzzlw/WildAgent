---
building_category: residential
entity_name: villa
topic: assembly
status: supported
authority: engine
source: building_types/residential/villas.md
primary_terms:
  - 别墅
  - 现代别墅
  - 中式传统别墅
  - 新中式别墅
  - 四合院
  - 低层住宅
synonyms:
  - villa
---

# 居住建筑：别墅

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：现代别墅、中式传统别墅、新中式别墅的 WILD Blueprint 配方。
> 所有 JSON 示例只使用当前引擎支持的字段和类型。

---

## 1.1 现代别墅（架空层 + 水平长窗）

<!-- rag-meta
entity_type: building
entity_name: modern_villa
topic: assembly
status: supported
authority: engine
primary_terms:
  - 现代别墅
  - 架空层
  - 水平长窗
  - pilotis
synonyms:
  - modern villa
-->

### 构件清单（仅列当前引擎支持的类型）

| 构件 | WILD type | 关键参数 |
|---|---|---|
| 架空柱 | `column` | style=modern, bottomRadius=0.15, topRadius=0.15, height=3.0 |
| 底层楼板 | `floor` | shape=rect, thickness=0.15 |
| 二层悬挑板 | `floor` | shape=rect, thickness=0.15 |
| 外围护墙 | `wall` | thickness=0.15, height=3.0 |
| 弧形入口墙 | `wall` | curve={type:"arc", sweep:180} |
| 水平带状窗 | `window` 组件 | parentWall=wall, width≥1.0, height=1.1 |
| 平屋顶板 | `roof` | roofType=flat, thickness=0.15 |
| 室内楼梯 | `stair` | from→to, width=1.0 |
| 入口门 | `door` 组件 | width=1.2, height=2.4, openingStyle=arched |
| 入口雨棚 | `canopy` 组件 | parentWall=wall, depth=1.2, thickness=0.12 |
| 无障碍坡道 | `ramp` 组件 | from→to, width=1.2, thickness=0.15 |

### 最少可行 Blueprint（10×8m 现代别墅，2F）

以下是完整 `.wild` 文件：

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "现代别墅" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_ground", "from": [0, 0, 0], "to": [10, 0, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "floor", "id": "floor_upper", "from": [0, 3, 0], "to": [10, 3, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "column", "id": "col_01", "base": [0.5, 0, 0.5], "height": 6.0, "bottomRadius": 0.15, "topRadius": 0.15, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_02", "base": [9.5, 0, 0.5], "height": 6.0, "bottomRadius": 0.15, "topRadius": 0.15, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_03", "base": [0.5, 0, 7.5], "height": 6.0, "bottomRadius": 0.15, "topRadius": 0.15, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_04", "base": [9.5, 0, 7.5], "height": 6.0, "bottomRadius": 0.15, "topRadius": 0.15, "style": "modern", "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 8], "to": [10, 3, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 3, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [10, 0, 0], "to": [10, 3, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_upper_front", "from": [0, 3, 0], "to": [10, 6, 0], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_upper_back", "from": [0, 3, 8], "to": [10, 6, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_upper_left", "from": [0, 3, 0], "to": [0, 6, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_upper_right", "from": [10, 3, 0], "to": [10, 6, 8], "thickness": 0.2, "material": "concrete" },
      { "type": "stair", "id": "stair_main", "from": [8, 0, 1], "to": [8, 3, 4], "width": 1.0, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "flat", "span": 11.0, "depth": 9.0, "height": 0.3, "thickness": 0.2, "material": "concrete", "position": [5, 6, 4] }
    ],
    "components": [
      { "type": "door", "id": "door_entry", "parentWall": "wall_front", "from": [4.4, 0, 0], "width": 1.2, "height": 2.4, "frameMaterial": "metal", "leafMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "window", "id": "win_left", "parentWall": "wall_front", "from": [0.8, 1.0, 0], "width": 3.0, "height": 1.1, "verticalMullions": 2, "horizontalMullions": 0, "frameMaterial": "metal", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_right", "parentWall": "wall_front", "from": [6.2, 1.0, 0], "width": 3.0, "height": 1.1, "verticalMullions": 2, "horizontalMullions": 0, "frameMaterial": "metal", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "canopy", "id": "canopy_entry", "parentWall": "wall_front", "from": [4.2, 2.5, 0], "width": 1.6, "depth": 1.2, "thickness": 0.12, "supportCount": 2, "material": "concrete" },
      { "type": "ramp", "id": "ramp_entry", "from": [4.0, 0, -1.2], "to": [4.0, 0, 0], "width": 1.2, "thickness": 0.15, "material": "concrete" }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.85, 0.85, 0.82], "roughness": 0.6, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "metal": { "baseColor": [0.15, 0.15, 0.15], "roughness": 0.35, "metallic": 0.65, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0.0, "albedo": 1.0, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

### 组装顺序

`floor → column → wall → door/window → stair → roof → canopy → ramp`

---

## 1.2 中式传统别墅（四合院/江南民居）

<!-- rag-meta
entity_type: building
entity_name: chinese_traditional_villa
topic: assembly
status: supported
authority: engine
primary_terms:
  - 中式别墅
  - 四合院
  - 江南民居
  - 木构架
synonyms:
  - Chinese traditional villa
-->

### 构件清单

| 构件 | WILD type | 关键参数 |
|---|---|---|
| 檐柱 | `column` | style=chinese_wooden, bottomRadius=0.18~0.25, topRadius=0.20, height=3.0~4.5 |
| 金柱 | `column` | style=chinese_wooden, bottomRadius=0.20, height=4.5~6.0 |
| 额枋/梁 | `beam` | crossSection=rect, width=0.15, height=0.25 |
| 檩条 | `beam` | crossSection=circular, width=0.10, height=0.10（直径=宽度×2） |
| 青砖墙 | `wall` | thickness=0.24, height=3.0~4.5 |
| 台基 | `floor` | shape=rect, thickness=0.5~1.0 |
| 举折屋面 | `roof` | roofType=chinese_curved |
| 隔扇门 | `door` 组件 | width=0.9~1.0/扇, height=2.4 |
| 槛窗 | `window` 组件 | width=0.9, height=1.5, verticalMullions=2~4 |
| 漏窗（院墙） | `window` 组件 | width=0.6, height=0.6 |
| 飞檐檐口 | `cornice` 组件 | path=屋面边缘, profile=弧形截面 |
| 游廊 | `beam` + `railing` | 柱间梁 + 矮栏杆 height=0.5 |

### 最少可行 Blueprint（一进四合院正房，面阔 12m，进深 6m）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "四合院正房" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_platform", "from": [0, 0, 0], "to": [12, 0.6, 6], "thickness": 0.6, "material": "stone_grey" },
      { "type": "column", "id": "col_eave_01", "base": [0, 0.6, 0], "height": 3.6, "bottomRadius": 0.22, "topRadius": 0.20, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_eave_02", "base": [6, 0.6, 0], "height": 3.6, "bottomRadius": 0.22, "topRadius": 0.20, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_eave_03", "base": [12, 0.6, 0], "height": 3.6, "bottomRadius": 0.22, "topRadius": 0.20, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_eave_04", "base": [0, 0.6, 6], "height": 3.6, "bottomRadius": 0.22, "topRadius": 0.20, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_eave_05", "base": [6, 0.6, 6], "height": 3.6, "bottomRadius": 0.22, "topRadius": 0.20, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "column", "id": "col_eave_06", "base": [12, 0.6, 6], "height": 3.6, "bottomRadius": 0.22, "topRadius": 0.20, "style": "chinese_wooden", "material": "wood_red" },
      { "type": "beam", "id": "beam_eave_front", "from": [0, 3.6, 0], "to": [12, 3.6, 0], "crossSection": "rect", "width": 0.15, "height": 0.25, "material": "wood_red" },
      { "type": "beam", "id": "beam_eave_back", "from": [0, 3.6, 6], "to": [12, 3.6, 6], "crossSection": "rect", "width": 0.15, "height": 0.25, "material": "wood_red" },
      { "type": "wall", "id": "wall_back", "from": [0, 0.6, 6], "to": [12, 3.6, 6], "thickness": 0.24, "material": "brick_grey" },
      { "type": "wall", "id": "wall_left", "from": [0, 0.6, 0], "to": [0, 3.6, 6], "thickness": 0.24, "material": "brick_grey" },
      { "type": "wall", "id": "wall_right", "from": [12, 0.6, 0], "to": [12, 3.6, 6], "thickness": 0.24, "material": "brick_grey" },
      { "type": "roof", "id": "roof_main", "roofType": "chinese_curved", "span": 13.5, "depth": 7.5, "height": 2.5, "thickness": 0.2, "material": "tile_grey", "position": [6, 3.6, 3], "eaveCurveHeight": 0.6 }
    ],
    "components": [
      { "type": "door", "id": "door_main_left", "parentWall": "beam_eave_front", "from": [3.0, 0.6, -0.12], "width": 0.9, "height": 2.4, "doorStyle": "double", "frameWidth": 0, "frameMaterial": "wood_red", "leafMaterial": "wood_red", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "window", "id": "win_left_side", "parentWall": "wall_left", "from": [1.5, 1.5, 0], "width": 0.9, "height": 1.5, "verticalMullions": 3, "horizontalMullions": 2, "frameMaterial": "wood_red", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_right_side", "parentWall": "wall_right", "from": [1.5, 1.5, 0], "width": 0.9, "height": 1.5, "verticalMullions": 3, "horizontalMullions": 2, "frameMaterial": "wood_red", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "cornice", "id": "cornice_eave", "path": [[-0.5, 3.6, -0.5], [12.5, 3.6, -0.5]], "profile": [[0, 0], [0.3, 0], [0.2, -0.2], [0, -0.3]], "closedProfile": false, "material": "wood_red", "parentRoof": "roof_main" }
    ]
  },
  "materials": {
    "stone_grey": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "wood_red": { "baseColor": [0.55, 0.22, 0.12], "roughness": 0.65, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "brick_grey": { "baseColor": [0.42, 0.38, 0.35], "roughness": 0.85, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "tile_grey": { "baseColor": [0.25, 0.25, 0.27], "roughness": 0.75, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0.0, "albedo": 1.0, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

> 注意：中式别墅的 `wood_red` 材质用 baseColor `[0.55, 0.22, 0.12]` 模拟传统红木色。`tile_grey` 用 `[0.25, 0.25, 0.27]` 模拟小青瓦深灰色。`brick_grey` 模拟青砖墙。

### 当前不支持的能力

| 需求 | 降级方案 |
|---|---|
| 隔扇门棂花图案（步步锦/灯笼锦） | 门扇之间放 `window` 组件替代棂花部分 |
| 漏窗雕花图案 | 用多个细 `primitive.box` 排列模拟 |
| 美人靠/坐凳栏杆 | 用 `primitive.box` 组合 + `railing` 矮栏杆 |
| 影壁砖雕 | 用 `primitive.box` 薄板 + 材质颜色区分 |
| 垂花门垂莲柱 | 用两个 `column` 倒置 + `primitive.sphere` 模拟 |
| 游廊连续屋面 | 用多个 `roof` + `beam` 分段组合 |

---

## 1.3 新中式别墅（现代材料 + 传统美学）

<!-- rag-meta
entity_type: building
entity_name: neo_chinese_villa
topic: assembly
status: supported
authority: engine
primary_terms:
  - 新中式别墅
  - 框架结构
  - 传统美学
synonyms:
  - neo-Chinese villa
-->

新中式别墅采用**框架结构 + 传统坡屋顶 + 简化装饰**。构件组合为：

```
column(框架柱) + beam(框架梁) → floor(楼板)
  → wall(填充墙, 非承重)
  → roof(chinese_curved 或 gable)
  → door(简洁面板) + window(大玻璃+竖向窗棂)
```

### 最少可行 Blueprint（8×6m 新中式小别墅，2F）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "新中式别墅" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_ground", "from": [0, 0, 0], "to": [8, 0, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "floor", "id": "floor_upper", "from": [0, 3.3, 0], "to": [8, 3.3, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "column", "id": "col_01", "base": [0.5, 0, 0.5], "height": 6.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete_light" },
      { "type": "column", "id": "col_02", "base": [7.5, 0, 0.5], "height": 6.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete_light" },
      { "type": "column", "id": "col_03", "base": [0.5, 0, 5.5], "height": 6.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete_light" },
      { "type": "column", "id": "col_04", "base": [7.5, 0, 5.5], "height": 6.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete_light" },
      { "type": "beam", "id": "beam_front_1f", "from": [0, 3.3, 0], "to": [8, 3.3, 0], "crossSection": "rect", "width": 0.2, "height": 0.3, "material": "concrete_light" },
      { "type": "beam", "id": "beam_back_1f", "from": [0, 3.3, 6], "to": [8, 3.3, 6], "crossSection": "rect", "width": 0.2, "height": 0.3, "material": "concrete_light" },
      { "type": "wall", "id": "wall_front_1f", "from": [0, 0, 0], "to": [8, 3.3, 0], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_back_1f", "from": [0, 0, 6], "to": [8, 3.3, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_left_1f", "from": [0, 0, 0], "to": [0, 3.3, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_right_1f", "from": [8, 0, 0], "to": [8, 3.3, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_front_2f", "from": [0, 3.3, 0], "to": [8, 6.6, 0], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_back_2f", "from": [0, 3.3, 6], "to": [8, 6.6, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_left_2f", "from": [0, 3.3, 0], "to": [0, 6.6, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "wall", "id": "wall_right_2f", "from": [8, 3.3, 0], "to": [8, 6.6, 6], "thickness": 0.2, "material": "concrete_light" },
      { "type": "stair", "id": "stair_main", "from": [6, 0, 1], "to": [6, 3.3, 4], "width": 1.0, "material": "concrete_light" },
      { "type": "roof", "id": "roof_main", "roofType": "chinese_curved", "span": 9.0, "depth": 7.0, "height": 2.0, "thickness": 0.2, "eaveCurveHeight": 0.4, "material": "tile_dark", "position": [4, 6.6, 3] }
    ],
    "components": [
      { "type": "door", "id": "door_entry", "parentWall": "wall_front_1f", "from": [3.5, 0, 0], "width": 1.0, "height": 2.3, "frameMaterial": "wood_dark", "leafMaterial": "wood_dark", "interaction": { "mode": "swing", "hingeSide": "right", "openAngle": 90 } },
      { "type": "window", "id": "win_front_1f", "parentWall": "wall_front_1f", "from": [0.6, 0.9, 0], "width": 2.3, "height": 1.5, "verticalMullions": 2, "horizontalMullions": 1, "frameMaterial": "wood_dark", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_front_2f", "parentWall": "wall_front_2f", "from": [2.0, 0.9, 0], "width": 4.0, "height": 1.6, "verticalMullions": 4, "horizontalMullions": 1, "frameMaterial": "wood_dark", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } }
    ]
  },
  "materials": {
    "concrete_light": { "baseColor": [0.88, 0.86, 0.82], "roughness": 0.55, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "wood_dark": { "baseColor": [0.28, 0.15, 0.08], "roughness": 0.65, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "tile_dark": { "baseColor": [0.2, 0.2, 0.22], "roughness": 0.75, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0.0, "albedo": 1.0, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

### 新中式配色建议

| 元素 | 材质名 | baseColor |
|---|---|---|
| 框架柱梁 | `concrete_light` | `[0.88, 0.86, 0.82]`（浅灰混凝土） |
| 木色门窗框 | `wood_dark` | `[0.28, 0.15, 0.08]`（深木色） |
| 深灰屋面 | `tile_dark` | `[0.2, 0.2, 0.22]` |
| 白墙（可选） | `white` | `[0.92, 0.90, 0.88]` |

---

## 常见的字段错误（源文档 vs WILD Schema）

| 源文档写法 ❌ | WILD Schema ✅ | 说明 |
|---|---|---|
| `column.crossSection: "circular"` | 不写 crossSection，用 `style` | column 只有 style + bottomRadius/topRadius |
| `beam.style: "chinese_wooden"` | 不写 style，用 `crossSection` | beam 用 crossSection 控制截面 |
| `wall.curve: "line"` | 不写 curve（默认直线）或 `{"type":"arc",...}` | curve 是对象不是字符串 |
| `opening` + `door` 分开写 | `door` 组件（编译器自动生成 opening） | door 是组合构件，不手动写 opening |
| `window.sashType`, `muntinPattern` | `verticalMullions` + `horizontalMullions` | 窗棂只能通过数量控制 |
| `stair.autoRailing: true` | 不存在此字段 | 栏杆需单独加 `railing` 组件 |
| `canopy.supportType` | 不存在此字段 | 用 `supportCount` 控制支柱数量 |
| `ramp.slope`, `surface` | 不存在此字段 | 通过 `from`/`to` 的高度差隐含坡度 |
