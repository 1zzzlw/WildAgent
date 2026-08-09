# RAG整体开发路线

> 本文件是 WildAgent Phase 3 LangGraph 与 RAG 优化的总步骤路线，后续开发按此顺序推进。

## 1. 目标

- 把当前 Phase 2 的单体 Agent + 线性校验流水线，升级为 Phase 3 的 LangGraph 分片节点流水线。
- 后端按“解析请求 → 组件生成 → 合并校验 → 回调重试”的方式工作。
- 前端按“流水线节点可视化 + 思考内容并行展示”的风格展示对话过程。
- 保留现有自动修复代码作为 LangChain / fallback 路径，但 Phase 3 主流程优先使用节点回调重试。

## 2. 核心原则

1. 组件拆分优先
   - 先识别用户需求，提取组件清单（门、窗、屋顶、栏杆、雨棚、阳台、灯具、坡道、凸窗、檐口、烟囱等）。
   - 每个组件用独立节点生成，避免一次性生成完整 Blueprint。

2. 内存合并
   - 各节点产出的 fragment 保存在 LangGraph State 内存中。
   - 合并节点负责组装完整 Blueprint，不做深度修复。

3. 结构化校验与回调
   - 组件节点后要做本地校验。
   - 校验失败返回结构化错误信息，包含责任组件、错误字段、当前值、参考范围、已通过组件列表。
   - 失败组件可循环回调修正，最多 `max_retries=3`。

4. 前端可视化
   - 所有节点应在前端按流水线样式展示。
   - 每个节点可独立展开，显示节点状态、诊断、RAG trace 和思考内容。
   - 思考内容与节点流水线属于不同事件类型，UI 区分展示。

5. 兼容性优先
   - 保持现有 `AIChatPanel`、`agentStore.ts`、`agentBridge.ts` 的核心结构不变。
   - 后端可以灰度切换 LangChain/LangGraph。

## 3. 总步骤

### Step 0：梳理现有文档与约定

- 对齐现有文档：`docs/项目阶段路线文档.md`、`docs/LangGraph规划/01-总体架构设计.md`、`docs/LangGraph规划/03-回调与重试机制.md`、`docs/LangGraph规划/08-实施进度.md`。
- 确认当前 `wild-server/app/services/agent_service.py` 15 步校验流水线与现有工具接口。
- 确认前端 `wild-web/src/components/panels/AIChatPanel.vue` 当前流水线、思考内容和精密模式展示方式。

### Step 1：定义 LangGraph State 与节点框架

1. 新建 `app/agent/graph_state.py`
   - 定义 `GenerationState`，包含请求、组件 fragments、校验结果、RAG trace、retry_count、node_diagnostics 等。
2. 基于 `langgraph.graph.StateGraph` 创建 `app/agent/graph.py`
   - 添加入口节点、组件节点、合并节点、验证节点、回调节点。
3. 设计节点事件协议
   - `node_started`, `node_finished`, `node_error`, `node_diagnostics`, `reasoning_content`。
   - 区分 `pipeline` 事件和 `thinking` 事件。

### Step 2：实现骨架生成节点

1. 新建 `skeleton_node.py`
   - 负责用户输入解析、建筑类型识别、骨架 RAG、骨架 LLM 生成。
   - 输出 walls/floors/columns/beams、bounding_box、skeleton_summary。
2. 校验骨架结果
   - 调用现有 schema 校验。
   - 失败时直接终止或返回可修正错误。

### Step 3：实现组件节点与生成工厂

1. 建立组件节点工厂 `base_component_node.py`
   - 组件节点统一接口。
   - 通过配置自动生成 `door_node.py`、`window_node.py`、`roof_node.py`、`railing_node.py`、`canopy_node.py`、`balcony_node.py`、`light_node.py`、`ramp_node.py`、`bay_window_node.py`、`cornice_node.py`、`chimney_node.py`。
2. 确定 `need_keywords` 规则
   - 让低频组件在用户输入未提及时自动跳过，零 Token 消耗。
3. 每个组件节点实现：
   - 独立 RAG：只检索该组件相关知识片段。
   - 生成输出：组件 fragment、诊断信息、状态。
   - 结构化校验：本地字段和引用基本正确性。

### Step 4：实现 merge 节点与一致性检查

1. 新建 `merge_node.py`
   - 聚合各组件 fragments，生成 `merged_blueprint`。
   - 检查 ID 冲突、parent 引用、重复元素、坐标系一致性。
2. 只做合并与一致性检查，不做深度修复。

### Step 5：实现全局校验节点

