---
doc_type: component
doc_scope: generation
knowledge_layer: architecture
entity_type: window
entity_name: window_family
topic: assembly
wild_version: "1.1"
status: proposed
authority: domain_reference
source: components/windows.md
keywords:
  - 窗
  - window
  - opening
  - mullion
  - sashType
---

# 窗构件分类与组装规则

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理 window/opening/mullion 等组合形成窗型的规则。
> RAG 关键词：window、opening、mullion、窗、槛窗、支摘窗、漏窗、欧式窗、现代窗、sashType、muntinPattern
> 能力边界：`geometry.elements` 没有 `window`、`mullion` 类型；`geometry.components` 只支持基础静态 `window` 及横竖窗棂数量，不支持本文的 `sashType`、`muntinPattern` 和开启机制，`opening` 也不能引用屋顶。本文仍整体标为 `proposed`，用于保留窗型需求，不参与默认正式生成；可执行基础窗语法见 `engine-capability-boundaries.md`。

---
## X.3 窗分类（核心）

**窗不是单一构件——它是 WILD 多个子构件协同组装的结果。**

一扇复杂窗户的完整构成：

```
窗 = opening(洞口, 在墙上打孔)
    + window(窗扇, 玻璃+可开启机制)
    + mullion(窗棂/分格, 可选, 装饰图案)
    + cornice(窗楣/窗台, 可选, 装饰线条)
```

**核心设计原则**：`opening` 决定窗的**轮廓造型**（方/拱/圆/哥特尖）；`mullion` 决定窗的**内部图案**（棂花/菱花/分格）；`window` 决定**开启方式**和**透光材质**；`cornice` 提供**装饰收边**。

### X.3.1 按开启方式分类 —— window.sashType 映射

<!-- rag-meta
entity_type: window
entity_name: window_opening_modes
topic: classification
status: proposed
authority: domain_reference
keywords: 窗开启方式, window opening, sashType
-->

| 开启方式 | sashType | 特征 | 通风效率 | 密封 | 典型应用 |
|:---|:---:|:---|:---:|:---:|:---|
| **固定窗** | `fixed` | 不可开启，仅采光观景 | — | ★★★★★ | 高层幕墙、天窗 |
| **平开窗(外开)** | `casement` | 铰链侧边，向外推 | ★★★★★ | ★★★★ | 住宅、学校、别墅 |
| **平开窗(内开)** | `casement` + swingDirection=inward | 向内拉 | ★★★★★ | ★★★★★ | 欧洲常见 |
| **内开内倒** | `casement` + tiltMode | 可平开可上悬 | ★★★ | ★★★★ | 现代高层住宅 |
| **推拉窗** | `sliding` | 水平滑动 | ★★★ | ★★ | 阳台、普通住宅 |
| **上悬窗** | `awning` | 底部外推，上轴旋转 | ★★ | ★★★★ | 卫生间、高窗 |
| **下悬窗** | `hopper` | 顶部内拉，下轴旋转 | ★★ | ★★ | 地下室 |
| **中悬窗** | `pivot` | 水平中轴旋转 | ★★★★ | ★★ | 厂房、体育场 |
| **立转窗** | `pivot_vertical` | 垂直中轴旋转 | ★★★★ | ★★ | 特殊建筑 |

### X.3.2 中式传统窗 —— 构件组装公式

<!-- rag-meta
entity_type: window
entity_name: traditional_chinese_window_family
topic: assembly
status: proposed
authority: domain_reference
keywords: 中式窗, traditional Chinese window, mullion, 支摘窗, 漏窗
-->

> 图示：中式窗示意图（直棂·一码三箭·槛窗·支摘窗）（原始资源：`docs/建筑类型分类体系_images/11_中式窗_直棂槛窗支摘.png`）

中式窗的核心特征是**窗棂艺术**——在 `opening` 内部用 `mullion` 构成各种几何图案，兼具采光和装饰功能。

---

#### 直棂窗（最古早的中式窗型）

<!-- rag-meta
entity_type: window
entity_name: zhiling_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 直棂窗, zhiling window, vertical mullion, window
-->

