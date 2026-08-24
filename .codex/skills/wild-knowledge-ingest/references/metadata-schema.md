# RAG Metadata 规范

metadata 用于过滤、追踪、父子关联和冲突处理，不能代替自包含正文。

## 文档级 Frontmatter

每份准备进入普通 RAG 的 Markdown 使用：

```yaml
---
knowledge_layer: architecture
entity_type: window
entity_name: window_family
topic: assembly
status: supported
authority: schema
source: components/windows.md
primary_terms:
  - 窗
  - opening
synonyms:
  - window
---
```

README 和目录导航使用：

```yaml
---
entity_name: components_index
status: supported
authority: maintainer
source: components/README.md
primary_terms:
  - 构件索引
synonyms: []
---
```

上面的精简文件头依赖知识库根目录的 `config.yaml`。组件目录已经提供
`doc_type/component`、`doc_scope/generation` 和全局 `wild_version`；README 规则还会
提供 `knowledge_layer/navigation`、`entity_type/index`、`topic/navigation`。只有配置
没有提供的内容字段才写在文件头。

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
primary_terms:
  - 支摘窗
  - opening
synonyms:
  - zhizhai window
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
| `topic` | 当前回答的问题 | `definition / schema / parameters / constraints / composition / assembly / fallback / example / error / navigation` |
| `wild_version` | 适用版本 | 当前为 `"1.1"` |
| `status` | 能力状态 | `supported / experimental / proposed / deprecated` |
| `authority` | 事实依据 | `engine / schema / verified_example / maintainer / domain_reference / inferred` |
| `source` | 可追踪来源 | 知识库相对路径或源码位置 |
| `parent_id` | 可选父块 | 稳定 chunk/entity ID |
| `primary_terms` | 主术语 | 正式实体名、稳定领域术语、当前 WILD 类型/字段；非空 YAML 数组 |
| `synonyms` | 同义词 | 翻译、别名、俗称、用户输入变体；YAML 数组，无同义词时写 `[]` |

## 主术语与同义词怎么分

使用下面的判断顺序：

1. 这是实体本身的正式名称、规范概念或当前 WILD 标识符吗？是则放
   `primary_terms`，例如 `支摘窗`、`opening`、`parentWall`。
2. 它只是主术语的英文翻译、旧称、俗称或用户常用说法吗？是则放
   `synonyms`，例如 `zhizhai window`、`支摘式窗`。
3. 它只是与实体相关，但不能与实体互换吗？两边都不放。例如“采光好”是窗的属性，
   不是“窗”的同义词。

两组词不允许重复。新文档禁止写 legacy `keywords`。Loader 仍可读取外部旧文档的
`keywords`，只是为了平滑迁移，不代表知识库可以继续使用旧字段。

## 路径映射配置

`knowledge_base/config.yaml` 只存放能由文件路径稳定推断的公共字段：

```yaml
defaults:
  wild_version: "1.1"

mapping_rules:
  - path_pattern: "components/*.md"
    metadata:
      doc_type: component
      doc_scope: generation
```

合并优先级从低到高是 `defaults`、按书写顺序命中的 `mapping_rules`、Markdown 文件头。
因此更具体的规则写在后面，单个文件的特例直接在 frontmatter 中覆盖。不要把
`entity_name`、`primary_terms`、`synonyms` 等内容字段按目录批量猜出来。
`path_pattern` 使用知识库相对路径，`*` 匹配一层，递归目录使用 `**`。

如果文件头显式值与路径配置完全相同，该声明属于冗余，应删除；只有真实特例才显式
覆盖。可先审计再写入：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/compact_frontmatter_metadata.py <knowledge-base-dir>
python .codex/skills/wild-knowledge-ingest/scripts/compact_frontmatter_metadata.py <knowledge-base-dir> --write
```

工具会验证清理前后的最终合并 metadata 完全一致，不会删除内容字段或不同值的覆盖项。

迁移旧文档时先预览统计，再实际写入：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/migrate_keyword_metadata.py <knowledge-base-dir>
python .codex/skills/wild-knowledge-ingest/scripts/migrate_keyword_metadata.py <knowledge-base-dir> --write
```

## 检索规则

- 普通蓝图生成默认排除 `doc_scope=index`。
- `status=proposed` 和 `authority=inferred` 默认不进入正式生成上下文。
- `experimental` 可以进入召回，但 Loader 必须把 `status` 和 `authority` 明确显示给模型。
- 精确构件查询先按 `doc_type`、`entity_type` 缩小范围，再做向量相似度召回。
- `primary_terms` 与 `synonyms` 都可以触发实体匹配；字段分离用于提升可解释性和审计质量。
- 建筑生成分别召回建筑类型、构件和 recipe，不能让所有文档无条件竞争一个 `top_k`。
- 建筑类型的默认生成优先召回 `topic=composition`；只有明确低复杂度或失败回退时才使用 `topic=fallback`。不得让 fallback 的短摘要覆盖完整构成合同。
- 命中带 `parent_chunk_id` 的长度子片时，补充相邻 `part_index`，但不跨业务实体扩展。
- 跨来源去重使用不含祖先知识路径的正文哈希，避免相同表格因 H1 不同重复进入上下文。
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
