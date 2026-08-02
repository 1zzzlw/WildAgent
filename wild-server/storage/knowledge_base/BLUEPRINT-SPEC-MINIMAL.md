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
  "geometry": { "elements": [], "components": [] },
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

### opening（墙体洞口）⚠️ 坐标最容易出错
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
- 不要为篮球、花瓶等名词发明新的 `geometry.elements.type`；檐口等已注册语义组件只能写入 `geometry.components`。

---

## 10 种组合构件（只能写入 geometry.components）

`door`、`window`、`railing`、`canopy`、`balcony`、`ramp`、`bay_window`、`cornice`、`chimney`、`light` 是组合构件编译器输入，不是 `geometry.elements` 类型。编译器会在渲染前把它们转换为 Core 基础元素。

### door（门）

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "door",
  "id": "front_door",
  "parentWall": "wall_front",
  "from": [2.4, 0.0, 0],
  "width": 1.2,
  "height": 2.2,
  "frameMaterial": "wood",
  "leafMaterial": "door_wood",
  "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 }
}
```

- 必填：`id`、`parentWall`、`from`、`width`、`height`、**`interaction`**。
- `from` 与 opening 相同：`[沿父墙弧长距离, 底部世界Y, 法向偏移]`；支持直线墙和单段曲线墙。
- **`interaction` 是必填项**，不提供则门无法开合；默认使用 `{"mode": "swing", "hingeSide": "left", "openAngle": 90}`；支持 `swing/slide`；前端左键选择、右键开合，不包含碰撞。

### window（窗）

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "window",
  "id": "front_window",
  "parentWall": "wall_front",
  "from": [4.2, 0.9, 0],
  "width": 1.2,
  "height": 1.2,
  "verticalMullions": 1,
  "horizontalMullions": 1,
  "frameMaterial": "window_frame",
  "glassMaterial": "glass",
  "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 60 }
}
```

- 必填：`id`、`parentWall`、`from`、`width`、`height`、**`interaction`**。
- `verticalMullions` 和 `horizontalMullions` 是 0–32 的整数。
- `mullion` 不是独立 element 或 component 类型。
- **`interaction` 是必填项**，不提供则窗无法开合；默认使用 `{"mode": "swing", "hingeSide": "left", "openAngle": 60}`；支持直线墙、单段曲线墙。交互式双窗扇可分别右键开合，也可同时处于打开状态。

