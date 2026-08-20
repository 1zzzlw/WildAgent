---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_99138da39c4911f184de525400f8a581
    ReservedCode1: gejGZnmfBcymXIdcs2eQkxm9DWB86kCRhF3rGGcfnfGAXoY9TXYrztnGfr0uah++9hScePxSrvr4Fue+pxwAwI+bvWMut0fskcZ8JCouMeBIAx9hCbPy5nbqGAEGgHo9TyiaeWzDPIv970qhAeTw6GFVtvp536w0wRhUOyFo2cGJKxMwIXVkCKy2CAc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_99138da39c4911f184de525400f8a581
    ReservedCode2: gejGZnmfBcymXIdcs2eQkxm9DWB86kCRhF3rGGcfnfGAXoY9TXYrztnGfr0uah++9hScePxSrvr4Fue+pxwAwI+bvWMut0fskcZ8JCouMeBIAx9hCbPy5nbqGAEGgHo9TyiaeWzDPIv970qhAeTw6GFVtvp536w0wRhUOyFo2cGJKxMwIXVkCKy2CAc=
---





# rag/ — 知识库分片与 RAG 评测脚本

RAG 相关的检查、展示与评测工具，覆盖知识库同步状态、分片质量、分片展示报告、组合构件检索评测与线上索引检索效果评测。

## 文件清单

| 文件 | 作用 |
|---|---|
| `check_sync_status.py` | 打印知识库同步状态：总文档片段数、已更新/已删除片段数、Spec Loader 类型与来源文档数。 |
| `inspect_knowledge_chunks.py` | 知识库分片检查：对单个 Markdown 文件或整个知识库目录分片，打印分片明细（metadata、内容摘要）、统计与合法性检查；控制台日志与 Markdown 检查报告默认输出到 `scripts/reports/`，用于验证分片策略。 |
| `inspect_chunks_demo.py` | 分片展示报告：控制台打印每个分片的来源、数量、字符数、内容摘要与合法性检查，同时写入 Markdown 报告；控制台输出默认另存为日志文件。 |
| `evaluate_component_rag.py` | 组合构件固定 RAG 评测集：固定问题集 + 临时 Chroma + 本地 HashEmbeddingFunction，验证真实分片、metadata 过滤、召回与排序；无需 API Key，不修改 `storage/chroma`。 |
| `eval_retrieval.py` | **线上索引检索效果评测**：调用真实检索链路（`RAGSpecLoader.retrieve` + config embedding + `storage/chroma` 线上索引），对内置/外部问题集逐条执行 Top-K 检索，输出命中明细、汇总统计与 Markdown 评测报告（`scripts/reports/eval_retrieval_<时间戳>.md` + Tee 日志），量化评估知识库检索效果。 |
| `README_INSPECT_CHUNKS.md` | `inspect_knowledge_chunks.py` / `inspect_chunks_demo.py` 的详细使用文档（参数、示例、常见场景）。 |
| `README_EVAL_RETRIEVAL.md` | `eval_retrieval.py` 的详细使用文档（参数、示例、"报告怎么看"完整说明、优化方向指引）。 |

## 运行方式

需在 **wild-server 根目录** 下运行，并设置 `PYTHONPATH="."`：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py storage\knowledge_base --table
.\.venv\Scripts\python.exe scripts\rag\check_sync_status.py
.\.venv\Scripts\python.exe scripts\rag\evaluate_component_rag.py
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py
```

或使用 uv（免手动激活）：

```powershell
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

## 输出说明

- `inspect_knowledge_chunks.py` 默认将 Markdown 检查报告与控制台日志输出到 `scripts/reports/`（`inspect_chunks_<时间戳>.md`、`chunks_console_<时间戳>.txt`），可用 `--output` / `--log-output` 自定义路径，`--no-log-output` 关闭日志保存。
- `inspect_chunks_demo.py` 默认将 Markdown 报告与控制台日志输出到 `scripts/reports/`（`chunks_report_<时间戳>.md`、`chunks_console_<时间戳>.txt`），可用 `--output` / `--log-output` 自定义。
- `eval_retrieval.py` 默认将评测报告与控制台日志输出到 `scripts/reports/`（`eval_retrieval_<时间戳>.md`、`eval_console_<时间戳>.txt`），支持 `--questions` / `--limit` / `--top-k` / `--namespace` / `--embedding`（`real`=线上真实 embedding，`hash`=本地降级 embedding，默认 `real`），可用 `--output` / `--log-output` 自定义路径。
- 详细用法见 [README_INSPECT_CHUNKS.md](README_INSPECT_CHUNKS.md) 与 [README_EVAL_RETRIEVAL.md](README_EVAL_RETRIEVAL.md)。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
