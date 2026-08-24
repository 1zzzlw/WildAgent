---
knowledge_layer: architecture
entity_type: assembly
entity_name: component_building_matrix
topic: matrix
status: experimental
authority: domain_reference
source: recipes/component-building-matrix.md
primary_terms:
  - 构件矩阵
  - 建筑类型矩阵
  - component
  - building type
synonyms: []
---

# 构件-建筑类型速查矩阵

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理不同建筑类型对 column/wall/floor/roof/opening/door/window/truss/stair/railing 的依赖强度。
> RAG 关键词：构件矩阵、建筑类型矩阵、column、wall、floor、roof、opening、door、window、truss、stair、railing
> 能力边界：表中的 door、window、railing 表示建筑语义需求。它们可以转换为 `geometry.components`，但不能写入 `geometry.elements`；truss 仍是未实现提案。具体参数必须按 `engine-capability-boundaries.md` 收敛，表中的开启方式、防火、保温和填充描述不等于当前引擎字段。

---
## 5.2 构件-建筑类型速查矩阵

| 建筑类型 | column | wall | floor | beam | roof | opening | door | window | truss | stair | railing |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **现代别墅** | ●● modern | ●● 0.15m | ●● 悬挑 | ○ | ● flat | ●● 长窗 | ● panel | ● fixed | — | ● | ● canopy |
| **中式别墅** | ●●● chinese_wooden | ●● 青砖 | ●● 台基 | ●● 额枋 | ●●● curved | ●● 隔扇/漏窗 | ● panel | ● casement槛窗 | — | ● | ●● 美人靠 |
| **新中式别墅** | ● modern | ●● 白墙 | ●● | ● | ● gable | ●● 落地窗 | ● panel | ● fixed | — | ● | ●● glass |
| **住宅多层** | ○ | ●●● 0.24m | ●● 0.12m | ● | ● gable | ●● | ● panel | ● sliding | — | ●● | ○ |
| **住宅高层** | ●● square | ●●● 0.20m | ●● 0.15m | ● | ● flat | ●● | ● panel | ● sliding | — | ●● | ○ |
| **酒店** | ● modern | ●● 0.12m | ●● | ● | ● flat | ●● | ● panel | ● fixed | — | ●● | ● glass |
| **教育** | ● square | ●● 0.24m | ●● 0.12m | ● | ● flat | ●● | ● panel+观察窗 | ● sliding | — | ●● | ● |
| **办公高层** | ●● rectangular | ●●● 0.40m核心筒 | ●● 0.15m | ●● | ● flat | ●● | ● glass | ● fixed | — | ●● | ○ |
| **博物馆** | ● 大间距 | ●● 0.24m | ● 0.15m | ●● 大跨 | ● | ● 天窗 | ● glass | — | ● 隐藏 | ● | ● |
| **剧院** | ○ | ●● 弧形声学 | ● 下沉 | ●● | ● | ● | ● | — | ●●● 屋架 | ● | ● |
| **商业** | ● 8.4m柱网 | ●● 玻璃幕墙 | ●● 留洞 | ● | ○ | ● 天窗 | ● glass | — | — | ●● 扶梯 | ●● glass |
| **体育场** | ●● 巨柱 | ○ 椭圆 | ●● 看台 | ● | ●● 膜 | ○ | ● glass | — | ●●● 罩棚 | ●● | ● |
| **医疗** | ● 0.5m | ●●● 0.50m防辐射 | ●● 0.20m | ● | ● | ●● | ● 气密门 | ● casement | — | ●● | ● |
| **交通** | ●● 巨柱少柱 | ● 玻璃 | ● 夹层 | ● | ●●● 超大跨 | ● | ● glass | — | ●●● 屋盖 | ●● | ● |
| **园林** | ●● chinese_wooden | ● 漏窗 | ● 台基 | ●● 廊梁 | ●● curved | ●● | ● 隔扇 | ● 槛窗 | — | ● | ●● 美人靠 |
| **单层厂房** | ●●● 阶形 | ● 彩钢板 | ● 地坪 | ●● 吊车梁 | ●● gable | ● 天窗 | ● 工业门 | — | ●●● 屋架 | — | — |
| **工业上楼** | ●● square≥0.6 | ● | ●●● 0.30m | ●● | ● | ● | ● 货梯门 | — | — | ●● | — |
| **温室** | ●● 钢方管 | ●(透明) | ● 苗床 | ● 弧形 | ●(采光) | ● 通风 | — | — | ● 轻型 | — | — |
| **养殖场** | ●● 钢柱 | ●● 夹芯板 | ●● 漏缝 | ●● 门式刚架 | ●● gable | ●● 风机 | ● | — | ●● | — | — |

> ●●● = 核心必用 | ●● = 常用 | ● = 视情况 | ○ = 偶尔 | — = 基本不用
