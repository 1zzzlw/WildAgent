# WildAgent 架构说明

最后核对：2026-10-15。

## 1. 产品与边界

WildAgent 是 AI 辅助的参数化 3D 建筑编辑器。AI 负责理解需求并生成结构化参数，确定性引擎负责几何重建，用户负责最终确认和编辑。

四条边界必须保持：

- `.wild` Blueprint 是场景唯一事实来源。
- `wild-core` 只做解析、空间求解与几何重建，不依赖 Vue、Three.js 或 Agent。
- 前端负责编辑状态、ScenePatch、交互和渲染适配，不发明新的 WILD 语义。
- Agent 只生成 Blueprint 或 ScenePatch，不生成 Three.js 代码或三角网格。

## 2. 系统结构

```text
自然语言 / 手动编辑
        │
        ├── WebSocket ──> wild-server Agent
        │                    ├── 意图分类
        │                    ├── RAG + 建筑或物件设计 + 材质方案
        │                    ├── 设计审核 + 任务展开
        │                    ├── 构件实现 + 对账重规划
        │                    ├── 装配 + 全量校验/有限修正
        │                    └── Blueprint / ScenePatch
        │
        └── ScenePatch ──> sceneStore ──> Blueprint
                                          │
                                          v
                          wild-compiler（组合构件展开）
                                          │
                                          v
                          wild-core（确定性几何重建）
                                          │
                                          v
                          renderer ──> Three.js 场景
```

| 模块 | 主要职责 | 权威入口 |
|---|---|---|
| `wild-core` | **独立包**（与 wild-server / wild-web 同级）：从 Blueprint 确定性重建 MeshData，不依赖 Vue / Three.js / Agent | `wild-core/src/index.ts` |
| └ `compiler` | `wild-core` 子模块：把门窗、阳台、灯具等组合构件展开为基础元素 | `wild-core/src/compiler/` |
| `wild-web` | Vue 编辑器、状态、会话、交互、3D 展示 | `src/stores/sceneStore.ts` |
| `wild-server` | Agent、RAG、校验、会话和场景文件 API | `wild-server/app/` |
| WILD 契约 | 语言规范与机器可读 Schema（原 `wild-web/wild-lang/` 已删除） | `docs/specs/WILD_BLUEPRINT_SPEC.md`、`wild-core/schema.json` |

## 3. 核心数据模型

### Blueprint

`.wild` 是 JSON 文档，核心包含 `meta`、`geometry`、`materials`、可选的 `assets` 与 `behaviors`，编辑器私有状态放在 `editor`。`geometry.elements` 保存基础构件，`geometry.components` 保存可编译的组合构件。PBR 材质通过 `materials.<id>.textureSet` 引用 `assets.<assetId>`；图片二进制不属于 Blueprint。

### ScenePatch

所有增量编辑使用 ScenePatch：

```text
patch_id + base_revision + source + mode + operations
```

`base_revision` 必须匹配当前场景版本。Agent 修改使用 `mode=proposal` 和 `requires_confirmation=true`，前端确认后才调用 `sceneStore.applyPatch()`；手动编辑可以直接生成并应用用户 Patch。

现有纹理的智能调优使用专用 `tune_material` 操作，而不是让模型重写完整材质。操作只携带选中实体、实体已有材质字段、新材质名和受控数值差异；前后端应用器从当前 Blueprint 克隆源材质、覆盖差异并重新绑定选中实体。这样图片 URL、通道、`textureSet` 和其他材质元数据由程序继承，模型无法修改，使用同一旧材质的其他实体也不会被连带改变。

### 会话与场景文件

- 会话元数据、消息与 Agent Turn：`wild-server/storage/sessions/`。
- 场景蓝图：`wild-server/storage/scenes/YYYY-MM-DD/{session_id}_{name}.wild`。
- 浏览器保留消息和 Agent Turn 的本地副本，服务器快照是刷新及跨设备恢复入口。
- 同一会话的 Turn 快照按发送顺序串行写入，避免旧 `running` 快照覆盖新 `completed` 状态。
- 页面刷新遗留的本地 `running` Turn 会恢复为“已中断”；服务重启后，不属于当前服务实例的服务端 `running` Turn 也会被标记为中断。
- 持久化生成任务携带 `_pipeline_version`。服务升级后，仍停在旧 Graph 拓扑的运行中或待审核任务会被标记失败并提示重新发起，禁止恢复到已经删除的节点。
- 迟到的 WebSocket 事件按 `request_id + session_id` 路由，不能覆盖用户已切换到的当前画布。

