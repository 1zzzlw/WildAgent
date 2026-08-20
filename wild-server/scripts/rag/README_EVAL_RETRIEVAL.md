---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_ec9b634e9b7411f18cca525400e6dd8f
    ReservedCode1: PcCRc+WVZEU7mc91a6nnLpYSbeyxDbuJL1+Tw3LlzoPKQX1h/jMBBxk4f+RXOoujVNyUM7/qnVNnHrtV1Rw1W/suWBBAQE7MTpPQ+ZBx5mWVBG8LBSjeXo1CIhIB9+SXVaHbP3Uj0fRHNnKL8c+GkMbNsY2yrTWYCRukvyFSt/eyZya71uQd/oz5If0=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_ec9b634e9b7411f18cca525400e6dd8f
    ReservedCode2: PcCRc+WVZEU7mc91a6nnLpYSbeyxDbuJL1+Tw3LlzoPKQX1h/jMBBxk4f+RXOoujVNyUM7/qnVNnHrtV1Rw1W/suWBBAQE7MTpPQ+ZBx5mWVBG8LBSjeXo1CIhIB9+SXVaHbP3Uj0fRHNnKL8c+GkMbNsY2yrTWYCRukvyFSt/eyZya71uQd/oz5If0=
---



# RAG 检索评测（eval_retrieval.py）使用说明

`eval_retrieval.py` 是 RAG 检索效果的量化评测工具：它**调用项目真实检索链路**
（`app/spec/loader.py` 的 `RAGSpecLoader.retrieve` + `config` 中的 embedding 配置与线上
Chroma 索引），对一批典型问题逐条执行 Top-K 检索，输出命中明细与汇总统计，并生成
Markdown 报告与控制台日志。

- 与 `evaluate_component_rag.py` 的区别：后者用**临时 Chroma + 本地 HashEmbeddingFunction**
  验证"真实分片 + metadata 过滤"，不读线上向量；本脚本默认**读取线上持久化索引**
  `storage/chroma`（集合 `wild_knowledge_base`），评测的是真实生产检索效果。
- 与 `inspect_knowledge_chunks.py` 的区别：后者检查**分片本身**（粒度、标题路径、合法性），
  本脚本检查**检索出来的效果**（召回、排序、命中分布）。

## 运行方式

需在 **wild-server 根目录** 运行，并设置 `PYTHONPATH="."`：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py
```

或使用 uv（免手动激活，且保证 Python 版本足够新，系统 Python 过低会报 f-string 语法错误）：

```powershell
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py
```

示例命令：

```powershell
# 使用内置问题集评测线上索引（默认 top_k=5）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py

# 只跑前 10 条问题（快速冒烟）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --limit 10

# 自定义 Top-K
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --top-k 8

# 从外部文件加载问题（每行一条，支持 "id|query" 或纯 query）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --questions my_questions.txt

# 指定逻辑命名空间（默认 wild_spec，必须与索引一致）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --namespace wild_spec

# 离线 smoke：本地 hash embedding + 临时索引，不读线上向量
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --embedding hash

# 自定义报告与日志输出路径 / 关闭日志
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --output reports/eval.md --log-output reports/eval.log
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py --no-log-output
```

## 参数说明

| 参数 | 默认 | 说明 |
|---|---|---|
| `--questions <file>` | 内置问题集 | 外部问题文件路径，每行一条；`id\|query` 格式可自定义编号，纯 query 自动编号 |
| `--limit <n>` | 全部 | 限制评测问题数（取问题集前 n 条） |
| `--top-k <n>` | 5 | 每个问题保留的 Top-K 命中数 |
| `--namespace <ns>` | `wild_spec` | 逻辑命名空间，**必须与索引中分片的 namespace 一致**（线上索引默认 `wild_spec`）；不一致会得到 0 分片并报错提示 |
| `--embedding auto\|hash` | auto | `auto` 用 `config` 真实 embedding（线上索引）；`hash` 用本地 HashEmbeddingFunction + **临时目录重建索引**，仅离线 smoke |
| `--output <path>` | `scripts/reports/eval_retrieval_<时间戳>.md` | 报告 Markdown 输出路径 |
| `--log-output <path>` | `scripts/reports/eval_console_<时间戳>.txt` | 控制台日志保存路径（Tee 双写） |
| `--no-log-output` | 关闭 | 不保存控制台日志 |

## 问题集

- **内置问题集**：28 条，覆盖建筑类型（凉亭/别墅/塔楼/木屋/合院/住宅/宿舍酒店/办公学校/商业/工业/农业）、
  构件组装（窗/门/墙/栏杆/屋顶/幕墙/洞口/雨棚/凸窗/结构构件）、材质（住宅/公共色板）、
  装配关系与模板、能力边界、高细节模式等知识库主题。每条带 `id` 与 `topic` 主题标注，
  用于报告分组与人工复核。
- **外部问题文件**：每行一条，空行与 `#` 注释行跳过。示例：

  ```text
  # 自定义问题集
  q_custom_1|怎么生成中式四角凉亭
  玻璃幕墙的龙骨间距默认是多少
  ```

