---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: tower
topic: definition
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/catalog/towers.md
keywords:
  - 塔楼
  - tower
  - 石塔
---

# 轻量建筑分类：塔楼（Tower）

> 来源：从旧版根目录轻量建筑类型参考库拆分。
> 用途：当用户模糊请求“生成一个塔楼”时，提供默认语义入口、常见变体和最少可行版本。
> RAG 关键词：塔楼、Tower、中世纪石塔、观景塔、高塔、默认塔楼

---
## 塔楼（Tower）

塔楼是多层垂直结构，层高较低，平面面积小，层数多（3~8层）。常见于城堡、灯塔、钟楼。

### 标准功能分区

| 区域 | 层位 | 核心构件 |
|------|------|---------|
| 底座 | 底部 1~2层 | floor + wall（较厚，0.5~0.8m）|
| 标准层 | 中间各层 | wall × 4 + floor + opening（箭孔/窗）|
| 顶层 | 最高层 | wall + 垛口（用 column 模拟）|
| 塔顶 | 屋顶 | roof（gable 或 hip，坡度陡）|
| 楼梯 | 内部贯通 | stair × (层数-1) |

### 变体 A：中世纪石塔（4层）

**构件清单**：
- floor × 4（每层楼板）
- wall × 16（每层4面，共4层，越高越薄）
- opening × 12（每层3个箭孔/窗，底层1个门）
- stair × 3（连接1-2层、2-3层、3-4层）
- roof × 1（hip 或 gable，高耸，height = span × 0.8）

**典型尺寸**：
- 平面：4m × 4m
- 各层高：3m（共12m总高）
- 底层墙厚：0.8m；顶层墙厚：0.4m
- 窗/箭孔：宽0.4m，高0.8m

**材质建议**：
- 墙体：粗糙石材 baseColor [0.50, 0.47, 0.43]，roughness 0.95
- 楼板：石板 baseColor [0.55, 0.52, 0.48]
- 屋顶：深灰石板 baseColor [0.35, 0.35, 0.35]

---
