---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: components_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: components/README.md
keywords:
  - 构件索引
  - components
  - WILD type
---

# 构件知识索引

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：记录“用什么构件、构件有哪些参数和变体”这类知识。
> RAG 关键词：WILD 构件、column、beam、floor、wall、roof、opening、door、window、mullion、stair、railing

---
## 零、WILD 构件速查

> 完整规范见《WILD蓝图构件与组合方式完整规范》，此处仅列本文用到的 22 种构件速查卡。

### 结构构件（承重骨架）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 柱子 | `column` | base, height, crossSection, style | 截面: circular/square/rectangular；风格: doric/ionic/corinthian/modern/chinese_wooden |
| 梁 | `beam` | from, to, crossSection, width, height | 截面: rect/circular/i-beam；支持曲线梁 |
| 楼板 | `floor` | from, to, thickness, shape | 形状: rect/circle；支持 surfaces 纹理 |
| 桁架 | `truss` | from, to, height, trussType | 形式: king_post/queen_post/fink/howe/pratt/warren |

### 围护构件（空间封闭）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 墙体 | `wall` | from, to, thickness, curve | 曲线: line/arc/ellipse/catenary |
| 屋顶 | `roof` | position, span, depth, height, roofType | 类型: gable/hip/dome/flat/chinese_curved/chinese_pagoda |
| 洞口 | `opening` | parentWall, from, width, height, style | 风格: rectangular/arched/gothic/circular |
| 门 | `door` | parentOpening, style, leafCount, hingeSide | 风格: flush/panel/glass/louvered |
| 窗 | `window` | parentOpening, sashType, muntinPattern | 窗扇: fixed/casement/sliding/awning/sash |
| 窗棂 | `mullion` | parentOpening, pattern, cols, rows | 图案: grid/vertical/horizontal/cross/custom |

### 辅助构件（功能附加）

| 构件 | type | 核心参数 | 变体 |
|:---:|:---:|:---|:---|
| 楼梯 | `stair` | from, to, width, stepCount, autoRailing | 自动推算踏步 |
| 坡道 | `ramp` | from, to, width, slope, surface | surface: flat/grooved/brushed |
| 栏杆 | `railing` | path, height, postSpacing, infill | 填充: none/vertical_bar/horizontal_bar/glass/mesh |
| 檐口 | `cornice` | parentWall, profile, position | position: top/bottom/middle |
| 烟囱 | `chimney` | base, height, crossSection, penetrateRoof | capType: none/simple/corbeled |
| 雨棚 | `canopy` | parentWall, anchor, projection, supportType | 支撑: none/bracket/post/cable |
| 家具 | `furniture` | position, dimensions, subtype | 子类型: table/chair/bed/lamp/bookshelf/tile |
| 贴附 | `placement` | onSurface.parent, rows, cols | 网格批量实例 |
| 地形 | `terrain` | origin, size, heightmap, surfaceZones | 高度图地表 |
| 模板 | `templates` | 定义 + instances 偏移复用 | 深拷贝批量生成 |

## 当前拆分

| 文件 | 内容 |
|---|---|
| `structural-components.md` | 柱、梁、楼板、桁架等承重骨架构件 |
| `walls.md` | 墙体分类、受力角色、材料、构造方式、模数规格 |
| `doors.md` | 门开启方式、中式/欧式/现代门组装公式、建筑速配 |
| `windows.md` | 窗开启方式、中式/欧式/现代窗组装公式、建筑速配 |
| `roofs-and-eaves.md` | 屋顶、檐口、雨棚等顶部和边缘围护构件 |
