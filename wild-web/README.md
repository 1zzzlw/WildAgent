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

所有编辑操作（用户手动 + Agent 生成）统一转换为 `ScenePatch`。这是编辑器最核心的设计——不管修改来自拖拽、属性面板还是 AI 对话，都走同一条管道。

#### 为什么需要统一格式

编辑器有两个修改来源，如果各用各的格式会杂乱且容易互相覆盖：

| 来源 | 场景 |
|---|---|
| 用户手动操作 | 拖拽添加构件、属性面板改参数、删除构件 |
| AI Agent 建议 | 用户说"加个凉亭"，Agent 生成一批构件 |

ScenePatch 把它们统一：**不管谁发起的修改，都转成同一种 patch，走同一个 `applyPatch()`**。

#### Patch 结构

```typescript
interface ScenePatch {
  type: 'scene_patch'
  patch_id: string            // 唯一标识，防重复
  base_revision: number       // 👈 基于哪个版本，这是版本控制的关键
  source: 'user' | 'agent' | 'system'
  mode: 'apply' | 'proposal'  // 直接应用 / 仅提案（需用户确认）
  requires_confirmation: boolean
  operations: SceneOperation[]
  summary?: string            // 给用户看的摘要
}
```

#### revision 版本控制机制（乐观锁）

`sceneStore` 维护一个 `revision` 计数器。每次成功应用 patch 后 +1。patch 的 `base_revision` 必须等于当前 `revision`，否则拒绝。

这跟 Git 的运作方式类似——你基于旧 commit 做了改动，push 时发现别人已经推了新的，你的 base 不对，就会被拒绝：

```
初始状态：revision = 5

T1：用户修改柱子高度
  → patch_A，base_revision = 5
  → applyPatch(patch_A) → 匹配 ✓ → 应用 → revision = 6

T2：Agent 基于旧状态生成了修改
  → patch_B，base_revision = 5
  → applyPatch(patch_B) → 当前 revision=6，patch 期望 5 → 拒绝 ✗
```

当前阶段（单用户本地编辑器）revision 冲突几乎不会发生。等到 Phase 3 用户和 Agent 同时操作场景时，这个机制就会真正发挥作用。

#### sceneStore.applyPatch() 完整流程

```typescript
async function applyPatch(patch: ScenePatch): Promise<boolean> {
  // 1. 检查 revision 是否匹配（乐观锁）
  if (patch.base_revision !== document.value.revision) {
    return false  // 拒绝，防止基于过期状态修改
  }

  // 2. 把 patch 应用到 Blueprint 深拷贝
  const newBlueprint = applyPatchToBlueprint(document.value.blueprint, patch)

  // 3. 运行 Blueprint 校验

  // 4. 成功后 revision + 1
  document.value.revision++

  // 5. 触发 wild-core 重建 → Three.js 渲染
  // 6. 记录 undo 快照
}
```

#### 11 种操作类型

| 操作 | 用途 |
|---|---|
| `add_element` | 添加构件（id + type + 参数） |
| `update_element` | 修改构件属性（id + changes 对象） |
| `remove_element` | 删除构件 |
| `upsert_material` | 添加/更新材质 |
| `add_template` | 添加模板（可复用的构件组合） |
| `update_template` | 修改模板 |
| `remove_template` | 删除模板 |
| `add_instance` | 添加模板实例 |
| `add_placement` | 批量放置（按规则生成多个构件） |
| `set_behaviors` | 设置行为脚本 |
| `set_editor_meta` | 设置编辑器元数据（不影响渲染） |

`applyPatchToBlueprint()` 遍历 operations 列表，对 Blueprint 深拷贝逐条执行——push 新元素、Object.assign 修改属性、delete 删除元素等。

#### 实际使用位置

| 位置 | 场景 | source | 状态 |
|---|---|---|---|
| [PropertyPanel.vue](src/components/panels/PropertyPanel.vue) | 属性面板改参数 | `'user'` | ✅ 已生效 |
| [BlockLibrary.vue](src/components/panels/BlockLibrary.vue) | 构件库点击添加构件 | `'user'` | ⚠️ 代码已接入，待验证 |
| [AIChatPanel.vue](src/components/panels/AIChatPanel.vue) | AI 增量修改建议 | `'agent'` | 🔜 预留（AI 尚无增量修改能力） |

> **注意**：AI 从零生成完整蓝图时**不走 ScenePatch**。后端保存 `.wild` 文件后，前端通过 HTTP 拉取 JSON，直接调用 `loadBlueprint()` 替换整个场景——跟本地导入 `.wild` 文件走的是同一个函数。ScenePatch 只用于增量修改，不会用于完整场景替换。

#### 辅助函数 createPatch()

```typescript
createPatch(
  baseRevision = 5,
  operations = [
    { op: 'add_element', element: { id: 'col_01', type: 'column', base: [3,0,4], height: 3.5 } }
  ],
  source = 'user',
  requiresConfirmation = false,
  summary?: '添加一根柱子'
)
// → 返回完整的 ScenePatch 对象，patch_id 自动生成
```

Agent 生成的 patch 会设置 `requires_confirmation = true` 和 `mode = 'proposal'`，前端在聊天面板展示预览，用户确认后才调用 `applyPatch()`。用户手动操作则直接应用，无需确认。

### 数据流

```
用户操作 / Agent 建议
  ↓
createPatch() → ScenePatch
  ↓
sceneStore.applyPatch(patch)
  ├─ 检查 base_revision 匹配
  ├─ applyPatchToBlueprint() → Blueprint 深拷贝 + operations 逐条应用
  ├─ 校验 Blueprint
  ├─ revision++
  ├─ wild-core.reconstructEntity()
  └─ Three.js 渲染刷新
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
