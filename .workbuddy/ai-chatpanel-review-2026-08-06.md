# AI 对话框（AIChatPanel）问题诊断与修复

> 审计日期：2026-08-06
> 范围：wild-web/src/components/panels/AIChatPanel.vue 及其挂载链（BottomPanel → AIChatPanel）
> 关联：用户报两个 bug —— (1) 发一条消息后对话框上移、下方大片空白、对话区变小；(2) LangGraph 多节点应像 Claude 那样流式展示每个节点的思考内容，但未达预期。

## 结论速览

**两个问题的根因都已定位，且都不在“设计没实现”，而在“实现细节”与“模型数据依赖”：**

- 问题 1（布局）：精密模式下思考面板作为 `flex-shrink:0` 块插在「消息列表」与「输入框」之间（最大 40vh），既挤占了对话区高度，又叠加上消息列表 `flex-start` 顶部对齐，造成下方大片空白 + 对话区变小。
- 问题 2（流式思考）：端到端管线**已正确接好**（LangGraph 节点调用 `on_reasoning_delta(node, delta)` → `send_thinking_delta` 发 `thinking_delta{node}` → bridge `appendThinkingContent(delta, node)` → store `nodeThinkingMap` → 面板 `getNodeThinking`）。唯一脆弱环节是**模型是否在流式增量里返回 `reasoning_content`**（`model_client.py` 从 `delta["reasoning_content"]` 取）。若模型不回流，则 `nodeThinkingMap` 为空 → 面板只剩节点标签和“思考 X字”摘要，没有流式正文。代码里甚至有 `ws_agent.py:682` 的兜底提示“当前模型接口没有返回 reasoning_content”。

## 已实施修复（AIChatPanel.vue）

1. **对话底部锚定**：`.messages-container::before` 加 `flex:1 1 auto` 占位，内容少时对话贴底（输入框上方），不再下方留大片空白；内容溢出时占位收缩为 0，正常滚动。
2. **思考面板改为浮动覆盖**：`.thinking-panel` 由 `flex-shrink:0`（占流内高度）改为 `position:absolute; top:44px; left/right:8px; z-index:5`，浮动在消息区上方，不再挤占对话区 flex 高度。配合 `.ai-chat-panel{position:relative}` 与 `:deep(.session-list-panel){z-index:10}` 保证会话头在面板之上。
3. **思考内容回退兜底**：节点推理块在 `getNodeThinking(node.name)` 为空时，回退显示诊断里的 `reasoning_preview`（后端 `send_debug("node", {... reasoning_preview ...})` 已提供）。这样即使模型不回流 reasoning_content，每个节点仍能展示其思考预览（虚线框区分）。

## 仍需用户确认 / 可继续做的

- **确认模型是否回流 reasoning_content**：打开浏览器控制台，发一条消息并开精密模式。若看到 `[agentStore] appendThinking node=...` 日志 → 实时流正常，问题 2 已靠回退兜底解决；若完全看不到该日志且面板里只有“思考 X字” → 模型未回流 reasoning_content（`model_client.py:_convert_chunk_to_generation_chunk` 读取 `delta["reasoning_content"]` 可能是字段名/嵌套结构不符）。可换用确实支持 `enable_thinking` 并回流 `reasoning_content` 的模型，或扩展适配器兼容其他字段名（如 `delta.thinking`）。
- 可选增强：把思考面板做成可拖拽高度 / 更小默认高度，或在非精密模式也复用同一面板。

## 关键文件 / 行

- 前端：`wild-web/src/components/panels/AIChatPanel.vue`（模板 + 样式均已改）
- 前端状态：`wild-web/src/stores/agentStore.ts:246` `appendThinkingContent`、`:503` `updateGeneratingNode`
- 前端桥接：`wild-web/src/agent/agentBridge.ts:394` `thinking_delta`、`:373` `agent_step generating`
- 后端流式：`wild-server/app/api/ws_agent.py:300` `send_thinking_delta`、`:349` `astream_events`
- 后端节点：`wild-server/app/agent/nodes/{skeleton_node,base_component_node,callback_node}.py` 均调用 `on_reasoning_delta(...)`
- 后端模型适配：`wild-server/app/agent/model_client.py:36` `reasoning_delta = delta.get("reasoning_content")`
