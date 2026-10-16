# Agent 后端目录边界

`app/agent` 只负责 LangGraph 工作流及建筑生成领域逻辑。跨工作流复用的模型调用、RAG 和传输协议分别位于 `app/llm`、`app/rag` 和 `app/contracts`。

## 目录职责

- `graph.py`：创建 StateGraph、注册节点、连接边和条件路由。
- `state.py`：声明图的公开输入与完整持久化状态。
- `routing.py`：识别用户意图并生成路由决策。
- `runtime.py`：保存不应写入 checkpoint 的运行时回调和上下文。
- `nodes/`：LangGraph 的薄入口；只暴露图所需函数，不放 Prompt、解析器、校验器或修复算法。
- `planning/`：动态任务契约、归一化与校验（`execution.py`），以及结构化要求编译、节点消费指导、
  逐条验收和阶段进度（`requirements.py`）。
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

## 计划与验收边界

固定节点顺序只由 `graph.py` 决定。计划层不复制节点流程，也不负责选择下一个节点：

```text
execution_plan          本次需求要完成什么
structured_requirements 已批准任务编译出的、节点可消费和可校验的业务约束
acceptance_results      每条验收条件的实际值与证据；业务完成的唯一依据
execution_progress      固定节点运行到哪里；只用于展示，不证明业务完成
```

节点运行成功只更新 `execution_progress`；动态任务是否完成由 `acceptance_results` 计算。
无法机器判定的验收标为 `needs_review`，当前能力明确做不到的标为 `unsupported`——
两者都**只标记不阻断**（`severity="warning"`），写进验收结果供人查看，但不会终止本轮生成。

真正会让本轮失败的只剩两类：**计划对象本身不合法**（缺字段、ID 重复、引用被篡改，
放过去下游必然崩）和 **模型服务终态错误**（没有任何东西可生成）。
判定准则：问"是真的做不了，还是做得到但和用户措辞不一致、或者这份数据本身坏了"——
只有后者才配终止一次生成。

## 阅读顺序

从 `graph.py` 看节点与边，从 `nodes/*_node.py` 找到该节点对应的用例，再进入所属领域的
`*workflow.py` 阅读执行步骤。具体的数据解析、确定性规则和 Prompt 继续沿 import 进入同目录
模块；因此一个工作流文件只说明“先做什么、后做什么”，不再同时充当规则仓库。
