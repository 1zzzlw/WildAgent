---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: pavilion
entity_name: pavilion_garden_structure
topic: composition
status: supported
authority: maintainer
primary_terms:
  - 亭子
  - 四角亭
  - 凉亭
  - 水榭
  - 亭廊
  - 园林建筑
  - 六角亭
  - 八角亭
synonyms:
  - 亭
  - gazebo
  - pavilion
applies_to:
  - 亭子
  - 凉亭
  - 水榭
  - 园林建筑
  - 景观亭
---

# 亭与园林建筑的设计表达

适用于亭子、凉亭、水榭和亭廊的开敞空间。平面、层数、屋面和材料由本次需求决定；四角亭、圆亭、多层楼阁不能共用固定体量或构件配额。

## 设计与任务的交接

- 开敞面在对应体量的 `facades` 中写 `open`；`empty` 表示有墙而不开洞。需要围合的面按实际设计另设围护，不能把通透亭自动封成房子。
- `components` 逐项声明柱、梁架、台基及选用的顶饰、栏板或坐凳，写稳定 id、type、host、placement、size、form 和 description。仅写 structural_grid.system 或 concept 不会自动产生这些实体。
- 柱中心可直接写 `placement.position`；柱高和截面写 `size`。原生柱的 `base` 是柱底中心，不能把设计中心高度当柱底。
- 结构关系明确到柱顶、梁底/梁顶、屋面支承标高；低粒度可以简化线脚，不能把已选梁架省成屋顶直接搭在孤立柱上的另一套结构。
- 抬高台基时，用 `floor_layouts[].level` 声明地面顶面标高；台基中心与柱底、楼板底分别计算。
- 材料先在设计中作出明确选择：木、石、混凝土均可，但不能把“木或混凝土”作为尚未决定的方案。使用材质角色时写 `material_role`，并保留材料、颜色和表面表达。
- 坐凳、栏板、桌凳与宝顶都是独立设计内容，需由实际构件或 primitive 组合实现。低粒度不默认增加家具；用户指定参考中的这些内容时应保留。引擎不会从“亭”或某个 roofType 自动补出整套细部。

## 屋面形态与当前能力

| 设计形态 | WILD 表达与边界 |
|---|---|
| 四坡屋面 | 原生 `hip`；正方形 span/depth 的四坡汇于顶点，可表达简化四角攒尖。矩形时保留实际屋脊，不把它说成尖顶 |
| 双坡曲面屋顶 | `chinese_curved` 是沿一个轴展开的双坡曲面，不能用来冒充四坡攒尖；ridgeAxis 不能把它变成四个坡面 |
| 四坡翘角、复杂曲面 | 需要单独设计合法的组合几何，并核对四坡覆盖与转角衔接；原生 hip 不自动提供这种曲面，不能用文字声称已完成 |
| 圆形攒尖或多层重檐 | 按圆形或各层实际形制选择组合；参照圆台锥坡等局部知识，不照搬方形屋面 |

`roof.span` / `depth` 是世界 X/Z 的最终覆盖尺寸；除 `chinese_pagoda` 外，出檐由覆盖尺寸表达，不能再叠加无效的 eaveOutset。`position[1]` 为屋面支承标高。宝顶和檐下梁不能仅靠 roof 的名称派生。

## 四坡屋面、梁与宝顶的局部表达

<!-- rag-meta
entity_type: roof
entity_name: hip_roof
topic: composition
primary_terms:
  - 四坡屋顶
  - 四角攒尖
  - 庑殿屋顶
synonyms:
  - hip
  - hip roof
-->

下列是局部组装片段，elements 并入 `geometry.elements`，materials 并入材质字典；不是完整 `.wild` 或建筑模板。仅截取一根梁代表其字段写法，其余梁柱由当前图纸安排，不会自动补齐。本例柱顶应接梁底 2.88，梁顶为 3.12；屋面支承 3.12、顶点 4.22，宝顶基座与球相接。所有位置、尺寸、构件数量和材料均为可替换变量。
实施时只取当前标记负责的部分；若梁或宝顶已单列任务，屋面任务不复制这些实体。屋面下的斜梁按截面外包面留出净空，不能仅让中心线顶端贴住瓦面而使木料穿出。

```json
{
  "elements": [
    {"type":"beam","id":"eave_beam","from":[-1.5,3,-1.5],"to":[1.5,3,-1.5],"crossSection":"rect","width":0.18,"height":0.24,"material":"timber"},
    {"type":"roof","id":"hip_cover","roofType":"hip","span":3.8,"depth":3.8,"height":1.1,"thickness":0.1,"position":[0,3.12,0],"material":"tile"},
    {"type":"primitive","id":"finial_base","shape":"cylinder","position":[0,4.27,0],"radius":0.08,"height":0.1,"material":"tile"},
    {"type":"primitive","id":"finial_ball","shape":"sphere","position":[0,4.43,0],"radius":0.11,"material":"tile"}
  ],
  "components": [],
  "materials": {
    "timber":{"baseColor":[0.45,0.3,0.18],"roughness":0.6,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
    "tile":{"baseColor":[0.25,0.26,0.28],"roughness":0.85,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}
  }
}
```