### PBR 资产

- 图片本体：`wild-server/storage/assets/{assetId}/`，生产环境必须挂载持久化目录；以后可替换为对象存储/CDN。
- 资产清单：不可变 `assetId`、内容哈希、来源、授权、纹理通道 URL、MIME、字节数和通道哈希。
- Blueprint：只复制清单与 `textureSet` 引用，因此 `.wild` 可读、可比较，不会因 Base64 急剧膨胀。
- 兼容策略：旧 `.wild` 的 `embeddedImage/textures` Base64 仍可读取；新入库流程只生成 `encoding=url`。

## 4. 前端数据流

```text
Agent WebSocket event
  -> agentBridge（协议、request/session 路由、产物加载顺序）
  -> agentStore（消息、Turn、步骤、诊断、会话）
  -> AIChatPanel / AgentExecutionPanel

Blueprint / ScenePatch
  -> sceneStore
  -> 重建 Worker
  -> wild-compiler
  -> wild-core
  -> renderer
```

关键原则：网络逻辑集中在 `agentBridge`，领域状态集中在 Store，组件只负责展示和用户动作。蓝图产物加载完成后，正式回复才同步到会话历史，避免消息先完成而场景仍在加载的竞态。

重建不是黑盒成功/失败：`wildCoreAdapter` 在组合构件展开和 Core 重建后生成 `ReconstructionReport`。报告把源构件 ID 映射到临时 Core 元素及实际网格包围盒，并记录它与宿主墙/楼板/屋顶的预期关系。缺失网格、与宿主分离、屋顶覆盖不足以结构化 `EngineDiagnostic` 进入校验面板；这里只诊断，不在前端静默修改几何。重建级 `error` 会让场景加载返回失败；ScenePatch 提交遇到该错误时恢复上一版 Blueprint 和网格，错误实体不会被当作成功修改。

墙体几何不再用整张网格的一次平面投影处理所有表面。`wild-core` 按每个三角面的朝向生成硬边法线和以米为尺度的逐面 UV，因此墙正反面、顶面与门窗洞口侧壁保持一致纹理密度；曲墙也携带沿弧长展开的 UV。Three.js 适配层同时提供 `uv1/uv2` 兼容 AO 通道，并按实际 GPU 上限设置纹理各向异性。

墙角闭合保持“蓝图中心线不可变”：空间解析器只对竖向范围重叠、端点相接、近似 90° 的直线墙写入运行时 `_jointExtensions`，每端按相邻墙半厚延伸渲染网格，并同步平移墙洞局部切口。相邻楼层不会互相参与墙角延伸；斜角墙和曲墙暂不自动延伸，避免用视觉修复破坏结构语义。门窗的世界位置仍按原始 `from/to` 中心线计算。

门窗深度统一继承父墙。门框和窗框的默认 `frameDepth` 等于父墙 `thickness`；门扇默认厚度为 `min(0.04, frameDepth)`，玻璃默认厚度为 `min(0.012, frameDepth)`。门扇和玻璃由零厚平面升级为封闭实体网格，编译器会阻止面板厚于边框、框体过度突出或法向偏移导致门窗与父墙完全分离。

阳台采用单一组合构件表达：`balcony` 自身负责悬挑板和 U 形栏杆，模型不得再为同一阳台生成独立楼板与栏杆。编译器根据宿主墙相对建筑水平包围盒中心的位置推断外侧方向，`depth` 始终从墙面向室外悬挑；合并阶段会按楼板足迹清理与阳台重合的重复楼板及其附属栏杆，并移除依附在首层地坪上的入口栏杆，避免阳台进入室内、栏杆叠加和入口被封堵。

视口统一使用 sRGB 输出、ACES 色调映射、RoomEnvironment、白天/黄昏/夜晚光照和软阴影。相机按水平/垂直 FOV 与模型包围盒取景，而不是固定乘一个距离；阴影相机只覆盖建筑附近，地面阴影随模型最低标高移动，从而在不盲目提高贴图分辨率的情况下改善阴影密度和初始构图。

## 5. 后端数据流

生成、编辑与问答都进入持久化 LangGraph。请求模式可以影响执行参数，不再分别维护两套意图分类和生成入口。

