# 前端流式思考展示测试指南

## 修改内容总结

### 后端修改
无需修改，后端已经正确发送带 `node` 参数的 `thinking_delta` 消息。

### 前端修改

#### 1. 类型定义 (`wild-web/src/types/agent.ts`)
```typescript
export interface ThinkingDeltaResponse {
  type: 'thinking_delta'
  request_id: string
  node?: string  // ✅ 新增：标识是哪个节点的思考内容
  delta: string
}
```

#### 2. Store 状态管理 (`wild-web/src/stores/agentStore.ts`)
- ✅ 新增 `nodeThinkingMap` 来按节点存储思考内容
- ✅ 修改 `appendThinkingContent()` 支持节点参数
- ✅ 新增 `completeNodeThinking()` 标记节点思考完成

#### 3. WebSocket 消息处理 (`wild-web/src/agent/agentBridge.ts`)
```typescript
case 'thinking_delta':
  if (agentStore.thinkingMode || agentStore.precisionMode) {
    agentStore.appendThinkingContent(message.delta, message.node)  // ✅ 传递 node 参数
  }
  break
```

#### 4. UI 展示 (`wild-web/src/components/panels/AIChatPanel.vue`)
- ✅ 在精密模式的节点卡片中添加实时思考内容展示
- ✅ 使用类似图片的折叠样式
- ✅ 添加思考时间估算
- ✅ 区分"实时思考"和"完整思考记录"

## 测试步骤

### 1. 启动后端服务
```bash
cd wild-server
.\.venv\Scripts\activate
python main.py
```

### 2. 启动前端服务
```bash
cd wild-web
npm run dev
```

### 3. 测试流式思考

#### 方式1：精密模式测试（推荐）
1. 打开前端页面 `http://localhost:5173`
2. 在底部连接状态栏，**开启"精密"开关**
3. 输入测试消息：`生成一个10×8米的欧式别墅`
4. 观察效果：
   - 骨架节点卡片展开后应该看到 "💭 思考过程" 区域
   - 思考内容应该**实时流式**显示，而非等待完成后一次性显示
   - 每个被建议的组件节点（door, window, roof, balcony）都应该有独立的思考内容
   - 思考内容应该有深色背景，类似图片中的样式

#### 方式2：LangChain 模式测试
1. **关闭"精密"开关**，**开启"思考"开关**
2. 输入测试消息：`生成一个中式凉亭`
3. 观察效果：
   - 应该看到"模型思考内容"区域
   - 思考内容应该实时流式显示

## 预期效果

### 精密模式
```
🔬 精密模式 — 实时节点进度

✅ 骨架 4构件 | RAG 17470字 948ms | LLM 4326字 89310ms | 思考 6154字 | 建议组件: door, window, roof, balcony
  ▼ [展开]
  
  💭 思考过程 (123s)
  ┌─────────────────────────────────────┐
  │ 思考过程：1. **分析请求**：         │
  │   * 目标：生成一个10×8米的欧式别墅 │
  │   * 角色：建筑骨架生成专家         │
  │   ...（实时流式展示）              │
  └─────────────────────────────────────┘
  
  📝 完整思考记录
  [生成完成后显示完整的 reasoning_preview]
  
  📊 诊断数据
  [RAG、LLM、Token 等统计信息]

🔄 门 RAG检索 → LLM思考生成中...
  ▼ [展开]
  
  💭 思考过程 (45s)
  ┌─────────────────────────────────────┐
  │ 用户要求生成一个10×8米的欧式别墅的门│
  │ 组件。根据系统提示，我只需要生成... │
  │ （实时流式展示）                   │
  └─────────────────────────────────────┘
```

### 关键特征
1. ✅ **实时流式**：思考内容逐字符/逐句显示，不是等完成后一次性显示
2. ✅ **按节点分组**：skeleton、door、window、roof 等节点各自独立的思考内容
3. ✅ **可折叠展开**：点击节点标题可以展开/收起思考内容
4. ✅ **深色主题**：类似图片中的深色背景样式
5. ✅ **时间估算**：显示思考耗时（基于字符数估算）

## 故障排查

### 问题1：思考内容不是实时显示，而是等完成后一次性显示
**原因**：后端流式传输有问题，或者前端没有正确监听 `nodeThinkingMap` 变化

**解决**：
1. 检查后端日志，确认 `thinking_delta` 消息是逐 delta 发送的
2. 检查浏览器控制台 WebSocket 消息，应该看到多条 `thinking_delta` 消息
3. 检查前端是否正确添加了 `watch(() => agentStore.nodeThinkingMap.size, ...)`

### 问题2：思考内容为空或不显示
**原因**：`thinking_mode` 或 `precision_mode` 未开启，或 `node` 参数传递有误

**解决**：
1. 确保精密模式开关已开启
2. 检查后端发送的消息是否包含 `node` 字段
3. 检查 `getNodeThinking()` 函数是否正确读取 Map

### 问题3：样式不对，没有深色背景
**原因**：CSS 样式未正确应用

**解决**：
1. 检查 `.node-thinking-stream` 样式是否正确添加
2. 刷新浏览器缓存（Ctrl+Shift+R）
3. 检查浏览器控制台是否有 CSS 错误

## 技术细节

### 数据流
```
后端 LLM stream
  ↓
后端 on_reasoning_delta(node_name, delta)
  ↓
WebSocket 发送: { type: "thinking_delta", node: "skeleton", delta: "..." }
  ↓
前端 agentBridge 接收
  ↓
前端 agentStore.appendThinkingContent(delta, "skeleton")
  ↓
前端 nodeThinkingMap.set("skeleton", { node: "skeleton", content: "...", status: "thinking" })
  ↓
前端 Vue 响应式更新
  ↓
UI 展示实时思考内容
```

### 性能优化
- 使用 `Map` 而非对象来存储节点思考内容，性能更好
- 使用 `deep: true` 监听 Map 变化
- 限制思考内容最大高度（320px），超出滚动显示

### 与图片样式对比
- ✅ 深色背景：`#0d0d1a`
- ✅ 边框：`1px solid #1e1e35`
- ✅ 等宽字体：`Consolas, Menlo, Monaco`
- ✅ 文字颜色：`#a8a8c0`
- ✅ 行高：`1.6`
- ✅ 滚动条：`max-height: 320px; overflow-y: auto`
- ✅ 动画效果：`thinkingPulse` 淡入效果
