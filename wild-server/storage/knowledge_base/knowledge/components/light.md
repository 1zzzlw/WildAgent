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
  - 壁灯
  - 吸顶灯
  - 筒灯
  - 灯泡
  - 照明
  - 发光
  - 可开关灯具
  - 灯体
  - 吊灯
synonyms:
  - lamp
  - 光源
  - 灯具安装
---

# 灯具（light）组件参数契约

> 来源：引擎 `light` 组件实现（`wild-core/src/compiler/components/light.ts`）与 `schema.json` 的 `$defs.lightComponent` 核对。
> 用途：定义可发光、可开关灯具 `light` 的参数与挂装方式。旧版 `furniture.subtype: "lamp"` 只是静态家具占位，不产生真实光照。

## 基本定义

`light` 是 `geometry.components` 中的组合组件。灯体由 `body` 逐段描述，光源行为挂在其中一段上：

```json
{
  "type": "light",
  "id": "ceiling_disc_1",
  "position": [3.0, 2.9, 2.0],
  "body": [
    {"shape": "cylinder", "position": [3.0, 2.96, 2.0], "radiusTop": 0.3, "radiusBottom": 0.3, "height": 0.06},
    {"shape": "cylinder", "position": [3.0, 2.92, 2.0], "radiusTop": 0.26, "radiusBottom": 0.26, "height": 0.03, "interactive": true}
  ],
  "lightType": "point",
  "color": [1.0, 0.87, 0.68],
  "lowIntensity": 12,
  "highIntensity": 40,
  "distance": 7,
  "initiallyOn": true
}
```

## 必填与可选字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | ✓ | `"light"` |
| `id` | ✓ | 稳定唯一 ID |
| `position` | ✓ | 世界坐标 `[x, y, z]`。**挂装参考点**：顶装贴顶棚下沿，壁装贴墙面外挑，落地落地面 |
| `body` | ✗ | 灯体几何分段（见下）。**新形态首选此字段** |
| `fixtureType` | ✗ | 预设灯体快捷写法：`bulb`（球泡+灯座）或 `table_lamp`（灯座+灯杆+灯罩）。`body` 存在时该字段不参与 |
| `lightType` | ✗ | 发光算法：`point` 或 `spot` |
| `color` | ✗ | RGB，3 个 0~1 数值 |
| `lowIntensity` / `highIntensity` | ✗ | 弱光 / 强光强度 |
| `distance` | ✗ | 光照距离 |
| `angle` | ✗ | 光束角（`spot` 时），≤ 90 |
| `initiallyOn` | ✗ | 初始状态。默认 `false`（关灯）；要默认点亮必须显式写 `true` |

## 灯体：body 分段

`body` 是 `primitive` 原语的数组，**每段只能写几何字段，不写 `type` / `id`**（编译期生成）。
`shape` 取 `box` / `sphere` / `cylinder` / `profile_sweep` 四种之一，并满足该形状的参数配对：

| shape | 必带参数 | 用途 |
|---|---|---|
| `box` | `dimensions` | 矩形面板、壁灯、灯带槽 |
| `sphere` | `radius` | 球泡、装饰光球 |
| `cylinder` | `height` + （`radius` 或 `radiusTop`+`radiusBottom`） | 圆盘吸顶灯、吊杆、灯座 |
| `profile_sweep` | `path` + `profile` | 环形灯、曲线灯带 |

约束：

- **`interactive` 标记唯一命中体**。右键点灯需要明确的点击目标：标了 `interactive: true` 的那段挂上光源与开关交互；省略时默认**最后一段**。灯体通常是"外壳 + 发光面"两段，发光面写 `interactive: true`。
- **`profile_sweep` 的 `position` 必须为 `[0,0,0]`**。它的顶点已经把 `path` 的绝对坐标算进去了，写非零位置会整体平移一次。
- **`profile_sweep` 是开放路径扫掠**，不把末点连回首点。要闭合环形，沿圆弧布一圈点、**不要重复首点**（重复会被判 `path must not overlap`）。
- `body` 段的 `material` 省略时回落到组件级 `material`。

## 挂装方式：按安装面选 position

顶装、壁装、吊装由**安装面**决定，不是由"灯的种类"决定。同一种灯具安装面不同，`position` 落点就不同。

