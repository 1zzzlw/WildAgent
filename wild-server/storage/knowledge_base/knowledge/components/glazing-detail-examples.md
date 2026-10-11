---
entity_name: glazing_detail_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 玻璃窗、开启扇与凸窗 JSON 示例
synonyms: []
---

# 玻璃窗、开启扇与凸窗 JSON 示例

## 落地窗 · floor-window

<!-- rag-meta
entity_type: window
entity_name: floor_window
topic: composition
primary_terms:
  - 落地窗
  - floor-window
synonyms:
  - floor-to-ceiling window
  - full-height glazing
-->

低窗台、大玻璃与外围窗框构成落地窗。示例窗底为 0.15，可按真实门槛改为其他值；窗是 window，不能因落地就自动当门。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[0.8,0.15,0],"width":2.4,"height":2.8,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 通高窗 · double-height-window

<!-- rag-meta
entity_type: window
entity_name: double_height_window
topic: composition
primary_terms:
  - 通高窗
  - double-height-window
synonyms:
  - double-height window
  - 通高玻璃窗
-->

通高由宿主与开口的实际高度表达。示例整段高墙承载高窗，中部横梃只是分格；不能以多层重合 window 冒充一个连续开口。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,6.4,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[0.8,0.2,0],"width":2.4,"height":5.8,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass","verticalMullions":1,"horizontalMullions":1}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 开启扇 · operable-sash

<!-- rag-meta
entity_type: window
entity_name: operable_sash
topic: composition
primary_terms:
  - 开启扇
  - operable-sash
synonyms:
  - operable window sash
  - 开启窗扇
-->

开启语义使用 interaction，而不是新增 sash 类型。当前 window 交互编译会创建左右两扇；不能称作精确的单扇产品复制。开启角是示例取值。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[1.3,0.9,0],"width":1.4,"height":1.5,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass","interaction":{"mode":"swing","hingeSide":"left","openAngle":55}}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 固定玻璃 · fixed-glazing

<!-- rag-meta
entity_type: window
entity_name: fixed_glazing
topic: composition
primary_terms:
  - 固定玻璃
  - fixed-glazing
synonyms:
  - fixed glass
  - 固定玻璃窗
-->

固定玻璃用不带 interaction 的 window。外围框和玻璃深度由宿主厚度内的默认值承担；无交互表示固定窗，不能附加虚构的 fixed 字段。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[1.1,0.9,0],"width":1.8,"height":1.6,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 小窗 · small-window

<!-- rag-meta
entity_type: window
entity_name: small_window
topic: composition
primary_terms:
  - 小窗
  - small-window
synonyms: []
-->

小窗只调整 opening 的尺寸和窗台，不形成新类型。保留真实宿主、框及玻璃，参数仍需放在墙长和墙高以内；小窗尺寸是示例，不是通用下限。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[1.675,1.2,0],"width":0.65,"height":0.8,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 高窗 · high-window

<!-- rag-meta
entity_type: window
entity_name: high_window
topic: composition
primary_terms:
  - 高窗
  - high-window
synonyms:
  - clerestory window
-->

高窗指较高的窗底标高，不等于窗体很高。from[1] 为世界窗底，height 为开口高度；应同步调整宿主高度，不能把世界 X 误写进 from[0]。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[1.3,2.25,0],"width":1.4,"height":0.55,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 落地窗组 · floor-window-group

<!-- rag-meta
entity_type: window
entity_name: floor_window_group
topic: composition
primary_terms:
  - 落地窗组
  - floor-window-group
synonyms:
  - floor-to-ceiling window group
-->

这是一组等分玻璃的最小用法：一个 window 用两条竖梃得到三格。若需不同开启方式或不等宽扇，拆成多个互不重叠的 window，并保留各自沿墙坐标。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"window","id":"sample_window","parentWall":"host_wall","from":[0.4,0.2,0],"width":3.2,"height":2.7,"frameWidth":0.05,"frameMaterial":"metal","glassMaterial":"glass","verticalMullions":2}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 门窗立面与节点资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 凸窗 · bay-window

<!-- rag-meta
entity_type: bay_window
entity_name: bay_window
topic: composition
primary_terms:
  - 凸窗
  - bay-window
synonyms: []
-->

参考图的前窗、侧窗及上下平台保留为凸窗的分件意识。当前 bay_window 为矩形外挑盒式窗体，projectionDepth 是外挑深度；不声称复现原图 30°／45° 的斜侧窗。该斜角造型需改用多个墙窗或 primitive。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.2,0],"thickness":0.24,"material":"plaster"}
    ],
    "components":[{"type":"bay_window","id":"bay","parentWall":"host_wall","from":[0.8,0.8,0],"width":2.4,"height":1.7,"projectionDepth":0.65,"frameWidth":0.06,"frameMaterial":"metal","glassMaterial":"glass"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Andersen 30°／45° 凸窗组装图](https://www.andersenwindows.com/-/media/Project/AndersenCorporation/AndersenWindows/AndersenWindows/files/technical-docs/installation-guide/installationguide-0005132.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
