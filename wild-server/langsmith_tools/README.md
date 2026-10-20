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

模型和 Embedding 使用原 `CHAT__*`、`EMBEDDING__*` 配置。`CHAT__PROVIDER=auto` 沿用按地址识别，也可显式选择 `openai/dashscope/deepseek/moonshot/mimo/custom`；Studio 与原页面共用 `app/llm/factory.py`。MiMo 支持思考开关，`CHAT__THINKING_BUDGET` 不会被当作其独立思考预算发送。进程环境变量优先于 `.env`。若设置过 `UV_PROJECT_ENVIRONMENT`，需确保它指向项目现有 `.venv`。

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
  "query": "窗组件需要哪些宿主与局部坐标字段",
  "metadataFilter": {"doc_type": "component", "entity_type": "window"}
}
```

参考输出 outputs：

```json
{
  "expectedSources": ["components/windows-supported.md"]
}
```

可从现有 [rag_retrieval_cases.json](../evals/rag_retrieval_cases_langsmith.csv) 取样：将 `query`、`metadataFilter` 放进 inputs，将 `expectedSources` 放进参考 outputs。脚本读取已有云端数据集，不自动新建或重复上传样例。

运行：

```powershell
uv run python -m langsmith_tools.evaluate_rag --dataset wildagent-rag
uv run python -m langsmith_tools.evaluate_rag --dataset wildagent-rag --top-k 6 --experiment-prefix rag-routing-v3
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

## 4. Studio：architecture 调试图实验记录（已回退）

> 2026-10-20：下述专用调试图已回退。当前 [studio_graph.py](studio_graph.py) 恢复导出 `build_generation_graph(enable_callback=True)`，使用原完整项目图，不再在 architecture 后设置本轮静态断点。下文保留作历史记录，见[代码回退记录](../../docs/10月20日优化/10-代码回退记录.md)。

当前入口 [studio_graph.py](studio_graph.py) 是专门的设计调试图，直接复用现有 classifier 和 architecture 节点：

```text
START → classifier → architecture → END
                         ↑
                  执行完成后的静态断点
```

非建筑生成请求会在 classifier 后结束。这个入口只加载前两个业务节点，避免因后续旧节点仍引用已删除 design 模块而在启动时失败；业务完整图 app/agent/graph.py 本轮没有修改。

断点配置在图编译处：

```python
graph = builder.compile(interrupt_after=["architecture"])
```

这是节点执行完成后的断点，图纸和派生数据已经写回 State。检查点由 Agent Server 管理，不手工创建正式任务 SQLite checkpointer。调试图在 architecture 后收尾，继续执行也不会进入材质、计划或编译节点。

从 wild-server 目录启动：

```powershell
uv run langgraph dev --config langsmith_tools/langgraph.json
```

打开终端给出的 Studio 链接，选择 wildagent 图，新建一个线程，使用 [studio-input.example.json](studio-input.example.json)。修改 user_message 和 detail_level 来比较需求及粒度。不要复用旧协议生成过图纸的线程。

输入中的 request_id/session_id 只是业务关联信息；Studio 的线程由 Studio 管理。

点开 architecture 的输出或 State，重点看：

| 字段 | 看什么 |
| --- | --- |
| design_document | 通过本轮字段和参数校验的图纸；布局、房间、门窗、楼梯设计是否符合需求 |
| resolved_design | 程序计算的高差、级数、步高、平台标高、梯井、楼板分片和坐标 |
| architecture_diag.rounds | 每轮原始回复 output、工具提交 tool_calls、结构化 inspection、错误 issue、调用 ID 和用量 |
| architecture_diag.tool_schemas | calculate_stair / inspect_design / revise_design 的实际参数 Schema |
| architecture_diag.last_candidate | 最近一次完整候选，包括失败稿 |
| error | 未通过时的终止原因 |

第一轮可能先调用 calculate_stair。寻找 inspect_design 的 args.design 查看首次完整提交；revise_design 的 args.changes 是局部修改，rounds[i].candidate 是程序装配后的完整候选。last_inspection 包含 defaults / derived / focus 以及 coverage，详见 [当前交接说明](../../docs/10月20日优化/09-architecture检查工具与修订.md)。

本入口没有 plan_mode 或人工审核分支。此前 README 中有关 plan_review/design_review 的启动与恢复说明已不适用于当前调试图。

若现有开发服务器出现同步 I/O 的 BlockingError，才按具体堆栈考虑原来的 --allow-blocking 参数；它不能修复导入或配置错误。

当前协议为 design-facts/2，边界具名、楼梯占地由程序计算，需新建线程。经用户授权，已开展设计节点离线回归与真实模型测试，见 [证据记录](../../docs/10月20日优化/architecture最后修复/README.md)。测试没有覆盖浏览器断点操作及后续旧链路。

官方行为依据：[LangGraph 静态断点与 Studio](https://docs.langchain.com/oss/python/langgraph/interrupts#debugging-with-interrupts)。


## 5. 历史验证与官方参考

以下是此前接入时的历史记录。当前 architecture 修复的验证结果以上一节链接的证据为准。

查看脚本参数（不调用模型或 LangSmith）：

```powershell
.\.venv\Scripts\python.exe -m langsmith_tools.evaluate_rag --help
```

真实实验和 Studio 需要可用的网络、凭据与索引。当前宿主机在导入 `asyncio` 时报告 `WinError 10106`，真实启动与云端联调需在该环境问题解除后验证。

初次接入时，依赖同步因 `WinError 10106` 无法连接 PyPI，未完成 CLI 安装与锁文件更新。2026-09-06 后续排查时，本地已存在 CLI 和 API 依赖；已根据安装的 CLI 源码修正 `dev` 模式的路径配置。助手执行环境仍无法导入 `asyncio`，与用户终端能进入应用启动阶段的情况不同，不能把该环境错误直接认定为用户本次启动失败原因。

本轮 Python 编译与参数帮助检查通过；3 项适配层测试中，缺失答案校验通过，另外 2 项在导入原项目依赖时被上述环境错误阻断，未完成运行验收。

- [官方追踪接入](https://docs.langchain.com/langsmith/trace-with-langgraph)
- [官方 evaluate 用法](https://docs.langchain.com/langsmith/evaluate-llm-application)
- [官方 Studio 接入](https://docs.langchain.com/oss/python/langgraph/studio)
- [官方 CLI 参数](https://docs.langchain.com/langsmith/cli)
