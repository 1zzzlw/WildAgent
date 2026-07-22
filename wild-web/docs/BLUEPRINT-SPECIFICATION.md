# Wild建筑蓝图规范文档 (Blueprint Specification)

## 概述

Wild蓝图是描述3D建筑场景的JSON格式文件，扩展名为`.wild`。本文档定义了蓝图文件的完整规范，用于AI生成和人工编辑。

## 文件结构

```json
{
  "meta": { /* 元数据 */ },
  "geometry": { /* 几何定义 */ },
  "materials": { /* 材质定义 */ },
  "behaviors": { /* 行为定义 */ }
}
```

---

## 1. Meta 元数据

描述蓝图的基本信息。

```json
{
  "meta": {
    "version": "1.0",
    "type": "building",
    "name": "建筑名称",
    "author": "作者名称",
    "createdAt": 1778402494274,
    "style": "rustic-cabin | modern | traditional",
    "seed": 42
  }
}
```

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| version | string | ✓ | 蓝图格式版本，当前为"1.0" |
| type | string | ✓ | 类型，通常为"building" |
| name | string | ✓ | 建筑物名称 |
| author | string | ✗ | 作者 |
| createdAt | number | ✗ | 创建时间戳（毫秒） |
| style | string | ✗ | 建筑风格 |
| seed | number | ✗ | 随机种子 |

---

## 2. Geometry 几何定义

### 2.1 结构

```json
{
  "geometry": {
    "elements": [ /* 构件列表 */ ],
    "templates": { /* 模板定义 */ },
    "placements": [ /* 放置规则 */ ]
  }
}
```

### 2.2 构件类型 (Elements)

#### 2.2.1 墙体 (Wall)

```json
{
  "type": "wall",
  "id": "wall_front",
  "from": [-8.0, 0.0, -6.0],
  "to": [8.0, 3.0, -6.0],
  "thickness": 0.3,
  "material": "exterior_stone"
}
```

**坐标系统**：
- `from`: [X, Y, Z] - 墙起点的世界坐标
- `to`: [X, Y, Z] - 墙终点的世界坐标
- 墙沿from到to的方向延伸
- Y坐标：from[1]是墙底，to[1]是墙顶

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| type | "wall" | ✓ | 固定值 |
| id | string | ✓ | 唯一标识符 |
| from | [number, number, number] | ✓ | 起点世界坐标[X,Y,Z] |
| to | [number, number, number] | ✓ | 终点世界坐标[X,Y,Z] |
| thickness | number | ✓ | 墙厚度（米） |
| material | string | ✓ | 材质ID |
| curve | object | ✗ | 弧形墙定义（见弧形墙） |

**示例**：
```json
// 沿X轴的墙（前墙）
{
  "type": "wall",
  "id": "wall_front",
  "from": [0, 0.5, 0],
  "to": [6, 3.5, 0],
  "thickness": 0.2,
  "material": "wood"
}

// 沿Z轴的墙（左墙）
{
  "type": "wall",
  "id": "wall_left",
  "from": [0, 0.5, 0],
  "to": [0, 3.5, 5],
  "thickness": 0.2,
  "material": "wood"
}
```

#### 2.2.2 弧形墙 (Curved Wall)

```json
{
  "type": "wall",
  "id": "circular_wall",
  "from": [5, 0, 0],
  "to": [5, 3, 0],
  "thickness": 0.3,
  "material": "brick",
  "curve": {
    "type": "arc",
    "center": [0, 0, 0],
    "sweep": 360,
    "segments": 32
  }
}
```

**curve字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| type | "arc" | 弧形类型 |
| center | [number, number, number] | 圆心世界坐标 |
| sweep | number | 扫掠角度（度），360为完整圆 |
| segments | number | 细分段数，影响平滑度 |

#### 2.2.3 开口 (Opening) - 门窗

**关键规范**：开口坐标使用**相对于墙体的局部坐标**，不是世界坐标！

```json
{
  "type": "opening",
  "id": "front_door",
  "parentWall": "wall_front",
  "from": [3.0, 0.0, 0.0],
  "width": 1.2,
  "height": 2.4,
  "style": "rectangular",
  "material": "oak_door"
}
```

**坐标系统（重要！）**：

`from`字段格式：`[沿墙距离, Y坐标, 法向偏移]`

- **from[0]** - **沿墙距离**：从墙起点沿墙方向的距离（米）
  - 直线墙：从wall.from到wall.to方向的距离
  - 弧形墙：沿弧长的距离
  - ⚠️ **不是世界X坐标！**

