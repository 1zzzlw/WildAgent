# 开发与测试

最后核对：2026-08-09。命令默认从仓库根目录 `E:\AgentProject\WildAgent` 执行。

## 1. 环境要求

- Node.js 与 npm；前端依赖版本见 `wild-web/package.json`。
- Python 3.12+ 与 uv；后端依赖见 `wild-server/pyproject.toml`。
- 一个 OpenAI-compatible Chat 模型；需要远程向量时再配置 embedding 模型。

不要提交 `.env`、API Key、服务端私钥或生产数据库凭据。

## 2. 后端配置

在 `wild-server/.env` 中使用双下划线映射嵌套设置：

```dotenv
CHAT__NAME=qwen-plus
CHAT__API_KEY=replace-me
CHAT__BASE_URL=https://example.com/v1

EMBEDDING__NAME=
EMBEDDING__API_KEY=
EMBEDDING__BASE_URL=

RAG__ENABLED=true
RAG__PERSIST_DIR=storage/chroma
RAG__COLLECTION_NAME=wild_knowledge_base
RAG__CHUNK_SIZE=900
RAG__CHUNK_OVERLAP=150
RAG__TOP_K=6
RAG__MAX_CONTEXT_CHARS=18000
RAG__ALLOW_HASH_FALLBACK=true
```

空 embedding 配置且允许 hash fallback 时只适合本地冒烟验证，不代表生产语义检索质量。

## 3. 本地启动

后端：

```powershell
cd wild-server
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
cd wild-web
npm install
npm run dev
```

前端默认通过当前站点的 `/ws/agent` 和 `/api/*` 访问后端；生产环境由 `wild-web/nginx.conf` 反向代理。

## 4. 变更验证

全部测试文件的逐项作用、单文件命令、LangGraph 图展示、RAG 评测和历史脚本状态见
[测试文件使用指南](TESTING.md)。

前端最低检查：

```powershell
cd wild-web
npm run build
npm run check:core
npm run check:compiler
```

后端：

```powershell
cd wild-server
uv run --with pytest python -m pytest tests -q
```

仓库根下的 `wild-server/test_*.py` 是需要真实模型或手工观察输出的旧集成脚本，不属于上述自动化测试集；不要用无路径的 `pytest` 把它们误当成普通单元测试收集。

Agent/协议相关变更至少覆盖：

- 真实编译图的 `GENERATE / EDIT / CHAT` 路由；
- ScenePatch 拒绝直接应用；
- 修正后复检覆盖初检、最终错误阻止保存；
- WebSocket `protocol_version`、结构化 `agent_step` 和断连；
- Turn 去重、服务重启中断恢复及迟到事件会话隔离。
- 流式模型把最终 JSON 放入 `reasoning_content`、不使用 Markdown 代码围栏时仍可提取 Blueprint；ScenePatch 提取不能被 Blueprint 结构筛选影响。

门窗/合并相关变更还必须覆盖：

- 骨架墙体 `from[1] == to[1]` 时，在派发组件前按楼板标高补齐墙高；
- 只有 `geometry.components`、没有 `opening` element 时仍执行墙体范围校验；
- 背墙或侧墙把世界 X/Z 误写进 `from[2]` 时，能投影回父墙局部坐标；
- 同一父墙上的门窗二维开口重叠会被阻断；
- 设计清单要求的最小组件数和立面最大开口数会在合并阶段复核；
- 未定义材质引用会在交付前报错。
- 同一实体的多条校验错误会被分别结构化并聚合到同一失败组件；不能只保留第一条。
- 模型修复只能调用白名单动作，不能修改非失败实体、`id/type`、不存在的父墙或材质。
- callback 候选只有在错误数严格下降且没有引入新错误时才提交；否则应保持原分片不变并记录回滚审计。
- 设计配额缺少门窗等组件时会产生 `design:<type>` 修复目标；`add_entity` 只能新增该类型，且新增结果仍须通过必填字段、父对象、几何和配额复检。
- 回调模型把工具动作放入 `reasoning_content` 或在前面输出其他规划数组时，解析器仍应选择最后一个合法动作数组。

固定回归样本：`wild-server/storage/scenes/2026-08-08/session_1786189311071_现代别墅.wild`。测试时使用副本运行修复，不能覆盖原始问题样本；重点断言 `door_back_service.from` 从 `[3.4, 0, 6]` 修正为 `[3.4, 0, 0]`。

前端流式对话人工验收：停留底部时连续 `thinking_delta` 应逐帧跟随；向上滚动后位置保持稳定并出现“回到最新”；执行说明区域自身不得出现第二层纵向滚动条；主动发送或切换会话后恢复到底部。

知识库修改应额外预览实际 RAG 分片并验证索引同步。

## 5. Docker 本地部署

仓库根目录的 `docker-compose.yml` 定义：

- `server`：构建 `wild-server`，映射 `8000:8000`，挂载 `wild-server/storage`。
- `web`：构建 `wild-web`，映射 `80:80`，依赖后端。

```powershell
docker compose up -d --build
docker compose logs -f server
```

服务器的环境文件位置、旧版手工容器兼容方式和上线核对步骤统一见
[服务器部署与运维](DEPLOYMENT.md)。不要把 `docs-dev` 中的归档手册作为当前部署依据。

生产部署前确认：

- `wild-server/.env` 已在服务器单独配置且不进入镜像或 Git。
- `wild-server/storage` 有持久卷和备份策略。
- 反向代理允许 WebSocket Upgrade，并限制请求体、超时和跨域来源。
- HTTPS 下使用 `wss://`；不要把开发用宽松 CORS 直接暴露到公网。
- 删除会话会永久删除对应文件，生产环境需要快照或回收站策略。

## 6. 常见排查顺序

1. `/api/sessions` 与 `/api/scenes` 是否可访问。
2. 浏览器 WebSocket 是否连接到 `/ws/agent`，是否正常收到 `pong`。
3. 后端 `.env` 是否在 `wild-server` 工作目录被读取。
4. Agent 返回的是聊天、Patch 还是 Blueprint；不要只看最终 UI。
5. Blueprint 是否通过最终校验，文件是否实际写入 `storage/scenes`。
6. 前端是否因用户切换会话而主动阻止迟到结果覆盖画布。
7. 控制台出现场景 404 时先检查该会话是否实际拥有 `filename`；draft 会话没有 `.wild` 属于正常状态，前端不应发起场景请求。
8. 问答显示 `'ChatCompletion' object has no attribute 'get'` 时，表示模型 SDK 响应适配层版本不兼容，不代表 Chroma 或知识文档损坏。`model_client.py` 必须先把 Pydantic 响应通过 `model_dump()` 转为映射；用 `python -m app.rag.smoke_test` 可独立验证不调用远程模型的检索链路。
9. 精密模式出现“最终 Blueprint 缺失”时，先看 skeleton 节点的具体错误。当前实现支持从普通内容、`reasoning_content` 和常见 `blueprint/result/data` 包装对象提取；首次提取失败会自动执行一次非思考格式恢复。日志中的 `finish_reason`、`meta_marker`、`geometry_marker` 和 `recovery` 用于区分截断、漏输出和 JSON 格式错误。
10. Qwen、GLM 等模型漏掉 `meta.version`、`meta.type` 或 `meta.name` 时由归一化层补齐固定默认值，不属于 Linux 文件路径问题。界面若把 `meta.name` 显示为链接，只是 Markdown 自动识别 `.name` 域名；错误字段名必须使用反引号显示。