| 安装面 | `position[1]` 落点 | 灯体表达 | `lightType` |
|---|---|---|---|
| **顶装**（吸顶灯、嵌入灯、环形灯） | 顶棚下沿 ≈ 顶棚标高 − 灯体半厚 | 薄 `cylinder` / `box` 作盘体，发光面朝下 | `point` |
| **壁装**（壁灯、洗墙灯、画框灯） | 离地 1.5~2.0m（入口门两侧常取 1.8m） | `box` 贴墙面，凸出量 0.06~0.25m | 面板朝下用 `point`，定向洗墙用 `spot` |
| **吊装**（吊灯、线型吊灯） | 低于顶棚，由杆件长度决定 | 杆（细 `cylinder`）+ 灯罩，`body` 内表达连接 | `point` |
| **落地 / 台面** | 地面或桌面标高 | 用 `fixtureType: table_lamp` 预设，或 `body` 自绘底座 | `point` |

**顶装示例**（薄盘贴顶，发光面朝下）：

```json
{"type": "light", "id": "ceiling_1", "position": [3.0, 2.9, 2.0],
 "body": [
   {"shape": "cylinder", "position": [3.0, 2.96, 2.0], "radiusTop": 0.3, "radiusBottom": 0.3, "height": 0.06},
   {"shape": "cylinder", "position": [3.0, 2.92, 2.0], "radiusTop": 0.26, "radiusBottom": 0.26, "height": 0.03, "interactive": true}],
 "lightType": "point", "initiallyOn": true}
```

**壁装示例**（矩形面板贴墙，`spot` 定向洗墙）：

```json
{"type": "light", "id": "sconce_1", "position": [0.28, 1.8, 4.0],
 "body": [
   {"shape": "box", "position": [0.15, 1.8, 4.0], "dimensions": [0.06, 0.3, 0.16]},
   {"shape": "box", "position": [0.24, 1.8, 4.0], "dimensions": [0.08, 0.22, 0.6], "interactive": true}],
 "lightType": "spot", "angle": 60, "initiallyOn": true}
```

**顶装环形示例**（`profile_sweep` 表达环体）：

```json
{"type": "light", "id": "ring_1", "position": [4.5, 2.8, 2.0],
 "body": [
   {"shape": "profile_sweep",
    "path": [[4.8, 2.8, 2.0], [4.7, 2.8, 2.4], [4.5, 2.8, 2.5], [4.3, 2.8, 2.4], [4.2, 2.8, 2.0]],
    "profile": [[0.06, 0.0], [0.0, 0.06], [-0.06, 0.0], [0.0, -0.06]],
    "closedProfile": true, "interactive": true}],
 "lightType": "point", "initiallyOn": true}
```

壁装面板贴哪面墙：墙是沿 `from`→`to` 轴线居中的，两侧各厚 `thickness/2`，**哪侧是室外没有统一手性规则**（取决于墙的绕向）。唯一可靠判据：**灯体凸出方向必须背离建筑几何中心**——取墙中点，朝建筑中心的反向即室外法向。挂反了灯会装进室内，**所有校验器都不会报错**。

## 约束

- **`fixtureType` 与 `lightType` 不混用**：前者是预设灯体，后者是发光算法，二者独立。
- **`body` 与 `fixtureType` 二选一**：`body` 存在时 `fixtureType` 的几何不参与（不会报错，只是不生效）。新形态一律写 `body`，不要去找不存在的 `fixtureType` 枚举值。
- **一个 `light` = 一个真实光源**。多头吊灯、分子灯只给 1~3 个 `light`，其余装饰泡用 `body` 里不发光的 `sphere` 段表达。
- **交互**：右键在关灯 → 弱光 → 强光之间循环；运行时亮度级别不写回 Blueprint，`initiallyOn` 只保存初始状态。
- **没有昼夜自动开关**：`initiallyOn: false` 就是常关。要"黄昏亮灯"的效果必须显式 `true`。
- **发光材质**：灯体发光段用 `materials` 里带 `emissive` 的材质（如 `emissive: [1.0, 0.87, 0.68]`），否则只有光源照不到灯体自身。
- **`draggable: true`** 允许手动拖动并写回当前草稿，不表示已实现自动贴面或碰撞校验。

## 造型变体

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

用 `body` 表达杆件 + 灯罩，光源挂在灯罩内那段。杆件高度 = 顶棚标高 − 灯罩顶标高：

```json
{"type": "light", "id": "pendant_1", "position": [5.0, 2.3, 2.0],
 "body": [
   {"shape": "cylinder", "position": [5.0, 2.85, 2.0], "radius": 0.01, "height": 0.3},
   {"shape": "cylinder", "position": [5.0, 2.6, 2.0], "radiusTop": 0.06, "radiusBottom": 0.18, "height": 0.22},
   {"shape": "sphere", "position": [5.0, 2.62, 2.0], "radius": 0.05, "interactive": true}],
 "lightType": "point", "initiallyOn": true}
```

