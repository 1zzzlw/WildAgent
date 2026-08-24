# WildAgent RAG：从分片到召回率的入门实验手册

这套脚本解决两个问题：

1. Markdown 最终被切成了什么样的分片？
2. 分片向量化后，正确知识能否进入 Top-K？

先不要急着改 embedding、加 BM25 或 rerank。建议先建立一份可重复的基线报告，再一次只改一个变量。

## 1. 先理解完整流程

```text
知识库 Markdown
  ↓ MarkdownChunker：按标题、实体 metadata、长度兜底分片
SpecChunk（正文 + 来源 + 标题路径 + entity_type 等 metadata）
  ↓ embedding：把每个分片变成一组数字
Chroma 向量索引
  ↓ 把用户问题也向量化并计算距离
Top-K 候选
  ↓ 去重、过滤 proposed/inferred、补相邻 part
注入 architecture / skeleton / component / callback / chat 节点的 Prompt
```

可以把 embedding 想成“把句子的意思转换为坐标”。用户问题和某个分片越接近，通常越容易被召回。

项目真正使用的分片器是 `app/spec/loader.py` 中的 `MarkdownChunker`。下面的检查脚本直接调用它，不是另写一套简化模拟算法。

## 2. 现有脚本分别测什么

| 文件 | 测试层次 | 能回答的问题 | 不能回答的问题 |
|---|---|---|---|
| `inspect_knowledge_chunks.py` | 分片预览 | 标题、JSON、表格、metadata、长度是否正确 | 向量语义排序好不好 |
| `inspect_chunks_demo.py` | 分片展示 | 与上一个脚本相近，但报告更详细 | 不能计算召回率；功能有部分重复 |
| `eval_retrieval.py` | 检索质量 | 真实/临时索引的 Hit@K、Recall@K、MRR 和命中明细 | Agent 召回后是否真的采用知识 |
| `check_sync_status.py` | 运行状态 | 当前服务 Loader 和同步数量 | 分片或召回质量 |

推荐把 `inspect_knowledge_chunks.py` 当作主要分片工具；`inspect_chunks_demo.py` 暂时保留用于查看更完整的展示报告，不必两个都跑。

## 3. 第一次运行：只做三个实验

所有命令都在 `wild-server` 目录执行：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
```

### 实验 A：看一个文件如何分片

```powershell
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py `
  storage\knowledge_base\components\windows-supported.md `
  --show-content --no-log-output
```

先检查：

- 每片开头是否有“知识路径”；
- JSON 是否从开头到结尾都在同一片；
- 表格被拆分后是否重复表头；
- `entity_type`、`entity_name`、`topic` 是否属于当前内容；
- 有没有只有标题、没有正文的空壳片。

### 实验 B：离线跑通检索流程

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --embedding hash --limit 5 --no-log-output
```

这个命令会创建临时 Chroma，用完自动清理，不访问正式索引，也不需要 API Key。它只能证明程序链路能跑，不能证明中文语义召回质量。

### 实验 C：评测当前真实向量索引

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py
```

默认行为是：

- 使用配置中的 embedding；报告应确认不是 `HashEmbeddingFunction` 后再作为语义质量结论；
- 只读已有 `storage/chroma` 分片，不自动同步知识库；
- 使用 `evals/rag_retrieval_cases.json` 的标准答案；
- 输出 Hit@K、Recall@K、MRR 和逐题命中来源。

如果索引还没建立，不要直接改正式库。可以安全地临时重建：

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py --temporary-index
```

配置完整时这会调用真实 embedding，可能产生 API 用量，但索引写在临时目录，不修改 `storage/chroma`。若配置允许 hash fallback，务必先看报告中的 embedding 类型。

## 4. 三个核心指标怎么理解

### 4.1 先理解 K 和标准答案

`K` 表示只检查排在最前面的 K 个检索结果。例如：

- `Hit@1` 只看第 1 名；
- `Hit@3` 看前 3 名；
- `Recall@5` 看前 5 名找回了多少标准来源。

本项目先按 `parent_chunk_id` 把同一章节的相邻子片合并成一次排名，再取前 K 个父级 section。因此，Loader 为一条命中补充的相邻片不会重复占用 K 个名额。

指标不能凭空判断结果是否正确。每道可自动评分的问题必须在 `evals/rag_retrieval_cases.json` 中提供 `expectedSources`，也就是人工确认的标准来源。没有 `expectedSources` 的临时问题仍会显示命中明细，但不会参与 Hit@K、Recall@K 和 MRR 的总体计算。

