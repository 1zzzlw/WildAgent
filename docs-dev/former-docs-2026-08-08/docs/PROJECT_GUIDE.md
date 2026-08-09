# WildAgent 项目指南

> 本文档整合自项目核心文档，帮助开发者快速理解 WildAgent 的全貌。
> 最后更新：2026-08-07

---

## 1. 项目概述

**WildAgent** 是一个 AI 辅助的参数化 3D 建筑编辑器。用户用自然语言描述建筑，系统自动生成 `.wild` 蓝图文件并实时渲染 3D 效果。

### 核心差异

| 主流 AI 3D 工具 | WildAgent |
|---|---|
| AI 直接生成顶点坐标 | AI 只生成参数值 |
| 几何不确定，可能模糊 | 精确到小数，100% 可复现 |
| .glb 死文件（几十 MB） | .wild 活参数（几 KB） |
| 不可参数化编辑 | 每个参数独立可调 |
| 无确定性 | 同一 .wild 永远同一结果 |

### 一句话

用户输入自然语言 → AI 生成 `.wild` 蓝图 → `wild-core` 确定性重建几何 → Three.js 实时渲染 → 用户可拖拽/调参/对话持续编辑。

---

## 2. 核心理念与边界

### 五条核心原则

| 原则 | 说明 |
|---|---|
| `.wild` 是唯一场景源文件 | 所有建筑结构、材质、行为最终都落到 `.wild` JSON |
| 渲染引擎只复用不重做 | `wild-core` 是现有核心引擎，新系统只接入它 |
| AI 不直接生成三角形 | AI 只生成参数、构件、材质、patch |
| 用户保留最终决策权 | 批量修改、删除、覆盖场景必须用户确认 |
| 手动编辑不走 Agent | 拖拽、属性面板、场景树操作直接修改本地状态 |

### 四条不可破坏的边界

1. `.wild` 永远是唯一场景源文件
2. `wild-core` 只负责解析、展开、空间解析和几何重建，不管 UI 和 AI
3. Editor / `wild-web` 只管状态、交互、Patch、渲染适配，不发明新的语言语义
4. Agent / `wild-server` 只改参数和生成 Blueprint / ScenePatch，不输出 Three.js、HTML、CSS、JS

### 特别避免

- 不重写 `wild-core` 几何算法，除非任务明确是修引擎 bug
- 不让后端参与三角形计算
- 不把 UI 临时状态混入 `.wild` 几何语义；编辑器私有信息放 `editor` 字段
- 不让 Agent 生成未知构件类型或大段不可校验 JSON
- 删除、覆盖、批量整理必须走用户确认

---

## 3. 技术栈

| 层 | 技术 |
|---|---|
| 前端框架 | Vue 3.5 + TypeScript 6.0（组合式 API） |
| 状态管理 | Pinia 2.1 |
| 3D 渲染 | Three.js 0.160 |
| 构建工具 | Vite 8.1 |
| 实时通信 | WebSocket |
| 后端框架 | FastAPI + uvicorn |
| AI Agent | LangChain / LangGraph |
| LLM | OpenAI 兼容接口 |
| 包管理 | uv（Python）/ npm（前端） |

---

## 4. 项目结构

```
WildAgent/
├── README.md                           # 项目理念和价值说明
├── 架构设计方案.md                      # 完整架构设计（最重要）
├── 项目进展总结.md                      # 当前状态、优先级、关键文件索引
├── agent.md                            # 快速熟悉笔记（给 AI 协作用）
├── docker-compose.yml                  # 前后端容器编排
├── docs/
│   ├── PROJECT_GUIDE.md                # 本文档
│   ├── 项目阶段路线文档.md              # 六阶段路线
│   ├── 从开发到部署完整指南.md           # 本地、Docker、CI/CD、部署说明
│   └── 服务器环境变量配置.md             # 环境变量说明
├── docs-dev/                           # 开发过程文档归档
├── wild-web/                           # Vue 3 + TypeScript 编辑器
│   ├── src/
│   │   ├── agent/                      # Agent 通信
│   │   ├── components/                 # Vue 组件
│   │   ├── renderer/                   # Three.js 渲染适配层
│   │   ├── stores/                     # Pinia 状态管理
│   │   ├── types/                      # TypeScript 类型
│   │   ├── wild/                       # 编辑器领域逻辑
│   │   ├── wild-compiler/              # 组合构件编译器
│   │   ├── wild-core/                  # 确定性几何重建引擎
│   │   └── workers/                    # 后台重建 Worker
│   ├── wild-lang/                      # WILD 语言规范
│   └── lantu/                          # 示例 .wild 蓝图
├── wild-server/                        # FastAPI + LangChain Agent 后端
│   ├── app/
│   │   ├── agent/                      # 模型工厂、Prompt
│   │   ├── api/                        # WebSocket + REST 端点
│   │   ├── services/                   # Agent 与会话服务
│   │   ├── tools/                      # 空间检测与修正工具
│   │   └── spec/                       # 规范文档加载层
│   └── storage/
│       ├── scenes/                     # 已保存的 .wild 文件
│       ├── knowledge_base/             # 规范文档和知识库
│       └── chroma/                     # RAG 向量索引
```

