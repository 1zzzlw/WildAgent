---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: education_office_culture_family
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/public/education-office-culture.md
keywords:
  - 教育建筑
  - 学校
  - 办公建筑
  - 博物馆
  - 剧院
  - 图书馆
---

# 公共建筑：教育、办公、文化

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理学校、办公楼、博物馆、剧院、图书馆等公共建筑构件配方。
> RAG 关键词：教育建筑、学校、办公建筑、写字楼、博物馆、剧院、音乐厅、图书馆、公共建筑

---
## 二、公共建筑

---

### 2.1 教育建筑

<!-- rag-meta
entity_type: building
entity_name: education_building
topic: assembly
status: experimental
authority: domain_reference
keywords: 教育建筑, school, classroom, 学校
-->

> 规范依据：GB 50099-2011《中小学校设计规范》

**教室标准尺寸**（联网搜索 GB 50099 数据）

| 子类 | 开间 | 进深 | 净高 | 面积 | 强制规则 |
|:---:|:---:|:---:|:---:|:---:|:---|
| 幼儿园活动室 | 6.0~9.0m | 6.0~7.2m | 3.3m | 54~60 m² | **强制 ≤3F** |
| 小学教室 | 9.0m | 6.0m | 3.0m | ≥54 m² | 黑板≥3.6m宽 |
| 中学教室 | 9.0m | 6.4~7.2m | 3.0m | ≥54 m² | 黑板≥4.0m宽 |
| 大学教学楼 | 7.2~8.4m柱网 | — | 3.6m | — | 可做高层 |
| 实验室 | 8.4~12.0m | — | 4.2~5.0m | — | **限低层**（振动控制） |

**构件清单**

| 构件 | WILD type | 幼儿园 | 中小学 | 大学 |
|:---:|:---:|:---|:---|:---|
| 教室外墙 | `wall` | 0.24m, 圆角处理 | 0.24m | 0.20m(框架填充) |
| 教室隔墙 | `wall` | 0.12m, 墙裙1.2m高 | 0.12m, 墙裙1.4m高 | 0.12m |
| 框架柱 | `column` | 无(砖混) | 构造柱 | crossSection=square, side=0.4m, style=modern, 柱网7.2~8.4m |
| 梁 | `beam` | — | — | rect 0.3×0.6m |
| 楼板 | `floor` | 0.12m | 0.12m | 0.15m |
| 走廊 | `floor` + `railing` | 外廊式, autoRailing h=1.2m | 外廊/内廊, h=1.1m | 内廊 |
| 教室门 | `opening`+`door` | w=1.0m, h=2.1m, door:panel, **附观察窗** | 同左 | w=1.0m, door:flush |
| 教室窗 | `opening`+`window` | w=窗地比1:5, window:sliding | 窗间墙≤1.2m, 窗端墙≥1.0m, window:sliding | window:casement |
| 楼梯 | `stair` | width=1.2m | width=1.2m | width=1.4m |
| 黑板区墙面 | `wall` | — | 前墙, 黑板3.6~4.0m宽 | — |
| 屋顶 | `roof` | flat(可上人活动) | flat/gable | flat |

**关键规则卡**

> **幼儿园绝对 ≤3 层**（GB 50099 强制）
> **教室窗地比 ≥1:5**（采光要求）
> **窗间墙 ≤1.2m**，前端侧窗端墙 ≥1.0m（防眩光）
> **门扇附设观察窗**（除心理咨询室外）
> **墙裙高度**：小学 1.2m / 中学 1.4m / 舞蹈教室 2.1m

**典型案例**：富士幼儿园（手冢建筑，环形屋顶跑道）、深圳百校焕新

---

### 2.2 办公建筑

<!-- rag-meta
entity_type: building
entity_name: office_building
topic: assembly
status: experimental
authority: domain_reference
keywords: 办公建筑, office building, 写字楼
-->

> 图示：超高层写字楼结构示意图（原始资源：`docs/建筑类型分类体系_images/02_超高层写字楼.png`）

**构件清单**

