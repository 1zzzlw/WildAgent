# 测试文件使用指南

最后核对：2026-10-13。本文覆盖仓库内当前可见的自动化测试、评测脚本、分片检查工具、图展示工具和人工模型冒烟入口。命令默认使用 Windows PowerShell；路径从仓库根目录 `E:\AgentProject\WildAgent` 开始。

代码位置索引见 [项目索引](项目索引.md)，架构见 [架构说明](ARCHITECTURE.md)。

## 1. 测试分层

| 层级 | 适合作为门禁 | 需要模型或外网 | 用途 |
|---|---:|---:|---|
| `wild-server/tests/**/test_*.py` | 是 | 否 | 后端确定性单元与集成回归（16 个子目录、148 个文件） |
| `wild-web/scripts/check-*.mjs` | 是 | 否 | 前端核心、编译器、渲染与状态集成回归 |
| `wild-web` 生产构建 | 是 | 否 | TypeScript、Vue 和 Vite 构建检查 |
| `scripts/rag/eval_retrieval.py --embedding hash` | 知识库变更的本地冒烟 | 否 | 固定题集验证 RAG 分片、过滤与评测流程 |
| `scripts/rag/inspect_*.py` | 否 | 否 | 人工观察分片结果，不做断言 |
| `tests/misc/show_langgraph_graph.py` | 结构变更时使用 | HTML 渲染需要 CDN | 校验并展示实际编译的 LangGraph |

前端以 `build`、`check:core`、`check:compiler`、`check:rendering` 四条命令共同作为最低门禁。

**不要在文档中长期写死 passed 数量**：新增或删除测试后数量会变化，应以当次命令的退出码和报告为准。

## 2. 日常完整回归

后端依赖由 uv 管理，`pytest` 通过 `--with` 临时提供，不会写入生产依赖：

```powershell
cd wild-server
uv sync
uv run --with pytest python -m pytest tests -q
```

前端：

```powershell
cd wild-web
npm install
npm run build
npm run check:core
npm run check:compiler
npm run check:rendering
```

单文件或单用例：

```powershell
cd wild-server
uv run --with pytest python -m pytest tests/network/test_generation_job_service.py -q
uv run --with pytest python -m pytest tests/network/test_generation_job_service.py::GenerationJobServiceTest::test_restart_recovers_running_job_and_replays_events -q
```

常用调试选项：

| 选项 | 作用 |
|---|---|
| `-x` | 停在第一个失败 |
| `--lf` | 只重跑上次失败的用例 |
| `-s` | 关闭输出捕获，直接看 `print` |
| `--tb=long` | 完整堆栈 |
| `-vv` | 逐用例详细输出 |

这些测试使用 mock、临时目录或本地确定性实现，**不要求 `.env` 中存在有效模型 Key**。Chroma 可能输出一条第三方弃用警告；只要 pytest 退出码为 0，就不影响通过。

## 3. 测试目录与分包说明

每个子包有自己的 `README.md`，写明该包内每个文件的作用与单文件命令。**查某个测试文件做什么，先看它所在目录的 README。**

| 目录 | 文件数 | 有独立 README | 职责 |
|---|---:|---:|---|
| [`tests/agent/`](../wild-server/tests/agent/) | 29 | 是 | 图拓扑、三类意图真实编译图、节点边界守卫、交付门禁、模型错误 |
| [`tests/plan/`](../wild-server/tests/plan/) | 19 | 否 | plan 契约、对账、策略、replan、工具；图纸实现的专项回归 |
| [`tests/design/`](../wild-server/tests/design/) | 21 | 否 | 设计文档契约、审核、修订、履约、材质区域、逐体量屋顶 |
| [`tests/rag/`](../wild-server/tests/rag/) | 14 | 是 | 索引同步、缓存、语义分片、rerank、检索评测、trace |
| [`tests/validators/`](../wild-server/tests/validators/) | 12 | 是 | 空间校验器专项：共墙、屋顶覆盖、贯通构件、楼梯洞口 |
| [`tests/components/`](../wild-server/tests/components/) | 10 | 是 | 组件蓝图、校验复检、法线朝向、立面配方、材质计划 |
| [`tests/misc/`](../wild-server/tests/misc/) | 9 | 是 | 推理流、Patch 生成、checkpoint 恢复、部署预检、就绪检查 |
| [`tests/compiler/`](../wild-server/tests/compiler/) | 7 | 否 | 设计编译、组件实例、电梯推导、管线缺陷 |
| [`tests/network/`](../wild-server/tests/network/) | 6 | 是 | WS/HTTP 传输层：提交、停止、断连、运行时 env、会话轮次 |
| [`tests/repair/`](../wild-server/tests/repair/) | 5 | 是 | 回调修复闭环、白名单工具、合并精度、骨架恢复 |
| [`tests/assets/`](../wild-server/tests/assets/) | 4 | 是 | 模型工厂与客户端兼容、PBR 资产、材质调参 |
| [`tests/blueprint/`](../wild-server/tests/blueprint/) | 4 | 是 | 解析、归一化、材质校验、分片路由 |
| [`tests/api/`](../wild-server/tests/api/) | 3 | 否 | 节点标签表契约、配置接口、架构步状态 |
| [`tests/vision/`](../wild-server/tests/vision/) | 3 | 否 | 离线视觉评价、修订、基准 |
| [`tests/generation/`](../wild-server/tests/generation/) | 2 | 否 | 能力查询面、材质与设计分离 |

