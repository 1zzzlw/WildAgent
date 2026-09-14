# Agent 后端目录边界

`app/agent` 只负责 LangGraph 工作流及建筑生成领域逻辑。跨工作流复用的模型调用、RAG 和传输协议分别位于 `app/llm`、`app/rag` 和 `app/contracts`。

## 目录职责

- `graph.py`：创建 StateGraph、注册节点、连接边和条件路由。
- `state.py`：声明图的公开输入与完整持久化状态。
- `routing.py`：识别用户意图并生成路由决策。
- `runtime.py`：保存不应写入 checkpoint 的运行时回调和上下文。
- `nodes/`：LangGraph 节点入口；节点只做编排，不承载可复用领域算法。
- `planning/`：ExecutionPlan 类型契约、归一化、校验和状态更新。
- `generation/`：建筑方案、骨架、立面、组件、材质与空间规则。
- `knowledge/`：知识使用策略和仅对当前请求生效的受控网络研究。
- `validation/`：结构化问题、诊断快照和 Blueprint 约束校验。
- `repair/`：模型选择、程序执行的白名单修复工具。
- `prompts/`：按规划、生成和修复阶段拆分的提示词构建器。
- `assets/`：独立于建筑主图的 PBR 资源工作流。

## 依赖规则

1. `graph.py` 可以依赖 `state.py` 和 `nodes/`，节点之间不得互相导入。
2. 节点可以调用 `planning`、`generation`、`knowledge`、`validation`、`repair`、`app.llm` 和 `app.rag`。
3. 领域模块不得反向依赖 `nodes/` 或 `graph.py`。
4. `state.py` 与 `planning/contracts.py` 是结构化状态边界，不依赖具体节点。
5. API 和 Service 优先调用公开工作流入口；共享基础设施不放回 `app/agent` 根目录。
