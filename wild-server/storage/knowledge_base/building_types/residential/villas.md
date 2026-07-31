---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: villa
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/residential/villas.md
keywords:
  - 别墅
  - villa
  - 现代别墅
  - 中式传统别墅
  - 新中式别墅
---

# 居住建筑：别墅

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理现代别墅、中式传统别墅、新中式别墅等低层别墅的构件配方。
> RAG 关键词：别墅、现代别墅、中式别墅、新中式别墅、低层住宅、架空层、四合院、江南民居

---
## 1.1 别墅（低层 1~3F）

> 别墅按建筑风格可分为**现代别墅**、**中式传统别墅**、**新中式别墅**、**欧式别墅**等。以下按风格给出构件配方。

---

### 1.1.1 现代别墅（架空层）

<!-- rag-meta
entity_type: building
entity_name: modern_villa
topic: assembly
status: experimental
authority: domain_reference
keywords: 现代别墅, modern villa, 架空层
-->

> 图示：现代别墅结构示意图（原始资源：`docs/建筑类型分类体系_images/01_现代别墅.png`）

**构件清单**

```
column(架空柱) ─→ floor(底层架空板) ─→ wall(外围护墙) ─→ opening(水平长窗)
      │                                      │
      └─→ floor(二层悬挑板) ─→ floor(屋顶板)  └─→ wall(弧形入口墙)
```

| 构件 | WILD type | 精确参数 | 数量 |
|:---:|:---:|:---|:---:|
| 架空柱 | `column` | crossSection=circular, style=modern, bottomRadius=0.15m, topRadius=0.15m, height=3.0m, flutes=32, material=white_concrete | 16~20 |
| 底层楼板 | `floor` | from=[x,0,z] to=[x,0.15,z], thickness=0.15m, shape=rect, material=white_concrete | 1 |
| 二层悬挑板 | `floor` | from=[-0.75,3.0,-0.75] to=[21.75,3.15,18.75], thickness=0.15m | 1 |
| 外围护墙 | `wall` | thickness=0.15m, height=3.0m, curve=line, material=white_concrete | 4 |
| 弧形入口墙 | `wall` | thickness=0.15m, curve=arc, center=[x,0,z], sweep=-180°, segments=32 | 1 |
| 水平带状窗 | `opening` | parentWall=wall_id, from=[偏移,1.0,0], width=14~17m, height=1.1m, style=rectangular | 4 |
| 平屋顶板 | `floor` | 顶板，可上人做屋顶花园 | 1 |
| 室内楼梯 | `stair` | from=[x,0,z] to=[x,3.0,z], width=1.0m, autoRailing=true | 1 |
| 入口雨棚 | `canopy` | parentWall=wall, anchor=入口上方, projection=1.2m, supportType=bracket, material=white_concrete | 1 |
| 无障碍坡道 | `ramp` | from=[x,0,z] to=[x,0.15,z], width=1.2m, slope=1:12, surface=brushed(入口) | 1 |

**门窗规格**

| 部位 | opening style | door style | window sashType | 尺寸 |
|:---:|:---:|:---:|:---:|:---|
| 入口门 | arched | panel, leafCount=1, hingeSide=left | — | w=1.2m, h=2.4m |
| 水平长窗 | rectangular | — | fixed, glassOpacity=0.35 | w=14~17m, h=1.1m |
| 屋顶采光 | circular | — | fixed | d=1.5m |

**WILD JSON 示例**

```json
{
  "type": "column", "id": "pilotis_01",
  "base": [0, 0, 0], "height": 3.0,
  "crossSection": "circular",
  "bottomRadius": 0.15, "topRadius": 0.15,
  "style": "modern", "flutes": 32,
  "material": "white_concrete"
}
```

**组装顺序**：column → floor(底层) → floor(二层悬挑) → wall(外围护) → wall(弧形入口) → opening(长窗) → door(入口) → stair → floor(屋顶板)

**总构件数**：约 35 个

