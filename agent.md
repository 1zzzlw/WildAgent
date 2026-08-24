# WildAgent 协作上下文

此文件只提供给后续 Agent/AI 快速建立边界；正式项目文档以 [`docs/README.md`](docs/README.md) 为入口，历史材料位于 `docs-dev/`。

## 必须保持的边界

1. `.wild` Blueprint 是唯一场景事实来源。
2. `wild-core` 只做确定性解析和几何重建，不承载 UI 或 Agent 逻辑。
3. 组合构件先经 `wild-compiler` 展开，再进入 `wild-core`。
4. Agent 只产出 Blueprint、ScenePatch 或文本；不产出 Three.js 几何代码。
5. Agent 的增量编辑必须是需要用户确认的 ScenePatch。
6. 最终校验有错误时不得保存或自动加载 Blueprint。

## 代码入口

| 目标 | 入口 |
|---|---|
| 场景状态与 Patch | `wild-web/src/stores/sceneStore.ts`、`wild-web/src/wild/scenePatch.ts` |
| Agent 会话与 Turn | `wild-web/src/stores/agentStore.ts` |
| WebSocket/REST 桥接 | `wild-web/src/agent/agentBridge.ts` |
| AI 对话展示 | `wild-web/src/components/panels/AIChatPanel.vue`、`AgentExecutionPanel.vue` |
| LangGraph | `wild-server/app/agent/graph.py`、`graph_state.py`、`nodes/` |
| 快速 Agent 与校验 | `wild-server/app/services/agent_service.py` |
| Agent WebSocket | `wild-server/app/api/ws_agent.py` |
| RAG | `wild-server/app/spec/loader.py`、`wild-server/storage/knowledge_base/` |
| WILD 契约 | `wild-web/wild-lang/` |

## 修改原则

- 先核对源码和测试，不以 `docs-dev/` 的旧设计作为现状。
- 网络逻辑放在 Bridge/API，领域状态放 Store/Service，组件只展示与触发动作。
- 保持修改小而可验证；Agent/协议变更同时更新 `docs/agent/AGENT_AND_CHAT.md`。
- 前端至少运行 `npm run build`；后端至少运行相关 pytest 与 Python 语法检查。

当前架构、开发方式和待办分别见 `docs/ARCHITECTURE.md`、`docs/DEVELOPMENT.md`、`docs/ROADMAP.md`。
