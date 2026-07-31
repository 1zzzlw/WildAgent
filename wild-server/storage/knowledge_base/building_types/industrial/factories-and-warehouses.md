---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: industrial_building_family
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/industrial/factories-and-warehouses.md
keywords:
  - 工业建筑
  - 厂房
  - factory
  - 仓储
  - warehouse
---

# 工业建筑：厂房、工业上楼、仓储

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理单层重工业厂房、工业上楼、高层厂房、仓储建筑的构件配方。
> RAG 关键词：工业建筑、厂房、重工业厂房、工业上楼、高层厂房、仓库、仓储、门式刚架、桁架

---
## 三、工业建筑

---

### 3.1 单层重工业厂房

<!-- rag-meta
entity_type: building
entity_name: heavy_industrial_factory
topic: assembly
status: experimental
authority: domain_reference
keywords: 重工业厂房, industrial factory, 单层厂房
-->

> 图示：工业厂房结构示意图（原始资源：`docs/建筑类型分类体系_images/04_工业厂房.png`）

**构件清单**

| 构件 | WILD type | 精确参数 | 数量 |
|:---:|:---:|:---|:---:|
| 排架柱(阶形) | `column` | crossSection=rectangular, 上柱0.4×0.6m/下柱0.6×1.0m, height=12~25m, style=modern | 20~60 |
| 屋架桁架 | `truss` | trussType=howe/pratt, from/to=柱顶, height=2~4m, span=18~36m, panelCount=4~6 | 10~30 |
| 吊车梁 | `beam` | crossSection=i-beam, 承受50~150t动荷载, height=0.8~1.5m | 15~40 |
| 柱间支撑 | `beam` | 斜撑, X形交叉, crossSection=rect 0.2×0.3m | 10~20 |
| 屋盖支撑 | `beam` | 水平/垂直支撑, crossSection=rect 0.15×0.2m | 10~20 |
| 外围护墙 | `wall` | 彩钢夹芯板, thickness=0.05~0.08m(夹芯板) | 8~16 |
| 屋面 | `roof` | roofType=gable, 压型钢板, 有檩体系, 檩距1.5~3m | 1~3 |
| 天窗 | `opening` | parentWall=roof, style=rectangular, 屋脊排烟 | 2~6 |
| 工业大门 | `opening`+`door` | w=3~6m, h=4~6m, door:flush(推拉/卷帘), leafCount=2+ | 2~6 |
| 屋瓦贴附 | `placement` | onSurface.parent=roof, rows×cols网格 | 1 |

**排架柱 WILD JSON 示例**

```json
{
  "type": "column", "id": "frame_col_01",
  "base": [0, 0, 0], "height": 18.0,
  "crossSection": "rectangular",
  "bottomWidth": 0.6, "bottomDepth": 1.0,
  "topWidth": 0.4, "topDepth": 0.6,
  "style": "modern",
  "material": "grey_concrete"
}
```

**组装顺序**：column(排架柱) → beam(柱间支撑) → beam(吊车梁) → truss(屋架) → beam(屋盖支撑) → roof(屋面) → wall(彩钢板围护) → opening(天窗/大门) → door

**总构件数**：约 **60~150 个**

**典型案例**：宝钢热轧车间、特斯拉超级工厂（Gigafactory 3）

---

### 3.2 工业上楼（4F+ 高层厂房）

<!-- rag-meta
entity_type: building
entity_name: multistory_industrial_building
topic: assembly
status: experimental
authority: domain_reference
keywords: 工业上楼, multistory factory, 高层厂房
-->

**构件清单**

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 框架柱 | `column` | crossSection=square, side≥0.6m, style=modern, 首层层高≥6m |
| 承重楼板 | `floor` | thickness=0.20~0.30m, 首层荷载≥12kN/m², 2~3层≥8kN/m² |
| 主梁 | `beam` | rect 0.4×0.8m, 柱距≥8.4m |
| 货梯井 | `wall` | 围合竖井, thickness=0.20m, ≥2台/层, 载重≥3t |
| 装卸坡道 | `ramp` | width=4.0m, slope=1:8, surface=grooved |
| 设备管井 | `wall` | 密集竖井, 给排水/强弱电/压缩空气 |
| 外围护墙 | `wall` | 轻质, 大尺寸可开启窗 |
| 货梯门 | `door` | w=2.5m, h=3.0m, flush(工业门) |

**关键参数**：首层≥6m / 标准层≥4.5m / 柱距≥8.4m / 标准层面积≥2000m² / 限高≤100m

**典型案例**：深圳光明生物医药工业大厦（12F）

---

### 3.3 仓储建筑

<!-- rag-meta
entity_type: building
entity_name: warehouse
topic: assembly
status: experimental
authority: domain_reference
keywords: 仓储建筑, warehouse, 仓库
-->

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 外围护墙 | `wall` | height=6~24m, 无窗或少窗 |
| 大跨屋盖 | `roof` + `truss` | roofType=gable, trussType=pratt, span=20~60m |
| 装卸平台 | `floor` | 1.2m高台, 与货车车厢平齐 |
| 雨棚 | `canopy` | parentWall=wall, supportType=post, projection=3m |
| 装卸门 | `door` | w=3.0m, h=3.5m, flush(卷帘门) |
| 排烟天窗 | `opening` | 顶部, style=rectangular |

**典型案例**：京东"亚洲一号"智能物流仓库（AS/RS 立体库，高度 24m）

---