- **from[1]** - **Y坐标**：开口底部的Y坐标（**世界坐标**）
  - 使用绝对世界Y坐标，不是相对墙底的偏移
  - 例如：墙从Y=3到Y=5.8，窗户底部Y=4.0，就填4.0
  - 渲染引擎会自动处理：开口几何体的中心会放在 `Y + height/2` 位置

- **from[2]** - **法向偏移**：垂直于墙面的偏移
  - 通常为0（在墙面上）
  - 正值向外，负值向内

**计算示例**：

```javascript
// 墙体定义
wall_front: from=[-8, 0, -6], to=[8, 3, -6]  // X轴，长度16米

// 错误❌：使用世界坐标X作为沿墙距离
{"id": "door", "from": [0, 0, -6]}  // 错误！0是世界X坐标

// 正确✓：使用沿墙距离
{"id": "door", "from": [8, 0, 0]}   // 正确！中心位置（沿墙8米处）

// 沿墙距离计算：
// 世界坐标X=-5的窗户：-5 - (-8) = 3米
{"id": "window", "from": [3, 1, 0]}  // 沿墙3米，高度Y=1米（世界坐标）

// 二层墙体和窗户：
wall_upper: from=[-8, 3, -6], to=[8, 5.8, -6]  // 墙底Y=3，墙顶Y=5.8
{"id": "upper_window", "from": [8, 4.0, 0]}    // 沿墙8米，底部Y=4.0（世界坐标）
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| type | "opening" | ✓ | 固定值 |
| id | string | ✓ | 唯一标识符 |
| parentWall | string | ✓ | 所属墙体的ID |
| from | [number, number, number] | ✓ | [沿墙距离, Y坐标, 法向偏移] |
| width | number | ✓ | 宽度（米） |
| height | number | ✓ | 高度（米） |
| style | string | ✓ | 样式："rectangular" 等 |
| material | string | ✓ | 材质ID |

**完整示例**：

```json
// 墙体：前墙，X轴从0到6，长6米，高3米
{
  "type": "wall",
  "id": "front_wall",
  "from": [0, 0.5, 0],      // 墙底Y=0.5
  "to": [6, 3.5, 0],        // 墙顶Y=3.5
  "thickness": 0.2,
  "material": "wood"
}

// 正确的开口定义
{
  "type": "opening",
  "id": "front_door",
  "parentWall": "front_wall",
  "from": [2.4, 0.5, 0],    // 沿墙2.4米，底部Y=0.5（与墙底对齐）
  "width": 1.2,
  "height": 2.2,
  "style": "rectangular",
  "material": "oak_door"
}

