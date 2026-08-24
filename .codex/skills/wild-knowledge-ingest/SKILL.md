---
name: wild-knowledge-ingest
description: Convert raw notes and supplied documents into verified, classified, retrieval-ready WildAgent Markdown while preserving source-described building composition, spatial systems, component roles, assembly relations, and supported downgrade mappings through a traceable coverage audit; match the project's real RAG chunker, preview actual chunks, merge and deduplicate approved knowledge, and integrate it into E:\AgentProject\WildAgent\wild-server\storage\knowledge_base. Use for buildings, doors/windows/walls/roofs/stairs/furniture, recipes, patterns, blueprint rules, knowledge-base audits, metadata, semantic chunking, or any request to feed knowledge into WildAgent RAG.
---

# Wild RAG Knowledge Author

## 目标

把原始资料转换为事实受当前 WildAgent 引擎约束、结构对应业务实体、可被 metadata 过滤且经过真实 Loader 预览的 Markdown。Skill 负责语义分块、来源信息保真和入库前验收；Loader 负责确定性物理分片、索引和召回。不要手工写向量数据库，不要用润色掩盖事实冲突，不要把建筑概念直接发明成 WILD 字段，也不要因为某个 JSON 示例无效而连带删除其仍有价值的建筑构成语义。

## 默认位置

- 知识库：`wild-server/storage/knowledge_base/`
- 路径 metadata 配置：`wild-server/storage/knowledge_base/config.yaml`
- 当前 WILD 规范：`wild-server/storage/knowledge_base/BLUEPRINT-SPEC-FULL.md`
- 最小铁律：`wild-server/storage/knowledge_base/BLUEPRINT-SPEC-MINIMAL.md`
- Loader：`wild-server/app/spec/loader.py`
- 校验器：`wild-server/app/tools/spatial_tools.py`
- 归一化与 Schema 预检：`wild-server/app/utils/blueprint_parser.py`

保留用户提供的源文件；除非用户明确要求，不移动或改写源文件。

## 必读引用

根据任务读取以下文件，不要把全部引用无条件塞入上下文：

- 分类或决定目标路径：读取 `references/classification-taxonomy.md`。
- 新建、重构文档：读取 `references/document-templates.md`。
- 编写或检查 metadata：读取 `references/metadata-schema.md`。
- 编写、重构或验收任何 RAG 文档：读取 `references/chunk-contract.md`。
- 转换建筑类型、构件体系或跨构件配方：读取 `references/source-fidelity-and-composition.md`。
- 所有交付前检查：读取 `references/rag-readiness-checklist.md`。

## Skill 与 Loader 的边界

必须遵守 `references/chunk-contract.md`：

- Skill 把用户资料拆成真实 Markdown 标题下的业务实体，保证单个实体可独立召回。
- Skill 把说明、参数、表格和 JSON 放在同一实体路径中，不让 Loader 猜测它们属于谁。
- Loader 只按标题/实体 metadata 切分，保护代码块和表格，并对普通长文本长度兜底。
- 不用增大 `chunk_size` 掩盖文档结构问题；实际 chunk 不自包含时先重构文档。

## 事实优先级

按以下顺序判断事实：

1. 当前渲染引擎源码、Schema、类型定义、确定性校验代码。
2. 当前版本完整 WILD 规范。
3. 已通过渲染和校验的 WILD 样例。
4. 项目维护者明确确认的规则。
5. 建筑领域资料。
6. AI 推断。

低优先级来源不得覆盖高优先级事实。未经源码或规范验证的能力标记为 `status: proposed`，不得出现在正式生成配方或“有效 JSON”中。

## 信息保真铁律

- 先建立来源声明清单，再摘要和分块；不得只凭“看起来重要”保留少数内容。
- 每条非重复声明必须标记为 `preserved / normalized / routed / downgraded / deferred_conflict / rejected` 之一，不允许无记录丢弃。
- 建筑领域语义与 WILD 实现事实分开判断。字段或 JSON 无效时，只拒绝无效语法；结构体系、空间组织、视觉特征、组件角色和搭接意图仍应保留，并标明受支持映射、近似降级或待确认状态。
- “默认完整构成”与“最少可行回退”必须分块。最小构件集合只用于低复杂度或失败回退，不能替代建筑类型在普通/精密生成中的默认构成。
- 详细建筑实体必须提供构成合同，至少区分主体骨架、空间/体量、外围护、开口、交通、附属组件、重复模数、依附/搭接和降级映射；来源未提供的类别明确写“未提供”，不得由 AI 补写成事实。

具体声明分类、优先级和构成合同格式见 `references/source-fidelity-and-composition.md`。

## 工作流

### 1. 识别任务

判断任务属于新建、修改、资料转换、事实审查、结构重构、目录设计或 metadata 设计。无法确定文档类型时，只询问一个会改变结果的关键问题。

