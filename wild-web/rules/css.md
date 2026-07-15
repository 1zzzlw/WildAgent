# WILD 编辑器 CSS 样式规范

本文档定义 WILD 建筑编辑器的 CSS 样式规范，确保整个项目视觉风格统一、代码可维护。

## 设计理念

### 核心原则

1. **专业编辑器风格**: 参考 VS Code 深色主题
2. **简洁优雅**: 避免过度装饰，注重功能性
3. **一致性**: 所有组件遵循相同的设计语言
4. **响应式**: 适配不同屏幕尺寸
5. **高对比度**: 确保文本可读性

---

## 颜色系统

### 主题色板

```css
/* 背景色 */
--bg-primary: #1e1e1e        /* 主背景 */
--bg-secondary: #252526      /* 次级背景（面板） */
--bg-tertiary: #2d2d30       /* 三级背景（标题栏、输入框） */
--bg-hover: #2a2d2e          /* 悬停背景 */
--bg-active: #3e3e42         /* 激活/按下背景 */

/* 边框色 */
--border-default: #3e3e42    /* 默认边框 */
--border-focus: #007acc      /* 聚焦边框 */
--border-hover: #4e4e52      /* 悬停边框 */

/* 文本色 */
--text-primary: #cccccc      /* 主文本 */
--text-secondary: #888888    /* 次要文本 */
--text-disabled: #666666     /* 禁用文本 */
--text-header: #ffffff       /* 标题文本 */

/* 强调色 */
--accent-blue: #007acc       /* 蓝色（聚焦、链接） */
--accent-blue-dark: #094771  /* 深蓝（选中背景） */
--accent-blue-hover: #1177bb /* 蓝色悬停 */

/* 状态色 */
--success: #4ec9b0           /* 成功/正确 */
--warning: #dcdcaa           /* 警告 */
--error: #f48771             /* 错误 */
--info: #0e639c              /* 信息 */

/* 功能色 */
--dirty-indicator: #f48771   /* 未保存标记 */
```

### 颜色使用规范

| 场景 | 颜色 | 示例 |
|---|---|---|
| 主背景 | `#1e1e1e` | body, canvas viewport |
| 面板背景 | `#252526` | 左右侧面板 |
| 标题栏背景 | `#2d2d30` | 顶部工具栏、面板标题 |
| 边框 | `#3e3e42` | 所有边框 |
| 主文本 | `#cccccc` | 正文内容 |
| 次要文本 | `#888888` | 提示、时间戳、类型标签 |
| 选中背景 | `#094771` | 场景树选中项 |
| 悬停背景 | `#2a2d2e` 或 `#3e3e42` | 按钮、列表项悬停 |
| 聚焦边框 | `#007acc` | 输入框聚焦 |
| 成功状态 | `#4ec9b0` | 校验通过 |
| 错误状态 | `#f48771` | 错误提示、删除按钮 |

---

## 布局规范

### 间距系统

```css
/* 间距单位（建议使用 4 的倍数） */
--space-xs: 4px
--space-sm: 8px
--space-md: 12px
--space-lg: 16px
--space-xl: 24px
--space-xxl: 32px
```

### 常用间距

| 用途 | 值 |
|---|---|
| 组件内边距（小） | `8px` |
| 组件内边距（中） | `12px` |
| 组件内边距（大） | `16px` 或 `24px` |
| 组件间距 | `8px` 或 `12px` |
| 面板内边距 | `8px` 或 `12px` |
| 标题栏内边距 | `8px 12px` |

### 高度规范

| 元素 | 高度 |
|---|---|
| 顶部工具栏 | `48px` |
| 面板标题栏 | `36px` |
| 按钮（标准） | `32px` |
| 按钮（小型） | `24px` |
| 输入框 | `24px` 或 `32px` |

### 面板尺寸

