---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: building_catalog_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: building_types/catalog/README.md
keywords:
  - 轻量建筑目录
  - building catalog
  - 默认建筑
---

# 轻量建筑类型目录

> 用途：存放用户用一个建筑名模糊请求时的默认语义入口，例如别墅、凉亭、木屋、庭院、塔楼。
> RAG 关键词：建筑类型目录、默认建筑、轻量建筑分类、别墅、凉亭、木屋、庭院、塔楼。

## 与其他目录的关系

- `catalog/`：轻量入口，回答“用户只说一个建筑名时默认生成什么”。
- `residential/`、`public/`、`industrial/`、`agricultural/`：按建筑用途组织的深度构件配方。
- `components/`：单个构件族的分类、参数和组装规则。
- `recipes/`：跨构件、跨建筑类型的组装模板和速查矩阵。

## 当前条目

| 文件 | 内容 |
|---|---|
| `villas.md` | 别墅轻量默认参考 |
| `pavilions.md` | 凉亭/廊架轻量默认参考 |
| `cabins.md` | 小屋/木屋轻量默认参考 |
| `courtyards.md` | 院落/庭院轻量默认参考 |
| `towers.md` | 塔楼轻量默认参考 |