> 组装公式：**`opening`(rectangular) + `window`(fixed) + `mullion`(vertical, 等距排列)**

```
直棂窗 = opening(高瘦矩形)
        + mullion(pattern=vertical, 椽条断面方形, 间距=椽条宽×3)
        + window(fixed, 内侧糊纸/外侧玻璃)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 窗洞 | `opening` | style=rectangular, width=1.0~1.5m, height=1.8~2.4m |
| 直棂 | `mullion` | pattern=vertical, cols=0(仅竖), rows=8~14, 断面=方10mm |
| 窗扇 | `window` | sashType=fixed |

**WILD JSON**：

```text
{ "type": "opening", "id": "zhiling_opening",
  "parentWall": "temple_wall", "from": [2.0, 1.2, 0],
  "width": 1.2, "height": 2.0, "style": "rectangular" },
{ "type": "mullion", "id": "zhiling_mullion",
  "parentOpening": "zhiling_opening",
  "pattern": "vertical", "cols": 0, "rows": 12 },
{ "type": "window", "id": "zhiling_window",
  "parentOpening": "zhiling_opening",
  "sashType": "fixed" }
```

---

#### 一码三箭直棂窗（直棂窗进阶版）

<!-- rag-meta
entity_type: window
entity_name: yima_sanjian_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 一码三箭直棂窗, Chinese lattice window, grid mullion
-->

> 组装公式：**`opening`(rectangular) + `mullion`(grid, 3 rows × N cols) + `window`(fixed)**

与直棂窗的区别：在竖棂条的上、中、下部位各横穿三根水平棂条，形成 `grid` 图案。`mullion` 的 `pattern` 从 `vertical` 变为 `grid`，`rows=3`。

```text
{ "type": "opening", "id": "yima_opening",
  "parentWall": "courtyard_wall",
  "width": 1.4, "height": 1.8, "style": "rectangular" },
{ "type": "mullion", "id": "yima_mullion",
  "parentOpening": "yima_opening",
  "pattern": "grid", "cols": 16, "rows": 3 },
{ "type": "window", "id": "yima_window",
  "parentOpening": "yima_opening",
  "sashType": "fixed" }
```

---

#### 槛窗（与隔扇门配套的标准窗）

<!-- rag-meta
entity_type: window
entity_name: sill_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 槛窗, sill window, geshan door, window
-->

> 组装公式：**`opening`(rectangular, 宽=隔扇门宽, 高=隔扇门高−裙板高) + `mullion`(grid/custom, 与隔扇门棂花一致) + `window`(casement) + `wall`(槛墙, 窗下矮墙)**

```
槛窗 = 槛墙(砖砌, 高0.8~1.0m, 承托窗扇)
      + opening(宽同隔扇门, 高=隔扇门去裙板)
      + mullion(custom, 图案与相邻隔扇门统一)
      + window(casement, 可向外开启)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 槛墙 | `wall` | height=0.8~1.0m, thickness=0.24m, material=grey_brick |
| 窗洞 | `opening` | 位于槛墙之上, width=0.6~0.9m, height=1.8~2.4m |
| 棂心 | `mullion` | pattern=grid/custom, 与同立面隔扇门使用相同 pattern |
| 窗扇 | `window` | sashType=casement, 可内外开 |

---

#### 支摘窗（民居经典——可支起+可摘下）

<!-- rag-meta
entity_type: window
entity_name: zhizhai_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 支摘窗, zhizhai window, casement, opening
-->

> 组装公式：**2 × [opening(上下两层) + window + mullion]** — 上层 awning(支起)，下层 casement(摘下)**

```
支摘窗 = 上段 opening(高=总高×2/3)
         + window(awning, 可推出支起)
         + mullion(grid)
       + 下段 opening(高=总高×1/3)
         + window(casement, 可拆卸摘下)
         + mullion(grid)
```

**WILD JSON 示例**：

