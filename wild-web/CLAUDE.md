# wild-web 协作说明

正式项目文档位于 [`../docs/`](../docs/README.md)。旧版前端说明和接口文档已归档到 `../docs-dev/wild-web/`，不要把它们当作当前实现。

## 前端边界

- `sceneStore` 持有 Blueprint 与 revision，所有结构修改通过 ScenePatch。
- `wild-core`（同仓库独立包，与 `wild-server` / `wild-web` 同级）负责组合构件展开与确定性几何重建；
  `renderer` 只做 Three.js 适配，不重复实现几何算法。
- `agentBridge` 独占 Agent 网络通信和 request/session 路由，Vue 组件不直接实现协议。
- `agentStore` 持有消息、会话与 `AgentTurn`；一次请求的步骤、过程和诊断不能使用全局浮层状态替代。
- Agent 提议的 Patch 必须经用户确认；迟到的蓝图结果不能覆盖当前已切换的画布。

## 关键入口

| 目标 | 文件 |
|---|---|
| 场景状态 | `src/stores/sceneStore.ts` |
| ScenePatch | `src/wild/scenePatch.ts` |
| Agent 状态 | `src/stores/agentStore.ts` |
| Agent 通信 | `src/agent/agentBridge.ts`、`src/agent/protocol.ts` |
| 对话 UI | `src/components/panels/AIChatPanel.vue`、`AgentExecutionPanel.vue` |
| 几何引擎（独立包） | `../wild-core/`，入口 `../wild-core/src/index.ts` |
| ├ 组合构件编译 | `../wild-core/src/compiler/` |
| └ 原语重建 | `../wild-core/src/primitive/` |
| 渲染适配 | `src/renderer/` |
| WILD 契约 | `../docs/specs/WILD_BLUEPRINT_SPEC.md`、`../wild-core/schema.json` |

## 验证

```powershell
# 引擎包自身（在 wild-core 下）
npm run typecheck

# 前端（在 wild-web 下）
npm run build
npm run check:core
npm run check:compiler
```

Agent 与对话协议详见 [`../docs/agent/AGENT_AND_CHAT.md`](../docs/agent/AGENT_AND_CHAT.md)。
