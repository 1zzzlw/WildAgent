---
# WildAgent RAG 全链路研究说明书

> 文档分类：RAG 专题。返回 [RAG 文档入口](README.md)。

> 适用对象：第一次接触 WildAgent 知识库 / RAG 链路的开发者、评估者。
> 当前代码链路最后核对：2026-08-24。第 7、8、12 节保留的是 2026-08-20 的索引实测快照，只用于讲解存储结构，不代表当前部署配置或当前分片数量。

---

## 0. 一句话结论

WildAgent 的知识库（Markdown）经 **MarkdownChunker 分片** → **配置的 Embedding 模型向量化** → **ChromaDB 索引** → **RAGSpecLoader 检索、过滤、排序和门控** → **Agent 将完整分片注入 Prompt**。知识问答最终返回经过白名单校验的 `chunk_id` 引用；每次请求的查询、距离、耗时和 Token 会写入 `storage/sessions/rag_traces`。

---

## 1. 全链路总览

```
┌─────────┐  ①分片    ┌──────────┐  ②向量化   ┌───────────────┐  ③入库   ┌────────────────┐
│ 知识库    │ ───────▶ │  Markdown │ ────────▶ │  ChromaDB      │ ──────▶ │ HNSW 向量索引   │
│ *.md     │  chunker │  Chunker  │  embed   │ wild_knowledge │  upsert │ + documents/    │
│ 42 篇    │          │           │          │ _base          │         │ metadata       │
└─────────┘          └──────────┘           │ N 个分片         │         └────────┬───────┘
                                            └────────────────┘                     │
                                                                                  │ ④检索 query(1024d)
┌─────────┐  ⑤注入    ┌──────────────────┐  ④Top-K   ┌──────────────┐             │
│ LLM      │ ◀────── │  RAGSpecLoader    │ ◀──────── │  AgentService │ ──────────▶│
│ (agent)  │ prompt  │  .retrieve/load   │  片段      │ _build_rag_   │            │
└─────────┘          └──────────────────┘            │ queries(1~8) │            │
                                                      └──────────────┘            │
                                                                        collection.query
```

| 环节 | 核心代码位置 | 关键类/函数 |
|---|---|---|
| ① 分片 | `app/spec/loader.py` | `MarkdownChunker.split_file` / `collect_markdown_paths` |
| ② 向量化 | `app/spec/loader.py` + `config.py` | `OpenAICompatibleEmbeddingFunction` / `create_embedding_function` |
| ③ 入库 | `app/spec/loader.py` | `RAGSpecLoader.sync_index`（增量 upsert） |
| ④ 检索 | `app/spec/loader.py` | `RAGSpecLoader.retrieve`（query → 排序去重 → parent 扩展） |
| ⑤ agent 消费 | `app/services/agent_service.py` | `_create_spec_loader` / `_build_rag_queries` / `_agent_for_query` / `build_system_prompt` |
| 权限、门控与追踪 | `app/agent/rag_security.py` / `rag_gate.py` / `rag_trace.py` | `AccessContext` / `evaluate_retrieval_gate` / `RAGTrace` |
| 配置 | `config.py`（RAGConfig / ModelConfig）+ `.env` | `EMBEDDING__NAME`、`RAG__*` 系列 |

---

## 2. 环节①：知识库文档 → 分片（MarkdownChunker）

### 2.1 知识库形态

- 根目录：`storage/knowledge_base/`，共 **42 篇 Markdown**，按业务组织：
  - `BLUEPRINT-SPEC-FULL.md` / `BLUEPRINT-SPEC-MINIMAL.md`（蓝图规范主文档）
  - `building_types/`（住宅、公共、工业、农业、目录 taxonomy）
  - `components/`（墙、门、窗、栏杆、玻璃幕墙、屋顶等，含 `engine-capability-boundaries.md` 边界文档）
  - `patterns/`（高细节生成）、`recipes/`（装配模板、材质色板、装配关系）
- 每篇 Markdown 可通过 **frontmatter / `<!-- rag-meta -->` 块** 声明文档级元数据（`doc_type`、`doc_scope`、`entity_type`、`entity_name`、`status`、`authority`、`building_category` 等）。

### 2.2 分片逻辑（`app/spec/loader.py` → `MarkdownChunker`）

