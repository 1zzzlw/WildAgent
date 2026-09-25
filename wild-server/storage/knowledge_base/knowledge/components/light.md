---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: light
entity_name: light_component
topic: parameters
status: supported
authority: engine
primary_terms:
  - 灯具
  - light
  - 台灯
  - 壁灯
  - 灯泡
  - 照明
  - 发光
  - 可开关灯具
synonyms:
  - lamp
  - 光源
---

# 灯具（light）组件参数契约

> 来源：引擎 light 组件实现与 `BLUEPRINT-SPEC-MINIMAL.md` 的 light 定义核对。
> 用途：定义可发光、可开关灯具 `light` 组件的参数与约束。用户要求台灯、亮灯、发光或可开关灯具时使用本组件；旧版 `furniture.subtype: "lamp"` 只是静态家具占位，不产生真实光照。

## 基本定义

`light` 是 `geometry.components` 中的组合组件：

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
  "initiallyOn": false
}
```

## 必填与可选字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | ✓ | `"light"` |
| `id` | ✓ | 稳定唯一 ID |
| `position` | ✓ | 世界坐标 `[x, y, z]`；`table_lamp` 是底座支承面锚点，`bulb` 是灯泡中心 |
| `fixtureType` | ✗ | 外观业务类型：`bulb` 或 `table_lamp` |
| `lightType` | ✗ | 发光算法：`point` 或 `spot` |
| `color` | ✗ | RGB，3 个 0~1 数值 |
| `lowIntensity` / `highIntensity` | ✗ | 弱光/强光强度 |
| `distance` | ✗ | 光照距离 |
| `angle` | ✗ | 光束角（`spot` 时） |
| `initiallyOn` | ✗ | 初始状态：默认 `true`（亮灯）；`false` 表示默认关灯。省略按亮灯处理 |

## 约束

- **`fixtureType` 与 `lightType` 不混用**：`fixtureType` 是外观（bulb/table_lamp），`lightType` 是发光算法（point/spot），二者独立。
- **`table_lamp` 编译产物**：灯泡、底座、灯杆和灯罩；`bulb` 只编译灯泡与灯座。
- **交互**：右键在关灯、弱光和强光之间循环；运行时亮度级别不写回 Blueprint，`initiallyOn` 只保存初始状态。
- **`draggable: true`** 允许用户手动拖动并把位置写回当前草稿，不表示已实现自动贴桌面或空间碰撞校验。
- **壁灯挂墙**：壁灯（`fixtureType: bulb`）的 `position` 应落在墙上安装高度（如离地 1.8m 左右），不要悬浮在半空；竖条壁灯的灯体造型见"造型变体·壁灯"。

## 造型变体：吊灯、吸顶灯、落地灯与线性灯

`fixtureType` 只有 `bulb` / `table_lamp` 两个枚举值（schema 硬约束，写 `pendant` / `chandelier` 会直接校验失败）。
图中常见的吊灯、吸顶灯、落地灯等造型变体按下面的组合方式表达；**用户显式点名**某类灯具时才需要套用，
"温馨""明亮"这类氛围词不触发。共通原则：**一个 `light` 组件 = 一个真实光源**（挂在发光灯泡上），
灯体造型用 `primitive` 装饰件拼装；多头吊灯默认只给 1 个光源（性能友好），装饰泡用不发光的小球体。

### 吊灯（单头 / 多头 / 分子灯）

<!-- rag-meta
entity_type: light
entity_name: pendant_light
topic: composition
primary_terms:
  - 吊灯
  - 餐吊灯
  - 多头吊灯
  - 分子灯
synonyms: []
-->

吊灯 = `bulb` 光源（挂在灯罩内的悬挂高度）+ `primitive` 吊杆（细圆柱，从天花板到灯罩顶）+
灯罩（圆柱/圆台）。`bulb` 的 `position` 是**灯泡中心**，不是天花板锚点。以下为
`geometry.components`（light）与 `geometry.elements`（吊杆灯罩）的混合片段，不是完整 `.wild` 文件：

```json
[
  { "type": "light", "id": "pendant_1", "fixtureType": "bulb", "position": [5.0, 2.25, 2.0],
    "bulbRadius": 0.08, "lightType": "point", "color": [1.0, 0.82, 0.58] },
  { "type": "primitive", "shape": "cylinder", "id": "pendant_1_cord",
    "position": [5.0, 2.75, 2.0], "radius": 0.01, "height": 0.5 },
  { "type": "primitive", "shape": "cylinder", "id": "pendant_1_shade",
    "position": [5.0, 2.35, 2.0], "radiusTop": 0.06, "radiusBottom": 0.18, "height": 0.22 }
]
```

- 悬挂高度、灯罩尺寸、吊杆长度是**自由变量**；示例按 3.0m 天花板、灯罩顶 2.5m 取值。
- 多头吊灯 / 分子灯：若干 `primitive` 球体（装饰泡，不发光）+ 从灯泡中引出的支臂圆柱；
  真实光源 1~3 个即可，不要每颗泡都配 `light`。

### 吸顶灯

<!-- rag-meta
entity_type: light
entity_name: ceiling_light
topic: composition
primary_terms:
  - 吸顶灯
  - 圆盘灯
synonyms: []
-->

`bulb` 的编译产物天然是吸顶形态：底座圆盘在灯泡**上方**。把 `position[1]` 贴到天花板下
（灯泡中心 ≈ 天花板标高 - bulbRadius），调大 `bulbRadius` 即得圆盘吸顶灯，无需任何 primitive：

```json
{ "type": "light", "id": "ceiling_1", "fixtureType": "bulb", "position": [3.0, 2.86, 2.0],
  "bulbRadius": 0.14, "baseHeight": 0.06, "lightType": "point" }