1. 新建 `validate_node.py`
   - 调用现有 `run_validation_pipeline()`。
   - 记录每一步结果，并把错误归因到组件 ID。
2. 设计结构化结果格式
   - `failed_components`, `passed_components`, `error_summary`, `suggestions`。

### Step 6：实现回调重试节点

1. 新建 `callback_node.py`
   - 失败组件回调：使用清晰的结构化 payload/
   - 尽量只修正失败组件，不改写已通过组件。
2. 控制重试次数
   - `retry_count < 3` 时回调。
   - 超过上限时标记人工介入或降级。
3. 明确旧自动修复的定位
   - LangGraph 主流程优先节点回调重试。
   - 旧 `fix_*` 自动修复代码作为 fallback 路径或 LangChain 兼容路径。

### Step 7：实现前端进度与样式优化

1. 在前端展示“节点流水线”风格
   - 类似流水线，每个节点按顺序或并行块展示。
   - 节点项显示 `name`, `status`, `耗时`, `RAG 信息`, `LLM 信息`。
2. 同时显示思考内容
   - 思考内容可展开查看，思考内容与流水线内容分区。
   - 如果该节点有 `reasoning_content`，展开后显示 Markdown/文本。
3. 兼容现有对话框
   - 保持原有 `AIChatPanel` 样式基础。
   - 只是把“校验流水线”扩展为“节点流水线 + 思考内容”。
4. 严格区分事件类型
   - `thinking` 事件：实际返回的模型思考内容。
   - `pipeline` 事件：真实节点执行状态。

### Step 8：灰度切换与集成测试

1. 确保后端可灰度开关
   - 保持 `precision_mode` 兼容。
   - 关闭时仍走旧 LangChain 路径。
   - 开启时走 LangGraph 路径。
2. 前端请求兼容
   - 现有 `precision_mode` 和 `thinking_mode` 参数不变。
3. 集成测试
   - 固定 prompt → 组件节点生成 → merge → 校验 → 无 ❌ 错误。
   - 前端接收 `agent_step`、`debug_log`、`reasoning_content`。
4. 验证结果
   - 流水线节点在 UI 中完整展示。
   - 思考内容可同时展开。
   - 失败节点可回调重试。

## 4. 前端优化细节

### 4.1 样式方向

- 节点像流水线步骤一样排列。
- 重要节点用颜色区分：
  - 进行中：蓝色/动画
  - 成功：绿色
  - 警告：黄色
  - 失败：红色
- 每个节点的右侧或下方显示可展开的思考内容。
- 保持聊天对话框和流水线面板并行显示，用户可以同时看到对话和节点状态。

### 4.2 关键组件

- `AIChatPanel.vue`
  - 主区域：用户消息 + AI 回复。
  - 右侧/下方：节点流水线面板。
  - 面板可折叠：展开显示每个节点的思考内容。
- `agentStore.ts`
  - 新增 `generatingNodes`、`debugLogs`、`sessionMetrics`。
  - 保留 `pipelineSteps` 原有校验流水线数据。
- `agentBridge.ts`
  - 接收后端 `agent_step`、`debug_log`、`reasoning_content`。
  - 把节点事件和思考事件分装到不同 store 字段。

### 4.3 UI 行为

- 生成开始后自动打开节点流水线面板。
- 节点完成后自动滚动到最新节点。
- 思考内容超过 400px 时局部滚动，不影响整个面板布局。
- 关闭思考模式时，只显示节点状态，不显示模型推理文本。

## 5. 验收标准

- 后端 `graph.py` 能完整执行 `skeleton → 组件节点 → merge → validate → callback`。
- 节点事件数据能传到前端，并在 UI 中显示。
- 前端对话框样式显示流水线节点与思考内容，并与现有对话文本兼容。
- LangChain / LangGraph 两条路径可灰度切换。
- 校验失败后可以明确回调失败组件，并统计重试次数。

## 6. 参考文件

- `docs/项目阶段路线文档.md`
- `docs/LangGraph规划/01-总体架构设计.md`
- `docs/LangGraph规划/03-回调与重试机制.md`
- `docs/LangGraph规划/06-前后端影响分析.md`
- `docs/LangGraph规划/08-实施进度.md`
- `wild-web/src/components/panels/AIChatPanel.vue`
- `wild-server/app/api/ws_agent.py`

## 7. 备注

- 本路线强调“前端流水线节点可视化 + 同时可见思考内容”。
- 若后续发现某个节点结构太复杂，可先拆成“骨架 → 组件组 → 诊断节点”再逐步细化。
- 任何新的组件类型都应先在后端注册表里定义，再在前端节点展示中补充。
