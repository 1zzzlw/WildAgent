---
entity_name: knowledge_base_index
status: supported
authority: maintainer
source: README.md
primary_terms:
  - WILD 知识库
  - 文档分类
synonyms:
  - knowledge base
---

# WILD 知识库索引

> 本目录下除 `BLUEPRINT-SPEC-MINIMAL.md` 外，所有 Markdown 都会被 `collect_markdown_paths()` 自动扫描并进入 RAG 分片；`doc_scope: index` 的 README 只用于导航，不进入普通生成召回。
> Markdown 链接不会被自动追踪；需要参与召回的内容必须实际放在本目录或子目录下。

## 目录职责

| 目录 / 文件 | 存放内容 | 建议粒度 |
|---|---|---|
| `BLUEPRINT-SPEC-MINIMAL.md` | 基础蓝图铁律，直接注入 System Prompt | 小而稳定，不放风格知识 |
| `BLUEPRINT-SPEC-FULL.md` | 完整 .wild 表达规范 | 完整规范，参与 RAG |
| `building_types/catalog/` | 轻量建筑类型默认语义参考 | 用户只说“别墅/木屋/凉亭/塔楼”时的默认入口 |
| `building_types/` | 按建筑用途分类的构件配方 | 一个文件对应一个建筑主题或小类集合 |
| `components/` | 按构件族分类的参数、变体、组装规则 | 一个文件对应墙/门/窗/屋顶等构件族 |
| `recipes/` | 跨构件组装模板和速查矩阵 | 说明一个建筑如何搭配和组装多个构件 |
| `patterns/` | 用户确认后的项目案例、偏好和可复用模式 | 一个条目一个 Markdown |

## 分类 metadata

`config.yaml` 保存可由路径稳定推断的公共默认值。Loader 的合并顺序是
`defaults → mapping_rules（按书写顺序）→ 当前 Markdown 文件头`，所以单个文件的
显式 frontmatter 始终拥有最高优先级。`entity_name`、`primary_terms` 和 `synonyms`
仍需按文档内容填写，不能仅凭目录名批量猜测。

| 类别 | `doc_type` | `entity_type` | 默认 `doc_scope` |
|---|---|---|---|
| 完整或精简 WILD 规范 | `blueprint_spec` | `schema` | `generation` / `system` |
| 建筑类型与轻量目录条目 | `building_type` | `building` | `generation` |
| 单一构件族 | `component` | 对应构件类型 | `generation` |
| 跨构件组装与矩阵 | `recipe` | `assembly` | `generation` |
| 用户确认的项目经验 | `pattern` | 对应业务实体 | `generation` |
| 各级 README | `index` | `index` | `index` |

当前 Schema、构件注册表、resolver 和经过源码核对的能力边界标记为 `supported`。建筑类型、风格和尺寸建议通常是 `experimental/domain_reference`；尚未进入 Schema 的专用构件及自动组合机制一律标为 `proposed`，默认生成检索会排除它们。

### `primary_terms` 和 `synonyms` 怎么区分

- `primary_terms`：实体正式名称、稳定的建筑/构件术语，以及当前 WILD 类型或字段。
- `synonyms`：与主术语可以互换的翻译、别名、俗称或用户常用说法。
- 只是“相关”不等于“同义”。例如 `opening` 是支摘窗的实现术语，应放主术语；
  `zhizhai window` 是“支摘窗”的英文检索写法，才放同义词。
- 两组不得重复；没有同义词时必须显式写 `synonyms: []`。
- legacy `keywords` 已停用，Loader 只为尚未迁移的外部文档保留兼容读取。

## 新增文档模板

```md
---
knowledge_layer: architecture
entity_type: window
entity_name: example_entity
topic: assembly
status: experimental
authority: domain_reference
source: components/example.md
primary_terms:
  - 中文主术语
  - WILD type
synonyms:
  - English alias
---

# 主题名称

> 来源：手工维护 / 用户确认 / 规范整理。
> 用途：说明这个文档回答哪类生成问题。
> RAG 关键词：关键词一、关键词二、WILD type、常见中文别名。

## 适用范围

## 构件清单

## 参数建议

## 组装规则

## 最少可行版本
```
