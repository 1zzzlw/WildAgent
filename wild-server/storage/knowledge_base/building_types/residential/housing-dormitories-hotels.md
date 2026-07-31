---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: residential_accommodation_family
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/residential/housing-dormitories-hotels.md
keywords:
  - 住宅
  - housing
  - 宿舍
  - dormitory
  - 酒店
  - hotel
---

# 居住与类居住建筑：住宅、宿舍、酒店

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理普通住宅、宿舍、宾馆酒店等居住或类居住建筑的构件配方。
> RAG 关键词：普通住宅、低层住宅、多层住宅、高层住宅、宿舍、宾馆、酒店、剪力墙、客房、走廊

---
## 1.2 普通住宅（低层~超高层）

<!-- rag-meta
entity_type: building
entity_name: residential_building
topic: assembly
status: experimental
authority: domain_reference
keywords: 普通住宅, residential building, 低层住宅, 高层住宅
-->

**构件清单（按层数分级）**

| 构件 | WILD type | 低层(1~3F) | 多层(4~6F) | 高层(10~33F) | 超高层(>100m) |
|:---:|:---:|:---|:---|:---|:---|
| 承重外墙 | `wall` | thickness=0.24m(砖混) | 0.24m(砖混) | 0.20m(剪力墙) | 0.20~0.30m(剪力墙) |
| 内隔墙 | `wall` | 0.12m | 0.12m | 0.10m | 0.10m |
| 框架柱 | `column` | 无(砖混) | 无/构造柱 | crossSection=square, side=0.3~0.5m, style=modern | side=0.4~0.8m, CFT钢管混凝土 |
| 楼板 | `floor` | thickness=0.12m | 0.12~0.15m | 0.15m | 0.15~0.20m |
| 梁 | `beam` | rect 0.2×0.3m | 0.25×0.5m | 0.3×0.6m | 0.4×0.7m |
| 屋顶 | `roof` | gable(坡顶) | gable/flat | flat | flat |
| 楼梯 | `stair` | width=0.9m | 1.1m, autoRailing | 1.2m, 加压送风 | 1.4m, 避难层 |

**标准层门窗规格**

| 部位 | opening | door | window | 尺寸 |
|:---:|:---|:---|:---|:---|
| 入户门 | rectangular | panel, leafCount=1, hingeSide=left | — | w=1.0m, h=2.1m |
| 室内门 | rectangular | flush, leafCount=1 | — | w=0.9m, h=2.1m |
| 采光窗 | rectangular | — | sliding, sashCount=2, glassOpacity=0.35 | w=1.5~2.4m, h=1.5m |
| 阳台门 | rectangular | glass, leafCount=2 | sliding | w=2.4m, h=2.4m |

**阳台构件**

```json
{
  "type": "floor", "id": "balcony_slab",
  "from": [6.0, 3.0, 0], "to": [7.2, 3.15, 4.0],
  "thickness": 0.15, "shape": "rect",
  "autoRailing": { "edges": ["north", "east", "south"], "height": 1.1 }
}
```

> `autoRailing` 自动生成 `railing`：height=1.1m, infill=vertical_bar, material=steel_railing

**组装顺序**：wall(核心筒/楼梯间) → wall(分户墙) → floor(楼板) → opening(门窗洞) → door + window → floor(阳台, autoRailing) → stair → 逐层重复

**标准层构件数**：wall 8~12 + floor 1 + opening 6~10 + column 0~8 = **约 20~30 个/层**

**典型案例**：城市商品住宅塔楼（33 层卡 99m 红线）、杭州良渚天空之城

---

## 1.3 宿舍（≤9F）

<!-- rag-meta
entity_type: building
entity_name: dormitory
topic: assembly
status: experimental
authority: domain_reference
keywords: 宿舍, dormitory, 学生宿舍
-->

> 规范依据：JGJ 36《宿舍建筑设计规范》，层数多 ≤9 层（给排水水压限制）

**构件清单**

