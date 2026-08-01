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

# 轻量建筑类型与分类路由目录

> 用途：存放用户用建筑名称模糊请求时的默认语义入口，并把尚无详细配方的名称路由到七大建筑分类。

## 与其他目录的关系

- `catalog/`：轻量入口，回答“这个建筑名属于什么”和“已有配方在哪里”。
- `residential/`、`public/`、`industrial/`、`agricultural/`：按建筑用途组织的深度构件配方。
- `components/`：单个构件族的分类、参数和组装规则。
- `recipes/`：跨构件、跨建筑类型的组装模板和速查矩阵。

## 当前条目

| 文件 | 内容 |
|---|---|
| `building-type-taxonomy.md` | 七大类、165+ 建筑名称的轻量分类与知识路由，不含详细生成配方 |
| `villas.md` | 别墅轻量默认参考 |
| `pavilions.md` | 凉亭、廊架轻量默认参考 |
| `cabins.md` | 小屋、木屋轻量默认参考 |
| `courtyards.md` | 院落、庭院轻量默认参考 |
| `towers.md` | 塔楼轻量默认参考 |

## 分类入口的能力边界

轻量分类首先解决名称识别和知识路由问题；它不会为缺失的建筑类型自动补齐尺寸、构件参数、组装顺序或有效 JSON。

- 分类条目用于意图识别，不是 WILD 构件类型。
- 只有分类名称而没有详细文档时，生成必须采用已支持构件的简化版本。
- 来源目录中的模板 A～Y 缺少组装步骤和已验证示例，当前不作为正式 recipe 使用。
