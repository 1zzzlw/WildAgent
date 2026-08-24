---
knowledge_layer: architecture
entity_type: door
entity_name: door_family
topic: assembly
status: proposed
authority: domain_reference
source: components/doors.md
primary_terms:
  - 门
  - door
  - opening
  - leafCount
  - hingeSide
synonyms: []
---

# 门构件分类与组装规则

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理 door/opening/mullion/column/beam 等组合形成门型的规则。
> RAG 关键词：door、opening、门、隔扇门、板门、玻璃门、拱门、旋转门、折叠门、门型速配
> 能力边界：`geometry.elements` 没有 `door`、`mullion`、`cornice` 类型；`geometry.components` 只支持基础静态 `door`，不支持本文的 `leafCount`、`hingeSide`、`swingDirection` 等详细字段。本文仍整体标为 `proposed`，用于保留门型需求，不参与默认正式生成；可执行基础门语法见 `engine-capability-boundaries.md`。

---
## X.2 门分类

门在 WILD 中有两个关键构件：**`opening`**（洞口）定义墙上的开洞尺寸和形状，**`door`**（门扇）定义可开合实体。复杂造型的门 = `opening` + `door` + `mullion` + `window`（门亮子）+ `cornice`（门楣装饰）。

### X.2.1 按开启方式分类

<!-- rag-meta
entity_type: door
entity_name: door_opening_modes
topic: classification
status: proposed
authority: domain_reference
primary_terms:
  - 门开启方式
  - door opening
  - leafCount
  - hingeSide
synonyms: []
-->

| 开启方式 | WILD door.leafCount | hingeSide | 特点 | 适用场景 |
|:---|:---:|:---|:---|:---|
| **平开门(单扇)** | 1 | left/right | 最常用，内开或外开 | 住宅卧室、办公室 |
| **平开门(双扇)** | 2 | left+right | 大开间入口 | 客厅、酒店大堂 |
| **推拉门** | 1~2 | — (滑动) | 不占空间，密封差 | 阳台、衣帽间 |
| **折叠门** | ≥2 | — (折叠) | 全开敞 | 商铺门面、庭院 |
| **转门** | 3~4（旋转体） | — | 防气流，恒温 | 酒店/写字楼入口 |
| **卷帘门** | 1（卷轴式） | — | 占高不占深 | 厂房、车库 |

**WILD 门的核心参数**：

| 参数 | 说明 | 可选值 |
|:---|:---|:---|
| `style` | 门扇样式 | `flush`(平板) / `panel`(嵌板) / `glass`(玻璃) / `louvered`(百叶) |
| `leafCount` | 门扇数 | 1(单扇) / 2(双扇) / 4(四扇折叠) |
| `hingeSide` | 铰链侧 | `left` / `right` |
| `swingDirection` | 开启方向 | `inward` / `outward` |
| `material` | 材质 | `wood_oak` / `steel` / `glass_tempered` / `aluminum` |

### X.2.2 中式传统门 —— 构件组装公式

<!-- rag-meta
entity_type: door
entity_name: traditional_chinese_door_family
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 中式门
  - opening
  - door
synonyms:
  - traditional Chinese door
-->

> 图示：中式传统门示意图（原始资源：`docs/建筑类型分类体系_images/08_中式传统门.png`）

#### 实榻门（宫殿/城门）

<!-- rag-meta
entity_type: door
entity_name: palace_solid_panel_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 实榻门
  - door
synonyms:
  - palace gate
  - solid panel door
-->

> 组装公式：**`opening`(rectangular, 超大) + `door`(leafCount=2, style=panel, 实木厚板) + `placement`(门钉阵列, 铜钉) + `cornice`(门簪)**

```
实榻门 = opening(高5~9m) + door(双扇, 240mm厚木板)
       + placement(门钉 9×9=81, 贴附于门扇表面)
       + cornice(门楣, 装饰横枋)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=3.6~5.4m, height=5~9m |
| 门扇 | `door` | style=panel, leafCount=2, material=wood_hardwood |
| 门钉 | `placement` | 贴附于 door, rows=9, cols=9, object=半球体铜钉 |
| 门楣 | `cornice` | 洞口上方横枋, position=top |

**WILD JSON 示例——故宫太和殿式实榻门**：

```text
/* 实榻门 — 宫殿大门，高宽比约 1:0.6 */
{ "type": "opening", "id": "shitamen_opening",
  "parentWall": "palace_wall", "from": [4.0, 0, 0],
  "width": 4.2, "height": 6.6, "style": "rectangular" },
{ "type": "door", "id": "shitamen_door",
  "parentOpening": "shitamen_opening",
  "style": "panel", "leafCount": 2, "hingeSide": "left",
  "material": "hardwood", "thickness": 0.24 },
