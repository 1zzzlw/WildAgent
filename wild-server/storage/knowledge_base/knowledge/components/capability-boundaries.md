---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: constraint
entity_type: component
entity_name: engine_capability_boundaries
topic: constraints
wild_version: "1.1"
status: supported
authority: engine
primary_terms:
  - 引擎能力边界
  - engine capability
  - stable
  - partial
  - experimental
  - 不支持的类型
  - 降级方案
  - 组合构件
synonyms: []
---

# 引擎能力边界

> 定义当前引擎**能做什么**、**不能做什么**  
> 来源：`schema.json`、`types.ts`、`registry.ts`、`resolver.ts`

本文档帮助 Agent 理解：

- 哪些构件类型可以使用
- 哪些字段已实现、哪些还未实现
- 遇到不支持的需求如何降级或告知用户

---

## 1. geometry.elements 支持的类型

### 1.1 稳定支持 (stable)

| 类型 | 能力摘要 | 关键字段 |
|------|---------|---------|
| `wall` | 直线或曲线墙体，支持开口 | `from`, `to`, `thickness`, `curve` |
| `floor` | 矩形或圆形楼板 | `from`, `to`, `thickness`, `shape`, `radius`；**无开洞字段**——楼梯井/天井用多块矩形 floor 拼出（见《运行时校验规则》§4.4） |
| `stair` | 直跑楼梯，自动计算踏步 | `from`, `to`, `width`, `stepCount`；两端端点须落在标高匹配的楼板上，上方楼板须留井 |
| `primitive` | 通用几何体 | `shape`, `position`, `dimensions` 等 |

### 1.2 部分支持 (partial)

| 类型 | 能力摘要 | 限制 |
|------|---------|------|
| `column` | 圆形参数化柱 | 柱式细部仍在补齐；**无方柱** |
| `beam` | 矩形/圆形/工字截面 | 支持 `rect`, `circular`, `i-beam` |
| `roof` | 多种屋顶类型 | 支持 `gable`, `hip`, `dome`, `flat`, `chinese_curved`, `chinese_pagoda` |
| `opening` | 墙体洞口 | 必须引用 `parentWall` |
| `furniture` | 参数化家具（**无宿主**，可单独成一个场景） | 支持 `table`, `chair`, `sofa`, `bookshelf`, `bed`, `wardrobe`, `nightstand`, `tv_cabinet`, `lamp`, `tile`（均为引擎原生 subtype，`position` 为底面中心锚点）；`rotation` 可任意朝向，绕底面中心旋转，写**弧度三维数组** `[0, 弧度, 0]`（写成度数标量 `180` 或度数数组 `[0,90,0]` 时引擎按度数自动换算，不丢件）；所有子类型**正面统一朝 +Z**；`couch` 由服务端归一器收敛为 `sofa`（详见《家具参数契约》与《沙发表达》） |
| `body` | 简化人物 | 用于化身，建筑中不常用 |

### 1.3 实验性支持 (experimental)

| 类型 | 能力摘要 | 限制 |
|------|---------|------|
| `dense_brick` | 体素细节 | 等级为 experimental：当前版本尚未实现体素解压与等值面提取，使用时返回明确诊断，不再静默输出空网格 |

### 1.4 不支持的类型

以下类型**不存在于 WILD v1.1**：

- ❌ `truss`（桁架）→ 用多个 `beam` 或 `primitive` 组合
- ❌ `door`（作为 element）→ 应使用 `geometry.components` 中的 `door`
- ❌ `window`（作为 element）→ 应使用 `geometry.components` 中的 `window`

---

## 2. geometry.components 支持的类型

组合构件在编译时展开为基础元素。

### 2.1 支持的组合构件

