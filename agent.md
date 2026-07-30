# WildAgent 快速熟悉笔记

> 给后续 Agent / AI 协作时快速建立项目上下文使用。整理时间：2026-07-29。  
> 主要依据：`README.md`、`架构设计方案.md`、`项目进展总结.md`、`docs/项目阶段路线文档.md`、`docs/从开发到部署完整指南.md`、`wild-web/README.md`、`wild-web/docs/FRONTEND_API.md`、`wild-web/wild-lang/*`、`wild-server/storage/knowledge_base/*`，并用源码校准当前工具数量与入口。

## 1. 项目一句话

WildAgent 是一个 AI 辅助的参数化 3D 建筑编辑器。

用户用自然语言描述或修改建筑，后端 Agent 生成 `.wild` Blueprint 或 ScenePatch，前端把 Blueprint 作为唯一场景源文件，交给 `wild-core` 确定性重建几何，再用 Three.js 实时渲染。

核心差异：

- 不做文生死网格，不生成 GLB/OBJ 作为主资产。
- AI 只生成参数、构件、材质和 patch，不直接生成 Three.js 几何代码。
- `.wild` 是几 KB 级 JSON 活参数文件，每个构件有语义 ID，可编辑、可校验、可版本管理。
- `wild-core` 用数学规则从 `.wild` 生成几何，同一 Blueprint 应该永远得到同一结果。

## 2. 四条不可破坏的边界

后续改代码优先守住这些边界：

1. `.wild` 永远是唯一场景源文件。
2. `wild-core` 只负责解析、展开、空间解析和几何重建，不管 UI 和 AI。
3. Editor / `wild-web` 只管状态、交互、Patch、渲染适配，不发明新的语言语义。
4. Agent / `wild-server` 只改参数和生成 Blueprint / ScenePatch，不输出 Three.js、HTML、CSS、JS 几何实现。

需要特别避免：

- 不重写 `wild-core` 几何算法，除非任务明确是修引擎 bug。
- 不让后端参与三角形计算。
- 不把 UI 临时状态混入 `.wild` 几何语义；编辑器私有信息放 `editor` 字段。
- 不让 Agent 生成未知构件类型或大段不可校验 JSON。
- 删除、覆盖、批量整理必须走用户确认。

## 3. 顶层结构

```text
WildAgent/
├── README.md                         # 项目理念和价值说明
├── 架构设计方案.md                    # 最重要的完整架构文档
├── 项目进展总结.md                    # 当前状态、优先级、关键文件索引
├── docker-compose.yml                # 前后端容器编排
├── docs/
│   ├── 项目阶段路线文档.md             # 六阶段路线
│   └── 从开发到部署完整指南.md          # 本地、Docker、CI/CD、部署说明
├── wild-web/                         # Vue 前端编辑器
└── wild-server/                      # FastAPI 后端 Agent 服务
```

## 4. `.wild` / Blueprint

`.wild` 文件是 JSON，顶层必须包含 `meta` 和 `geometry`，可选 `materials`、`behaviors`、`editor`。

最小结构：

```json
{
  "meta": { "version": "1.0", "type": "building", "name": "未命名建筑" },
  "geometry": { "elements": [] },
  "materials": {},
  "behaviors": {}
}
```

核心字段：

- `meta.version`：当前主要是 `"1.0"`，语言规范遵循“永不删除”向后兼容承诺。
- `meta.type`：`building` 或 `avatar`。
- `geometry.elements`：构件列表，每个元素必须有唯一 `id` 和 `type`。
- `materials`：PBR 数值材质，不依赖外部纹理；`baseColor` 必须是 `[R,G,B]` 数组，不能用 `#RRGGBB`。
- `behaviors`：物理、动画和有限交互脚本。
- `editor`：前端私有元数据，不影响渲染。

当前标准构件：

```text
wall / floor / column / beam / roof / opening / stair / furniture / dense_brick / body
```

AI 生成时优先看：