### 2. 读取最小事实集

只读取与主题直接相关的：

- 引擎 builder、类型定义或 Schema；
- 归一化和校验代码；
- 完整规范中的对应章节；
- 已验证样例；
- 现有同主题知识文档。

不要为了一个窗型加载全部建筑知识。

### 3. 保留原始资料并运行初检

把用户提供的文件视为来源，不原地覆盖。先确认目标知识库中是否已有相同实体，再决定合并、新建或报告冲突。

对已有 RAG 文档运行静态审计；原始资料尚无 frontmatter 时，允许初检报告格式问题：

本地可执行时运行：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py <source-or-target.md>
```

静态脚本只检查可确定的格式问题，不能代替源码事实审查。

### 4. 建立事实与冲突表

先逐实体建立来源声明清单，再记录事实与冲突：

| claim_id | 实体 | 类别 | 原始声明 | 来源 | authority | status | disposition | 目标位置/原因 |
|---|---|---|---|---|---|---|---|---|

来源声明类别至少覆盖 `identity / program_space / massing / structure / envelope / opening / circulation / auxiliary / assembly / repetition / material / parameter / unsupported / example`。不存在的类别不补写；存在的类别不得因为目标文档想保持简短而静默删除，应路由到详细建筑、组件或 recipe 文档。

发现冲突时先报告：

- 冲突内容及各自来源；
- 当前可信结论；
- 尚需确认的部分；
- 对现有 RAG 或蓝图生成的影响。

无法从更高优先级来源解决的冲突，不得静默写成确定事实。

### 5. 分类并规划业务实体

读取分类引用，选择 `blueprint_spec / component / building_type / recipe / pattern`。在写正文前规划每个可独立召回的业务实体：

| chunk_id | 标题路径 | 回答的问题 | 父块 | metadata |
|---|---|---|---|---|

一个实体块只解决一个完整问题。门与窗、具体变体、不同版本、不同 status 或不同 authority 不得为了凑长度合并。为每个独立实体选择稳定的 `entity_name`；不要把 A/B/C 粗体项目当作实体边界。

对建筑类型额外规划两种不能互相替代的实体：

- `topic: composition`：默认完整构成合同，是未给详细提示时生成的主要依据；
- `topic: fallback`：最少可行回退，只在低复杂度或明确降级时使用。

大型来源包含多个建筑类型时，不得把每类压缩成只有“视觉特征 + 最小表达”的单段摘要。每类至少保留一个可独立召回的默认完整构成合同；跨建筑复用的幕墙、门窗、屋盖等关系另行路由到 component/recipe，不在建筑块中重复整篇。

### 6. 按模板编写

遵守以下结构约束：

- `#` 表示文档领域；
- `##` 表示可独立检索的业务实体或规范大类；
- `###` 表示实体下的独立主题；
- `####` 表示具体变体、规则、错误或示例；
- 禁止用 `**A. 名称**` 代替标题；
- 标题必须包含实体名称或继承后仍能形成明确标题路径；
- JSON、表格、公式和对应解释保持原子性；
- 每个实体块正文可脱离相邻块独立理解。

建筑构成合同使用来源明确的优先级：

- `required`：缺失会破坏基本结构、功能或身份，默认不得省略；
- `characteristic`：决定该类型辨识度，普通/精密生成应保留，可在回退模式简化；
- `conditional`：只有触发条件成立时使用，并写明条件；
- `optional`：允许受种子、风格或预算控制变化。

不要把来源中全部 components 平铺成 `required`，也不要把 `characteristic` 降成可随意省略的装饰。

当一个变体包含定义、参数、组装公式和 JSON 时，用 `####`/`#####` 建立真实边界；禁止让一个 part 以“WILD JSON：”结束、下一个 part 才出现代码块。

使用文档级 YAML frontmatter；多实体文档使用实体标题后的 `rag-meta` 注释覆盖 metadata。具体格式读取 metadata 引用。

术语字段必须分开维护：`primary_terms` 只放实体正式名称、稳定领域术语和当前
WILD 类型/字段；`synonyms` 只放翻译、别名、俗称和用户可能输入的变体。同一个词
不得同时出现在两组中，相关概念不能冒充同义词。新建或修改的知识文档禁止继续写
`keywords`；仅在迁移外部旧文档时使用
`scripts/migrate_keyword_metadata.py`。可由目录稳定推断的公共字段写入知识库
`config.yaml`，按“全局默认值 → 路径规则 → 文件头”的顺序覆盖；内容相关字段仍写在
文档或实体 metadata 中。文件头与路径配置值完全相同时删除重复声明；批量清理使用
`scripts/compact_frontmatter_metadata.py`，并以清理前后最终 metadata 完全一致为门槛。

### 7. 验证 WILD 示例

所有标为有效的 JSON 必须：

