---
doc_type: blueprint_spec
doc_scope: system
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_spec_minimal
topic: constraints
wild_version: "1.1"
status: supported
authority: schema
source: BLUEPRINT-SPEC-MINIMAL.md
keywords:
  - WILD
  - Blueprint
  - 系统铁律
  - 空间规则
  - 必填字段
---

# Wild 蓝图规范（精简版 · AI 生成专用）

> 完整规范见 BLUEPRINT-SPEC-FULL.md（用于 RAG 检索）。本文档只含 AI 生成必需的最小信息。

---

## 顶层结构（必须严格遵守）

```json
{
  "meta": { "version": "1.1", "type": "building", "name": "建筑名称" },
  "geometry": { "elements": [] },
  "materials": {},
  "behaviors": {}
}
```

禁止在根级别出现 elements、bounds 或其他字段。

---

## 全局空间规则

- 两面墙体在转角处相接时必须共享完全相同的端点坐标，不能使用近似值。
- 生成屋顶前应先使用 `get_wall_bounding_box` 获取墙体包围盒，不要猜测尺寸。
- `roof.span` 必须覆盖墙体 X 方向范围，`roof.depth` 必须覆盖墙体 Z 方向范围；需要出檐时在两侧增加相应余量。
- `roof.position` 应位于墙体 XZ 中心和墙顶高度。

---

## 11 种构件必填字段速查

### wall（墙体）
```json
{
  "type": "wall", "id": "wall_front",
  "from": [0, 0, 0], "to": [6, 3, 0],
  "thickness": 0.3, "material": "wood"
}
```
- from/to 均为世界坐标 [X, Y, Z]，from[1] 是墙底，to[1] 是墙顶

### floor（地板）
```json
{
  "type": "floor", "id": "ground_floor",
  "from": [0, 0, 0], "to": [6, 0, 5],
  "thickness": 0.2, "material": "stone"
}
```

### column（柱子）
```json
{
  "type": "column", "id": "col_1",
  "base": [0, 0, 0], "height": 3,
  "bottomRadius": 0.12, "topRadius": 0.1,
  "style": "modern", "material": "wood"
}
```
- style 可选值：doric / ionic / corinthian / modern / chinese_wooden

### beam（梁）
```json
{
  "type": "beam", "id": "beam_1",
  "from": [0, 3, 0], "to": [6, 3, 0],
  "crossSection": "rect", "width": 0.15, "height": 0.25,
  "material": "wood"
}
```

### roof（屋顶）
```json
{
  "type": "roof", "id": "main_roof",
  "roofType": "gable",
  "span": 7.0, "depth": 6.0, "height": 2.5,
  "thickness": 0.3, "material": "tile",
  "position": [3, 3, 2.5]
}
```
- roofType 可选：gable（双坡） / hip（四坡） / dome（穹顶） / flat（平顶） / chinese_curved（中式曲面） / chinese_pagoda（多层塔顶）
- span 覆盖 X 方向，depth 覆盖 Z 方向，必须大于等于墙体范围

### opening（门窗）⚠️ 坐标最容易出错
```json
{
  "type": "opening", "id": "front_door",
  "parentWall": "wall_front",
  "from": [2.0, 0.0, 0],
  "width": 1.2, "height": 2.2,
  "style": "rectangular", "material": "wood"
}
```
- **from[0] = 沿墙距离**（从 parentWall.from 沿墙方向量起，单位米）
- **from[1] = 开口底部的世界 Y 坐标**（通常与墙底 Y 相同表示落地门）
- **from[2] = 0**（法向偏移，通常不动）
- ❌ 绝对禁止把世界坐标填入 from[0]

### stair（楼梯）
```json
{
  "type": "stair", "id": "main_stair",
  "from": [2, 0, 1], "to": [2, 3, 4],
  "width": 1.2, "material": "wood"
}
```
- from[1] = 下层地板 Y，to[1] = 上层地板 Y，from[1] < to[1]

### furniture（参数化家具）
```json
{
  "type": "furniture", "id": "lamp_1",
  "subtype": "lamp",
  "position": [3, 2.5, 2],
  "dimensions": { "width": 0.3, "depth": 0.3, "height": 0.5 },
  "material": "metal"
}
```
- subtype 可选：table / chair / bookshelf / bed / lamp / tile。
- `furniture` 适合中低细节参数化家具；需要特殊结构时再用基础构件或 `primitive` 组合。

### dense_brick（体素）

当前参考引擎状态为 `experimental`，体素解压与等值面提取尚未实现。AI 不应生成 `dense_brick`；如确实需要，先向用户说明该构件会产生 `ELEMENT_BUILD_FAILED` 诊断。

### body（化身）
```json
{
  "type": "body", "id": "avatar_1",
  "height": 1.75, "build": "athletic",
  "headShape": "round",
  "armLength": 0.6, "legLength": 0.9,
  "cloakLength": 0, "hoodUp": false
}
```

### primitive（v1.1 通用形体）

```json
{
  "type": "primitive", "id": "ball_body",
  "shape": "sphere", "position": [0, 0.12, 0],
  "radius": 0.12, "segments": 32, "heightSegments": 20,
  "material": "orange_rubber"
}
```

