---
entity_name: cabin
topic: definition
status: experimental
authority: domain_reference
source: building_types/catalog/cabins.md
primary_terms:
  - 小屋
  - 木屋
synonyms:
  - cabin
---

# 轻量建筑分类：小屋 / 木屋（Cabin）

> 来源：从旧版根目录轻量建筑类型参考库拆分。
> 用途：当用户模糊请求“生成一个木屋”时，提供默认语义入口、常见变体和最少可行版本。
> RAG 关键词：小屋、木屋、Cabin、标准木屋、前廊木屋、默认木屋

---
## 小屋 / 木屋（Cabin）

小屋是单层或低矮的简单住宅，结构简单，空间紧凑，常见于山地、林间或农村。

### 标准功能分区

| 区域 | 位置 | 核心构件 |
|------|------|---------|
| 地基 | 底部 | floor × 1 |
| 外墙 | 四周 | wall × 4 |
| 门窗 | 外墙开口 | opening：门×1，窗×2~4 |
| 屋顶 | 顶部 | roof × 1（gable 双坡为主） |
| 前廊 | 可选，正面外延 | floor + column × 2 + beam × 1 |
| 烟囱 | 可选，屋顶侧面 | column（烟囱体）+ floor（顶盖）|

### 变体 A：标准木屋

**构件清单**：
- floor × 1（地基）
- wall × 4（外墙，木板材质）
- opening × 3（正门1 + 前窗1 + 侧窗1）
- roof × 1（gable，坡度较陡：height = span × 0.5）

**典型尺寸**：
- 占地：5m × 4m
- 层高：2.8m
- 屋顶：span 6m，depth 5m，height 3m

**材质建议**：
- 外墙/屋顶：原木 baseColor [0.45, 0.28, 0.12]
- 地基：石材 baseColor [0.62, 0.59, 0.55]

---

### 变体 B：带前廊木屋

在标准木屋基础上，正面增加：
- floor × 1（前廊地面，从正面墙外延 2m）
- column × 2（前廊两侧支柱）
- beam × 1（门廊横梁，连接两柱顶）
- roof（主屋顶 depth 延伸覆盖前廊，或单独 flat 小雨棚）

---

### 构件最少可行版本

```
单层木屋
- 地基 floor ×1，5m×4m
- 外墙 wall ×4
- 正门 opening ×1（宽0.9m，高2.0m）
- 前窗 opening ×2（宽1.0m，高0.9m，台高1.0m）
- 屋顶 roof ×1，gable，span 6m，depth 5m，height 2.5m
```

---