| 类型 | 必填字段 | 编译结果 |
|------|---------|---------|
| `door` | `parentWall`, `from`, `width`, `height` | `opening` + 门框 primitive |
| `window` | `parentWall`, `from`, `width`, `height` | `opening` + 窗框 primitive + 玻璃 |
| `railing` | `path`, `height` | 立柱 + 横杆 (primitive + beam)；**原生栏板**——`infillType: glass/panel` 沿 `path` 逐段生成等厚板（见 3.7） |
| `canopy` | `parentWall`, `from`, `width`, `depth` | 雨棚板 + 支柱 |
| `balcony` | `parentWall`, `from`, `width`, `depth` | 悬挑板 + U 形栏杆 |
| `ramp` | `from`, `to`, `width` | 坡面 + 可选栏杆 |
| `bay_window` | `parentWall`, `from`, `width`, `height`, `projectionDepth` | 凸窗洞 + 窗体 |
| `cornice` | `path`, `profile` | 檐口扫掠 (profile_sweep)；**分层腰线/层间线脚**也用它——不指定 `parentRoof`、按世界坐标沿墙拉通的独立线脚（矩形/台阶形 closedProfile） |
| `chimney` | `position`, `width`, `depth`, `height` | 四面薄壁烟囱 |
| `light` | `position`, `fixtureType`, `lightType` | 灯具网格 + 光源；`fixtureType` 仅 `bulb`/`table_lamp`，吊灯/吸顶/落地/线性/竖条壁灯/檐下筒灯造型走 light+primitive 组合（见《灯具》） |
| `elevator` | `position`, `dimensions`, `floorHeight`, `floorCount` | 可动轿厢 + 导轨 + 呼梯按钮；**右键**点击轿厢或按钮升到下一楼层（顶层循环回底层，仅编辑器视口响应）；井道围合用 `wall_core_*` 墙表达（单井 2.4×2.6m、双联 4.6×2.6m 外廓）、楼板留井，轿厢坐标由骨架井格确定性对齐（见《电梯》） |

---

## 3. 具体能力边界

### 3.1 柱 (column)

<!-- rag-meta
entity_type: structural_component
-->

**能做**：

- ✅ 圆形柱，参数化高度和收分
- ✅ 多种柱式：`doric`, `ionic`, `corinthian`, `modern`, `chinese_wooden`
- ✅ 卷杀 (`entasis`) 和侧脚 (`inclination`)

**不能做**：

- ❌ 方柱（Schema 无 `crossSection` 字段）
- ❌ 复杂柱头雕刻（需要用 `dense_brick` 或 `primitive` 近似）

**降级方案**：

```python
# 如果需要方柱
def create_square_column(position, width, height):
    return {
        "type": "primitive",
        "shape": "box",
        "position": position,
        "dimensions": [width, height, width]
    }
```

### 3.2 梁 (beam)

<!-- rag-meta
entity_type: structural_component
-->

**能做**：

- ✅ 三种截面：`rect`, `circular`, `i-beam`
- ✅ 直线或曲线路径

**不能做**：

- ❌ 桁架 (`truss` 类型不存在)
- ❌ 变截面梁（截面沿路径变化）

**降级方案**：

```python
# 如果需要桁架
def create_truss(positions):
    elements = []
    # 手工组合多个 beam
    for i in range(len(positions) - 1):
        elements.append({
            "type": "beam",
            "from": positions[i],
            "to": positions[i+1],
            "crossSection": "rect",
            "width": 0.08,
            "height": 0.08
        })
    return elements
```

### 3.3 门 (door)

<!-- rag-meta
entity_type: door
-->

**能做**：

- ✅ 矩形门洞 + 门框
- ✅ 交互：`swing` (平开) / `slide` (水平推拉) / `lift` (向上抬起，卷帘·卷闸·上翻门)
- ✅ 开启方向和初始状态
- ✅ 门扇横向分节：`leafRows`（1~8），车库门帘片用 4~6，与 `doorStyle` 正交

**不能做**：

- ❌ 四开门等多门扇（双开门已由 `doorStyle: "double"` 支持：单洞口 + 四段框，无中框）
- ❌ 独立的厚门扇几何
- ❌ 碰撞检测（门开关时不检测阻挡）
- ❌ 真非矩形门洞（墙体开洞只有矩形；`openingStyle: "arched"` 是覆盖棱柱近似，见下）

**降级方案**：

双开门直接使用 `doorStyle: "double"`（单洞口 + 四段框，无中框），无需拆分。
以下拆分只用于四开门等多门扇需求：

```python
# 四开门：按需拆成多个门洞（每洞一个 door，doorStyle 可为 double）
def create_double_door(parent_wall, position, total_width, height):
    left_door = {
        "type": "door",
        "parentWall": parent_wall,
        "from": [position[0], position[1], 0],
        "width": total_width / 2,
        "height": height,
        "interaction": {
            "mode": "swing",
            "hingeSide": "left"
        }
    }
    right_door = {
        "type": "door",
        "parentWall": parent_wall,
        "from": [position[0] + total_width / 2, position[1], 0],
        "width": total_width / 2,
        "height": height,
        "interaction": {
            "mode": "swing",
            "hingeSide": "right"
        }
    }
    return [left_door, right_door]
```

#### 组合关系与禁止字段