- shape 可选：box / sphere / cylinder / profile_sweep。
- box 使用 `dimensions: [width, height, depth]`。
- cylinder 使用 `height` 和 `radius`，或 `radiusTop` / `radiusBottom`。
- profile_sweep 使用 `path: Vec3[]`，可选闭合 `profile: [number, number][]`；未给 profile 时可用 `radius` + `segments` 生成圆截面。
- 不要为篮球、花瓶、檐口等名词发明新 type；优先由多个 primitive、模板和已有构件组合。

---

## 材质格式（铁律）

```json
"materials": {
  "wood":  { "baseColor": [0.55, 0.27, 0.07], "roughness": 0.7, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "stone": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "tile":  { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "metal": { "baseColor": [0.7, 0.7, 0.7],   "roughness": 0.3,  "metallic": 0.9, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0.0, "albedo": 1.0, "opacity": 0.35, "lightingCondition": "D65_noon" }
}
```
- baseColor 必须是 [R, G, B] 数组（0.0~1.0），**绝对禁止** "#RRGGBB" 字符串
- baseColor、emissive 和效果层中的数值颜色统一按 sRGB authored value 表达，由渲染器转换到线性工作空间
- 用户未指定颜色时，必须采用检索到的建筑类型默认配色；墙、楼板、屋顶、门、玻璃应使用角色独立的材质名
- 不要默认把墙、楼板和屋顶全部设成同一个 `concrete`；玻璃材质必须显式给出 `opacity`

---

## 常用尺寸参考

| 构件 | 典型值 |
|------|--------|
| 层高 | 2.8 ~ 3.5 m |
| 墙厚 | 0.2 ~ 0.4 m |
| 门宽/高 | 1.0 m / 2.2 m |
| 窗宽/高 | 1.2 m / 1.2 m |
| 窗台高（世界Y） | 墙底 Y + 0.9 m |
| 柱半径 | 0.08 ~ 0.15 m |

---

## 完整示例：简单小屋（4墙 + 地板 + 2门窗 + 屋顶）

```json
{
  "meta": { "version": "1.0", "type": "building", "name": "简单小屋" },
  "geometry": {
    "elements": [
      { "type": "floor",   "id": "floor_1",   "from": [0,0,0],   "to": [6,0,5],   "thickness": 0.2, "material": "stone" },
      { "type": "wall",    "id": "wall_front", "from": [0,0,0],   "to": [6,3,0],   "thickness": 0.3, "material": "wood" },
      { "type": "wall",    "id": "wall_back",  "from": [0,0,5],   "to": [6,3,5],   "thickness": 0.3, "material": "wood" },
      { "type": "wall",    "id": "wall_left",  "from": [0,0,0],   "to": [0,3,5],   "thickness": 0.3, "material": "wood" },
      { "type": "wall",    "id": "wall_right", "from": [6,0,0],   "to": [6,3,5],   "thickness": 0.3, "material": "wood" },
      {
        "type": "opening", "id": "front_door", "parentWall": "wall_front",
        "from": [2.4, 0.0, 0], "width": 1.2, "height": 2.2,
        "style": "rectangular", "material": "wood"
      },
      {
        "type": "opening", "id": "front_window", "parentWall": "wall_front",
        "from": [4.8, 0.9, 0], "width": 1.0, "height": 1.0,
        "style": "rectangular", "material": "wood"
      },
      {
        "type": "roof", "id": "main_roof", "roofType": "gable",
        "span": 7.0, "depth": 6.0, "height": 2.0, "thickness": 0.3,
        "material": "tile", "position": [3, 3, 2.5]
      }
    ]
  },
  "materials": {
    "wood":  { "baseColor": [0.55, 0.27, 0.07], "roughness": 0.7,  "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "stone": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9,  "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "tile":  { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" }
  },
  "behaviors": {}
}
```

**注意 opening 沿墙距离验算**：
- wall_front: from=[0,0,0] → to=[6,3,0]，方向 X+，墙长 6m
- front_door: from[0]=2.4（距起点 2.4m，居中偏左）✓
- front_window: from[0]=4.8（距起点 4.8m，右侧）✓

---

## 板凳示例（禁止用 furniture，必须用构件组合）

```json
{
  "elements": [
    { "type": "column", "id": "leg_fl", "base": [-0.5, 0, -0.15], "height": 0.42, "bottomRadius": 0.03, "topRadius": 0.03, "style": "modern", "material": "wood" },
    { "type": "column", "id": "leg_fr", "base": [ 0.5, 0, -0.15], "height": 0.42, "bottomRadius": 0.03, "topRadius": 0.03, "style": "modern", "material": "wood" },
    { "type": "column", "id": "leg_bl", "base": [-0.5, 0,  0.15], "height": 0.42, "bottomRadius": 0.03, "topRadius": 0.03, "style": "modern", "material": "wood" },
    { "type": "column", "id": "leg_br", "base": [ 0.5, 0,  0.15], "height": 0.42, "bottomRadius": 0.03, "topRadius": 0.03, "style": "modern", "material": "wood" },
    { "type": "floor",  "id": "seat",  "from": [-0.55, 0.42, -0.2], "to": [0.55, 0.42, 0.2], "thickness": 0.05, "material": "wood" }
  ]
}
```