`tests/artifacts/`、`tests/fixtures/`、`tests/langsmith/` 只有样本数据，没有测试文件。

### 3.1 必须长期关注的守卫测试

| 文件 | 守住什么 |
|---|---|
| `tests/agent/test_agent_module_boundaries.py` | agent 根目录只允许 4 个 `.py`；`nodes/` 之间不得互相 import；节点入口文件 ≤ 100 行；领域包不得反向 import |
| `tests/agent/test_agent_graph_execution.py` | `GENERATE` / `EDIT` / `CHAT` 三条分支走真实编译图；已下线节点名不得复活 |
| `tests/agent/test_plan_progress_channel.py` | `:progress` 通道边界，防止执行说明与模型 reasoning 混淆 |
| `tests/api/test_ws_step_labels.py` | 前后端节点标签表必须同批修改 |
| `tests/plan/test_plan_chain_e2e.py` | plan 全链路 |
| `tests/validators/test_validation_cache.py` | 最终校验可复用时不重复执行 |
| `tests/components/test_component_validation_recheck.py` | 修复后必须复检，复检失败不能伪报成功 |
| `tests/repair/test_targeted_repair_tools.py` | 修复动作白名单、ID/类型保护、错误必须严格下降 |

## 4. LangGraph 图展示与结构检查

文件：[`tests/misc/show_langgraph_graph.py`](../wild-server/tests/misc/show_langgraph_graph.py)。

```powershell
cd wild-server
.venv\Scripts\python.exe -B tests\misc\show_langgraph_graph.py
```

只生成 Mermaid 和 HTML、不启服务，适合 CI：

```powershell
.venv\Scripts\python.exe -B tests\misc\show_langgraph_graph.py --no-serve
```

常用参数：`--no-callback` 隐藏校验失败后的 callback 回路；`--port 8765` 指定展示端口；`--output-dir <目录>` 指定输出目录（默认系统临时目录）。

HTML 用 Mermaid CDN 渲染，浏览器离线时仍可查看生成的 `.mmd` 源码，但图形页面可能无法渲染。

## 5. RAG 专项工具

全部脚本在 `wild-server/scripts/rag/`，详细说明见该目录下的 README。

### 5.1 检索评测

[`scripts/rag/eval_retrieval.py`](../wild-server/scripts/rag/eval_retrieval.py)：

```powershell
cd wild-server
.venv\Scripts\python.exe -B scripts\rag\eval_retrieval.py --embedding hash
```

使用统一评测集、临时 Chroma 集合和本地 HashEmbeddingFunction，检查真实分片、metadata 过滤与评测流程；不需要 API Key，也不修改 `storage/chroma`。Hash 模式**不代表真实语义召回质量**；评估真实召回率按 [eval_retrieval 说明](../wild-server/scripts/rag/README_EVAL_RETRIEVAL.md) 使用真实 embedding 临时索引。

### 5.2 分片检查（人工观察，无断言）

改分片策略或知识库文档后，先用这两个脚本**看一眼实际分片**，再跑测试：

```powershell
cd wild-server
$env:PYTHONPATH = "."
uv run --no-project python scripts\rag\inspect_knowledge_chunks.py storage\knowledge_base --table
uv run --no-project python scripts\rag\inspect_chunks_demo.py storage\knowledge_base\knowledge\protocol\blueprint-skeleton.md
```

`inspect_knowledge_chunks.py` 参数：`--namespace`、`--chunk-size`（900）、`--chunk-overlap`（150）、`--table`（表格输出）、`--show-content`、`--limit N`、`--no-summary`、`--output <file>`、`--log-output <file>`、`--no-log-output`。

`inspect_chunks_demo.py` 参数：`--chunk-size`（900）、`--chunk-overlap`（150）、`--show-full`、`--limit N`、`--output <file>`、`--log-output <file>`、`--no-log-output`。

两者都会把控制台输出双写到 `scripts/reports/`，并生成 Markdown 报告；用 `--no-log-output` 可关闭日志保存。

### 5.3 其余 RAG 脚本

| 脚本 | 用途 |
|---|---|
| `check_sync_status.py` | 查看 Chroma 索引同步进度 |
| `resync_knowledge_index.py` | 强制重建索引 |
| `calibrate_retrieval_gate.py` | 用正负样本校准检索门控阈值 |
| `check_rag_quality_gate.py` | 检索质量门禁检查 |
| `judge_rag_answer.py` | 回答质量评判 |
| `lint_wild_rag_docs.py` | 知识文档格式检查 |
| `summarize_rag_traces.py` | 汇总 RAGTrace |
| `migrate_embedding_index.py` | 换 Embedding 模型后迁移索引 |
| `smoke_test.py` | 不调用远程模型的检索链路冒烟 |