```text
/* 上段 — 支窗 */
{ "type": "opening", "id": "zhizhai_upper_opening",
  "parentWall": "siheyuan_wall", "from": [0.5, 1.6, 0],
  "width": 1.2, "height": 1.0, "style": "rectangular" },
{ "type": "mullion", "id": "zhizhai_upper_mullion",
  "parentOpening": "zhizhai_upper_opening",
  "pattern": "grid", "cols": 10, "rows": 6 },
{ "type": "window", "id": "zhizhai_upper_window",
  "parentOpening": "zhizhai_upper_opening",
  "sashType": "awning", "swingDirection": "outward" },

/* 下段 — 摘窗 */
{ "type": "opening", "id": "zhizhai_lower_opening",
  "parentWall": "siheyuan_wall", "from": [0.5, 0.3, 0],
  "width": 1.2, "height": 1.3, "style": "rectangular" },
{ "type": "mullion", "id": "zhizhai_lower_mullion",
  "parentOpening": "zhizhai_lower_opening",
  "pattern": "grid", "cols": 10, "rows": 8 },
{ "type": "window", "id": "zhizhai_lower_window",
  "parentOpening": "zhizhai_lower_opening",
  "sashType": "casement" }
```

---

#### 漏窗（花窗/墙窗）——园林灵魂

<!-- rag-meta
entity_type: window
entity_name: lattice_leak_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 漏窗, 花窗, lattice leak window, mullion
-->

> 组装公式：**`opening`(多边形/圆形/扇形, 在砖墙上) + `mullion`(custom, 镂空图案) — 无 window 扇，仅 open frame**

漏窗是中式园林的标志元素。核心特点：**没有窗扇，只有窗洞+镂空棂条**，让墙内外景色互相渗透。

```
漏窗 = opening(自由形: 矩形/六边形/扇形/海棠形/圆形)
      + mullion(custom, 冰裂纹/万字纹/梅花纹/葵花纹)
      // 无 window 构件 — 通透无遮挡
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 窗洞 | `opening` | style=rectangular(非标准)/circular(月洞门式)/扇形, width=0.6~1.5m |
| 镂空棂条 | `mullion` | pattern=custom, 图案=冰裂纹/万字纹/梅花纹 |

```text
/* 园林冰裂纹漏窗 */
{ "type": "opening", "id": "louchuang_hexagon",
  "parentWall": "garden_wall",
  "width": 1.0, "height": 1.0, "style": "rectangular" },
{ "type": "mullion", "id": "louchuang_mullion",
  "parentOpening": "louchuang_hexagon",
  "pattern": "custom", "patternName": "ice_crack",
  "cols": 0, "rows": 0 }
/* 注意：漏窗无 window 构件 */
```

---

#### 空窗（洞窗/月洞门式窗）

<!-- rag-meta
entity_type: window
entity_name: empty_frame_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 空窗, 洞窗, empty frame window, opening
-->

> 组装公式：**仅 `opening`(圆形/多边形) — 无 mullion, 无 window — 纯粹的开洞**

园林墙上的圆洞、扇形洞，无棂无扇，纯粹框景。

```json
{ "type": "opening", "id": "moon_gate_window",
  "parentWall": "garden_wall",
  "width": 1.5, "height": 1.5, "style": "circular" }
```

---

#### 菱花窗（三交六椀/双交四椀）——宫殿最高等级

<!-- rag-meta
entity_type: window
entity_name: diamond_lattice_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 菱花窗, diamond lattice window, mullion, palace window
-->

> 组装公式：**`opening`(rectangular) + `mullion`(custom, 三交六椀放射状) + `window`(fixed)**

故宫建筑群的标准窗型。特点是棂条以 60° 三向交叉，每个交点形成六瓣菱花。

```
菱花窗 = opening(瘦高矩形, 0.7×2.4m)
        + mullion(custom, radial, 60°交叉, 花心钉铜帽)
        + window(fixed)
```

```text
{ "type": "opening", "id": "linghua_opening",
  "parentWall": "palace_wall",
  "width": 0.7, "height": 2.4, "style": "rectangular" },
{ "type": "mullion", "id": "linghua_mullion",
  "parentOpening": "linghua_opening",
  "pattern": "custom", "patternName": "san_jiao_liu_wan",
  "cols": 0, "rows": 0 },
{ "type": "window", "id": "linghua_window",
  "parentOpening": "linghua_opening",
  "sashType": "fixed" }