**典型案例**：萨伏耶别墅（勒·柯布西耶，底层 16 根 pilotis + 水平长窗 + 平屋顶花园）

---

### 1.1.2 中式传统别墅（四合院/江南民居）

<!-- rag-meta
entity_type: building
entity_name: traditional_chinese_villa
topic: assembly
status: experimental
authority: domain_reference
keywords: 中式传统别墅, Chinese villa, 四合院, 江南民居
-->

> 图示：中式别墅结构示意图（原始资源：`docs/建筑类型分类体系_images/06_中式别墅.png`）

> 依据：《清式营造则例》、GB 50352-2019。传统中式别墅采用**木构架承重体系**，"墙倒屋不塌"。

**构件清单**

| 构件 | WILD type | 精确参数 | 数量 |
|:---:|:---:|:---|:---:|
| 檐柱 | `column` | crossSection=circular, style=chinese_wooden, bottomRadius=0.18~0.25m, topRadius=0.20m(卷杀), height=3.0~4.5m, material=wood_red | 20~40 |
| 金柱 | `column` | crossSection=circular, style=chinese_wooden, bottomRadius=0.20~0.28m, height=4.5~6.0m | 4~8 |
| 额枋/梁 | `beam` | crossSection=rect, width=0.15m, height=0.25m, from檐柱to檐柱, style=chinese_wooden | 10~20 |
| 檩条 | `beam` | crossSection=circular, radius=0.08~0.12m, 架于梁上 | 20~40 |
| 砖墙(围护) | `wall` | thickness=0.24m(青砖), 非承重, curve=line, material=grey_brick | 4~8 |
| 丝缝内墙 | `wall` | thickness=0.12m(丝缝), 白灰膏勾缝 | 4~8 |
| 砖台基 | `floor` | shape=rect, thickness=0.30~1.0m, 须弥座或普通台基, material=stone | 1 |
| 举折屋面 | `roof` | roofType=chinese_curved, eaveOutset=1.0~2.0m, 瓦作小青瓦, material=grey_tile | 1~3 |
| 隔扇门(正房) | `opening` + `door` | opening: arched/rectangular, w=1.0m, h=2.4m; door: panel, leafCount=2, muntinPattern=grid(灯笼框/步步锦) | 4~8 |
| 槛窗(次间) | `opening` + `window` | window: casement, w=0.9m, h=1.5m, muntinPattern=grid(龟背锦/方格) | 4~8 |
| 漏窗(影壁/院墙) | `opening` | style=circular, w=0.6m, h=0.6m, muntinPattern=custom | 2~4 |
| 飞檐檐口 | `cornice` | parentWall=roof, profile=curved_eave, position=top | 1 |
| 垂花门(二进院) | `opening` + `door` | opening: arched, w=1.2m, h=2.6m; door: panel, leafCount=2, 垂莲柱装饰 | 1 |
| 游廊 | `beam` + `railing` | beam: crossSection=rect, 0.10×0.15m; railing: height=0.5m, infill=none(美人靠) | 2~4 |
| 庭院踏步 | `ramp` | surface=grooved, 垂带踏跺, slope=1:3 | 1~2 |
| 影壁墙 | `wall` | thickness=0.24m, height=2.5m, material=grey_brick_with_carving | 1 |
| 砖细贴附 | `placement` | onSurface.parent=wall, 砖雕图案 | 1 |

**WILD JSON 示例（中式檐柱）**

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

**组装顺序**：floor(台基) → column(檐柱/金柱) → beam(额枋/梁) → beam(檩条) → roof(举折屋面) → cornice(飞檐) → wall(围护砖墙) → wall(内墙) → opening(隔扇门/槛窗) → door + window → railing(美人靠) → placement(砖雕)

**总构件数**：约 **60~100 个**

**典型案例**：北京四合院、苏州拙政园住宅部、徽派民居（马头墙+白墙黛瓦）

---

### 1.1.3 新中式别墅（现代材料+传统美学）

