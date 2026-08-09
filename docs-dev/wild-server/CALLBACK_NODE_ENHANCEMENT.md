# Callback Node 思考内容流式传输与重试次数显示

## 问题背景

用户指出：
1. **Merge 节点**：不调用 LLM（只是数据合并）— ✅ 正确，无需思考内容
2. **Validate 节点**：不调用 LLM（只是校验工具）— ✅ 正确，无需思考内容
3. **Callback 节点**：**调用 LLM 但缺少流式思考支持** — ❌ 需要修复
4. **前端未显示回调重试次数** — ❌ 需要修复

## 解决方案

### 1. 后端修改

#### callback_node.py
- ✅ 添加 `thinking_mode` 和 `on_reasoning_delta` 参数支持
- ✅ 修改为使用流式 LLM 调用 (`llm.astream`)
- ✅ 实时捕获 `reasoning_content` delta 并通过回调转发
- ✅ 回调时附带节点名称 "callback"

```python
# 流式调用：实时推送思考内容
async for chunk in llm.astream(messages):
    if hasattr(chunk, "additional_kwargs"):
        reasoning_delta = chunk.additional_kwargs.get("reasoning_content", "")
        if reasoning_delta:
            reasoning += reasoning_delta
            await on_reasoning_delta("callback", reasoning_delta)
```

#### ws_agent.py
- ✅ Callback 节点消息已包含重试次数：`f"callback:done:修正完成 (第{retry_count}次)"`
- ✅ 在 `session_metrics` 中添加 `retry_count` 和 `max_retries` 字段

```python
await send_debug("session_metrics", {
    # ... 其他字段 ...
    "retry_count": final_state.get("retry_count", 0),
    "max_retries": final_state.get("max_retries", 3),
    "status": final_state.get("status", "?"),
})
```

### 2. 前端修改

#### types/agent.ts
- ✅ 在 `SessionMetrics` 接口中添加 `retry_count?` 和 `max_retries?` 字段
- ✅ 添加 `suggested_components?` 字段（骨架节点建议的组件列表）

```typescript
export interface SessionMetrics {
  // ... 其他字段 ...
  retry_count?: number
  max_retries?: number
  status: string
}
```

#### AIChatPanel.vue
- ✅ 在性能汇总区域添加"回调重试"指标
- ✅ 显示格式：`retry_count/max_retries 次`（例如："1/3 次"）
- ✅ 仅在 `retry_count !== undefined` 时显示（避免初始状态显示 0/3）

```vue
<div v-if="agentStore.sessionMetrics.retry_count !== undefined" class="metric-item">
  <span class="metric-label">回调重试</span>
  <span class="metric-value">{{ agentStore.sessionMetrics.retry_count }}/{{ agentStore.sessionMetrics.max_retries || 3 }}次</span>
</div>
```

## 测试验证

### 测试文件
创建 `test_callback_thinking.py` 用于验证：
1. ✅ callback_node 是否正确启用思考模式
2. ✅ callback_node 是否实时推送思考内容 delta
3. ✅ 前端是否正确显示 callback 节点的思考内容
4. ✅ 前端是否正确显示回调重试次数

### 运行测试
```bash
cd wild-server
.\.venv\Scripts\activate
python test_callback_thinking.py
```

## 显示效果

### 精密面板 - 节点卡片
```
🔬 精密模式 — 实时节点进度

[callback] 修正 > ▼
  💭 思考过程 (估算 3s)
    [实时流式展示 callback 节点的思考内容...]
  
  📝 完整思考记录
    [LLM 完整思考内容]
  
  📊 诊断数据
    RAG 上下文: 2000字 / 150ms
    LLM 输出: 800字 / 5000ms
    ...
```

### 性能汇总
```
📊 性能汇总
- 活跃节点: 5/14
- 总 Token: 15,234
- RAG 耗时: 850ms
- LLM 耗时: 23,400ms
- 组件总数: 12个
- 校验: 12步 (2错)
- 回调重试: 1/3次    ← 新增显示
```

## 架构说明

### LangGraph 节点分类

1. **有 LLM 调用 + 思考内容的节点**（需要流式支持）
   - ✅ skeleton_node（骨架规划）
   - ✅ base_component_node（11 种组件生成）
   - ✅ callback_node（回调修正）

2. **无 LLM 调用的节点**（不需要思考内容）
   - ✅ merge_node（数据合并）
   - ✅ validate_node（工具校验）

### 思考内容传输路径

```
callback_node.py
  └─> llm.astream() 捕获 reasoning_content delta
      └─> on_reasoning_delta("callback", delta)
          └─> ws_agent.py: send_thinking_delta()
              └─> WebSocket: thinking_delta 消息 (含 node="callback")
                  └─> agentBridge.ts
                      └─> agentStore.appendThinkingContent(delta, "callback")
                          └─> nodeThinkingMap.set("callback", {content, status})
                              └─> AIChatPanel.vue: 实时显示
```

## 相关文件

### 后端
- `wild-server/app/agent/nodes/callback_node.py` — 回调节点实现
- `wild-server/app/api/ws_agent.py` — WebSocket 消息处理
- `wild-server/app/agent/graph_state.py` — State 定义

### 前端
- `wild-web/src/types/agent.ts` — 类型定义
- `wild-web/src/stores/agentStore.ts` — Store 管理
- `wild-web/src/components/panels/AIChatPanel.vue` — UI 显示

### 测试
- `wild-server/test_callback_thinking.py` — 回调节点测试

## 下一步

1. ✅ **测试骨架节点新 Prompt** — 验证是否正确丰富用户需求，不再产生"不要生成屋顶"的困惑
2. ✅ **测试完整流程** — 使用 "生成一个欧式别墅" 等测试用例验证整体效果
3. ✅ **观察回调机制** — 故意制造错误，验证 callback 节点是否正确触发和显示
4. ⬜ **优化知识库分配** — 确保每个节点调用正确的知识库路径

## 总结

现在所有调用 LLM 的节点（skeleton、11 种组件、callback）都支持流式思考内容实时显示，并且前端性能汇总区域会显示回调重试次数，用户可以清晰看到系统的修正尝试情况。
