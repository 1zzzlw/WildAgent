---
entity_name: envelope_detail_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 墙体、基座与围墙接口 JSON 示例
synonyms: []
---

# 墙体、基座与围墙接口 JSON 示例

## 建筑主体 · building-body

<!-- rag-meta
entity_type: component
entity_name: building_body
topic: composition
primary_terms:
  - 建筑主体
  - building-body
synonyms:
  - building_body
  - 主体骨架
  - building body
  - main building body
-->

这是宿主骨架示例，不是别墅设计模板。楼板底标高 -0.18、厚 0.18，板顶为 0；四面 wall 接到标高 3。替换各端点和材料即可表达本次体量，不能自动加窗、屋顶或固定层数。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"floor","id":"body_slab","from":[-2,-0.18,-1.5],"to":[2,-0.18,1.5],"thickness":0.18,"material":"stone"},
      {"type":"wall","id":"front","from":[-2,0,-1.5],"to":[2,3,-1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"right","from":[2,0,-1.5],"to":[2,3,1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"back","from":[2,0,1.5],"to":[-2,3,1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"left","from":[-2,0,1.5],"to":[-2,3,-1.5],"thickness":0.24,"material":"plaster"}
    ],
    "components":[],
  "materials":{"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[CMHA 砌体基础详图](https://www.cmha.org/resource/tek-05-03a/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 实墙基座 · solid-base

<!-- rag-meta
entity_type: wall
entity_name: solid_base
topic: composition
primary_terms:
  - 实墙基座
  - solid-base
synonyms:
  - 墙体基座
  - solid wall base
-->

保留基础底座、基座墙与顶面压盖的分层表达。示例仅显示外观；墙宽、厚度、基座高度和压盖外挑可改，不从参考图移植承载或配筋要求。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"footing","shape":"box","position":[0,-0.175,0],"dimensions":[4.8,0.35,0.75],"material":"stone"},
      {"type":"wall","id":"host_wall","from":[-2.2,0,0],"to":[2.2,0.65,0],"thickness":0.24,"material":"stone"},
      {"type":"primitive","id":"base_cap","shape":"box","position":[0,0.69,0],"dimensions":[4.6,0.08,0.55],"material":"stone"}
    ],
    "components":[],
  "materials":{"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[CMHA 砌体基础详图](https://www.cmha.org/resource/tek-05-03a/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 实墙 · solid-wall

<!-- rag-meta
entity_type: wall
entity_name: solid_wall
topic: composition
primary_terms:
  - 实墙
  - solid-wall
synonyms:
  - 实体墙
  - solid wall
-->

实墙、实体墙属于同一原生 wall 用法，不因名称不同重复建模。from/to 同时表达水平端点及底顶标高，thickness 为墙厚；出现开口时另用宿主开口组件，不把窗形装饰贴在整块实墙上。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[],
  "materials":{"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[CMHA 砌体基础详图](https://www.cmha.org/resource/tek-05-03a/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 景观矮墙 · landscape-low-wall

<!-- rag-meta
entity_type: wall
entity_name: landscape_low_wall
topic: composition
primary_terms:
  - 景观矮墙
  - landscape-low-wall
synonyms: []
-->

用低 wall 和略外挑的顶盖表达矮墙。压顶底面与墙顶相接；端部、转角或分段高度依据本次设计调整。该 JSON 没有挡土计算或地下排水系统。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-1.5,0,0],"to":[1.5,0.6,0],"thickness":0.24,"material":"stone"},
      {"type":"primitive","id":"cap","shape":"box","position":[0,0.64,0],"dimensions":[3.1,0.08,0.35],"material":"stone"}
    ],
    "components":[],
  "materials":{"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Allan Block 墙顶、端部和转角](https://allanblock.com/installation/commercial-installation/finishing-retaining-walls)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 庭院围墙接口 · garden-wall-junction

<!-- rag-meta
entity_type: wall
entity_name: garden_wall_junction
topic: composition
primary_terms:
  - 庭院围墙接口
  - garden-wall-junction
synonyms: []
-->

这里的接口是两段围墙的端点及压顶关系，不是新增 WILD 类型。转角共享水平端点 [0,0,0]，高低墙可以独立取高度；接已有建筑时替换墙端点和材质，不自动复制第二面重合墙。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"wall_a","from":[0,0,-1.5],"to":[0,2,0],"thickness":0.24,"material":"stone"},
      {"type":"wall","id":"wall_b","from":[0,0,0],"to":[2,1,0],"thickness":0.24,"material":"stone"},
      {"type":"primitive","id":"cap_b","shape":"box","position":[1,1.04,0],"dimensions":[2,0.08,0.34],"material":"stone"}
    ],
    "components":[],
  "materials":{"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Allan Block 墙顶、端部和转角](https://allanblock.com/installation/commercial-installation/finishing-retaining-walls)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
