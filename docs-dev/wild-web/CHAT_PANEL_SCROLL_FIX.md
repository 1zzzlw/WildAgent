# AI对话框滚动问题修复

## 问题描述

在精密模式下，LangGraph 多节点思考内容实时流式更新时，对话框会自动向上滚动，用户无法查看历史内容。

## 根本原因分析

### 主要原因：布局结构错误

**原始错误布局：**
```html
<div class="messages-container">
  <!-- 用户消息 -->
  <div>用户消息列表</div>
  
  <!-- thinking-panel 在 messages-container 内部！ -->
  <div class="thinking-panel">
    思考内容
  </div>
  
  <!-- AI 回复 -->
  <div>AI 回复</div>
</div>
```

**问题：**
1. `thinking-panel` 在 `messages-container` 内部
2. 当 `thinking-panel` 出现或展开时，会占据 `messages-container` 的空间
3. 导致上方的消息被挤压向上，产生"自动上移"的错觉
4. 用户滚动查看历史消息时，`thinking-panel` 内容更新会改变容器高度，触发滚动位置重新计算

### 次要原因：watch 监听器过多

前端有过多的 `watch` 监听器在内容变化时触发 `scrollToBottom()`：

```typescript
// 修复前：9个 watch 监听器
watch(() => agentStore.session.messages.length, scrollToBottom)
watch(() => agentStore.pipelineSteps.length, scrollToBottom)
watch(() => agentStore.thinkingContent.length, scrollToBottom)
watch(() => agentStore.thinkingStatus, scrollToBottom)
watch(() => agentStore.isProcessing, scrollToBottom)
watch(() => agentStore.blueprintLoaded, scrollToBottom)
watch(() => agentStore.generatingNodes.length, scrollToBottom)
watch(() => agentStore.sessionMetrics, scrollToBottom)
watch(() => agentStore.nodeThinkingMap.size, scrollToBottom, { deep: true })  // ← 最频繁触发
```

## 解决方案

### 1. 修复布局结构（核心修复）

**正确布局：**
```html
<!-- 消息区域 -->
<div class="messages-container">
  <!-- 用户消息 -->
  <div>用户消息列表</div>
  
  <!-- AI 回复 -->
  <div>AI 回复</div>
</div>

<!-- thinking-panel 独立于 messages-container 外部 -->
<div class="thinking-panel">
  思考内容
</div>
```

**优势：**
- ✅ 消息区域和思考面板完全独立
- ✅ `thinking-panel` 出现/展开不会影响消息区域的布局
- ✅ 各自独立滚动，互不干扰
- ✅ 消息区域可以自由滚动查看历史内容

```typescript
// 修复后：仅保留必要的监听器
// 消息变化时滚动（用户发送、AI回复）
watch(() => agentStore.session.messages.length, scrollToBottom)

// Blueprint 加载成功时滚动
watch(() => agentStore.blueprintLoaded, scrollToBottom)

// 精密模式下，只在生成节点数量变化（新节点开始）时滚动
// 避免思考内容更新时频繁触发
watch(() => agentStore.generatingNodes.length, scrollToBottom)

// 非精密模式下的滚动触发器
watch(() => agentStore.pipelineSteps.length, () => {
  if (!agentStore.precisionMode) scrollToBottom()
})
watch(() => agentStore.thinkingContent.length, () => {
  if (!agentStore.precisionMode) scrollToBottom()
})
```

### 2. 优化策略

- ✅ **只在节点开始时滚动** - `generatingNodes.length` 变化表示新节点开始执行
- ✅ **思考内容更新不滚动** - `nodeThinkingMap` 的变化不再触发滚动
- ✅ **保留用户滚动检测** - 现有的 `isUserScrolling` 机制继续工作
- ✅ **模式分离** - 精密模式和非精密模式使用不同的滚动策略

## 验证测试

### 测试步骤

1. 启动前后端服务
   ```bash
   # 后端
   cd wild-server
   python main.py

   # 前端
   cd wild-web
   npm run dev
   ```

2. 打开精密模式开关

3. 输入：`生成一个10×8米的欧式别墅`

4. 等待骨架节点开始生成思考内容

5. **向上滚动查看历史消息**

### 预期行为

