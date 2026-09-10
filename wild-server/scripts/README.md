---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_962efdeb9c4911f19046525400287e28
    ReservedCode1: 46E6t7yt17SFbATr6Ts8M9sLXtdUgJlWVOMMy5pFX7K1ODbCGq4CE3+1QOlcMPH1pj1frrpZm2MMomB4Xx/IISi5P4r0ObDT4priRfZBr1O4cm9KFgQGPAw8kpCNejL19xefZqBIP9/v1NxD2CfGfP5qOLmZj5I+4+CZipGyRF/T8ii9XJRqDM5tcEQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_962efdeb9c4911f19046525400287e28
    ReservedCode2: 46E6t7yt17SFbATr6Ts8M9sLXtdUgJlWVOMMy5pFX7K1ODbCGq4CE3+1QOlcMPH1pj1frrpZm2MMomB4Xx/IISi5P4r0ObDT4priRfZBr1O4cm9KFgQGPAw8kpCNejL19xefZqBIP9/v1NxD2CfGfP5qOLmZj5I+4+CZipGyRF/T8ii9XJRqDM5tcEQ=
---



# scripts/ 脚本目录

wild-server 的辅助脚本目录，按功能分类组织为 `deploy/`、`rag/`、`building/` 和 `reports/`。

## 运行前提

所有脚本需在 **wild-server 根目录** 下运行，并设置 `PYTHONPATH="."`（脚本依赖 `app.*`、`config` 等包）：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
```

推荐使用项目虚拟环境解释器直接运行（能复用已装依赖），或使用 uv（免手动激活）：

```powershell
# venv 解释器
.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py storage\knowledge_base --table

# uv run（免手动激活）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

## 目录结构

| 目录 | 用途 |
|---|---|
| `deploy/` | 生产部署前检查脚本（模型、Embedding、镜像知识库连通性） |
| `rag/` | 知识库分片检查 / 展示 / RAG 评测脚本 |
| `reports/` | `inspect_chunks_demo.py` 等脚本生成的报告产物（Markdown 报告 + 控制台日志） |

## 文件清单

| 文件 | 作用 |
|---|---|
| `deploy/deployment_preflight.py` | 部署前默认离线检查镜像知识库；可选真实 Chat/Embedding 冒烟 |
| `rag/check_sync_status.py` | 打印知识库同步状态（总片段数、更新/删除数、RAG 检索能力） |
| `rag/inspect_knowledge_chunks.py` | 知识库分片检查：分片明细、统计、分片策略验证 |
| `rag/inspect_chunks_demo.py` | 分片展示报告：控制台展示 + Markdown 报告 + 控制台日志 |
| `rag/eval_retrieval.py` | 当前 RAG 召回率评测（Hit@K、Recall@K、MRR、逐题报告） |
| `rag/README_INSPECT_CHUNKS.md` | `inspect_*` 系列脚本的详细使用文档 |
| `reports/` | 分片报告与日志产物（`inspect_chunks_*.md`、`chunks_report_*.md`、`chunks_console_*.txt`） |

## 各脚本详细说明

> 每个脚本的完整参数表、示例与产物解读见各自子目录 README（链接见下表）。本节给出**快速上手**。

### deploy/ — 部署前检查

| 脚本 | 快速运行 | 产物 / 怎么看 |
|---|---|---|
| `deployment_preflight.py` | `.\.venv\Scripts\python.exe scripts\deploy\deployment_preflight.py` | 默认不访问供应商并输出 `preflight_mode=offline`；传入 `--live-providers` 才执行真实 Chat/Embedding 冒烟。详见 [deploy/README.md](deploy/README.md) |

### rag/ — 分片检查与 RAG 评测

| 脚本 | 快速运行 | 产物 / 怎么看 |
|---|---|---|
| `check_sync_status.py` | `.\.venv\Scripts\python.exe scripts\rag\check_sync_status.py` | 控制台打印知识库同步状态：总片段数 / 已更新 / 已删除 / Spec Loader 类型 / 来源文档数 |
| `inspect_knowledge_chunks.py` | `.\.venv\Scripts\python.exe scripts\rag\inspect_knowledge_chunks.py storage\knowledge_base --table` | `scripts/reports/inspect_chunks_<时间戳>.md` + `chunks_console_<时间戳>.txt`；报告含分片信息表 / 标题路径 / 统计分析。完整解读见 [README_INSPECT_CHUNKS.md](rag/README_INSPECT_CHUNKS.md) |
| `inspect_chunks_demo.py` | `.\.venv\Scripts\python.exe scripts\rag\inspect_chunks_demo.py storage\knowledge_base` | `scripts/reports/chunks_report_<时间戳>.md` + `chunks_console_<时间戳>.txt`；报告含每个分片来源 / 字符数 / 内容摘要 / 合法性检查 |
| `eval_retrieval.py` | `.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py` | `scripts/reports/eval_retrieval_<时间戳>.md` + `eval_console_<时间戳>.txt`；报告含汇总统计 / 信号提示 / 分组分布 / 逐题 Top-K 命中明细。完整"报告怎么看"见 [README_EVAL_RETRIEVAL.md](rag/README_EVAL_RETRIEVAL.md) |

## 导入说明

`scripts/` 下无 `__init__.py`，子目录作为 namespace package 被 Python 3.3+ 自动支持，可通过 `from scripts.deploy.deployment_preflight import ...` 导入（如 `tests/misc/test_deployment_preflight.py`）。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