| 面板 | 默认宽度/高度 |
|---|---|
| 左侧面板 | `280px` |
| 右侧面板 | `320px` |
| 底部面板 | `240px` |

---

## 字体规范

### 字体族

```css
/* 系统字体栈 */
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
  'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
  sans-serif;

/* 等宽字体（代码、数值） */
font-family: ui-monospace, Consolas, monospace;
```

### 字体大小

| 用途 | 大小 | 行高 |
|---|---|---|
| 正文 | `13px` | `1.5` |
| 小字 | `11px` 或 `12px` | `1.4` |
| 标题 | `13px`（加粗） | - |
| 工具栏按钮 | `13px` | - |
| 图标 | `14px` ~ `24px` | `1` |

### 字重

| 用途 | 字重 |
|---|---|
| 正文 | `400` (normal) |
| 标题 | `500` (medium) |
| 强调 | `500` 或 `600` |

---

## 组件样式规范

### 按钮

#### 标准按钮

```css
.toolbar-btn {
  height: 32px;
  padding: 0 12px;
  background: transparent;
  border: 1px solid #3e3e42;
  color: #cccccc;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
  transition: all 0.15s;
}

.toolbar-btn:hover:not(:disabled) {
  background: #3e3e42;
  border-color: #4e4e52;
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

#### 主要操作按钮

```css
.primary-btn {
  background: #0e639c;
  border: none;
  color: #ffffff;
}

.primary-btn:hover:not(:disabled) {
  background: #1177bb;
}
```

#### 危险操作按钮

```css
.danger-btn {
  background: transparent;
  border: 1px solid #f48771;
  color: #f48771;
}

.danger-btn:hover:not(:disabled) {
  background: rgba(244, 135, 113, 0.1);
}
```

### 输入框

```css
input[type="text"],
input[type="number"],
textarea,
select {
  height: 24px;
  padding: 0 8px;
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #cccccc;
  font-size: 12px;
  border-radius: 2px;
  font-family: inherit;
}

input:focus,
textarea:focus,
select:focus {
  outline: none;
  border-color: #007acc;
}

input[readonly],
textarea[readonly] {
  opacity: 0.6;
  cursor: not-allowed;
}
```

### 面板

```css
.panel {
  background: #252526;
  border: 1px solid #3e3e42; /* 根据位置调整 border 方向 */
  display: flex;
  flex-direction: column;
}

.panel-header {
  height: 36px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
  align-items: center;
  padding: 0 12px;
}

.panel-title {
  font-size: 13px;
  color: #cccccc;
  font-weight: 500;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
```

### 标签页

```css
.panel-tabs {
  height: 36px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
}

.tab {
  flex: 1;
  background: transparent;
  border: none;
  color: #cccccc;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.tab:hover {
  background: #3e3e42;
}

.tab.active {
  background: #252526;
  color: #ffffff;
}
```

### 列表项

```css
.list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 3px;
  font-size: 13px;
  transition: all 0.15s;
}

.list-item:hover {
  background: #2a2d2e;
}

.list-item.selected {
  background: #094771;
}
```

### 图标

```css
.icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}
```

---

## 过渡和动画

### 标准过渡

```css
/* 所有交互元素使用统一过渡时间 */
transition: all 0.15s;

/* 或者单独指定属性 */
transition: background 0.15s, border-color 0.15s;
```

### 加载动画

```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-icon {
  animation: spin 1s linear infinite;
}
```

### 淡入淡出

```css
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.fade-in {
  animation: fadeIn 0.3s ease-in;
}
```

---

## 滚动条样式

```css
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

::-webkit-scrollbar-track {
  background: #1e1e1e;
}

::-webkit-scrollbar-thumb {
  background: #424242;
  border-radius: 5px;
}