/* 门钉阵列 — placement 贴附于门扇表面，9×9=81 颗 */
{ "type": "placement", "id": "shitamen_nails",
  "parentId": "shitamen_door",
  "rows": 9, "cols": 9, "object": "半球体铜钉" },
/* 门楣 — 门洞上方的装饰横枋 */
{ "type": "cornice", "id": "shitamen_cornice",
  "parentOpening": "shitamen_opening",
  "profile": "rectangular", "position": "top",
  "overhang": 0.15, "material": "wood" }
```

---

#### 隔扇门（厅堂/宫殿内檐）

<!-- rag-meta
entity_type: door
entity_name: geshan_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 隔扇门
  - door
synonyms:
  - geshan door
  - lattice door
-->

> 组装公式：**`opening`(rectangular, 瘦高) + `door`(leafCount=4~8, style=panel) + `mullion`(棂花图案, grid/custom) + `placement`(裙板浮雕)**

隔扇门是中式建筑使用最广的门，既是门又是窗。每扇高宽比约 4:1，上部 2/3 为透光棂心（`mullion`），下部 1/3 为实心裙板。

```
隔扇门 = opening(宽0.6~0.9m/扇, 高3~4m)
        + 多扇 door(leafCount=4~8, 偶数排列)
        + mullion(在每扇上部, pattern=custom/步步锦/灯笼锦/冰裂纹)
        + 裙板 placement(下部浮雕, 如意纹/花卉)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=0.6~0.9m/扇, height=3~4m |
| 门扇骨架 | `door` | style=panel, leafCount=4|6|8, material=wood_nanmu |
| 棂心 | `mullion` | parentOpening=门洞, pattern=custom, 图案=步步锦/灯笼锦/冰裂纹 |
| 绦环板 | `placement` | 位于棂心与裙板之间, object=横板条 |
| 裙板 | `placement` | 位于下部, object=木板+浮雕 |

**WILD JSON 示例——四扇隔扇门**：

```text
/* 四扇隔扇门 — 明间厅堂入口 */
{ "type": "opening", "id": "geshan_opening_01",
  "parentWall": "mingjian_wall", "from": [2.4, 0, 0],
  "width": 3.2, "height": 3.6, "style": "rectangular" },
{ "type": "mullion", "id": "geshan_mullion_01",
  "parentOpening": "geshan_opening_01",
  "pattern": "custom", "patternName": "bubujin",
  "cols": 8, "rows": 12 },
{ "type": "door", "id": "geshan_door_01",
  "parentOpening": "geshan_opening_01",
  "style": "panel", "leafCount": 4,
  "hingeSide": "left", "material": "wood_nanmu" }
```

#### 其他中式门型速查

<!-- rag-meta
entity_type: door
entity_name: traditional_chinese_door_quick_reference
topic: matrix
status: proposed
authority: domain_reference
primary_terms:
  - 中式门型
  - 棋盘门
  - 垂花门
  - 屏门
synonyms:
  - Chinese door
-->

| 门型 | 组装公式 | leafCount | 特征 |
|:---|:---|:---:|:---|
| **棋盘门(攒边门)** | opening + door(panel, 2扇) + 角叶placement | 2 | 四边框+心板，民居大门 |
| **撒带门** | opening + door(panel, 单边无框) | 1 | 一侧无边，小院落外门 |
| **屏门(镜面门)** | opening + door(flush, 4~6扇) | 4~6 | 无棂花，素面，垂花门后 |
| **垂花门** | opening + door(2扇) + cornice(垂莲柱) + roof(gable小顶) | 2 | 二门制，前后檐悬垂莲柱 |

**WILD JSON 示例——棋盘门（民居大门）**：