// 渲染引擎的处理：
// 1. resolver: 转换为墙体局部坐标 localY = 0.5 - 0.5 = 0
// 2. boxWithHoles: 在墙体上切孔，孔底部在墙底向上0米
// 3. buildOpening: 生成开口几何体，中心在 Y = 0.5 + 2.2/2 = 1.6米
```

**关键点**：
- `from[1]` 填开口**底部**的世界Y坐标
- 开口几何体会自动居中（中心在 `from[1] + height/2`）
- 墙体切孔使用的是相对墙底的偏移（引擎自动转换）

#### 2.2.4 地板 (Floor)

```json
{
  "type": "floor",
  "id": "ground_floor",
  "from": [-8.0, -0.3, -6.0],
  "to": [8.0, -0.3, 8.0],
  "thickness": 0.3,
  "material": "stone_floor"
}
```

**坐标系统**：
- `from`, `to`: 定义矩形区域的对角点
- Y坐标通常相同（水平地板）
- thickness向下延伸

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| from | [number, number, number] | ✓ | 区域角点1 |
| to | [number, number, number] | ✓ | 区域角点2 |
| thickness | number | ✓ | 厚度（米） |
| material | string | ✓ | 材质ID |

#### 2.2.5 屋顶 (Roof)

```json
{
  "type": "roof",
  "id": "main_roof",
  "roofType": "gable",
  "span": 17.0,
  "depth": 15.0,
  "height": 3.0,
  "thickness": 0.3,
  "material": "roof_tile",
  "position": [0, 5.8, 1]
}
```

**roofType类型**：
- `gable`: 双坡屋顶
- `hip`: 四坡屋顶
- `flat`: 平屋顶

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| roofType | string | ✓ | 屋顶类型 |
| span | number | ✓ | 跨度（X方向，米） |
| depth | number | ✓ | 进深（Z方向，米） |
| height | number | ✓ | 高度（米） |
| thickness | number | ✗ | 厚度（米） |
| material | string | ✓ | 材质ID |
| position | [number, number, number] | ✗ | 位置（自动计算时可省略） |

#### 2.2.6 柱子 (Column)

```json
{
  "type": "column",
  "id": "corner_pillar_1",
  "base": [0, 0.5, 0],
  "height": 3,
  "bottomRadius": 0.12,
  "topRadius": 0.1,
  "style": "modern",
  "material": "wood"
}
```

#### 2.2.7 梁 (Beam)

```json
{
  "type": "beam",
  "id": "beam_front",
  "from": [-8.0, 3.0, -6.0],
  "to": [8.0, 3.0, -6.0],
  "crossSection": "rect",
  "width": 0.15,
  "height": 0.25,
  "material": "oak_beam"
}
```

#### 2.2.8 楼梯 (Stair)

```json
{
  "type": "stair",
  "id": "main_stair",
  "from": [2.0, 0.0, 1.0],
  "to": [2.0, 3.0, 4.0],
  "width": 1.2,
  "material": "oak_stair"
}
```

#### 2.2.9 家具 (Furniture)

```json
{
  "type": "furniture",
  "id": "living_table",
  "subtype": "table",
  "position": [-1.5, 0.0, -2.0],
  "style": "rustic_wooden",
  "dimensions": {
    "width": 2.0,
    "depth": 1.2,
    "height": 0.75
  },
  "material": "oak_furniture"
}
```

---

## 3. Materials 材质定义

```json
{
  "materials": {
    "material_id": {
      "baseColor": [0.68, 0.65, 0.62],
      "roughness": 0.9,
      "metallic": 0.0,
      "albedo": 1.0,
      "opacity": 1.0,
      "lightingCondition": "D65_noon",
      "effects": [ /* 效果列表 */ ]
    }
  }
}
```

### 3.1 材质参数

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| baseColor | [R, G, B] | 0.0-1.0 | 基础颜色（RGB） |
| roughness | number | 0.0-1.0 | 粗糙度（0=光滑，1=粗糙） |
| metallic | number | 0.0-1.0 | 金属度 |
| albedo | number | 0.0-1.0 | 反照率 |
| opacity | number | 0.0-1.0 | 不透明度（可选） |
| lightingCondition | string | - | 光照条件："D65_noon" 等 |

### 3.2 材质效果

#### 颗粒感 (Grain)

```json
{
  "type": "grain",
  "intensity": 0.25,
  "scale": 0.04
}
```

#### 风化效果 (Weathering)

```json
{
  "type": "weathering",
  "dustColor": [0.45, 0.42, 0.38],
  "dustOpacity": 0.3,
  "crackIntensity": 0.1,
  "colorFade": 0.15
}
```

#### 苔藓效果 (Moss)

```json
{
  "type": "moss",
  "mossColor": [0.2, 0.4, 0.12],
  "coverage": 0.25,
  "pattern": "base_up"
}
```

**pattern类型**：
- `base_up`: 底部密集向上渐变
- `patchy`: 随机斑块

#### 边缘磨损 (Edge Wear)

```json
{
  "type": "edgeWear",
  "wearColor": [0.6, 0.55, 0.5],
  "intensity": 0.2
}
```

---

## 4. Behaviors 行为定义

```json
{
  "behaviors": {
    "physics": { /* 物理属性 */ },
    "scripts": [ /* 脚本列表 */ ]
  }
}
```

### 4.1 物理属性

```json
{
  "physics": {
    "mass": 0,
    "collisionShape": "mesh",
    "constraints": [
      {
        "type": "hinge",
        "target": "front_door",
        "axis": "y",
        "limit": [0, 90]
      }
    ]
  }
}
```

### 4.2 交互脚本

```json
{
  "scripts": [
    {
      "on_click": {
        "condition": "event.target == 'front_door'",
        "actions": [
          {"type": "toggle_hinge", "target": "front_door"},
          {"type": "play_sound", "sound": "wooden_door_open"}
        ]
      }
    }
  ]
}
```

---

## 5. 坐标系统总结

### 5.1 世界坐标系

- **X轴**：左(-) → 右(+)
- **Y轴**：下(-) → 上(+)
- **Z轴**：前(-) → 后(+)
- 单位：米

### 5.2 墙体局部坐标系

对于直线墙：
- **沿墙方向**：from → to
- **法线方向**：垂直于墙面
- **Y轴**：与世界Y轴相同

### 5.3 开口坐标转换

**关键公式**：

```javascript
// 已知：墙体world坐标和开口world坐标
// 求：开口的from[0]（沿墙距离）