✅ **正确**：
- 向上滚动时，滚动位置保持在用户选择的位置
- 思考内容在底部继续流式更新，但不会自动滚动
- 新节点开始时（如从骨架节点到门节点），会自动滚动到新节点
- 用户可以自由查看历史思考内容
- 停止滚动 2 秒后，自动滚动恢复
- 滚动到底部时，立即恢复自动滚动

❌ **错误（修复前）**：
- 向上滚动后立即被拉回底部
- 思考内容每次更新都触发滚动
- 无法查看历史内容

## 多节点思考内容显示

### 架构确认

后端已正确实现节点思考内容推送：

```python
# wild-server/app/api/ws_agent.py
async def send_thinking_delta(node_name: str, delta: str):
    """实时推送节点的思考内容给前端（带节点标识）"""
    await ws.send_json({
        "type": "thinking_delta",
        "request_id": request_id,
        "node": node_name,  # 标记是哪个节点的思考
        "delta": delta,
    })
```

各节点正确调用：

```python
# skeleton_node.py
await on_reasoning_delta("skeleton", reasoning_delta)

# callback_node.py
await on_reasoning_delta("callback", reasoning_delta)

# base_component_node.py
await on_reasoning_delta(f"{config.component_type}_gen", reasoning_delta)
```

前端正确处理：

```typescript
// agentBridge.ts
case 'thinking_delta':
  if (agentStore.thinkingMode || agentStore.precisionMode) {
    agentStore.appendThinkingContent(message.delta, message.node)
  }
  break

// agentStore.ts
function appendThinkingContent(delta: string, nodeName?: string) {
  if (precisionMode.value && nodeName) {
    const existing = nodeThinkingMap.value.get(nodeName)
    if (existing) {
      existing.content += delta
    } else {
      nodeThinkingMap.value.set(nodeName, {
        node: nodeName,
        content: delta,
        status: 'thinking'
      })
    }
    nodeThinkingMap.value = new Map(nodeThinkingMap.value)
  }
}
```

前端展示：

```vue
<!-- AIChatPanel.vue -->
<div v-for="node in agentStore.generatingNodes" :key="node.name" class="thinking-node">
  <!-- 节点标题 -->
  <div class="thinking-node-bar">
    <span class="thinking-node-label">{{ node.label }}</span>
  </div>
  
  <!-- 推理内容 -->
  <div v-if="getNodeThinking(node.name)" class="reasoning-block">
    <div class="reasoning-block-text" v-html="renderMarkdown(getNodeThinking(node.name))"></div>
  </div>
</div>
```

### 显示流程

1. 后端节点开始执行 → 发送 `agent_step` 消息（如 `skeleton:running:...`）
2. 前端 `updateGeneratingNode()` 添加节点到 `generatingNodes` 列表
3. 节点思考内容流式生成 → 后端发送 `thinking_delta` 带 `node` 字段
4. 前端 `appendThinkingContent()` 更新 `nodeThinkingMap`
5. UI 渲染各节点的思考内容（Markdown 格式）

## 相关文件

### 前端
- `wild-web/src/components/panels/AIChatPanel.vue` - 对话面板主组件（已修复滚动）
- `wild-web/src/stores/agentStore.ts` - 状态管理
- `wild-web/src/agent/agentBridge.ts` - WebSocket 消息处理

### 后端
- `wild-server/app/api/ws_agent.py` - WebSocket API
- `wild-server/app/agent/nodes/skeleton_node.py` - 骨架节点
- `wild-server/app/agent/nodes/base_component_node.py` - 组件节点
- `wild-server/app/agent/nodes/callback_node.py` - 回调节点

### 文档
- `wild-server/SCROLL_FIX.md` - 原滚动问题文档
- `wild-server/THINKING_UI_REDESIGN.md` - UI 设计文档
- `wild-web/CHAT_PANEL_SCROLL_FIX.md` - 本修复文档

## 总结

通过精简 watch 监听器，从 9 个减少到 5 个，并确保思考内容更新不触发自动滚动，解决了用户无法查看历史内容的问题。

多节点思考内容的完整流程已经正确实现，每个节点的思考内容会独立显示在精密模式面板中。

修复后的体验：
- ✅ 流畅的自动滚动（仅在必要时）
- ✅ 尊重用户的滚动操作
- ✅ 清晰的多节点思考内容展示
- ✅ 完整的 Markdown 格式支持
