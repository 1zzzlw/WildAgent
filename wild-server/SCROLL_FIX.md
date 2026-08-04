# 滚动问题修复

## 问题描述

在精密模式下查看思考内容时，当用户向上滚动时，会被自动拉回底部，无法查看历史思考内容。

### 原因分析

Vue 组件中有多个 `watch` 监听器，当以下内容变化时会自动滚动到底部：

```typescript
watch(() => agentStore.session.messages.length, scrollToBottom)
watch(() => agentStore.pipelineSteps.length, scrollToBottom)
watch(() => agentStore.thinkingContent.length, scrollToBottom)
watch(() => agentStore.nodeThinkingMap.size, scrollToBottom, { deep: true })
// ... 等等
```

在思考内容**实时流式更新**时，`nodeThinkingMap` 持续变化，触发频繁的自动滚动，导致用户无法向上滚动查看。

## 解决方案

### 1. 添加用户滚动检测

```typescript
// 用户滚动检测
const isUserScrolling = ref(false)
const scrollTimeout = ref<number | null>(null)

// 检测用户是否在滚动
function handleUserScroll() {
  if (!messagesRef.value) return
  
  const container = messagesRef.value
  const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50
  
  // 如果不在底部，说明用户在向上滚动
  if (!isAtBottom) {
    isUserScrolling.value = true
  } else {
    // 如果在底部，允许自动滚动
    isUserScrolling.value = false
  }
  
  // 清除之前的定时器
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
  
  // 2秒后如果用户没有继续滚动，恢复自动滚动
  scrollTimeout.value = window.setTimeout(() => {
    isUserScrolling.value = false
  }, 2000)
}
```

### 2. 修改自动滚动逻辑

```typescript
function scrollToBottom() {
  // 如果用户正在滚动，不要自动滚动
  if (isUserScrolling.value) return
  
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}
```

### 3. 注册滚动监听器

```typescript
onMounted(() => {
  if (messagesRef.value) {
    messagesRef.value.addEventListener('scroll', handleUserScroll)
  }
  restoreSessionsFromServer()
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', handleUserScroll)
  }
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
})
```

## 工作原理

### 1. 检测滚动位置

当用户滚动时，计算当前滚动位置：
- **在底部** (`scrollHeight - scrollTop - clientHeight < 50`)：允许自动滚动
- **不在底部**：用户在查看历史内容，禁止自动滚动

### 2. 延迟恢复

当用户停止滚动 2 秒后，自动恢复自动滚动功能。这样：
- 用户可以向上滚动查看历史内容
- 停止滚动后，新内容继续自动滚动
- 如果用户滚动到底部，立即恢复自动滚动

### 3. 状态管理

```
用户操作             isUserScrolling    自动滚动
──────────────────   ───────────────   ──────
初始状态             false             ✅ 启用
向上滚动             true              ❌ 禁用
停留在历史位置        true              ❌ 禁用
2秒后                false             ✅ 启用
滚动到底部           false             ✅ 启用
```

## 测试验证

### 测试步骤

1. 启动前端服务
   ```bash
   cd wild-web
   npm run dev
   ```

2. 访问 `http://localhost:5173`

3. 开启**精密模式**

4. 输入：`生成一个10×8米的欧式别墅`

5. 等待骨架节点开始生成思考内容

6. 展开骨架节点卡片

7. 当思考内容实时流式显示时，尝试向上滚动

### 预期行为

✅ **正确行为**：
- 向上滚动时，滚动条停留在用户选择的位置
- 思考内容继续在底部更新，但不会自动滚动
- 用户可以从容查看历史思考内容
- 停止滚动 2 秒后，自动滚动恢复
- 滚动到底部时，立即恢复自动滚动

❌ **错误行为（修复前）**：
- 向上滚动后，立即被拉回底部
- 无法查看历史内容
- 用户体验很差

## 技术细节

### 滚动位置计算

```typescript
const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50
```

- `scrollHeight`: 内容总高度（包括不可见部分）
- `scrollTop`: 当前滚动位置（顶部）
- `clientHeight`: 可见区域高度
- `< 50`: 50px 的容差，考虑到像素取整误差

### 为什么是 2 秒？

- **太短**（如 0.5 秒）：用户还在阅读，就开始自动滚动，打断阅读
- **太长**（如 10 秒）：用户看完想恢复自动滚动，等待时间太长
- **2 秒**：平衡点，用户阅读完一段内容的平均时间

### 内存泄漏防护

```typescript
onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', handleUserScroll)
  }
  if (scrollTimeout.value) {
    clearTimeout(scrollTimeout.value)
  }
})
```

- 组件卸载时，移除事件监听器
- 清除定时器，防止内存泄漏

## 其他改进

### 1. 性能优化

可以添加节流（throttle）来减少滚动事件的处理频率：

```typescript
import { throttle } from 'lodash-es'

const handleUserScroll = throttle(() => {
  // ... 原有逻辑
}, 100) // 每 100ms 最多处理一次
```

### 2. 用户反馈

可以添加视觉提示，告诉用户自动滚动已暂停：

```vue
<div v-if="isUserScrolling" class="scroll-hint">
  📌 自动滚动已暂停 · 滚动到底部恢复
</div>
```

```css
.scroll-hint {
  position: sticky;
  top: 0;
  padding: 4px 8px;
  background: rgba(78, 161, 243, 0.2);
  border-bottom: 1px solid #4ea1f3;
  font-size: 11px;
  color: #4ea1f3;
  text-align: center;
  z-index: 10;
  animation: fadeIn 0.2s;
}
```

### 3. 快捷跳转按钮

当用户向上滚动时，显示"跳转到底部"按钮：

```vue
<el-button
  v-if="isUserScrolling"
  class="scroll-to-bottom"
  circle
  size="small"
  @click="forceScrollToBottom"
>
  <el-icon><ArrowDown /></el-icon>
</el-button>
```

```typescript
function forceScrollToBottom() {
  isUserScrolling.value = false
  scrollToBottom()
}
```

```css
.scroll-to-bottom {
  position: sticky;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
```

## 总结

通过添加用户滚动检测和智能暂停自动滚动，我们解决了：

✅ 用户无法向上滚动查看历史内容的问题
✅ 自动滚动与用户滚动的冲突
✅ 实时流式内容更新时的用户体验

同时保持了：

✅ 新内容到达时的自动滚动
✅ 用户滚动到底部时的立即恢复
✅ 简洁的代码实现，无需额外依赖
