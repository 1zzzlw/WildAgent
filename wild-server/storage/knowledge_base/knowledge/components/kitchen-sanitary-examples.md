---
entity_name: kitchen_sanitary_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 橱柜与厨卫设施 JSON 示例
synonyms: []
---

# 橱柜与厨卫设施 JSON 示例

## 橱柜 · kitchen-cabinet

<!-- rag-meta
entity_type: furniture
entity_name: kitchen_cabinet
topic: composition
primary_terms:
  - 橱柜
  - kitchen-cabinet
synonyms:
  - kitchen cabinet
  - 厨房橱柜
  - 厨柜
-->

用 primitive.box 分别表达柜体、踢脚、三扇门板、把手与台面；世界坐标 position 是各盒体中心，板件底部不能直接把 Y 写为 0。来源是吊柜板件图，本例转换为自选落地橱柜，不照搬安装高度。门板在 +Z 为正面；没有抽屉/开门动作、厨房设备或水槽。柜体尺寸、门数、台面与材质分层均可修改。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"cabinet_body","shape":"box","position":[0,0.425,0],"dimensions":[1.8,0.7,0.6],"material":"wood"},
      {"type":"primitive","id":"cabinet_plinth","shape":"box","position":[0,0.075,-0.025],"dimensions":[1.74,0.15,0.52],"material":"wood"},
      {"type":"primitive","id":"countertop","shape":"box","position":[0,0.8,0],"dimensions":[1.86,0.05,0.64],"material":"stone"},
      {"type":"primitive","id":"cabinet_door_0","shape":"box","position":[-0.6,0.43,0.312],"dimensions":[0.588,0.68,0.024],"material":"wood"},
      {"type":"primitive","id":"cabinet_handle_0","shape":"box","position":[-0.6,0.68,0.34],"dimensions":[0.12,0.02,0.03],"material":"metal"},
      {"type":"primitive","id":"cabinet_door_1","shape":"box","position":[0,0.43,0.312],"dimensions":[0.588,0.68,0.024],"material":"wood"},
      {"type":"primitive","id":"cabinet_handle_1","shape":"box","position":[0,0.68,0.34],"dimensions":[0.12,0.02,0.03],"material":"metal"},
      {"type":"primitive","id":"cabinet_door_2","shape":"box","position":[0.6,0.43,0.312],"dimensions":[0.588,0.68,0.024],"material":"wood"},
      {"type":"primitive","id":"cabinet_handle_2","shape":"box","position":[0.6,0.68,0.34],"dimensions":[0.12,0.02,0.03],"material":"metal"}
    ],
    "components":[],
  "materials":{"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"},"stone":{"baseColor":[0.72,0.69,0.62],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[IKEA METOD 柜体装配图，第 1 页](https://www.ikea.com/de/de/assembly_instructions/metod-korpus-wandschrank-weiss__AA-2238433-5-2.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 洗手盆 · washbasin

<!-- rag-meta
entity_type: furniture
entity_name: washbasin
topic: composition
primary_terms:
  - 洗手盆
  - washbasin
synonyms:
  - wash basin
  - 洗脸盆
  - 台盆
  - lavatory
-->

用底板和四侧板形成有开口的盆体，避免整块实心箱体；另组合自选支座与水龙头。来源平面图标注宽 600、深 470 mm，转换为 0.6、0.47 m；其余高度、板厚、支座与龙头是本项目示例假设，不是厂家安装规范。primitive.position 是分件几何中心，所有片段需一起平移到安装位置。盆的圆角、排水和曲面仅近似表达，没有给排水模拟。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"basin_bottom","shape":"box","position":[0,0.735,0],"dimensions":[0.6,0.03,0.47],"material":"ceramic"},
      {"type":"primitive","id":"basin_front","shape":"box","position":[0,0.81,0.2175],"dimensions":[0.6,0.12,0.035],"material":"ceramic"},
      {"type":"primitive","id":"basin_back","shape":"box","position":[0,0.81,-0.2175],"dimensions":[0.6,0.12,0.035],"material":"ceramic"},
      {"type":"primitive","id":"basin_left","shape":"box","position":[-0.2825,0.81,0],"dimensions":[0.035,0.12,0.4],"material":"ceramic"},
      {"type":"primitive","id":"basin_right","shape":"box","position":[0.2825,0.81,0],"dimensions":[0.035,0.12,0.4],"material":"ceramic"},
      {"type":"primitive","id":"basin_pedestal","shape":"box","position":[0,0.36,-0.05],"dimensions":[0.18,0.72,0.2],"material":"ceramic"},
      {"type":"primitive","id":"faucet_stem","shape":"box","position":[0,0.945,-0.21],"dimensions":[0.035,0.15,0.035],"material":"metal"},
      {"type":"primitive","id":"faucet_spout","shape":"box","position":[0,1.015,-0.155],"dimensions":[0.035,0.035,0.11],"material":"metal"}
    ],
    "components":[],
  "materials":{"ceramic":{"baseColor":[0.94,0.94,0.92],"roughness":0.2,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"metal":{"baseColor":[0.13,0.15,0.17],"roughness":0.4,"metallic":0.75,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Duravit Vero 台盆平面图，第 1 页](https://csassets.duravit.com/1/2/Duravit_TD_1266386.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 马桶 · toilet

<!-- rag-meta
entity_type: furniture
entity_name: toilet
topic: composition
primary_terms:
  - 马桶
  - toilet
synonyms:
  - WC
  - 坐便器
-->

primitive 组合底座、盆侧、水箱、箱盖与椭圆开口盆沿，保留侧视图中水箱在后、盆口在前的关系。盆沿用闭合 profile_sweep，未用实心盒封死盆口；模型不具备冲水或盖板开合。来源标注高 730、坐高 410 mm，对应约 0.73、0.41 m；横向宽度与椭圆轮廓为自选近似，不宣称复刻内部水封。安装时整体平移/旋转各分件，不能给 primitive 添加 toilet 类型。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"primitive","id":"toilet_pedestal","shape":"box","position":[0,0.18,0.04],"dimensions":[0.24,0.36,0.3],"material":"ceramic"},
      {"type":"primitive","id":"toilet_tank","shape":"box","position":[0,0.52,-0.2],"dimensions":[0.36,0.4,0.18],"material":"ceramic"},
      {"type":"primitive","id":"toilet_tank_lid","shape":"box","position":[0,0.73,-0.2],"dimensions":[0.38,0.03,0.2],"material":"ceramic"},
      {"type":"primitive","id":"toilet_bowl_rim","shape":"profile_sweep","profile":[[-0.035,-0.02],[0.035,-0.02],[0.035,0.02],[-0.035,0.02]],"path":[[0.19,0.41,0.05],[0.183525906994923,0.41,0.11470476127563019],[0.16454482671904336,0.41,0.175],[0.13435028842544405,0.41,0.2267766952966369],[0.09500000000000003,0.41,0.26650635094610964],[0.04917561856947894,0.41,0.2914814565722671],[1.1634144591899856e-17,0.41,0.3],[-0.04917561856947892,0.41,0.2914814565722671],[-0.09499999999999996,0.41,0.2665063509461097],[-0.13435028842544403,0.41,0.2267766952966369],[-0.16454482671904336,0.41,0.175],[-0.18352590699492297,0.41,0.11470476127563026],[-0.19,0.41,0.05000000000000003],[-0.183525906994923,0.41,-0.014704761275630196],[-0.16454482671904339,0.41,-0.07499999999999993],[-0.1343502884254441,0.41,-0.12677669529663677],[-0.09500000000000008,0.41,-0.1665063509461096],[-0.04917561856947892,0.41,-0.19148145657226706],[-3.490243377569956e-17,0.41,-0.2],[0.04917561856947886,0.41,-0.19148145657226712],[0.09500000000000003,0.41,-0.16650635094610966],[0.134350288425444,0.41,-0.12677669529663693],[0.1645448267190433,0.41,-0.07500000000000011],[0.18352590699492294,0.41,-0.01470476127563039],[0.19,0.41,0.04999999999999994]],"closedProfile":true,"material":"ceramic"},
      {"type":"primitive","id":"toilet_bowl_side_0","shape":"box","position":[-0.14,0.31,0.08],"dimensions":[0.06,0.16,0.36],"material":"ceramic"},
      {"type":"primitive","id":"toilet_bowl_side_1","shape":"box","position":[0.14,0.31,0.08],"dimensions":[0.06,0.16,0.36],"material":"ceramic"}
    ],
    "components":[],
  "materials":{"ceramic":{"baseColor":[0.94,0.94,0.92],"roughness":0.2,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Duravit 马桶侧面尺寸图，第 1 页](https://csassets.duravit.com/2/9/Duravit_TD_2912316.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
