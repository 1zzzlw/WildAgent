# Metadata 与实际过滤

路径公共字段写 config.yaml；文档 frontmatter 覆盖路径，标题后的 rag-meta 覆盖当前实体及子标题。重复值由 compact_frontmatter_metadata.py 清理并验证解析结果一致。

## 字段

| 字段 | 用途 |
|---|---|
| knowledge_revision | 当前 rules-v3；由根 config 维护，旧索引不参与生成 |
| knowledge_role | 活动内容使用 protocol / capability / relation / navigation；strategy / example / fallback / identity 属于隔离或遗留角色 |
| doc_scope | 活动内容使用 generation / system / index；reference 只为未来独立参考索引保留 |
| doc_type | 活动内容使用 blueprint_spec / component / recipe / index；building_type / pattern 不得进入当前活动库 |
| entity_type / entity_name | 构件族与稳定实体 ID |
| topic | parameters / constraints / assembly / composition / definition / example / fallback 等主题 |
| status | supported / experimental / proposed / deprecated |
| authority | engine / schema / verified_example / maintainer / domain_reference / inferred |
| source | 文件或源码事实位置 |
| primary_terms / synonyms | 正式术语 / 可互换别名，互不重复 |
| applies_to | 专用系统或构件变体的显式名称与别名数组，用于匹配本次请求或已选方案 |

生成默认条件：revision=rules-v3，scope=generation，role 属于 protocol/capability/relation，status 为 supported/experimental，authority 非 inferred。当前图没有 reference 消费者，策略与案例应存放在扫描目录之外；不能靠标题写“仅供参考”代替调用链。

组件查询按本次构件 `entity_type` 限定；专用 recipe 额外检查 `applies_to`。已选方案可作为后续查询上下文。否定和复杂意图需结合规划结果；简单词匹配不能被当作完整语义理解。

类型语义与渲染实现不共用一个虚假的 engine 权威。资料中的经验尺寸不能因为使用 WILD 字段就变为引擎约束；混合权威时拆块。新增字段必须核查 MarkdownChunker 的持久化、真实索引和查询过滤。