```

### 落地灯

<!-- rag-meta
entity_type: light
entity_name: floor_lamp
topic: composition
primary_terms:
  - 落地灯
synonyms: []
-->

`table_lamp` 的形状（底座 + 灯杆 + 灯罩）对落地灯完全适用：把 `height` 拉到 1.5~1.7、
`position[1]` 落到地面即可，`shadeRadius` 按灯罩比例放大：

```json
{ "type": "light", "id": "floor_lamp_1", "fixtureType": "table_lamp", "position": [1.0, 0.0, 3.5],
  "height": 1.6, "shadeRadius": 0.24, "lightType": "point", "initiallyOn": false }
```

### 线性灯具（长条吊灯 / 灯带）

<!-- rag-meta
entity_type: light
entity_name: linear_light
topic: composition
primary_terms:
  - 线性灯
  - 长条吊灯
  - 灯带
synonyms: []
-->

没有线状光源类型。长条吊灯 = `primitive` 细长盒体作灯体 + 沿轴 1~2 个 `bulb` 光源 +
两端吊杆；LED 灯带（暗藏光槽）**没有对应表达**，只能用隐藏在槽内的低强度 `bulb` 近似或
明确告知不支持。灯体示例：

```json
{ "type": "primitive", "shape": "box", "id": "linear_1_body",
  "position": [5.0, 2.45, 2.0], "dimensions": [1.2, 0.08, 0.12] }
```

### 壁灯（竖条壁灯 / 壁装灯体）

<!-- rag-meta
entity_type: light
entity_name: wall_sconce
topic: composition
primary_terms:
  - 壁灯
  - 条形壁灯
  - 竖条壁灯
  - 壁装灯
synonyms: []
-->

引擎没有壁灯专用 fixtureType（枚举只有 `bulb` / `table_lamp`），bare `bulb` 挂墙只是
"悬浮灯泡 + 上方圆盘"，没有灯体造型。竖条壁灯（门/窗两侧的装饰壁灯）= `primitive` 竖条盒
做灯体（亮色材质）+ `bulb` 光源藏在灯体内。

🔴 **内外侧判断（校验器不查，最容易错）**：墙是沿 from→to 轴线居中的，两侧各厚 `thickness/2`，
**哪侧是室外没有统一的手性规则**（取决于墙的绕向）。唯一可靠判据：**灯体偏移方向必须背离
建筑几何中心**。做法：取墙中点 → 朝建筑中心向量取反 → 得室外法向 → 灯体中心 = 室外墙面
沿法向外推 0.03。挂反了灯会在室内，渲染外观直接丢灯，且所有校验器都不会报错。

以下是 `geometry.elements`（灯体）与 `geometry.components`（光源）的混合片段，
不是完整 `.wild` 文件（前墙 `from:[0,0,0]→to:[14,3,0]`、建筑在 +z 侧，室外墙面 z=-0.12）：

```json
[
  { "type": "primitive", "shape": "box", "id": "sconce_1_body",
    "position": [5.7, 1.95, -0.15], "dimensions": [0.12, 0.55, 0.06], "material": "sconce_white" },
  { "type": "light", "id": "sconce_1", "fixtureType": "bulb",
    "position": [5.7, 1.95, -0.15], "bulbRadius": 0.06, "lightType": "point",
    "color": [1.0, 0.85, 0.6], "lowIntensity": 10, "highIntensity": 35, "distance": 5,
    "initiallyOn": true }
]
```

### 檐下筒灯（屋檐板底一排小灯）

<!-- rag-meta
entity_type: light
entity_name: eave_downlight
topic: composition
primary_terms:
  - 檐下筒灯
  - 筒灯
  - 屋檐灯
synonyms: []
-->

效果图中屋檐板底的一排嵌入式筒灯没有专用类型：用小半径 `bulb`（`bulbRadius` 0.04~0.06）
贴在檐口板底（`position[1]` ≈ 屋檐底标高 - 0.05），沿檐口方向等距排布。🔴 引擎**没有昼夜
自动开关**：`initiallyOn: false` 就是常关，要"黄昏亮灯"的效果图感必须显式 `true`。
屋檐出挑位置由屋顶 `depth`/`span` 决定（出檐 ≈ (depth − 进深)/2）。

```json
{ "type": "light", "id": "eave_downlight_1", "fixtureType": "bulb",
  "position": [3.5, 5.88, -0.5], "bulbRadius": 0.05, "lightType": "point",
  "color": [1.0, 0.9, 0.7], "lowIntensity": 8, "highIntensity": 30, "distance": 4,
  "initiallyOn": false }
```

## 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| 台灯悬浮半空 | `position[1]` 过高且 `fixtureType: table_lamp` | 把底座 Y 落到支承面（桌面/地面） |
| 无光照的静态灯 | 用了 `furniture.subtype: "lamp"` | 改用 `light` 组件 |
| `initiallyOn` 缺失被误判 | 省略即亮灯 | 需要默认关灯时显式写 `false` |
| `position` 高度为负 | 灯具埋入地下 | 修正 `position[1]` ≥ 0 |
| 吊灯写成 `fixtureType: "pendant"` | 枚举只有 `bulb`/`table_lamp`，schema 直接拒绝 | 用 `bulb` 光源 + `primitive` 吊杆灯罩组合（见"造型变体"） |
| 每颗装饰泡都配一个 `light` | 光源数量膨胀，交互与性能浪费 | 1 个 `light` 光源 + 其余泡用不发光 `primitive` 球体 |
| 壁灯挂到室内侧 | 墙两侧各厚 thickness/2，哪侧朝外取决于墙绕向，**校验器不查内外侧** | 按"灯体偏移方向背离建筑几何中心"判断室外法向（见"造型变体·壁灯"） |
