# 屋顶、屋檐与顶部围护构件

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理 roof、cornice、canopy 等顶部和边缘围护构件的类型、适用建筑和维护边界。
> RAG 关键词：roof、cornice、canopy、屋顶、屋檐、檐口、雨棚、gable、hip、dome、flat、chinese_curved、chinese_pagoda

---
## 核心构件速查

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 屋顶 | `roof` | position, span, depth, height, roofType | 类型: gable/hip/dome/flat/chinese_curved/chinese_pagoda |
| 檐口 | `cornice` | parentWall, profile, position | position: top/bottom/middle |
| 雨棚 | `canopy` | parentWall, anchor, projection, supportType | 支撑: none/bracket/post/cable |

## 5.4 屋顶类型速查

| 屋顶类型 | roofType | 适用建筑 |
|:---:|:---:|:---|
| 人字坡顶 | `gable` | 木屋、现代别墅、新中式别墅、厂房、平房仓 |
| 四坡顶 | `hip` | 欧式庄园、新中式别墅 |
| 穹顶 | `dome` | 祈年殿宝顶、教堂、筒仓顶 |
| 平顶 | `flat` | 现代别墅(架空层)、住宅高层、办公、商业 |
| 中式曲面 | `chinese_curved` | 中式传统别墅(四合院)、庙宇单檐、园林建筑 |
| 中式重檐 | `chinese_pagoda` | 祈年殿、塔（tiers=2~3） |

## 维护说明

- 单个屋顶构件参数和 roofType 适配放在本文档。
- 某类建筑的完整屋顶做法，例如体育场膜屋面、温室采光顶、中式重檐，放在对应 `building_types/` 文档。
- 跨建筑复用的屋顶组装顺序放在 `recipes/`。
