---
entity_name: roof_facade_detail_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 屋面、老虎窗、壁柱与雨棚 JSON 示例
synonyms: []
---

# 屋面、老虎窗、壁柱与雨棚 JSON 示例

## 屋顶 · hip-roof

<!-- rag-meta
entity_type: roof
entity_name: hip_roof
topic: composition
primary_terms:
  - 屋顶
  - hip-roof
synonyms:
  - roof
-->

roof 是原生元素，这里展示四坡屋面落在宿主墙顶标高 3。position 是中心与支承标高，span/depth 为屋面覆盖尺寸，height 为屋面上表面从檐口到屋脊的高差。多体量按各体量独立覆盖，不把此矩形示例当整栋固定屋顶。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"floor","id":"body_slab","from":[-2,-0.18,-1.5],"to":[2,-0.18,1.5],"thickness":0.18,"material":"stone"},
      {"type":"wall","id":"front","from":[-2,0,-1.5],"to":[2,3,-1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"right","from":[2,0,-1.5],"to":[2,3,1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"back","from":[2,0,1.5],"to":[-2,3,1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"left","from":[-2,0,1.5],"to":[-2,3,-1.5],"thickness":0.24,"material":"plaster"},
      {"type":"roof","id":"main_roof","roofType":"hip","span":4.4,"depth":3.4,"height":0.8,"thickness":0.08,"position":[0,3,0],"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[RHEINZINK 屋面与建筑节点](https://www.rheinzink.com/products/architectural-details/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 单坡屋面 · shed-roof

<!-- rag-meta
entity_type: roof
entity_name: shed_roof
topic: composition
primary_terms:
  - 单坡屋顶
  - 单坡屋面
synonyms:
  - shed roof
  - mono pitch roof
-->

当前原生 `roofType` 没有 `shed`。单坡可以用一整片薄 `primitive.box` 配合 `rotation` 表达，而不是改成双坡，或只生成南北两条封檐块。`rotation` 是 XYZ 欧拉角弧度；绕 X 旋转时，屋面向 +Z 降低。设计的世界进深为 D 时，薄板局部进深取 `D / cos(angle)`，不能忽略旋转后的投影缩短。

以下仅为屋面安装片段：宿主体量 X[-2,2]、Z[-1.5,1.5]、墙顶3m；每边出檐0.2m，5°仅为本例取值。薄板上表面投影为4.4×3.4m。高侧墙顶至板底的填充、端面与檐下封闭须按当前主体设计补充，此片段不证明围护闭合。

```json
{
  "elements": [
    {"type":"primitive","id":"shed_surface","shape":"box","position":[0,3.228426304,-0.006972459],"rotation":[0.087266463,0,0],"dimensions":[4.4,0.16,3.412987448],"material":"metal_roof"}
  ],
  "components": [],
  "materials": {"metal_roof":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

字段与变换依据：`wild-core/schema.json::$defs.primitive`、`wild-core/src/primitive/geometry/primitive.ts::buildPrimitive`。示例尺寸与坡度为项目换算，不能作为所有屋顶的默认值。矩形体量的实现验收核对该标记所拥有实体的屋面投影并集及出檐；只返回封檐条会得到待修片段。

## 女儿墙 · parapet

<!-- rag-meta
entity_type: wall
entity_name: parapet
topic: composition
primary_terms:
  - 女儿墙
  - parapet
synonyms: []
-->

平屋面边沿采用两段相交的低 wall 与可选压顶。floor 底 2.82、厚 0.18，顶为 3；女儿墙底接 3。其高度、覆盖边数及压顶外挑留给图纸，不把示例高度当规范，也不自动补满未选的四边。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"floor","id":"roof_slab","from":[-2,2.82,0],"to":[2,2.82,2],"thickness":0.18,"material":"stone"},
      {"type":"wall","id":"parapet_front","from":[-2.0,3,0],"to":[2.0,3.9,0],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"parapet_side","from":[-2,3,0],"to":[-2,3.9,2],"thickness":0.24,"material":"plaster"},
      {"type":"primitive","id":"coping_front","shape":"box","position":[0,3.94,0],"dimensions":[4.1,0.08,0.34],"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[RHEINZINK 屋面与建筑节点](https://www.rheinzink.com/products/architectural-details/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 屋檐下悬 · eave-soffit

<!-- rag-meta
entity_type: roof
entity_name: eave_soffit
topic: composition
primary_terms:
  - 屋檐下悬
  - eave-soffit
synonyms:
  - soffit
  - 檐下封板
-->

这里按檐下封板及下挂封檐条解释“屋檐下悬”。封板只占墙外至屋面边缘的窄带，不以整块板堵住阁楼；示例展示前檐，其他边需要按本次覆盖关系补齐。若用户指悬挑构架，应按原图重新选构造，而不是仅改这个名称。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"floor","id":"body_slab","from":[-2,-0.18,-1.5],"to":[2,-0.18,1.5],"thickness":0.18,"material":"stone"},
      {"type":"wall","id":"front","from":[-2,0,-1.5],"to":[2,3,-1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"right","from":[2,0,-1.5],"to":[2,3,1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"back","from":[2,0,1.5],"to":[-2,3,1.5],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"left","from":[-2,0,1.5],"to":[-2,3,-1.5],"thickness":0.24,"material":"plaster"},
      {"type":"roof","id":"main_roof","roofType":"hip","span":4.4,"depth":3.4,"height":0.8,"thickness":0.08,"position":[0,3,0],"material":"metal"},
      {"type":"primitive","id":"front_soffit","shape":"box","position":[0,2.98,-1.6],"dimensions":[4.4,0.04,0.2],"material":"plaster"},
      {"type":"primitive","id":"front_fascia","shape":"box","position":[0,2.93,-1.68],"dimensions":[4.4,0.14,0.08],"material":"plaster"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[RHEINZINK 屋面与建筑节点](https://www.rheinzink.com/products/architectural-details/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 装饰檐口 · decorative-cornice

<!-- rag-meta
entity_type: cornice
entity_name: decorative_cornice
topic: composition
primary_terms:
  - 装饰檐口
  - decorative-cornice
synonyms: []
-->

截面线脚通过 cornice 沿墙顶扫掠表达，适合腰线或屋檐装饰。profile 是二维截面，path 是世界路径；改变走向时需检查截面朝向，转角共享端点。此阶梯形截面是自行简化的示例，不是 Melton 产品尺寸复刻，也不增加不存在的齿饰字段。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"cornice","id":"cornice","path":[[-2,3.2,0],[2,3.2,0]],"profile":[[0,0],[0.18,0],[0.18,0.08],[0.1,0.08],[0.1,0.18],[0,0.18]],"closedProfile":true,"material":"stone"}],
  "materials":{"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Melton 檐口线脚图纸目录](https://meltonclassics.com/products/cornices/fiberglass-cornices/designs/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 装饰壁柱 · decorative-pilaster

<!-- rag-meta
entity_type: column
entity_name: decorative_pilaster
topic: composition
primary_terms:
  - 装饰壁柱
  - decorative-pilaster
synonyms:
  - pilaster
  - 壁柱
-->

壁柱是贴墙的矩形浅浮雕，而非独立圆柱。使用 primitive.box 组合柱脚、柱身、柱头，后侧略嵌入墙面；若设计要槽纹可再组合细条。保留壁柱与 host_wall 的位置关系，不把没有的 parentWall 属性写进 primitive。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"},
      {"type":"primitive","id":"pilaster_base","shape":"box","position":[0,0.1,-0.16],"dimensions":[0.45,0.2,0.2],"material":"stone"},
      {"type":"primitive","id":"pilaster_shaft","shape":"box","position":[0,1.4,-0.15],"dimensions":[0.25,2.4,0.12],"material":"stone"},
      {"type":"primitive","id":"pilaster_cap","shape":"box","position":[0,2.68,-0.16],"dimensions":[0.5,0.16,0.25],"material":"stone"}
    ],
    "components":[],
  "materials":{"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Melton 门套、壁柱和上部饰件图](https://www.meltonclassics.com/files/melton-urethane-entry-systems.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 罗马柱 · roman-column

<!-- rag-meta
entity_type: column
entity_name: roman_column
topic: composition
primary_terms:
  - 罗马柱
  - roman-column
synonyms: []
-->

原生 column 放入 elements，用 base、height、上下半径和 style 描述独立柱。ionic 是当前支持的样式枚举；引擎为简化表达，不以 style 名称宣称历史柱式细部完全复原。需要额外柱头饰件时另用 primitive，柱高和柱数由本次方案决定。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"column","id":"roman_column","base":[0,0,0],"height":3,"bottomRadius":0.23,"topRadius":0.19,"style":"ionic","flutes":16,"entasis":0.015,"material":"stone"}
    ],
    "components":[],
  "materials":{"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Melton Roman Ionic 柱式与分件尺寸图](https://meltonclassics.com/products/architectural-columns/fiberglass-composite-columns/designs/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 老虎窗 · gable-dormer

<!-- rag-meta
entity_type: roof
entity_name: gable_dormer
topic: composition
primary_terms:
  - 老虎窗
  - gable-dormer
synonyms:
  - dormer
  - 屋面老虎窗
-->

老虎窗由凸出屋面的前窗、两侧围护和自身小屋顶组成，区别于直接嵌在坡面里的天窗。这里给出自选双坡造型，官方照片用于侧壁和屋面接口参考。原生主屋顶没有任意开孔字段：此独立样例没有主屋面；装到整栋时要按交线分块主屋面，不能直接叠在完整 hip/gable 屋面上。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"floor","id":"dormer_base","from":[-0.7,1.9,-0.7],"to":[0.7,1.9,0.7],"thickness":0.1,"material":"stone"},
      {"type":"wall","id":"dormer_front","from":[-0.7,2,-0.7],"to":[0.7,3.2,-0.7],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"dormer_left","from":[-0.7,2,-0.7],"to":[-0.7,3.2,0.7],"thickness":0.12,"material":"metal"},
      {"type":"wall","id":"dormer_right","from":[0.7,2,-0.7],"to":[0.7,3.2,0.7],"thickness":0.12,"material":"metal"},
      {"type":"roof","id":"dormer_roof","roofType":"gable","span":1.65,"depth":1.8,"height":0.5,"thickness":0.05,"position":[0,3.2,0],"material":"metal"}
    ],
    "components":[{"type":"window","id":"dormer_window","parentWall":"dormer_front","from":[0.25,2.2,0],"width":0.9,"height":0.9,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[RHEINZINK 老虎窗及屋面接口](https://www.rheinzink.com/products/architectural-details/dormer/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 雨棚构造 · framed-awning

<!-- rag-meta
entity_type: canopy
entity_name: framed_awning
topic: composition
primary_terms:
  - 雨棚构造
  - framed-awning
synonyms:
  - awning
  - 雨棚支承构造
-->

参考装配图保留透明顶板、两侧支承和墙连接的组合。顶板用 glass 材料，曲折支架用 profile_sweep；这组原语用世界坐标，不能套 canopy.from 的沿墙坐标。原图的精确曲率、密封件和螺栓被简化，安装需替换墙位置并同步支架末端与板底。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.1,0],"thickness":0.24,"material":"plaster"},
      {"type":"primitive","id":"awning_panel","shape":"box","position":[0,2.565,-0.62],"dimensions":[2.1,0.03,1],"material":"glass"},
      {"type":"primitive","id":"curved_bracket_0","shape":"profile_sweep","profile":[[-0.02,-0.02],[0.02,-0.02],[0.02,0.02],[-0.02,0.02]],"path":[[-0.75,1.9,-0.12],[-0.75,2.12,-0.3],[-0.75,2.35,-0.55],[-0.75,2.5,-0.85],[-0.75,2.55,-1.1]],"closedProfile":true,"material":"metal"},
      {"type":"primitive","id":"side_frame_0","shape":"box","position":[-0.75,2.575,-0.62],"dimensions":[0.04,0.08,1.04],"material":"metal"},
      {"type":"primitive","id":"curved_bracket_1","shape":"profile_sweep","profile":[[-0.02,-0.02],[0.02,-0.02],[0.02,0.02],[-0.02,0.02]],"path":[[0.75,1.9,-0.12],[0.75,2.12,-0.3],[0.75,2.35,-0.55],[0.75,2.5,-0.85],[0.75,2.55,-1.1]],"closedProfile":true,"material":"metal"},
      {"type":"primitive","id":"side_frame_1","shape":"box","position":[0.75,2.575,-0.62],"dimensions":[0.04,0.08,1.04],"material":"metal"}
    ],
    "components":[],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Canopia Aquila 雨棚组装图](https://canopia.com/app/uploads/2022/03/600483_Palram-Canopia_Door-Awnings_Aquila_1x2_3x7_Assembly-Instructions.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