- 门上亮子使用独立 `window`，两者引用同一父墙并保持竖向范围不重叠。
- 门侧亮同样使用独立 `window`；**不能把窗挂在门生成的临时 `opening` 上**。
- 拱形门洞由 `openingStyle: "arched"` 表达，但**只是近似**：墙洞仍是矩形（引擎只切矩形通孔），
  门扇仍是矩形，拱形只体现在门扇上方的覆盖棱柱带上——正视有拱形轮廓，侧视/斜视能看到
  矩形洞壁。需要向用户声明这一差异；用户不接受时退回 `rectangular`（默认）。
- 车库门/卷帘门/上翻门用 `interaction.mode: "lift"`（整扇沿世界竖直方向向上让开洞口），
  配 `leafRows`（4~6）做出横向帘片分节，即可读作卷帘门。`openDistance` 可省略，缺省等于洞口高度。
  **不要**给车库门配 `swing`（侧开语义错位）；`slide` 只在"横向平移的推拉门"场景用。
- ⚠️ **`lift` 的抬起量由引擎钳到门头净空**：拾起量 = `min(openDistance ?? 洞口高度, 墙顶 − 洞口顶)`。
  引擎不剪裁门扇，所以**不要**按洞口高度硬抬（会顶出墙外）；钳位后门扇多出来的部分正好落在
  「洞口上方那块实心墙」的高度带里被墙遮住，视觉上是**一樘从下往上收的半开卷帘门**——
  洞口下半透空、上半盖着门帘，立面不会多出板子。**因此 `openDistance` 通常省略即可**，不需要为了
  "别超模"去写保守值；只有当用户明确要"只开一条缝"时才显式给一个**更小**的值。
  门头净空不足（例如 3.6m 墙 + 2.5m 门，净空 1.1m）时门只会升起 1.1m，这是正确的半开观感，不是缺陷。
  门头净空为 0（洞口顶与墙顶齐平）时门不动、看起来仍关着——这种立面不要用车库门，改用 `swing`。
- ⚠️ **`lift` 依赖门扇写在墙中线上**（`from[2]` 即法向偏移取 0，默认值就是 0）：
  靠"墙厚 > 叶板厚"把升起的那半截吃掉。**不要给门写非零法向偏移**，否则门扇会露在立面上。
- ⚠️ **`leafRows` 的分节"存在但很淡"，可见性随门在画面里的大小变化**：面板凸起深度被门扇厚度上限
  约束（总厚 ≤ 80mm，单侧 ≤ ~20mm，固定 8mm），实测分节线对比度只有 5~13/255 灰阶。
  **近景/正对细节图**里读得出横向分格线（`rows=8` 可数出 7 处），**整栋远景构图**里门只占几十像素、
  会落进材质噪声本底，看起来接近一整块平板 —— 两种观感都是正常的，**不要声称"一眼就是卷帘门"**。
  需要更强的卷帘门识别度时，**首选叠加深色/金属感的 `leafMaterial`**（如低 albedo + metallic），
  而不是指望加深分节；也不要去放宽 `check-component-compiler.mjs` 的门扇厚度门禁换取更深的缝
  （那条 40~80mm 是门窗比例的真实约束，放宽会连累所有门）。

```json
{
  "type": "door",
  "id": "door_garage",
  "parentWall": "wall_garage_front",
  "from": [1.2, 0.0, 0.0],
  "width": 3.0,
  "height": 2.4,
  "leafRows": 5,
  "leafMaterial": "garage_slats",
  "interaction": { "mode": "lift" }
}
```

- 自动感应、卷帘**驱动机构**、防火、气密等专业性能**没有对应字段**；只能表达外观与已有开合交互，
  不能声称实现这些性能（例如不能声称"带电机/自动感应"）。
- 旋转门、折叠门和复杂雕花没有原生门型；只有用户接受几何近似时才使用显式 `primitive`。
- **禁止字段**：不使用 `style`、`leafCount` 或 `parentOpening`；
  `hingeSide`、`openAngle`、`openDistance` 只能放在 `interaction` 中；
  不把 `door` 写入 `geometry.elements`，也不创建不存在的 `mullion` 类型。

### 3.4 窗 (window)

<!-- rag-meta
entity_type: window
-->

**能做**：

- ✅ 矩形窗洞 + 窗框 + 玻璃
- ✅ 窗棂：`verticalMullions`, `horizontalMullions`
- ✅ 框深度、玻璃深度

**不能做**：

- ❌ 圆形窗、尖拱窗（`window` 组件无 `openingStyle` 字段；拱形/圆形轮廓可用 `opening` 元素的
  `style: "arched"/"gothic"/"circular"` 覆盖棱柱近似，见《窗样式变体》）
- ❌ 真非矩形墙洞（引擎 `box-with-holes.ts` 只切**矩形**通孔；非矩形 style 只是洞内的
  覆盖棱柱造型，斜视角可见矩形洞内壁转角——需向用户声明）
