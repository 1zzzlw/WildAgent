# RAG 单元测试：初学者阅读指南

这里测试的是 RAG 基础零件，不直接调用线上 embedding，也不会修改正式 `storage/chroma`。

## 运行

在 `wild-server` 目录：

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest tests\rag -v
```

只跑一个文件：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\rag\test_rag_semantic_chunking.py -v
```

只跑一个用例：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\rag\test_eval_retrieval_metrics.py::RetrievalMetricTest::test_mrr_uses_first_relevant_rank -v
```

## 文件与学习重点

| 文件 | 测什么 | 适合学习的 Python |
|---|---|---|
| `test_eval_retrieval_metrics.py` | Hit/Recall/MRR 公式 | list、dict、函数返回值、断言 |
| `test_rag_semantic_chunking.py` | 标题、metadata、JSON/表格、上下文原子性 | 临时文件、类、循环、Mock |
| `test_rag_index_sync.py` | Chroma 增量新增、更新、删除与相邻 part | 集合差、假对象、调用参数 |
| `test_rag_retrieval_cache.py` | 查询缓存键何时相同或失效 | 稳定哈希、输入组合 |
| `test_query_planner.py` | 查询别名、过滤条件和安全改写 | dataclass、过滤、白名单 |

## 一个测试怎么看

以 `test_mrr_uses_first_relevant_rank` 为例：

1. 准备两条模拟命中；
2. 把正确来源放在第 2；
3. 调用 `score_ranked_hits()`；
4. 断言 `first_relevant_rank == 2`；
5. 断言倒数排名 `MRR == 0.5`。

测试函数名称通常就是它要证明的规则。阅读时先看测试输入和最后几行 `assert`，再进入生产函数。

## 结果怎么看

- `PASSED`：这个规则仍成立；
- `FAILED`：断言不成立，pytest 会显示期望值与实际值；
- `ERROR collecting`：测试尚未开始，通常是依赖、导入或本机 Python 环境问题；
- `ModuleNotFoundError: app`：通常忘了在 `wild-server` 目录运行，或没有设置 `PYTHONPATH="."`。

当前目录共有 27 个用例。新增或删除测试后，以 pytest 最后一行显示的实际数量为准，不需要依赖文档中的固定数字。

## 单元测试与召回评测的区别

- 单元测试回答“代码规则有没有被改坏”；
- `eval_retrieval.py` 回答“真实问题能不能召回标准知识”；
- 两者都通过，仍不能证明 Agent 最终采用了知识；那需要记录节点 Prompt、RAG 命中和 Blueprint 输出做流程评测。