::-webkit-scrollbar-thumb:hover {
  background: #4e4e4e;
}
```

---

## 布局模式

### Flex 布局

#### 水平居中

```css
.flex-center {
  display: flex;
  align-items: center;
  justify-content: center;
}
```

#### 垂直布局

```css
.flex-column {
  display: flex;
  flex-direction: column;
}
```

#### 水平分布

```css
.flex-between {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
```

### Grid 布局

```css
.block-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
```

---

## 响应式设计

### 媒体查询断点

```css
/* 小屏幕（平板） */
@media (max-width: 1024px) {
  /* 调整字体、间距 */
}

/* 移动设备 */
@media (max-width: 768px) {
  /* 调整布局、隐藏次要内容 */
}
```

### 响应式原则

1. 优先保证桌面端体验（编辑器主要使用场景）
2. 移动端简化功能，保留核心操作
3. 使用相对单位（%）而非固定像素（px）设置面板宽度

---

## 特殊状态样式

### 空状态

```css
.empty-state {
  padding: 24px;
  text-align: center;
  color: #666666;
  font-size: 13px;
}
```

### 禁用状态

```css
.disabled,
:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

### 加载状态

```css
.loading {
  opacity: 0.6;
  pointer-events: none;
}
```

### Dirty 状态（未保存）

```css
.dirty-indicator {
  color: #f48771;
  margin-left: 4px;
}
```

---

## 消息和提示

### 成功消息

```css
.message-success {
  padding: 8px 12px;
  background: rgba(78, 201, 176, 0.15);
  border-left: 3px solid #4ec9b0;
  color: #4ec9b0;
  border-radius: 3px;
}
```

### 警告消息

```css
.message-warning {
  padding: 8px 12px;
  background: rgba(220, 220, 170, 0.15);
  border-left: 3px solid #dcdcaa;
  color: #dcdcaa;
  border-radius: 3px;
}
```

### 错误消息

```css
.message-error {
  padding: 8px 12px;
  background: rgba(244, 135, 113, 0.15);
  border-left: 3px solid #f48771;
  color: #f48771;
  border-radius: 3px;
}
```

---

## 组件间距规范

### 工具栏

```css
.top-bar {
  height: 48px;
  padding: 0 12px;
  gap: 16px; /* 工具栏组之间 */
}

.toolbar-section {
  display: flex;
  gap: 4px; /* 按钮之间 */
}
```

### 表单

```css
.property-section {
  margin-bottom: 16px; /* 表单组之间 */
}

.property-row {
  margin-bottom: 8px; /* 表单项之间 */
  gap: 8px;            /* 标签和输入框之间 */
}

.property-row label {
  flex: 0 0 80px;      /* 固定标签宽度 */
}
```

### 面板

```css
.panel-content {
  padding: 8px;        /* 面板内边距 */
}

.tree-content,
.library-content {
  padding: 4px;        /* 列表容器内边距 */
}
```

---

## 最佳实践

### 1. 使用 scoped 样式

```vue
<style scoped>
/* 所有组件样式应该使用 scoped，避免全局污染 */
</style>
```

### 2. 命名规范

- **BEM 命名法**（可选）: `.block__element--modifier`
- **语义化命名**: 使用描述性的类名
- **避免过度嵌套**: 最多 3 层嵌套

### 3. CSS 属性顺序

推荐顺序：

```css
.selector {
  /* 1. 布局 */
  display: flex;
  position: relative;
  flex-direction: column;
  
  /* 2. 盒模型 */
  width: 100%;
  height: 48px;
  padding: 8px 12px;
  margin: 0;
  
  /* 3. 边框 */
  border: 1px solid #3e3e42;
  border-radius: 3px;
  
  /* 4. 背景 */
  background: #252526;
  
  /* 5. 文本 */
  color: #cccccc;
  font-size: 13px;
  text-align: center;
  
  /* 6. 其他 */
  cursor: pointer;
  transition: all 0.15s;
}
```

### 4. 避免魔术数字

不好的写法：
```css
.panel {
  height: 237px; /* 这个数字从哪来的？ */
}
```

好的写法：
```css
.panel {
  height: calc(100vh - 48px - 36px); /* 视口高度 - 顶栏 - 标题栏 */
}
```

### 5. 复用 CSS 变量

```css
/* 定义变量 */
:root {
  --panel-padding: 8px;
  --border-radius: 3px;
}

/* 使用变量 */
.panel {
  padding: var(--panel-padding);
  border-radius: var(--border-radius);
}
```

### 6. 避免 !important

除非绝对必要，不要使用 `!important`。如果必须使用，添加注释说明原因。

---

## 常见组件模板

### 面板组件

```vue
<template>
  <div class="my-panel">
    <div class="panel-header">
      <span class="panel-title">标题</span>
    </div>
    <div class="panel-content">
      <!-- 内容 -->
    </div>
  </div>
</template>

<style scoped>
.my-panel {
  background: #252526;
  border: 1px solid #3e3e42;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  height: 36px;
  background: #2d2d30;
  border-bottom: 1px solid #3e3e42;
  display: flex;
  align-items: center;
  padding: 0 12px;
}

.panel-title {
  font-size: 13px;
  color: #cccccc;
  font-weight: 500;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
</style>
```

### 列表组件

```vue
<template>
  <div class="list-container">
    <div
      v-for="item in items"
      :key="item.id"
      :class="['list-item', { selected: isSelected(item.id) }]"
      @click="handleSelect(item.id)"
    >
      <span class="item-icon">{{ item.icon }}</span>
      <span class="item-label">{{ item.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.list-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 3px;
  font-size: 13px;
  transition: all 0.15s;
}

.list-item:hover {
  background: #2a2d2e;
}

.list-item.selected {
  background: #094771;
}

.item-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.item-label {
  flex: 1;
}
</style>
```

### 表单组件

```vue
<template>
  <div class="form-section">
    <div class="section-title">表单标题</div>
    <div class="form-row">
      <label>字段名</label>
      <input type="text" v-model="value" />
    </div>
  </div>
</template>

<style scoped>
.form-section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: #888888;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.form-row label {
  flex: 0 0 80px;
  font-size: 12px;
}

.form-row input {
  flex: 1;
  height: 24px;
  padding: 0 8px;
  background: #1e1e1e;
  border: 1px solid #3e3e42;
  color: #cccccc;
  font-size: 12px;
  border-radius: 2px;
}

.form-row input:focus {
  outline: none;
  border-color: #007acc;
}
</style>
```

---

## 调试技巧

### 1. 边框调试

```css
/* 临时添加，帮助查看元素边界 */
* {
  outline: 1px solid red;
}
```

### 2. 使用浏览器开发工具

- Chrome DevTools: Ctrl+Shift+C 选择元素
- 查看计算后的样式
- 实时修改样式测试效果

### 3. CSS 变量查看

```javascript
// 控制台查看 CSS 变量值
getComputedStyle(document.documentElement).getPropertyValue('--bg-primary')
```

---

## 性能优化

### 1. 避免复杂选择器

不好的写法：
```css
.panel > .content > div > ul > li > a {
  color: red;
}
```

好的写法：
```css
.nav-link {
  color: red;
}
```

### 2. 使用 transform 而非 position

```css
/* 性能更好 */
.element {
  transform: translateX(10px);
}

/* 避免 */
.element {
  left: 10px;
}
```

### 3. 避免触发重排

避免频繁修改这些属性：
- width, height
- margin, padding
- border
- position
- display

优先使用：
- transform
- opacity

---

## 参考资源

- [VS Code 主题颜色](https://code.visualstudio.com/api/references/theme-color)
- [MDN CSS 文档](https://developer.mozilla.org/zh-CN/docs/Web/CSS)
- [CSS Tricks](https://css-tricks.com/)

---

**最后更新**: 2026-07-14  
**版本**: 1.0  
**维护者**: 前端团队
