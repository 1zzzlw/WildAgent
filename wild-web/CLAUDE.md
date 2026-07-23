# WildAgent 项目快速了解文档

## 项目概述

**WildAgent** 是一个 AI 辅助的参数化 3D 建筑编辑器。用户用自然语言描述建筑，系统自动生成 `.wild` 蓝图文件并实时渲染 3D 效果。

### 核心理念

不同于主流 AI 3D 生成工具（Meshy/Tripo）直接生成三角网格，WildAgent 采用：
- **AI 只填参数表**，不生成几何
- **数学引擎负责计算**，保证精确和可复现
- **产物是活参数文件**（几 KB），不是死网格文件（几十 MB）
- **完全可编辑**，每个参数独立可调

### 三大组成部分

```
┌─────────────────┐
│   wild-core     │  已有：渲染/重建引擎（不重做）
│  (引擎核心)      │  输入 .wild → 输出几何
└─────────────────┘

┌─────────────────┐
│   wild-web      │  新建：前端编辑器
│  (前端编辑器)    │  UI + 状态管理 + Three.js 渲染
└─────────────────┘

┌─────────────────┐
│   wild-server   │  新建：后端 Agent 服务
│  (AI 服务)       │  理解意图 → 生成 .wild / Patch
└─────────────────┘
```

---

## 项目结构

```
WildAgent/
├── wild-web/                   # ✨ 前端编辑器（当前主要开发）
│   ├── src/
│   │   ├── stores/             # Pinia 状态管理
│   │   │   ├── sceneStore.ts          # 场景文档 + Blueprint + 重建
│   │   │   ├── selectionStore.ts      # 选择 / hover 状态
│   │   │   ├── historyStore.ts        # 撤销/重做（50 步）
│   │   │   ├── agentStore.ts          # AI 对话消息 + WebSocket 状态
│   │   │   └── uiStore.ts             # UI 面板布局
│   │   ├── types/              # TypeScript 类型定义
│   │   │   ├── blueprint.ts
│   │   │   ├── scenePatch.ts
│   │   │   ├── scene.ts
│   │   │   └── agent.ts
│   │   ├── wild/               # WILD 核心逻辑
│   │   │   ├── scenePatch.ts          # Patch 应用
│   │   │   ├── sceneValidator.ts      # Blueprint 校验
│   │   │   ├── sceneSummary.ts        # 场景摘要
│   │   │   ├── idFactory.ts           # ID 生成
│   │   │   └── blueprintDefaults.ts   # 构件默认参数
│   │   ├── wild-core/          # 渲染引擎（内嵌）
│   │   │   ├── types.ts
│   │   │   └── src/primitive/
│   │   │       ├── index.ts           # 入口：parseBlueprint + reconstructEntity
│   │   │       ├── parser.ts          # .wild JSON 解析
│   │   │       ├── expander.ts        # 模板展开 + placement 展开
│   │   │       ├── resolver.ts        # 空间关系解析
│   │   │       ├── geometry/          # 几何构建器（wall/floor/column/beam/roof/stair/opening/furniture/body/denseBrick）
│   │   │       ├── materials/apply.ts # 材质应用 + 程序化效果
│   │   │       └── behaviors/scripts.ts
│   │   ├── renderer/           # ✅ 渲染适配层（已完成）
│   │   │   ├── wildCoreAdapter.ts     # wild-core 封装（parse + reconstruct）
│   │   │   ├── meshDataToGeometry.ts  # MeshData → Three.js BufferGeometry
│   │   │   ├── materialAdapter.ts     # MaterialParams → Three.js 材质 + 缓存
│   │   │   └── renderEntity.ts        # ReconstructedEntity → Three.js Group
│   │   ├── components/         # Vue 组件
│   │   │   ├── layout/                # EditorTopBar / LeftPanel / RightPanel / BottomPanel
│   │   │   ├── viewport/              # CanvasViewport（Three.js 渲染 + 灯光 + 控制器）
│   │   │   └── panels/                # SceneTree / BlockLibrary / PropertyPanel / ValidationPanel / AIChatPanel
│   │   ├── agent/              # Agent 通信
│   │   │   ├── agentBridge.ts         # WebSocket 桥接（心跳 + 自动重连 + 页面可见性检测）
│   │   │   └── protocol.ts
│   │   └── utils/common.ts
│   └── docs/
│       ├── FRONTEND_API.md            # 前后端接口文档
│       └── 渲染引擎死循环问题修复报告.md
│
├── wild-server/                # 🚧 后端 Agent 服务
│   ├── main.py                 # FastAPI 入口（uvicorn）
│   ├── config.py               # Pydantic Settings 配置
│   ├── pyproject.toml          # Python 3.12+ 项目配置
│   ├── storage/
│   │   ├── knowledge_base/     # 规范文档（BLUEPRINT-SPEC-MINIMAL.md 等）
│   │   ├── scenes/             # 生成的 .wild 文件存储
│   │   └── sessions/           # 会话数据
│   └── app/
│       ├── api/
│       │   ├── ws_agent.py            # WebSocket 端点（心跳 / 消息分发 / 并发锁 / 思考动画）
│       │   └── scenes.py              # 场景 HTTP API（GET /api/scenes/{filename}）
│       ├── services/
│       │   ├── agent_service.py       # Agent 服务（核心：15 步校验流水线 + create_agent）
│       │   └── session_service.py
│       ├── agent/
│       │   ├── graph.py               # LangGraph Agent 图定义（预留）
│       │   ├── prompts.py             # System Prompt 组装（8 条空间铁律 + 工作流程）
│       │   └── model_client.py        # LLM 模型客户端（OpenAI 兼容工厂）
│       ├── tools/
│       │   └── spatial_tools.py       # 16 个空间工具（1 查询 + 9 检测 + 6 修正）
│       ├── spec/
│       │   └── loader.py              # SpecLoader 抽象 + FileSpecLoader（预留 RAG 接口）
│       ├── utils/
│       │   ├── blueprint_parser.py    # Blueprint 提取/校验/保存
│       │   └── ws_heartbeat.py        # WebSocket 心跳监控器
│       └── rag/                       # RAG 向量索引库（预留）
│
├── README.md
└── 架构设计方案.md
```

