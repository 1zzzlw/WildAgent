# Wild 蓝图规范（精简版 · AI 生成专用）

> 完整规范见 BLUEPRINT-SPEC-FULL.md（用于 RAG 检索）。本文档只含 AI 生成必需的最小信息。

---

## 顶层结构（必须严格遵守）

```json
{
  "meta": { "version": "1.0", "type": "building", "name": "建筑名称" },
  "geometry": { "elements": [] },
  "materials": {},
  "behaviors": {}
}
```

禁止在根级别出现 elements、bounds 或其他字段。

---

## 10 种构件必填字段速查

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
- style 可选值：modern / classical / rustic

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
- roofType 可选：gable（双坡） / hip（四坡） / flat（平顶）
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

### furniture（仅用于灯具/瓦片）
```json
{
  "type": "furniture", "id": "lamp_1",
  "subtype": "lamp",
  "position": [3, 2.5, 2],
  "dimensions": { "width": 0.3, "depth": 0.3, "height": 0.5 },
  "material": "metal"
}
```
- ⚠️ 凳子/椅子/桌子/床 禁止用 furniture，必须用 column + floor 组合搭建

### dense_brick（体素）
```json
{
  "type": "dense_brick", "id": "voxel_1",
  "resolution": [4, 4, 4],
  "origin": [0, 0, 0],
  "data": [1,1,1,1, 1,0,0,1, 1,0,0,1, 1,1,1,1,
           0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0,
           0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0,
           1,1,1,1, 1,0,0,1, 1,0,0,1, 1,1,1,1]
}
```

### body（化身）
```json
{
  "type": "body", "id": "avatar_1",
  "height": 1.75, "build": "average",
  "headShape": "round",
  "armLength": 0.6, "legLength": 0.9,
  "cloakLength": 0, "hoodUp": false
}
```

---

## 材质格式（铁律）

```json
"materials": {
  "wood":  { "baseColor": [0.55, 0.27, 0.07], "roughness": 0.7, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "stone": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "tile":  { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "metal": { "baseColor": [0.7, 0.7, 0.7],   "roughness": 0.3,  "metallic": 0.9, "albedo": 1.0, "lightingCondition": "D65_noon" }
}
```
- baseColor 必须是 [R, G, B] 数组（0.0~1.0），**绝对禁止** "#RRGGBB" 字符串

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