配置基线（`config.py` 中 `RAGConfig`）：

| 参数 | 值 | 说明 |
|---|---|---|
| `persist_dir` | `storage/chroma` | Chroma 持久化目录 |
| `collection_name` | `wild_knowledge_base` | 集合名 |
| `chunk_size` | 900 | 目标分片字符数 |
| `chunk_overlap` | 150 | 分片重叠字符数 |
| `top_k` | 6 | 检索默认返回数 |
| `max_context_chars` | 18000 | 注入 prompt 的最大字符数 |

分片策略（要点）：
1. **按标题层级 + 业务实体分块**：识别 Markdown 标题（`#`/`##`/`####` 等）形成"知识路径"；同一实体/构件条目尽量整块保留（JSON 示例、表格、说明文字一起）。
2. **前置知识路径头**：每个分片开头注入 `> 知识路径：<文档标题> > <各级标题> > <小节>`，保证脱离上下文后仍能自解释（实证样例见 8.3）。
3. **长度兜底**：超过 `chunk_size` 的超长块会二次切分，重叠 `chunk_overlap` 保留边界信息，`part_index`/`parent_chunk_id` 标记父子关系。
4. **metadata 构造**：`config.yaml` 路径默认值、文档 frontmatter 和分片级 `rag-meta` 按优先级合并。正式术语字段是 `primary_terms` 与 `synonyms`；`keywords` 只为尚未迁移的外部文档兼容读取。

---

## 3. 环节②：向量化（Embedding）

### 3.1 模型与配置来源

- `.env` 或部署环境变量配置 `EMBEDDING__NAME`、`EMBEDDING__BASE_URL` 和 `EMBEDDING__API_KEY`。文档不记录密钥值，也不假定某个部署当前使用哪一个模型。
- `config.py` 用 Pydantic Settings 加载配置：`Settings.embedding` 保存模型连接参数，`Settings.rag` 保存分片、索引、Gate、Trace 和安全参数。
- 2026-08-20 快照使用 `qwen3.7-text-embedding` 和 `OpenAICompatibleEmbeddingFunction`；当前环境必须以评测报告中的 embedding 名称和 `index_signature` 为准。

### 3.2 双实现与降级开关（`create_embedding_function`）

| 实现 | 何时使用 | 向量维度 |
|---|---|---|
| `OpenAICompatibleEmbeddingFunction` | 配置了真实 API Key、模型名和兼容服务地址 | 由实际模型决定；2026-08-20 快照为 1024 |
| `HashEmbeddingFunction` | 无 Key / 显式 `RAG__ALLOW_HASH_FALLBACK=true` 降级 | 256 |

- `RAG__ALLOW_HASH_FALLBACK` 决定缺少真实 Embedding 配置时是否允许降级。生产环境建议关闭；运行报告必须先确认实际 embedding 类型。
- 注意：`eval_retrieval.py --embedding hash` 仅用于本地流程冒烟，会使用 HashEmbeddingFunction + 临时索引，结果不能代表线上 embedding 的语义质量。

---

## 4. 环节③：入库（ChromaSpecLoader.sync_index）

位置：`app/spec/loader.py` → `RAGSpecLoader.sync_index`。

要点：
1. **增量 upsert**：以 `content_hash` / `body_hash` 判断分片是否变化，只写入"新增/变更"分片，删除已移除分片。实证 `eval_retrieval` 报告显示某次同步 `updated=500, deleted=0`。
2. **集合元数据**：保存 `namespace/project/version/index_signature`；签名用于判断 Embedding 与分片配置是否兼容。
3. **入库数据三元组**：`documents`（分片原文）、`embeddings`（模型对应维度的向量）、`metadatas`（分片 metadata）。
4. 分片数量会随知识库和切片规则变化，使用 `check_sync_status.py` 或分片检查脚本读取当前值；2026-08-20 快照为 516。

---

## 5. 环节④：检索（RAGSpecLoader.retrieve）

位置：`app/spec/loader.py` → `RAGSpecLoader.retrieve`。

