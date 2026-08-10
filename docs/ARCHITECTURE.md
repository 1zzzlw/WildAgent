# WildAgent 架构说明

最后核对：2026-08-10。

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
        │                    ├── RAG + 建筑方案候选/评分
        │                    ├── 受方案约束的骨架与组件生成
        │                    ├── 确定性校验/修正
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
| `wild-web` | Vue 编辑器、状态、会话、交互、3D 展示 | `src/stores/sceneStore.ts` |
| `wild-compiler` | 把门窗、阳台、灯具等组合构件展开为基础元素 | `wild-web/src/wild-compiler/` |
| `wild-core` | 从 Blueprint 确定性重建 MeshData | `wild-web/src/wild-core/` |
| `wild-server` | Agent、RAG、校验、会话和场景文件 API | `wild-server/app/` |
| `wild-lang` | WILD 语言和兼容性契约 | `wild-web/wild-lang/` |

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

后端提供两条执行路径：

- 快速模式：统一 Agent 服务完成生成、修改或问答，适合低延迟请求。
- 精密模式：LangGraph 先生成两个建筑方案候选并确定性评分，再让骨架节点落实所选方案；实际墙体完成后由程序解析立面槽位，组件并行生成只填写槽位允许的门窗，随后进入组件校验、合并、最终校验和按组件重试。编辑和问答走各自短路径。
- 资产模式：独立 `asset_graph.py` 处理 PBR 上传。最短图只做显式参数提取、文件签名/大小校验、内容寻址入库和 ScenePatch 提案，不调用建筑 LLM，也不进入建筑合并节点。
- 材质调优仍属于 EDIT 短路径，不增加新的建筑生成节点。前端选择 ID 会进入快速和精密模式的同一 Patch 上下文；没有选择时不调用模型。模型只能建议基础色、粗糙度、金属度、反照率、自发光、透明度、法线强度和 UV 比例，服务端随后按当前材质与实际纹理通道检查其是否安全且能产生效果。

两条路径必须共享相同安全出口：

