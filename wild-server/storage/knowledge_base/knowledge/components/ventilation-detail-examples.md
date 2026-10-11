---
entity_name: ventilation_detail_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 固定百叶叶片与排风口 JSON 示例
synonyms: []
---

# 固定百叶叶片与排风口 JSON 示例

## 通风百叶 · ventilation-louvre

<!-- rag-meta
entity_type: window
entity_name: ventilation_louvre
topic: composition
primary_terms:
  - 通风百叶
  - ventilation-louvre
synonyms:
  - 百叶叶片
  - ventilation louver
  - 通风百叶构造
  - 设备百叶
-->

TROX 图纸的边框与倾斜叶片保留为独立几何，不用窗棂冒充叶片。此模块用 primitive.box 旋转出八片固定叶片；rotation 为弧度。数量、间距、倾角和框深可改。安装示例包含真实墙洞；没有通风计算、叶片联动或防雨认证。
沿墙安装时，以图纸 offset/sill_height 和宽高设置 opening，再把叶片与边框按真实宿主方向换算到世界坐标；
不能只把这一独立叶片示例贴到实墙上，遮阳格栅则围绕已有窗洞布置，避免重复切洞或叠加玻璃。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2,0,0],"to":[2,3.2,0],"thickness":0.24},
      {"type":"opening","id":"vent_hole","parentWall":"host_wall","from":[1.4,1,0],"width":1.2,"height":1,"style":"rectangular"},
      {"type":"primitive","id":"top","shape":"box","position":[0,2,-0.14],"dimensions":[1.2,0.05,0.18],"material":"metal"},
      {"type":"primitive","id":"bottom","shape":"box","position":[0,1,-0.14],"dimensions":[1.2,0.05,0.18],"material":"metal"},
      {"type":"primitive","id":"left","shape":"box","position":[-0.575,1.5,-0.14],"dimensions":[0.05,1,0.18],"material":"metal"},
      {"type":"primitive","id":"right","shape":"box","position":[0.575,1.5,-0.14],"dimensions":[0.05,1,0.18],"material":"metal"},
      {"type":"primitive","id":"blade_0","shape":"box","position":[0,1.105,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_1","shape":"box","position":[0,1.215,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_2","shape":"box","position":[0,1.325,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_3","shape":"box","position":[0,1.435,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_4","shape":"box","position":[0,1.545,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_5","shape":"box","position":[0,1.655,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_6","shape":"box","position":[0,1.7650000000000001,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_7","shape":"box","position":[0,1.875,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[TROX WG 外墙通风百叶构造](https://www.troxuk.co.uk/external-weather-louvres/wg-3a5581e60ae1533b)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 排风口 · exhaust-outlet

<!-- rag-meta
entity_type: component
entity_name: exhaust_outlet
topic: composition
primary_terms:
  - 排风口
  - exhaust-outlet
synonyms:
  - exhaust vent
  - 排气口
-->

排风口复用边框及固定百叶，后方圆筒只显示短管外形；cylinder 不是空心风管。示例包含矩形墙洞；接外墙或设备平台时按实际接口定位，不能靠把模块贴在未开孔的实墙上宣称通风已连通。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2,0,0],"to":[2,3.2,0],"thickness":0.24},
      {"type":"opening","id":"vent_hole","parentWall":"host_wall","from":[1.4,1,0],"width":1.2,"height":1,"style":"rectangular"},
      {"type":"primitive","id":"top","shape":"box","position":[0,2,-0.14],"dimensions":[1.2,0.05,0.18],"material":"metal"},
      {"type":"primitive","id":"bottom","shape":"box","position":[0,1,-0.14],"dimensions":[1.2,0.05,0.18],"material":"metal"},
      {"type":"primitive","id":"left","shape":"box","position":[-0.575,1.5,-0.14],"dimensions":[0.05,1,0.18],"material":"metal"},
      {"type":"primitive","id":"right","shape":"box","position":[0.575,1.5,-0.14],"dimensions":[0.05,1,0.18],"material":"metal"},
      {"type":"primitive","id":"blade_0","shape":"box","position":[0,1.105,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_1","shape":"box","position":[0,1.215,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_2","shape":"box","position":[0,1.325,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_3","shape":"box","position":[0,1.435,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_4","shape":"box","position":[0,1.545,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_5","shape":"box","position":[0,1.655,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_6","shape":"box","position":[0,1.7650000000000001,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"blade_7","shape":"box","position":[0,1.875,-0.14],"dimensions":[1.1,0.025,0.14],"material":"metal","rotation":[0.6108652381980153,0,0]},
      {"type":"primitive","id":"rear_stub","shape":"cylinder","position":[0,1.5,0.03999999999999998],"rotation":[1.5707963267948966,0,0],"radius":0.32,"height":0.2,"segments":24,"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[TROX WG 外墙通风百叶构造](https://www.troxuk.co.uk/external-weather-louvres/wg-3a5581e60ae1533b)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
