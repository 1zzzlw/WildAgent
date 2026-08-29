---
entity_name: pavilion
topic: assembly
status: experimental
authority: domain_reference
source: building_types/catalog/pavilions.md
primary_terms:
  - 凉亭
  - 廊架
  - 中式亭
synonyms:
  - pavilion
---

# 轻量建筑分类：凉亭（Pavilion）

> 来源：从旧版根目录轻量建筑类型参考库拆分。
> 用途：当用户模糊请求“生成一个凉亭”时，提供默认语义入口、常见变体和最少可行版本。
> RAG 关键词：凉亭、Pavilion、中式四角凉亭、中式八角凉亭、现代廊架、亭子、默认凉亭

---
## 凉亭（Pavilion）

凉亭是供休憩观景的开放或半开放构筑物，通常无墙或仅有矮墙，以柱支撑屋顶为核心结构。

### 标准功能分区

| 区域 | 位置 | 核心构件 |
|------|------|---------|
| 台基 | 底部 | floor（台面）、可选台阶 stair |
| 柱网 | 台基四角或周边 | column × 4~8 |
| 连系梁 | 柱顶 | beam（连接相邻柱子的横梁） |
| 屋顶 | 柱网之上 | roof（单层或双层） |
| 坐凳 | 可选，台基边缘 | floor（凳面）+ column（凳腿）|
| 栏杆 | 可选，台基边缘 | column（矮柱）+ beam（横档）|

<!-- rag-meta
entity_type: building
entity_name: chinese_square_pavilion
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 中式四角凉亭
  - 四角亭
  - 中式凉亭
synonyms:
  - chinese square pavilion
-->

### 变体 A：中式四角凉亭

**构件清单**：
- floor × 1（台基，厚 0.3~0.5m）
- column × 4（四角檐柱，高 3m，bottomRadius 0.12m）
- beam × 4（檐枋，连接四柱顶端形成方框）
- roof × 1（gable 或 hip，span/depth 比柱网各大 1~1.5m）

**典型尺寸**：
- 柱网：3m × 3m（柱心距）
- 柱高：3.2m
- 台基：4m × 4m，高出地面 0.4m
- 屋顶：span 5m，depth 5m，height 1.8m，position 在柱顶

**材质建议**：
- 柱/梁：红木 baseColor [0.50, 0.18, 0.08]
- 台基：青石 baseColor [0.55, 0.57, 0.55]
- 屋顶：青瓦 baseColor [0.28, 0.32, 0.30]

---

<!-- rag-meta
entity_type: building
entity_name: chinese_octagonal_pavilion
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 中式八角凉亭
  - 八角亭
  - 八角凉亭
synonyms:
  - chinese octagonal pavilion
-->

### 变体 B：中式八角凉亭

**构件清单**：
- floor × 1（八边形台基，用多个 floor 拼合）
- column × 8（八角均布，高 3~3.5m）
- beam × 8（连接相邻柱顶）
- roof × 1（hip 四坡，或用两层叠加模拟重檐）
- stair × 1（台阶入口）

**说明**：wild-core 暂不支持八边形 floor，用 3~4 个矩形 floor 交叠拼近似八边形。

---

<!-- rag-meta
entity_type: building
entity_name: modern_pergola
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 现代廊架
  - 廊架
  - 花园廊架
  - 停车棚
synonyms:
  - pergola
-->

### 变体 C：现代简约廊架

**构件清单**：
- column × 4~6（方形截面，style: modern，间距 3m）
- beam × 3~5（横跨柱顶的主梁）
- beam × 6~10（次梁，垂直于主梁，间距 0.6m，形成格栅顶）
- floor × 1（可选地面铺装）

**用途**：花园廊架、停车棚、户外休息区。

---

### 构件最少可行版本

```
四角凉亭
- 台基 floor 1个，4m×4m
- 柱 column ×4，高3m，置于台基四角
- 檐枋 beam ×4，连接柱顶
- 屋顶 roof ×1，gable，span 5m，depth 5m，height 1.8m
```

---