---

## 核心概念

### 1. Blueprint（蓝图）

`.wild` 文件的 JSON 格式，是场景的唯一源文件。包含 `meta`（版本/类型/名称）、`geometry`（构件数组）、`materials`、`behaviors`。

```json
{
  "meta": { "version": "1.0", "type": "building", "name": "中式凉亭" },
  "geometry": {
    "elements": [
      { "id": "col_01", "type": "column", "base": [0, 0, 0], "height": 3.5, "bottomRadius": 0.25, "topRadius": 0.25 }
    ]
  }
}
```

### 2. ScenePatch（场景补丁）

所有修改操作的统一格式。用户操作和 Agent 建议都转为 `ScenePatch`，基于 revision 防止冲突。

```typescript
interface ScenePatch {
  type: 'scene_patch'
  patch_id: string
  base_revision: number        // 基于哪个版本，不匹配则拒绝
  source: 'user' | 'agent' | 'system'
  mode: 'apply' | 'proposal'
  requires_confirmation: boolean
  operations: SceneOperation[] // add_element / update_element / remove_element / upsert_material / add_placement / add_template + add_instance
  summary?: string
}
```

- 每次成功应用后 `revision++`
- Patch 的 `base_revision` 必须等于当前 revision

### 3. 数据流

```
用户操作 / Agent 建议 → ScenePatch → sceneStore.applyPatch() → Blueprint 更新 → 校验
  → wild-core.reconstructEntity() → MeshData + MaterialParams → Three.js 渲染
```

---

## 当前状态

### 技术栈

- **Vue 3.5** + TypeScript 6.0（组合式 API）
- **Pinia 2.1**: 状态管理
- **Three.js 0.160**: 3D 渲染
- **Vite 8.1**: 构建工具
- **WebSocket**: Agent 实时通信

### ✅ 已完成

- [x] 状态管理系统（5 个 Store）
- [x] ScenePatch 协议定义 + 应用逻辑 + 校验
- [x] UI 组件框架（4 布局 + 5 面板 + 1 视口）
- [x] 基础编辑（拖拽添加构件 / 属性面板 / 场景树 / .wild 导入导出）
- [x] **wild-core 渲染适配层**（wildCoreAdapter → meshDataToGeometry → materialAdapter → renderEntity）
- [x] Three.js 视口（灯光 / 阴影 / 轨道控制 / 响应式 / 场景重建观察器）
- [x] wild-core 引擎内嵌（parser / expander / resolver / 10 种几何构建器 / 材质系统）
- [x] **WebSocket 通信**（心跳 ping/pong / 自动重连 / 页面可见性检测 / 指数退避）
- [x] **后端 Agent 服务骨架**（FastAPI + WebSocket 端点 + LangGraph Agent + 心跳监控工具类）

### 🚧 进行中 / 待开发

- [ ] **3D 交互增强**：点击拾取 / 选中高亮 / Transform Gizmo
- [ ] **Agent AI 能力接入**：真实 LLM 生成 Blueprint / ScenePatch
- [ ] **Patch 确认 UI**：Agent 建议 → 预览 → 应用/拒绝
- [ ] 后端场景保存 API
- [ ] 局部重建优化
- [ ] 更多构件类型支持