## 6. 前端自动检查逐文件说明

### `check-wild-core.mjs`

```powershell
cd wild-web
npm run check:core
```

临时编译并加载 Wild Core，重建 `lantu/*.wild` 全部样本；检查 mesh、索引、法线、UV、包围盒、版本迁移、primitive box、斜梁方向、侧墙开口、直角墙角、程序化红砖参数透传和非法材质回退。临时构建目录结束时删除。

### `check-component-compiler.mjs`

```powershell
npm run check:compiler
```

临时编译组件编译器和前端集成模块，覆盖组件能力、几何评测样本、门窗深度、可交互窗扇与灯具、坡道/檐口/曲墙、缓存、Schema 拒绝、渲染、ScenePatch、材质优化、PBR、撤销历史、Worker 传输、拖拽、Presence 和显式保存。

### `check-rendering-pipeline.mjs`

```powershell
npm run check:rendering
```

通过 Vite 加载真实渲染模块，验证历史构件兼容模式默认 DoubleSide、已验证封闭实体可显式使用 FrontSide、玻璃使用 `MeshPhysicalMaterial` 及受控 transmission/IOR/thickness、AO 所需 UV，以及程序化红砖 Shader 注入、uniform、材质签名和 Program cache key。

### 生产构建检查

`npm run build` 不对应单一测试文件，但必须与上面三条一起运行。它执行 `vue-tsc -b` 和 Vite 生产构建，用于发现类型错误、模块引用错误和打包失败。

### 其他前端脚本

`wild-web/scripts/` 下还有 `analyze-batch.mjs`、`check-agent-detail.mjs`、`check-agent-stop.mjs`、`render-baseline.mjs`、`validate-generated.mjs`，属于人工分析与批处理工具，不在门禁内。

## 7. 变更类型与最低测试

| 变更范围 | 最低测试 |
|---|---|
| LangGraph 节点、路由、State | 后端完整回归 + `show_langgraph_graph.py --no-serve` |
| 模块边界或目录拆分 | `tests/agent/test_agent_module_boundaries.py` + 后端完整回归 |
| 节点标签 | `tests/api/test_ws_step_labels.py`（前后端标签表同批改） |
| plan 层（策略、对账、replan、工具） | `tests/plan/` 整包 + `test_plan_chain_e2e.py` |
| checkpointer、WebSocket、断线恢复 | `tests/network/test_generation_job_service.py`、`tests/misc/test_langgraph_checkpoint_resume.py`、`tests/network/test_ws_agent_disconnect.py` |
| Blueprint Schema、空间与校验 | `tests/blueprint/`、`tests/validators/`、`tests/repair/test_merge_precision.py`、`npm run check:core` |
| 组件或渲染 | `tests/components/` + `npm run check:compiler` + `check:core` + `check:rendering` |
| RAG 文档、分片、metadata | `tests/rag/` 整包 + `eval_retrieval.py`，并人工看一次分片 |
| 前端 Agent 协议或状态 | `tests/network/` + `npm run build` + `npm run check:compiler` |
| 部署就绪与模型响应兼容 | `tests/misc/test_deployment_preflight.py`、`tests/misc/test_readiness.py`、`tests/assets/test_model_client_compat.py` |

## 8. 需要真实模型的人工验证

自动化套件不覆盖真实模型调用。需要真实模型时：

- 从前端发起**精密模式**，与生产使用同一 runtime callback、checkpointer 和事件协议；
- 或用 LangSmith Studio 运行 `wildagent` 图，见 [`wild-server/langsmith_tools/README.md`](../wild-server/langsmith_tools/README.md)。

这类验证会产生模型费用，且异常未必返回非零退出码，**不能作为 CI 门禁**。

## 9. 编写新测试

约定与现有代码一致：

- 文件名 `test_<feature>.py`，类名 `<Feature>Test`，方法名 `test_<具体行为>`；
- 用 `unittest.TestCase` 风格（见 `tests/assets/test_material_tuning.py`）；
- 一个测试只验证一个行为；用 mock 隔离外部依赖；覆盖边界与错误分支；
- 不依赖执行顺序。

新增测试后，把该文件登记到所在目录的 `README.md`，并按需更新本文件第 3 节的职责描述。

## 10. Checkpointer 部署说明

LangGraph SQLite 文件由服务首次启动自动创建在：

```text
wild-server/storage/sessions/langgraph_checkpoints.sqlite3
```

无需新增环境变量或部署参数。生产 Jenkins 已创建并挂载 `/app/storage/sessions`，本地 Compose 也持久化 `storage`，因此正常进程重启和使用同一数据卷的容器重建都能读取 checkpoint。备份与迁移时应把该 SQLite 文件和对应的 `-wal`、`-shm` 文件视为同一组数据；丢失持久卷后无法恢复未完成任务。

部署与生产运维见 [服务器部署与运维](DEPLOYMENT.md)。