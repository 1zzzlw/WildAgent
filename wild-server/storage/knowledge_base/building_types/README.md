---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: building_types_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: building_types/README.md
keywords:
  - 建筑类型索引
  - building types
  - 建筑分类
---

# 建筑类型知识索引

> 分类来源：用户提供的《建筑类型分类体系_总目录.md》及现有建筑类型文档。
> 用途：供维护者查看分类覆盖和详细配方位置；本 README 不进入普通生成召回。

## 七大建筑分类与当前覆盖

| 建筑大类 | 轻量分类入口 | 当前详细配方覆盖 |
|---|---|---|
| 居住建筑 | `catalog/building-type-taxonomy.md` | `residential/villas.md`、`residential/housing-dormitories-hotels.md`、`residential/extended-residential-types.md` |
| 公共建筑 | `catalog/building-type-taxonomy.md` | `public/education-office-culture.md`、`public/commercial-sports-medical-transport-other.md`、`public/public-building-subtypes.md` |
| 工业建筑 | `catalog/building-type-taxonomy.md` | `industrial/factories-and-warehouses.md` |
| 农业建筑 | `catalog/building-type-taxonomy.md` | `agricultural/agricultural-buildings.md` |
| 市政基础设施 | `catalog/building-type-taxonomy.md` | 尚无详细生成配方 |
| 景观小品与纪念性建筑 | `catalog/building-type-taxonomy.md` | 凉亭、塔楼可参考 `catalog/pavilions.md`、`catalog/towers.md` |
| 特殊专项建筑 | `catalog/building-type-taxonomy.md` | 尚无详细生成配方 |

## 目录职责

| 子目录 | 内容 |
|---|---|
| `catalog/` | 模糊建筑名称的默认语义、分类词典和详细文档路由 |
| `residential/` | 别墅、普通住宅、宿舍、酒店等居住或类居住建筑 |
| `public/` | 教育、办公、文化、商业、体育、医疗、交通等公共建筑 |
| `industrial/` | 厂房、工业上楼和仓储建筑 |
| `agricultural/` | 温室、畜禽饲养场、粮仓和农机站 |

## 使用约束

本索引只说明知识文件的覆盖范围，不参与普通蓝图生成；需要生成时应继续读取相应的轻量分类或详细配方文档。

- 分类目录中的建筑名称不等于 WILD `type`。
- “已收录分类”不等于“已有完整生成配方”，详细覆盖以上表为准。
- 模板 A～Y 目前只有目录名称，没有足够事实形成正式 `recipes/` 文档。
