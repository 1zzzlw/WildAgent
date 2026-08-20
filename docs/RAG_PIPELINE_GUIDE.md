---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_31198a039c3e11f19155525400826444
    ReservedCode1: M+VTE5ZdSj/4WSbg4hD8BgnXXE6vGpSn/IGrqKk12+47r7bMnLtZUBtilgnyTpDBJLuXgXj8FbcHmg77OomjuahamQZe7e3qZdReBOX6YVvzAuhO9fMOk732urJy3e660IEopGQG9klVxhr2buXtnvgpnrLsNsyec2M8+NUCnGRyPYOE4N1ds4rq+x8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_31198a039c3e11f19155525400826444
    ReservedCode2: M+VTE5ZdSj/4WSbg4hD8BgnXXE6vGpSn/IGrqKk12+47r7bMnLtZUBtilgnyTpDBJLuXgXj8FbcHmg77OomjuahamQZe7e3qZdReBOX6YVvzAuhO9fMOk732urJy3e660IEopGQG9klVxhr2buXtnvgpnrLsNsyec2M8+NUCnGRyPYOE4N1ds4rq+x8=
---

# WildAgent RAG 全链路研究说明书

> 适用对象：第一次接触 WildAgent 知识库 / RAG 链路的开发者、评估者。
> 本文档基于 **wild-server 当前代码与线上 storage/chroma 索引（2026-08-20 实证）** 编写，所有"实证"结论均来自真实运行结果。

---

## 0. 一句话结论

WildAgent 的知识库（Markdown）经 **MarkdownChunker 分片** → **qwen3.7-text-embedding（DashScope，1024 维）向量化** → **ChromaDB（HNSW 索引）入库** → **RAGSpecLoader.retrieve 语义检索 + 成熟度重排** → **AgentService 将 Top-K 分片注入 System Prompt 的"WILD 规范"段** 被 agent 消费。ChromaDB 中 **存储的是真实 1024 维向量数据**（L2 范数=1.0 的归一化向量），但注意：**新版 Chroma（1.5.9）的 sqlite 中看不到向量明文**，向量本体落在 HNSW 二进制索引文件中，sqlite 里只有 id 与 metadata 关联表。

---

## 1. 全链路总览

```
┌─────────┐  ①分片    ┌──────────┐  ②向量化   ┌───────────────┐  ③入库   ┌────────────────┐
│ 知识库    │ ───────▶ │  Markdown │ ────────▶ │  ChromaDB      │ ──────▶ │ HNSW 向量索引   │
│ *.md     │  chunker │  Chunker  │  embed   │ wild_knowledge │  upsert │ + documents/    │
│ 42 篇    │          │           │          │ _base          │         │ metadata(516)   │
└─────────┘          └──────────┘           │ 516 分片         │         └────────┬───────┘
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
4. **metadata 构造**：固定字段 + 条件字段 + 文档级字段，**落库后共 31 个 key**（实证，见 8.4）。

---

## 3. 环节②：向量化（Embedding）

### 3.1 模型与配置来源

- `.env` 中配置：`EMBEDDING__NAME=qwen3.7-text-embedding`、`EMBEDDING__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、API Key 已配置。
- `config.py` 用 pydantic settings 加载 `ModelConfig(name/api_key/base_url)`，`RAGConfig` 持有 `embedding` 配置。
- 实证：`EMBEDDING__NAME: qwen3.7-text-embedding`，embedding function 实际为 **`OpenAICompatibleEmbeddingFunction`**（真实语义向量，非降级 hash）。

### 3.2 双实现与降级开关（`create_embedding_function`）

| 实现 | 何时使用 | 向量维度 |
|---|---|---|
| `OpenAICompatibleEmbeddingFunction` | 配置了真实 API Key + 模型名（当前线上状态） | **1024（实证）** |
| `HashEmbeddingFunction` | 无 Key / 显式 `RAG__ALLOW_HASH_FALLBACK=true` 降级 | 256 |

- 当前 `.env` 为 `RAG__ALLOW_HASH_FALLBACK=false`，不会静默降级。
- 注意：`evaluate_component_rag.py` 这类**离线评测脚本**会强制用 HashEmbeddingFunction + 临时索引，与线上 embedding 不一致（见 10.3 欠缺项）。

