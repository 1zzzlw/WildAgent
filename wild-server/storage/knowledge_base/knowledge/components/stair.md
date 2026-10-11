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