```text
{ "type": "opening", "id": "qipan_opening",
  "parentWall": "courtyard_wall", "from": [0, 0, 0],
  "width": 1.8, "height": 2.4, "style": "rectangular" },
{ "type": "door", "id": "qipan_door",
  "parentOpening": "qipan_opening",
  "style": "panel", "leafCount": 2, "hingeSide": "left",
  "material": "wood_elm" }
```

**WILD JSON 示例——垂花门（四合院二门）**：

```text
/* 垂花门 = 双扇门 + 悬垂莲柱(前后) + 小屋顶 */
{ "type": "opening", "id": "chuihua_opening",
  "parentWall": "ermen_wall", "from": [0, 0, 0],
  "width": 2.4, "height": 2.8, "style": "rectangular" },
{ "type": "door", "id": "chuihua_door",
  "parentOpening": "chuihua_opening",
  "style": "panel", "leafCount": 2,
  "material": "wood_nanmu" },
{ "type": "cornice", "id": "chuihua_verandah_front",
  "parentOpening": "chuihua_opening",
  "profile": "hanging_lotus", "position": "top",
  "overhang": 1.2, "material": "wood" },
{ "type": "roof", "id": "chuihua_roof",
  "plan": [[-1.2,0],[3.6,0],[3.6,2.4],[-1.2,2.4]],
  "roofType": "gable", "height": 3.5, "overhang": 0.9,
  "material": "grey_clay_tile" }
```

**WILD JSON 示例——屏门（镜面门，垂花门后）**：

```text
{ "type": "opening", "id": "pingmen_opening",
  "parentWall": "screen_wall", "from": [0, 0, 0],
  "width": 3.6, "height": 2.4, "style": "rectangular" },
{ "type": "door", "id": "pingmen_door",
  "parentOpening": "pingmen_opening",
  "style": "flush", "leafCount": 4,
  "material": "wood_pine", "paint": "green" }
```

### X.2.3 欧式古典门 —— 构件组装公式

<!-- rag-meta
entity_type: door
entity_name: classical_european_door_family
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 欧式门
  - panel door
  - arched door
synonyms:
  - classical European door
-->

> 图示：欧式古典门示意图（原始资源：`docs/建筑类型分类体系_images/09_欧式古典门.png`）

---

#### 嵌板门（Panel Door）——欧洲最通用的古典门型

<!-- rag-meta
entity_type: door
entity_name: panel_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 嵌板门
  - door
synonyms:
  - panel door
  - classical door
-->

> 组装公式：**`opening`(rectangular) + `door`(panel, leafCount=1, 横竖框分割 6 嵌板)**

```
嵌板门 = opening(标准门洞, w=0.9~1.2m, h=2.1~2.4m)
        + door(style=panel, 横3条+竖2条中挺 → 6格嵌板)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=1.0m, height=2.1m |
| 门扇 | `door` | style=panel, leafCount=1, material=wood_oak |

```text
{ "type": "opening", "id": "panel_door_opening",
  "parentWall": "european_hall", "from": [2.0, 0, 0],
  "width": 1.0, "height": 2.1, "style": "rectangular" },
{ "type": "door", "id": "panel_door",
  "parentOpening": "panel_door_opening",
  "style": "panel", "leafCount": 1, "hingeSide": "left",
  "material": "wood_oak", "panels": [2, 3] }
```

---

#### 平板门（Flush Door）——现代简化版欧式门

<!-- rag-meta
entity_type: door
entity_name: flush_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 平板门
  - door
synonyms:
  - flush door
  - modern door
-->

> 组装公式：**`opening`(rectangular) + `door`(flush)**

```
平板门 = opening(标准) + door(flush, 素面无嵌板, 可烤漆/贴面)
```
| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=0.9m, height=2.1m |
| 门扇 | `door` | style=flush, leafCount=1, material=wood_pine |

```text
{ "type": "opening", "id": "flush_door_opening",
  "parentWall": "hotel_corridor", "from": [1.5, 0, 0],
  "width": 0.9, "height": 2.1, "style": "rectangular" },
{ "type": "door", "id": "flush_door",
  "parentOpening": "flush_door_opening",
  "style": "flush", "leafCount": 1,
  "material": "wood_pine" }