```

---

#### 横披窗（门/窗上方的固定亮窗）

<!-- rag-meta
entity_type: window
entity_name: transom_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 横披窗, transom window, fixed window
-->

> 组装公式：**`opening`(扁长形, 装在门上槛以上) + `window`(fixed)**

```text
{ "type": "opening", "id": "hengpi_opening",
  "parentWall": "temple_wall", "from": [0, 3.0, 0],
  "width": 3.2, "height": 0.5, "style": "rectangular" },
{ "type": "window", "id": "hengpi_window",
  "parentOpening": "hengpi_opening",
  "sashType": "fixed" }
```

---

> 图示：中式窗示意图（漏窗·空窗·菱花窗·横披窗）（原始资源：`docs/建筑类型分类体系_images/12_中式窗_漏窗菱花横披.png`）

### X.3.3 欧式古典窗 —— 构件组装公式

<!-- rag-meta
entity_type: window
entity_name: classical_european_window_family
topic: assembly
status: proposed
authority: domain_reference
keywords: 欧式窗, classical European window, rose window, bay window
-->

> 图示：欧式古典窗示意图（原始资源：`docs/建筑类型分类体系_images/13_欧式古典窗.png`）

---

#### 玫瑰窗（Rose Window）——哥特教堂标志

<!-- rag-meta
entity_type: window
entity_name: rose_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 玫瑰窗, rose window, Gothic window, radial mullion
-->

> 组装公式：**`opening`(circular, 直径 3~13m) + `mullion`(custom, 放射辐条状) + `window`(fixed, 彩色玻璃)**

```
玫瑰窗 = opening(圆形, style=circular, 极大直径)
        + mullion(custom, radial_pattern, 从圆心辐射)
        + window(fixed, 彩色玻璃, 红/蓝/金色调)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 圆窗洞 | `opening` | style=circular, width=3~13m, height=3~13m |
| 放射棂 | `mullion` | pattern=custom, patternName=radial, 从圆心发散 |
| 花窗玻璃 | `window` | sashType=fixed, material=stained_glass(红/蓝) |

```text
{ "type": "opening", "id": "rose_window_opening",
  "parentWall": "cathedral_facade", "from": [0, 12, 0],
  "width": 8.0, "height": 8.0, "style": "circular" },
{ "type": "mullion", "id": "rose_mullion",
  "parentOpening": "rose_window_opening",
  "pattern": "custom", "patternName": "radial_rose",
  "cols": 0, "rows": 0 },
{ "type": "window", "id": "rose_window",
  "parentOpening": "rose_window_opening",
  "sashType": "fixed", "material": "stained_glass" }
```

---

#### 帕拉第奥窗（Palladian Window / Serliana）——文艺复兴经典

<!-- rag-meta
entity_type: window
entity_name: palladian_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 帕拉第奥窗, Palladian window, Serliana
-->

> 组装公式：**1 × opening(arched, 中央大拱) + 2 × opening(rectangular, 两侧小矩形) + 3 × window(fixed) + mullion(分隔) + cornice(拱顶石)**

```
帕拉第奥窗 = 中间 opening(arched, w=1.5h)
            + window(fixed, 中央大玻璃)
            + 左侧 opening(rectangular, w=0.4h)
            + window(fixed, 左)
            + 右侧 opening(rectangular, w=0.4h)
            + window(fixed, 右)
            + mullion(分隔柱, 拱窗与平窗之间)
            + cornice(拱顶石, 拱窗顶部)
```

| 子构件 | type | 关键参数 |
|:---:|:---:|:---|
| 中央拱洞 | `opening` | style=arched, width=1.5m, height=2.4m |
| 左平窗洞 | `opening` | style=rectangular, width=0.6m, height=2.0m |
| 右平窗洞 | `opening` | style=rectangular, width=0.6m, height=2.0m |
| 三扇窗 | `window` × 3 | sashType=fixed |
| 分隔竖棂 | `mullion` | pattern=vertical, cols=2(分隔拱窗与平窗) |

