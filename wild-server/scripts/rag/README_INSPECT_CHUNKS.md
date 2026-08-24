# RAG 分片检查说明

`inspect_knowledge_chunks.py` 和 `inspect_chunks_demo.py` 都直接调用生产 `MarkdownChunker`。它们只生成内存中的分片和报告，不写 Chroma。

推荐日常使用 `inspect_knowledge_chunks.py`；需要更完整的逐片展示报告时再用 `inspect_chunks_demo.py`。

如果你已经生成了一份控制台输出，不知道每个字段和 chunk 应该怎么判断，请直接阅读 [RAG 分片结果怎么看](README_CHUNK_RESULTS.md)。其中包含一份 `windows-supported.md` 的逐片判读实例。

## 快速开始

在 `wild-server` 目录执行：

```powershell
$env:PYTHONPATH="."

# 表格快速浏览
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py `
  storage\knowledge_base\components\windows-supported.md --table

# 展开完整内容，观察真实切分边界
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py `
  storage\knowledge_base\components\windows-supported.md --show-content

# 检查整个知识库，但只处理前 5 个文件
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py `
  storage\knowledge_base --table --limit 5

# 临时模拟另一组长度参数
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py `
  storage\knowledge_base\components\windows-supported.md `
  --chunk-size 600 --chunk-overlap 100 --show-content
```

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `path` | 必填 | 一个 Markdown 文件或目录 |
| `--chunk-size` | 900 | 普通长文本长度兜底预算 |
| `--chunk-overlap` | 150 | 普通长文本相邻片重叠字符数 |
| `--show-content` | 关闭 | 输出完整 chunk 正文 |
| `--table` | 关闭 | 紧凑表格模式 |
| `--limit` | 不限制 | 目录模式只处理前 N 个文件 |
| `--output` | 时间戳报告 | 自定义 Markdown 报告 |
| `--log-output` | 时间戳日志 | 自定义控制台日志 |
| `--no-log-output` | 关闭 | 不保存控制台日志 |

`inspect_chunks_demo.py` 对应使用 `--show-full`，其他核心参数相近。

## 每个分片重点看什么

1. `heading_path`：脱离原文件后还能否知道属于哪个实体；
2. `entity_name / entity_type / topic`：能否支持生产 metadata 过滤；
3. `part_index / parent_chunk_id`：长章节拆片后是否仍属于同一个父块；
4. `status / authority`：正式召回是否会排除 proposed/inferred；
5. 正文：定义、参数、约束、JSON 是否仍然能独立理解；
6. 表格和 fenced code：有没有被从中间切断；
7. 长度分布：是否有大量极短空壳片或异常超长原子块。

## `chunk_size` 不是“无条件切到固定长度”

当前分片器先按 Markdown 标题形成业务 section，再识别普通文本、fenced code 和表格：

- fenced code 保持完整；
- 长表格按行拆分并重复表头；
- 普通长文本才使用长度兜底和 overlap；
- 每个物理子片重复知识路径；
- README 会标记成 index scope，不进入普通生成检索。

因此，发现超长 JSON 时应先重构文档实体，不要只是盲目调大 `chunk_size`。

## 推荐检查流程

1. 先看单个刚修改的 Markdown；
2. 用 `--show-content` 人工检查边界；
3. 运行 `tests/rag/test_rag_semantic_chunking.py` 防止分片规则回归；
4. 再运行 `eval_retrieval.py --temporary-index`，验证向量召回；
5. 确认报告后才考虑同步正式索引。

分片“结构合法”只说明格式没有明显坏掉，不表示事实正确，也不表示 Recall@K 一定高。
