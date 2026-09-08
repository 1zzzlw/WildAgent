# LangSmith 追踪、检索评测与 Studio

这里仅存放评测脚本和 Studio 配置。统一使用 **wild-server/.venv**、**wild-server/.env** 和原项目依赖声明，没有独立虚拟环境、独立 `.env` 或启动框架。

以下命令均在 `E:\AgentProject\WildAgent\wild-server` 目录执行。

## 1. 安装与配置

开发依赖已声明在上级 [pyproject.toml](../pyproject.toml)，同步到现有环境：

```powershell
uv sync --dev
```

在原 `wild-server/.env` 中设置以下字段。已有字段直接复用，不要重复添加：

```dotenv
LANGSMITH_API_KEY=填写你的密钥
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=wildagent
```

模型和 Embedding 继续使用原 `CHAT__*`、`THINKING__*`、`EMBEDDING__*` 配置。进程环境变量优先于 `.env`。若设置过 `UV_PROJECT_ENVIRONMENT`，需确保它指向项目现有 `.venv`。

## 2. Tracing：观察原页面触发的调用

使用官方 Uvicorn 启动命令加载原 `.env`，启动原 FastAPI 应用：

```powershell
uv run python -m uvicorn main:app --env-file .env --host 127.0.0.1 --port 8000
```

