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
编译器按等分比例生成棂条）。外框用 `frameWidth` + `frameDepth` + `frameMaterial`，棂条另用 `mullionWidth` 指定宽度。
`frameWidth` 是外框宽度，不能拿它当密集棂条的宽度；缺省棂条宽度为 `min(frameWidth, 0.02)` 米。

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
  "mullionWidth": 0.02,
  "frameDepth": 0.12,
  "frameMaterial": "dark_wood",
  "glassMaterial": "glass"
}
```

- 棂格密度与棂条宽度属于自由变量；`verticalMullions`/`horizontalMullions` 取值范围为 0–32 的整数。
  水平净宽为 `width - 2*frameWidth`，竖向净高为 `height - 2*frameWidth`；等分后棂条宽度必须小于相邻棂条中心间距。
  例如宽 1.8m、外框 0.09m、15 根竖棂时中心间距为 1.62/16=0.10125m；棂条若也宽 0.09m，玻璃几乎被遮住。
  用独立的 0.02m 棂条可以保留透光格心；这是参数示例，不规定设计密度。交互双扇窗另有中央竖梃，也要保留净空。
- 图 4/5/8 一类的横直棂变体：减少单向棂条数量即可（如 `verticalMullions: 2` + `horizontalMullions: 7`），
  不需要额外字段。

窗外独立格栅应保留真实 `window` 洞口，格栅的外框由四条边框组成。整块木色 `box` 即使命名为 frame，仍是实心板，会把玻璃全部遮住；不能用它当镂空框。下面是局部安装片段，已有宿主时复用墙 ID，不重复添加墙。

```json
{
  "elements": [
    {"type":"wall","id":"host","from":[0,0,0],"to":[4,3.2,0],"thickness":0.24},
    {"type":"primitive","id":"lattice_left","shape":"box","position":[0.66,1.65,-0.16],"dimensions":[0.06,1.62,0.04],"material":"dark_wood"},
    {"type":"primitive","id":"lattice_right","shape":"box","position":[2.34,1.65,-0.16],"dimensions":[0.06,1.62,0.04],"material":"dark_wood"},
    {"type":"primitive","id":"lattice_top","shape":"box","position":[1.5,2.43,-0.16],"dimensions":[1.62,0.06,0.04],"material":"dark_wood"},
    {"type":"primitive","id":"lattice_bottom","shape":"box","position":[1.5,0.87,-0.16],"dimensions":[1.62,0.06,0.04],"material":"dark_wood"},
    {"type":"primitive","id":"lattice_bar","shape":"box","position":[1.5,1.65,-0.16],"dimensions":[0.03,1.5,0.04],"material":"dark_wood"}
  ],
  "components": [
    {"type":"window","id":"glazed_opening","parentWall":"host","from":[0.6,0.9,0],"width":1.8,"height":1.5,"frameWidth":0.06,"frameDepth":0.08,"frameMaterial":"dark_wood","glassMaterial":"glass"}
  ],
  "materials": {"dark_wood":{"baseColor":[0.2,0.12,0.08],"roughness":0.6,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"glass":{"baseColor":[0.75,0.85,0.9],"roughness":0.05,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92}}
}
```

本例是现有 WILD 字段与实际窗洞安装的项目映射，不是外部规范。条数、间距和尺寸随图纸调整；实心板遮满窗洞的检查由 `app/design/relations.py::opening_design_errors` 执行，适用直轴墙与未旋转 box，不证明任意格栅形态的透光率。

**不能做**：

- 不支持：套方纹、回纹、步步锦等**装饰图案格心**。棂条只有均匀等分一种排布，
  Schema 没有图案定义字段，也没有对应编译器实现。禁止编造 `pattern`、`latticeStyle` 之类字段。
- 开启窗扇由 `interaction` 支持，省略时为固定窗。
- 不支持：圆形或异形窗洞。

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

- 不支持：门扇的**腰板 + 裙板分段**（图上隔扇门"上格心、中横板、下裙板"的三段式）。
  Schema 的门扇没有分段定义，扇体是整体几何；禁止编造 `leafSections`、`panelCount` 等字段。
- 不支持：四开门等多门扇（双开已由 `doorStyle: "double"` 支持，四开没有）。
- 不支持：门扇雕花、门钉等表面装饰。

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
