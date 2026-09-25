---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: component
entity_name: massing_layers
topic: composition
status: supported
authority: schema
primary_terms:
  - 退台
  - 裙房
  - 层次感
  - 分层体量
  - 腰线
  - 错层
synonyms: []
applies_to:
  - 退台
  - 裙房
  - 错层
  - 分层体量
---

# 分层体量表达（退台、裙房与层间腰线）

适用条件：**用户或已批准方案显式提出**退台、裙房、错层、层间线脚等"一二层要分开"的造型要求时
使用本文档；普通方盒子别墅不需要。风格词（"现代中式""层次感"）本身不构成触发条件——
"层次感"是用户意图描述，落地方案仍要按本文档的四件手段显式列出。

WILD 没有"体量/退台"这一层抽象：**楼层之间的形体差异全部靠各层墙体、楼板、屋顶的坐标错位实现**，
不需要新字段。四件手段：

## 退台（上层内缩）

<!-- rag-meta
entity_type: component
entity_name: setback_massing
topic: composition
primary_terms:
  - 退台
  - 上层内缩
  - 逐层收进
synonyms: []
-->

上层墙线相对下层**内缩**，形成露台/挑檐平台。做法：把 L2 四面墙整体向内平移一个退台量
（常用 0.6~1.2m），楼板跟着缩；下层墙照旧。**必须同步改的四处**：

1. L2 墙的 `from`/`to` 四边同步内缩（不能只缩一面还叫退台）；
2. L2 楼板 `from`/`to` 跟着缩（否则板挑空外露）；
3. 挂在 L2 前墙上的构件（阳台、雨棚、窗、壁灯）——它们的 `from[0]` 沿墙距离不变，
   但**外墙定位变了**：壁灯/灯体这类世界坐标定位的构件要跟着墙的新外表面平移，
   否则会悬在半空（校验器不查"灯是否贴墙"，见《灯具》壁灯节）；
4. 屋顶仍按**下层**轮廓取值（`span`/`depth` ≈ L1 跨 + 出檐），退台处的屋顶成为上层挑檐。

以下是 L1 前墙 z=0、L2 前墙退台 0.6m 的墙体片段，不是完整 `.wild` 文件：

```json
[
  { "type": "wall", "id": "wall_ext_front_l1", "from": [0.0, 0.0, 0.0], "to": [14.0, 3.0, 0.0], "thickness": 0.24, "material": "wall_white" },
  { "type": "wall", "id": "wall_ext_front_l2", "from": [0.6, 3.0, 0.6], "to": [13.4, 6.0, 0.6], "thickness": 0.24, "material": "wall_white" }
]
```

## 裙房（低层附属体量）

<!-- rag-meta
entity_type: component
entity_name: podium_massing
topic: composition
primary_terms:
  - 裙房
  - 附属体量
  - 单层附属
synonyms: []
-->

单层附属体量（门厅、车库、茶室）就是**只建 L1 墙 + 给它自己的一个小 `roof` 元素**；
主体继续两层。要点：

- 每个体量一个屋顶元素，**屋顶可以多片**，但每片都要盖住自己承托墙的墙顶（7e 反向覆盖判据：
  只查结构性墙、屋顶基底不低于墙顶即可，不看片数）；
- 附属体量墙顶标高要和主体楼板/墙对齐，避免 7e 报"墙顶无覆盖"；
- 体量之间的接缝处两墙端点坐标要精确一致（容差 0.01m），否则判"孤立端点"⚠️。

## 层间腰线（水平线脚）

<!-- rag-meta
entity_type: component
entity_name: floor_band_cornice
topic: composition
primary_terms:
  - 腰线
  - 层间线脚
  - 水平线脚
synonyms: []
-->

层间分界最省事的手段是**一圈 `cornice` 独立线脚**：不指定 `parentRoof`，
`path` 用世界坐标沿外墙拉通，`profile` 是一个闭合小矩形（凸出墙面 5~8cm、高 12~16cm），
材质与墙同色——靠自遮挡阴影形成分界线。退台方案里，腰线放在**下层墙顶标高**，
正好勾出退台的楼板边界。

`profile` 坐标是相对 sweep 路径的二维偏移（水平向, 竖向），矩形即可：

```json
{
  "type": "cornice",
  "id": "band_l2",
  "path": [[0.0, 3.0, -0.12], [14.0, 3.0, -0.12]],
  "profile": [[-0.06, -0.08], [0.06, -0.08], [0.06, 0.08], [-0.06, 0.08]],
  "closedProfile": true,
  "material": "wall_white"
}
```

## 挑板与阳台线脚

`balcony` 的楼板本身就是最好的层间横向线条：把 `slabThickness` 加到 0.2~0.25、
沿正面拉通，视觉上等于一道厚挑板；再配玻璃栏板（见《引擎能力边界》railing 行）
就成了效果图里"二层坐落在白色挑板上"的观感。

## 能力边界

- ✅ 退台 / 裙房 / 错层：靠墙、楼板、屋顶的坐标错位实现，不用新字段。
- ✅ 多层腰线：无 `parentRoof` 的独立 `cornice` 沿墙拉通。
- ✅ 多片屋顶：每体量一个 `roof` 元素，各自盖住自己墙顶。
- ❌ 连续 L 形 / 回字形整体屋面：`roofType` 只有 `gable`/`hip`/`dome`/`flat`/`chinese_curved`/
  `chinese_pagoda` 六种、单片轮廓是矩形，拼不出转角连续的大屋面。
- ❌ 曲屋面沿退台连续跌落：同上，需按体量分段用多片屋顶近似，接缝需人工对齐。
