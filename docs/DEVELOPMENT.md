# 开发与测试

最后核对：2026-10-13。命令默认从仓库根目录 `E:\AgentProject\WildAgent` 执行，使用 Windows PowerShell。

代码位置见 [项目索引](项目索引.md)，测试细节见 [测试文件使用指南](TESTING.md)，部署见 [服务器部署与运维](DEPLOYMENT.md)。

## 1. 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.12+ | 见 `wild-server/.python-version` |
| [uv](https://docs.astral.sh/uv/) | 任意近期版本 | 生产 Jenkins 固定 `0.11.14` |
| Node.js 与 npm | 满足 `wild-web/package.json` | Vite 8 + Vue 3.5 |

另需一个 OpenAI-compatible Chat 模型；使用语义检索时还需单独配置 Embedding 模型（两者不能共用同一套凭据）。

不要提交 `.env`、API Key、服务端私钥或生产数据库凭据。

### 未上线阶段的版本约定

软件包固定 `0.1.0`；WILD、图纸、校验及内部协议固定首版，Shader 和渲染报告使用各自首版标记。普通修复或优化不递增版本，只有用户明确要求发布或版本迁移时才调整。保留当前字段与功能，旧标记只作为输入兼容处理，不再按版本改写设计内容。

场景/图纸的 `revision` 记录实际编辑次数，用于撤销、补丁冲突和审核，不属于发布版本。第三方依赖、LangGraph 事件 API 的版本参数和已有向量签名算法保持各自契约。缓存及验证依据实际内容与现有指纹；开发代码变更后重启相应服务或刷新页面，截图比较继续使用源码和配置摘要。

## 2. 仓库结构

| 目录 | 作用 | 是否需要独立启动 |
|---|---|---|
| `wild-server/` | FastAPI 后端：REST/WebSocket、LangGraph 编排、RAG、Blueprint 校验 | 是 |
| `wild-web/` | Vue 编辑器：Three.js 实时预览、Agent 对话 | 是 |
| `wild-core/` | 确定性几何引擎，被前端以 `file:../wild-core` 引用 | 否 |
| `docs/` | 与当前代码一致的正式文档 | — |
| `docs-dev/` | 开发过程记录与历史归档，已在 `.gitignore` 中，**不进入版本库** | — |

## 3. 后端配置

配置统一读取 `wild-server/.env`，路径由 `app/utils/runtime_env.py` 按 `wild-server` 目录解析，**与启动时的当前目录无关**。先复制模板：

```powershell
Copy-Item wild-server/.env.example wild-server/.env
```

必填项：

```dotenv
CHAT__NAME=你的模型 ID
CHAT__API_KEY=你的密钥
CHAT__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

EMBEDDING__NAME=text-embedding-v4
EMBEDDING__API_KEY=你的密钥
EMBEDDING__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

嵌套配置用双下划线映射：`CHAT__API_KEY` 对应 `Settings.chat.api_key`。完整可选项以 `wild-server/config.py` 为准：

| 配置段 | 默认值 | 说明 |
|---|---|---|
| `CHAT__*` | `provider=auto`、`timeout=300`、`max_retries=2` | `auto` 按地址识别，也可显式选 `openai/dashscope/deepseek/moonshot/mimo/custom` |
| `CHAT__THINKING_BUDGET` | `4096` | 支持预算的模型用 Token 上限，其他已知模型映射为推理档位；`0` 表示用供应商默认值 |
| `EMBEDDING__*` | `timeout=60`、`max_retries=1` | 单批向量请求超时，指数退避重试 |
| `RAG__*` | `chunk_size=900`、`chunk_overlap=150`、`top_k=6`、`max_context_chars=18000` | `RAG__AUTO_SYNC=true` 时服务启动后在后台线程增量同步索引，不阻塞启动 |
| `RAG__RETRIEVAL_GATE__*` | `mode=observe` | `observe` 只记结论，`enforce` 才影响运行时；阈值需用当 embedding 的正负样本校准 |
| `RAG__TRACE__*` | 开启 | RAGTrace 落盘路径，供排障 |
| `WEB_RESEARCH__*` | `enabled=false`、`provider=tavily` | 缺少形态资料时的网络检索；需额外 `WEB_RESEARCH__API_KEY` |
| `ASSETS__*` | `backend=local`、`root_dir=storage/assets`、`public_base_url=/api/assets` | PBR 资产存储；单文件 20MB、总量 80MB 上限 |
| `PRESENCE__*` | `enabled=true` | 在线人数、IP 脱敏与可信代理头 |
| `WILD_SCENES_DIR` | `storage/scenes` | 蓝图存储目录，容器部署时挂载到 `/app/storage/scenes` |

三个仅供部署层使用的环境变量，不写进 `.env`：

| 变量 | 用途 |
|---|---|
| `WILD_RUNTIME_ENV_FILE` | 指定运行时 `.env` 的绝对路径（Docker 等部署层） |
| `WILD_RUNTIME_ENV_PERSISTENT` | 声明该路径已映射到持久化存储 |
| `WILD_RUNTIME_ENV_HOST_PATH` | 声明宿主机路径，仅用于向管理员解释保存位置 |

前端顶部「配置」保存 Chat 模型时，会写入同一个 `.env` 并热重载模型客户端，无需重启进程。手工改文件不会通知运行中的进程，仍需重启或通过界面保存。

`RAG__ALLOW_HASH_FALLBACK=true` 只适合无 Embedding API 时的本地冒烟，**不代表生产语义检索质量**。

## 4. 本地启动

### 4.1 后端

```powershell
cd wild-server
uv sync --dev
```

`uv run` 需在 `wild-server` 目录执行，以便读取该目录的 `pyproject.toml` 与 `uv.lock`。以下写法等价，任选其一：

```powershell
# FastAPI 官方 CLI：读取 [tool.fastapi] entrypoint = "main:app"，
# 自动发现 main.py，默认监听 127.0.0.1:8000 且已开启热重载
uv run fastapi dev

# 显式指定入口与监听参数
uv run fastapi dev main.py --reload
uv run fastapi dev main.py --reload --host 127.0.0.1 --port 8000

# 生产式启动：关闭热重载
uv run fastapi run main:app --host 0.0.0.0 --port 8000

# 直接使用 uvicorn
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 绕过 uv，直接调用虚拟环境中的 CLI
.\.venv\Scripts\fastapi.exe dev
```

`fastapi dev` 默认就是 reload 并绑定 `127.0.0.1`，等价于 `fastapi run` 加自动重载。`--reload` 资源开销大，正式环境用 `fastapi run`。需要排查应用如何被发现与导入时加 `-v`。

就绪检查：`/health/ready`；会话列表：`/api/sessions`；Agent 通道：`/ws/agent`。

### 4.2 前端

```powershell
cd wild-web
npm install
npm run dev
```

开发服务器默认监听 `5173`，`vite.config.ts` 已把 `/api` 与 `/ws` 代理到 `http://127.0.0.1:8000`，因此需先启动后端。`wild-core` 通过 `file:../wild-core` 链接进 `node_modules`，改动引擎源码后由 Vite 热更新生效，无需重新安装。

### 4.3 LangSmith Studio

调试 LangGraph 用，需 `dev` 组依赖（上面的 `uv sync --dev` 已安装），并在 `wild-server/.env` 中补充：

```dotenv
LANGSMITH_API_KEY=你的密钥
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=wildagent
```

```powershell
cd wild-server
uv run langgraph dev --config langsmith_tools/langgraph.json
```

CLI 按**命令执行目录**解析依赖、图文件和环境文件，所以必须在 `wild-server` 执行。配置放在子目录，必须用 `--config` 指定。若确实出现同步 I/O 的 `BlockingError`，可临时加 `--allow-blocking`（只关闭报错，不修复阻塞）。

详见 [`wild-server/langsmith_tools/README.md`](../wild-server/langsmith_tools/README.md)。

## 5. 变更验证

最低门禁：

```powershell
# 后端
cd wild-server
uv run --with pytest python -m pytest tests -q

# 前端
cd wild-web
npm run build
npm run check:core
npm run check:compiler
npm run check:rendering
```

按变更类型的额外要求见 [测试文件使用指南 · 变更类型与最低测试](TESTING.md#7-变更类型与最低测试)。

### 5.1 Agent 与协议变更必须覆盖

- 真实编译图的 `GENERATE` / `EDIT` / `CHAT` 路由；
- ScenePatch 拒绝直接应用；
- 修正后复检覆盖初检，最终错误阻止保存；
- WebSocket `protocol_version`、结构化 `agent_step` 和断连恢复；
- Turn 去重、服务重启中断恢复、迟到事件不覆盖已切换的画布；
- 流式模型把最终 JSON 放入 `reasoning_content`、不用 Markdown 代码围栏时仍能提取 Blueprint；
- ScenePatch 提取不被 Blueprint 结构筛选影响。

### 5.2 节点标签变更必须同批改四处

`app/api/ws_agent.py` 的 `_NODE_LABELS`、`wild-web/src/stores/agentStore.ts` 的兜底 `_NODE_LABELS`、`tests/api/test_ws_step_labels.py`，以及本仓库的 [项目索引 · 节点表](项目索引.md#32-节点全集与路由)。

### 5.3 知识库修改

先跑 `scripts/rag/inspect_knowledge_chunks.py` 人工看一次实际分片，再跑 `tests/rag/` 与 `eval_retrieval.py`。

## 6. 常见排查顺序

1. `/api/sessions` 与 `/api/scenes` 是否可访问。
2. 浏览器 WebSocket 是否连到 `/ws/agent`，是否收到 `pong`。
3. `.env` 是否被正确读取（路径与启动目录无关，看启动日志中的配置摘要）。
4. Agent 返回的是聊天、Patch 还是 Blueprint；不要只看最终 UI。
5. Blueprint 是否通过最终校验，文件是否实际写入 `storage/scenes`。
6. 前端是否因用户切换会话而阻止迟到结果覆盖画布。
7. 场景 404 时先检查该会话是否真的拥有 `filename`；draft 会话没有 `.wild` 属正常状态，前端不应发起场景请求。

具体错误：

| 现象 | 原因与处理 |
|---|---|
| `'ChatCompletion' object has no attribute 'get'` | 模型 SDK 响应适配层版本不兼容，不代表 Chroma 或知识文档损坏。`app/llm/model_client.py` 必须先把 Pydantic 响应经 `model_dump()` 转成映射；用 `.venv\Scripts\python.exe -B scripts\rag\smoke_test.py` 可独立验证不调用远程模型的检索链路 |
| 精密模式报「最终 Blueprint 缺失」 | 先看骨架节点的具体错误。提取层支持从普通内容、`reasoning_content` 和常见 `blueprint`/`result`/`data` 包装对象提取；首次失败会自动执行一次非思考格式恢复。日志中的 `finish_reason`、`meta_marker`、`geometry_marker`、`recovery` 用于区分截断、漏输出和 JSON 格式错误 |
| 模型漏掉 `meta.version` / `meta.type` / `meta.name` | 归一化层会补齐固定默认值，不属于文件系统问题。界面若把 `meta.name` 显示成链接，是 Markdown 自动识别了 `.name` 域名，错误字段名要用反引号 |
| 节点标签前端不更新 | 后端与前端各有一份标签表，必须同批改，并跑 `tests/api/test_ws_step_labels.py` |
| 改 `wild-core` 后前端无变化 | 确认 `wild-core/node_modules` 已 `npm install`，且 Vite 的 `fs.allow` 放行了上一级目录 |

## 7. Docker 本地部署

仓库根目录的 `docker-compose.yml` 定义 `server`（映射 `8000:8000`，挂载 `storage` 与 `.env`）和 `web`（映射 `80:80`，由 nginx 反向代理到 `wild-server:8000`）。

```powershell
docker compose up -d --build
docker compose logs -f server
```

生产部署由 Jenkins 执行，不要用 Compose 代替，详见 [服务器部署与运维](DEPLOYMENT.md)。
