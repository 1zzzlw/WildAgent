# WildAgent RAG 与知识库优化总结

> 更新时间：2026-08-01
> 范围：`wild-knowledge-ingest` Skill、知识库 Markdown 分类、RAG Loader 分片、检索过滤与本次完整构件规范审计。

## 一、优化目标

这几轮优化要解决的不是单一的“按多少字符切片”，而是让文档制作和 RAG 分片形成稳定契约：AI 先把原始资料审查、分类成可检索的业务实体，Loader 再做受限制的物理长度分片，检索阶段按 metadata 排除不可信或未实现内容。

最终数据流如下：

```text
原始资料
  → wild-knowledge-ingest：事实核对、分类、去重、实体标题、metadata
  → retrieval-ready Markdown：building_types / components / recipes / patterns / blueprint_spec
  → Loader：H1~H5 语义块、原子代码/表格、900/150 长度兜底
  → 向量库：正文哈希去重、metadata 同步
  → 检索：按 doc_type/entity_type/status/authority 过滤并分路召回
  → Prompt：完整 chunk 与相邻 part，不截断 JSON
```

## 二、原始问题与判断

最初的“标题分片，过长再按长度切分”方向没有错，但只有两层仍不够。标题如果只是目录标题、粗体编号或大章节标题，Loader 无法知道一个片段属于哪种门、窗、屋顶或建筑类型；纯字符切分还可能拆散解释、表格和 JSON。因此真正需要的是三层结构：

1. 文件分类：按知识用途进入不同目录；
2. 业务实体分块：用真实 H1～H5 和 `rag-meta` 定义可独立召回的实体；
3. 物理长度兜底：只对仍然过长的普通正文分 part，代码块和表格保持原子。

用户担心“向量库存储混乱会让模型拿到互相冲突的上下文”是有依据的。主要风险并不是向量库把文件顺序打乱，而是多个语义相近、可信度不同的片段竞争同一个 `top_k`，以及未实现字段被错误标成正式能力。解决手段是单一规范来源、正文哈希去重、业务实体 metadata、可信度过滤和分路查询，而不是单纯增大 chunk 或 overlap。

## 三、Skill 的职责与规范

项目 Skill 位于 `.codex/skills/wild-knowledge-ingest/`，当前职责包括：

- 读取原始文档，但不覆盖原文件；
- 按“引擎/Schema > 完整 WILD 规范 > 已验证示例 > 维护者规则 > 领域资料 > AI 推断”的顺序核对事实；
- 把资料分类到 `building_types`、`components`、`recipes`、`patterns` 或蓝图规范；
- 用真实 Markdown 标题和实体级 `rag-meta` 建立业务边界；
- 把未验证或未实现能力标为 `proposed`，不能伪装成 `supported`；
- 保证标为 `json` 的代码块能被严格 JSON 解析；带注释、多个并列对象或伪代码必须用 `text`；
- 合并同一实体的补充信息，跳过重复内容，不把原始长文整篇追加到知识库；
- 使用项目真实 Loader 预览最终 chunks，再决定是否入库。

Skill 和 Loader 的职责被明确分开：Skill 不生成 embedding、不直接写 Chroma；Loader 不猜测粗体标题的业务意义，也不修复错误事实。

## 四、知识库分类与 metadata

当前知识库采用以下主要路由：

| 路径 | `doc_type` | 作用 |
|---|---|---|
| `BLUEPRINT-SPEC-FULL.md` | `blueprint_spec` | 完整 WILD 字段、坐标、引用与约束 |
| `building_types/catalog/` | `building_type` | 模糊建筑名称的轻量默认入口 |
| `building_types/<use>/` | `building_type` | 住宅、公共、工业、农业等详细配方 |
| `components/` | `component` | 单一构件族、参数、能力边界与降级方式 |
| `recipes/` | `recipe` | 跨构件组装关系、顺序和矩阵 |
| `patterns/` | `pattern` | 用户确认或项目验证后的案例与偏好 |
| 各级 `README.md` | `index` | 人类导航，不进入普通生成召回 |