- `wild-server/storage/knowledge_base/BLUEPRINT-SPEC-MINIMAL.md`
- `wild-server/storage/knowledge_base/BLUEPRINT-SPEC-FULL.md`
- `wild-server/storage/knowledge_base/building_types/catalog/`
- `wild-web/wild-lang/SPEC.md`
- `wild-web/wild-lang/PRIMITIVES.md`
- `wild-web/wild-lang/MATERIALS.md`
- `wild-web/wild-lang/BEHAVIORS.md`
- `wild-web/wild-lang/VERSIONING.md`

容易出错的规范点：

- `opening.from[0]` 是沿 `parentWall.from -> parentWall.to` 的墙体局部距离，不是世界 X。
- `opening.from[1]` 是开口底部的世界 Y。
- `opening.from[2]` 通常为 0，表示法向偏移。
- `roof.span` 覆盖 X 方向，`roof.depth` 覆盖 Z 方向，必须覆盖墙体包围盒。
- `stair.from[1]` 是下层地板 Y，`stair.to[1]` 是上层地板 Y，必须 `from[1] < to[1]`。
- `furniture` 当前精简规范只建议用于灯具、瓦片等；凳子、桌椅、床一类优先用 `column + floor` 组合表达。

## 5. ScenePatch 协议

ScenePatch 是所有增量修改的统一格式，用户手动操作和 Agent 建议都走同一条 `sceneStore.applyPatch()` 管线。

```ts
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

当前源码支持 11 种操作：

```text
add_element
update_element
remove_element
upsert_material
add_template
update_template
remove_template
add_instance
add_placement
set_behaviors
set_editor_meta
```

应用流程：

```text
收到 patch
  -> 检查 base_revision == 当前 revision
  -> 应用到 Blueprint 深拷贝
  -> 前端校验 Blueprint
  -> wild-core reconstructEntity smoke test
  -> 成功后替换 Blueprint，revision++
  -> 触发 Three.js 重建渲染
```

确认规则：

- 单个添加、单个修改通常可直接应用。
- 删除、批量添加、批量删除、覆盖整个场景、一键整理必须确认。
- Agent 生成的增量修改通常是 `mode: "proposal"`、`requires_confirmation: true`。
- AI 从零生成完整 Blueprint 时不一定走 ScenePatch，可能保存 `.wild` 后由前端直接 `loadBlueprint()` 替换场景。

## 6. 前端 `wild-web`

技术栈：

- Vue 3.5 + Composition API
- TypeScript 6
- Vite 8
- Pinia 2
- Three.js 0.160
- Element Plus
- markdown-it + highlight.js

关键目录：

```text
wild-web/src/
├── App.vue
├── main.ts
├── stores/
│   ├── sceneStore.ts          # 场景文档、Blueprint、revision、重建
│   ├── selectionStore.ts      # 选中和 hover
│   ├── historyStore.ts        # undo / redo，50 步快照
│   ├── agentStore.ts          # AI 消息、会话、WebSocket 状态、pipelineSteps
│   └── uiStore.ts             # 面板布局状态
├── wild/
│   ├── scenePatch.ts          # Patch 应用逻辑
│   ├── sceneValidator.ts      # Blueprint 校验
│   ├── sceneSummary.ts        # 发给 Agent 的场景摘要
│   ├── idFactory.ts
│   └── blueprintDefaults.ts
├── wild-core/                 # 当前内嵌核心引擎，后续计划抽为 @wild/core
├── renderer/
│   ├── wildCoreAdapter.ts     # parseBlueprint + reconstructEntity 封装
│   ├── meshDataToGeometry.ts  # MeshData -> THREE.BufferGeometry
│   ├── materialAdapter.ts     # MaterialParams -> Three.js 材质
│   └── renderEntity.ts        # ReconstructedEntity -> THREE.Group
├── components/
│   ├── layout/                # 顶栏、左右面板、底部面板
│   ├── viewport/CanvasViewport.vue
│   └── panels/                # SceneTree / BlockLibrary / PropertyPanel / ValidationPanel / AIChatPanel
└── agent/
    ├── agentBridge.ts         # WebSocket + HTTP 桥接
    └── protocol.ts
