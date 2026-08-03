---
doc_type: component
doc_scope: generation
knowledge_layer: wild_schema
entity_type: door
entity_name: static_door_component
topic: schema
wild_version: "1.1"
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
keywords:
  - 门
  - door
  - geometry.components
  - parentWall
  - interaction
  - 平开门
  - 推拉门
  - 双开门
  - 门亮子
---

# 门组合构件（当前引擎支持）

`type: "door"` 必须写入 `geometry.components`，不能写入 `geometry.elements`。编译器将其展开为 1 个 `opening`（矩形洞口）+ 3 段 `primitive.box`（左/右/顶门框）。

---

## 参数契约

| 字段 | 必填 | 约束 |
|---|---|---|
| `type` | ✅ | 固定为 `"door"` |
| `id` | ✅ | 非空字符串，与所有 elements/components 唯一 |
| `parentWall` | ✅ | 已存在的 `wall` ID（直线墙或单段曲线墙） |
| `from` | ✅ | `[沿墙弧长距离(m), 底部世界Y, 法向偏移]` |
| `width` | ✅ | 正数，门宽建议 0.8~1.2m（双扇×2） |
| `height` | ✅ | 正数，门高建议 2.0~2.4m |
| `interaction` | ✅ | `{"mode":"swing","hingeSide":"left","openAngle":90}` |
| `frameWidth` | 可选 | 门框宽度，默认 0.08m |
| `frameDepth` | 可选 | 门框深度，默认墙厚+0.04m |
| `frameMaterial` | 可选 | 门框材质名 |
| `leafMaterial` | 可选 | 门扇覆盖面材质名（控制门的外观颜色） |

**`interaction` 子字段**：

| 字段 | 说明 |
|---|---|
| `mode` | `"swing"`（平开）或 `"slide"`（推拉） |
| `hingeSide` | `"left"` 或 `"right"`（仅 swing 模式） |
| `openAngle` | 最大开启角度（度），默认 90 |
| `openDistance` | 推拉位移（米），仅 slide 模式 |
| `initiallyOpen` | 初始是否开启，默认 false |

---

## 门型变体（全部用当前编译器可实现）

### 1. 基础平开门（单扇）

最常见的门。编译器展开为矩形 opening + 3 段门框。

```json
{
  "type": "door",
  "id": "door_entry",
  "parentWall": "wall_front",
  "from": [1.2, 0.0, 0],
  "width": 1.0,
  "height": 2.2,
  "frameMaterial": "wood",
  "leafMaterial": "door_wood",
  "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 }
}
```

### 2. 双开门（两个 door 组件并排，铰链各朝左右）

双开门 = **两个独立的 door 组件**。左侧门铰链在左，右侧门铰链在右。两扇门的总宽度 = 门洞宽度。

```json
[
  {
    "type": "door",
    "id": "door_double_left",
    "parentWall": "wall_front",
    "from": [2.4, 0.0, 0],
    "width": 0.9,
    "height": 2.2,
    "frameMaterial": "wood",
    "leafMaterial": "door_wood",
    "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 }
  },
  {
    "type": "door",
    "id": "door_double_right",
    "parentWall": "wall_front",
    "from": [3.3, 0.0, 0],
    "width": 0.9,
    "height": 2.2,
    "frameMaterial": "wood",
    "leafMaterial": "door_wood",
    "interaction": { "mode": "swing", "hingeSide": "right", "openAngle": 90 }
  }
]
```

> 注意：`door_double_right.from[0]` = `door_double_left.from[0]` + `door_double_left.width` = 2.4 + 0.9 = 3.3。两扇门之间不留缝时 `frameWidth` 设为 0。

### 3. 推拉门

`interaction.mode` 设为 `"slide"`。门扇沿墙方向滑动而不是旋转。

```json
{
  "type": "door",
  "id": "door_sliding",
  "parentWall": "wall_front",
  "from": [1.5, 0.0, 0],
  "width": 1.2,
  "height": 2.2,
  "frameMaterial": "metal",
  "leafMaterial": "glass",
  "interaction": { "mode": "slide", "hingeSide": "left", "openDistance": 1.0 }
}
```

### 4. 门 + 亮子（门上方的小窗）

门上方加亮子 = **door 组件 + window 组件**。门从墙底部开始，窗在门的上方。

```json
[
  {
    "type": "door",
    "id": "door_with_transom",
    "parentWall": "wall_front",
    "from": [2.0, 0.0, 0],
    "width": 1.0,
    "height": 2.2,
    "frameMaterial": "wood",
    "leafMaterial": "door_wood",
    "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 }
  },
  {
    "type": "window",
    "id": "transom_above_door",
    "parentWall": "wall_front",
    "from": [2.0, 2.2, 0],
    "width": 1.0,
    "height": 0.6,
    "verticalMullions": 0,
    "horizontalMullions": 0,
    "frameMaterial": "wood",
    "glassMaterial": "glass",
    "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 }
  }
]
```

