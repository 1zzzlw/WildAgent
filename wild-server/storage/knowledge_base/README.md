---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: knowledge_base_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: README.md
keywords:
  - WILD 知识库
  - 文档分类
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

| 类别 | `doc_type` | `entity_type` | 默认 `doc_scope` |
|---|---|---|---|
| 完整或精简 WILD 规范 | `blueprint_spec` | `schema` | `generation` / `system` |
| 建筑类型与轻量目录条目 | `building_type` | `building` | `generation` |
| 单一构件族 | `component` | 对应构件类型 | `generation` |
| 跨构件组装与矩阵 | `recipe` | `assembly` | `generation` |
| 用户确认的项目经验 | `pattern` | 对应业务实体 | `generation` |
| 各级 README | `index` | `index` | `index` |

现有建筑、构件和配方资料来自领域整理，尚未逐项通过当前引擎验证，因此统一标记为 `status: experimental`、`authority: domain_reference`。只有当前 Schema 文档标记为 `supported`。

## 新增文档模板

```md
---
doc_type: component
doc_scope: generation
knowledge_layer: architecture
entity_type: window
entity_name: example_entity
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: components/example.md
keywords:
  - 中文关键词
  - English keyword
  - WILD type
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