```text
/* 以中央拱窗为例，左右平窗同理 */
{ "type": "opening", "id": "palladian_center",
  "parentWall": "villa_facade", "from": [4.5, 1.0, 0],
  "width": 1.5, "height": 2.4, "style": "arched" },
{ "type": "window", "id": "palladian_center_win",
  "parentOpening": "palladian_center",
  "sashType": "fixed" },
{ "type": "opening", "id": "palladian_left",
  "parentWall": "villa_facade", "from": [3.5, 1.4, 0],
  "width": 0.6, "height": 2.0, "style": "rectangular" },
{ "type": "window", "id": "palladian_left_win",
  "parentOpening": "palladian_left",
  "sashType": "fixed" },
{ "type": "cornice", "id": "palladian_keystone",
  "parentOpening": "palladian_center",
  "profile": "keystone", "position": "top" }
```

---

#### 尖拱窗（哥特式）

<!-- rag-meta
entity_type: window
entity_name: gothic_pointed_arch_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 尖拱窗, Gothic pointed arch window, opening
-->

> 组装公式：**`opening`(gothic, 尖顶双弧) + `window`(fixed) + `mullion`(vertical, 2~3列瘦高棂) + `mullion`(horizontal, 上部玫瑰纹)**

哥特窗的 `opening.style=gothic`，顶部由两段弧相交成尖角。内部用竖棂将窗分为 2~3 条细长区域（"柳叶"），上部可加一组小型玫瑰纹分格。

```text
{ "type": "opening", "id": "gothic_window",
  "parentWall": "cathedral_nave", "from": [1.5, 2.0, 0],
  "width": 1.2, "height": 6.0, "style": "gothic" },
{ "type": "mullion", "id": "gothic_vertical_mullion",
  "parentOpening": "gothic_window",
  "pattern": "vertical", "cols": 2, "rows": 0 },
{ "type": "mullion", "id": "gothic_tracery",
  "parentOpening": "gothic_window",
  "pattern": "custom", "patternName": "trefoil_tracery" },
{ "type": "window", "id": "gothic_stained_glass",
  "parentOpening": "gothic_window",
  "sashType": "fixed", "material": "stained_glass" }
```

---

#### 圆拱窗（罗马风）

<!-- rag-meta
entity_type: window
entity_name: roman_round_arch_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 圆拱窗, Roman round arch window, opening
-->

> 组装公式：**`opening`(arched, 半圆拱) + `window`(fixed/casement) — 比哥特窗矮、宽**

罗马风窗的特点是厚重石墙上的小圆拱洞，装饰简洁。`opening.style=arched` 产生顶部半圆形。

```text
{ "type": "opening", "id": "romanesque_window",
  "parentWall": "church_wall",
  "width": 1.0, "height": 2.0, "style": "arched" },
{ "type": "window", "id": "romanesque_win",
  "parentOpening": "romanesque_window",
  "sashType": "fixed" }
```

---

#### 柳叶窗（Lancet Window）——哥特教堂细长窗

<!-- rag-meta
entity_type: window
entity_name: lancet_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 柳叶窗, lancet window, Gothic church window
-->

> 组装公式：**`opening`(gothic, 极瘦高, 宽0.3~0.5m, 高3~8m) + `window`(fixed)**

比哥特窗更窄更高，宽高比可达 1:8~1:10。

```text
{ "type": "opening", "id": "lancet_window",
  "parentWall": "cathedral_apse",
  "width": 0.4, "height": 4.0, "style": "gothic" },
{ "type": "window", "id": "lancet_win",
  "parentOpening": "lancet_window",
  "sashType": "fixed", "material": "stained_glass" }
```

---

### X.3.4 现代窗 —— 构件组装公式

<!-- rag-meta
entity_type: window
entity_name: modern_window_family
topic: assembly
status: proposed
authority: domain_reference
keywords: 现代窗, modern window, curtain wall, corner window
-->

> 图示：现代窗示意图（原始资源：`docs/建筑类型分类体系_images/14_现代窗.png`）

---

#### 幕墙窗（Curtain Wall Grid）

<!-- rag-meta
entity_type: window
entity_name: curtain_wall_window
topic: assembly
status: experimental
authority: engine
keywords: 幕墙窗, curtain wall grid, fixed window, verticalMullions, horizontalMullions
-->