执行流水线：
1. **query 向量化**：同一 embedding function 对查询文本编码（实证 query 向量维度 1024）。
2. **Chroma `collection.query`**：默认 `top_k=6`，返回 `ids/documents/metadatas/distances`；`chunk_id` 使用 Chroma 的真实 ID。
3. **`_retrieval_priority_score` 排序去重**：语义距离 + **status / authority 成熟度惩罚**（`supported` 优于 `experimental`；`engine` 优于 `schema`/`domain_reference`/`inferred`）。
4. **强制服务端过滤**：限定 `namespace=wild_spec`，排除 `doc_scope=index`、`status=proposed`、`authority=inferred`，并追加 `public/tenant/department/clearance_level` 权限条件。调用方传入的权限字段会被移除，不能覆盖服务端 AccessContext。
5. **业务 metadata 过滤**：查询规划可携带 `doc_type/entity_type/building_category` 等白名单条件，减少跨域噪声。
6. **parent 扩展**：命中子分片时可能回带父分片/相邻 part，保证注入上下文完整；相邻补片没有独立向量距离。
7. **Retrieval Gate**：检索后按原始 distance 执行 `off/observe/enforce`。问答证据不足时可拒答；建筑生成只降级为基础规范，不因一个可选知识点缺失而终止整个任务。
8. 返回结构：`RetrievedSpecChunk(document, metadata, distance, id)` 列表。

**真实检索样例**（本次实证，query="生成一栋现代别墅，包含正门、水平长窗、平屋顶、楼梯和入口雨棚"，Top-6）：

| # | distance | source | heading 前缀 | status / authority |
|---|---|---|---|---|
| 1 | 0.4041 | villas.md | 居住建筑：别墅 > 1.1 现代别墅（架空层 + 水平长窗）> 构件清单 | supported / engine |
| 2 | 0.4429 | villas.md | … > 最少可行 Blueprint（10×8m 现代别墅，2F） | supported / engine |
| 3 | 0.5615 | villas.md | … > 组装顺序 | supported / engine |
| 4 | 0.5644 | villas.md | … > 最少可行 Blueprint | supported / engine |
| 5 | 0.5823 | villas.md | 轻量建筑分类：别墅 > 变体 A：现代简约别墅 | experimental / domain_reference |
| 6 | 0.6050 | villas.md | … > 构件最少可行版本（默认生成） | experimental / domain_reference |

> 观察：语义上完全命中"现代别墅"，且 `supported/engine` 的成熟分片排在 `experimental/domain_reference` 之前，说明成熟度惩罚生效。

---

## 6. 环节⑤：agent 消费（注入上下文）

位置：`app/services/agent_service.py`。

1. **装配**：`_create_spec_loader()` 用 config 创建 `RAGSpecLoader`（`auto_sync=True` 时启动时自动建索引）。日志实证：`RAGSpecLoader: 已启用 Chroma, persist_dir=...storage\chroma, collection=wild_knowledge_base`。
2. **意图拆解**：`_build_rag_queries()` 把用户一句话拆成 **1~8 个检索意图**（建筑类型 / 构件 / 材质 / 装配关系等多角度）。
3. **检索吸收**：`_agent_for_query()` 对每个意图调用 `loader.load / load_many`，得到的分片拼成 `spec_text`。
4. **注入 prompt**：`build_system_prompt()` 将 `spec_text` 放入 System Prompt 的 **`# WILD 规范`** 段。超过 `max_context_chars=18000` 时舍弃放不下的整片，不截断 JSON、表格或单个分片。
5. 因此 agent 的生成依据是"Top-K 分片原文 + 成熟度排序后的优先采用顺序"，**是否真正采用取决于 LLM 对 prompt 的执行**（这正是欠缺分析中的 P0 项，见 10.1）。
6. **引用闭环**：注入内容带 `[chunk_id=...]`；知识问答只接受本次实际注入 ID 对应的 `[引用:chunk_id]`，伪造引用会被清除。
7. **请求追踪**：RAGTrace 记录查询、最终过滤条件、真实 chunk ID、原始距离、实际注入 ID、Gate 结论、LLM 耗时与 Token，并原子写入 `storage/sessions/rag_traces/<session_id>/<request_id>.json`。

---

## 7. ChromaDB 存储实证（2026-08-20 历史快照）

### 7.1 结论

**是向量数据。** 下表是 2026-08-20 快照，用来解释 Chroma 的存储方式；模型、维度、文件大小和分片数量可能随重新建索引而变化。

