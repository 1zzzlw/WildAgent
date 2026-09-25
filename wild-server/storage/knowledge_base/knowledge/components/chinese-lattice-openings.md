---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: component
entity_name: chinese_lattice_openings
topic: composition
status: supported
authority: engine
primary_terms:
  - 中式格棂门窗
  - 仿古门窗
  - 隔扇门
  - 格扇门
  - 套方纹
  - 回纹棂格
  - chinese lattice window
synonyms: []
applies_to:
  - 中式格棂门窗
  - 仿古门窗
  - 隔扇门
  - 回纹棂格
  - 套方纹棂格
---

# 中式格棂门窗（近似表达与能力边界）

适用条件：**用户或已批准方案显式点名**中式格棂、仿古门窗、隔扇门等构件变体时，才按本文档表达。
"中式建筑"这类风格词本身不触发本文档——不得因为建筑是中式风格就自动把普通门窗替换成格棂门窗；
风格与建筑类别不能替代对构件变体的显式选择。

视觉来源是一组仿古门窗立面图（双框深色木、方格棂条格心、套方/回纹装饰图案、门扇腰板与裙板分段）。
本文档只保留"当前引擎能写什么、不能写什么"，不收录风格百科。

## 中式格棂窗

<!-- rag-meta
entity_type: window
entity_name: chinese_lattice_window
topic: composition
primary_terms:
  - 中式格棂窗
  - 格心棂条
synonyms: []
-->

格心棂条用 `window` 的均匀等分棂格近似（`verticalMullions` / `horizontalMullions`，
编译器按等分比例生成棂条，有真实执行点）。深色木框用 `frameWidth` + `frameDepth` + `frameMaterial`。

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "window",
  "id": "window_lattice_1",
  "parentWall": "wall_front_l1",
  "from": [1.2, 0.9, 0],
  "width": 1.5,
  "height": 1.5,
  "verticalMullions": 4,
  "horizontalMullions": 5,
  "frameWidth": 0.09,
  "frameDepth": 0.12,
  "frameMaterial": "dark_wood",
  "glassMaterial": "glass"
}
```

- 棂格密度属于自由变量：传统格心棂条间距通常较密（约 0.10–0.15m 一格），这是领域参考值，
  不是引擎约束；`verticalMullions`/`horizontalMullions` 取值范围为 0–32 的整数。
- 图 4/5/8 一类的横直棂变体：减少单向棂条数量即可（如 `verticalMullions: 2` + `horizontalMullions: 7`），
  不需要额外字段。

**不能做**：

- ❌ 套方纹、回纹、步步锦等**装饰图案格心**。棂条只有均匀等分一种排布，
  Schema 没有图案定义字段，也没有对应编译器实现。禁止编造 `pattern`、`latticeStyle` 之类字段。
- ❌ 开启窗扇（窗是静态几何）。
- ❌ 圆形或异形窗洞。

**近似方式（downgraded）**：图案格心用较密的均匀棂格表达"格心密度"这一视觉特征；
图案语义丢失。用户要求精确还原图案时，明确告知该限制，不要假装已表达图案。

## 中式隔扇门

<!-- rag-meta
entity_type: door
entity_name: chinese_lattice_door
topic: composition
primary_terms:
  - 中式隔扇门
  - 双扇格门
synonyms: []
-->

单扇用 `doorStyle: "single"`，双扇用 `doorStyle: "double"`（双开 = 一个宽洞口 + 四段框，
无中框，有真实执行点）。深色木框同样用 `frameWidth`/`frameDepth`/`frameMaterial`。

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "door",
  "id": "door_lattice_main",
  "parentWall": "wall_front_l1",
  "from": [4.0, 0.0, 0],
  "width": 1.8,
  "height": 2.4,
  "doorStyle": "double",
  "openingStyle": "rectangular",
  "frameWidth": 0.1,
  "frameDepth": 0.14,
  "frameMaterial": "dark_wood",
  "leafMaterial": "dark_wood",
  "interaction": { "mode": "swing", "hingeSide": "left", "openAngle": 90 }
}
```

**不能做**：

- ❌ 门扇的**腰板 + 裙板分段**（图上隔扇门"上格心、中横板、下裙板"的三段式）。
  Schema 的门扇没有分段定义，扇体是整体几何；禁止编造 `leafSections`、`panelCount` 等字段。
- ❌ 四开门等多门扇（双开已由 `doorStyle: "double"` 支持，四开没有）。
- ❌ 门扇雕花、门钉等表面装饰。

**近似方式（downgraded）**：隔扇门的分段感只能靠"整扇深色木 + 格棂窗组合"间接暗示，
扇面本身没有分段。腰板、裙板的独立几何需要用户接受 `primitive` 近似时才显式构造，
且要声明这是近似而非隔扇门本体。

## 上下组合（固定上亮 / 裙窗）

图 5 一类"上双扇 + 下固定格心"的立面，用**两樘独立的 `window`** 表达：同一 `parentWall`、
同一水平范围、竖向范围不重叠。上亮与门组合时同理——门上亮子使用独立 `window`，
两者引用同一父墙并保持竖向范围不重叠；不能把窗挂在门生成的临时 `opening` 上。

检查：交付前确认同墙上的上下两樘 `window` 的 `from[1] + height` 与另一樘的 `from[1]` 不侵入。

## 与引擎能力文档的关系

门窗通用字段、交互与禁止字段（不使用 `style`/`leafCount`/`parentOpening`，不创建不存在的
`mullion` 类型等）以《引擎能力边界》的门、窗两节为准；本文档只补充"中式格棂变体"这一层
近似表达与专属边界，两处冲突时以 `schema.json` 与编译器实现为准。