---

## 4. 环节③：入库（ChromaSpecLoader.sync_index）

位置：`app/spec/loader.py` → `RAGSpecLoader.sync_index`。

要点：
1. **增量 upsert**：以 `content_hash` / `body_hash` 判断分片是否变化，只写入"新增/变更"分片，删除已移除分片。实证 `eval_retrieval` 报告显示某次同步 `updated=500, deleted=0`。
2. **集合元数据**（实证）：`collection.metadata = {'namespace': 'wild_spec', 'project': 'WildAgent', 'version': '3', 'index_signature': 'f58d314dff00b82e'}`。
3. **入库数据三元组**：`documents`（分片原文）、`embeddings`（1024 维向量）、`metadatas`（31 键）。
4. 当前 **516 个分片**（实证 `col.count() == 516`）。

---

## 5. 环节④：检索（RAGSpecLoader.retrieve）

位置：`app/spec/loader.py` → `RAGSpecLoader.retrieve`。

执行流水线：
1. **query 向量化**：同一 embedding function 对查询文本编码（实证 query 向量维度 1024）。
2. **Chroma `collection.query`**：默认 `n_results=top_k=6`，余弦距离排序，返回 `(documents, metadatas, distances)`。
3. **`_retrieval_priority_score` 排序去重**：语义距离 + **status / authority 成熟度惩罚**（`supported` 优于 `experimental`；`engine` 优于 `schema`/`domain_reference`/`inferred`）。
4. **强制 namespace 过滤**：仅返回 `namespace=wild_spec` 分片。
5. **排除三类分片**：`doc_scope=index`、`status=proposed`、`authority=inferred`。
6. **parent 扩展**：命中子分片时可能回带父分片/相邻 part，保证注入上下文完整。
7. 返回结构：`RetrievedSpecChunk(document, metadata, distance)` 列表。

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
4. **注入 prompt**：`build_system_prompt()` 将 `spec_text` 放入 System Prompt 的 **`# WILD 规范`** 段，受 `max_context_chars=18000` 上限约束（超出截断）。
5. 因此 agent 的生成依据是"Top-K 分片原文 + 成熟度排序后的优先采用顺序"，**是否真正采用取决于 LLM 对 prompt 的执行**（这正是欠缺分析中的 P0 项，见 10.1）。

---

## 7. ChromaDB 存储实证（是否向量数据？）

### 7.1 结论

**是向量数据。** 但必须分清三层事实：

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

## 8. 实证数据附录（真实运行结果）

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

### 8.4 metadata 键集合（31 个，516 分片）

全量键（516/516）：`wild_version, topic, status, source_file, source, path, part_index, parent_chunk_id, namespace, mtime, knowledge_layer, keywords, heading_path, heading, entity_type, entity_name, doc_type, doc_scope, declared_source, content_hash, chunk_index, chroma:document, body_hash, authority, _source, _file_name, _extension`

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
| `evaluate_component_rag.py` | 组合构件固定评测集：临时 Chroma + **HashEmbedding**，验证分片/metadata 过滤/召回排序 | 控制台 | 否（临时索引，不改线上） |
| `eval_retrieval.py` | **线上真实链路评测**：`RAGSpecLoader.retrieve` + 真实 embedding + `storage/chroma`；内置 28 问，支持 `--questions/--limit/--top-k/--namespace` | `scripts/reports/eval_retrieval_<ts>.md` + `eval_console_<ts>.txt` | 是（读线上） |

配套文档：`README_INSPECT_CHUNKS.md`（分片工具用法）、`README_EVAL_RETRIEVAL.md`（评测报告怎么看）。

**评测报告真实样例**（`scripts/reports/eval_retrieval_20260819_101824.md`，28 问 / Top-5 / 516 分片）：

| 指标 | 值 | 解读 |
|---|---|---|
| 空召回率 | 0.0% | 所有问题都有 Top-1 命中 |
| 平均 Top-1 距离 | 0.4915 | 首条相关度较好 |
| 每问平均命中数 | 5.46 | Top-5 基本填满 |
| **平均同源率** | **64%** | ⚠️ 偏高，Top-K 多来自同一文件，提示**漏召回** |

按文件命中 TOP：BLUEPRINT-SPEC-FULL.md(22)、engine-capability-boundaries.md(15)、villas.md(12)…