| 构件 | WILD type | 精确参数 | 说明 |
|:---:|:---:|:---|:---|
| 走廊两侧隔墙 | `wall` | thickness=0.12m, 开间3.6m, 进深6~8m | 密集排布 |
| 公共卫生间墙 | `wall` + `floor` | wall=0.12m, floor 防水 surfaces=stone_block | 上下对齐 |
| 宿舍门 | `opening` + `door` | opening: rectangular, w=0.9m, h=2.1m; door: flush, leafCount=1 | 沿走廊均匀排布 |
| 走廊窗 | `opening` + `window` | window: sliding, sashCount=2 | w=1.5m, h=1.5m |
| 公共楼梯 | `stair` | width=1.4m, 两端各一, autoRailing=true | 疏散双楼梯 |
| 管道井 | `wall` | 围合竖井, thickness=0.12m | 卫生间对位 |

**组装顺序**：wall(外墙) → wall(走廊隔墙) → wall(卫生间) → floor → opening(宿舍门) → door → opening(窗) → window → stair → 逐层

**典型案例**：清华大学紫荆公寓（6F）、华为松山湖员工宿舍

---

## 1.4 宾馆/酒店

<!-- rag-meta
entity_type: building
entity_name: hotel
topic: assembly
status: experimental
authority: domain_reference
keywords: 宾馆, 酒店, hotel, guest room
-->

> 规范依据：JGJ 62-2014《旅馆建筑设计规范》

**客房标准尺寸**（联网搜索 GB/JGJ 数据）

| 酒店类型 | 开间 | 进深 | 层高 | 客房面积 |
|:---:|:---:|:---:|:---:|:---:|
| 快捷酒店 | 3.2~3.8m | 6.0~6.2m | 3.0m | 19~24 m² |
| 商务酒店 | 3.7~4.2m | 7.2~8.4m | 3.0~3.9m | 26~35 m² |
| 五星级酒店 | 4.5~4.8m | 9.0~9.8m | 3.9~4.2m | 40~48 m² |
| 度假酒店 | 5.1~6.0m | 8.1~11.6m | 3.3~3.6m | 50~60 m² |

**构件清单**

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 客房隔墙 | `wall` | thickness=0.12m, 隔声处理, 开间3.7~4.5m |
| 客房门 | `opening` + `door` | w=0.9m, h=2.1m; door: panel, leafCount=1, 观察窗 |
| 卫生间门 | `opening` + `door` | w=0.75m, h=2.0m; door: flush |
| 落地窗 | `opening` + `window` | w≥2.7m, h=2.4m; window: fixed, glassOpacity=0.35 |
| 大堂通高空间 | `wall`(首层) + `column` | 2~3层通高, column: modern, r=0.3m |
| 宴会厅大跨 | `beam` + `roof` | beam: i-beam, 大跨无柱; roof: flat |
| 玻璃幕墙 | `wall` | material=glass, 外立面 |
| 屋顶泳池 | `floor` + `railing` | autoRailing: height=1.1, infill=glass |
| 客房层楼梯 | `stair` | width=1.2m, autoRailing=true |
| 电梯井 | `wall` | 核心筒围合, thickness=0.20m, 分区运行 |

**WILD JSON 示例（客房标准层单元）**

```json
{
  "templates": [
    { "name": "guest_room_unit", "type": "group", "components": [
      { "type": "wall", "id": "room_wall_l", "from": [0,0,0], "to": [0,3.0,7.5], "thickness": 0.12 },
      { "type": "opening", "id": "room_door", "parentWall": "room_wall_l", "from": [3.0,0,0], "width": 0.9, "height": 2.1, "style": "rectangular" },
      { "type": "door", "id": "door_1", "parentOpening": "room_door", "style": "panel", "leafCount": 1, "hingeSide": "right" },
      { "type": "opening", "id": "room_win", "parentWall": "room_wall_l", "from": [5.0,0.9,0], "width": 2.7, "height": 2.4, "style": "rectangular" },
      { "type": "window", "id": "win_1", "parentOpening": "room_win", "sashType": "fixed", "glassOpacity": 0.35 }
    ]}
  ],
  "instances": [
    { "template": "guest_room_unit", "position": [0, 0, 0] },
    { "template": "guest_room_unit", "position": [4.2, 0, 0] },
    { "template": "guest_room_unit", "position": [8.4, 0, 0] }
  ]
}
```

> 用 `templates` + `instances` 批量复用客房单元，走廊两侧镜像排布

**典型案例**：香山饭店（贝聿铭，多层文旅）、上海 J 酒店（632m 超高层地标）

---