> 组装公式：**`wall` 宿主 + `window` 网格 + 分离的框/玻璃材质；高细节时改用 `primitive.box` 显式骨架。**

当前 `window` 直接通过 `parentWall` 依附墙体，并由 `verticalMullions`、`horizontalMullions` 生成分格。不要另外创建 `opening` 再让窗引用 `parentOpening`，也不要输出不存在的 `mullion` 类型。

完整的能力边界见 `components/glass-curtain-walls.md`；整片立面的生成顺序、网格公式、示例和回退见 `recipes/glass-curtain-wall-assembly.md`。

#### 转角窗（Corner Window）——现代别墅标志

<!-- rag-meta
entity_type: window
entity_name: corner_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 转角窗, corner window, modern villa
-->

> 组装公式：**2 × `opening`(分别在相邻两面墙上, 交汇于阳角) + 2 × `window`(fixed) — 转角处无柱**

```text
/* 墙 A 上的转角窗段 */
{ "type": "opening", "id": "corner_opening_a",
  "parentWall": "wall_south", "from": [6.8, 1.0, 0],
  "width": 2.0, "height": 2.4, "style": "rectangular" },
{ "type": "window", "id": "corner_win_a",
  "parentOpening": "corner_opening_a", "sashType": "fixed" },
/* 墙 B(垂直) 上的转角窗段 — 与墙A段连续 */
{ "type": "opening", "id": "corner_opening_b",
  "parentWall": "wall_west", "from": [0, 1.0, 6.8],
  "width": 2.0, "height": 2.4, "style": "rectangular" },
{ "type": "window", "id": "corner_win_b",
  "parentOpening": "corner_opening_b", "sashType": "fixed" }
```

---

#### 条形窗（Ribbon/Strip Window）——柯布西耶五原则

<!-- rag-meta
entity_type: window
entity_name: ribbon_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 条形窗, ribbon window, strip window
-->

> 组装公式：**单个 `opening`(超长, 宽可达整面墙 80%) + `window`(fixed)**

```text
{ "type": "opening", "id": "ribbon_window",
  "parentWall": "villa_wall",
  "from": [0.5, 1.0, 0],
  "width": 14.0, "height": 1.1, "style": "rectangular" },
{ "type": "window", "id": "ribbon_win",
  "parentOpening": "ribbon_window",
  "sashType": "fixed" }
```

---

#### 天窗（Skylight）——开在屋顶上

<!-- rag-meta
entity_type: window
entity_name: skylight
topic: assembly
status: proposed
authority: domain_reference
keywords: 天窗, skylight, roof opening
-->

> 组装公式：**`opening`(parent=roof, 而非 wall) + `window`(fixed/awning)**

天窗的特殊之处：`opening` 的 `parentWall` 改为 `parentRoof`。

```text
{ "type": "opening", "id": "skylight_opening",
  "parentRoof": "flat_roof",
  "from": [4.0, 0, 3.0],
  "width": 1.0, "height": 1.0, "style": "rectangular" },
{ "type": "window", "id": "skylight_win",
  "parentOpening": "skylight_opening",
  "sashType": "awning" }
```

---

#### 落地窗（Floor-to-Ceiling）

<!-- rag-meta
entity_type: window
entity_name: floor_to_ceiling_window
topic: assembly
status: proposed
authority: domain_reference
keywords: 落地窗, floor-to-ceiling window, fixed window
-->

> 组装公式：**`opening`(高=层高, 从地面到梁底) + `window`(fixed/casement) + `railing`(落地护栏)**

```text
{ "type": "opening", "id": "full_height_opening",
  "parentWall": "living_room_wall",
  "from": [3.0, 0, 0],
  "width": 3.6, "height": 3.0, "style": "rectangular" },
{ "type": "window", "id": "full_height_win",
  "parentOpening": "full_height_opening",
  "sashType": "fixed", "material": "glass_tempered" },
{ "type": "railing", "id": "window_guardrail",
  "path": [ [3.0,0,0], [6.6,0,0] ],
  "height": 1.1, "infill": "glass" }
```

---