> 另有 `app/agent/rag/hybrid_retriever.py`（BM25+向量融合检索器，P1 方案），当前**未接入** agent 主链路，仅测试引用。

---

## 10. 欠缺分析与改进优先级

| 优先级 | 欠缺 | 现状证据 | 建议 |
|---|---|---|---|
| **P0** | **端到端 agent 吸收率评测缺失** | 现有评测只到"检索层"（`eval_retrieval.py` 验证 Top-K 命中），没有验证"注入 prompt 后 agent 是否真正采用、蓝本是否合规"。RAG 价值最终要体现在生成质量 | 新增 E2E 评测：固定 N 个生成任务 → 跑 agent → 校验输出 Blueprint 是否包含知识库要求（构件合法、装配顺序正确、材质可用），统计"知识吸收率/合规率" |
| **P0** | **知识库文档规范缺失** | 42 篇 md 的 frontmatter/rag-meta 字段（`status/authority/doc_scope/entity_type` 等）靠人工维护，无 schema 校验；字段缺失会静默进入"默认值"，可能被检索过滤掉 | 建立知识库规范模板 + 校验脚本（字段必填/枚举校验、`declared_source` 一致性、`building_category` 与 taxonomy 对齐） |
| **P1** | **分片参数未对比实验** | `chunk_size=900/overlap=150` 是固定值；`eval_retrieval` 平均同源率 64% 提示漏召回，可能与小分片粒度/标题切分有关 | 用 `inspect_knowledge_chunks.py` + `eval_retrieval.py` 做参数网格（如 600/900/1200 × overlap 100/150/200），比较 Top-1 距离与同源率 |
| **P1** | **embedding 模型未对比** | 仅 qwen3.7-text-embedding（1024 维）单一选择；无不同模型在同一评测集上的对照 | 编写 embedding 对比脚本：同一 28 问评测集，分别用 qwen/bge-m3/text-embedding-v3 等跑 `eval_retrieval`，比较距离分布与命中质量 |
| **P1** | **metadata 过滤利用度不足** | 检索只做 `namespace/status/authority/doc_scope` 硬过滤；`doc_type/entity_type/building_category/role_tags/constraint_tags` 等 31 个键基本未参与查询过滤（检索意图拆分后未映射到 metadata filter） | 在 `_build_rag_queries` 中让每个意图携带候选 `entity_type/building_category` 过滤，减少跨域噪声 |
| **P2** | **混合检索未接入** | `hybrid_retriever.py`（BM25+向量融合）已实现但闲置；纯向量对精确规格词（如 `"thickness": 0.3`）不敏感 | 接入主链路或在评测集中增加"精确术语"类问题对比混合/纯向量 |
| **P2** | **离线评测 embedding 不一致** | `evaluate_component_rag.py` 用 HashEmbedding(256 维)，与线上 1024 维语义向量不可比 | 统一：离线评测支持 `--embedding real` 或显式标注"仅验证流程不验证质量" |
| **P2** | **检索可观测性不足** | agent 生产日志不暴露"本次生成本次用了哪些分片、距离多少"，排障依赖重跑评测 | 在 `_agent_for_query` 增加结构化日志（query → Top-K 片段 id/距离） |

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

# 3) 跑线上检索评测（真实 embedding + 线上索引，28 问）
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
| sqlite 实证 | 直连 `chroma.sqlite3` 查 collections/segments/embeddings/embedding_metadata | dimension=1024；embeddings 表 516 行无向量列；metadata 31 键；无 documents 表；HNSW 二进制文件落盘 |
| API 实证 | `verify_chroma_api.py`（真实 embedding + `collection.get`） | count=516；向量 1024 维、float64、L2=1.0；分片样例 748 字符 |
| 真实检索 | 同脚本 `collection.query`，query=“生成一栋现代别墅…” | Top-6 全部命中 villas.md 现代别墅，distance 0.40–0.61，成熟度排序生效 |
| 工具链运行 | `check_sync_status.py` | RAGSpecLoader 启用 Chroma，collection=wild_knowledge_base |

---

*文档生成时间：2026-08-20；数据源：WildAgent wild-server 当前代码 + storage/chroma 线上索引实证。*
*（内容由AI生成，仅供参考）*