---

## 关键设计决策

### 1. 为什么不重做 wild-core？

wild-core 是**核心资产**：已实现复杂几何算法、确定性的（同一输入永远同一输出）、语言无关。重做风险高，不必要。当前已内嵌到 `src/wild-core/` 直接调用。

### 2. 为什么使用 ScenePatch？

统一用户操作和 Agent 建议的接口。基于 revision 的版本控制（类似 Git），可追溯、可撤销，前端负责最终校验和应用。

### 3. 为什么使用单 Agent？

任务域集中在**一份 .wild 文件**上，不需要多 Agent 协作。避免通信开销和冲突合并。

### 4. 为什么 .wild 是唯一源文件？

可移植（几 KB JSON）、Git 友好、确定性、参数化可编辑。不是死网格文件。

---

## 开发阶段

### Phase 1: 前端基础框架 ✅（已完成）

前端编辑器完整搭建：状态管理、ScenePatch 协议、UI 组件、wild-core 接入、Three.js 渲染。

### Phase 2: 后端 Agent MVP 🚧（当前，接近完成）

目标：AI 能根据自然语言生成完整的 Blueprint JSON。

- ✅ FastAPI + WebSocket 端点（心跳 / 消息分发 / 并发锁 / 思考动画）
- ✅ 16 个空间工具（1 查询 + 9 检测 + 6 修正）
- ✅ 15 步服务端校验流水线（Structure → Schema → Reference → Geometry → Fix → Collision）
- ✅ LangChain Agent + 知识库规范文档加载
- ✅ 前后端 WebSocket 联通 + 端到端对话测试
- 🚧 RAG 索引向量库（提高 AI 建模精度）

### Phase 3: 完整编辑工作流

- 3D 拾取和选中高亮
- Transform Gizmo
- 更多 Agent 工具
- Patch 确认 UI
- 自动保存

### Phase 4: 稳定化和扩展

- 后端场景持久化
- 错误恢复
- 性能优化
- 更多构件类型

---

## 快速上手

### 启动前端

```bash
cd wild-web
npm install
npm run dev        # 访问 http://localhost:5173
```

### 基础操作

1. 点击「新建」创建空场景
2. 左侧「构件库」拖拽添加构件
3. 点击构件，右侧「属性」面板修改参数
4. 「保存」导出 .wild 文件，「打开」加载已有 .wild 文件

### 启动后端

```bash
cd wild-server
python main.py     # 启动 FastAPI + WebSocket 服务，监听 ws://localhost:8000/ws/agent
```

---

## 重要文件索引

### 文档

| 文件 | 说明 |
|---|---|
| `../README.md` | 项目主文档 |
| `../架构设计方案.md` | 完整架构设计（最重要） |
| `CLAUDE.md` | 本文档 |
| `docs/FRONTEND_API.md` | 前后端接口文档 |
| `docs/渲染引擎死循环问题修复报告.md` | 渲染引擎接入修复记录 |

### 前端核心代码

| 文件 | 说明 |
|---|---|
| `src/stores/sceneStore.ts` | 场景状态管理 |
| `src/wild/scenePatch.ts` | Patch 应用逻辑 |
| `src/renderer/wildCoreAdapter.ts` | wild-core 封装入口 |
| `src/renderer/renderEntity.ts` | 场景 → Three.js 转换 |
| `src/renderer/materialAdapter.ts` | 材质转换 + 缓存 |
| `src/components/viewport/CanvasViewport.vue` | 3D 视口 |
| `src/agent/agentBridge.ts` | Agent WebSocket 通信（心跳 + 自动重连 + 页面可见性检测） |

### 后端核心代码

| 文件 | 说明 |
|---|---|
| `app/api/ws_agent.py` | Agent WebSocket 端点（消息分发 + 并发锁 + 思考动画） |
| `app/services/agent_service.py` | Agent 服务（15 步校验流水线 + create_agent） |
| `app/tools/spatial_tools.py` | 16 个空间工具（get_wall_bounding_box / validate_*/fix_*） |
| `app/agent/prompts.py` | System Prompt 组装（8 条空间铁律 + 工作流） |
| `app/agent/model_client.py` | LLM 模型客户端（OpenAI 兼容工厂） |
| `app/spec/loader.py` | 规范文档加载器（FileSpecLoader + RAG 预留接口） |
| `app/utils/blueprint_parser.py` | Blueprint 提取/校验/保存 |
| `main.py` | FastAPI 入口（uvicorn） |

---

**最后更新**: 2026-07-22
**项目阶段**: Phase 1 完成，Phase 2 接近完成（15 步校验流水线 + 16 个工具已就绪，下一步 RAG 向量库）