| 事实 | 实证 |
|---|---|
| Chroma 集合记录的向量维度 | `collections.dimension = 1024`（与 qwen3.7 对齐） |
| 向量本体（经 API 读取） | 每条 1024 维 `numpy.float64`，**L2 范数 = 1.0（归一化单位向量）**，例：`[0.0274, 0.0402, -0.0391, 0.0100, -0.0446, ...]` |
| sqlite 里能看到什么 | **看不到向量明文**——新版 Chroma 的 `embeddings` 表只有 `id/segment_id/embedding_id/seq_id`，向量以 HNSW 图结构存于 **VECTOR segment 的二进制文件** |
| 分片原文存在哪 | sqlite 的 `embedding_metadata` 表 `chroma:document` 键（无独立 `documents` 表） |

### 7.2 存储文件形态（实证 `storage/chroma/`）

```
chroma.sqlite3                                    9,121,792 bytes  ← 元数据 + 文档文本
5f82d632-…/data_level0.bin + header/length/links       ~0.4 MB     ← HNSW 索引段
a068d30a-…/data_level0.bin + index_metadata.pickle   ~2.5 MB     ← HNSW 索引段
c2e72054-…/data_level0.bin …                          ~0.4 MB     ← HNSW 索引段
f7b05c77-…/data_level0.bin + index_metadata.pickle   ~4.6 MB     ← HNSW 索引段（最大，516 条向量的主图）
```

`a068d30a` / `f7b05c77` 带 `index_metadata.pickle`，说明是带元数据的 HNSW 索引段；四个 segment 对应 VECTOR / METADATA 两类存储。

### 7.3 sqlite 实证细节

- `collections` 表：`name=wild_knowledge_base, dimension=1024`。
- `embeddings` 表：**516 行**，字段为 `id, segment_id, embedding_id, seq_id`（无向量列）。
- `embedding_metadata` 表：**516 行**，按 `key/string_value/int_value/float_value/bool_value` 通用列存 metadata。
- **无 `documents` 表**：分片原文在 `embedding_metadata` 的 `chroma:document` 键（每行一条完整分片）。

---

## 8. 实证数据附录（2026-08-20 历史运行结果）

### 8.1 运行环境

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe <script>
# Python 3.12.13 / chromadb 1.5.9
```

### 8.2 集合统计

- `col.count() = 516`；`collection.metadata = {'namespace': 'wild_spec', 'project': 'WildAgent', 'version': '3', 'index_signature': 'f58d314dff00b82e'}`

### 8.3 分片原文样例（弧形墙，748 字符）

```markdown
> 知识路径：Wild建筑蓝图规范文档 (Blueprint Specification) > 2. Geometry 几何定义 > 2.2 构件类型 (Elements) > 2.2.2 弧形墙 (Curved Wall)

#### 2.2.2 弧形墙 (Curved Wall)

```json
{
  "type": "wall", "id": "circular_wall", "from": [5,0,0], "to": [5,3,0],
  "thickness": 0.3, "material": "brick",
  "curve": {"type": "arc", "center": [0,0,0], "sweep": 360, "segments": 32}
}
```

