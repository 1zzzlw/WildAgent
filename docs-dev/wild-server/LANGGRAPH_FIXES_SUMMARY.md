# LangGraph 架构修复总结

## 问题 1：骨架节点 Prompt 设计错误 ✅ 已修复

### 问题描述
骨架节点的 Prompt 第一条规则说"**不要生成门、窗、屋顶**"，这导致大模型思考时产生困惑：
- 用户说"生成欧式别墅"
- 大模型想"别墅应该有屋顶啊"
- 但规则说"不要生成屋顶"
- 大模型在思考内容中反复纠结这个矛盾

### 根本原因
**没有理解 LangGraph 分层架构的设计意图**：

```
错误理解：
  骨架节点 → 生成完整建筑（包括门窗屋顶）
  
正确理解：
  骨架节点 → 理解建筑类型 + 丰富需求描述 + 生成基础结构 + 建议组件列表
  组件节点 → 根据建议列表并行生成各自的组件
```

### 修复方案

#### 1. 修改骨架节点 Prompt (`wild-server/app/agent/prompts.py`)

**旧 Prompt（错误）**:
```python
"""你是建筑骨架生成专家。只生成 walls、floors、columns、beams 等结构元素。

# 规则
1. **只生成骨架**：不要生成门、窗、屋顶或任何组合构件（geometry.components 为空数组）
...
"""
```

**新 Prompt（正确）**:
```python
"""你是建筑规划专家。你的任务是理解用户需求，规划建筑结构，并生成骨架。

# 你的任务

1. **理解建筑类型**：根据用户描述（如"欧式别墅"、"中式庭院"），从知识库中找到对应的建筑特征
2. **丰富需求描述**：基于建筑类型，补充细节描述，例如：
   - 欧式别墅 → 应有对称布局、大门、落地窗、四坡屋顶、柱廊
   - 中式庭院 → 应有院墙、月亮门、木窗、坡屋顶、飞檐
3. **生成骨架结构**：只生成 walls（墙）、floors（楼板）、columns（柱）、beams（梁）
4. **不生成组件**：不要生成 door（门）、window（窗）、roof（屋顶）等，这些由后续专用节点负责

# 输出格式要求
你必须输出完整的 Blueprint JSON，但 `geometry.components` **必须为空数组**。
...
"""
```

关键改进：
- ✅ 明确说明"理解建筑类型"和"丰富需求描述"
- ✅ 举例说明如何丰富（"欧式别墅 → 应有大门、落地窗、四坡屋顶"）
- ✅ 清楚解释为什么不生成组件（"由后续专用节点负责"）
- ✅ 避免产生"为什么不能生成屋顶"的困惑

#### 2. 优化骨架节点 RAG 调用 (`wild-server/app/agent/nodes/skeleton_node.py`)

**旧代码（过于宽泛）**:
```python
queries = [
    SpecQuery(user_message, {"doc_type": "building_type"}),
    SpecQuery(user_message, {"doc_type": "recipe"}),
    SpecQuery(user_message, {"entity_type": "structural_component"}),
    SpecQuery(user_message, {"entity_type": "wall"}),  # 太具体了
]
spec_text = agent_service.spec_loader.load_many(queries, per_query=1)
```

**新代码（专注建筑类型）**:
```python
queries = [
    # 主查询：建筑类型特征（如"欧式别墅"、"中式庭院"）
    SpecQuery(user_message, {"doc_type": "building_type"}),
    # 补充：建筑配方和结构组件通用规范
    SpecQuery(user_message, {"doc_type": "recipe"}),
    SpecQuery("墙体 楼板 柱子 梁", {"entity_type": "structural_component"}),
]
spec_text = agent_service.spec_loader.load_many(queries, per_query=2)
```

改进：
- ✅ 专注于 `building_types/` 知识库（理解建筑类型特征）
- ✅ 使用通用查询"墙体 楼板 柱子 梁"而非具体的 user_message
- ✅ 增加 per_query 到 2，获取更丰富的建筑类型知识

#### 3. 知识库调用分工

| 节点类型 | 调用的知识库 | 目的 |
|---------|-------------|------|
| 骨架节点 | `building_types/`<br>`building_types/catalog/`<br>`structural_component` | 理解建筑类型特征<br>丰富需求描述<br>生成基础结构 |
| 门节点 | `components/door/`<br>`entity: door` | 门的详细规范<br>交互方式、尺寸规范 |
| 窗节点 | `components/window/`<br>`entity: window` | 窗的详细规范<br>窗棂、材质规范 |
| 屋顶节点 | `components/roof/`<br>`entity: roof` | 屋顶类型、坡度规范 |
| ... | ... | ... |

