# 公共建筑：商业、体育、医疗、交通、园林纪念司法

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理商业、体育、医疗、交通、园林、纪念、司法建筑的构件配方。
> RAG 关键词：商业建筑、体育场、医疗建筑、医院、交通建筑、航站楼、园林、纪念建筑、司法建筑

---
## 2.4 商业建筑

**构件清单**

| 构件 | WILD type | 购物中心(4~7F) | 超市(1~2F) |
|:---:|:---:|:---|:---|
| 外围护墙 | `wall` | 玻璃幕墙, material=glass | 0.24m |
| 商铺隔墙 | `wall` | 轻质0.08m, 灵活分隔, 面宽8~12m | — |
| 中庭楼板 | `floor` | 各层留洞, 3~7层通高 | — |
| 中庭栏杆 | `railing` | autoRailing, height=1.1m, infill=glass | — |
| 首层楼板 | `floor` | thickness=0.15m, 层高5.4~6.0m | 4.5~5.5m |
| 标准层楼板 | `floor` | 层高4.5~5.4m | — |
| 框架柱 | `column` | square 0.5m, 柱网8.4×8.4m | square 0.5m |
| 梁 | `beam` | rect 0.35×0.7m | rect 0.3×0.6m |
| 采光顶 | `opening` | 顶部, 中庭天窗 | — |
| 自动扶梯 | `stair`(倾斜) | 30°倾斜, 跨1~2层 | — |
| 货梯井 | `wall` | 核心筒围合 | — |
| 商铺门 | `opening`+`door` | w=1.5m, door:glass, leafCount=1 | — |

**中庭 WILD JSON 示例**

```json
{
  "type": "floor", "id": "atrium_l2",
  "from": [0, 5.4, 0], "to": [40, 5.55, 40],
  "thickness": 0.15, "shape": "rect",
  "autoRailing": { "edges": ["north", "south", "east", "west"], "height": 1.1, "infill": "glass" }
}
```

> 中庭各层 floor 留洞 + 四面 autoRailing 玻璃栏板

**关键规则**：购物中心**极少超过 7 层**——消费者爬不动，高层租金倒挂。

**典型案例**：北京国贸商城、成都大悦城

---

## 2.5 体育建筑

> 图示：体育场结构示意图（原始资源：`docs/建筑类型分类体系_images/03_体育场.png`）

**构件清单**

| 构件 | WILD type | 精确参数 | 数量 |
|:---:|:---:|:---|:---:|
| 看台踏步 | `floor` | 逐级抬高, 坡度28~34°, 视线C值法 | 20~40 |
| 疏散楼梯 | `stair` | width=1.4m, autoRailing=true, 分布于看台四周 | 8~16 |
| 罩棚桁架 | `truss` | trussType=howe/pratt, 悬挑跨度30~70m, height=3~5m, memberProfile=rect | 30~60 |
| 膜结构屋面 | `roof` | roofType=flat(张拉膜), 或 custom | 1~3 |
| 外围环墙 | `wall` | thickness=0.3m, 椭圆形 curve=ellipse | 8~12 |
| 巨型柱 | `column` | crossSection=rectangular, 0.8×1.0m, style=modern | 20~40 |
| 看台栏杆 | `railing` | height=1.1m, infill=vertical_bar | 沿看台前沿 |
| 入口大门 | `opening`+`door` | w=3.0m, door:glass, leafCount=4 | 4~8 |

**罩棚桁架 WILD JSON 示例**

```json
{
  "type": "truss", "id": "canopy_truss_01",
  "from": [0, 30.0, 0], "to": [0, 30.0, 60.0],
  "height": 4.0,
  "trussType": "howe",
  "panelCount": 8,
  "memberProfile": "rect",
  "memberWidth": 0.15, "memberHeight": 0.25,
  "spacing": 6.0,
  "material": "steel_truss"
}
```

**关键规则**

> **看台坡度**：28~34°，按 C 值法视线设计
> **罩棚悬挑**：30~70m，用 `truss` howe/pratt
> **跨度与用钢量**：跨度增加一倍，用钢量可能增加 3~4 倍
> **总构件数**：约 **100~150 个**

**典型案例**：鸟巢（91,000 座，跨度 296m）、水立方（ETFE 气枕膜结构）

---

## 2.6 医疗建筑

> 规范依据：GB 51039-2014《综合医院建筑设计标准》（原 JGJ 49）

**功能区构件清单**

| 功能区 | 构件 | WILD type | 精确参数 |
|:---:|:---|:---:|:---|
| **门诊楼** | 候诊大厅柱 | `column` | square 0.5m, 间距6~9m, 层高3.6~4.2m |
| | 诊室隔墙 | `wall` | 0.12m, 开间≥3.0m, 进深≥3.9m, 面积≥12m² |
| | 诊室门 | `opening`+`door` | w=1.0m, h=2.1m, door:panel, **附观察窗** |
| | 诊室窗 | `opening`+`window` | window:casement, w=1.5m |
| **医技楼** | CT/MRI机房墙 | `wall` | thickness=0.5m+, 铅板/硫酸钡防辐射 |
| | 设备楼板 | `floor` | thickness=0.20m+, 荷载加大 |
| | 手术室墙 | `wall` | 洁净无缝, thickness=0.15m, 材质=抗菌板 |
| | 手术室门 | `door` | style=flush, **气密门**, w=1.4m |
| | 手术室净高 | — | ≥2.7m, 层流净化 |
| **住院楼** | 病房墙 | `wall` | 0.12m, 病房3.6×7.5m, 南向 |
| | 病房门 | `door` | w=0.9m, h=2.1m, flush |
| | 病房窗 | `window` | casement, w=1.8m, glassOpacity=0.35 |
| | 卫生间门 | `door` | w≥1.1m(无障碍), flush |
| | 护士站 | `wall`(半围合) | 每护理单元中心 |
| | 污物通道 | `wall` | 独立竖井, 与洁物完全分离 |