// 1. 计算墙方向向量
wallDir = normalize(wall.to - wall.from)

// 2. 计算开口到墙起点的向量
toOpening = opening.worldPos - wall.from

// 3. 投影到墙方向，得到沿墙距离
alongWall = dot(toOpening, wallDir)

// 4. 开口from字段
opening.from = [alongWall, opening.worldY, 0]
```

**实例计算**：

```
墙体：wall_front
  from = [0, 0.5, 0]
  to = [6, 3.5, 0]
  方向 = [1, 0, 0]（X轴）
  长度 = 6米

开口世界坐标：[2.4, 0.5, 0]

计算沿墙距离：
  toOpening = [2.4, 0.5, 0] - [0, 0.5, 0] = [2.4, 0, 0]
  alongWall = dot([2.4, 0, 0], [1, 0, 0]) = 2.4

开口from字段：[2.4, 0.5, 0] ✓
```

---

## 6. 最佳实践

### 6.1 命名规范

- **ID命名**：使用下划线分隔的描述性名称
  - 墙体：`wall_front`, `wall_back`, `wall_left`, `wall_right`
  - 楼层：`wall_upper_front`, `ground_floor`, `upper_floor`
  - 开口：`front_door`, `window_front_left`

### 6.2 尺寸参考

**住宅常用尺寸**：

| 构件 | 典型尺寸 |
|------|---------|
| 墙高 | 2.8-3.5米（层高） |
| 墙厚 | 0.2-0.4米 |
| 门宽 | 0.9-1.2米 |
| 门高 | 2.0-2.4米 |
| 窗宽 | 1.0-1.8米 |
| 窗高 | 1.0-1.5米 |
| 窗台高 | 0.9-1.2米 |
| 地板厚 | 0.15-0.3米 |
| 屋顶坡度 | 高度=跨度×0.3-0.5 |

### 6.3 构件顺序

推荐按以下顺序定义构件：

1. 地板/基础
2. 一层墙体
3. 一层开口（门窗）
4. 一层楼板
5. 二层墙体
6. 二层开口
7. 梁
8. 屋顶
9. 楼梯
10. 柱子
11. 家具

### 6.4 常见错误

❌ **错误1：开口使用世界坐标（最严重！）**

这是最常见的错误，会导致**所有门窗模型悬浮脱离墙体、窗框/玻璃游离于墙体表面之外**。

```json
// 墙：沿X轴，长度16m
{"id": "wall_front", "from": [-8, 0, -6], "to": [8, 3, -6]}

// ❌ 错误！from[0]=-5 是 world X 坐标，不是沿墙距离
{"id": "window", "parentWall": "wall_front", "from": [-5, 1, -6]}
```

**渲染后果**：
- 墙体切孔（cutout）位置计算错误 → `localX = -5` 实际应在3m处 → 切孔在墙外
- 窗框世界坐标计算错误 → `worldX = -8 + (-5)*1 = -13` → 窗户被放到建筑外13米处
- 窗框和玻璃呈现为"悬浮在墙体表面之外"的错位效果

✓ **正确：使用沿墙距离**
```json
// from[0] = (-5) - (-8) = 3（沿墙距离），from[2] = 0（法向偏移）
{"id": "window", "parentWall": "wall_front", "from": [3, 1, 0]}
```

> **AI生成专用规则**：生成opening时，**严禁**直接将墙体世界坐标填入from字段。必须以from[0]=沿墙距离、from[2]=法向偏移(通常为0)的格式填写。

❌ **错误2：墙角坐标不对齐**
```json
{"id": "wall_front", "from": [-8, 0, -6], "to": [8, 3, -6]},
{"id": "wall_left", "from": [-8, 0, -5.7], "to": [-8, 3, 8]}
// Z坐标不匹配：-6 vs -5.7
```

✓ **正确：墙角对齐**
```json
{"id": "wall_front", "from": [-8, 0, -6], "to": [8, 3, -6]},
{"id": "wall_left", "from": [-8, 0, -6], "to": [-8, 3, 8]}
// Z坐标匹配：都是-6
```

❌ **错误3：Y坐标混用**
```json
// 墙体：from[1]=3, to[1]=5.8
{"type": "opening", "from": [2.4, 1.5, 0]}  
// 不清楚1.5是世界坐标还是相对墙底的偏移
```

✓ **正确：明确使用世界Y坐标**
```json
// 墙体：from[1]=3, to[1]=5.8
{"type": "opening", "from": [2.4, 4.0, 0]}
// 4.0是世界Y坐标（墙底3 + 偏移1 = 4）
```

---

## 7. 验证清单

生成蓝图后，检查以下项目：

- [ ] 所有`id`唯一
- [ ] 墙角坐标精确对齐
- [ ] **开口的`from[0]`是沿墙距离，不是世界坐标**（重中之重！）
- [ ] 开口的`from[1]`是世界Y坐标（在墙的Y范围内）
- [ ] 开口的`from[2]`是法向偏移（通常为0，不是世界Z坐标）
- [ ] 开口的`parentWall`存在且是墙类型
- [ ] 材质ID都已定义
- [ ] 楼层之间Y坐标连续
- [ ] 屋顶位置合理（在墙顶上方）

### 7.1 开口坐标自检方法

生成opening后，对每个opening执行以下快速验证：

```javascript
// 已知：wall 的 from/to 坐标
// 已知：opening 的 from[0]（沿墙距离）和 from[2]（法向偏移）