### X.3.5 窗-构件组装关系总表

<!-- rag-meta
entity_type: window
entity_name: window_component_matrix
topic: matrix
status: proposed
authority: domain_reference
keywords: 窗构件矩阵, window component matrix, opening, mullion
-->

**这张表是本章的核心产出**——按照 WILD 子构件组合方式，你将知道如何用底层组件拼出任何想要的窗型。

| 窗型 | opening.style | window.sashType | mullion.pattern | cornice | 子构件数 |
|:---|:---:|:---:|:---:|:---:|:---:|
| **直棂窗** | rectangular | fixed | vertical | — | 3 |
| **一码三箭** | rectangular | fixed | grid(cols=N,rows=3) | — | 3 |
| **槛窗** | rectangular | casement | grid/custom | — | 4(含槛墙) |
| **支摘窗** | rectangular×2 | awning+casement | grid×2 | — | 6 |
| **漏窗(花窗)** | rect/circular/扇形 | — | custom(冰裂纹/万字) | — | 2 |
| **空窗(洞窗)** | circular/扇形 | — | — | — | 1 |
| **菱花窗** | rectangular | fixed | custom(三交六椀) | — | 3 |
| **横披窗** | rectangular | fixed | — | — | 2 |
| **玫瑰窗** | circular | fixed | custom(放射) | — | 3 |
| **帕拉第奥窗** | arched+rect×2 | fixed×3 | vertical(分隔) | 拱顶石 | 8 |
| **尖拱窗(哥特)** | gothic | fixed | vertical+custom | — | 4 |
| **圆拱窗(罗马风)** | arched | fixed/casement | — | — | 2 |
| **柳叶窗** | gothic | fixed | — | — | 2 |
| **幕墙窗** | rectangular | awning(部分) | grid(均匀) | — | 3~N |
| **转角窗** | rect(两墙) | fixed | — | — | 4 |
| **条形窗** | rectangular(超长) | fixed | — | — | 2 |
| **天窗** | rect(parentRoof) | fixed/awning | — | — | 2 |
| **落地窗** | rect(高=层高) | fixed/casement | — | — | 3(含护栏) |

> **图例**：子构件数 = 该窗型所需的独立 WILD 构件数量（opening/mullion/window/cornice/wall/railing 各计 1）

---

### X.3.6 窗型与建筑类型速配

<!-- rag-meta
entity_type: window
entity_name: window_building_style_matrix
topic: matrix
status: proposed
authority: domain_reference
keywords: 窗型速配, window style, building type
-->

| 建筑类型 | 推荐窗型 | 说明 |
|:---|:---|:---|
| 现代别墅 | 条形窗 + 转角窗 + 落地窗 | 柯布西耶水平长窗 + 角部开敞 |
| 中式传统别墅 | 槛窗 + 支摘窗 + 漏窗 + 空窗 | 四合院立面 + 园林墙窗 |
| 新中式别墅 | 槛窗(简化棂) + 落地窗(大面积玻璃) | 传统符号 + 现代采光 |
| 住宅高层 | 推拉窗 + 内开内倒 | 经济实用+密封 |
| 办公超高层 | 幕墙窗(固定) + 上悬窗(通风) | 玻璃幕墙+个别可开启 |
| 学校 | 平开窗(外开) | 通风优先 |
| 商业综合体 | 幕墙窗 + 天窗 | 采光+品牌展示 |
| 体育场馆 | 中悬窗 + 天窗 | 大通风量 |
| 哥特教堂 | 玫瑰窗 + 尖拱窗 + 柳叶窗 | 垂直神性 + 彩色光 |
| 文艺复兴别墅 | 帕拉第奥窗 + 圆拱窗 | 古典秩序 |
| 苏州园林 | 漏窗(冰裂纹/万字纹) + 空窗(月洞) | 框景 + 借景 |
| 工业厂房 | 中悬窗 + 天窗(采光带) | 通风排烟 |

---

*本章节通过 X.1~X.3 完整定义了 WILD 中墙体、门、窗三大围护构件的**逐级分类**和**子构件组装规则**，是后续按建筑类型生成完整蓝图的基础。*

---
