---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: component
entity_name: window_variants
topic: composition
status: supported
authority: engine
primary_terms:
  - 拱形窗
  - 百叶窗
  - 多扇组合窗
  - 上亮窗
  - 扇形拱顶窗
  - arched window
  - louvered window
synonyms: []
applies_to:
  - 拱形窗
  - 百叶窗
  - 多扇组合窗
  - 上亮窗
  - 圆形窗
---

# 窗样式变体（拱形、百叶与多扇组合）

适用条件：**用户或已批准方案显式点名**拱形窗、百叶窗、多扇组合窗、上亮窗等窗样式变体时，
才按本文档表达；普通平开窗不需要引用本文。"欧式建筑"这类风格词本身不触发本文档。

上下组合（上亮 / 裙窗：同墙两樘 `window` 竖向不重叠）的完整规则与检查点见《中式格棂门窗》的
"上下组合"小节，本档不重复；本文档只写该档没有的水平并排组合。

## 拱形窗

<!-- rag-meta
entity_type: window
entity_name: arched_window
topic: composition
primary_terms:
  - 拱形窗
  - 半圆拱窗
  - 尖拱窗
synonyms: []
-->

`window` 组件本身只有矩形洞（没有 `openingStyle` 字段），**不能**把窗写成拱形，
也不要借 `door` 的 `openingStyle: "arched"` 表达拱形窗（语义错位）。非矩形洞形由 **`opening` 元素**
表达：`style` 支持 `rectangular` / `arched`（半圆拱）/ `gothic`（尖拱）/ `circular`（圆）。

🔴 **必须向用户声明的引擎事实**：`arched` / `gothic` / `circular` 只是 opening 元素自身的
**覆盖棱柱**造型（墙体开洞在引擎里只有矩形通孔一种，见 `box-with-holes.ts`）。
即"拱形窗" = 矩形墙洞 + 洞内的拱形玻璃棱柱；斜视角能看到矩形洞口的内壁转角，
不是把墙真切成拱洞。

拱形窗 = `opening`（拱形覆盖棱柱，材质直接给玻璃）即可，**不要再叠加矩形玻璃盒**——
覆盖棱柱已填充洞口，再放盒体会双层玻璃重叠（下层发暗）。

以下是 `geometry.elements` 数组中的组合片段，不是完整 `.wild` 文件：

```json
{
  "type": "opening",
  "id": "opening_arch_1",
  "parentWall": "wall_front_l1",
  "from": [2.0, 1.2, 0],
  "width": 1.0,
  "height": 1.58,
  "style": "arched",
  "depth": 0.24,
  "material": "glass"
}
```

- 拱顶内的放射分格、扇形（fanlight）分格、方格分格都**没有对应字段**，棂条细节不可表达。
- 矩形 `window` 是更简单的降级：真窗框 + 真分格，但轮廓是矩形。用户在意拱形轮廓且接受
  "面板近似、斜角见矩形洞壁"时用 `opening`；在意窗体完整度时用矩形 `window`，二选一并说明取舍。

## 百叶窗

<!-- rag-meta
entity_type: window
entity_name: louvered_window
topic: composition
primary_terms:
  - 百叶窗
  - 活动百叶
synonyms: []
-->

Schema 没有百叶字段，也没有百叶叶片几何。视觉近似方式：用密集的横向棂条
（`horizontalMullions` 取较大值）模拟百叶的水平线条。

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "window",
  "id": "window_louver_1",
  "parentWall": "wall_front_l1",
  "from": [3.2, 1.2, 0],
  "width": 1.0,
  "height": 1.58,
  "horizontalMullions": 10,
  "frameWidth": 0.08,
  "frameDepth": 0.1,
  "frameMaterial": "dark_wood",
  "glassMaterial": "glass"
}
```

**语义差异（downgraded）**：棂条是矩形截面框料，不是可调角度的百叶叶片；没有通风、
遮阳语义。用户问"能否开合百叶"时，明确回答不支持，不要把 `horizontalMullions` 说成百叶功能。

## 多扇组合窗（水平并排）

<!-- rag-meta
entity_type: window
entity_name: combination_window
topic: composition
primary_terms:
  - 多扇组合窗
  - 三扇窗
  - 四扇窗
  - 固定扇
synonyms: []
-->

宽洞口的分扇（两扇对开、三扇、四扇，中间固定两侧开扇等）用**同墙多樘 `window` 水平并排**
表达：把总宽按扇宽切分，每樘一个 `window`，`from[0]` 依次排布，竖向范围一致。
玻璃幕墙系统的整面分格走幕墙装配文档，不使用本规则；本规则用于普通墙面上的少量分扇。

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
[
  { "type": "window", "id": "window_combo_1", "parentWall": "wall_front_l1",
    "from": [1.0, 0.9, 0], "width": 0.6, "height": 1.58, "verticalMullions": 1 },
  { "type": "window", "id": "window_combo_2", "parentWall": "wall_front_l1",
    "from": [1.6, 0.9, 0], "width": 0.8, "height": 1.58 },
  { "type": "window", "id": "window_combo_3", "parentWall": "wall_front_l1",
    "from": [2.4, 0.9, 0], "width": 0.6, "height": 1.58, "verticalMullions": 1 }
]
```

- 扇宽、开扇与固定扇的分布是自由变量，由本次方案决定；示例数值仅解释字段。
- 相邻窗之间留出墙垛或梃位宽度时，直接体现在各 `from[0]` 与 `width` 的切分上；
  不要让相邻窗的洞口重叠。
- 上下叠用两行（`from[1]` 与 `height` 切分），规则同上，检查点见《中式格棂门窗》"上下组合"。

## 能力边界汇总

- 🟡 拱形 `window`：window 组件只有矩形洞；拱形轮廓用 `opening`（`arched`/`gothic`/`circular`）
  覆盖棱柱近似——**墙体开洞只有矩形**（引擎 `box-with-holes.ts` 只切矩形通孔），
  斜视角可见矩形洞内壁转角；opening 材质给玻璃即可，不要再叠玻璃盒。
- ❌ 拱顶放射格、扇形分格：无字段，棂条图案不可表达。
- ❌ 真百叶：无叶片几何与通风语义，只能横向密棂近似。
- ❌ 窗扇开启：窗是静态几何（门的开合交互不适用于窗）。
- ✅ 均匀棂格（田字格、横直棂）：`verticalMullions` / `horizontalMullions` 直接表达。
- ✅ 多扇并排与上下组合：同墙多樘 `window` 切分表达。