## 报告怎么看（重点）

报告默认输出到 `scripts/reports/eval_retrieval_<时间戳>.md`，分为五部分：
**头部信息 / 汇总统计 / 信号提示 / 分组分布 / 逐题明细**。下面按阅读顺序讲解。

### 0. 头部信息

| 字段 | 含义 |
|---|---|
| 索引 / collection / embedding | 本次评测用的向量库、集合名与 embedding 类型，**跨配置对比时先对齐这一行** |
| 总分片数 | 索引中的分片总量（`total`）；括号内的 `updated/deleted` 是本次启动时索引同步的增量（`updated` 多为 metadata 刷新，不表示向量重建） |
| 问题数 / Top-K | 评测规模与召回深度 |

### 1. 汇总统计表 — 数字怎么理解

| 指标 | 好 | 差 | 怎么理解 |
|---|---|---|---|
| 空召回数 / 空召回率 | 0 | >20% 重点排查 | 完全没召回任何分片的问题占比。高说明问题用词与知识库语义空间不对齐，或 namespace 错配 |
| 检索异常数 | 0 | >0 | embedding 服务/网络导致的查询失败，通常与检索质量无关，先排除环境问题 |
| 平均命中距离 | 越小越好 | 明显偏大 | 所有命中的语义距离均值，反映整体相关度；**注意**：距离只在同一 embedding 下可比，换 embedding 后数字不可直接对比 |
| 平均 Top-1 距离 | 越小越好 | 明显偏大 | 每条问题首条命中的平均距离。Top-1 是实际进入上下文概率最高的分片，比全量均值更贴近"首屏体验" |
| 每问平均命中数 | 接近 Top-K | 远小于 Top-K | Top-K 被有效填充的程度。明显偏低说明很多问题召不满，可能是知识库覆盖不足或分片过碎 |
| 平均同源率 | 适中（30%-60%） | >60% | 每个问题 Top-K 中来自同一文件的占比均值。**过高提示漏召回**：相关内容可能分散在多个文件，但只召回了单一文件 |

### 2. 信号提示

脚本基于汇总统计自动生成观察信号（如空召回率高、同源率偏高、平均距离偏大），
是报告自带的"第一层诊断"，但**不能替代人工逐题复核**——它只发现统计异常，不判断语义是否正确。

### 3. 分组分布（按实体 / 按文件）

- **按实体分组**：看哪些 `entity_name` 高频命中。若高频实体与问题主题明显不符（例如大量命中
  `blueprint_spec_full` 而问题都是构件参数），说明**泛化召回过强、精准性不足**。
- **按文件分组**：看命中集中在哪些来源文件。期望是"问题主题 -> 对应文件"一一对应；
  若某文件被大量无关问题命中，该文件分片可能语义过宽（一个分片混了多个主题）。

### 4. 逐题明细 — Top-K 命中分片表怎么读

每个问题一张表，列含义：

| 列 | 作用 |
|---|---|
| 排名 | 相关度从高到低，Top-1 最重要 |
| 距离 | 语义距离，越小越相关；`-` 表示该命中未返回距离（部分来源分片无向量距离，常见于 base 规范分片） |
| 来源文件 | 命中分片所属文件，**判断"是否答非所问"的第一依据** |
| 标题路径 | 分片在文档树中的层级（如 `居住建筑：别墅 > 1.1 现代别墅 > 最少可行...`），判断命中的是"正确章节"还是"恰好同文件的错误章节" |
| 实体 | metadata 的 `entity_name`，辅助确认主题 |
| 内容摘要 | 分片正文前 80 字符，用于快速人工判断命中是否真的有用 |

阅读步骤：
1. 先看 **Top-1 的来源文件 + 标题路径** 是否与问题主题匹配（例如"玻璃幕墙怎么组装"应命中
   `glass-curtain-wall-assembly.md`）；
2. 再看 **Top-2 ~ Top-K** 是否有"次优但有用"的补充分片（好检索通常 Top-3 内就有多个可用分片）；
3. 若 Top-1 就偏题，记为**乱召回**；若 Top-K 里根本没有预期文件，记为**漏召回**。