### 4.2 用一个例子计算

假设问题需要同时参考两份标准来源：

```text
components/windows-supported.md
components/doors-supported.md
```

实际 Top-3 返回：

```text
1. walls.md
2. windows-supported.md
3. roofs-and-eaves.md
```

这道题的结果是：

| 指标 | 计算 | 结果 | 表示什么 |
|---|---|---:|---|
| `Hit@3` | 前 3 名至少出现一个标准来源 | `1` | 命中过，但不能说明是否找全 |
| `Recall@3` | 找到 1 个 ÷ 应找 2 个 | `0.5` | 只找回了一半标准来源 |
| `Reciprocal Rank` | 第一条正确结果排第 2，因此 `1 ÷ 2` | `0.5` | 正确结果出现得不够靠前 |

### 4.3 Hit@K：有没有至少找到一个正确来源

单题只有两种结果：

```text
Top-K 至少命中一个 expectedSources → 1
Top-K 一个标准来源也没命中       → 0
```

报告中的总体 `Hit@K` 是所有可评分问题的平均值。例如 10 道题中有 8 道至少命中一个标准来源，`Hit@K = 80%`。

它适合回答“多数问题能不能碰到正确知识”，但无法判断多个标准来源是否全部找齐。一道题需要 3 份来源、只找到 1 份时，Hit 仍然是成功。

### 4.4 Recall@K：应该找到的来源找回了多少

单题计算方式：

```text
Recall@K = Top-K 命中的标准来源数量 ÷ 该题标准来源总数
```

如果标准来源有 4 份，Top-K 找到 3 份，那么该题 `Recall@K = 3/4 = 75%`。报告中的总体 Recall 是“每道题 Recall 的宏平均”：先分别计算每道题，再让每道题以相同权重参与平均，不会因为某一道题标准来源更多就占更大权重。

Recall 适合回答“知识有没有找全”，但不会惩罚无关结果。Top-5 中找全 2 个标准来源、同时混入 3 个错误来源时，Recall 仍然是 100%。当前脚本没有计算 Precision@K，因此还要查看逐题命中明细判断噪声。

### 4.5 MRR：第一个正确来源排得有多靠前

MRR 是 Mean Reciprocal Rank，即“平均倒数排名”。先计算每道题第一条正确结果的倒数排名：

| 第一条正确结果的位置 | 单题倒数排名 |
|---:|---:|
| 第 1 名 | `1/1 = 1.0` |
| 第 2 名 | `1/2 = 0.5` |
| 第 3 名 | `1/3 ≈ 0.333` |
| Top-K 没有正确结果 | `0` |

最后对所有可评分问题取平均，得到报告里的 `MRR@K`。它适合衡量“正确知识是否排在前面”，但只关注第一条正确结果：第二、第三份标准来源是否缺失，需要看 Recall@K。

### 4.6 三个指标要一起看

| 现象 | 通常说明什么 |
|---|---|
| Hit 高、Recall 低 | 大多数问题能碰到正确知识，但需要的多个来源没有找全 |
| Hit 高、MRR 低 | 能找到正确知识，但正确结果排名靠后 |
| Recall 高、MRR 高 | 正确来源比较完整，而且排位靠前 |
| 三项都低 | 先检查标准答案、metadata 过滤、知识内容和分片，再考虑 embedding 或 rerank |

“空召回率”只表示有没有返回任何内容。返回五条错误内容时，空召回率仍是 0%，所以它不能代替 Recall@K。

距离只适合同一个 embedding 模型、同一种距离配置之间比较。换模型后，不要直接比较距离数字。

这些指标只评价“检索阶段有没有把正确知识放进 Top-K”，不能证明后续 Agent 已经阅读、理解并正确使用了这些知识。

## 5. 标准答案文件怎么写

默认评测集是 `evals/rag_retrieval_cases.json`：

```json
{
  "id": "comp_window",
  "query": "默认窗的 geometry.components 参数有哪些",
  "topic": "构件-窗",
  "metadataFilter": {
    "doc_type": "component",
    "entity_type": "window"
  },
  "expectedSources": ["components/windows-supported.md"],
  "requiredTerms": ["geometry.components", "parentWall"]
}
```

字段含义：

| 字段 | 用途 |
|---|---|
| `id` | 稳定编号，报告中定位失败问题 |
| `query` | 模拟用户或 Agent 的检索问题 |
| `topic` | 只用于报告分组 |
| `metadataFilter` | 模拟生产节点的业务过滤条件 |
| `expectedSources` | 标准来源；自动计算 Recall@K 的依据 |
| `requiredTerms` | Top-K 内容至少应包含的关键事实词，属于辅助覆盖检查 |

