---
entity_name: stair
entity_type: stair
topic: composition
status: supported
authority: schema
primary_terms:
  - 楼梯
synonyms:
  - staircase
  - stairs
  - 直跑楼梯
  - straight stair
applies_to:
  - 楼梯
  - staircase
---

# 楼梯 · stair

`stair` 是 `geometry.elements` 原生元素。`staircase`、stairs、楼梯属于同一检索名称，
输出 type 使用 stair。来源为当前 Schema 的 stairParams 与 wild-core 的 stair 几何实现；
from/to 是世界坐标的起步、到达点，width 是梯段宽度。stepCount、stepHeight、stepDepth
可省略由引擎计算；指定时需与两端高差、水平距离一致。

以下为局部片段，合并到当前图纸对应的 geometry.elements；尺寸、方向、材料均可调整。
材料引用和两端标高仍需结合真实楼板。不要复制另一条已存在的核心楼梯。

```json
{
  "elements": [
    {"type":"stair","id":"sample_stair","from":[0,0,0],"to":[0,3,5.7],"width":1.2,"stepCount":20,"material":"concrete"}
  ],
  "components": [],
  "materials": {
    "concrete":{"baseColor":[0.41,0.42,0.43],"roughness":0.76,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}
  }
}
```

这段示例只表达直跑梯段，不自动表达栏杆、休息平台或楼板洞口。上层楼板不得封住通道；
可用矩形楼板分片留空。不同楼层的起终点、数量及通道位置由图纸决定。
当前轴对齐直梯洞口检查不覆盖斜向梯段；转折、旋转或曲线楼梯需多个梯段或独立组合，
不能把一次 profile_sweep 当作重复踏步生成器，也不能把单梯段成功当作完整交通验证。

## 双跑楼梯与实体平台

<!-- rag-meta
entity_type: stair
entity_name: stair
topic: composition
primary_terms: [楼梯, 双跑楼梯, 折返楼梯]
synonyms: [staircase, two-flight stair, return stair]
-->

双跑不能只返回两个 stair 并在 explanation 中称它们“通过平台衔接”。中间承托面
必须有实际 floor 或 primitive.box 实体，其顶面落在两跑衔接标高并覆盖完整梯宽。
本例每跑净宽1.2m、高差2m、水平投影3.6m。行进沿 Z、两跑沿 X 并列：第一跑保持自己的 X 不变，从 Z=4.8 上行到 Z=1.2；第二跑在另一条 X 中心线上，从 Z=1.2 上行到 Z=4.8。平台位于较小Z的一侧（Z=0～1.2），因此第一跑的上行终点和第二跑的上行起点必须在平台边 Z=1.2，不能让第一跑朝远离平台的一侧上行。沿X并列不等于沿X行进。平台顶2m，
到达楼板顶4m。整体宽度包含两跑和间隔，整体进深包含梯跑和平台，不把整组占地
size.width 当成每跑净宽。踏步参数只写 stepCount=12，其余由端点计算；不能把
四舍五入的0.167m当成精确层高等式。显式参数相互冲突时说明需要修订图纸，不静默扩宽。

以下 elements/components 并入 geometry，materials 并入材质字典。ground_support
与 upper_arrival 是安装前提示例，整栋已有楼板时复用现有实体、核对其顶面标高，
不重建主体。中间平台属于当前楼梯组合；原生 floor 的 from[1] 是板底，顶=板底+厚度。
primitive.box 的顶=position[1]+dimensions[1]/2，位置须按实际宿主平移和旋转。

```json
{"elements":[{"type":"floor","id":"ground_support","from":[0,-0.18,0],"to":[2.8,-0.18,6],"thickness":0.18,"material":"concrete"},{"type":"floor","id":"upper_arrival","from":[0,3.82,4.8],"to":[2.8,3.82,6],"thickness":0.18,"material":"concrete"},{"type":"primitive","id":"middle_landing","shape":"box","position":[1.4,1.925,0.6],"dimensions":[2.8,0.15,1.2],"material":"concrete"},{"type":"stair","id":"flight_first","from":[0.65,0,4.8],"to":[0.65,2,1.2],"width":1.2,"stepCount":12,"material":"concrete"},{"type":"stair","id":"flight_second","from":[2.15,2,1.2],"to":[2.15,4,4.8],"width":1.2,"stepCount":12,"material":"concrete"}],"components":[],"materials":{"concrete":{"baseColor":[0.41,0.42,0.43],"roughness":0.76,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

这是完整双跑与平台的几何示例，已通过实现、梯宽承托检查及实际渲染；未含栏杆，
也不是专业安全规范判断。上层楼板留出通道，平台不盖住上升梯段；本例到达板只在
终点外侧，整体板需要由当前编译按楼梯路径分片。参考依据为当前 stair/floor Schema、
原生几何实现及 collect_stair_placement_issues；所有示例尺寸服从本次图纸。