核心 metadata 包括 `doc_type`、`doc_scope`、`knowledge_layer`、`entity_type`、`entity_name`、`topic`、`wild_version`、`status`、`authority`、`source` 和 `keywords`。默认生成排除 `doc_scope=index`、`status=proposed` 和 `authority=inferred`；`experimental` 可以召回，但可信度会显示给模型。

## 五、Loader 与检索层优化

`wild-server/app/spec/loader.py` 当前实现：

- 识别 H1～H5、YAML frontmatter 和实体级 `rag-meta`；
- 跳过只有标题、分隔线或空内容的壳 chunk；
- fenced code 保持原子，Markdown 表格按行组拆分并重复表头；
- 普通长文本使用 `chunk_size=900`、`chunk_overlap=150` 兜底；
- 每个物理 part 重复知识路径，并携带 `parent_chunk_id`、`part_index`；
- 使用忽略祖先标题路径的 `body_hash` 跨来源去重；
- metadata 变化但正文不变时仍能同步向量库记录；
- 召回时默认过滤 proposed/inferred，并向模型展示实体、主题、状态和依据；
- 命中长度子片时补相邻 part，但不跨业务实体扩展；
- 上下文预算按完整 chunk 计算，不在字符中间截断 JSON 或表格。

Agent 的建筑生成知识查询被拆成建筑类型、组装 recipe、结构构件、墙、窗、门、屋顶等独立查询，避免所有知识无条件竞争同一个 `top_k`。

## 六、本次《WILD 蓝图构件与组合方式完整规范》审计

原始文件保持在用户提供的位置，没有修改，也没有整篇复制进知识库。审计发现原文把当前实现和未来设计混在一起：原文称有 22 种构件和 24 种组合，但当前 WILD v1.1 Schema 只有 11 个 `geometry.elements` 类型。

### 6.1 类型分类结论

| 分类 | 内容 | 处理 |
|---|---|---|
| 当前几何类型 | wall、floor、column、beam、roof、opening、stair、furniture、dense_brick、body、primitive | 以 Schema 和构件注册表为准，写入能力边界文档 |
| 顶层几何系统 | templates/instances、placements | 明确为 `geometry` 子系统，不当成 element type |
| 未实现专用类型 | door、window、truss、ramp、railing、cornice、mullion、terrain、chimney、canopy | 统一归入 `proposed-component-extensions.md`，默认检索排除 |

原文的方柱/矩形柱 `crossSection`、`bottomSide`、`bottomWidth` 等字段不在当前 column Schema；`floor.surfaces` 也不存在。`door/window/mullion` 等专用 JSON 即使语法可读，也不能作为 WILD v1.1 正式示例。

### 6.2 组合机制分类结论

当前实际执行的空间解析是 `resolveWallJoints`、`resolveBeamSupports`、`resolveRoofBoundary`、`resolveFloorRegions`、`resolveStairSteps`、`resolveColumnOffsets`、`resolveOpenings`；另有 `expandTemplates` 和受限的 `expandPlacements`。

原文中的 `resolveDoorPlacement`、`resolveWindowPlacement`、`resolveMullionLayout`、`resolveStairRailing`、`resolveFloorRailing`、`resolveCornicePath`、`resolveRoofTruss`、`resolveRampConnection`、`resolveChimneyPenetration`、`resolveDoorCanopy`、`resolveTerrainSnap`、`resolveMemberSupports` 均未在当前源码中出现，已作为实现提案隔离。

### 6.3 合并与去重结果

原文抽取出 147 个较长段落，与知识库没有完全相同的规范化段落，但在构件、门窗、屋顶和组装关系上存在大量语义重合。因此没有创建一份竞争性的“22 构件完整规范”副本，而是：

