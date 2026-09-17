# Metadata 与实际过滤

## 三层合并

```
config.yaml: defaults  →  config.yaml: mapping_rules（按书写顺序，后者覆盖前者）  →  文档 frontmatter（最高）
```

路径能决定的字段**写在 `config.yaml` 里**（例如 `knowledge/protocol/*.md` → `doc_type: blueprint_spec` +
`knowledge_role: protocol`），不要在每份文件重复抄；frontmatter 只写**路径给不出**的东西
（`entity_name`、`topic`、`primary_terms`、`synonyms`、`applies_to`、来源）。

frontmatter 由 `MarkdownChunker._parse_metadata_lines` 解析（`app/spec/loader.py`），
**不是 YAML**：扁平 `key: value` + `- ` 列表，`synonyms: []` 可用，不要写嵌套结构。

## 字段（白名单，`MarkdownChunker._DOCUMENT_METADATA_FIELDS`，`loader.py:453-470`）

| 字段 | 用途 |
|---|---|
| doc_type | blueprint_spec / component / recipe / index |
| doc_scope | generation / system / index |
| knowledge_layer | wild_schema / constraint / navigation |
| entity_type / entity_name | 构件族与稳定实体 ID |
| topic | parameters / constraints / assembly / composition / definition / navigation |
| wild_version | 当前 "1.1" |
| status | supported / experimental / proposed / deprecated |
| authority | engine / schema / verified_example / maintainer / domain_reference / inferred |
| knowledge_revision | 当前 rules-v3；由根 config 维护，旧索引不参与生成 |
| knowledge_role | protocol / capability / relation / navigation |
| applies_to | 只能显式选择专用系统或构件变体的术语数组 |
| primary_terms / synonyms | 正式术语 / 可互换别名，互不重复 |
| keywords | 仅兼容未迁移的外部文档；正式知识库不再写 |

🔴 **白名单外的键会被 loader 静默忽略**。特别注意 **`source` 不在白名单里，可以省略**：

- loader 在 `loader.py:536` 把 `source` 取出来后**就不再使用**，它不会进入任何分片 metadata → 对检索零影响；
- 手动工具 `wild-server/scripts/rag/lint_wild_rag_docs.py` 要求它，但只查"键存在且非空"，
  **不解析路径、不校验文件是否存在**，也没有 `ALLOWED_VALUES` 约束 → 纯形式要求；
  且该脚本**没有任何 CI 或测试把它当门禁跑**（`tests/rag/test_knowledge_rules_v3.py` 只 import 它的 helper）。
- 结论：**不写 `source` 不会破坏任何东西**。需要人工溯源时才写，值用后端/文档来源
  （`schema.json`、`app/agent/validation/structure.py`），**不要写前端路径**（前后端分部署后无意义）。

`status` / `authority` 取值必须落在 `_retrieval_priority_score` 表内（`loader.py:181`）；
**不在表内的取值按未知值加罚**，宁可不写也不要自创枚举。

## 生成默认条件与查询

默认检索条件：`knowledge_revision=rules-v3`、`doc_scope=generation`、
`knowledge_role ∈ {protocol, capability, relation}`、`status ∈ {supported, experimental}`、`authority ≠ inferred`。

组件查询按本次构件的 `entity_type` 限定；专用 recipe 额外检查 `applies_to`。已选方案可作为后续查询上下文。
否定和复杂意图需结合规划结果；简单词匹配不能被当作完整语义理解。

## 一致性纪律

- 类型语义与渲染实现不共用一个虚假的 `engine` 权威。资料里的经验尺寸不能因为用了 WILD 字段就变成引擎约束；
  混合权威时拆块。
- 新增/移动/删除文档必须同步 `config.yaml` 的 `required_documents` —— 这是**真门禁**
  （`scripts/deploy/deployment_preflight.py`，Jenkinsfile 部署前调用）。
  🔴 它**只接受 `.md`**（断言后缀、非绝对路径、无 `..`、不重复），`schema.json` 这类资产不要写进去。
- 别把"手动工具脚本"当成门禁：`scripts/rag/lint_wild_rag_docs.py` 无任何 CI 调用，
  它报错不等于流程会失败；判断某条检查是不是真门禁，去 `Jenkinsfile` 里搜它。
- 新增字段前先核查它是否真能被 `MarkdownChunker` 持久化、被真实索引、被查询过滤；不要写完就宣称生效。