- ❌ 复杂斜格、花纹窗棂
- ❌ 开启窗扇（当前窗是静态的）

**降级方案**：

```python
# 如果需要圆形窗
def create_circular_window(parent_wall, center, radius):
    return [
        {
            "type": "opening",
            "id": generate_id("opening"),
            "parentWall": parent_wall,
            "from": [center[0] - radius, center[1] - radius, 0],
            "width": radius * 2,
            "height": radius * 2,
            "style": "circular",  # 覆盖棱柱支持 rectangular/arched/gothic/circular
            "material": "glass"   # 棱柱自身填充洞口，不要再叠加玻璃盒（会双层）
        }
    ]
```

### 3.5 屋顶 (roof)

<!-- rag-meta
entity_type: roof
-->

**能做**：

- ✅ 6 种类型：`gable`, `hip`, `dome`, `flat`, `chinese_curved`, `chinese_pagoda`
- ✅ 中式屋顶：飞檐 (`eaveCurveHeight`)、重檐 (`tiers`)
- ✅ **多体量分段屋顶**：L 形 / U 形 / 退台的建筑，为**每个体量各写一个 `roof` 元素**，
  `span`/`depth` 只取该体量自己的轮廓（外露一侧留 0~2m 出檐），不得用整栋外包络。

**不能做**：

- ❌ 用一个 `roof` 元素盖住复杂组合屋顶 —— 引擎没有"组合屋顶"这种类型：单个 `roof` 只有
  一种 `roofType` 和一组坡面，**盖不住** L 形 / U 形 / 错落体量，多写一个也没用。
- ❌ 自动生成瓦片（需用 `placements` 批量生成）

**降级方案**：多体量按体量拆成多个 `roof` 元素，每个体量一块。

```jsonc
// L 形：主楼 X[0,10] Z[0,8] + 侧翼 X[10,16] Z[4,8]，两块的 position[1] 都等于各自墙顶标高。
// 出檐只朝外；公共墙（X=10）一侧不出檐，避免一块屋顶伸到另一块体量上空。
{ "type": "roof", "id": "roof_main", "roofType": "gable",
  "span": 10.0, "depth": 8.8, "height": 2.2, "thickness": 0.24,
  "material": "roof_tile", "position": [5.0, 6.25, 4.0] },

{ "type": "roof", "id": "roof_wing", "roofType": "gable",
  "span": 6.0, "depth": 4.8, "height": 2.2, "thickness": 0.24,
  "material": "roof_tile", "position": [13.0, 6.25, 6.0] }
```

🔴 **体量怎么数**：把顶层墙段按端点串成环，一个环 = 一个体量（L 形 = 2 个矩形 = 2 块屋顶）。
漏掉任何一块体量的屋顶都过不了校验：流水线 `validate_roof_top_coverage`（7e 步）会把
"墙顶正上方没有任何构件"的墙逐面列出来。

### 3.6 楼梯 (stair)

**能做**：

- ✅ 直跑楼梯
- ✅ 自动计算踏步数（符合人体工学）

**不能做**：

- ❌ 旋转楼梯
- ❌ L 形、U 形楼梯
- ❌ 自动生成栏杆（需单独加 `railing`）

**降级方案**：

```python
# 如果需要 L 形楼梯
def create_l_shaped_stair(start, turn, end, width):
    return [
        {
            "type": "stair",
            "from": start,
            "to": turn,
            "width": width
        },
        {
            "type": "floor",  # 平台
            "from": turn,
            "to": [turn[0] + width, turn[1], turn[2] + width],
            "thickness": 0.15
        },
        {
            "type": "stair",
            "from": turn,
            "to": end,
            "width": width
        }
    ]
```

---

### 3.7 栏杆 (railing)

<!-- rag-meta
entity_type: railing
-->

`railing` 必须写入 `geometry.components`。它根据显式路径生成等距圆柱立杆，并在每段路径上按高度比例生成圆形横杆；路径可以随楼梯高度变化。默认路径为世界坐标，指定 `parentFloor` 后改用父楼板局部坐标。

#### 参数契约

