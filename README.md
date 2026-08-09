# WildAgent

WildAgent 是 AI 辅助的参数化 3D 建筑编辑器：模型生成可校验的 `.wild` Blueprint 或 ScenePatch，`wild-core` 负责确定性几何重建，Vue + Three.js 编辑器负责展示和持续编辑。

```text
自然语言 -> Agent / RAG / 校验 -> Blueprint 或 ScenePatch
                                   -> wild-compiler
                                   -> wild-core
                                   -> Three.js
```

与直接生成三角网格不同，WildAgent 的主资产是带语义 ID、可版本化、可复现和可逐参数编辑的 `.wild` 文件。Agent 不输出 Three.js 代码；批量或增量修改必须通过 ScenePatch，并由用户确认。

## 项目组成

- `wild-web/`：Vue 3 + TypeScript 编辑器、组合构件编译器、wild-core 和 Three.js 渲染。
- `wild-server/`：FastAPI、LangChain/LangGraph Agent、RAG、确定性校验、会话与场景 API。
- `docs/`：与当前实现一致的正式文档。
- `docs-dev/`：历史方案、阶段总结和问题复盘，仅供追溯。

## 开始使用

先阅读 [正式文档入口](docs/README.md)。本地启动、配置和测试见 [开发与测试](docs/DEVELOPMENT.md)，服务器环境文件、容器重建和排障见 [部署与运维](docs/DEPLOYMENT.md)，Agent 设计与对话事件见 [Agent 与 AI 对话设计](docs/AGENT_AND_CHAT.md)。

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

## 当前状态

已具备 Blueprint 生成、ScenePatch 增量修改、建筑知识问答、快速/精密 Agent 模式、RAG、确定性校验、会话恢复、组合构件编译和 3D 编辑。当前优化重点是协议版本化、双模式执行出口统一、Turn 服务端持久化和图级评测，详见 [优化路线](docs/ROADMAP.md)。