悬挂高度、灯罩尺寸、吊杆长度是**自由变量**。

### 落地灯 / 台灯

<!-- rag-meta
entity_type: light
entity_name: floor_lamp
topic: composition
primary_terms:
  - 落地灯
  - 台灯
  - 灯
synonyms:
  - floor lamp
-->

这两个 `fixtureType` 预设没坏，直接用：`table_lamp` 编译出灯座 + 灯杆 + 灯罩。落地灯把
`height` 拉到 1.5~1.7、`position[1]` 落到地面；台灯把 `position[1]` 落到桌面标高：

```json
{"type": "light", "id": "floor_lamp_1", "fixtureType": "table_lamp", "position": [1.0, 0.0, 3.5],
 "height": 1.6, "shadeRadius": 0.24, "lightType": "point", "initiallyOn": false}
```

### 线性灯与灯带

<!-- rag-meta
entity_type: light
entity_name: linear_light
topic: composition
primary_terms:
  - 线性灯
  - 长条吊灯
  - 灯带
  - 灯槽
synonyms: []
-->

`box` 作长条灯体（`dimensions` 拉长），`interactive` 段与 `position` 同心。
暗藏灯槽的效果靠 `materials` 里低强度 `emissive` 材质表达，不是靠 `light` 的 `distance`：

```json
{"type": "light", "id": "linear_1", "position": [5.0, 2.45, 2.0],
 "body": [
   {"shape": "box", "position": [5.0, 2.45, 2.0], "dimensions": [1.2, 0.08, 0.12]},
   {"shape": "box", "position": [5.0, 2.42, 2.0], "dimensions": [1.1, 0.02, 0.08], "interactive": true}],
 "lightType": "point", "initiallyOn": false}
```

### 筒灯（檐下或吊顶一排小灯）

<!-- rag-meta
entity_type: light
entity_name: downlight
topic: composition
primary_terms:
  - 筒灯
  - 檐下筒灯
  - 射灯
synonyms: []
-->

小半径 `cylinder`（`radius` 0.04~0.08、`height` 0.05~0.1）贴在安装面下沿，
沿面等距排布；`body` 只有一段时它就是 `interactive` 段：

```json
{"type": "light", "id": "downlight_1", "position": [3.5, 2.9, 2.0],
 "body": [
   {"shape": "cylinder", "position": [3.5, 2.95, 2.0], "radius": 0.06, "height": 0.08, "interactive": true}],
 "lightType": "spot", "angle": 45, "initiallyOn": true}
```

## 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| 写了 `fixtureType: "pendant"` / `"ceiling"` / `"wall"` | 枚举只有 `bulb` / `table_lamp`，schema 直接拒绝 | 用 `body` 写灯体，不要新造 `fixtureType` 值 |
| 灯体拼好了却点不亮 | 拼的是 `geometry.elements` 的 `primitive`，`light` 组件没被使用 | 灯体必须写在 `light` 的 `body` 里，元素级 `primitive` 不带光源与交互 |
| `profile_sweep` 的灯整体偏移 | 段内写了非零 `position` | `profile_sweep` 段的 `position` 必须是 `[0,0,0]` |
| 环形灯报 `path must not overlap` | 末尾重复了首点想闭合 | 开放路径扫掠，沿弧布点且不重复首点 |
| 点一下跳了两档亮度 | 多个段都标了 `interactive: true` | 只保留一段标 `interactive` |
| 吸顶灯悬在顶棚下方一段距离 | 忘了灯体本身有厚度 | `position` 落到"顶棚标高 − 灯体半厚"，灯体贴顶 |
| 壁灯装进室内 | 墙两侧各厚 `thickness/2`，哪侧朝外取决于墙绕向，**校验器不查内外侧** | 按"凸出方向背离建筑几何中心"判断室外侧 |
| 台灯悬浮半空 | `position[1]` 过高 | 落到支承面（桌面 / 地面） |
| 要默认关灯却一直亮 | 省略 `initiallyOn` 时按 `false` 处理；要亮必须显式 `true` | 需要常亮的效果图显式写 `"initiallyOn": true` |
| 每颗装饰泡都配一个 `light` | 光源数量膨胀，交互与性能浪费 | 1 个 `light` + 其余泡用不发光的 `sphere` 段 |