### 目录边界

| 修改目标 | 首选目录 | 不应放入 |
|---|---|---|
| 新增业务组合构件 | `wild-web/src/wild-compiler/components/` | 直接膨胀 renderer |
| 新增底层几何能力 | `wild-web/src/wild-core/src/primitive/geometry/` | Vue 组件 |
| Three.js 显示或运行时交互 | `wild-web/src/renderer/`、`CanvasViewport.vue` | 后端 |
| Agent 协议适配 | `wild-web/src/agent/`、`wild-server/app/api/` | Store 内直接请求网络 |
| Blueprint 检测与修正 | `wild-server/app/tools/` | Prompt 中只写自然语言兜底 |
| RAG 分片与检索 | `wild-server/app/spec/loader.py` | 前端 |

---

## 5. 核心数据模型

### 5.1 Blueprint（蓝图）

`.wild` 文件的 JSON 格式，是场景的唯一源文件。

**最小结构**：
```json
{
  "meta": { "version": "1.0", "type": "building", "name": "未命名建筑" },
  "geometry": { "elements": [] },
  "materials": {},
  "behaviors": {}
}
```

**标准构件类型**：

| type | 用途 |
|---|---|
| `wall` | 墙体 |
| `floor` | 地板/平台 |
| `column` | 柱子 |
| `beam` | 梁 |
| `roof` | 屋顶 |
| `opening` | 门窗洞口 |
| `stair` | 楼梯 |
| `furniture` | 参数化家具和瓦片 |
| `dense_brick` | 高分辨率体素细节 |
| `body` | 化身身体 |
| `primitive` | 通用参数化形体（box/sphere/cylinder/profile_sweep） |

### 5.2 ScenePatch（场景补丁）

所有编辑操作的统一格式，用户操作和 Agent 建议都转为 ScenePatch。

```typescript
interface ScenePatch {
  type: 'scene_patch'
  patch_id: string
  base_revision: number        // 基于哪个版本，不匹配则拒绝
  source: 'user' | 'agent' | 'system'
  mode: 'apply' | 'proposal'
  requires_confirmation: boolean
  operations: SceneOperation[]
  summary?: string
}
```

**支持的操作**：add_element / update_element / remove_element / upsert_material / add_template / update_template / remove_template / add_instance / add_placement / set_behaviors / set_editor_meta

### 5.3 数据流

```
用户操作 / Agent 建议
  → ScenePatch
  → sceneStore.applyPatch()
  → Blueprint 更新 → 校验
  → wild-core.reconstructEntity()
  → MeshData + MaterialParams
  → Three.js 渲染
```

---

## 6. 前端架构

### 6.1 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│ 顶部工具栏：新建 / 打开 / 保存 / 导出 / 撤销 / 重做           │
├──────────────┬───────────────────────────────┬───────────────┤
│ 左侧面板      │ 中央 3D 视口                    │ 右侧面板       │
│              │                               │               │
│ 构件库        │ CanvasViewport                 │ 属性面板        │
│ - 基础构件    │ - Three.js                      │ - 按类型渲染表单 │
│ - AI 生成     │ - OrbitControls                 │ - 数值输入       │
│              │ - 选中高亮                       │ - 材质选择       │
│ 场景树        │ - Transform Gizmo              │               │
├──────────────┴───────────────────────────────┴───────────────┤
│ 底部 AI 对话面板：用户输入 / Agent 流式过程 / patch 确认         │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 状态管理（5 个 Pinia Store）

| Store | 职责 |
|---|---|
| `sceneStore` | 场景文档 + Blueprint + 重建触发 |
| `selectionStore` | 选中 / hover 状态 |
| `historyStore` | 撤销/重做（50 步历史） |
| `agentStore` | AI 消息、会话、WebSocket 状态 |
| `uiStore` | UI 面板布局状态 |