| 构件 | WILD type | 园区独栋(2~6F) | 商务写字楼(高层) | 超高层(>100m) |
|:---:|:---:|:---|:---|:---|
| 核心筒墙体 | `wall` | — | thickness=0.3m, 含电梯井+楼梯井+管井 | 0.3~0.6m |
| 外框架柱 | `column` | square 0.3m, 柱距8.4m | square 0.4~0.5m | rectangular 0.6~0.8m, CFT钢管混凝土 |
| 标准层梁 | `beam` | rect 0.25×0.5m | 0.3×0.6m | 0.4×0.7m |
| 楼板 | `floor` | 0.15m | 0.15m, 含设备夹层 | 0.15~0.20m |
| 玻璃幕墙 | `wall` | material=glass | 隐框/明框幕墙 | 单元式幕墙 |
| 幕墙窗 | `opening`+`window` | fixed, glassOpacity=0.35 | fixed | fixed, low_e玻璃 |
| 避难层楼板 | `floor` | — | 每50m设一层, 加强 | 每50m |
| 楼梯 | `stair` | width=1.2m | 1.2m, 加压送风 | 1.4m, 避难层 |
| 入口大门 | `opening`+`door` | w=1.8m, glass, leafCount=2 | w=3.0m, glass | w=3.0m, glass |
| 入口雨棚 | `canopy` | parentWall=入口上方, projection=2.0m, supportType=cable | projection=3.0m, supportType=post | 3.0m, post |
| 无障碍坡道 | `ramp` | width=1.2m, slope=1:12, surface=brushed | 1.2m, 1:12 | 1.5m, 1:12 |

**核心筒 WILD JSON 示例**

```json
{
  "type": "wall", "id": "core_wall_n",
  "from": [0, 0, 6.0], "to": [20.0, 3.9, 6.0],
  "thickness": 0.40, "curve": "line",
  "material": "grey_concrete"
}
```

**组装顺序**：wall(核心筒围合) → column(外框架) → beam(主梁) → floor(楼板) → wall(玻璃幕墙) → opening(幕墙窗) → window → stair → 避难层 floor → 逐层重复

**标准层构件数**：核心筒 wall 8~12 + 外框柱 12~20 + floor 1 + 幕墙 wall 4 = **约 30 个/层**

**典型案例**：Apple Park（园区独栋）、上海中心大厦（632m, 128F）

---

### 2.3 文化建筑

<!-- rag-meta
entity_type: building
entity_name: cultural_building
topic: assembly
status: experimental
authority: domain_reference
keywords: 文化建筑, cultural building, 博物馆, 剧院, 图书馆
-->

**按子类构件清单**

#### 博物馆

<!-- rag-meta
entity_type: building
entity_name: museum
topic: assembly
status: experimental
authority: domain_reference
keywords: 博物馆, museum, 展厅
-->

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 展厅外墙 | `wall` | thickness=0.24m, 层高4.5~8.0m |
| 展厅框架柱 | `column` | 最少化, crossSection=square, side=0.5m, 间距12~18m |
| 大跨梁 | `beam` | rect 0.4×0.8m, 或 truss(隐藏于吊顶) |
| 展厅楼板 | `floor` | thickness=0.15m, 荷载加大 |
| 可移动隔墙 | `wall` | 轻质, 非承重, thickness=0.08m |
| 天窗/高侧窗 | `opening` | style=rectangular, 顶部/高位, 避免直射 |
| 入口大厅 | `column` + `floor` | 通高空间, column: doric/modern |

#### 剧院/音乐厅

<!-- rag-meta
entity_type: building
entity_name: theater_concert_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 剧院, 音乐厅, theater, concert hall
-->

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 观众厅围合墙 | `wall` | curve=arc(弧形声学造型), thickness=0.3m |
| 舞台塔超高墙 | `wall` | height≥30m, 围合"品"字形舞台 |
| 屋盖桁架 | `truss` | trussType=howe/pratt, span=主台口宽度, height=2.5倍台口高 |
| 乐池 | `floor` | 下沉, from=[x,h,z] to=[x,h-1.5,z] |
| 面光桥 | `floor` | 悬挑, 挂于观众厅上方 |
| 声学吊顶 | `floor` | 反射板阵列 |

> **关键规则**：剧院**不做高层**——主舞台上部需 2.5 倍台口高度用于布景升降，天然大跨单层。

#### 图书馆

<!-- rag-meta
entity_type: building
entity_name: library
topic: assembly
status: experimental
authority: domain_reference
keywords: 图书馆, library, 书架区
-->

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 密集书架区楼板 | `floor` | thickness=0.20m, 荷载12kN/m² |
| 阅览大厅 | `column`(减少) + `floor` | 中庭通高, 双层floor |
| 阅览窗 | `opening`+`window` | window: fixed, 避免直射, glassOpacity=0.25 |

**典型案例**：苏州博物馆（贝聿铭）、国家大剧院（保罗·安德鲁，钛金属椭球）

---