```

前端数据流：

```text
用户操作 / Agent 建议
  -> createPatch()
  -> sceneStore.applyPatch()
  -> Blueprint 更新
  -> sceneValidator
  -> wildCoreAdapter
  -> meshDataToGeometry + materialAdapter + renderEntity
  -> CanvasViewport 显示
```

重要实现点：

- `agentBridge.ts` 根据当前页面地址生成 WebSocket URL，并通过 nginx `/ws/` 代理适配部署。
- `agentStore.ts` 用 localStorage 保存会话列表和当前会话。
- 一个会话对应一个后端 `.wild` 文件，按 `session_id` 命名。
- 前端渲染层有 `MAX_VERTICES = 50000` 保护，超限时替换为红色线框占位网格，避免浏览器卡死。

## 7. 后端 `wild-server`

技术栈：

- Python 3.12+
- FastAPI + uvicorn
- LangChain / LangGraph 预留
- OpenAI Compatible API
- Pydantic Settings
- 文件系统存储，后续再升级 SQLite / PostgreSQL

关键目录：

```text
wild-server/
├── main.py                         # FastAPI 入口
├── config.py                       # ModelConfig / Settings
├── pyproject.toml
├── storage/
│   ├── knowledge_base/             # 规范文档和建筑类型参考
│   ├── scenes/                     # 会话对应 .wild 文件
│   └── sessions/
└── app/
    ├── api/
    │   ├── ws_agent.py             # /ws/agent
    │   └── scenes.py               # /api/scenes
    ├── services/
    │   ├── agent_service.py        # AgentService + query_structured + 校验流水线
    │   └── session_service.py
    ├── agent/
    │   ├── model_client.py         # OpenAI 兼容 LLM 工厂
    │   ├── prompts.py              # System Prompt 组装
    │   └── graph.py                # LangGraph 预留
    ├── spec/
    │   └── loader.py               # FileSpecLoader，RAGSpecLoader 预留
    ├── tools/
    │   └── spatial_tools.py        # 当前 18 个空间工具
    └── utils/
        ├── blueprint_parser.py     # Blueprint / Patch 提取、校验、保存
        └── ws_heartbeat.py
```

当前 REST API 源码入口：

- `GET /api/scenes`：列出已保存蓝图。
- `GET /api/scenes/{filename}`：读取蓝图文件。
- `PUT /api/scenes/{filename}`：更新/保存蓝图文件。
- `DELETE /api/scenes/{filename}`：删除蓝图文件。

Agent WebSocket：

- `ws://localhost:8000/ws/agent`
- 前端发送 `user_message`，包含 `request_id`、`session_id`、`scene_revision`、`message`、`scene_summary`、`selection`，当前代码还会带当前 `blueprint` 做增量修改上下文。
- 后端返回 `agent_step`、`patch_proposal`、`agent_reply`、`error`、心跳 `pong` / `network_error`。
- 心跳：前端每 15s ping，后端空闲超过 90s 会断开；AI 处理中豁免超时。
- 后端有并发锁，避免同一连接同时处理多个 Agent 请求。

## 8. 后端 Agent 与校验流水线

设计逻辑：

```text
ws_agent.py              # 传输层
  -> AgentService.query_structured()
  -> SpecLoader.load()
  -> build_system_prompt()
  -> LLM / LangChain Agent 生成 Blueprint 或 ScenePatch
  -> run_validation_pipeline()
  -> 返回完整 Blueprint / Patch / 错误
```

当前 `spatial_tools.py` 中源码校准为 18 个 `@tool`：

