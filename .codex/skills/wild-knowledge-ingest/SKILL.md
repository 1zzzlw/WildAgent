---
name: wild-knowledge-ingest
description: Write, review, refactor, classify, merge, and validate WildAgent RAG knowledge Markdown for WILD generation. Use when the user asks to add or revise building types, components such as doors/windows/walls/roofs/stairs/furniture, assembly recipes, verified patterns, blueprint rules, or metadata; convert research notes into retrieval-ready knowledge; inspect whether Markdown is safe for semantic chunking; verify WILD fields against current engine/schema/validators; or integrate an approved document into E:\AgentProject\WildAgent\wild-server\storage\knowledge_base.
---

# Wild RAG Knowledge Author

## 目标

产出事实受当前 WildAgent 引擎约束、结构对应语义知识块、可被 metadata 过滤、适合向量召回的 Markdown。不要负责向量入库，不要用润色掩盖事实冲突，不要把建筑概念直接发明成 WILD 字段。

## 默认位置

- 知识库：`wild-server/storage/knowledge_base/`
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
- 所有交付前检查：读取 `references/rag-readiness-checklist.md`。

## 事实优先级

按以下顺序判断事实：

1. 当前渲染引擎源码、Schema、类型定义、确定性校验代码。
2. 当前版本完整 WILD 规范。
3. 已通过渲染和校验的 WILD 样例。
4. 项目维护者明确确认的规则。
5. 建筑领域资料。
6. AI 推断。

低优先级来源不得覆盖高优先级事实。未经源码或规范验证的能力标记为 `status: proposed`，不得出现在正式生成配方或“有效 JSON”中。

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

### 3. 运行静态审计

本地可执行时运行：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py <source-or-target.md>
```

静态脚本只检查可确定的格式问题，不能代替源码事实审查。

### 4. 建立事实与冲突表

在内部记录：

| 声明 | 来源 | authority | status | 处理 |
|---|---|---|---|---|

发现冲突时先报告：

- 冲突内容及各自来源；
- 当前可信结论；
- 尚需确认的部分；
- 对现有 RAG 或蓝图生成的影响。

无法从更高优先级来源解决的冲突，不得静默写成确定事实。

### 5. 分类并规划知识块

读取分类引用，选择 `blueprint_spec / component / building_type / recipe / pattern`。在写正文前规划每个可独立召回的业务实体：

| chunk_id | 标题路径 | 回答的问题 | 父块 | metadata |
|---|---|---|---|---|

一个块只解决一个完整问题。门与窗、不同变体、不同版本、不同 status 或不同 authority 不得为了凑长度合并。

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

使用文档级 YAML frontmatter；多实体文档使用实体标题后的 `rag-meta` 注释覆盖 metadata。具体格式读取 metadata 引用。

### 7. 验证 WILD 示例

所有标为有效的 JSON 必须：

- 是严格 JSON，不含 `//` 或 `/* */`；
- 只使用当前源码或规范支持的类型、字段和枚举；
- 引用的构件和材质真实存在；
- 坐标、尺寸与文字一致；
- 能通过已有确定性校验；
- 片段明确标注“不是完整 `.wild` 文件”。

错误示例单独标记，不能与正确示例放在同一个代码块。当前不支持的能力分成“当前能力、可用降级、未来提案”，不得伪装成正式语法。

### 8. 执行 RAG 就绪检查

读取检查清单并逐项确认。至少检查：

- 标题是否对应真实语义边界；
- 每个块是否自包含；
- 标题路径是否进入 chunk 正文或 metadata；
- JSON、表格是否会被长度兜底切断；
- README、Mermaid 或索引是否会污染生成召回；
- metadata 是否足够过滤版本、状态、权限和实体；
- 是否存在重复、冲突或不受支持的 WILD 示例。

修改后再次运行 linter。存在错误时不要入库。

### 9. 仅在授权时集成

用户明确要求写入知识库时：

1. 先读取目标文件并做语义合并，不盲目追加。
2. 精确重复保留一份；近重复合并到规范段；冲突放入待确认区。
3. 新建文件时更新必要的目录索引，但让 README 保持 `doc_scope: index`。
4. 不手动写 Chroma，不主动删除持久化索引；项目 Loader 负责同步。
5. 保留无关文件和用户已有改动。

## 固定输出

按任务需要输出：

1. 新建或修改后的 Markdown；
2. 冲突与待确认项；
3. 建议或实际 chunk 清单；
4. metadata；
5. RAG 就绪检查结果；
6. 分片器需要调整的事项；
7. 若已集成，列出创建、更新、合并和跳过的文件。
