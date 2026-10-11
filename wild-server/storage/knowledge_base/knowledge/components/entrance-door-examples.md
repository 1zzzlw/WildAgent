---
entity_name: entrance_door_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 门斗、庭院门与车库门 JSON 示例
synonyms: []
---

# 门斗、庭院门与车库门 JSON 示例

## 侧门 · side-door

<!-- rag-meta
entity_type: door
entity_name: side_door
topic: composition
primary_terms:
  - 侧门
  - side-door
synonyms: []
-->

侧门是单扇 door 的安装位置选择。复用真正宿主墙和沿墙起点，不自动生成旁边的小窗；interaction 提供侧铰平开语义。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"door","id":"sample_door","parentWall":"host_wall","from":[1.525,0,0],"width":0.95,"height":2.1,"frameMaterial":"metal","leafMaterial":"wood","interaction":{"mode":"swing","hingeSide":"left","openAngle":80}}],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 储藏间门 · storage-door

<!-- rag-meta
entity_type: door
entity_name: storage_door
topic: composition
primary_terms:
  - 储藏间门
  - storage-door
synonyms: []
-->

储藏间门仍是 door，尺寸、门扇材料与铰链侧按本次空间决定。此示例不附带不存在的储藏间房间结构，安装时替换为本次室内墙宿主。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"door","id":"sample_door","parentWall":"host_wall","from":[1.6,0,0],"width":0.8,"height":2.0,"frameMaterial":"metal","leafMaterial":"wood","interaction":{"mode":"swing","hingeSide":"right","openAngle":70}}],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 大面积玻璃移门 · glass-sliding-door

<!-- rag-meta
entity_type: door
entity_name: glass_sliding_door
topic: composition
primary_terms:
  - 大面积玻璃移门
  - glass-sliding-door
synonyms:
  - glass sliding door
  - 大面积玻璃推拉门
-->

玻璃移门使用 doorStyle=double、玻璃门扇材料和 slide。滑移示例不表示多轨折叠或完全收入墙内；将门旁滑移空间、玻璃和框料一起核对。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"door","id":"sample_door","parentWall":"host_wall","from":[0.5,0,0],"width":3,"height":2.4,"frameMaterial":"metal","leafMaterial":"glass","doorStyle":"double","leafRows":1,"interaction":{"mode":"slide","openDistance":1.3}}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 车库门 · sectional-garage-door

<!-- rag-meta
entity_type: door
entity_name: sectional_garage_door
topic: composition
primary_terms:
  - 车库门
  - sectional-garage-door
synonyms:
  - garage door
  - 分节车库门
-->

