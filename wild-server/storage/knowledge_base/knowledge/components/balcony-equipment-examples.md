---
entity_name: balcony_equipment_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 阳台栏板、露台栏杆与设备平台 JSON 示例
synonyms: []
---

# 阳台栏板、露台栏杆与设备平台 JSON 示例

## 阳台栏板 · balcony-panel

<!-- rag-meta
entity_type: balcony
entity_name: balcony_panel
topic: composition
primary_terms:
  - 阳台栏板
  - balcony-panel
synonyms: []
-->

采用 balcony 生成悬挑板，railingEnabled=false 后由独立 panel 栏杆接管三边。宿主后方楼板确定内外方向；沿墙 from[0]=0.5，板顶 from[1]=3.2，墙外表面 z=-0.12，因此外边 z=-1.37。更换宿主后重算世界路径，不能只改板宽。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,4,0],"thickness":0.24,"material":"plaster"},
      {"type":"floor","id":"interior_slab","from":[-2,3.02,0],"to":[2,3.02,2],"thickness":0.18,"material":"stone"}
    ],
    "components":[{"type":"balcony","id":"balcony","parentWall":"host_wall","from":[0.5,3.2,0],"width":3,"depth":1.25,"slabThickness":0.18,"railingEnabled":false,"material":"stone"},{"type":"railing","id":"panel_guard","path":[[-1.5,3.2,-0.12],[-1.5,3.2,-1.37],[1.5,3.2,-1.37],[1.5,3.2,-0.12]],"height":1.05,"postSpacing":0.75,"infillType":"panel","infillThickness":0.06,"infillMaterial":"stone","material":"metal"}],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Q-railing 栏杆系统技术图纸入口](https://q-railing.com/pl-pl/uslugi/materialy-do-pobrania/rysunki-cad/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 露台栏杆 · terrace-railing

<!-- rag-meta
entity_type: railing
entity_name: terrace_railing
topic: composition
primary_terms:
  - 露台栏杆
  - terrace-railing
synonyms: []
-->

楼板底标高为 -0.18、顶面为 0，栏杆世界路径从板顶起。三边栏杆由连续 path 与 glass 填充构成；没有 parentFloor 时 path 是世界坐标，不把这些点当沿墙坐标。栏杆高度及立柱间距是本次示例值。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"floor","id":"terrace_slab","from":[-1.5,-0.18,0],"to":[1.5,-0.18,1.8],"thickness":0.18,"material":"stone"}
    ],
    "components":[{"type":"railing","id":"glass_guard","path":[[-1.5,0,0],[-1.5,0,1.8],[1.5,0,1.8],[1.5,0,0]],"height":1.1,"postSpacing":1,"infillType":"glass","infillThickness":0.012,"infillMaterial":"glass","material":"metal"}],
  "materials":{"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Q-railing 栏杆系统技术图纸入口](https://q-railing.com/pl-pl/uslugi/materialy-do-pobrania/rysunki-cad/)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 设备平台 · equipment-platform

<!-- rag-meta
entity_type: component
entity_name: equipment_platform
topic: composition
primary_terms:
  - 设备平台
  - equipment-platform
synonyms:
  - 设备承托平台
-->

以悬挑楼板和两组墙支架表达设备平台。floor.from[1]=2.08、厚度 0.12，故板顶 2.2；支架水平臂顶面接板底。安装原点、平台外挑、支架位置及设备净空由本次需求给出，不套用产品图的气候或载荷要求。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"wall","id":"host_wall","from":[-2.0,0,0],"to":[2.0,3.4,0],"thickness":0.24,"material":"plaster"},
      {"type":"floor","id":"equipment_slab","from":[-1,2.08,-0.12],"to":[1,2.08,-1.12],"thickness":0.12,"material":"stone"},
      {"type":"primitive","id":"bracket_0","shape":"box","position":[-0.7,2.04,-0.62],"dimensions":[0.08,0.08,1],"material":"metal"},
      {"type":"primitive","id":"anchor_0","shape":"box","position":[-0.7,1.7,-0.15],"dimensions":[0.08,0.72,0.06],"material":"metal"},
      {"type":"primitive","id":"bracket_1","shape":"box","position":[0.7,2.04,-0.62],"dimensions":[0.08,0.08,1],"material":"metal"},
      {"type":"primitive","id":"anchor_1","shape":"box","position":[0.7,1.7,-0.15],"dimensions":[0.08,0.72,0.06],"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Daikin 外机支架与底座安装图](https://www.daikin.eu/content/dam/document-library/installation-manuals/ac/split/RXP-L%2CARXP-L%2CRXF-A_3PDA512025-2_Installation%20Manual_Danish.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 空调机位 · ac-position

<!-- rag-meta
entity_type: component
entity_name: ac_position
topic: composition
primary_terms:
  - 空调机位
  - ac-position
synonyms:
  - air conditioning unit
  - air conditioner platform
  - 空调外机位
-->

机位示例包含底座、外机外壳和前侧风扇外观；底座顶为 0.12，机壳底为 0.12。安装到设备平台时将这组世界坐标平移到板顶，并保留方案要求的通风空间。该几何不表示制冷、排水、风量或风扇动画。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"equipment_base","shape":"box","position":[0,0.06,0],"dimensions":[1.2,0.12,0.65],"material":"stone"},
      {"type":"primitive","id":"condenser","shape":"box","position":[0,0.445,0],"dimensions":[0.95,0.65,0.3],"material":"plaster"},
      {"type":"primitive","id":"fan_face","shape":"cylinder","position":[0,0.45,-0.16],"rotation":[1.5707963267948966,0,0],"radius":0.22,"height":0.02,"segments":24,"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"plaster":{"baseColor":[0.9,0.88,0.81],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Daikin 外机支架与底座安装图](https://www.daikin.eu/content/dam/document-library/installation-manuals/ac/split/RXP-L%2CARXP-L%2CRXF-A_3PDA512025-2_Installation%20Manual_Danish.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 铁艺栏杆 · ornamental-iron-railing

<!-- rag-meta
entity_type: railing
entity_name: ornamental_iron_railing
topic: composition
primary_terms:
  - 铁艺栏杆
  - ornamental-iron-railing
synonyms:
  - wrought iron railing
  - 铁艺护栏
-->

保留顶部扶手、下横杆、竖条和两端卷花。卷花使用小方截面沿折线扫掠，路径点越密轮廓越平滑；不是把普通两道横杆称为铁艺。安装在露台时整体平移并按实际长度重复所选竖条。这里只表达静态外观，没有来源产品的受力或规范声明。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"iron_top","shape":"box","position":[0,1.1,0],"dimensions":[2.4,0.04,0.04],"material":"metal"},
      {"type":"primitive","id":"iron_bottom","shape":"box","position":[0,0.08,0],"dimensions":[2.4,0.04,0.04],"material":"metal"},
      {"type":"primitive","id":"iron_bar_0","shape":"box","position":[-1.15,0.59,0],"dimensions":[0.025,1.02,0.025],"material":"metal"},
      {"type":"primitive","id":"iron_bar_1","shape":"box","position":[-0.6,0.59,0],"dimensions":[0.025,1.02,0.025],"material":"metal"},
      {"type":"primitive","id":"iron_bar_2","shape":"box","position":[0,0.59,0],"dimensions":[0.025,1.02,0.025],"material":"metal"},
      {"type":"primitive","id":"iron_bar_3","shape":"box","position":[0.6,0.59,0],"dimensions":[0.025,1.02,0.025],"material":"metal"},
      {"type":"primitive","id":"iron_bar_4","shape":"box","position":[1.15,0.59,0],"dimensions":[0.025,1.02,0.025],"material":"metal"},
      {"type":"primitive","id":"lower_scroll","shape":"profile_sweep","profile":[[-0.008,-0.008],[0.008,-0.008],[0.008,0.008],[-0.008,0.008]],"path":[[0.02,0.32,0],[0.18,0.2,0],[0.28,0.29,0],[0.24,0.4,0],[0.12,0.42,0],[0.08,0.36,0],[0.12,0.3,0]],"closedProfile":true,"material":"metal"},
      {"type":"primitive","id":"upper_scroll","shape":"profile_sweep","profile":[[-0.008,-0.008],[0.008,-0.008],[0.008,0.008],[-0.008,0.008]],"path":[[-0.02,0.78,0],[-0.18,0.9000000000000001,0],[-0.28,0.81,0],[-0.24,0.7000000000000001,0],[-0.12,0.6800000000000002,0],[-0.08,0.7400000000000001,0],[-0.12,0.8,0]],"closedProfile":true,"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[King Metals 双端卷花栏杆构件](https://www.kingmetals.com/ECItemMainPage.aspx?ItemId=ITM-10273550)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