来源：用户提供的《方胜亭·四角庑殿亭.wild》用于分件与材料参考，以上为重新计算的局部示例。能力核对依据为 `wild-core/schema.json` 及当前屋面重建实现；原生 hip 与双坡 chinese_curved 的区别已用同引擎真实渲染核对。本文不把参考建筑的尺寸、风格、家具数量或完整清单提升为默认要求。

## 宝顶的局部表达

<!-- rag-meta
entity_type: primitive
entity_name: roof_finial
topic: composition
primary_terms:
  - 宝顶
  - 屋顶顶饰
synonyms:
  - finial
-->

选用宝顶时，用独立构件标记声明尺寸、位置和材质；不能只把“宝顶”写进屋顶说明。以下为 geometry.elements 中的局部片段，假定屋面尖顶为 4.22，材质 tile 已存在；圆柱基座顶为 4.32，球底也为 4.32。屋面标高、顶饰尺寸和材料变化时共同换算这两个中心，不直接沿用示例。

```json
[
  {"type":"primitive","id":"finial_base","shape":"cylinder","position":[0,4.27,0],"radius":0.08,"height":0.1,"material":"tile"},
  {"type":"primitive","id":"finial_ball","shape":"sphere","position":[0,4.43,0],"radius":0.11,"material":"tile"}
]
```

## 坐凳与靠背的局部表达

<!-- rag-meta
entity_type: primitive
entity_name: garden_bench
topic: composition
primary_terms:
  - 园林坐凳
  - 坐凳
  - 美人靠
synonyms:
  - garden bench
-->

仅在本次设计选用坐凳时使用；与四面 open 的围护语义兼容，不额外建墙。凳面、支脚、背部横条和竖条分别表达；本例为直背简化组合，不声称实现曲面美人靠。放在所选边缘并留出入口净空，数量、方向与格栅密度由图纸决定。下列局部 elements 片段只演示一张直凳，材质 timber 已存在，地面顶为 0.3，凳面顶为 0.75，背顶为 1.1；竖条仅给一根写法，按实际设计计算其余位置。

```json
[
  {"type":"primitive","id":"bench_seat","shape":"box","position":[0,0.69,0],"dimensions":[1.8,0.12,0.4],"material":"timber"},
  {"type":"primitive","id":"bench_leg_l","shape":"box","position":[-0.72,0.465,0],"dimensions":[0.12,0.33,0.32],"material":"timber"},
  {"type":"primitive","id":"bench_leg_r","shape":"box","position":[0.72,0.465,0],"dimensions":[0.12,0.33,0.32],"material":"timber"},
  {"type":"primitive","id":"bench_post_l","shape":"box","position":[-0.85,0.925,0.16],"dimensions":[0.08,0.35,0.08],"material":"timber"},
  {"type":"primitive","id":"bench_post_r","shape":"box","position":[0.85,0.925,0.16],"dimensions":[0.08,0.35,0.08],"material":"timber"},
  {"type":"primitive","id":"bench_back_top","shape":"box","position":[0,1.075,0.16],"dimensions":[1.8,0.05,0.08],"material":"timber"},
  {"type":"primitive","id":"bench_back_bottom","shape":"box","position":[0,0.8,0.16],"dimensions":[1.8,0.05,0.08],"material":"timber"},
  {"type":"primitive","id":"bench_slat","shape":"box","position":[0,0.925,0.16],"dimensions":[0.04,0.25,0.04],"material":"timber"}
]
```

## 圆石桌的局部表达

<!-- rag-meta
entity_type: primitive
entity_name: stone_table
topic: composition
primary_terms:
  - 圆石桌
  - 石桌
synonyms:
  - stone table
-->

本次图纸选择圆石桌时，可用支脚圆柱与桌面圆柱组合，石凳另列实际标记。下列 geometry.elements 片段假定地面顶为 0.3，桌腿从 0.3 到 0.95，桌面底 0.95、顶 1.05；radius 是半径，height 是圆柱高度，position 是中心，不能用 box 的 dimensions 替代。材质 stone 已存在。桌径、桌高、台面厚度、位置和凳数均由当前需求决定。

```json
[
  {"type":"primitive","id":"table_support","shape":"cylinder","position":[0,0.625,0],"radius":0.15,"height":0.65,"material":"stone"},
  {"type":"primitive","id":"table_surface","shape":"cylinder","position":[0,1,0],"radius":0.45,"height":0.1,"material":"stone"}
]
```

## 石凳的局部表达

<!-- rag-meta
entity_type: primitive
entity_name: stone_stool
topic: composition
primary_terms:
  - 石凳
  - 圆凳
synonyms:
  - stone stool
-->

图纸选择石凳时，用一个独立标记表达一张凳子，位置与数量按桌边通行空间安排，不把示例固定复制四份。以下为 geometry.elements 的局部片段：地面顶 0.3，凳底 0.3、顶 0.7，材质 stone 已存在；直径、高度与材料按实际设计替换。

```json
[
  {"type":"primitive","id":"stone_stool","shape":"cylinder","position":[0,0.5,0],"radius":0.175,"height":0.4,"material":"stone"}
]
```

以上局部组合的分件来源均为同一份用户参考文件；坐凳支脚、局部尺寸与标高是本项目为可复用示例作的重新表达，不是原文件原样复制。它们只提供选定构件的字段与连接方法，不使任意亭子自动增加家具或装饰。
