# WildAgent 架构说明

最后核对：2026-08-09。

## 1. 产品与边界

WildAgent 是 AI 辅助的参数化 3D 建筑编辑器。AI 负责理解需求并生成结构化参数，确定性引擎负责几何重建，用户负责最终确认和编辑。

四条边界必须保持：

- `.wild` Blueprint 是场景唯一事实来源。
- `wild-core` 只做解析、空间求解与几何重建，不依赖 Vue、Three.js 或 Agent。
- 前端负责编辑状态、ScenePatch、交互和渲染适配，不发明新的 WILD 语义。
- Agent 只生成 Blueprint 或 ScenePatch，不生成 Three.js 代码或三角网格。

## 2. 系统结构

```text
自然语言 / 手动编辑
        │
        ├── WebSocket ──> wild-server Agent
        │                    ├── 意图分类
        │                    ├── RAG + LLM
        │                    ├── 确定性校验/修正
        │                    └── Blueprint / ScenePatch
        │
        └── ScenePatch ──> sceneStore ──> Blueprint
                                          │
                                          v
                          wild-compiler（组合构件展开）
                                          │
                                          v
                          wild-core（确定性几何重建）
                                          │
                                          v
                          renderer ──> Three.js 场景
```

| 模块 | 主要职责 | 权威入口 |
|---|---|---|
| `wild-web` | Vue 编辑器、状态、会话、交互、3D 展示 | `src/stores/sceneStore.ts` |
| `wild-compiler` | 把门窗、阳台、灯具等组合构件展开为基础元素 | `wild-web/src/wild-compiler/` |
| `wild-core` | 从 Blueprint 确定性重建 MeshData | `wild-web/src/wild-core/` |
| `wild-server` | Agent、RAG、校验、会话和场景文件 API | `wild-server/app/` |
| `wild-lang` | WILD 语言和兼容性契约 | `wild-web/wild-lang/` |

## 3. 核心数据模型

### Blueprint

`.wild` 是 JSON 文档，核心包含 `meta`、`geometry`、`materials`、`behaviors`，编辑器私有状态放在 `editor`。`geometry.elements` 保存基础构件，`geometry.components` 保存可编译的组合构件。

### ScenePatch

所有增量编辑使用 ScenePatch：

```text
patch_id + base_revision + source + mode + operations
```

`base_revision` 必须匹配当前场景版本。Agent 修改使用 `mode=proposal` 和 `requires_confirmation=true`，前端确认后才调用 `sceneStore.applyPatch()`；手动编辑可以直接生成并应用用户 Patch。

### 会话与场景文件

- 会话元数据、消息与 Agent Turn：`wild-server/storage/sessions/`。
- 场景蓝图：`wild-server/storage/scenes/YYYY-MM-DD/{session_id}_{name}.wild`。
- 浏览器保留消息和 Agent Turn 的本地副本，服务器快照是刷新及跨设备恢复入口。
- 同一会话的 Turn 快照按发送顺序串行写入，避免旧 `running` 快照覆盖新 `completed` 状态。
- 页面刷新遗留的本地 `running` Turn 会恢复为“已中断”；服务重启后，不属于当前服务实例的服务端 `running` Turn 也会被标记为中断。
- 迟到的 WebSocket 事件按 `request_id + session_id` 路由，不能覆盖用户已切换到的当前画布。

## 4. 前端数据流

```text
Agent WebSocket event
  -> agentBridge（协议、request/session 路由、产物加载顺序）
  -> agentStore（消息、Turn、步骤、诊断、会话）
  -> AIChatPanel / AgentExecutionPanel

Blueprint / ScenePatch
  -> sceneStore
  -> 重建 Worker
  -> wild-compiler
  -> wild-core
  -> renderer
```

关键原则：网络逻辑集中在 `agentBridge`，领域状态集中在 Store，组件只负责展示和用户动作。蓝图产物加载完成后，正式回复才同步到会话历史，避免消息先完成而场景仍在加载的竞态。

## 5. 后端数据流

后端提供两条执行路径：