> 注意：亮子窗的 `from[1]` = 门的 `from[1]` + 门的 `height` = 0 + 2.2 = 2.2。`openAngle: 0` 表示亮子不可开启（固定窗）。

### 5. 门 + 侧亮（门两侧窄窗）

门两侧加窄窗 = **window（左）+ door（中）+ window（右）**，三个组件并排。

```json
[
  {
    "type": "window",
    "id": "sidelight_left",
    "parentWall": "wall_front",
    "from": [1.4, 0.9, 0],
    "width": 0.5,
    "height": 1.3,
    "verticalMullions": 0,
    "horizontalMullions": 1,
    "frameMaterial": "wood",
    "glassMaterial": "glass",
    "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 }
  },
  {
    "type": "door",
    "id": "door_center",
    "parentWall": "wall_front",
    "from": [1.9, 0.0, 0],
    "width": 1.0,
    "height": 2.2,
    "frameMaterial": "wood",
    "leafMaterial": "door_wood",
    "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 }
  },
  {
    "type": "window",
    "id": "sidelight_right",
    "parentWall": "wall_front",
    "from": [2.9, 0.9, 0],
    "width": 0.5,
    "height": 1.3,
    "verticalMullions": 0,
    "horizontalMullions": 1,
    "frameMaterial": "wood",
    "glassMaterial": "glass",
    "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 0 }
  }
]
```

### 6. 材质变体

通过 `leafMaterial` 和 `frameMaterial` 控制门的外观：

| 效果 | leafMaterial | frameMaterial | 材质定义要点 |
|---|---|---|---|
| 木门 | `"door_wood"` | `"wood"` | baseColor 偏棕黄，roughness 0.7 |
| 白漆木门 | `"door_white"` | `"wood_white"` | baseColor [0.9, 0.9, 0.88]，roughness 0.5 |
| 玻璃门 | `"glass"` | `"metal"` | opacity 0.35，roughness 0.12 |
| 金属门 | `"door_metal"` | `"metal"` | metallic 0.9，roughness 0.3 |

> 注意：当前 `DoorComponent` 没有 `style` 字段。不要写 `"style": "glass"` 或 `"style": "panel"`——这些字段不存在，会被 Schema 校验拒绝。门的视觉效果通过 `leafMaterial` 对应的材质定义来控制。

---

## 当前引擎边界

| 能力 | 状态 | 说明 |
|---|---|---|
| 单扇平开门 | ✅ supported | 编译器直接支持 |
| 双扇平开门 | ✅ supported | 两个 door 组件并排，见上文示例 |
| 推拉门 | ✅ supported | `interaction.mode: "slide"` |
| 门+亮子 | ✅ supported | door + window 组件组合，见上文示例 |
| 门+侧亮 | ✅ supported | window + door + window，见上文示例 |
| 多材质门 | ✅ supported | 通过 `leafMaterial` 控制 |
| 拱形门 | ⚠️ 当前不可用 | compileDoor 硬编码 `style: "rectangular"`；如需拱形需手动写 `opening` 元素 + `primitive` 组合 |
| 多门扇（>2） | ⚠️ 有限支持 | 可放置 ≥3 个 door 组件，但中间扇的铰链位置需手动计算 |
| 门上雕花/面板 | ❌ proposed | 当前无 `mullion` 独立类型，门上装饰面板需用多个细 `primitive.box` 手动组合 |
| 门钉/浮雕 | ❌ proposed | `placement` 的网格贴附能力仍不完整 |
| 旋转门 | ❌ proposed | 需要旋转体几何 + 特殊交互逻辑 |
| 折叠门 | ❌ proposed | 需要多段门扇 + 折叠铰链逻辑 |
| 门楣装饰 | ⚠️ 有限支持 | 可用 `cornice` 组件放在门上方墙体外侧，但不自动关联门 |

---

## 常见错误

| 错误写法 | 正确写法 | 原因 |
|---|---|---|
| `"style": "glass"` | 不写 style，用 `"leafMaterial": "glass"` | DoorComponent 没有 style 字段 |
| `"leafCount": 2` | 写两个独立的 door 组件 | DoorComponent 没有 leafCount 字段 |
| `"parentOpening": "xxx"` | `"parentWall": "xxx"` | door 依附于 wall，不是 opening |
| `"hingeSide": "left"` 直接写在 door 上 | 写在 `interaction` 对象内 | hingeSide 是 interaction 的子字段 |
| `"type": "door"` 写在 `geometry.elements` 中 | 写在 `geometry.components` 中 | door 是组合构件，不是基础元素 |
| `"type": "mullion"` | 不存在此 type | mullion 通过 `window.verticalMullions` 实现 |
