# RAG 就绪检查清单

## 事实

- [ ] 每个 WILD 类型、字段、枚举和引用规则都有当前源码或规范依据。
- [ ] 低优先级建筑资料没有覆盖引擎或 Schema。
- [ ] 未验证能力标为 `proposed`，并与 supported 内容分块。
- [ ] 冲突列出来源、可信结论和待确认项。
- [ ] 无效字段或 JSON 只影响对应实现声明，没有连带删除仍成立的领域构成语义。

## 来源覆盖与建筑构成

- [ ] 已按实体建立来源声明清单，覆盖 identity、空间、体量、结构、围护、开口、交通、附属、组装、重复、材质、参数、降级和示例。
- [ ] 每条非重复声明都有 `preserved / normalized / routed / downgraded / deferred_conflict / rejected` disposition。
- [ ] `routed` 指向具体目标文件/实体；`rejected` 有明确原因，没有静默丢弃。
- [ ] 每个详细建筑实体有 `topic: composition` 的默认完整构成合同。
- [ ] 构成合同区分 `required / characteristic / conditional / optional`，并写明条件或省略后果。
- [ ] 主体骨架、空间/体量、外围护、开口、交通、附属组件、重复模数、依附搭接和降级映射均保留；来源未提供的类别明确标注。
- [ ] `topic: fallback` 与默认完整构成分开，最小构件集合没有冒充默认生成配方。
- [ ] 多建筑长文没有被压缩成每类只有一段“视觉特征 + 最小表达”。

## 标题与语义块

- [ ] 只有一个清晰的 `#` 文档标题。
- [ ] `##`、`###`、`####` 分别表达实体、大主题和具体规则/变体。
- [ ] 没有使用粗体 A/B/C 伪装实体标题。
- [ ] 每个块只回答一个完整问题。
- [ ] 标题路径或等价上下文会进入每个子片段。
- [ ] 不同实体、版本、status 或 authority 没有合并。
- [ ] 去除标题和分隔线后，没有空正文或仅含“如下/清单”的壳 chunk。

## 长度兜底

- [ ] 先按实体和自然主题拆分，再考虑长度。
- [ ] JSON、表格、公式和解释保持完整。
- [ ] 超长表格按行组拆分并重复表头。
- [ ] 超长实体优先增加子标题，而不是调大 overlap。
- [ ] 子片段继承 metadata、`parent_chunk_id` 和 `part_index`。
- [ ] 实际运行 `preview_wild_rag_chunks.py`，多 part 边界没有拆散说明与对应 JSON。

## Metadata

- [ ] 文档级 frontmatter 字段完整。
- [ ] 多实体文档在实体标题后提供 `rag-meta`。
- [ ] `source` 可追踪。
- [ ] `keywords` 包含中文、英文和当前 WILD 名称。
- [ ] README 使用 `doc_type=index`、`doc_scope=index`。

## JSON

- [ ] 标为 `json` 的代码块可由严格 JSON 解析器解析。
- [ ] JSON 不含 `//`、`/* */` 或尾随逗号。
- [ ] 正确示例与错误示例分开。
- [ ] 片段明确说明不是完整 `.wild` 文件。
- [ ] 引用目标存在，尺寸、坐标与文字一致。
- [ ] 示例能够通过项目确定性校验。

## 语义一致性（交叉验证）

- [ ] 文档中声称的数字（如"9 类组件"、"11 种构件"）与对应表格/列表的实际行数一致。
- [ ] 同一概念在多个文档中的数量、名称和描述一致（如 `geometry.components` 的类型列表在 `engine-capability-boundaries.md` 和 `BLUEPRINT-SPEC-MINIMAL.md` 中数量和名称相同）。
- [ ] 所有 WILD `type` 值在 `wild-web/src/wild-core/src/primitive/registry.ts` 的 `registerBuiltins()` 中有对应注册。
- [ ] 所有组合组件 `type` 值在 `wild-web/src/wild-core/types.ts` 的 `ComponentSpec` 联合类型中有对应定义。
- [ ] 所有枚举值（`roofType`、`column.style`、`furniture.subtype`、`opening.style`、`beam.crossSection` 等）与 `wild-web/src/wild-core/types.ts` 中的类型字面量一致。
- [ ] "严禁使用"或"常见错误"清单覆盖了最近实际遇到的错误值（检查 git log 中的归一化映射记录）。
- [ ] `status: supported` 的能力描述没有与 `status: proposed` 或 `experimental` 文档中的内容矛盾。
- [ ] 运行 `lint_wild_rag_docs.py --cross-check` 无错误。

## 检索污染与重复

- [ ] README、Mermaid 和大型导航表不会作为普通生成知识。
- [ ] catalog 只保留轻量默认值，详细规则有单一规范来源。
- [ ] 重复规则内容一致；旧版本已标记。
- [ ] 同义词不会制造多份互相竞争的规范。
- [ ] 文档被召回单个 chunk 时仍可独立理解。
- [ ] `status`、`authority` 会参与过滤或明确显示给模型。

## 交付

- [ ] linter 已运行并解释未解决项。
- [ ] 给出实际或建议 chunk 清单。
- [ ] 给出冲突和待确认项。
- [ ] 未经用户授权没有写入知识库或修改源文件。