**这就是 LangGraph 的优势**：
- 每个节点独立调用知识库，缓解上下文压力
- 骨架节点不需要知道门的详细规范
- 门节点不需要知道建筑类型的特征
- 各司其职，减少 Token 消耗

---

## 问题 2：前端消息显示顺序错误 ✅ 已修复

### 问题描述
精密模式下，AI 回复消息显示在精密面板（思考内容）的**上面**，应该在**下面**。

期望顺序：
```
1. 用户消息："生成一个欧式别墅"
2. 🔬 精密模式面板（包含所有节点的思考内容）
   - 骨架节点 [展开] 💭 思考过程...
   - 门节点 [展开] 💭 思考过程...
   - ...
3. AI 回复："已生成欧式别墅（16元素 + 8组件）"
4. ✅ Blueprint 已加载到场景
```

实际顺序（错误）：
```
1. 用户消息
2. AI 回复 ← 错误！太早显示了
3. 精密模式面板
```

### 修复方案 (`wild-web/src/components/panels/AIChatPanel.vue`)

#### 1. 拆分消息显示逻辑

```vue
<!-- 精密模式：只显示用户消息 -->
<div v-if="agentStore.precisionMode">
  <div v-for="message in userMessagesOnly" :key="message.id">
    <!-- 用户消息 -->
  </div>
</div>

<!-- 非精密模式：显示所有消息 -->
<div v-else>
  <div v-for="message in agentStore.session.messages">
    <!-- 所有消息 -->
  </div>
</div>

<!-- 精密模式面板 -->
<div v-if="agentStore.precisionMode">
  <!-- 节点卡片 + 思考内容 -->
</div>

<!-- 精密模式：AI 回复和系统消息放到精密面板下方 -->
<div v-if="agentStore.precisionMode">
  <div v-for="message in nonUserMessages">
    <!-- AI 回复 + 系统消息 -->
  </div>
</div>
```

#### 2. 添加计算属性

```typescript
const userMessagesOnly = computed(() => {
  return agentStore.session.messages.filter(m => m.role === 'user')
})

const nonUserMessages = computed(() => {
  return agentStore.session.messages.filter(m => m.role !== 'user')
})
```

改进：
- ✅ 精密模式下，用户消息在最上面
- ✅ 精密面板在中间（包含所有节点的思考内容）
- ✅ AI 回复和系统消息在最下面
- ✅ 非精密模式保持原有顺序，不受影响

---

## 问题 3：前端流式思考展示 ✅ 已修复（之前完成）

### 问题描述
后端正确发送流式思考内容，但前端等待完成后一次性显示，而非实时流式展示。

### 修复方案
1. 在 `agentStore` 中添加 `nodeThinkingMap: Map<string, NodeThinking>`
2. 修改 `appendThinkingContent(delta, nodeName)` 支持按节点分组
3. WebSocket 消息处理传递 `message.node` 参数
4. UI 展示添加"💭 思考过程"区域，实时显示流式内容

详见：`wild-server/TEST_FRONTEND_THINKING.md`

---

## 完整的架构流程（正确版本）