```

---

#### 法式门（French Door）——通向花园/阳台的双扇玻璃门

<!-- rag-meta
entity_type: door
entity_name: french_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 法式门
  - glass door
  - double leaf
synonyms:
  - French door
-->

> 组装公式：**`opening`(arched/rect) + `mullion`(grid, cols=2 rows=3) + `door`(glass, leafCount=2)**

```
法式门 = opening(宽1.8m, 高2.4m)
        + mullion(grid, 每扇 2列×3行玻璃分格)
        + door(glass, 双扇外开, 白色木框)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=1.8m, height=2.4m |
| 玻璃分格 | `mullion` | pattern=grid, cols=2, rows=3 |
| 门扇 | `door` | style=glass, leafCount=2, swingDirection=outward |

```text
{ "type": "opening", "id": "french_door_opening",
  "parentWall": "garden_wall", "from": [3.0, 0, 0],
  "width": 1.8, "height": 2.4, "style": "rectangular" },
{ "type": "mullion", "id": "french_mullion",
  "parentOpening": "french_door_opening",
  "pattern": "grid", "cols": 2, "rows": 3 },
{ "type": "door", "id": "french_door",
  "parentOpening": "french_door_opening",
  "style": "glass", "leafCount": 2,
  "swingDirection": "outward", "material": "wood_white" }
```

---

#### 荷兰门（Dutch Door）——上下分体独立开启

<!-- rag-meta
entity_type: door
entity_name: dutch_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 荷兰门
synonyms:
  - Dutch door
  - split door
-->

> 组装公式：**2 × `opening`(上下叠加) + 2 × `door`(panel, 上半/下半独立)**

```
荷兰门 = 上半段 opening(从 1.1m 到顶)
         + door(panel, 单扇, 可独立内开→通风)
       + 下半段 opening(从地面到 1.1m)
         + door(panel, 单扇, 可锁→防畜)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 上段洞口 | `opening` | from y=1.1, width=1.0m, height=1.0m |
| 上段门扇 | `door` | style=panel, leafCount=1, hingeSide=left |
| 下段洞口 | `opening` | from y=0, width=1.0m, height=1.1m |
| 下段门扇 | `door` | style=panel, leafCount=1, hingeSide=left |

```text
{ "type": "opening", "id": "dutch_upper_opening",
  "parentWall": "farmhouse_wall", "from": [1.0, 1.1, 0],
  "width": 1.0, "height": 1.0, "style": "rectangular" },
{ "type": "door", "id": "dutch_upper_door",
  "parentOpening": "dutch_upper_opening",
  "style": "panel", "leafCount": 1, "hingeSide": "left" },
{ "type": "opening", "id": "dutch_lower_opening",
  "parentWall": "farmhouse_wall", "from": [1.0, 0, 0],
  "width": 1.0, "height": 1.1, "style": "rectangular" },
{ "type": "door", "id": "dutch_lower_door",
  "parentOpening": "dutch_lower_opening",
  "style": "panel", "leafCount": 1, "hingeSide": "left" }
```

---

#### 拱形大门（Arched Entrance）——教堂/市政厅入口

<!-- rag-meta
entity_type: door
entity_name: arched_entrance
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 拱形大门
  - opening
  - church door
synonyms:
  - arched entrance
-->

> 组装公式：**`opening`(arched, 高宽比 2:1) + `door`(panel, leafCount=2, 厚重木板) + `cornice`(拱顶石)**

```
拱形大门 = opening(arched, w=1.8~3.6m, h=3.6~8m)
          + door(panel, 双扇, 拼板, 铁质铰链)
          + cornice(拱顶石, 拱顶部中心)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 拱形洞口 | `opening` | style=arched, width=2.4m, height=5.0m |
| 门扇 | `door` | style=panel, leafCount=2, material=wood_oak |
| 拱顶石 | `cornice` | profile=keystone, position=top, parentOpening=拱洞 |

```text
{ "type": "opening", "id": "arched_entrance",
  "parentWall": "church_facade", "from": [6.0, 0, 0],
  "width": 2.4, "height": 5.0, "style": "arched" },
{ "type": "door", "id": "arched_door",
  "parentOpening": "arched_entrance",
  "style": "panel", "leafCount": 2,
  "material": "wood_oak", "thickness": 0.08 },
{ "type": "cornice", "id": "arched_keystone",
  "parentOpening": "arched_entrance",
  "profile": "keystone", "position": "top" }
```