- 新增当前引擎能力边界；
- 新增已实现的构件组合关系；
- 新增未实现构件扩展提案；
- 重写结构构件、屋顶和组装模板中的错误能力声明；
- 将既有门、窗专用类型文档整体降为 `proposed`；
- 为领域矩阵补充能力边界说明；
- 将 44 个非严格 JSON 代码块改标为 `text`，并把墙体示例改为严格可解析的 Schema 结构。

建筑实例、材质预设和实现优先级没有直接并入正式生成知识：实例尚未通过当前引擎验证，材质名称未证明在项目中已定义，实现优先级属于开发路线而不是蓝图事实。

## 七、当前验收结果

使用 Skill 自带 linter 和项目真实 Loader 验收后的快照：

| 指标 | 结果 |
|---|---:|
| Markdown 文件 | 30 |
| 全部物理 chunks | 284 |
| Chroma 普通知识索引 chunks | 264 |
| 正式生成可用 chunks | 171 |
| `supported / experimental / proposed` | 107 / 107 / 70 |
| chunk 中位数 / P95 / 最大值 | 379 / 860 / 1687 字符 |
| 多 part 业务标题 / 最大 parts | 34 / 4 |
| 正式生成正文重复组 | 0 |
| 真实 Loader 预览 | 0 errors，4 warnings |
| 文档 linter | 1 error，47 warnings |
| 后端回归测试 | 31 passed |

剩余 linter error 位于 `BLUEPRINT-SPEC-MINIMAL.md` 的材质片段：它标为 JSON，但本身只是 `"materials": {...}` 片段，不是独立 JSON 值。该文件是直接注入 System Prompt 的铁律，Skill 规定必须获得用户对该文件的明确授权后才能修改，所以本轮保留不动。

四个分片 warning 分别是精简规范完整小屋示例 1687 字符、文化建筑 11 字符薄壳、酒店原子片 943 字符、支摘窗提案原子片 978 字符。它们没有造成空 chunk、metadata 缺失、`rag-meta` 泄漏或解释与代码分离；其中门窗提案默认不会进入正式生成。

后端测试初始化 Loader 时已按正常应用流程同步本地 Chroma：当前 namespace 共 264 条普通知识索引记录，本轮更新 264 条并删除 80 条旧记录。`BLUEPRINT-SPEC-MINIMAL.md` 的 20 个预览 chunk 属于始终注入的 system 基础规范，不进入 Chroma 普通知识索引，因此 284 与 264 的差值符合设计。

## 八、后续投喂文档的标准流程

1. 保留原始资料，不直接复制进知识库；
2. 先核对 Schema、引擎注册表、resolver 和已验证示例；
3. 按检索意图拆入构件、建筑类型、recipe 或 pattern；
4. 用标题和 `rag-meta` 建立实体边界，supported 与 proposed 分块；
5. 对同一实体执行语义合并和正文哈希去重；
6. 严格检查 JSON，再运行真实 Loader 分片预览；
7. 只由 Loader 同步向量库，不手工修改 Chroma。

常用验收命令：

```powershell
python .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py wild-server/storage/knowledge_base
wild-server/.venv/Scripts/python.exe .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py wild-server/storage/knowledge_base
```

## 九、当前结论

当前 RAG 的分片机制已经形成合理的“文档分类 + 业务实体 + 受限长度兜底”结构，主要风险不再是字符切片本身，而是知识源事实质量。Skill 与 Loader 现在能相互配合：Skill 决定什么知识可以进入、属于哪个实体、可信度如何；Loader 负责把合格 Markdown 稳定地变成可过滤、可去重、可扩展上下文的 chunks。

下一阶段的重点应是逐步清理剩余领域文档中的旧字段，并用真实渲染或 Schema 校验把高价值 `experimental` 内容升级为 `supported`；不建议继续扩大 chunk 大小来掩盖文档语义边界问题。
