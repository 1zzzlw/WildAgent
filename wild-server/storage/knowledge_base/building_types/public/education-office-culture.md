---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: education_office_culture_family
topic: assembly
wild_version: "1.1"
status: supported
authority: engine
source: building_types/public/education-office-culture.md
keywords:
  - 教育建筑
  - 学校
  - 办公建筑
  - 写字楼
  - 博物馆
  - 剧院
  - 图书馆
---

# 公共建筑：教育 / 办公 / 文化

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 所有 JSON 示例只使用当前引擎支持的字段。

---

## 1. 教育建筑（学校）

<!-- rag-meta
entity_type: building
entity_name: school_building
topic: assembly
status: supported
authority: engine
keywords: 学校, school, 教室, 教学楼, 幼儿园, 中小学
-->

### 构件清单

| 构件 | WILD type | 关键参数 |
|---|---|---|
| 教室外墙 | `wall` | thickness=0.24, height=3.3~3.6 |
| 走廊隔墙 | `wall` | thickness=0.12, 走廊宽 2.4m |
| 框架柱 | `column` | style=modern, bottomRadius=0.2, height=3.3 |
| 楼板 | `floor` | thickness=0.15, 教室 9×6m |
| 梁 | `beam` | crossSection=rect, width=0.25, height=0.5 |
| 教室门 | `door` 组件 | width=1.0, height=2.1 |
| 教室窗 | `window` 组件 | width=2.4~3.0, height=1.8 |
| 走廊窗 | `window` 组件 | width=1.5, height=1.5 |
| 楼梯 | `stair` | width=1.8（疏散）, 两端各一 |
| 屋顶 | `roof` | roofType=flat |

