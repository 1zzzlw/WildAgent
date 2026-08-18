# 检索增强与自主纠错协议

## 1. 结构化查询计划

把用户原句保留为 `raw_query`，再生成不改变事实的检索计划：

```json
{
  "raw_query": "生成一个社区商铺",
  "intent": "building_generation",
  "entities": ["community_commercial"],
  "aliases": ["社区商业", "沿街商铺", "店面", "neighborhood retail", "storefront"],
  "topics": ["composition", "assembly", "fallback"],
  "filters": {"doc_type": "building_type", "entity_type": "building"},
  "constraints": ["floor_count_unspecified", "storefront_identity"]
}
```

查询计划的 `entities/topics/filters` 必须能追溯到用户原句或现有分类词表。LLM 可以改写同义词和检索意图，但不得在计划中新增未经来源支持的构件事实。无法确定建筑类型时保留多个候选并标记 `uncertain`，不要静默选择住宅模板。

## 2. 索引增强字段

索引字段只从来源正文和 metadata 确定性抽取：

| 字段 | 内容 | 用途 |
|---|---|---|
| `entity_aliases` | 中文别名、英文名、行业称呼 | 同义召回 |
| `entity_name` | 稳定 snake_case ID | 精确过滤 |
| `topic` | composition/assembly/fallback 等 | 意图路由 |
| `role_tags` | required/characteristic/conditional/optional | 构成排序 |
| `constraint_tags` | host、level、coverage、collision 等 | 关系召回 |
| `status`/`authority` | 原 metadata 值 | 可信度过滤 |
| `source` | 来源路径或源码入口 | 证据追踪 |

不要把这些字段只写进向量 metadata 而从正文删除；命中的 chunk 仍必须自包含地说明实体、条件和 WILD 映射。索引重建后通过项目 Loader 更新 Chroma，不手工写向量数据。

## 3. 两阶段召回与重排

1. 先按 `doc_type/entity_type/topic/status` 做受限召回，再执行向量或 BM25 相似度。
2. 建筑生成至少分开召回建筑类型 composition、组件规则和跨组件 recipe；按查询意图为每类分配配额。
3. 重排优先级为：源码/schema/engine > supported verified_example > maintainer > experimental domain_reference > inferred。
4. 按正文哈希和实体 ID 去重；同一实体的 composition 不得被 fallback 摘要挤掉。
5. 记录 query plan、命中 source/heading、过滤条件、重排理由和未命中项，便于诊断“知识不存在”与“召回失败”。

## 4. 有界自主纠错

对 Agent 草稿采用固定检查链：

```text
Draft
  -> Structure Check
  -> Source/Factual Check
  -> Tool/Schema Check
  -> Relation/Reasoning Check
  -> Final Output
```

- `Structure Check` 检查 JSON、字段、数量和阶段边界。
- `Source/Factual Check` 检查每个身份、构成、条件和降级是否有来源；不得用模型常识补齐缺口。
- `Tool/Schema Check` 调用仓库现有确定性校验器；Schema 失败先修结构，不让 LLM 重写整栋建筑。
- `Relation/Reasoning Check` 检查 parent、标高、覆盖、入口可达、组件冲突和建筑类型禁用项。
- 每次局部修正后重跑受影响检查和最终全量检查；最多固定轮数，失败输出可审计的错误与待确认项。

召回增强解决“找不到正确知识”，纠错链解决“生成后没有兑现约束”；二者都不能替代共享 validator 或确定性编译规则。
