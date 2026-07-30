# 门窗与屋顶风格速查

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理建筑类型与 opening/door/window/mullion/roofType 的速配关系。
> RAG 关键词：门窗风格、屋顶类型、opening style、door style、window sashType、mullion pattern、roofType

---
## 5.3 门窗风格速查

| 建筑类型 | opening style | door style | window sashType | mullion pattern |
|:---:|:---:|:---:|:---:|:---:|
| 现代别墅 | rectangular | panel | fixed | none |
| 中式别墅 | arched/rectangular | panel(隔扇) | casement(槛窗) | grid/custom |
| 新中式别墅 | rectangular | panel | fixed/casement | grid |
| 传统住宅 | rectangular | panel | sliding | grid |
| 酒店 | rectangular | panel+观察窗 | fixed | none |
| 学校 | rectangular | panel+观察窗 | casement | grid |
| 办公 | rectangular | glass | fixed | none |
| 商业 | rectangular | glass | fixed | none |
| 医院 | rectangular | flush(气密) | casement | none |
| 园林 | arched/circular | panel(隔扇) | casement(槛窗) | colonial/custom |
| 厂房 | rectangular | flush(卷帘) | — | — |
| 哥特教堂 | gothic | panel(尖拱) | fixed(彩色玻璃) | custom(花窗) |

## 5.4 屋顶类型速查

| 屋顶类型 | roofType | 适用建筑 |
|:---:|:---:|:---|
| 人字坡顶 | `gable` | 木屋、现代别墅、新中式别墅、厂房、平房仓 |
| 四坡顶 | `hip` | 欧式庄园、新中式别墅 |
| 穹顶 | `dome` | 祈年殿宝顶、教堂、筒仓顶 |
| 平顶 | `flat` | 现代别墅(架空层)、住宅高层、办公、商业 |
| 中式曲面 | `chinese_curved` | 中式传统别墅(四合院)、庙宇单檐、园林建筑 |
| 中式重檐 | `chinese_pagoda` | 祈年殿、塔（tiers=2~3） |