### 6.3 渲染管线

```
wildCoreAdapter (parse + reconstruct)
  → meshDataToGeometry (MeshData → BufferGeometry)
  → materialAdapter (MaterialParams → Three.js 材质 + 缓存)
  → renderEntity (ReconstructedEntity → Three.js Group)
  → CanvasViewport (灯光 + 阴影 + 轨道控制)
```

### 6.4 关键目录

```
wild-web/src/
├── stores/
│   ├── sceneStore.ts          # 场景文档、Blueprint、revision、重建
│   ├── selectionStore.ts      # 选中和 hover
│   ├── historyStore.ts        # undo / redo，50 步快照
│   ├── agentStore.ts          # AI 消息、会话、WebSocket 状态
│   └── uiStore.ts             # 面板布局状态
├── wild/
│   ├── scenePatch.ts          # Patch 应用逻辑
│   ├── sceneValidator.ts      # Blueprint 校验
│   └── sceneSummary.ts        # 发给 Agent 的场景摘要
├── renderer/
│   ├── wildCoreAdapter.ts     # parseBlueprint + reconstructEntity 封装
│   ├── meshDataToGeometry.ts  # MeshData -> THREE.BufferGeometry
│   ├── materialAdapter.ts     # MaterialParams -> Three.js 材质
│   └── renderEntity.ts        # ReconstructedEntity -> THREE.Group
├── wild-compiler/             # 组合构件编译器
│   └── components/            # 门窗、栏杆、坡道、檐口、灯具等
├── wild-core/                 # 确定性几何重建引擎
└── agent/
    ├── agentBridge.ts         # WebSocket + HTTP 桥接
    └── protocol.ts
```

---

## 7. 后端架构

### 7.1 服务模块

```
FastAPI app
├── Scene REST API            ← 列出、读取、显式保存和删除 .wild
├── WebSocket Agent API       ← 消息、心跳、推理流和 Patch/Blueprint 事件
├── Agent Service             ← LLM + Prompt + RAG + tools + 校验流水线
├── Model Client              ← OpenAI 兼容模型工厂
├── Spec Loader               ← Markdown 分片、Chroma 同步、过滤和检索
├── Spatial Tool Layer        ← Blueprint 检测、查询和自动修正纯函数
└── File Storage              ← scenes / knowledge_base / chroma
```

### 7.2 REST API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/scenes` | 列出所有已保存的蓝图文件 |
| `GET` | `/api/scenes/{filename}` | 获取单个蓝图文件 |
| `PUT` | `/api/scenes/{filename}` | 更新/保存蓝图文件 |
| `DELETE` | `/api/scenes/{filename}` | 永久删除对应文件 |

### 7.3 WebSocket Agent API

**连接地址**：`ws://localhost:8000/ws/agent`

**前端发送**：
```json
{
  "type": "user_message",
  "request_id": "req_001",
  "session_id": "sess_001",
  "scene_revision": 8,
  "message": "在别墅右侧加一个中式凉亭",
  "thinking_mode": false,
  "scene_summary": { "elements_count": 42, "types": ["wall", "floor", "roof"] }
}
```

**后端返回**：
- `agent_step`：流式状态（校验/生成进度）
- `blueprint_generated`：AI 全量生成完成（含 session_id / filename / file_url）
- `patch_proposal`：patch 提案
- `agent_reply`：最终文本回复
- `thinking_delta` / `thinking_status`：模型思考流式内容
- `presence_update`：在线人数快照
- `network_error`：心跳超时通知
- `error`：错误信息
- `pong`：心跳响应

### 7.4 关键目录

```
wild-server/
├── main.py                         # FastAPI 入口（注册 ws/scenes/sessions 路由）
├── config.py                       # Pydantic Settings 配置
├── app/
│   ├── api/
│   │   ├── ws_agent.py             # /ws/agent WebSocket 端点（precision_mode 走 LangGraph）
│   │   ├── scenes.py               # /api/scenes REST API（日期子目录 + 旧格式双路由）
│   │   └── sessions.py             # /api/sessions 会话 REST API（元数据 + 消息历史）
│   ├── services/
│   │   ├── agent_service.py        # Agent 服务核心（15 步校验流水线）
│   │   └── session_service.py      # 会话管理
│   ├── agent/
│   │   ├── model_client.py         # OpenAI 兼容 LLM 工厂
│   │   ├── prompts.py              # System Prompt 组装
│   │   ├── graph.py                # LangGraph StateGraph（已实现，生成编排）
│   │   ├── graph_state.py          # LangGraph 状态类型
│   │   ├── nodes/                  # 19 个节点文件（skeleton/classifier/merge/validate/callback + 组件节点）
│   │   └── utils/                  # fragment_merger / json_extractor
│   ├── tools/
│   │   ├── spatial_tools.py        # 18 个空间工具
│   │   └── component_tools.py      # 组合构件级 validate/fix 工具
│   └── spec/
│       └── loader.py               # 规范文档加载器（RAGSpecLoader）
```