**关键规则卡**

> **洁污分流**：最核心规则！污物通道与洁物通道完全独立
> **手术室净高 ≥2.7m**，洁净走廊净宽 ≥2.5m
> **门诊诊室**：开间≥3.0m，进深≥3.9m，面积≥12m²
> **病房净高 ≥2.8m**，卫生间净高 ≥2.4m
> **手术室门净宽 ≥1.4m**（手术车进出）

**典型案例**：北京协和医院、深圳中医院光明院区、火神山医院（10 天建成）

---

## 2.7 交通建筑

**构件清单**

| 子类 | 构件 | WILD type | 精确参数 |
|:---:|:---|:---:|:---|
| **航站楼** | 办票大厅柱 | `column` | rectangular 0.8×1.0m, 间距50~100m(少柱) |
| | 超大跨屋盖 | `truss` | trussType=warren, span=50~100m, height=5~8m |
| | 屋面 | `roof` | roofType=flat/curved, 跨度50~100m |
| | 幕墙 | `wall` | 玻璃超大板块, 高透光 |
| | 登机廊桥 | `ramp` | 可伸缩, slope=auto |
| | 行李夹层 | `floor` | 设备夹层, thickness=0.20m |
| **火车站** | 候车大厅柱 | `column` | rectangular 0.6×0.8m, 间距40~80m |
| | 屋盖桁架 | `truss` | trussType=pratt, span=40~80m |
| | 站台雨棚 | `roof` + `column` | 半室外, roofType=flat, 挑檐 |
| | 进出站通道 | `floor` + `stair` | 地下通道, 立体分流 |

**关键规则**：航站楼因超大空间无法按标准规范设计防火分区，必须用**性能化消防设计**（CFD 烟气模拟）。

**典型案例**：北京大兴国际机场（Zaha Hadid，700,000 m²，五指廊放射状）

---

## 2.8 园林/纪念/司法

**园林建筑构件清单**（联网搜索中国传统建筑数据）

| 构件 | WILD type | 精确参数 | 说明 |
|:---:|:---:|:---|:---|
| 木柱 | `column` | crossSection=circular, style=chinese_wooden, bottomRadius=0.18~0.25m, 柱径6~8斗口 | 檐柱/金柱/中柱/山柱 |
| 额枋(梁) | `beam` | crossSection=rect, 0.15×0.25m, 连接柱头 | 大额枋/小额枋 |
| 斗拱 | `truss`(简化) | 或 `dense_brick`(精细), 位于柱头 | 预留构件 |
| 曲面屋顶 | `roof` | roofType=chinese_curved, 出檐外挑eaveOutset=1.0~2.0m | 庑殿/歇山/悬山/硬山 |
| 重檐屋顶 | `roof` | roofType=chinese_pagoda, tiers=2~3, tierHeight, shrinkFactor | 塔/祈年殿 |
| 隔扇门 | `opening`+`door` | style=rectangular, door:panel, 格心+裙板+绦环板, muntinPattern=grid | 槛框内安装 |
| 槛窗 | `opening`+`window` | window:casement, muntinPattern=colonial, 格心木棂条 | 下槛上方 |
| 漏窗 | `opening` | style=circular/rectangular, muntion pattern=custom | 园林墙洞 |
| 廊梁 | `beam` | crossSection=rect, 廊道水平连接 | 廊道 |
| 美人靠栏杆 | `railing` | height=0.5m, infill=none, path沿廊道边缘 | 曲线扶手 |
| 台基 | `floor` | shape=rect, 厚度0.3~1.0m, 露明高度=檐柱高×1/10 | 须弥座/普通台基 |
| 坡道 | `ramp` | surface=grooved, 垂带踏跺 | 台阶 |

**中式古建 WILD JSON 示例**

```json
{
  "type": "column", "id": "eave_col_01",
  "base": [0, 0, 0], "height": 4.5,
  "crossSection": "circular",
  "bottomRadius": 0.22, "topRadius": 0.20,
  "style": "chinese_wooden", "flutes": 16,
  "material": "wood_red"
}
```

**纪念建筑**：`wall`(简洁肃穆) + `column`(纪念柱, doric风格) + `floor`(广场)

**司法建筑**：`wall`(法庭围合) + `column`(庄严, doric) + `stair`(法官/被告/旁听三线分离)

**典型案例**：祈年殿（chinese_pagoda, tiers=3）、拙政园（园林）、人民英雄纪念碑

---
