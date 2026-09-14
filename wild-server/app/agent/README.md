# Agent 后端目录边界

`app/agent` 只负责 LangGraph 工作流及建筑生成领域逻辑。跨工作流复用的模型调用、RAG 和传输协议分别位于 `app/llm`、`app/rag` 和 `app/contracts`。

## 目录职责

- `graph.py`：创建 StateGraph、注册节点、连接边和条件路由。
- `state.py`：声明图的公开输入与完整持久化状态。
- `routing.py`：识别用户意图并生成路由决策。
- `runtime.py`：保存不应写入 checkpoint 的运行时回调和上下文。
- `nodes/`：LangGraph 的薄入口；只暴露图所需函数，不放 Prompt、解析器、校验器或修复算法。
- `planning/`：ExecutionPlan 类型契约、归一化、校验和状态更新。
- `generation/`：建筑方案、骨架、立面、组件、材质与空间规则。
- `knowledge/`：知识使用策略和仅对当前请求生效的受控网络研究。
- `validation/`：结构化问题、诊断快照和 Blueprint 约束校验。
- `repair/`：模型选择、程序执行的白名单修复工具。
- `prompts/`：按问答、规划、生成、研究、恢复和修复阶段拆分的提示词构建器。
- `assets/`：独立于建筑主图的 PBR 资源工作流。

## 依赖规则

1. `graph.py` 可以依赖 `state.py` 和 `nodes/`，节点之间不得互相导入。
2. 节点可以调用 `planning`、`generation`、`knowledge`、`validation`、`repair`、`app.llm` 和 `app.rag`。
3. 领域模块不得反向依赖 `nodes/` 或 `graph.py`。
4. `state.py` 与 `planning/contracts.py` 是结构化状态边界，不依赖具体节点。
5. API 和 Service 优先调用公开工作流入口；共享基础设施不放回 `app/agent` 根目录。

## 阅读顺序

从 `graph.py` 看节点与边，从 `nodes/*_node.py` 找到该节点对应的用例，再进入所属领域的
`*workflow.py` 阅读执行步骤。具体的数据解析、确定性规则和 Prompt 继续沿 import 进入同目录
模块；因此一个工作流文件只说明“先做什么、后做什么”，不再同时充当规则仓库。