- 是严格 JSON，不含 `//` 或 `/* */`；
- 只使用当前源码或规范支持的类型、字段和枚举；
- 引用的构件和材质真实存在；
- 坐标、尺寸与文字一致；
- 能通过已有确定性校验；
- 片段明确标注“不是完整 `.wild` 文件”。

错误示例单独标记，不能与正确示例放在同一个代码块。当前不支持的能力分成”当前能力、可用降级、未来提案”，不得伪装成正式语法。

### 8. 交叉验证：数量、类型与枚举值

在运行静态检查之前，先做一轮语义级交叉验证，防止”写对了格式但写错了事实”：

**数量一致性**：
- 表格实际行数与文档中声称的数字（如”9 类组件”、”11 种构件”）必须一致。
- 列表项数与介绍性文字中的计数必须一致。
- 多个文档描述同一事物（如 `geometry.components` 的类型列表）时，所有文档的数量和名称必须一致。

**类型与枚举值验证**：
- 文档中列出的所有 WILD `type`、`subtype`、`style`、`roofType`、`crossSection`、`shape`、`fixtureType` 等枚举值必须在当前源码中存在：
  - `geometry.elements` 的 `type`：对照 `wild-web/src/wild-core/src/primitive/registry.ts` 的 `registerBuiltins()`。
  - `geometry.components` 的 `type`：对照 `wild-web/src/wild-core/types.ts` 的 `ComponentSpec` 联合类型。
  - 字段枚举值：对照 `wild-web/src/wild-core/types.ts` 中的类型字面量联合和 `wild-web/wild-lang/schema.json` 中的 `enum`/`const`。
- 文档中列出的”严禁使用”或”常见错误”清单必须包含最近实际遇到的错误值（参考 git log 中的归一化映射）。

**跨文档一致性**：
- 同一能力在不同文档中的描述不得矛盾（如 A 文档说”9 类组件”而 B 文档列出了 10 个）。
- 同一实体的必填字段、约束和降级方案在所有文档中保持一致。

**来源覆盖与构成完整性**：
- 对照来源声明清单，确认每条声明都有 disposition 和可追踪目标；目标正文不得出现静默丢失。
- 每个详细建筑实体同时包含默认完整构成与独立的最少回退；不得只剩 Core 能力清单。
- 原文中的构件顺序、依附/搭接、重复模数和“视觉身份组件”必须保留或明确路由。
- 无效 JSON、旧字段和未支持类型只使对应实现声明失效，不得导致整段建筑知识被删除。

**工具辅助**：linter 已支持部分交叉验证（如表格行数 vs 声称数字），但源码级别的类型校验仍需人工对照。修改涉及类型列表或枚举值的文档后，必须运行：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py <target.md> --cross-check
```

### 9. 执行静态检查和真实分片预览

先运行 linter，再调用项目真实 `MarkdownChunker` 预览：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py <target.md>
python .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py <target.md>
```

预览失败或出现空壳 chunk、脱离实体的 JSON/表格、缺失 metadata 时，返回第 5～8 步重构。不要用臆测代替真实预览。

读取检查清单并逐项确认。至少检查：

- 标题是否对应真实语义边界；
- 每个块是否自包含；
- 标题路径是否进入 chunk 正文或 metadata；
- JSON、表格是否会被长度兜底切断；
- README、Mermaid 或索引是否会污染生成召回；
- metadata 是否足够过滤版本、状态、权限和实体；
- 是否存在重复、冲突或不受支持的 WILD 示例。
- 构成合同是否被保留在可独立召回的 chunk 中，且 `required`、`characteristic`、`conditional` 没有混成一个无优先级列表。
- 来源覆盖表中是否仍有空 disposition 或没有目标位置的声明。

修改后再次运行 linter 和 preview。存在错误时不要入库；只有明确标注并经用户接受的历史遗留问题可以作为例外，且必须在交付中列出。

### 10. 仅在授权时集成

用户明确要求写入知识库时：

1. 先读取目标文件并做语义合并，不盲目追加。
2. 精确重复保留一份；近重复合并到规范段；冲突放入待确认区。
3. 新建文件时更新必要的目录索引，但让 README 保持 `doc_scope: index`。
4. 不手动写 Chroma，不主动删除持久化索引；项目 Loader 负责同步。
5. 保留无关文件和用户已有改动。
6. 集成后对最终文件重新运行 linter 和真实 chunk 预览。

## 固定输出

按任务需要输出：

1. 新建或修改后的 Markdown；
2. 来源覆盖与 disposition 摘要，包括 `routed/downgraded/deferred/rejected` 项；
3. 冲突与待确认项；
4. 建议或实际 chunk 清单；
5. metadata；
6. RAG 就绪检查结果；
7. 分片器需要调整的事项；
8. 若已集成，列出创建、更新、合并和跳过的文件。