- 快速模式：统一 Agent 服务完成生成、修改或问答，适合低延迟请求。
- 精密模式：LangGraph 对生成任务进行骨架规划、组件并行生成、组件校验、合并、最终校验和按组件重试；编辑和问答走各自短路径。

两条路径必须共享相同安全出口：

- `agent_delivery.py` 统一负责复检去重、最终错误门禁、安全文件名、保存和成功摘要。
- 精密模式在组件派发前先修复/阻断无效骨架（例如墙高为零）；`merge` 只做快速、确定性的归并和语义门禁。门窗局部坐标、父墙范围、同墙重叠、设计数量/立面开口约束及材质引用必须在最终交付前全部成立。合并耗时短不代表校验被省略。
- 最终校验把工具文本拆为稳定的 `ValidationIssue`：错误码、校验器、实体 ID/类型、消息、修复模式和建议工具。同一实体的多条错误全部保留，无法绑定实体的全局设计错误不会被误交给局部修复模型。
- 修复分两级：可确定的问题继续由 `fix_*` 工具直接处理；仍有歧义的问题进入 callback，模型只能输出白名单修复动作，程序在 Blueprint 副本上执行。动作只能修改本轮失败实体，禁止改写 `id/type`、引用不存在的父墙或材质；设计配额明确缺少某类构件时，可通过 `design:<type>` 目标受限调用 `add_entity`，不能任意新增组件。
- callback 候选必须经过完整复检。只有错误数量严格下降且没有引入新的“错误码 + 实体”组合时，才把修改同步回骨架或组件分片；否则候选自动回滚。该 JSON 动作协议不依赖某个供应商的原生 tool-calling，便于更换模型。
- OpenAI-compatible 流式响应的结构化产物优先从 `content` 提取，仅在失败时从 `reasoning_content` 兼容回退；解析器按 Blueprint/ScenePatch 结构选择完整 JSON，而不是依赖第一个 Markdown 代码块。
- 模型响应适配层同时接受旧版字典和新版 OpenAI SDK 的 Pydantic `ChatCompletion/ChatCompletionChunk` 对象；业务节点不得直接假定响应存在 `.get()`，避免 RAG 已召回但问答在响应转换阶段失败。
- 完整生成只有最终校验为 `complete` 且错误数为 0 时才能保存并加载；快速和精密模式不能各自绕过门禁。
- 增量修改只返回 ScenePatch 提案，不直接改场景。
- 问答只返回文本，不伪装成思考流或蓝图产物。
- 草稿或失败会话没有场景文件时，前端不得猜测 `/api/scenes/{session_id}.wild`；只有服务端返回权威 `filename/file_url` 后才能请求场景，避免把“尚无产物”表现成 404 加载故障。

## 6. API 边界

| 通道 | 路径 | 用途 |
|---|---|---|
| WebSocket | `/ws/agent` | Agent 请求、步骤、思考/进度、诊断和产物事件 |
| REST | `/api/scenes` | `.wild` 文件列表及新旧路径兼容 CRUD |
| REST | `/api/sessions` | 会话元数据与列表 |
| REST | `/api/sessions/{id}/messages` | 会话消息历史 |
| REST | `/api/sessions/{id}/turns` | Agent Turn 快照与中断恢复 |

具体 Agent 事件见 [Agent 与 AI 对话设计](AGENT_AND_CHAT.md)。

## 7. 架构评价

当前设计方向合理，尤其是 `.wild` 单一事实源、AI 与几何引擎隔离、ScenePatch 确认机制、确定性校验出口和 LangGraph 分片生成。这些边界能把模型的不确定性限制在结构化、可检查的范围内。

本轮已经补齐协议版本、结构化步骤、统一保存门禁、Turn 服务端恢复、图级路由测试以及“结构化错误 → 模型选择工具 → 程序执行 → 复检提交/回滚”的定向修复闭环。当前主要技术债转为：快速/精密模式仍有意图分类与事件适配重复、缺少覆盖各类建筑的固定质量评测集，以及会话元数据、Turn、消息和 `.wild` 尚未形成事务。后续处理顺序见 [优化路线](ROADMAP.md)。