```
用户输入: "生成一个10×8米的欧式别墅"
    ↓
【骨架节点】
  - RAG: 检索 building_types/ 知识库
    → "欧式别墅特征：对称布局、大门、落地窗、四坡屋顶、柱廊、石材外墙"
  - 思考: "用户要求欧式别墅，应该设计对称布局，预留大门入口位置、
          多个窗户位置、四坡屋顶..."
  - 输出: 
    1. 骨架结构（walls, floors, columns, beams）
    2. suggested_components: ['door', 'window', 'roof', 'balcony']
    3. skeleton_summary（包含墙体详细坐标供后续节点使用）
    ↓
【并行组件节点层】
  ┌─ 【门节点】(因为在建议列表中)
  │   - RAG: 检索 components/door/ 知识库
  │   - 思考: "欧式别墅大门通常是双开门，宽度1.8m，高度2.4m..."
  │   - 输出: door 组件 → 立即调用校验修复工具
  │
  ├─ 【窗节点】(因为在建议列表中)
  │   - RAG: 检索 components/window/ 知识库
  │   - 思考: "欧式落地窗，宽度1.5m，高度2.2m，从地面0.2m..."
  │   - 输出: window 组件 → 立即调用校验修复工具
  │
  ├─ 【屋顶节点】(因为在建议列表中)
  │   - RAG: 检索 components/roof/ 知识库
  │   - 思考: "欧式别墅用四坡屋顶(hip)，覆盖整个建筑..."
  │   - 输出: roof 元素 → 立即调用校验修复工具
  │
  ├─ 【阳台节点】(因为在建议列表中)
  │   - RAG: 检索 components/balcony/ 知识库
  │   - 输出: balcony 组件 → 立即调用校验修复工具
  │
  └─ 【其他节点】❌ 不在建议列表 → 跳过
      (railing, canopy, light, ramp, bay_window, cornice, chimney)
    ↓
【合并节点】
  - 将骨架 + 所有组件合并成完整 Blueprint
    ↓
【全局校验节点】
  - 校验结构完整性、引用完整性等
    ↓
【输出】
  - 保存 Blueprint 文件
  - 返回给前端
```

---

## 知识库调用优化总结

### 骨架节点（Skeleton Node）
**目标**: 理解建筑类型 + 规划结构

**RAG 查询**:
```python
SpecQuery(user_message, {"doc_type": "building_type"})      # 主查询
SpecQuery(user_message, {"doc_type": "recipe"})             # 配方
SpecQuery("墙体 楼板 柱子 梁", {"entity_type": "structural_component"})
```

**知识库路径**:
- `storage/knowledge_base/building_types/catalog/`
- `storage/knowledge_base/building_types/`
- `storage/knowledge_base/components/structural/`

**输出**:
- 墙体、楼板、柱子、梁的 JSON
- `suggested_components`: ['door', 'window', 'roof', ...]
- `skeleton_summary`: 墙体详细坐标信息

### 组件节点（Component Nodes）
**目标**: 生成具体组件

**RAG 查询**（以 door 为例）:
```python
SpecQuery(user_message, {"entity_type": "door"})
SpecQuery("door interaction opening", {"doc_type": "component"})
```

**知识库路径**:
- `storage/knowledge_base/components/door/`
- `storage/knowledge_base/components/opening/`

**输出**:
- door 组件的 JSON
- 立即调用 `validate_door_placement()` 校验
- 如有错误，调用 `fix_door_placement()` 修复

---

## 测试验证

### 1. 骨架节点 Prompt 测试
```bash
cd wild-server
.\.venv\Scripts\activate
python test_suggested_components.py
```

观察思考内容是否包含：
- ✅ "欧式别墅应有大门、落地窗、四坡屋顶、柱廊"
- ✅ 不再纠结"为什么不能生成屋顶"

### 2. 前端显示顺序测试
访问 `http://localhost:5173`，开启精密模式，输入"生成一个欧式别墅"

观察顺序：
1. ✅ 用户消息在最上面
2. ✅ 精密面板在中间（可展开各节点思考内容）
3. ✅ AI 回复在最下面
4. ✅ 系统消息在最下面

### 3. 流式思考测试
展开骨架节点卡片，观察"💭 思考过程"区域：
- ✅ 思考内容实时流式显示（逐句出现）
- ✅ 深色背景，等宽字体
- ✅ 可滚动查看完整内容

---

## 总结

### ✅ 已解决的问题
1. 骨架节点 Prompt 设计错误 → 重新设计，明确职责
2. RAG 知识库调用不合理 → 各节点独立调用专属知识库
3. 前端消息显示顺序错误 → 拆分用户消息和非用户消息
4. 流式思考展示（之前已完成）

### 🎯 架构优势
1. **职责清晰**: 骨架节点负责规划，组件节点负责实现
2. **知识隔离**: 每个节点只调用需要的知识库，缓解上下文压力
3. **流式展示**: 思考内容实时显示，用户体验更好
4. **智能建议**: 根据建筑类型自动建议需要的组件，避免无效计算

### 📝 关键设计原则
- 骨架节点：理解 + 规划 + 建议（不生成组件）
- 组件节点：根据建议 + 生成 + 校验（独立调用知识库）
- 前端展示：用户消息 → 精密面板 → AI 回复 → 系统消息