### 最少可行 Blueprint（单层教学楼，18×9m，3 间教室 + 走廊）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "单层教学楼" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [18, 0, 9], "thickness": 0.15, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [18, 3.6, 0], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 9], "to": [18, 3.6, 9], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 3.6, 9], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [18, 0, 0], "to": [18, 3.6, 9], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_corridor", "from": [0, 0, 3], "to": [18, 3.6, 3], "thickness": 0.12, "material": "concrete" },
      { "type": "wall", "id": "wall_div_01", "from": [6, 0, 3], "to": [6, 3.6, 9], "thickness": 0.12, "material": "concrete" },
      { "type": "wall", "id": "wall_div_02", "from": [12, 0, 3], "to": [12, 3.6, 9], "thickness": 0.12, "material": "concrete" },
      { "type": "column", "id": "col_01", "base": [0.5, 0, 2.5], "height": 3.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_02", "base": [5.5, 0, 2.5], "height": 3.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_03", "base": [12.5, 0, 2.5], "height": 3.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_04", "base": [17.5, 0, 2.5], "height": 3.6, "bottomRadius": 0.2, "topRadius": 0.2, "style": "modern", "material": "concrete" },
      { "type": "beam", "id": "beam_corridor", "from": [0, 3.6, 3], "to": [18, 3.6, 3], "crossSection": "rect", "width": 0.25, "height": 0.5, "material": "concrete" },
      { "type": "stair", "id": "stair_west", "from": [1, 0, 0], "to": [1, 3.6, 3], "width": 1.8, "material": "concrete" },
      { "type": "stair", "id": "stair_east", "from": [17, 0, 0], "to": [17, 3.6, 3], "width": 1.8, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "flat", "span": 19, "depth": 10, "height": 0.2, "thickness": 0.15, "material": "concrete", "position": [9, 3.6, 4.5] }
    ],
    "components": [
      { "type": "door", "id": "door_class_01", "parentWall": "wall_corridor", "from": [1.5, 0, 0.12], "width": 1, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_class_02", "parentWall": "wall_corridor", "from": [7.5, 0, 0.12], "width": 1, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "door", "id": "door_class_03", "parentWall": "wall_corridor", "from": [13.5, 0, 0.12], "width": 1, "height": 2.1, "frameMaterial": "wood", "leafMaterial": "wood", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } },
      { "type": "window", "id": "win_class_01", "parentWall": "wall_back", "from": [1.5, 1, 0], "width": 3, "height": 1.8, "verticalMullions": 2, "horizontalMullions": 1, "frameMaterial": "metal", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_class_02", "parentWall": "wall_back", "from": [7.5, 1, 0], "width": 3, "height": 1.8, "verticalMullions": 2, "horizontalMullions": 1, "frameMaterial": "metal", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } },
      { "type": "window", "id": "win_class_03", "parentWall": "wall_back", "from": [13.5, 1, 0], "width": 3, "height": 1.8, "verticalMullions": 2, "horizontalMullions": 1, "frameMaterial": "metal", "glassMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.85, 0.83, 0.80], "roughness": 0.55, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "wood": { "baseColor": [0.45, 0.25, 0.10], "roughness": 0.7, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal": { "baseColor": [0.15, 0.15, 0.15], "roughness": 0.35, "metallic": 0.65, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

---

## 2. 办公建筑

<!-- rag-meta
entity_type: building
entity_name: office_building
topic: assembly
status: supported
authority: engine
keywords: 办公建筑, office, 写字楼, 开敞办公
-->

办公楼与教学楼结构相似。主要差异：层高 3.3~3.9m，走廊宽 1.8m，大量使用 `window` 落地玻璃。高层写字楼需 `column` + `beam` 框架 + `roofType=flat`。**最少可行 Blueprint 可将上面的学校示例中的教室隔墙去掉，改为大空间开敞办公。**

---

## 3. 文化建筑

<!-- rag-meta
entity_type: building
entity_name: cultural_building
topic: assembly
status: supported
authority: engine
keywords: 博物馆, museum, 剧院, theater, 图书馆, library, 大空间
-->

### 三种文化建筑的构件差异

| 建筑 | 特征 | 关键 WILD 表达 |
|---|---|---|
| 博物馆 | 大跨无柱展厅 | `beam` crossSection=rect 大截面 + `roof` flat + `column` 周边柱 |
| 剧院 | 通高观众厅 + 舞台塔 | `wall` 围合观众厅 + `floor` 多层楼座 + `roof` gable 大跨 |
| 图书馆 | 高书架 + 阅览区 | `wall` 密集隔墙 + `beam` 承受书架荷载 + 大面积 `window` 采光 |

### 最少可行 Blueprint（小型博物馆展厅，15×10m）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "小型博物馆" },
  "geometry": {
    "elements": [
      { "type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [15, 0, 10], "thickness": 0.2, "material": "concrete" },
      { "type": "wall", "id": "wall_front", "from": [0, 0, 0], "to": [15, 5, 0], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_back", "from": [0, 0, 10], "to": [15, 5, 10], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_left", "from": [0, 0, 0], "to": [0, 5, 10], "thickness": 0.24, "material": "concrete" },
      { "type": "wall", "id": "wall_right", "from": [15, 0, 0], "to": [15, 5, 10], "thickness": 0.24, "material": "concrete" },
      { "type": "column", "id": "col_01", "base": [0.5, 0, 0.5], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_02", "base": [14.5, 0, 0.5], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_03", "base": [0.5, 0, 9.5], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "column", "id": "col_04", "base": [14.5, 0, 9.5], "height": 5, "bottomRadius": 0.3, "topRadius": 0.25, "style": "modern", "material": "concrete" },
      { "type": "beam", "id": "beam_main_01", "from": [0.5, 5, 0.5], "to": [14.5, 5, 0.5], "crossSection": "rect", "width": 0.3, "height": 0.6, "material": "concrete" },
      { "type": "beam", "id": "beam_main_02", "from": [0.5, 5, 9.5], "to": [14.5, 5, 9.5], "crossSection": "rect", "width": 0.3, "height": 0.6, "material": "concrete" },
      { "type": "roof", "id": "roof_main", "roofType": "flat", "span": 16, "depth": 11, "height": 0.3, "thickness": 0.2, "material": "concrete", "position": [7.5, 5, 5] }
    ],
    "components": [
      { "type": "door", "id": "door_entry", "parentWall": "wall_front", "from": [6.5, 0, 0], "width": 2, "height": 3, "doorStyle": "double", "frameWidth": 0, "frameMaterial": "metal", "leafMaterial": "glass", "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 } }
    ]
  },
  "materials": {
    "concrete": { "baseColor": [0.88, 0.86, 0.83], "roughness": 0.5, "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon" },
    "metal": { "baseColor": [0.12, 0.12, 0.12], "roughness": 0.3, "metallic": 0.7, "albedo": 1, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0, "albedo": 1, "opacity": 0.35, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

### 当前不支持的能力

| 需求 | 降级方案 |
|---|---|
| 大跨桁架/网架屋顶（剧院/体育馆） | 用多根 `beam` 密集排列 |
| 剧场舞台塔/乐池 | `primitive.box` 组合 |
| 圆形/椭圆形阅览室 | 用 `wall` + `curve={type:"arc"}` |
| `beam.crossSection: "i-beam"` | ✅ 已支持，大跨时使用 |
| 穹顶 museum rotunda | `roofType=dome` + `wall` 弧形围合 |
