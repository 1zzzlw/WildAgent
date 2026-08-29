---
entity_name: courtyard
topic: assembly
status: experimental
authority: domain_reference
source: building_types/catalog/courtyards.md
primary_terms:
  - 院落
  - 庭院
  - 四合院
synonyms:
  - courtyard
---

# 轻量建筑分类：院落 / 庭院（Courtyard）

> 来源：从旧版根目录轻量建筑类型参考库拆分。
> 用途：当用户模糊请求“生成一个庭院”时，提供默认语义入口、常见变体和最少可行版本。
> RAG 关键词：院落、庭院、Courtyard、四合院、地中海庭院、默认庭院

---
## 院落 / 庭院（Courtyard）

院落是以围合墙体或廊道形成内向庭院的建筑群，常见于中式四合院、地中海民居等。

### 标准功能分区

| 区域 | 位置 | 核心构件 |
|------|------|---------|
| 院墙 | 外围四周 | wall × 4（围合，矮于建筑本体）|
| 院门 | 院墙开口 | door × 1（大门，或带门楼）|
| 庭院地面 | 围合内部 | floor × 1（铺装地面）|
| 正房 | 北侧（主屋） | wall × 4 + door/window + roof |
| 厢房 | 东西两侧 | wall + door/window + roof（较小）|
| 倒座 | 南侧（辅屋） | wall + door/window + roof（可选）|
| 廊道 | 连接各房间 | column + beam + roof（单坡廊）|
| 景观 | 庭院内 | column（假山柱）、floor（水池）等 |

<!-- rag-meta
entity_type: building
entity_name: northern_courtyard
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 北方四合院
  - 四合院
  - 北京四合院
synonyms:
  - siheyuan
-->

### 变体 A：北方四合院（简化版）

**构件清单**：
- floor × 1（院内地面）
- wall × 4（院墙，高 2m，厚 0.4m）
- door × 1（院门，宽 2m，高 2.5m，居南墙中央）
- 正房：wall × 4，高 3.5m；door × 1（中门）+ window × 2；roof × 1（gable）
- 东厢房：wall × 4，高 3.2m；door × 1 + window × 1；roof × 1（gable）
- 西厢房：同东厢房（镜像）
- 廊道：column × 6~8（连接正房与厢房的檐廊柱）；beam × 6~8；roof × 2（单坡廊顶）

**典型尺寸**：
- 院落总尺寸：16m × 18m
- 院墙高：2m
- 正房：12m × 6m，层高 3.5m
- 厢房：6m × 4m，层高 3.2m
- 廊道宽：1.8m

---

<!-- rag-meta
entity_type: building
entity_name: mediterranean_courtyard
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 地中海庭院
  - 地中海小庭院
synonyms:
  - mediterranean courtyard
-->

### 变体 B：地中海小庭院

**构件清单**：
- floor × 1（庭院铺装，石板）
- wall × 4（外围墙，白色抹灰，高 2.5m）
- column × 6~8（回廊拱柱，白色，style: classical）
- beam × 6~8（廊道连梁）
- roof × 2~4（各房间独立坡顶）
- window × 多（窗户较多，拱形风格用 rectangular 近似）

---
