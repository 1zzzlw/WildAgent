# WILD 建筑编辑器前端

基于 Vue 3 + Vite + TypeScript + Three.js 的 AI 辅助参数化 3D 建筑编辑器。

## 项目结构

```
src/
├── main.ts                    # 应用入口
├── App.vue                    # 根组件
├── style.css                  # 全局样式
├── stores/                    # Pinia 状态管理
│   ├── sceneStore.ts         # 场景文档状态
│   ├── selectionStore.ts     # 选择状态
│   ├── historyStore.ts       # 撤销重做历史
│   ├── agentStore.ts         # Agent 对话状态
│   └── uiStore.ts            # UI 布局状态
├── types/                     # TypeScript 类型定义
│   ├── blueprint.ts          # Blueprint 核心类型
│   ├── scene.ts              # 场景文档类型
│   ├── scenePatch.ts         # ScenePatch 协议
│   └── agent.ts              # Agent 通信协议
├── wild/                      # WILD 核心逻辑
│   ├── scenePatch.ts         # Patch 应用逻辑
│   ├── sceneValidator.ts     # Blueprint 校验
│   ├── sceneSummary.ts       # 场景摘要生成
│   ├── idFactory.ts          # ID 生成工具
│   └── blueprintDefaults.ts  # 默认值定义
├── agent/                     # Agent 通信层
│   ├── agentBridge.ts        # WebSocket 桥接
│   └── protocol.ts           # 协议工具函数
├── renderer/                  # 3D 渲染适配层（待实现）
│   ├── wildCoreAdapter.ts    # wild-core 适配器
│   ├── renderEntity.ts       # 渲染实体转换
│   ├── meshDataToGeometry.ts # MeshData -> Three.js
│   ├── materialAdapter.ts    # 材质转换
│   └── picking.ts            # 拾取逻辑
├── components/
│   ├── layout/               # 布局组件
│   │   ├── EditorTopBar.vue  # 顶部工具栏
│   │   ├── LeftPanel.vue     # 左侧面板容器
│   │   ├── RightPanel.vue    # 右侧面板容器
│   │   └── BottomPanel.vue   # 底部面板容器
│   ├── viewport/             # 视口组件
│   │   └── CanvasViewport.vue # Three.js 渲染视口
│   └── panels/               # 功能面板
│       ├── SceneTree.vue     # 场景结构树
│       ├── BlockLibrary.vue  # 构件库
│       ├── PropertyPanel.vue # 属性编辑面板
│       ├── ValidationPanel.vue # 校验结果面板
│       └── AIChatPanel.vue   # AI 对话面板
├── services/                  # API 服务（待实现）
│   ├── sceneApi.ts           # 场景 REST API
│   └── fileExport.ts         # 文件导出
└── utils/
    └── common.ts             # 通用工具函数
```

## 核心架构

### 状态管理

采用 Pinia 管理应用状态：

- **sceneStore**: 当前场景文档、Blueprint、重建结果、校验结果
- **selectionStore**: 选中的构件、hover 状态
- **historyStore**: 撤销/重做历史
- **agentStore**: AI 对话消息、WebSocket 连接状态、待确认的 patch
- **uiStore**: 面板显示状态、尺寸

### ScenePatch 协议

所有编辑操作（用户手动 + Agent 生成）统一转换为 `ScenePatch`：

```typescript
interface ScenePatch {
  type: 'scene_patch'
  patch_id: string
  base_revision: number
  source: 'user' | 'agent' | 'system'
  mode: 'apply' | 'proposal'
  requires_confirmation: boolean
  operations: SceneOperation[]
  summary?: string
}
```

支持的操作类型：
- `add_element`: 添加构件
- `update_element`: 修改构件参数
- `remove_element`: 删除构件
- `upsert_material`: 添加/更新材质
- `add_template` / `update_template` / `remove_template`: 模板操作
- `add_instance`: 添加实例
- `add_placement`: 添加批量放置
- `set_behaviors`: 设置行为
- `set_editor_meta`: 设置编辑器元数据

### 数据流

```
用户操作 / Agent 建议
  ↓
ScenePatch
  ↓
sceneStore.applyPatch()
  ↓
应用到 Blueprint 副本
  ↓
校验 Blueprint
  ↓
wild-core 重建 (TODO)
  ↓
Three.js 渲染
```

## 开发命令

安装依赖（需要你手动执行）：

```bash
npm install
```

启动开发服务器：

```bash
npm run dev
```

构建生产版本：

```bash
npm run build
```

## 需要安装的依赖

```bash
npm install pinia three
npm install -D @types/three
```

或者使用 package.json 中已更新的依赖版本直接安装。

## 待实现功能

### Phase 1: 渲染引擎接入
- [ ] 实现 `renderer/wildCoreAdapter.ts`
- [ ] 接入 wild-core 的 `parseBlueprint` 和 `reconstructEntity`
- [ ] 实现 `MeshData` 到 `THREE.BufferGeometry` 转换
- [ ] 实现材质转换
- [ ] 实现场景重建和渲染

### Phase 2: 交互增强
- [ ] 实现 3D 拾取（点击选中构件）
- [ ] 实现选中高亮效果
- [ ] 实现 Transform Gizmo（平移、旋转、缩放）
- [ ] 优化属性面板（支持更多构件类型）

### Phase 3: Agent 集成
- [ ] 实现 WebSocket Agent 通信
- [ ] 实现 Agent 流式响应显示
- [ ] 实现 Patch 确认 UI
- [ ] 实现 Agent 错误处理和重试

### Phase 4: 保存和导出
- [ ] 实现本地 .wild 文件导入导出
- [ ] 实现后端场景保存 API 对接
- [ ] 实现自动保存
- [ ] 实现场景版本管理

## 技术栈

- **Vue 3**: 组合式 API + TypeScript
- **Vite**: 构建工具
- **Pinia**: 状态管理
- **Three.js**: 3D 渲染
- **WebSocket**: Agent 实时通信

## 关键设计决策

1. **保留 wild-core 引擎**: 不重新实现几何算法，只做适配层
2. **统一 Patch 协议**: 用户操作和 Agent 建议都转成 ScenePatch
3. **前端主导校验**: 后端 Agent 生成的 patch 由前端最终校验和应用
4. **确定性渲染**: 同一 Blueprint 永远产生相同的渲染结果
5. **.wild 是唯一源文件**: 不依赖数据库或其他状态存储