---

### X.2.4 现代门 —— 构件组装公式

<!-- rag-meta
entity_type: door
entity_name: modern_door_family
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 现代门
  - sliding glass door
  - revolving door
synonyms:
  - modern door
-->

> 图示：现代门示意图（原始资源：`docs/建筑类型分类体系_images/10_现代门.png`）

---

#### 玻璃推拉门（Sliding Glass Door）

<!-- rag-meta
entity_type: door
entity_name: sliding_glass_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 玻璃推拉门
  - glass
  - door
synonyms:
  - sliding glass door
-->

> 组装公式：**`opening`(rect, 宽 1.8~3.6m) + `door`(glass, leafCount=2, 滑轨模式)**

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=2.4m, height=2.4m |
| 玻璃门扇 | `door` | style=glass, leafCount=2, mechanism=sliding |

```text
{ "type": "opening", "id": "sliding_door_opening",
  "parentWall": "shop_front", "from": [2.0, 0, 0],
  "width": 2.4, "height": 2.4, "style": "rectangular" },
{ "type": "door", "id": "sliding_door",
  "parentOpening": "sliding_door_opening",
  "style": "glass", "leafCount": 2, "mechanism": "sliding",
  "material": "aluminum", "glassType": "tempered" }
```

---

#### 自动感应门（Automatic Sensor Door）

<!-- rag-meta
entity_type: door
entity_name: automatic_sensor_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 自动感应门
  - sliding door
synonyms:
  - automatic sensor door
-->

> 组装公式：**`opening`(rect, 宽 3~6m) + `door`(glass, leafCount=2~4, 传感器+电机驱动)**

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=4.0m, height=2.4m |
| 玻璃门扇 | `door` | style=glass, leafCount=4(两固定+两活动), mechanism=auto_sliding |

```text
{ "type": "opening", "id": "auto_door_opening",
  "parentWall": "office_lobby", "from": [0, 0, 0],
  "width": 4.0, "height": 2.4, "style": "rectangular" },
{ "type": "door", "id": "auto_door",
  "parentOpening": "auto_door_opening",
  "style": "glass", "leafCount": 4, "mechanism": "auto_sliding",
  "sensorType": "infrared", "material": "aluminum" }
```

---

#### 工业卷帘门（Roll-up Door）

<!-- rag-meta
entity_type: door
entity_name: roll_up_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 工业卷帘门
  - industrial door
synonyms:
  - roll-up door
-->

> 组装公式：**`opening`(rect, 宽 3~8m) + `door`(louvered, 卷轴机构, leafCount=1)**

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=5.0m, height=5.0m |
| 卷帘门扇 | `door` | style=louvered, leafCount=1, mechanism=roll_up |

```text
{ "type": "opening", "id": "rollup_door_opening",
  "parentWall": "factory_wall", "from": [6.0, 0, 0],
  "width": 5.0, "height": 5.0, "style": "rectangular" },
{ "type": "door", "id": "rollup_door",
  "parentOpening": "rollup_door_opening",
  "style": "louvered", "leafCount": 1, "mechanism": "roll_up",
  "material": "steel_galvanized", "slatWidth": 0.1 }
```

---

#### 气密门（医用密封门）

<!-- rag-meta
entity_type: door
entity_name: airtight_medical_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 气密门
  - 医用密封门
synonyms:
  - airtight medical door
-->

> 组装公式：**`opening`(rect, 标准) + `door`(flush, 密封胶条, 闭门器)**

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=1.2m, height=2.1m |
| 密封门扇 | `door` | style=flush, leafCount=1, seal=airtight |

```text
{ "type": "opening", "id": "airtight_door_opening",
  "parentWall": "or_wall", "from": [1.0, 0, 0],
  "width": 1.2, "height": 2.1, "style": "rectangular" },
{ "type": "door", "id": "airtight_door",
  "parentOpening": "airtight_door_opening",
  "style": "flush", "leafCount": 1,
  "material": "steel_stainless", "seal": "airtight",
  "closer": true, "panicBar": false }
```

---

#### 防火门（Fire-rated Door）