- `agent_delivery.py` 统一负责复检去重、最终错误门禁、安全文件名、保存和成功摘要。
- 精密模式在组件派发前先修复/阻断无效骨架（例如墙高为零）；`merge` 只做快速、确定性的归并和语义门禁。门窗局部坐标、父墙范围、同墙重叠、设计数量/立面开口约束及材质引用必须在最终交付前全部成立。合并耗时短不代表校验被省略。
- 骨架节点计算结构墙机器可读包围盒，并把墙体局部方向/法向、墙长、楼层标高组成 `spatial_invariants` 写入 LangGraph 状态。动态 `Send` 会把同一状态交给组件节点，组件 Prompt 必须服从这些确定性坐标，不得重新猜测宿主墙方向。
- `architecture_plan` 只表达体量、层数、立面轴网和屋顶意图；`resolve_facade_layout()` 才把它绑定到真实 wall id 并生成精确 `opening_slots`。`merge` 会对门窗二次吸附、补足设计下限并剔除无槽位开口，避免并行节点各自猜坐标造成漏门、错窗或重叠。
- 组件专用工具执行修复后，必须立即调用同一校验器复检。诊断分别记录“是否执行修复”和“复检是否通过”；前者不能替代后者，复检失败会以错误步骤进入后续全局修复与最终保存门禁。
- RAG 诊断保留实际命中的来源、标题和分类元数据，并随请求级步骤事件发送到前端，避免只能看到“召回了多少字符”却无法追溯知识来源。
- 建筑资料不能直接复制进向量库。知识文档先按 `building_type/component/recipe/pattern` 分类，再以真实标题和 `rag-meta` 拆成 definition、assembly、constraints 等业务块；Loader 只负责保护表格/JSON、长度兜底和增量索引。居住建筑扩展知识已按 20 个独立类型入库，既有别墅、普通住宅、农家宅院和度假木屋继续走原详细配方，避免同一实体重复召回。
- 最终校验把工具文本拆为稳定的 `ValidationIssue`：错误码、校验器、实体 ID/类型、消息、修复模式和建议工具。同一实体的多条错误全部保留，无法绑定实体的全局设计错误不会被误交给局部修复模型。
- 修复分两级：可确定的问题继续由 `fix_*` 工具直接处理；仍有歧义的问题进入 callback，模型只能输出白名单修复动作，程序在 Blueprint 副本上执行。动作只能修改本轮失败实体，禁止改写 `id/type`、引用不存在的父墙或材质；设计配额明确缺少某类构件时，可通过 `design:<type>` 目标受限调用 `add_entity`，不能任意新增组件。
- callback 候选必须经过完整复检。只有错误数量严格下降且没有引入新的“错误码 + 实体”组合时，才把修改同步回骨架或组件分片；否则候选自动回滚。该 JSON 动作协议不依赖某个供应商的原生 tool-calling，便于更换模型。
- OpenAI-compatible 流式响应的结构化产物优先从 `content` 提取，仅在失败时从 `reasoning_content` 兼容回退；解析器按 Blueprint/ScenePatch 结构选择完整 JSON，而不是依赖第一个 Markdown 代码块。
- 模型响应适配层同时接受旧版字典和新版 OpenAI SDK 的 Pydantic `ChatCompletion/ChatCompletionChunk` 对象；业务节点不得直接假定响应存在 `.get()`，避免 RAG 已召回但问答在响应转换阶段失败。
- 完整生成只有最终校验为 `complete` 且错误数为 0 时才能保存并加载；快速和精密模式不能各自绕过门禁。
- 增量修改只返回 ScenePatch 提案，不直接改场景。
- 问答只返回文本，不伪装成思考流或蓝图产物。
- 草稿或失败会话没有场景文件时，前端不得猜测 `/api/scenes/{session_id}.wild`；只有服务端返回权威 `filename/file_url` 后才能请求场景，避免把“尚无产物”表现成 404 加载故障。

## 6. API 边界

| 通道 | 路径 | 用途 |
|---|---|---|
| WebSocket | `/ws/agent` | Agent 请求、步骤、思考/进度、诊断和产物事件 |
| REST | `/api/scenes` | `.wild` 文件列表及新旧路径兼容 CRUD |
| REST | `/api/sessions` | 会话元数据与列表 |
| REST | `/api/sessions/{id}/messages` | 会话消息历史 |
| REST | `/api/sessions/{id}/turns` | Agent Turn 快照与中断恢复 |
| REST | `/api/assets/pbr` | 上传并注册 PBR 纹理集，返回资产/材质 ScenePatch |
| REST | `/api/assets` | 查询已入库的不可变 PBR 资产清单 |
| REST | `/api/assets/{assetId}/files/{filename}` | 按长缓存策略读取本地纹理；以后可由 CDN 地址替代 |

具体 Agent 事件见 [Agent 与 AI 对话设计](AGENT_AND_CHAT.md)。

## 7. 架构评价

当前设计方向合理，尤其是 `.wild` 单一事实源、AI 与几何引擎隔离、ScenePatch 确认机制、确定性校验出口和 LangGraph 分片生成。这些边界能把模型的不确定性限制在结构化、可检查的范围内。

当前已经补齐协议版本、统一保存门禁、Turn 恢复、定向修复闭环、建筑方案/立面槽位分工、Core 重建诊断、墙体语义 UV 和 PBR 单材质入库/渲染闭环。主要技术债是：快速/精密模式仍有意图分类与事件适配重复，尚缺按真实蓝图量化的建筑审美评测，会话元数据、Turn、消息和 `.wild` 尚未形成事务；PBR 也尚未接入外部搜索、AI 生成、自动通道处理、对象存储与 Blender。当前停点和人工门禁见 [优化路线](ROADMAP.md)。