### 5. 哪些信号说明检索好 / 差

**检索好**：
- 空召回率 0%，每问命中数接近 Top-K；
- Top-1 的来源文件与标题路径与问题主题一一对应；
- 平均同源率在 30%-60%：Top-K 既有主文件，也有补充文件；
- 逐题复核时 Top-3 内能找到"可直接用于回答"的分片。

**检索差（常见失败模式）**：

| 失败模式 | 报告中的表现 | 典型原因 |
|---|---|---|
| **漏召回** | 空召回率 >0；或命中数远小于 Top-K；或同源率 >60% 且预期文件没出现 | 问题用词与知识库关键词差异大（embedding 泛化不足）；相关内容被切碎到多个分片，单个分片向量太弱；知识库本身缺该主题 |
| **乱召回** | Top-1 来源文件与问题主题不符；按文件分组中某文件被大量无关问题命中 | 分片粒度太大，一个向量混多个主题；embedding 对建筑领域术语区分度不足；metadata 过滤未用上 |
| **浅召回（召回了但没用）** | 命中数满但内容摘要与问题不相关；平均距离偏大 | 泛化召回过强（如大量命中 BLUEPRINT-SPEC-FULL 规范文件），需要 metadata 过滤或调整检索策略 |
| **召不满（上下文碎片化）** | 每问命中数稳定偏低 | 分片过碎（<150 字符）导致单个分片信息量不足；或 Top-K 相对知识库规模偏小 |

### 6. 根据报告如何决定下一步优化方向

| 观测到的问题 | 建议优化方向 |
|---|---|
| 空召回率高 / 漏召回 | ① 检查问题用词是否贴近知识库关键词（先看知识库原文，调问题措辞再测一次）；② 调大 `chunk_size` 让分片信息更完整；③ 检查知识库是否缺该主题，补充文档；④ 检查 embedding 模型是否适合领域 |
| 同源率过高（>60%） | ① 说明检索"只见树木不见森林"，检查相关主题是否被拆到多个文件而缺少交叉引用；② 考虑父子分片/标题路径拼接让上下文更完整；③ 调小 `chunk_size` 使分片粒度更细、更易召回不同来源 |
| 乱召回（Top-1 偏题） | ① 调小 `chunk_size` 减少"一个向量混多主题"；② 加强 metadata（`entity_type`/`building_category`）并在检索时用 `metadata_filter` 过滤；③ 检查是否大量命中 base 规范文件（BLUEPRINT-SPEC-FULL），必要时将其移出候选或降低权重 |
| 平均距离整体偏大 | ① 换更强的 embedding 模型（在 `.env` 中调整 `EMBEDDING__NAME`）；② 检查分片语义完整性；③ 对比 `--top-k` 下是否有靠后分片反而更有用（说明排序策略需调整） |
| 某文件被大量无关问题命中 | ① 检查该文件分片是否过宽（拆分段落）；② 检查其 metadata 是否缺失导致无法过滤；③ 考虑在检索策略中对该文件降权 |
| 想系统性对比配置 | 用同一问题集跑多组 `--chunk-size` / `--chunk-overlap` / `--top-k`，对比各报告的"空召回率 + 平均 Top-1 距离 + 平均同源率"三维度 |

## 降级方案

- **无 API Key 或 embedding 服务不可达**：默认 `--embedding auto` 会尝试加载
  `config.embedding`（`.env` 中 `EMBEDDING__NAME` / `EMBEDDING__API_KEY` /
  `EMBEDDING__BASE_URL`，线上为 qwen3.7-text-embedding / dashscope）。缺失或网络不通时，
  脚本会报错并给出提示；此时可：
  1. 配置 `.env` 补齐 `EMBEDDING__API_KEY` 后重跑；
  2. 或使用 `--embedding hash` 做**离线 smoke**：本地 HashEmbeddingFunction + 临时目录
     重建一个临时索引（不读线上向量、不修改 `storage/chroma`），仅验证真实分片与检索
     链路可用性，**不能作为线上质量结论**。
- **注意**：`--embedding hash` 与线上 qwen 向量空间不兼容，若直接打开线上集合会触发
  `index_signature` 不匹配而重建索引（危险），因此脚本强制将其隔离到临时集合。

## 产物

- 报告：`scripts/reports/eval_retrieval_<时间戳>.md`
- 日志：`scripts/reports/eval_console_<时间戳>.txt`（控制台原始输出，Tee 双写，与终端逐行一致）

两个产物均为运行生成，可随时清理；`--output` / `--log-output` 可自定义路径。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
