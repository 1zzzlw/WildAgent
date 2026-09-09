# Metadata 与实际过滤

路径公共字段写 config.yaml；文档 frontmatter 覆盖路径，标题后的 rag-meta 覆盖当前实体及子标题。重复值由 compact_frontmatter_metadata.py 清理并验证解析结果一致。

## 字段

| 字段 | 用途 |
|---|---|
| knowledge_revision | 当前 rules-v2；由根 config 维护，旧索引不参与生成 |
| knowledge_role | protocol / capability / relation / identity / strategy / example / fallback / navigation |
| doc_scope | generation / reference / system / index |
| doc_type | blueprint_spec / component / recipe / building_type / pattern / index |
| entity_type / entity_name | 构件族与稳定实体 ID |
| topic | parameters / constraints / assembly / composition / definition / example / fallback 等主题 |
| status | supported / experimental / proposed / deprecated |
| authority | engine / schema / verified_example / maintainer / domain_reference / inferred |
| source | 文件或源码事实位置 |
| primary_terms / synonyms | 正式术语 / 可互换别名，互不重复 |
| applies_to | 类型卡的显式名称与别名数组，用于匹配本次请求 |

生成默认条件：revision=rules-v2，scope=generation，role 属于 protocol/capability/relation/identity，status 为 supported/experimental，authority 非 inferred。调用方显式 reference 查询才可取参考策略；不能靠标题写“仅供参考”替代代码过滤。

类型查询额外按 applies_to 对应实体过滤，未命中时允许为空；组件查询按本次构件 entity_type 限定。已选方案可作为后续查询上下文。否定和复杂意图需结合规划结果；简单词匹配不能被当作完整语义理解。

类型语义与渲染实现不共用一个虚假的 engine 权威。资料中的经验尺寸不能因为使用 WILD 字段就变为引擎约束；混合权威时拆块。新增字段必须核查 MarkdownChunker 的持久化、真实索引和查询过滤。