**curve字段**：| type | "arc" | … | sweep | number | 扫掠角度（度） | segments | number | 细分段数 |
```

### 8.4 metadata 键集合（历史快照与当前契约）

2026-08-20 的 516 分片快照仍使用 legacy `keywords`。当前正式知识库已经拆分为 `primary_terms`（主术语）和 `synonyms`（同义词），并增加服务端权限字段 `access_scope`；受限文档还可包含 `tenant_id/department/clearance_level`。Loader 只为外部旧文档保留 `keywords` 兼容读取。

稳定基础字段包括：`wild_version, topic, status, source_file, source, path, part_index, parent_chunk_id, namespace, mtime, knowledge_layer, primary_terms, synonyms, heading_path, heading, entity_type, entity_name, doc_type, doc_scope, declared_source, content_hash, chunk_index, body_hash, authority, access_scope`。实际键集合以当前分片报告为准，不能继续把历史“31 个键”当成固定 Schema。

条件键（仅部分分片有）：`entity_aliases(500), role_tags(277), constraint_tags(240), building_category(191)`

单条样例（节选）：`namespace=wild_spec, source=BLUEPRINT-SPEC-FULL.md, entity_type=schema, doc_type=blueprint_spec, doc_scope=generation, status=supported, authority=schema, heading_path=…>2.2.2 弧形墙, chunk_index=8, content_hash=d5b5ce856d631f8f, parent_chunk_id=wild_spec:…:section:09e843e9459b9abc`

### 8.5 向量本体样例

```python
len(emb) == 1024
type(emb) == numpy.ndarray, 元素 numpy.float64
emb[:10] = [0.027423, 0.040209, -0.039099, 0.009984, -0.044554, -0.011052, 0.014477, -0.022672, 0.018377, 0.041764]
L2 范数 = 1.0（已归一化）
```

---

## 9. 现有工具链盘点（scripts/rag/）

| 脚本 | 作用 | 输出 | 是否需要线上索引 |
|---|---|---|---|
| `check_sync_status.py` | 打印同步状态（片段数/更新/删除、loader 类型） | 控制台 | 读线上 |
| `inspect_knowledge_chunks.py` | 对 md 文件/目录分片，打印分片明细、统计、合法性检查 | 控制台 + `scripts/reports/inspect_chunks_<ts>.md` | 否（纯分片） |
| `inspect_chunks_demo.py` | 分片展示报告（来源/数量/字符数/内容摘要） | 控制台 + `scripts/reports/chunks_report_<ts>.md` | 否 |
| `eval_retrieval.py` | 运行 60 题 Golden Set（28 正样本 + 32 负样本），计算 Hit@K、Recall@K、MRR 和距离分布 | Markdown + 可选 JSON 报告 | 默认读取现有索引；`--embedding hash` 使用临时索引 |
| `calibrate_retrieval_gate.py` | 根据正负样本距离校准 Gate 阈值，输出错误拒答率、错误放行率和索引签名 | JSON | 读取评测 JSON，不直接访问索引 |
| `check_rag_quality_gate.py` | 按 `evals/rag_quality_gate.json` 检查题数、指标和检索异常 | 控制台退出码 | 否 |
| `summarize_rag_traces.py` | 汇总空召回率、平均距离、强制拒答率、P95 延迟、Token、反馈和可选成本 | 控制台或 JSON | 读取 `storage/sessions/rag_traces` |
| `judge_rag_answer.py` | 对问题、回答和 Context 做版本化 LLM-as-Judge 辅助评分 | JSON | 需要配置 Judge 使用的聊天模型 |

配套文档：`README_INSPECT_CHUNKS.md`（分片工具用法）、`README_EVAL_RETRIEVAL.md`（评测报告怎么看）。

**历史评测报告样例**（`scripts/reports/eval_retrieval_20260819_101824.md`，当时为 28 问 / Top-5 / 516 分片；不能作为当前 60 题基线）：

| 指标 | 值 | 解读 |
|---|---|---|
| 空召回率 | 0.0% | 所有问题都有 Top-1 命中 |
| 平均 Top-1 距离 | 0.4915 | 首条相关度较好 |
| 每问平均命中数 | 5.46 | Top-5 基本填满 |
| **平均同源率** | **64%** | ⚠️ 偏高，Top-K 多来自同一文件，提示**漏召回** |

按文件命中 TOP：BLUEPRINT-SPEC-FULL.md(22)、engine-capability-boundaries.md(15)、villas.md(12)…

> 另有 `app/agent/rag/hybrid_retriever.py`（BM25+向量融合检索器，P1 方案），当前**未接入** agent 主链路，仅测试引用。

---

## 10. 当前欠缺与 P0～P3 优先级

步骤 0～7 的运行时底座已经落地，详见 [RAG 能力与演进规划](RAG_CAPABILITIES_AND_EVOLUTION.md)；下面的 P0～P3 是后续生产化优先级，不要再把已经完成的 RAGTrace、引用或离线题集列为缺失。

| 优先级 | 当前缺口 | 现状证据 | 下一步验收 |
|---|---|---|---|
| **P0** | **生产阈值尚未校准和启用** | Gate 代码支持 `observe/enforce`，但默认阈值为空；HashEmbedding 阈值不能用于真实模型 | 使用部署相同的 Embedding、索引签名和 Top-K 跑 60 题；先 observe 审查误判，再配置 enforce |
| **P0** | **可信身份代理尚需部署配置** | 后端已强制 AccessContext 和权限过滤，但可信身份头依赖共享密钥及反向代理 | 配置 `RAG__SECURITY__TRUSTED_HEADER_SECRET`，用跨租户/跨部门用例验证越权召回为 0 |
| **P1** | **端到端知识吸收评测不足** | 当前固定题集主要评价检索；引用校验只能证明 ID 属于 Context，不能证明生成结果真正遵守知识 | 固定生成任务并校验 Blueprint 合规率、引用忠实度和拒答正确率 |
| **P1** | **分片与 Embedding 缺少对照实验** | 当前参数有可运行基线，但没有持续保存多组 chunk_size/overlap/模型对照 | 在同一 60 题集上比较参数与模型，并保存索引签名和报告 |
| **P2** | **混合检索尚未接入主链路** | `hybrid_retriever.py` 仍是独立能力；纯向量对精确字段和值可能不敏感 | 增加精确术语题，对比 BM25+向量与纯向量后再决定是否接入 |
| **P2** | **在线告警与保留策略不足** | Trace 已落盘并可汇总，但尚无自动告警、轮转和保留周期 | 对 P95、空召回率、拒答率和负反馈设置监控；制定 Trace 清理和访问策略 |
| **P3** | **高级质量与安全服务待接入** | 已有基础 PII/内容安全规则和按需 Judge，不等价于完整生产审核 | 按真实风险决定是否接入 Presidio、外部审核和抽样 LLM-as-Judge，保留人工复核 |

---

## 11. 新人快速上手

### 11.1 一小时内跑通

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."

# 1) 看知识库同步状态
.\.venv\Scripts\python.exe scripts\rag\check_sync_status.py

# 2) 看分片长什么样（整库分片体检）
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py storage\knowledge_base --table

# 3) 跑线上检索评测（真实 embedding + 线上索引，当前 60 题）
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py

# 4) 打开最新报告
#    scripts\reports\eval_retrieval_<时间戳>.md
```