```text
validate_blueprint_structure
validate_opening_coords
validate_wall_junctions
validate_roof_coverage
validate_stair_alignment
validate_element_required_fields
fix_opening_coords
validate_reference_integrity
validate_collision
validate_opening_fit
validate_element_dimensions
get_wall_bounding_box
fix_roof_coverage
fix_wall_junctions
fix_opening_fit
fix_stair_alignment
fix_element_dimensions
fix_element_elevations
```

流水线核心顺序：

```text
1  validate_blueprint_structure
2  validate_element_required_fields
3  validate_reference_integrity
4  validate_opening_coords
4b validate_opening_fit
5  validate_wall_junctions
6  validate_stair_alignment
7  validate_roof_coverage
7b validate_element_dimensions
8  fix_opening_coords
8b fix_opening_fit
8c fix_stair_alignment
8d fix_element_dimensions
8e fix_roof_coverage
8f fix_wall_junctions
9  validate_collision
9b fix_element_elevations
```

注意：架构文档早期段落只写到 Step 9，`.kiro/specs/fix-element-elevation/*` 和源码显示 Step 9b 已加入，用于修正 `column.base[1]`、`stair.from[1]`、`furniture.position[1]` 悬空或穿入楼板的问题。

流水线原则：

- LLM 只负责生成初稿；空间正确性由 Python 确定性工具兜底。
- 前序结构错误会跳过后续几何校验。
- 修正步骤只在对应检测发现问题时运行。
- 修正后会重跑相关检测。
- ❌ 级别错误要拦截，不把坏 patch 发给前端渲染。
- 所有工具尽量保持纯函数签名 `(blueprint: dict) -> str`，方便后续迁移 LangGraph 节点。

## 9. 运行命令

前端：

```bash
cd wild-web
npm install
npm run dev
# http://localhost:5173
```

前端构建：

```bash
cd wild-web
npm run build
```

后端：

```bash
cd wild-server
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
# http://localhost:8000
```

Docker 本地验证：

```bash
docker compose up -d
# 前端 http://localhost
# 后端 http://localhost:8000

docker compose down
```

后端环境变量使用 Pydantic Settings，文档中提到的关键项：

```text
CHAT__NAME
CHAT__API_KEY
CHAT__BASE_URL
EMBEDDING__NAME
EMBEDDING__API_KEY
EMBEDDING__BASE_URL
```

`.env` 不应提交到 Git；`docker-compose.yml` 会读取 `wild-server/.env`。

## 10. 当前阶段和路线

文档最新路线更新时间为 2026-07-25，当前整体处于 Phase 2 收尾。

阶段总览：

| 阶段 | 状态 | 核心目标 |
|---|---|---|
| Phase 1：前端基础框架 | 已完成 | Vue + Pinia + Three.js + wild-core 渲染管线 + ScenePatch |
| Phase 2：后端 Agent MVP | 接近完成 | FastAPI + LangChain + 18 工具 + 校验流水线，收尾 RAG |
| Phase 3：LangGraph 智能编排 | 待开始 | 并行校验、循环修正、条件路由、自动重试 |
| Phase 4：前端交互与渲染升级 | 待开始 | 3D 拾取、选中高亮、Transform Gizmo、渲染质量升级 |
| Phase 5：AI 组件模块化 | 待开始 | `/component` 命令、AI 构件库、智能吸附、组件持久化 |
| Phase 6：测试部署与稳定化 | 待开始 | pytest、vitest、Playwright、Docker、CI/CD |

当前优先级：

1. RAG 索引向量库：文档增多后按用户意图检索相关规范，减少全量 prompt 注入。
2. 3D 交互增强：点击拾取、选中高亮。
3. Transform Gizmo：平移、旋转、缩放。
4. 消息历史恢复：当前主要恢复场景蓝图，会话消息恢复仍待做。
5. 自动保存：手动编辑后同步后端。

## 11. 后续扩展原则

短期：

- 更多空间校验工具，例如柱间距、梁支撑。
- 优化 System Prompt。
- 前端解析 Agent 回复中的 JSON。
- 规范文档 hot-reload。

中期：

