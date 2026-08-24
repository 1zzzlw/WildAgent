# Skill 与 RAG Loader 分片契约

这份契约定义 Skill 产出的 Markdown 如何被 `wild-server/app/spec/loader.py` 转换成向量 chunk。

## 职责边界

| 阶段 | 负责内容 | 不负责内容 |
|---|---|---|
| Skill | 事实审查、去重、分类、实体边界、标题、metadata、原子示例 | embedding、向量写入、相似度排序 |
| Loader | 解析标题和 `rag-meta`、结构保护、有限长度兜底、索引、过滤与召回 | 猜测粗体列表的业务语义、修复错误事实 |

## 三层分片

1. **文件分类**：Skill 把原始资料拆分或合并到 `building_types / components / recipes / patterns / blueprint_spec`。
2. **业务实体分块**：Skill 在目标 Markdown 中用真实标题和 `rag-meta` 建立可独立召回的实体。
3. **物理长度分片**：Loader 对实体内仍过长的普通文本生成 `part_index`；代码块和表格保持原子。

前两层决定语义质量，第三层只保证索引尺寸。不要把原始长文直接交给第三层补救。

## Loader 可识别结构

- H1～H5 是可分片标题。
- `config.yaml` 提供路径级默认 metadata，文件 frontmatter 提供内容字段并覆盖路径特例。
- 标题后的 `<!-- rag-meta ... -->` 覆盖该标题及其子标题。
- `primary_terms` 与 `synonyms` 分别保存主术语和同义词，实体级声明会随标题路径继承。
- fenced code 是原子块，不做字符切断。
- Markdown 表格按行组拆分，子表重复表头。
- 普通长文本才使用 `chunk_size=900`、`chunk_overlap=150` 兜底。
- 每个物理子片重复知识路径，并带 `parent_chunk_id`、`part_index`。
- README/index 不进入普通生成召回。

## Skill 必须产出的语义结构

```text
# 文档领域
## 可独立召回的实体或规范大类
### 实体主题：定义 / 参数 / 组装 / 约束
#### 具体变体或规则
##### 变体的示例或错误（内容较长时）
```

每个具体变体必须使用真实标题。`**A. 支摘窗**`、`**模板 A**` 和纯分隔标题不是业务边界。

## 原子知识单元

一个原子单元应包含理解它所需的最小上下文：

1. 明确实体或变体标题；
2. 一句定义或适用范围；
3. 参数、表格或组装公式；
4. 对应 JSON；
5. 必要约束或降级说明。

不要让说明段以“JSON 如下：”结束而代码块落入另一个长度 part。若原子单元接近 900 字符，优先增加 `##### 参数`、`##### 示例` 等真实标题；不要调大 overlap。

## 建筑构成原子性

详细建筑类型必须让一个 `topic=composition` 的 chunk 独立回答“默认由什么组成”。该 chunk 至少同时包含：

- 建筑身份与关键视觉特征；
- 主体骨架、外围护以及开口/交通/附属组件的角色；
- `required / characteristic / conditional / optional` 优先级；
- 关键宿主、依附、重复或生成顺序；
- 未支持业务对象的当前降级映射。

不要把身份描述放在一个 chunk、components 列表放在另一个无父上下文的 chunk。详细关系可以另拆 recipe，但 composition chunk 仍要保留关系摘要和路由目标。`topic=fallback` 必须独立成块，不能与 composition 竞争同一个无标签摘要。

## 入库门槛

- 去掉标题、空行和分隔线后，Loader 不得产出空正文 chunk；纯父级标题可以保留为路径，但不会单独入索引。
- 单个 chunk 必须能说明自己属于哪个实体。
- 多 part 实体的每个 part 都应有可理解正文；命中时 Loader 会补充相邻 part，但这不能替代正确标题。
- 有效 JSON 必须严格可解析；带注释的演示改用 `text` 代码块。
- `status=proposed` 或 `authority=inferred` 不进入正式生成召回。
- `experimental` 内容允许召回，但必须把可信度显示给模型。
- 同一正文即使标题路径不同也应判重，不保留竞争性副本。

## 跨文档一致性

Skill 产出的所有文档必须保持事实一致。当多个文档描述同一能力时：

- 类型列表：`engine-capability-boundaries.md` 中 `geometry.elements` 和 `geometry.components` 的类型列表必须与 `BLUEPRINT-SPEC-MINIMAL.md`、`types.ts` 和 `registry.ts` 完全一致。
- 数量声明：任何文档中声称的数字（如"支持 X 类组件"）必须与对应表格/列表的实际行数匹配。
- 枚举值：文档中列出的枚举值（`roofType`、`column.style`、`furniture.subtype`、`opening.style`、`beam.crossSection` 等）必须与 `wild-web/src/wild-core/types.ts` 中的类型字面量联合和 `wild-web/wild-lang/schema.json` 中的定义一致。
- 必填字段：同一组件的必填字段列表在所有文档中保持相同。
- 降级策略：同一不支持能力的降级方式在不同文档中的描述不得矛盾。

修改涉及类型列表或枚举值的文档后，必须同时检查所有引用了这些值的其他文档，确保描述一致。

## 来源覆盖契约

分片前必须完成来源声明 disposition。Loader 不负责判断哪些原文信息被作者漏写。以下情况视为 Skill 失败：

- 无效 JSON 导致同段正确的建筑构成、组件角色或搭接关系一起消失；
- 多建筑长文被压缩成每类只有“视觉特征 + 最小表达”；
- 共用组件被路由后，建筑实体不再说明它为什么需要该组件；
- 最少可行回退被写成默认完整构成；
- 来源明确列出的 characteristic 组件没有保留、降级或冲突记录。

## 验收命令

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py <target.md>
python .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py <target.md>
```

先修复 error；warning 需要逐项判断并在交付中解释。
