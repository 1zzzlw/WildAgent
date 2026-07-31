---
doc_type: recipe
doc_scope: generation
knowledge_layer: architecture
entity_type: assembly
entity_name: building_assembly_templates
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: recipes/assembly-templates.md
keywords:
  - 组装模板
  - assembly
  - 低层建筑
  - 高层建筑
  - 大跨公建
---

# 四大构件组装模板

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理低层建筑、高层建筑、大跨公建、温室/养殖等跨建筑复用组装顺序。
> RAG 关键词：组装模板、低层建筑、高层建筑、大跨公建、温室、养殖、column、floor、wall、roof、truss

---
## 五、构件组装规则总表

### 5.1 四大组装模板

**模板 A：低层建筑**（别墅/园林/纪念/农机站）

```
column → floor(地基) → wall(围护) → opening(洞口) → door+window → stair → roof → railing
```

**模板 B：高层建筑**（住宅/办公/酒店/住院楼）

```
wall(核心筒) → column(外框) → beam(主梁) → floor(楼板) → wall(隔墙) → opening → door+window
→ stair → [避难层floor] → 逐层重复
```

**模板 C：大跨公建**（体育场/航站楼/剧院/厂房）

```
column(巨柱) → truss(桁架/网壳) → roof(屋面) → wall(局部围护) → floor(看台/地坪) → stair → railing
```

**模板 D：温室/养殖**（轻钢农业）

```
column(钢立柱) → truss(拱形轻桁架) → wall(透明/夹芯板) → roof(采光顶) → opening(通风) → furniture(苗床)
```
