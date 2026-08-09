# 思考内容展示 UI 重新设计 — 业界标准可折叠面板

## 设计目标

按照业界 AI 产品（如 ChatGPT、Claude 等）的标准，将思考内容展示改造为：

1. **半透明可折叠面板** — 位于正式回复上方，灰色背景降低视觉优先级
2. **图标化指示** — 使用大脑、齿轮、对话框图标提示"思考过程"
3. **逐行浮现动画** — 打字机效果实时生成，增强"模型正在思考"的临场感
4. **清晰的交互** — 折叠/展开箭头，默认展开便于观察，历史消息可手动折叠
5. **Markdown 渲染** — 思考内容支持完整 Markdown 格式化显示

## 视觉特征

### 1. 思考块容器 (.thought-block)
- 半透明背景：`rgba(255, 255, 255, 0.02)`
- 状态指示色：
  - 执行中：左侧蓝色边框 `#4ea1f3` + 蓝色半透明背景
  - 已完成：左侧绿色边框 `#4ec9b0`
  - 执行失败：左侧红色边框 `#f48771` + 红色半透明背景
  - 已跳过：灰色边框 `#555` + 降低透明度
- 悬停效果：背景和边框颜色微调，提供交互反馈
- 淡入动画：从上方滑入 + 透明度渐变

### 2. 思考块头部 (.thought-header)
```
[图标区] [节点名称 + 状态] [折叠箭头]
 28x28    flex:1            24x24
```
- **图标区**：圆角背景框 + Loading 动画或状态 emoji
- **元信息**：
  - 主标签：节点中文名称（如"骨架"、"门"、"窗"）
  - 副标签：状态描述（如"执行中..."、"已完成"）
  - 摘要信息：单行简要说明，超长省略号
- **折叠箭头**：Element Plus 的 ArrowRight/ArrowDown 图标

### 3. 推理过程区 (.reasoning-section)
```
┌─ 推理过程 ────────────────── 思考中... ─┐
│                                         │
│  [Markdown 渲染的思考内容]              │
│  - 支持代码块、列表、强调等格式         │
│  - 打字机效果实时浮现                   │
│  - 等宽字体 + 滚动条                    │
│                                         │
└─────────────────────────────────────────┘
```
- **标题栏**：图标 + 标题 + 状态徽章
- **状态徽章**：
  - 思考中：蓝色徽章 + 脉冲动画
  - 已完成：绿色徽章 + 无动画
- **内容区**：
  - Markdown-it 渲染，支持完整格式
  - 最大高度 400px，超出显示滚动条
  - 代码块深色背景高亮
  - 强调文本用主题色标注

### 4. 诊断信息区 (.diagnostics-section)
```
┌─ 执行诊断 ─────────────────────────────┐
│  ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │RAG 检索 │ │LLM 生成 │ │Token消耗│  │
│  │2000 字  │ │800 字   │ │15,234  │  │
│  │150ms    │ │5000ms   │ │↑8K ↓7K │  │
│  └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────┘
```
- 网格布局：自适应列数（min 140px）
- 卡片设计：半透明背景 + 悬停效果
- 数据标签：小写字母 + 大写标题
- 绿色数值：突出关键指标

### 5. 性能汇总卡片 (.metrics-card)
```
┌─ 📊 性能汇总 ────────────────────────────┐
│                                          │
│  节点执行 ················ 5/14 个      │
│  Token 消耗 ··············· 15,234      │
│  RAG 检索 ················· 850ms      │
│  LLM 生成 ················ 23,400ms    │
│  组件总数 ·················· 12 个      │
│  校验状态 ············· 12步 · 2错      │
│  回调重试 ················· 1/3 次     │
│                                          │
└──────────────────────────────────────────┘
```
- 渐变背景：蓝绿色渐变 + 高亮边框
- 行布局：标签左对齐，数值右对齐
- 分隔线：淡色底边分隔每行
- 等宽字体：数值使用 Consolas/Menlo

## 实现细节

### 前端组件更新

