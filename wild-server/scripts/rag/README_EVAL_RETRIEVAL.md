# `eval_retrieval.py` 详细说明

这个脚本调用生产 `RAGSpecLoader.retrieve()`，用固定问题集检查“正确知识能否进入 Top-K”。默认评测集带标准来源，因此会自动计算 Hit@K、Recall@K 和 MRR。

## 最常用命令

在 `wild-server` 目录执行：

```powershell
$env:PYTHONPATH="."

# 只读当前真实索引
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py

# 本地 hash 冒烟，不需要 API Key，不代表真实语义质量
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py --embedding hash --limit 5

# 真实 embedding + 临时索引，适合安全测试分片参数
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --temporary-index --chunk-size 900 --chunk-overlap 150
```

## 索引模式

| 命令 | embedding | 索引位置 | 会改正式索引吗 | 适用场景 |
|---|---|---|---|---|
| 默认 | 配置中的模型 | 已有 `storage/chroma` | 否 | 当前线上基线；先确认报告不是 hash fallback |
| `--embedding hash` | 本地 hash | 临时目录 | 否 | 程序冒烟 |
| `--temporary-index` | 配置中的真实模型 | 临时目录 | 否 | 分片参数/知识版本实验 |
| `--sync-index` | 配置中的真实模型 | `storage/chroma` | 是 | 明确需要同步正式索引时 |

正式索引默认只读。只有你明确传入 `--sync-index` 时，Loader 才会根据当前知识库执行增量更新/删除。

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--questions` | `evals/rag_retrieval_cases.json` | JSON 可自动判分；纯文本只能人工看 |
| `--limit` | 全部 | 只跑前 N 题 |
| `--top-k` | 5 | 语义候选数量 |
| `--namespace` | `wild_spec` | Chroma 逻辑命名空间 |
| `--embedding auto\|hash` | `auto` | 真实 embedding 或本地冒烟 embedding |
| `--temporary-index` | 关闭 | 临时重建索引，不修改正式库 |
| `--sync-index` | 关闭 | 同步正式索引后再评测 |
| `--chunk-size` | 项目配置 | 仅允许与临时索引一起使用 |
| `--chunk-overlap` | 项目配置 | 仅允许与临时索引一起使用 |
| `--ignore-case-filters` | 关闭 | 不使用每题 metadataFilter，观察纯向量基线 |
| `--output` | 时间戳报告 | 自定义 Markdown 报告路径 |
| `--log-output` | 时间戳日志 | 自定义终端日志路径 |
| `--no-log-output` | 关闭 | 不保存终端日志 |

## 报告阅读顺序

1. 先确认 embedding、索引模式、namespace、Top-K 和问题数相同；
2. 看 Hit@K：有多少题至少找到一个正确来源；
3. 看 Recall@K：需要多个来源的题是否找全；
4. 看 MRR：正确来源是否排在前面；
5. 打开失败题，核对标准来源、过滤条件、实际标题路径和缺失关键词；
6. 最后才参考平均距离、空召回率和同源率等诊断信号。

Loader 在命中长 section 的某个 part 后会补充相邻 part，所以报告中的实际上下文片数可能超过 `top_k`。自动评分先按 `parent_chunk_id` 把邻片折叠为一次语义命中，再取前 K 个父块。

## 如何新增一道题

在 `evals/rag_retrieval_cases.json` 的 `cases` 数组添加：

```json
{
  "id": "my_case",
  "query": "用户或 Agent 实际会问的问题",
  "topic": "用于分组的名称",
  "metadataFilter": {"doc_type": "component"},
  "expectedSources": ["components/example.md"],
  "requiredTerms": ["必须出现的事实词"]
}
```

`expectedSources` 支持文件名或相对知识库路径。相对路径更准确，尤其是不同目录存在同名文件时。

不要为了让分数好看而把当前错误命中写成标准答案。标准答案应由知识事实和生产需求决定。

## 常见错误

- “namespace 下没有分片”：当前索引未建立或命名空间不一致；可先用 `--temporary-index` 验证。
- “索引签名不一致”：当前 embedding 或分片配置和已有向量不兼容；默认会停止而不会删除正式集合，实验请用 `--temporary-index`。
- embedding API 失败：检查 `.env` 中 embedding 配置；也可先用 `--embedding hash` 排除代码问题。
- 想改 chunk 参数但脚本拒绝：加 `--temporary-index`。旧索引不会因为命令行参数自动重新分片。
- 空召回为 0，但 Recall 很低：说明检索返回了内容，只是内容不正确。
- hash 分数很好、真实模型很差：hash 仅是确定性冒烟，不具备可靠的中文语义判断能力。