| 字段 | 要求 |
|---|---|
| `type` | 固定为 `railing` |
| `id` | 非空且与全部元素、组件 ID 唯一 |
| `path` | 至少两个不重合的世界坐标点 |
| `height` | 正数，表示立杆高度 |
| `postSpacing` | 可选正数，默认 1.2m |
| `postRadius` | 可选正数，默认 0.035m |
| `railRadius` | 可选正数，默认 0.045m |
| `railLevels` | 可选，1–8 个不重复比例，每个值位于 `(0, 1]` |
| `material` | 可选，必须引用已有材质 |
| `parentFloor` | 可选；指定后 `path` 相对矩形楼板左下角顶面或圆形楼板中心顶面 |
| `infillType` | 可选，`glass` 或 `panel`；**不填则无栏板**（只有立杆 + 横杆） |
| `infillThickness` | 可选正数；默认 `glass` 0.02m、`panel` 0.05m |
| `infillTopRatio` | 可选，`(0, 1]`，默认 0.92；栏板高 = `height × infillTopRatio` |
| `infillMaterial` | 可选，必须引用已有材质；不填则继承 `material` |

#### 有效 JSON 片段

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "railing",
  "id": "terrace_railing",
  "path": [[0, 3, 0], [4, 3, 0]],
  "height": 1.1,
  "postSpacing": 0.8,
  "postRadius": 0.035,
  "railRadius": 0.045,
  "railLevels": [0.5, 1],
  "material": "metal",
  "infillType": "glass",
  "infillMaterial": "glass"
}
```

上例生成玻璃栏板：沿每段 `path` 拉一块厚 0.02m、高 `1.1 × 0.92 = 1.012m` 的玻璃板，
位于立杆之间；立杆与横杆仍按 `metal` 生成。

#### 当前边界

- 单个栏杆最多生成 2000 根立杆，横杆最多 8 层。
- 栏板按**每段路径**生成一块矩形板（直线段），多边形/弧形路径按折线逐段近似，转角处无斜接。
- 栏板是等厚平板，无边框、无分格、无纹理朝向控制；异形栏板改用 `primitive` 拼装。
- 重复路径点、重复横杆比例、非正尺寸会导致组件编译失败。
- 当前只表达静态几何，不代表满足栏杆高度、杆件净距或结构安全规范。
- 自动栏杆、曲面扶手、任意截面扫掠和交互行为仍未实现。

---

## 4. 材质能力边界

### 4.1 基础材质

**能做**：

- ✅ PBR 参数：`baseColor`, `roughness`, `metallic`, `albedo`
- ✅ 自发光：`emissive`
- ✅ 透明度：`opacity`

**不能做**：

- ❌ 程序化纹理（v1.0 只支持数值颜色）
- ❌ 法线贴图（v1.1 支持嵌入式图像，但增加文件体积）

### 4.2 效果层

**能做**：

- ✅ 风化：`weathering`（蒙尘、裂纹、褪色）
- ✅ 苔藓：`moss`（覆盖率、分布模式）
- ✅ 边缘磨损：`edgeWear`
- ✅ 木纹：`grain`（v1.1）

**不能做**：

- ❌ 自定义效果层（只能用已定义的类型）

---

## 5. 交互能力边界

### 5.1 支持的交互

**门**：

- ✅ 右键开合
- ✅ 平开 (`swing`) / 推拉 (`slide`) / 向上抬起 (`lift`，卷帘·卷闸·上翻门)
- ✅ 记忆开启状态

**灯**：

- ✅ 右键开关
- ✅ 循环光色温度

### 5.2 不支持的交互

- ❌ 窗户开关
- ❌ 家具抽屉/柜门
- ❌ 自定义脚本事件（v1.0 只有预定义交互）

---

## 6. 遇到不支持的需求怎么办

### 策略 1：组合近似

用现有构件组合模拟：

- 桁架 → 多个 `beam`
- 方柱 → `primitive.box`
- 复杂窗 → `opening` + `primitive`

### 策略 2：降级简化

简化需求到可实现范围：

- 复杂柱头 → 简化为基本柱式
- 旋转楼梯 → 简化为直跑楼梯
- 多门扇 → 简化为单门扇

### 策略 3：明确告知限制

如果无法近似或降级：

```jsonc
{
  "status": "not_supported",
  "message": "当前不支持旋转楼梯，已简化为直跑楼梯。如需精确还原，建议使用外部建模工具。",
  "fallback": { ... }  // 降级方案
}
```

---

## 7. 能力边界检查清单

生成 WILD 前，检查：

- [ ] 使用的所有 `type` 是否在支持列表中？
- [ ] 使用的字段是否都已实现？
- [ ] 是否猜测了未定义的字段？
- [ ] 不支持的需求是否有降级方案？
- [ ] 是否向用户明确了限制？

---

## 实现来源

- `wild-core/schema.json`
- `wild-core/types.ts`
- `wild-core/src/primitive/registry.ts`
- `wild-core/src/primitive/resolver.ts`

能力边界与当前引擎版本保持同步。