---

## 8. Agent 架构

### 8.1 设计逻辑

```
ws_agent.py              # 传输层
  → AgentService.query_structured()
  → SpecLoader.load()
  → build_system_prompt()
  → LLM / LangChain Agent 生成 Blueprint 或 ScenePatch
  → run_validation_pipeline()
  → 返回完整 Blueprint / Patch / 错误
```

### 8.2 空间工具（18 个）

| 类别 | 数量 | 示例 |
|---|---|---|
| 查询 | 1 | `get_wall_bounding_box` |
| 检测 | 9 | `validate_*` 系列（结构/引用/开口/墙体/楼梯/屋顶/尺寸/碰撞） |
| 修正 | 8 | `fix_*` 系列（开口坐标/开口适配/楼梯对齐/屋顶覆盖/墙体接缝/构件尺寸/构件标高） |

### 8.3 校验流水线

```
1  validate_blueprint_structure
2  validate_element_required_fields
3  validate_reference_integrity
4  validate_opening_coords / validate_opening_fit
5  validate_wall_junctions
6  validate_stair_alignment
7  validate_roof_coverage / validate_element_dimensions
8  fix_opening_coords / fix_opening_fit / fix_stair_alignment
   fix_element_dimensions / fix_roof_coverage / fix_wall_junctions
9  validate_collision / fix_element_elevations
```

**原则**：
- LLM 只负责生成初稿；空间正确性由 Python 确定性工具兜底
- 前序结构错误会跳过后续几何校验
- 修正步骤只在对应检测发现问题时运行
- ❌ 级别错误要拦截，不把坏 patch 发给前端渲染

---

## 9. 开发阶段

| 阶段 | 状态 | 核心目标 |
|---|---|---|
| Phase 1：前端基础框架 | ✅ 已完成 | Vue + Pinia + Three.js + wild-core 渲染管线 + ScenePatch |
| Phase 2：后端 Agent MVP | ✅ 已完成 | FastAPI + LangChain + 18 工具 + 校验流水线 + RAG |
| Phase 3：LangGraph 智能编排 | 🚧 生成编排已落地 | `graph.py` StateGraph + 19 节点 + precision_mode 接入；资产工作流待续 |
| Phase 4：前端交互与渲染升级 | ⏳ 待开始 | 3D 拾取、选中高亮、Transform Gizmo、环境渲染 |
| Phase 5：AI 组件模块化 | ⏳ 待开始 | `/component` 命令、AI 构件库、智能吸附 |
| Phase 6：测试部署与稳定化 | ⏳ 待开始 | pytest、vitest、Playwright、Docker、CI/CD |

### 当前优先级

1. **RAG 索引向量库** — 提升 AI 生成蓝图的精度
2. **3D 交互增强** — 点击拾取、选中高亮
3. **Transform Gizmo** — 平移/旋转/缩放
4. **消息历史恢复** — 刷新后恢复聊天记录（sessions API 已提供存储）
5. **自动保存** — 手动编辑时自动同步到后端

---

## 10. 运行命令

### 前端开发

```bash
cd wild-web
npm install
npm run dev        # 访问 http://localhost:5173
```

### 前端构建

```bash
cd wild-web
npm run build
```

### 后端开发

```bash
cd wild-server
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
# 访问 http://localhost:8000
```

### Docker 本地验证

```bash
docker compose up -d
# 前端 http://localhost
# 后端 http://localhost:8000

docker compose down
```

### 环境变量配置