#### AIChatPanel.vue 模板
```vue
<div class="thought-block" :class="`status-${node.status}`">
  <!-- 头部：图标 + 标题 + 折叠按钮 -->
  <div class="thought-header" @click="toggleNodeExpand(node.name)">
    <div class="thought-icon">
      <el-icon v-if="node.status === 'running'" class="is-loading">
        <Loading />
      </el-icon>
      <span v-else>{{ statusEmoji(node.status) }}</span>
    </div>
    <div class="thought-meta">
      <div class="thought-title">
        <span class="thought-label">{{ node.label }}</span>
        <span class="thought-status">{{ getStatusLabel(node.status) }}</span>
      </div>
      <div class="thought-summary">{{ node.detail }}</div>
    </div>
    <div class="thought-toggle">
      <el-icon>
        <component :is="expandedNodes.has(node.name) ? 'ArrowDown' : 'ArrowRight'" />
      </el-icon>
    </div>
  </div>
  
  <!-- 内容：折叠动画 -->
  <transition name="thought-expand">
    <div v-if="expandedNodes.has(node.name)" class="thought-content">
      <!-- 推理过程 -->
      <div class="reasoning-section">
        <div class="reasoning-header">
          <el-icon class="reasoning-icon"><ChatDotRound /></el-icon>
          <span class="reasoning-title">推理过程</span>
          <span class="reasoning-badge" :class="{completed: node.status !== 'running'}">
            {{ node.status === 'running' ? '思考中...' : '已完成' }}
          </span>
        </div>
        <div class="reasoning-content typewriter" 
             v-html="renderMarkdown(getNodeThinking(node.name))">
        </div>
      </div>
      
      <!-- 诊断信息 -->
      <div class="diagnostics-section">
        <!-- ... 诊断卡片网格 ... -->
      </div>
    </div>
  </transition>
</div>
```

#### 脚本增强
```typescript
// 新增图标导入
import {
  ArrowDown, ArrowRight,      // 折叠箭头
  ChatDotRound,                // 推理过程图标
  DataAnalysis,                // 诊断图标
  DataLine,                    // 性能图标
} from '@element-plus/icons-vue'

// 新增状态标签函数
function getStatusLabel(status: string) {
  return { 
    done: '已完成', 
    skipped: '已跳过', 
    error: '执行失败', 
    running: '执行中...' 
  }[status] || status
}

// Markdown 渲染思考内容
function getNodeThinking(nodeName: string): string {
  const thinking = agentStore.nodeThinkingMap.get(nodeName)
  return thinking?.content || ''
}
```

### CSS 动画效果

#### 1. 思考块淡入动画
```css
@keyframes thoughtFadeIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

#### 2. 状态徽章脉冲
```css
@keyframes reasoningPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

#### 3. 打字机闪烁
```css
@keyframes typewriterBlink {
  from { opacity: 0.7; }
  to { opacity: 1; }
}
```

#### 4. 折叠展开过渡
```css
.thought-expand-enter-active,
.thought-expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}
```

## Markdown 渲染增强

### 支持的格式
- ✅ 标题（H1-H6）
- ✅ 段落和换行
- ✅ 列表（有序/无序）
- ✅ 代码块（语法高亮）
- ✅ 行内代码
- ✅ 强调（加粗/斜体）
- ✅ 链接
- ✅ 引用块
- ✅ 水平分隔线
- ✅ 表格

### 样式定制
```css
.reasoning-content :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 5px;
  border-radius: 3px;
  color: #ce9178;
}

.reasoning-content :deep(strong) {
  color: #4ec9b0;  /* 主题绿色高亮 */
  font-weight: 600;
}

.reasoning-content :deep(em) {
  color: #dcdcaa;  /* 黄色强调 */
}
```

## 用户体验优化

### 1. 默认展开策略
- 执行中的节点：自动展开，便于观察实时思考
- 已完成的节点：保持展开状态
- 历史消息：用户可手动折叠节省空间

### 2. 滚动行为
- 新内容出现时自动滚动到底部
- 用户手动滚动时暂停自动滚动（2秒后恢复）
- 思考内容超过 400px 显示局部滚动条

### 3. 响应式布局
- 诊断卡片网格：`repeat(auto-fit, minmax(140px, 1fr))`
- 性能汇总行：固定两列布局（标签 | 数值）
- 移动端优化：缩小字号和间距