<!-- rag-meta
entity_type: building
entity_name: new_chinese_villa
topic: assembly
status: experimental
authority: domain_reference
keywords: 新中式别墅, new Chinese villa, 现代材料
-->

> 图示：新中式别墅结构示意图（原始资源：`docs/建筑类型分类体系_images/07_新中式别墅.png`）

> 新中式=现代框架结构+传统形制抽象。钢筋混凝土替代木构架，保留坡屋顶、灰瓦、白墙、木格栅等视觉符号。

**构件清单**

| 构件 | WILD type | 精确参数 | 数量 |
|:---:|:---:|:---|:---:|
| 框架柱 | `column` | crossSection=square, side=0.3m, style=modern, height=3.0~3.6m, C30混凝土 | 12~20 |
| 主梁 | `beam` | crossSection=rect, width=0.25m, height=0.50m, 现代简约 | 10~15 |
| 楼板 | `floor` | thickness=0.12m, 现浇混凝土 | 2~3 |
| 白色外墙 | `wall` | thickness=0.20m, 白色弹性涂料/真石漆, material=white_plaster | 4~6 |
| 青砖勒脚 | `wall` | thickness=0.24m, height=0.30m(勒脚), material=grey_brick | 4~6 |
| 双坡屋顶 | `roof` | roofType=gable, slope=30°, 仿古小青瓦/钛锌板, eaveOutset=0.6m | 1~3 |
| 对坡屋顶 | `roof` | roofType=hip, 四坡顶, 呼应传统庑殿 | 1 |
| 大面积落地窗 | `opening` + `window` | opening: rectangular, w=2.4~4.0m, h=2.7m; window: fixed, glassOpacity=0.35, 断桥铝+Low-E中空 | 4~8 |
| 木格栅隔断 | `opening` + `mullion` | mullion: pattern=grid, cols=4, rows=6, material=wood_red | 2~4 |
| 入户门 | `opening` + `door` | opening: rectangular, w=1.2m, h=2.4m; door: panel, leafCount=2, 铝包木 | 1 |
| 铝包木窗 | `opening` + `window` | window: casement, w=1.5m, h=1.8m, 中空玻璃, K值≤2.0 | 6~12 |
| 门廊雨棚 | `canopy` | parentWall=wall, anchor=入户门上方, projection=1.5m, supportType=bracket | 1 |
| 烟囱 | `chimney` | base=[x,y,z], height=4.0m, crossSection=square, penetrateRoof=true | 1~2 |
| 地下室采光井 | `opening` | style=rectangular, w=1.0m, h=1.0m, 地面天窗 | 2~4 |
| 庭院地形 | `terrain` | origin=[x,0,z], size=20×30m, heightmap=gentle_slope, 枯山水/镜面水景 | 1 |
| 无障碍坡道 | `ramp` | from=[x,0,z] to=[x,0.15,z], width=1.2m, slope=1:12, surface=brushed | 1 |
| 室内楼梯 | `stair` | width=1.0m, autoRailing=true, 现代简约 | 1~2 |
| 阳台栏杆 | `railing` | height=1.1m, infill=glass, material=steel_railing | 2~4 |

**WILD JSON 示例（新中式屋顶）**

```json
{
  "type": "roof", "id": "gable_main",
  "position": [0, 6.0, 0], "span": 12.0, "depth": 15.0,
  "height": 3.5, "roofType": "gable",
  "slope": 30, "eaveOutset": 0.6,
  "material": "grey_tile"
}
```

**组装顺序**：terrain(庭院) → column(框架柱) → beam(主梁) → floor(楼板) → wall(白色外墙) → wall(青砖勒脚) → roof(双坡/四坡) → chimney → canopy(门廊) → opening(落地窗) → window → opening(入户门) → door → opening(格栅隔断) → mullion → ramp(无障碍) → stair → railing(阳台)

**总构件数**：约 **50~80 个**

**典型案例**：北京顺义南彩四合院（混凝土框架+青砖木装修）、锦绣五溪新中式别墅

---