这是原后端的替代启动命令，8000 端口已有后端时先关闭旧进程。之后照常从原页面聊天、生成和审核，在 [LangSmith](https://smith.langchain.com) 的 `wildagent` 项目看调用记录。

LangGraph 节点与 LangChain 模型调用可自动追踪；普通 Python 函数不会全部自动显示为独立步骤。以后需要更细粒度的检索或装配记录时，再给对应函数加 `@traceable`。

Tracing 不需要 `evaluate()` 或额外 Python 启动脚本。开启后会向 LangSmith 发送运行输入、输出等追踪数据。

## 3. Evaluation：一个文件评测项目检索

入口：[evaluate_rag.py](evaluate_rag.py)。实际调用链：

```text
LangSmith 数据集 inputs
→ rag_target
→ 项目 RAGSpecLoader.retrieve
→ 原评测脚本的父分片合并和评分函数
→ evaluate(...)
→ LangSmith 实验结果
```

先在 LangSmith 创建数据集，例如 `wildagent-rag`。每条样例分别填写如下字段：

输入 inputs：

```json
{
  "query": "现代风格的度假别墅怎么生成",
  "metadataFilter": {"doc_type": "building_type"}
}
```

参考输出 outputs：

```json
{
  "expectedSources": ["building_types/residential/villas.md"]
}
```

可从现有 [rag_retrieval_cases.json](../evals/rag_retrieval_cases.json) 取样：将 `query`、`metadataFilter` 放进 inputs，将 `expectedSources` 放进参考 outputs。脚本读取已有云端数据集，不自动新建或重复上传样例。

运行：

```powershell
uv run python -m langsmith_tools.evaluate_rag --dataset wildagent-rag
uv run python -m langsmith_tools.evaluate_rag --dataset wildagent-rag --top-k 6 --experiment-prefix rag-routing-v2
```

也可以直接指定现有解释器：

```powershell
.\.venv\Scripts\python.exe -m langsmith_tools.evaluate_rag --dataset wildagent-rag
```

脚本加载原 `.env`，打开已有 Chroma 集合，不同步知识文件、不重建索引。签名不匹配、索引为空或缺少真实 Embedding 配置时停止。查询会调用真实 Embedding，并将实验输入输出提交 LangSmith。

指标含义：

- `hit_at_k`：前 K 个语义父块中是否出现至少一个标准来源；
- `recall_at_k`：标准来源中有多少比例被命中；
- `reciprocal_rank`：第一个正确来源排名的倒数，数据集均值为 MRR。

这里复用 [eval_retrieval.py](../scripts/rag/eval_retrieval.py) 的评分口径，相邻分片按父块合并。缺失标准来源会报告 evaluator 错误，不能解释为得分 0。查询失败会作为实验错误呈现。

本入口评测检索来源，不生成答案，也不把词面匹配冒充语义正确性。未来要评测 RAG 回答，可以在同一脚本中更换 target 并增加语义评判器。

## 4. Studio：直接运行官方开发服务器

入口为 [studio_graph.py](studio_graph.py)，复用项目 `build_generation_graph`，不复制节点。配置在 [langgraph.json](langgraph.json)。当前安装的 Python CLI 在 `dev` 模式下按命令执行目录解析依赖、图文件和环境文件，所以必须从 `wild-server` 目录执行以下命令；配置中的 `.` 和 `.env` 均指向该目录。

```powershell
uv run langgraph dev --config langsmith_tools/langgraph.json
```

`--config` 指定非默认位置的配置文件，不会把工作目录切换到该文件所在目录。省略时 CLI 默认查找命令执行目录下的 `langgraph.json`；本项目将配置集中放在子目录，因此需要指定。

`--allow-blocking` 是可选开发参数，不是启动 Studio 的必需参数。如果运行原图时确实出现同步 I/O 的 `BlockingError`，可以临时使用：

```powershell
uv run langgraph dev --config langsmith_tools/langgraph.json --allow-blocking
```

它只关闭对同步阻塞操作的报错，不会修复阻塞本身，也不能解决文件路径、导入或配置错误。原图含同步检索和文件操作，可能触发该检测，但要以具体堆栈为准。

启动后使用终端显示的 Studio 链接，选择 `wildagent` 图，输入 [studio-input.example.json](studio-input.example.json)。图输入是 `GenerationState`，不是原页面的 WebSocket 消息格式。

更换任务时修改 `user_message`、`building_type`、请求和会话 ID；测试计划模式时设置 `plan_mode=true`。图入口使用现有步数预算函数，示例的 `max_retries=3` 已与默认预算对齐；调大重试次数时还需同步调整运行配置。

遇到审核中断，在同一 Studio 线程恢复，例如：

```json
{"action": "confirm"}
```

平面方案只有 `can_confirm=true` 时可以确认，否则提交：

```json
{"action": "revise", "feedback": "保留两个卧室，缩短走廊"}
```

Studio 的检查点由 Agent Server 管理，不传入正式任务 SQLite checkpointer。它复用原业务配置：导入图可能初始化并同步原 RAG 索引，运行节点可能调用模型、Embedding 和工具，也会使用业务原有存储路径。请将它视为使用现有项目资源的开发运行。

Studio 不接管原 WebSocket 会话，不会执行原页面的进度推送和最终 Three.js 渲染。观察原页面请求用 Tracing；可视化调试图用 Studio。

## 5. 验证与官方参考

查看脚本参数（不调用模型或 LangSmith）：

```powershell
.\.venv\Scripts\python.exe -m langsmith_tools.evaluate_rag --help
```

真实实验和 Studio 需要可用的网络、凭据与索引。当前宿主机在导入 `asyncio` 时报告 `WinError 10106`，真实启动与云端联调需在该环境问题解除后验证。

适配层测试（不调用外部服务）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s langsmith_tools/tests -v
```

初次接入时，依赖同步因 `WinError 10106` 无法连接 PyPI，未完成 CLI 安装与锁文件更新。2026-09-06 后续排查时，本地已存在 CLI 和 API 依赖；已根据安装的 CLI 源码修正 `dev` 模式的路径配置。助手执行环境仍无法导入 `asyncio`，与用户终端能进入应用启动阶段的情况不同，不能把该环境错误直接认定为用户本次启动失败原因。

本轮 Python 编译与参数帮助检查通过；3 项适配层测试中，缺失答案校验通过，另外 2 项在导入原项目依赖时被上述环境错误阻断，未完成运行验收。

- [官方追踪接入](https://docs.langchain.com/langsmith/trace-with-langgraph)
- [官方 evaluate 用法](https://docs.langchain.com/langsmith/evaluate-llm-application)
- [官方 Studio 接入](https://docs.langchain.com/oss/python/langgraph/studio)
- [官方 CLI 参数](https://docs.langchain.com/langsmith/cli)