```text
main.py
  → api/ws_agent.py
  → services/generation_job_service.py（持久化任务、暂停恢复、事件分发）
  → agent/graph.py
      ├─ classifier → chat / patch → END
      ├─ architecture → material_plan → design_review → plan
      └─ object_design → material_plan → design_review → skeleton → plan
  → execute ⇄ replanner
  → 建筑 compile / 物件合并 → final_validate
  → services/agent_delivery.py（保存与交付）
```

建筑 `plan` 按批准图纸的构件标记展开任务；物件分支保留模型分组策略。审核可以返回设计节点修订。节点与路由以 [graph.py](../wild-server/app/agent/graph.py) 为准，文件职责见 [Agent 入口说明](../wild-server/app/agent/README.md)。

| 层 | 职责与边界 |
|---|---|
| `api/` | 接收请求、管理连接、适配事件；不承载生成算法 |
| `services/` | 任务持久化、会话、共享模型/知识服务、场景保存与资产存储 |
| `agent/` | 图编排、意图、设计、任务执行、校验与修复 |
| `contracts/` | 公共输入选项与前后端事件协议 |
| `design/` | DesignDocument、图纸投影、宿主和构件关系；`architecture_plan` 是兼容投影 |
| `llm/` | 模型创建、调用、流式响应适配和服务异常分类 |
| `spec/`、`rag/` | 知识加载、索引、检索、安全门控、引用与运行追踪 |
| `tools/`、`utils/` | 工具实现与通用 Blueprint 操作 |

意图分类失败不再尝试旧单标签或关键词分类。额度、鉴权、超时等调用异常，以及缺少 JSON 或非法意图，都返回终止信息；后续生成节点不会继续执行。

设计审核展示 DesignDocument 与 SVG。批准后的构件实现结果进入统一装配和候选校验，检查宿主引用、开口位置、楼梯洞口与已支持的设计关系。明确批准的位置、尺寸和材质意图不能被静默改写。

候选检查、确定性修复与模型修复分别保留结果和原因，复检针对最终采用的同一份 Blueprint。校验完成不代表视觉验收完成；仍需核对批准图纸、最终蓝图与真实渲染。

已有 Blueprint 可以作为带错误说明的草稿保存并尝试渲染，失败状态仍然保留。没有蓝图时不虚构产物，没有权威 `filename/file_url` 时前端不猜测场景路径。增量编辑返回待确认的 ScenePatch，应用失败应恢复原场景。

PBR 上传使用独立的 [assets/graph.py](../wild-server/app/agent/assets/graph.py)，不进入建筑主图；材质调优使用 EDIT 分支。视觉评价与修订工具位于 `agent/vision/`，需要单独调用。

## 6. API 边界

| 通道 | 路径 | 用途 |
|---|---|---|
| WebSocket | `/ws/agent` | Agent 请求、步骤、思考/进度、设计审核、诊断和产物事件 |
| REST | `/api/scenes` | `.wild` 文件列表及新旧路径兼容 CRUD |
| REST | `/api/sessions` | 会话元数据与列表 |
| REST | `/api/sessions/{id}/messages` | 会话消息历史 |
| REST | `/api/sessions/{id}/turns` | Agent Turn 快照与中断恢复 |
| REST | `/api/assets/pbr` | 上传并注册 PBR 纹理集，返回资产/材质 ScenePatch |
| REST | `/api/assets` | 查询已入库的不可变 PBR 资产清单 |
| REST | `/api/assets/{assetId}/files/{filename}` | 按长缓存策略读取本地纹理；以后可由 CDN 地址替代 |

具体 Agent 事件见 [Agent 与 AI 对话设计](agent/AGENT_AND_CHAT.md)。

## 7. 架构评价

当前设计方向合理，尤其是 `.wild` 单一事实源、AI 与几何引擎隔离、ScenePatch 确认机制、确定性校验出口和 LangGraph 分片生成。这些边界能把模型的不确定性限制在结构化、可检查的范围内。

当前主要需要持续验证的是设计落实与真实渲染的一致性、会话和文件保存的一致性，以及实际模型调用成本。API 的事件编排和部分生成模块仍较大，后续拆分应依据具体职责与可运行的回归。当前阅读入口与依赖边界见 [代码阅读路线](代码阅读路线.md)，不要把目录整理等同于生成质量已经通过验收。