### 11.2 关键文件速查

| 想了解 | 看哪里 |
|---|---|
| 分片/入库/检索实现 | `app/spec/loader.py`（MarkdownChunker / RAGSpecLoader） |
| RAG 配置 | `config.py` 的 `RAGConfig` + `.env` 的 `EMBEDDING__*` / `RAG__*` |
| agent 如何用 RAG | `app/services/agent_service.py` 的 `_build_rag_queries` / `build_system_prompt` |
| 检索评测报告怎么读 | `scripts/rag/README_EVAL_RETRIEVAL.md` |
| 分片检查报告怎么读 | `scripts/rag/README_INSPECT_CHUNKS.md` |

### 11.3 新增一条知识库文档的流程

1. 在 `storage/knowledge_base/` 对应目录新建 `.md`，写清 frontmatter（`doc_type/doc_scope/entity_type/status/authority` 等）。
2. 运行 `check_sync_status.py` / 重启服务触发 `auto_sync`（或直接跑 `sync_index`），确认入库分片数增加。
3. 用 `inspect_knowledge_chunks.py` 检查分片是否合理（标题被正确切开、无超长/空块）。
4. 用 `eval_retrieval.py --questions <含新知识的测试问题>` 验证能召回。

---

## 12. 本次验证运行记录（2026-08-20）

| 步骤 | 命令/脚本 | 结果 |
|---|---|---|
| sqlite 实证 | 直连 `chroma.sqlite3` 查 collections/segments/embeddings/embedding_metadata | dimension=1024；embeddings 表 516 行无向量列；当时 metadata 31 键；无 documents 表；HNSW 二进制文件落盘 |
| API 实证 | `verify_chroma_api.py`（真实 embedding + `collection.get`） | count=516；向量 1024 维、float64、L2=1.0；分片样例 748 字符 |
| 真实检索 | 同脚本 `collection.query`，query=“生成一栋现代别墅…” | Top-6 全部命中 villas.md 现代别墅，distance 0.40–0.61，成熟度排序生效 |
| 工具链运行 | `check_sync_status.py` | RAGSpecLoader 启用 Chroma，collection=wild_knowledge_base |

---

*历史快照采集时间：2026-08-20；当前代码说明最后核对：2026-08-24。涉及模型、维度、分片数和距离的结论必须用当前环境重新运行后确认。*
