# RAG Metadata 规范

metadata 用于过滤、追踪、父子关联和冲突处理，不能代替自包含正文。

## 文档级 Frontmatter

每份准备进入普通 RAG 的 Markdown 使用：

```yaml
---
doc_type: component
doc_scope: generation
knowledge_layer: architecture
entity_type: window
entity_name: window_family
topic: assembly
wild_version: "1.1"
status: supported
authority: schema
source: components/windows.md
keywords:
  - 窗
  - window
  - opening
---
```

README 和目录导航使用：

```yaml
---
doc_type: index
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: components_index
topic: navigation
wild_version: "1.1"
status: supported
authority: maintainer
source: components/README.md
keywords:
  - 构件索引
---
```

## 实体级覆盖

一个文件包含多个独立实体或变体时，在实体标题后使用 HTML 注释：

```md
## 支摘窗

<!-- rag-meta
entity_type: window
entity_name: zhizhai_window
topic: assembly
status: supported
authority: verified_example
keywords: 支摘窗, zhizhai window, opening
-->
```

`rag-meta` 只覆盖当前标题实体及其子标题；下一个同级或更高标题开始时结束。Loader 应把它解析进 metadata，并从展示正文中移除。

## 字段

| 字段 | 用途 | 建议值 |
|---|---|---|
| `doc_type` | 文档路由 | `component / building_type / recipe / blueprint_spec / pattern / index` |
| `doc_scope` | 检索范围 | `generation / index / system` |
| `knowledge_layer` | 知识层 | `architecture / constraint / wild_schema / project_pattern / navigation` |
| `entity_type` | 业务实体族 | `window / opening / wall / roof / stair / building / material / ...` |
| `entity_name` | 稳定英文 ID | 小写 snake_case |
| `topic` | 当前回答的问题 | `definition / schema / parameters / constraints / assembly / example / error / navigation` |
| `wild_version` | 适用版本 | 当前为 `"1.1"` |
| `status` | 能力状态 | `supported / experimental / proposed / deprecated` |
| `authority` | 事实依据 | `engine / schema / verified_example / maintainer / domain_reference / inferred` |
| `source` | 可追踪来源 | 知识库相对路径或源码位置 |
| `parent_id` | 可选父块 | 稳定 chunk/entity ID |
| `keywords` | 中英文别名 | YAML 列表；实体注释可用逗号列表 |

## 检索规则

- 普通蓝图生成默认排除 `doc_scope=index`。
- `status=proposed` 和 `authority=inferred` 默认不进入正式生成上下文。
- 精确构件查询先按 `doc_type`、`entity_type` 缩小范围，再做向量相似度召回。
- 建筑生成分别召回建筑类型、构件和 recipe，不能让所有文档无条件竞争一个 `top_k`。
- `BLUEPRINT-SPEC-MINIMAL.md` 继续作为 system 上下文，不依赖向量召回。

## 合并条件

只有以下字段一致时才考虑合并短片段：

```text
doc_type
doc_scope
knowledge_layer
entity_type
entity_name
topic
wild_version
status
authority
parent_id
```

即使 metadata 一致，也必须确认两个片段共同回答一个问题。长度不足本身不是合并理由。