### 4. 加载状态
- Loading 图标旋转动画
- "思考中..." 徽章脉冲效果
- 打字机效果：每次更新微闪

## 对比效果

### 改造前
```
🔬 精密模式 — 实时节点进度
────────────────────────────
✅ 骨架 25构件 | RAG 18000字...
  💭 思考过程 (3s)
    [纯文本块，无格式]
  📊 诊断数据
    RAG上下文: 2000字/150ms
    ...
────────────────────────────
```
- 界面拥挤，信息层级不清晰
- 纯文本显示，无法突出重点
- 缺少视觉反馈和动画

### 改造后
```
┌─────────────────────────────┐
│ [🔄] 骨架  执行中...      ▼ │
│                             │
│ ┌─ 推理过程 ─── 思考中... ─┐│
│ │ 根据用户需求"欧式别墅"： ││
│ │                          ││
│ │ 1. **建筑风格分析**      ││
│ │    - 需要大门、落地窗    ││
│ │    - 建议四坡屋顶       ││
│ │                          ││
│ │ 2. **组件规划**          ││
│ │    ```json              ││
│ │    ["door", "window"]   ││
│ │    ```                  ││
│ └─────────────────────────┘│
│                             │
│ ┌─ 执行诊断 ──────────────┐│
│ │ [RAG] [LLM] [Token]     ││
│ └─────────────────────────┘│
└─────────────────────────────┘
```
- 层次分明，专业美观
- Markdown 渲染，格式清晰
- 丰富动画，临场感强

## 技术栈

- **Vue 3** — Composition API + TypeScript
- **Element Plus** — 图标组件库
- **Markdown-it** — Markdown 渲染
- **Highlight.js** — 代码语法高亮
- **CSS3** — 动画和过渡效果

## 测试验证

### 启动测试
```bash
# 后端
cd wild-server
.\.venv\Scripts\activate
python main.py

# 前端
cd wild-web
npm run dev
```

### 测试场景
1. **骨架节点思考** — 输入："生成一个欧式别墅"
   - 验证思考内容实时流式显示
   - 验证 Markdown 格式正确渲染
   - 验证建议组件列表准确

2. **组件节点思考** — 查看门、窗等组件生成过程
   - 验证每个节点独立展示思考内容
   - 验证诊断数据正确显示
   - 验证折叠/展开交互流畅

3. **回调节点思考** — 故意制造错误触发 callback
   - 验证 callback 节点思考内容显示
   - 验证性能汇总显示回调重试次数
   - 验证修正过程完整记录

## 相关文件

### 前端
- `wild-web/src/components/panels/AIChatPanel.vue` — 主组件
- `wild-web/src/types/agent.ts` — 类型定义
- `wild-web/src/stores/agentStore.ts` — 状态管理

### 后端
- `wild-server/app/api/ws_agent.py` — WebSocket 通信
- `wild-server/app/agent/nodes/skeleton_node.py` — 骨架节点
- `wild-server/app/agent/nodes/base_component_node.py` — 组件节点
- `wild-server/app/agent/nodes/callback_node.py` — 回调节点

### 文档
- `CALLBACK_NODE_ENHANCEMENT.md` — 回调节点增强说明
- `THINKING_UI_REDESIGN.md` — 本文档

## 下一步优化

1. ✅ **基础样式完成** — 可折叠思考面板已实现
2. ✅ **Markdown 渲染** — 思考内容支持完整格式化
3. ✅ **动画效果** — 淡入、脉冲、打字机效果
4. ⬜ **移动端适配** — 响应式布局优化
5. ⬜ **主题切换** — 支持亮色/暗色模式
6. ⬜ **国际化** — 中英文界面切换

## 总结

按照业界 AI 产品标准重新设计了思考内容展示 UI：
- ✅ 半透明可折叠面板，视觉层次清晰
- ✅ 图标化指示，状态一目了然
- ✅ 打字机效果，实时流式展示
- ✅ Markdown 渲染，格式丰富美观
- ✅ 流畅动画，用户体验优秀

用户现在可以像使用 ChatGPT、Claude 等主流 AI 产品一样，清晰地观察 LangGraph 各节点的推理过程！