### railing（路径栏杆）

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "railing",
  "id": "terrace_railing",
  "path": [[0, 3, 0], [4, 3, 0]],
  "height": 1.1,
  "postSpacing": 0.8,
  "railLevels": [0.5, 1.0],
  "material": "metal"
}
```

- `path` 至少包含两个不重合点；默认是世界坐标，指定 `parentFloor` 后使用楼板局部坐标。
- `railLevels` 为 `(0, 1]` 的栏杆相对高度比例。
- 当前不会自动从 stair 或 ramp 推导路径，也不表示通过建筑规范校核。

### 第二批组件最小字段

| type | 必填字段 | 关键边界 |
|---|---|---|
| `canopy` | `id,parentWall,from,width,depth,thickness` | 墙体雨棚板和可选支柱 |
| `balcony` | `id,parentWall,from,width,depth,slabThickness` | 悬挑板和 U 形栏杆；**slabThickness 必填** |
| `ramp` | `id,from,to,width,thickness` | 仅直线坡道；可选左右栏杆 |
| `bay_window` | `id,parentWall,from,width,height,projectionDepth` | 静态凸窗投影体 |
| `cornice` | `id,path,profile` | 截面沿路径扫掠 |
| `chimney` | `id,position,width,depth,height` | 薄壁外观；不做屋顶真实穿透 |

`cornice`、`chimney` 的可选 `parentRoof` 只支持 `flat/gable/hip` 局部依附。通用 CSG、屋顶布尔穿透和地形贴合仍未实现。

### light（可发光灯具）

<!-- rag-meta
entity_type: light
entity_name: interactive_light_fixture
topic: schema
status: supported
authority: schema
keywords: 灯具, 台灯, 灯泡, light, table_lamp, fixtureType, lightType
-->

以下是 `geometry.components` 数组中的台灯片段，不是完整 `.wild` 文件：

```json
{
  "type": "light",
  "id": "desk_lamp",
  "fixtureType": "table_lamp",
  "position": [1.5, 0.75, 1.0],
  "lightType": "point",
  "color": [1.0, 0.78, 0.52],
  "lowIntensity": 18,
  "highIntensity": 65,
  "distance": 8,
  "height": 0.72,
  "shadeRadius": 0.28,
  "baseHeight": 0.07,
  "initiallyOn": false,
  "draggable": true
}
```

- `fixtureType` 是灯具外观业务类型，只能是 `bulb` 或 `table_lamp`；`lightType` 是发光算法，只能是 `point` 或 `spot`，二者不要混用。
- 用户要求台灯、亮灯、发光或可开关灯具时，必须使用 `geometry.components` 中的 `light`。旧版 `furniture.subtype: "lamp"` 只是静态家具占位，不产生真实光照。
- **`initiallyOn` 是必填项**，默认 `true` 表示默认亮灯；`false` 表示默认关灯。
- `table_lamp` 会编译为灯泡、底座、灯杆和灯罩，`position` 是台灯底座所在支承面的锚点；`bulb` 的 `position` 是灯泡中心。
- 右键在关灯、弱光和强光之间循环；运行时亮度级别不写回 Blueprint，`initiallyOn` 只保存初始状态。
- `draggable: true` 只允许用户手动拖动并把位置写回当前草稿，不表示已经实现自动贴桌面或空间碰撞校验。

---

## 材质格式（铁律）

```json
{
"materials": {
  "wood":  { "baseColor": [0.55, 0.27, 0.07], "roughness": 0.7, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "stone": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "tile":  { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "metal": { "baseColor": [0.7, 0.7, 0.7],   "roughness": 0.3,  "metallic": 0.9, "albedo": 1.0, "lightingCondition": "D65_noon" },
  "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0.0, "albedo": 1.0, "opacity": 0.35, "lightingCondition": "D65_noon" }
}
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
  "meta": { "version": "1.1", "type": "building", "name": "简单小屋" },
  "geometry": {
    "elements": [
      { "type": "floor",   "id": "floor_1",   "from": [0,0,0],   "to": [6,0,5],   "thickness": 0.2, "material": "stone" },
      { "type": "wall",    "id": "wall_front", "from": [0,0,0],   "to": [6,3,0],   "thickness": 0.3, "material": "wood" },
      { "type": "wall",    "id": "wall_back",  "from": [0,0,5],   "to": [6,3,5],   "thickness": 0.3, "material": "wood" },
      { "type": "wall",    "id": "wall_left",  "from": [0,0,0],   "to": [0,3,5],   "thickness": 0.3, "material": "wood" },
      { "type": "wall",    "id": "wall_right", "from": [6,0,0],   "to": [6,3,5],   "thickness": 0.3, "material": "wood" },
      {
        "type": "roof", "id": "main_roof", "roofType": "gable",
        "span": 7.0, "depth": 6.0, "height": 2.0, "thickness": 0.3,
        "material": "tile", "position": [3, 3, 2.5]
      }
    ],
    "components": [
      {
        "type": "door", "id": "front_door", "parentWall": "wall_front",
        "from": [2.4, 0.0, 0], "width": 1.2, "height": 2.2,
        "frameMaterial": "wood", "leafMaterial": "door_wood"
      },
      {
        "type": "window", "id": "front_window", "parentWall": "wall_front",
        "from": [4.8, 0.9, 0], "width": 1.0, "height": 1.0,
        "verticalMullions": 1, "horizontalMullions": 1,
        "frameMaterial": "window_frame", "glassMaterial": "glass"
      }
    ]
  },
  "materials": {
    "wood":  { "baseColor": [0.55, 0.27, 0.07], "roughness": 0.7,  "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "stone": { "baseColor": [0.62, 0.59, 0.55], "roughness": 0.9,  "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "tile":  { "baseColor": [0.60, 0.25, 0.15], "roughness": 0.85, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "door_wood": { "baseColor": [0.38, 0.16, 0.06], "roughness": 0.72, "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "window_frame": { "baseColor": [0.18, 0.18, 0.18], "roughness": 0.35, "metallic": 0.65, "albedo": 1.0, "lightingCondition": "D65_noon" },
    "glass": { "baseColor": [0.55, 0.72, 0.82], "roughness": 0.12, "metallic": 0.0, "albedo": 1.0, "opacity": 0.35, "lightingCondition": "D65_noon" }
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