- `RAGSpecLoader` 替代 `FileSpecLoader`，保持 `load() -> str` 接口不变。
- 用 LangGraph 改造 `app/agent/graph.py`，把线性流水线改成图节点。
- 增加语义级校验工具、设计建议工具、一键整理工具。

长期：

- 截屏二次检测：前端截图，视觉模型判断渲染是否符合参数意图。
- MCP 集成：地形、气候、真实建筑规范等外部数据。
- 多 Agent：生成、校验、设计顾问分工。
- World Agent：从建筑编辑器扩展到可自治演化的世界生成平台。

扩展时保持这些接口稳定：

- `SpecLoader.load() -> str`
- Tool 函数签名 `(blueprint: dict) -> str`
- `AgentService.query_structured(...)` 面向传输层的语义接口
- `ws_agent.py` 传输协议
- `.wild` / ScenePatch 的数据边界

## 12. 修改代码时的建议入口

前端相关：

- 场景状态或渲染触发：`wild-web/src/stores/sceneStore.ts`
- Patch 语义：`wild-web/src/wild/scenePatch.ts`
- Blueprint 校验：`wild-web/src/wild/sceneValidator.ts`
- 3D 渲染适配：`wild-web/src/renderer/*`
- 视口交互：`wild-web/src/components/viewport/CanvasViewport.vue`
- AI 对话 UI：`wild-web/src/components/panels/AIChatPanel.vue`
- Agent 通信：`wild-web/src/agent/agentBridge.ts`

后端相关：

- WebSocket 协议和消息分发：`wild-server/app/api/ws_agent.py`
- 场景文件 REST：`wild-server/app/api/scenes.py`
- Agent 服务核心和流水线：`wild-server/app/services/agent_service.py`
- 空间检测/修复工具：`wild-server/app/tools/spatial_tools.py`
- Prompt：`wild-server/app/agent/prompts.py`
- 模型配置：`wild-server/config.py`、`wild-server/app/agent/model_client.py`
- 规范加载 / RAG 接口：`wild-server/app/spec/loader.py`
- Blueprint / Patch 文本提取：`wild-server/app/utils/blueprint_parser.py`

文档相关：

- 总架构：`架构设计方案.md`
- 当前状态：`项目进展总结.md`
- 路线：`docs/项目阶段路线文档.md`
- 前后端协议：`wild-web/docs/FRONTEND_API.md`
- 语言规范：`wild-web/wild-lang/*`
- Agent 生成规范：`wild-server/storage/knowledge_base/*`

## 13. 已知文档差异

这些差异后续遇到时不要误判：

- 有些旧文档写空间工具是 16 个；源码当前是 18 个，包含 `fix_element_elevations`。
- `wild-web/README.md` 的“待实现功能”部分有旧状态描述；更新状态以 `项目进展总结.md`、`docs/项目阶段路线文档.md` 和源码为准。
- 架构文档中 REST API 早期设计写过 `POST /api/scenes` 和 `POST /api/validate`，当前源码校准到 `GET/PUT/DELETE /api/scenes` 为主；是否补齐接口需要看当前需求。
- `wild-server/README.md` 目前为空。

## 14. 做任务前的快速检查清单

1. 明确本次改动属于前端、后端、语言规范、引擎还是部署。
2. 先看对应文档，再看关键源码入口。
3. 若是场景修改能力，优先检查是否应该通过 ScenePatch。
4. 若是 AI 生成质量问题，优先看 `prompts.py`、知识库规范和 `spatial_tools.py`，不要先改前端渲染。
5. 若是渲染错位，先确认 Blueprint 是否合法，再判断是 `wild-core`、renderer 适配还是 Three.js 视口问题。
6. 若新增构件，路线是：规范文档 -> TypeScript 类型 -> `wild-core` geometry builder -> renderer / validator -> Agent 知识库。
7. 改完前端至少跑 `npm run build`；改后端至少跑相关 Python 测试或最小导入/接口 smoke test。