保留分节门面及提升语义。当前 lift 把门扇整体竖直上移，不沿 Hörmann 的弯曲轨道逐节翻转；不能用示例宣称真实分节轨道仿真。宿主高 4.6 为提升留出净空，不把该高度推广到所有车库。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,4.6,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"door","id":"sample_door","parentWall":"host_wall","from":[0.5,0,0],"width":3,"height":2.2,"frameMaterial":"metal","leafMaterial":"metal","leafRows":5,"interaction":{"mode":"lift","openDistance":2.2}}],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Hörmann 分节车库门与安装剖面](https://www.hoermann.com/fileadmin/_country/kataloge/pdf/86_912-Sectional_Garage_Doors_-0518-EN-UK.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 主入口门斗 · entrance-vestibule

<!-- rag-meta
entity_type: door
entity_name: entrance_vestibule
topic: composition
primary_terms:
  - 主入口门斗
  - entrance-vestibule
synonyms:
  - entry vestibule
  - 入口门斗
-->

门斗是有深度的入口空间，不能只画装饰门套。示例包含前后两道门、侧壁、楼板和顶盖；若本次只要开放门廊，应删去前道门和相应围护并重新设计，不机械保留封闭门斗。此空间组合是本项目示例设计，来源仅用于门窗和门套分件参考。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"inner_wall","from":[-1.7,0,0],"to":[1.7,2.8,0],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"outer_wall","from":[-1.7,0,-1.5],"to":[1.7,2.8,-1.5],"thickness":0.24,"material":"plaster"},
      {"type":"floor","id":"vestibule_slab","from":[-1.7,-0.15,-1.5],"to":[1.7,-0.15,0],"thickness":0.15,"material":"stone"},
      {"type":"primitive","id":"vestibule_roof","shape":"box","position":[0,2.9,-0.75],"dimensions":[3.6,0.2,1.7],"material":"stone"},
      {"type":"wall","id":"left_wall","from":[-1.7,0,-1.5],"to":[-1.7,2.8,0],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"right_wall","from":[1.7,0,-1.5],"to":[1.7,2.8,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"door","id":"inner_door","parentWall":"inner_wall","from":[0.9,0,0],"width":1.6,"height":2.35,"frameMaterial":"metal","leafMaterial":"wood","doorStyle":"double","interaction":{"mode":"swing","hingeSide":"left","openAngle":75}},{"type":"door","id":"outer_door","parentWall":"outer_wall","from":[0.8,0,0],"width":1.8,"height":2.35,"frameMaterial":"metal","leafMaterial":"wood","doorStyle":"double","interaction":{"mode":"swing","hingeSide":"right","openAngle":75}},{"type":"window","id":"side_light","parentWall":"left_wall","from":[0.25,0.5,0],"width":0.95,"height":1.9,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)；[Melton 门套、壁柱和上部饰件图](https://www.meltonclassics.com/files/melton-urethane-entry-systems.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 庭院门 · garden-gate

<!-- rag-meta
entity_type: door
entity_name: garden_gate
topic: composition
primary_terms:
  - 庭院门
  - garden-gate
synonyms: []
-->

用两座门柱、两组边框与竖条表达静态镂空庭院门，保留两扇间缝隙。primitive 组合没有自动铰链或 door 交互；若要交互可改原生 door 并说明其实体门扇与镂空造型的差别。这里不复制来源产品的尺寸或规范声明。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"pier_left","shape":"box","position":[-1.65,0.95,0],"dimensions":[0.3,1.9,0.3],"material":"stone"},
      {"type":"primitive","id":"pier_right","shape":"box","position":[1.65,0.95,0],"dimensions":[0.3,1.9,0.3],"material":"stone"},
      {"type":"primitive","id":"gate_0_rail_0.15","shape":"box","position":[-0.725,0.15,0],"dimensions":[1.42,0.045,0.05],"material":"metal"},
      {"type":"primitive","id":"gate_0_rail_1.65","shape":"box","position":[-0.725,1.65,0],"dimensions":[1.42,0.045,0.05],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_0","shape":"box","position":[-1.325,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_1","shape":"box","position":[-1.125,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_2","shape":"box","position":[-0.9249999999999999,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_3","shape":"box","position":[-0.7249999999999999,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_4","shape":"box","position":[-0.5249999999999999,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_5","shape":"box","position":[-0.32499999999999996,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_0_bar_6","shape":"box","position":[-0.12499999999999978,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_rail_0.15","shape":"box","position":[0.725,0.15,0],"dimensions":[1.42,0.045,0.05],"material":"metal"},
      {"type":"primitive","id":"gate_1_rail_1.65","shape":"box","position":[0.725,1.65,0],"dimensions":[1.42,0.045,0.05],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_0","shape":"box","position":[0.125,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_1","shape":"box","position":[0.325,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_2","shape":"box","position":[0.525,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_3","shape":"box","position":[0.7250000000000001,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_4","shape":"box","position":[0.925,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_5","shape":"box","position":[1.125,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"},
      {"type":"primitive","id":"gate_1_bar_6","shape":"box","position":[1.3250000000000002,0.9,0],"dimensions":[0.025,1.5,0.025],"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[King Metals 双端卷花栏杆构件](https://www.kingmetals.com/ECItemMainPage.aspx?ItemId=ITM-10273550)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