想看“纯向量、不加 metadata 过滤”的基线：

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py --ignore-case-filters
```

也可以传入自己的 JSON：

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py --questions evals\my_cases.json
```

纯文本问题文件仍然支持 `id|query`，但因为没有 `expectedSources`，只能看命中明细，不能自动计算召回率。

## 6. 安全比较不同分片参数

要比较 `chunk_size`，必须重新分片、重新 embedding、重新建索引。只在命令后写一个数字但继续读取旧索引，实验是无效的。

下面三次实验都使用真实 embedding + 临时索引：

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --temporary-index --chunk-size 600 --chunk-overlap 100 `
  --output scripts\reports\eval_chunk_600.md --no-log-output

.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --temporary-index --chunk-size 900 --chunk-overlap 150 `
  --output scripts\reports\eval_chunk_900.md --no-log-output

.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --temporary-index --chunk-size 1200 --chunk-overlap 200 `
  --output scripts\reports\eval_chunk_1200.md --no-log-output
```

比较时保持以下变量不变：评测集、embedding 模型、Top-K、metadata 过滤、知识库版本。否则无法判断差异究竟来自哪里。

`MarkdownChunker` 的 `chunk_size` 是普通长文本的兜底预算，不会强行切断 fenced JSON；超长代码块会保持原子并交给文档 linter 提醒重构。

## 7. 看到失败后先改哪里

| 报告现象 | 先检查 | 常见优化方向 |
|---|---|---|
| 标准来源根本不存在 | 知识库是否有对应事实 | 补知识，不要先调向量参数 |
| 正确章节被切成多个不自包含片 | Markdown 标题和实体边界 | 重构标题、metadata 和原子知识单元 |
| 纯向量失败，加过滤后成功 | metadata 是否稳定、节点是否传过滤 | 完善分类和生产查询计划 |
| Top-K 有正确来源但排名靠后 | 同主题重复文档、分片语义、embedding | 去重、增强标题上下文，再考虑 rerank |
| Recall 好但 Agent 输出仍错 | Prompt 中实际注入内容和节点行为 | 进入“Agent 吸收质量”测试，不再归因于召回 |
| 大量命中 `proposed/inferred` | status/authority metadata | 修 metadata 或过滤逻辑 |

推荐优化顺序：

1. 评测集是否覆盖真实建筑问题；
2. 知识内容是否正确、完整、无冲突；
3. 分片是否自包含；
4. metadata 和查询过滤是否正确；
5. embedding 与 Top-K；
6. 最后才是查询改写、混合检索和 rerank；
7. 再检查 Agent 是否采用了已召回知识。

项目中虽然已有 `app/agent/rag/hybrid_retriever.py`，但当前生产主链路仍由 `RAGSpecLoader` 的 Chroma 向量检索承担，不能把已有文件等同于功能已接入。

## 8. 用这些文件学习 Python

建议按这个顺序读：

1. `evals/rag_retrieval_cases.json`：先理解输入数据；
2. `tests/rag/test_eval_retrieval_metrics.py`：学习函数输入、返回值和断言；
3. `tests/rag/test_rag_semantic_chunking.py`：学习临时文件、类和 Mock；
4. `scripts/rag/eval_retrieval.py`：学习 argparse、循环、统计和报告生成；
5. `app/spec/loader.py`：最后再读生产分片、Chroma 同步与召回。

遇到陌生语法时，先追一个具体数据，例如一条 case 如何变成一个 `score`，不要试图一次读完整个 Loader。

## 9. 单元测试

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest tests\rag -v
```

单元测试使用临时文件、Mock 或临时索引，不会修改正式 Chroma。详细说明见 `tests/rag/README.md`。

## 10. 输出文件

默认报告写入 `scripts/reports/`：

- `inspect_chunks_<时间戳>.md`：分片检查报告；
- `eval_retrieval_<时间戳>.md`：召回评测报告；
- `*_console_<时间戳>.txt`：终端日志。

这些都是运行产物，可以用 `--output`、`--log-output` 指定路径，或用 `--no-log-output` 关闭控制台日志保存。

更详细的参数说明：

- [README_CHUNK_RESULTS.md](README_CHUNK_RESULTS.md)：拿到分片输出后逐字段怎么判断
- [README_INSPECT_CHUNKS.md](README_INSPECT_CHUNKS.md)
- [README_EVAL_RETRIEVAL.md](README_EVAL_RETRIEVAL.md)
