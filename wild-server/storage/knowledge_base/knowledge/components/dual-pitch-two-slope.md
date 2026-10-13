---
entity_name: dual_pitch_two_slope
entity_type: roof
topic: composition
status: experimental
authority: schema
primary_terms: [两斜板法, 双坡屋顶]
synonyms: [two slope roof]
applies_to: [双坡屋顶, 坡屋顶]
---

# 双坡屋面的两斜板表达

常规双坡优先用原生 roofType=gable；当前原生形体包含坡面、山墙端板与檐口。需要独立坡面或不同细部时，以下局部片段可作为实现参考，不固定屋顶形制、坡度或尺寸。材料字典合并到 materials，elements/components 合并到 geometry。

## 两坡与脊盖 JSON

本例屋脊沿 Z，半跨 HW=2m、坡高 H=0.8m、厚 t=0.12m，檐口顶面 Y=3m、深3.4m。位置是 box 几何中心，rotation 使用弧度。设 α=atan(H/HW)、SL=√(HW²+H²)：西坡中心 X=-HW/2+sin(α)t/2，东坡 X=HW/2-sin(α)t/2；两者 Y=檐口Y+H/2-cos(α)t/2。中心由顶面中点沿法线下移半厚，不能下移整厚或用错 X 符号。

```json
{"elements":[{"type":"primitive","id":"slope_w","shape":"box","position":[-0.9777165594187538,3.3442913985468845,0],"dimensions":[2.154065922853802,0.12,3.4],"rotation":[0,0,0.3805063771123649],"material":"roof_dark"},{"type":"primitive","id":"slope_e","shape":"box","position":[0.9777165594187538,3.3442913985468845,0],"dimensions":[2.154065922853802,0.12,3.4],"rotation":[0,0,-0.3805063771123649],"material":"roof_dark"},{"type":"primitive","id":"ridge_cap","shape":"box","position":[0,3.81,0],"dimensions":[0.16,0.06,3.4],"material":"roof_dark"}],"components":[],"materials":{"roof_dark":{"baseColor":[0.12,0.15,0.18],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

以上片段同时表达两片屋面与脊盖。核对两坡上表面端点分别为 (±HW,檐口Y) 与 (0,檐口Y+H)，不能只返回一片斜板或用封檐条代替屋面。屋面、墙顶、两端封闭件须按本次图纸共同定位；本例未含墙、山墙填充及装饰。

## 封口与坐标边界

profile_sweep 的 profile 是垂直路径的截面，沿 Z 的短路径可得到 XY 截面周边，但当前没有路径端盖，不能将其声称为封闭山花实面。实面可用匹配的原生 gable 端板或声明近似的 box 分片。框料可独立表达，不能沿 X 挤出整幅三角形而误成大悬挑体。

原生 roof.span 始终控制世界 X 覆盖，depth 控制世界 Z 覆盖，ridgeAxis 改变脊向而不交换二者。自建坡板换脊向时须共同旋转定位和截面。出檐、厚度、支承、材料和采样数服从当前图纸；不得用固定防共面间隙或缩放比例代替实际关系核对。当前共享校验已有共面检查，数值检查仍需真实渲染验证形态。

字段和中心语义依据当前 schema、primitive box 与 roof builder。原资料的整厚偏移公式、未封口扫掠填充以及“无共面检查”说明已移除。
