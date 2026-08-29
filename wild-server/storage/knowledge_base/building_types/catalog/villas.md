---
entity_name: villa
topic: definition
status: supported
authority: domain_reference
source: building_types/catalog/villas.md
primary_terms:
  - 别墅
  - 现代别墅
  - 中式别墅
  - 欧式别墅
synonyms:
  - villa
---

# 轻量建筑分类：别墅（Villa）

> 来源：轻量建筑类型参考库入口。
> 用途：当用户模糊请求"生成一个别墅"时，提供默认语义入口并**路由到详细配方**。
> 详细 WILD Blueprint 配方见 `building_types/residential/villas.md`（现代 / 中式传统 / 新中式别墅的构件清单、典型尺寸、材质与最少可行版本）。

## 语义入口

别墅是独立式住宅，通常 2~3 层，有独立庭院，注重居住舒适性和外观美感。

- **现代简约别墅**：平屋顶或轻坡顶，大面积落地窗，白色涂料或清水混凝土外墙。→ 见 `residential/villas.md`
- **中式传统别墅**：双坡或歇山屋顶，外廊柱列，木构件为主，青砖或夯土外墙。→ 见 `residential/villas.md`
- **欧式别墅**：四坡屋顶，外立面装饰线脚，门廊罗马柱，拱形窗。→ 参考 `residential/villas.md` 的中式/新中式配方，按欧式特征调整屋顶（hip）与立面装饰。

> ⚠️ 本文档只做路由。构件的 WILD 字段、数量与 JSON 示例以 `residential/villas.md` 和 `BLUEPRINT-SPEC-MINIMAL.md` 为准，避免与详细配方产生双源冲突。

---