<!-- rag-meta
entity_type: door
entity_name: fire_rated_door
topic: assembly
status: proposed
authority: domain_reference
primary_terms:
  - 防火门
synonyms:
  - fire-rated door
  - fire door
-->

> 组装公式：**`opening`(rect) + `door`(flush, steel, 闭门器+顺位器)**

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 门洞 | `opening` | style=rectangular, width=1.0~1.5m, height=2.1m |
| 防火门扇 | `door` | style=flush, leafCount=1/2, material=steel, fireRating=甲/乙/丙 |

```text
{ "type": "opening", "id": "fire_door_opening",
  "parentWall": "stairwell_wall", "from": [3.0, 0, 0],
  "width": 1.2, "height": 2.1, "style": "rectangular" },
{ "type": "door", "id": "fire_door",
  "parentOpening": "fire_door_opening",
  "style": "flush", "leafCount": 1, "hingeSide": "left",
  "material": "steel", "fireRating": "乙级_1h",
  "closer": true, "panicBar": true, "swingDirection": "outward" }
```

---

---

### X.2.5 门-构件组装关系总表

<!-- rag-meta
entity_type: door
entity_name: door_component_matrix
topic: matrix
status: proposed
authority: domain_reference
primary_terms:
  - 门构件矩阵
  - door component matrix
  - opening
  - door
  - mullion
synonyms: []
-->

| 门型 | opening.style | door.style | door.leafCount | mullion | cornice/placement | 子构件数 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **实榻门(宫殿)** | rectangular | panel | 2 | — | placement(门钉)+cornice(门楣) | 4 |
| **隔扇门(厅堂)** | rectangular | panel | 4~8 | custom(棂花) | placement(裙板) | 4 |
| **棋盘门(民居)** | rectangular | panel | 2 | — | placement(角叶) | 3 |
| **垂花门(二门)** | rectangular | panel | 2 | — | cornice(垂莲柱)+roof | 4 |
| **屏门(镜面)** | rectangular | flush | 4~6 | — | — | 2 |
| **嵌板门(欧式)** | rectangular | panel | 1 | — | — | 2 |
| **平板门(欧式)** | rectangular | flush | 1 | — | — | 2 |
| **法式门** | rect/arched | glass | 2 | grid(2×3) | — | 3 |
| **荷兰门** | rect×2(上下) | panel | 1+1 | — | — | 4 |
| **拱形大门** | arched | panel | 2 | — | cornice(拱顶石) | 3 |
| **玻璃推拉门** | rectangular | glass | 2 | — | — | 2 |
| **自动感应门** | rectangular | glass | 4 | — | — | 2 |
| **工业卷帘门** | rectangular | louvered | 1(卷轴) | — | — | 2 |
| **气密门(医用)** | rectangular | flush | 1 | — | — | 2 |
| **防火门** | rectangular | flush | 1~2 | — | — | 2 |

> **图例**：子构件数 = opening + door + mullion + 装饰件(cornice/placement/roof) 合计。

### X.2.6 门型与建筑类型速配

<!-- rag-meta
entity_type: door
entity_name: door_building_style_matrix
topic: matrix
status: proposed
authority: domain_reference
primary_terms:
  - 门型速配
  - door style
  - building type
synonyms: []
-->

| 建筑类型 | 推荐门型 | 说明 |
|:---|:---|:---|
| 中式传统别墅 | 棋盘门 + 垂花门 + 屏门 | 四合院大门+二门+屏门三进制 |
| 宫殿/庙宇 | 实榻门 + 隔扇门 | 威严+可拆卸全开 |
| 新中式别墅 | 简化隔扇门(玻璃+棂花) + 法式门 | 传统符号+现代采光 |
| 现代别墅 | 法式门 + 玻璃推拉门 | 大面积玻璃+花园贯通 |
| 欧式庄园 | 嵌板门 + 拱形大门 | 古典比例+仪式感入口 |
| 办公超高层 | 自动感应门 + 防火门 | 大堂自动+楼梯间防火 |
| 工业厂房 | 工业卷帘门 + 防火门 | 大跨物流+消防规范 |
| 医院 | 气密门 + 自动感应门 | 手术室洁净+公共区无障碍 |
| 哥特教堂 | 拱形大门(双扇, 拱顶石) | 神圣仪式入口 |

---