// 1. 计算墙长度
const wallLen = Math.sqrt((to[0]-from[0])**2 + (to[2]-from[2])**2);

// 2. 自检规则
if (opening.from[0] < 0 || opening.from[0] > wallLen) {
  console.error(`❌ 开口 ${opening.id}: from[0]=${opening.from[0]} 超出墙长度 ${wallLen}`);
  // 这通常是使用了世界坐标而非沿墙距离的症状！
}

// 3. 法向偏移检查
if (Math.abs(opening.from[2]) > wallThickness) {
  console.warn(`⚠️ 开口 ${opening.id}: from[2]=${opening.from[2]} 法向偏移异常大`);
  // from[2] 通常应为 0（开口在墙面上）
}
```

**快速判断法**：如果 opening 的 `from` 数组中有两个值与墙体 `from`/`to` 中的值相同（如都有 `-6`），则极可能误用了世界坐标。正确的 `from` 应该是：`[沿墙距离(0~墙长), Y_world, 0]`。

---

## 8. 示例参考

完整示例请参考：
- `cabin_v1.wild` - 正确格式的简单小屋
- `villa_correct.wild` - 正确格式的别墅

**构件库默认值**：
编辑器构件库使用的默认参数（可作为快速参考）：

```json
// 墙体 (4米长, 3米高)
{
  "type": "wall",
  "from": [0, 0, 0],
  "to": [4, 3, 0],
  "thickness": 0.24,
  "material": "default"
}

// 地板 (4米×4米矩形)
{
  "type": "floor",
  "from": [0, 0, 0],
  "to": [4, 0, 4],
  "thickness": 0.2,
  "material": "default"
}

// 柱子 (3米高)
{
  "type": "column",
  "base": [0, 0, 0],
  "height": 3,
  "bottomRadius": 0.2,
  "topRadius": 0.2,
  "material": "default"
}

// 屋顶 (双坡, 8米跨度)
{
  "type": "roof",
  "roofType": "gable",
  "span": 8,
  "depth": 6,
  "height": 3,
  "material": "default"
}
```

---

## 版本历史

- **v1.1** (2026-07-21) - 修复 bieshu.wild 开口坐标从世界坐标转为局部坐标；增强错误案例说明和自检方法
- **v1.0** (2026-07-21) - 初始版本，基于wild-core渲染引擎
- 规范作者：根据渲染引擎源码和测试案例整理

---

## 附录：快速参考

### 墙体开口坐标转换表

| 墙体方向 | 墙定义 | 开口世界坐标 | 开口from[0]计算 |
|---------|--------|------------|----------------|
| X轴正向 | from=[0,y,z], to=[6,y,z] | world_x=2.4 | 2.4 - 0 = 2.4 |
| X轴负向 | from=[6,y,z], to=[0,y,z] | world_x=2.4 | 反转后计算 |
| Z轴正向 | from=[x,y,0], to=[x,y,5] | world_z=2 | 2 - 0 = 2 |
| Z轴负向 | from=[x,y,5], to=[x,y,0] | world_z=2 | 反转后计算 |

**通用公式**：
```
沿墙距离 = |开口世界坐标 - 墙起点坐标| 在墙方向上的投影
```

---

**文档完成时间**: 2026-07-21  
**适用引擎版本**: wild-core v1.0  
**文档状态**: 可用于RAG向量库索引