```env
# wild-server/.env
CHAT__NAME=qwen-plus
CHAT__API_KEY=sk-xxx
CHAT__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

EMBEDDING__NAME=text-embedding-v3
EMBEDDING__API_KEY=sk-xxx
EMBEDDING__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

RERANK__NAME=bge-reranker-v2-m3
RERANK__API_KEY=sk-xxx
RERANK__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

---

## 11. 关键文件索引

### 文档

| 文件 | 说明 |
|---|---|
| [架构设计方案.md](../架构设计方案.md) | 完整架构设计（最重要） |
| [项目进展总结.md](../项目进展总结.md) | 当前状态、优先级、关键文件索引 |
| [agent.md](../agent.md) | 快速熟悉笔记（给 AI 协作用） |
| [docs/项目阶段路线文档.md](项目阶段路线文档.md) | 六阶段路线 |
| [docs/从开发到部署完整指南.md](从开发到部署完整指南.md) | 本地、Docker、CI/CD、部署说明 |

### 前端核心

| 文件 | 说明 |
|---|---|
| [sceneStore.ts](../wild-web/src/stores/sceneStore.ts) | 场景状态管理 |
| [scenePatch.ts](../wild-web/src/wild/scenePatch.ts) | Patch 应用逻辑 |
| [wildCoreAdapter.ts](../wild-web/src/renderer/wildCoreAdapter.ts) | wild-core 封装入口 |
| [renderEntity.ts](../wild-web/src/renderer/renderEntity.ts) | 场景 → Three.js 转换 |
| [CanvasViewport.vue](../wild-web/src/components/viewport/CanvasViewport.vue) | 3D 视口 |
| [agentBridge.ts](../wild-web/src/agent/agentBridge.ts) | Agent WebSocket 通信 |

### 后端核心

| 文件 | 说明 |
|---|---|
| [ws_agent.py](../wild-server/app/api/ws_agent.py) | WebSocket 端点 |
| [agent_service.py](../wild-server/app/services/agent_service.py) | Agent 服务核心 |
| [spatial_tools.py](../wild-server/app/tools/spatial_tools.py) | 18 个空间工具 |
| [prompts.py](../wild-server/app/agent/prompts.py) | System Prompt 组装 |
| [loader.py](../wild-server/app/spec/loader.py) | 规范文档加载器 |
| [blueprint_parser.py](../wild-server/app/utils/blueprint_parser.py) | Blueprint 提取/校验 |

---

## 12. 修改代码指南

### 做任务前的快速检查清单

1. 明确本次改动属于前端、后端、语言规范、引擎还是部署
2. 先看对应文档，再看关键源码入口
3. 若是场景修改能力，优先检查是否应该通过 ScenePatch
4. 若是 AI 生成质量问题，优先看 `prompts.py`、知识库规范和 `spatial_tools.py`
5. 若是渲染错位，先确认 Blueprint 是否合法，再判断是 `wild-core`、renderer 适配还是 Three.js 视口问题
6. 若新增构件，路线是：规范文档 → TypeScript 类型 → `wild-core` geometry builder → renderer / validator → Agent 知识库
7. 改完前端至少跑 `npm run build`；改后端至少跑相关 Python 测试

### 常见修改场景入口

**前端相关**：
- 场景状态或渲染触发：`wild-web/src/stores/sceneStore.ts`
- Patch 语义：`wild-web/src/wild/scenePatch.ts`
- Blueprint 校验：`wild-web/src/wild/sceneValidator.ts`
- 3D 渲染适配：`wild-web/src/renderer/*`
- 视口交互：`wild-web/src/components/viewport/CanvasViewport.vue`
- AI 对话 UI：`wild-web/src/components/panels/AIChatPanel.vue`
- Agent 通信：`wild-web/src/agent/agentBridge.ts`

**后端相关**：
- WebSocket 协议和消息分发：`wild-server/app/api/ws_agent.py`
- 场景文件 REST：`wild-server/app/api/scenes.py`
- Agent 服务核心和流水线：`wild-server/app/services/agent_service.py`
- 空间检测/修复工具：`wild-server/app/tools/spatial_tools.py`
- Prompt：`wild-server/app/agent/prompts.py`
- 模型配置：`wild-server/config.py`、`wild-server/app/agent/model_client.py`
- 规范加载 / RAG 接口：`wild-server/app/spec/loader.py`

---

## 13. 已知文档差异

- 有些旧文档写空间工具是 16 个；源码当前是 18 个，包含 `fix_element_elevations`
- `wild-web/README.md` 的"待实现功能"部分有旧状态描述；更新状态以 `项目进展总结.md` 和源码为准
- 架构文档中 REST API 早期设计写过 `POST /api/scenes` 和 `POST /api/validate`，当前源码校准到 `GET/PUT/DELETE /api/scenes` 为主
