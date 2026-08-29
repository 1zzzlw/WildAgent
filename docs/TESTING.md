---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_7f35cae09b6d11f18cca525400e6dd8f
    ReservedCode1: lsXf74jQCJUk3l8ByUIDjSbUWCOKHwys3seD1SmzqMBWdswS/rVcDRbI6cIaVOC27ZwwtZDv3d7VSRLszAXaR0ttPQKd700N5Clqmb0kbhjkNEZppiPuDFh4iqDOy0cb4NZLaMOhafjoyE670CLdoL35yhz/54SNK9NZ8kG3ti5w9XRIvS1FhDIGtnY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_7f35cae09b6d11f18cca525400e6dd8f
    ReservedCode2: lsXf74jQCJUk3l8ByUIDjSbUWCOKHwys3seD1SmzqMBWdswS/rVcDRbI6cIaVOC27ZwwtZDv3d7VSRLszAXaR0ttPQKd700N5Clqmb0kbhjkNEZppiPuDFh4iqDOy0cb4NZLaMOhafjoyE670CLdoL35yhz/54SNK9NZ8kG3ti5w9XRIvS1FhDIGtnY=
---

# 测试文件使用指南

最后核对：2026-08-26。本文覆盖仓库内当前可见的自动化测试、评测脚本、图展示工具和人工模型冒烟文件。命令默认使用 Windows PowerShell；路径从仓库根目录 `E:\AgentProject\WildAgent` 开始。

## 1. 测试分层

| 层级 | 是否适合作为门禁 | 是否需要模型或外网 | 用途 |
|---|---:|---:|---|
| `wild-server/tests/**/test_*.py` | 是 | 否 | 后端确定性单元与集成回归 |
| `wild-web/scripts/check-*.mjs` | 是 | 否 | 前端核心、编译器、渲染与状态集成回归 |
| `wild-web` 生产构建 | 是 | 否 | TypeScript、Vue 和 Vite 构建检查 |
| `scripts/rag/eval_retrieval.py --embedding hash` | 建议用于知识库变更的本地冒烟 | 否 | 固定题集验证 RAG 分片、过滤与评测流程 |
| `tests/misc/show_langgraph_graph.py` | 结构变更时使用 | HTML 渲染需要 CDN | 校验并展示实际编译的 LangGraph |
| `wild-server/test_graph_minimal.py` | 否 | 是 | 真实模型完整图人工冒烟 |

前端以 `build`、`check:core`、`check:compiler` 和 `check:rendering` 四条命令共同作为最低门禁。不要在文档中长期写死 passed 数量；新增或删除测试后数量会变化，应以当次命令的退出码和报告为准。

GitLab 在 Merge Request 以及 `main/master` 分支运行三组 validate 门禁：前端四项最低门禁、建筑生成质量门禁（Plan2Build/平面审核/材质/恢复与空间校验）和 RAG 质量门禁。Docker 构建与生产部署仍只允许 `main/master`，避免功能分支误发布。

## 2. 日常完整回归

后端依赖由项目虚拟环境管理，`pytest` 通过 uv 临时提供，不会写入生产依赖：

```powershell
cd E:\AgentProject\WildAgent\wild-server
uv sync
uv run --with pytest python -m pytest tests -q
```

前端：

```powershell
cd E:\AgentProject\WildAgent\wild-web
npm install
npm run build
npm run check:core
npm run check:compiler
npm run check:rendering
```

只运行一个后端文件或一个用例：

```powershell
cd E:\AgentProject\WildAgent\wild-server
uv run --with pytest python -m pytest tests/network/test_generation_job_service.py -q
uv run --with pytest python -m pytest tests/network/test_generation_job_service.py::GenerationJobServiceTest::test_restart_recovers_running_job_and_replays_events -q
```

不要使用不带路径的 `pytest`。它会额外收集后端根目录的 4 个旧异步脚本；这些脚本需要真实模型、执行时间和输出都不稳定，也不属于自动化门禁。

## 3. 后端自动化测试逐文件说明

以下文件统一使用：

```powershell
cd E:\AgentProject\WildAgent\wild-server
uv run --with pytest python -m pytest <文件路径> -q
```

| 文件路径 | 作用 |
|---|---|
| `tests/agent/test_agent_delivery.py` | 验证 Blueprint 交付入口：复检覆盖初检、错误结果禁止保存、保存异常分类，以及成功结果的文件引用和回复格式。 |
| `tests/agent/test_agent_graph_execution.py` | 使用真实编译图和隔离节点验证 `GENERATE`、`EDIT`、`CHAT` 三条执行分支。 |
| `tests/agent/test_agent_graph_routing.py` | 验证意图路由、生成先进入建筑方案、组件建议过滤、否定词处理及阳台栏杆去重。 |
| `tests/agent/test_model_errors.py` | 验证额度、鉴权、限流等模型服务异常会转换为稳定中文协议，并与组件建筑校验错误分流。 |
| `tests/components/test_floor_plan_design.py` | 验证平面设计节点的模型输出、确定性回退、SVG 门窗图例和逐层预览。 |
| `tests/components/test_floor_plan_review.py` | 验证第一次人工审核可直接确认、修改意见返回同一平面节点，以及预审失败自动重画两轮后有限暂停。 |
| `tests/components/test_style_review.py` | 验证主体完成后的第二次风格确认和修改循环。 |
| `tests/components/test_spatial_plan.py` | 验证 FloorPlanIR v2 的矩形、多矩形 L/U 形、斜墙、曲墙、多边形、中庭、跨层空间、全层电梯井自动补全与确定性几何装配。 |
| `tests/components/test_plan2build_pipeline.py` | 验证 ApprovedPlanAssembler 的确定性、G1-G6、三种 StylePackage、Decor IR、G7，以及中庭和六层住宅 Golden 样例。 |
| `tests/components/test_architecture_plan.py` | 验证建筑方案候选评分、中文层数识别、高层示意几何、公共建筑尺度、立面槽位、开口配额和地下交通建筑约束。 |
| `tests/blueprint/test_blueprint_material_validation.py` | 验证 Blueprint 字段归一化和 Schema：楼板坐标、墙高简写、primitive box 尺寸、家具别名、材质颜色，以及程序化红砖的范围、互斥和可执行字段门禁。 |
| `tests/blueprint/test_blueprint_text_extraction.py` | 验证从普通内容、`reasoning_content`、代码围栏和常见包装对象中提取 Blueprint/ScenePatch，并补齐确定性元数据。 |
| `tests/repair/test_callback_targeted_repair.py` | 验证 callback 只提交能减少错误的白名单动作、设计配额补件、立面超额开口移除，以及模型调用异常时保留逐目标重试计数并终止。 |
| `tests/components/test_component_blueprint.py` | 验证组件 Schema、组件和 element 共用 ID 命名空间、门窗 depth 字段，以及组件的增删改 Patch。 |
| `tests/components/test_component_state_reducer.py` | 验证 LangGraph 并行组件节点通过通用 State reducer 合并结果，不依赖硬编码字段白名单。 |
| `tests/components/test_component_validation_recheck.py` | 验证组件修复后必须复检、复检失败不能伪报成功、布尔值 `false` 不等于缺失。 |
| `tests/misc/test_deployment_preflight.py` | 验证部署预检默认不访问供应商、显式真实模式才调用 Chat/Embedding，并覆盖模型冒烟响应的 content/reasoning 兼容选择。测试本身不访问模型。 |
| `tests/network/test_generation_job_service.py` | 验证生成任务脱离 WebSocket 后继续、两类人工审核暂停与恢复、事件落库、重启恢复、补发顺序和终态原子落库。 |
| `tests/misc/test_ip_geolocation.py` | 验证 IP 脱敏、GeoIP 缺失回退、可信代理头和伪造代理头防护。 |
| `tests/misc/test_langgraph_checkpoint_resume.py` | 使用临时 SQLite checkpointer 验证恢复时跳过已完成节点，只重跑失败或未完成节点。 |
| `tests/assets/test_material_tuning.py` | 验证材质优化意图、必须先选择构件、Patch 安全边界、材质克隆、纹理资产保留和无效参数拒绝。 |
| `tests/components/test_material_plan.py` | 验证 AI 材质方案只能选择真实且角色匹配的 PBR 资产或受控程序化红砖、一图 PBR 候选识别、Shader 预设与语义等级展开、稳定 seed、未知 ID 清理、图片资产优先、物理玻璃预设和骨架引用闭合。 |
| `tests/repair/test_merge_precision.py` | 验证合并阶段的空间硬约束：世界/局部坐标修复、开口重叠阻断、配额缺失和阳台重复几何清理。 |
| `tests/assets/test_model_client_compat.py` | 验证 OpenAI-compatible 对象响应、内容块、空 content + reasoning 以及非流式响应的兼容转换。 |
| `tests/assets/test_pbr_assets.py` | 验证 PBR 资产图、本地内容寻址存储、单张 Base Color 入库、旧清单默认值兼容、公开 URL 前缀更新、上传 API 和材质 Patch 引用闭合。 |
| `tests/misc/test_prompt_composition.py` | 验证最小规范只注入一次、RAG 查询与业务 metadata 过滤、构件检索词和角色材质要求。 |
| `tests/rag/test_rag_index_sync.py` | 验证 RAG 增量同步：未变分片跳过、正文或 metadata 更新、删除陈旧分片、相邻父分片扩展及多查询去重。 |
| `tests/rag/test_rag_semantic_chunking.py` | 验证 Markdown 语义分片、标题路径和业务实体 metadata、JSON/表格原子性、README 范围推断与上下文上限。 |
| `tests/misc/test_readiness.py` | 验证 `/health/ready` 在 RAG 启用、禁用、降级和索引就绪状态下的响应。 |
| `tests/misc/test_reasoning_stream.py` | 验证 reasoning 流式片段保留、回调只转发真实 reasoning，以及思考模型请求参数。 |
| `tests/misc/test_scene_patch_generation.py` | 验证 ScenePatch 提取、格式恢复、reasoning 回退、目标预检、相邻建筑生成和完整 XYZ 场景摘要。 |
| `tests/network/test_session_turns.py` | 验证 Agent Turn 去重持久化，以及服务启动时对当前任务和旧运行任务的中断判定。 |
| `tests/repair/test_skeleton_blueprint_recovery.py` | 验证骨架首次输出无效时改用非思考模型恢复包装 Blueprint，并合并 token 用量。 |
| `tests/validators/test_spatial_invariants.py` | 验证骨架输出的墙体局部坐标系、楼层标高等机器可读空间不变量和墙体包围盒。 |
| `tests/validators/test_spatial_validation.py` | 验证墙高补齐、门窗贴墙与重叠、世界坐标投影、材质引用、碰撞例外和异常向量容错。 |
| `tests/repair/test_targeted_repair_tools.py` | 验证错误结构化、修复目标追踪、动作白名单、ID/类型保护、材质存在性、增删实体范围和错误下降原则。 |
| `tests/validators/test_validation_cache.py` | 验证 merge 已完成且可复用的最终校验不会在 `final_validate` 重复执行。 |
| `tests/validators/test_validation_pipeline_repairs.py` | 验证校验流水线会在最终引用检查前修复唯一材质别名。 |
| `tests/network/test_ws_agent_disconnect.py` | 验证 WebSocket 协议版本、心跳、Presence、快速/精密模式断线后持久恢复、平面审核协议、思考事件和生成结果引用。 |

这些测试使用 mock、临时目录或本地确定性实现，不要求 `.env` 中存在有效模型 Key。Chroma 可能输出一条第三方弃用警告；只要 pytest 退出码为 0，就不影响测试通过。

## 4. LangGraph 图展示与结构检查

文件：`wild-server/tests/misc/show_langgraph_graph.py`。

启动本地页面并自动打开浏览器：

```powershell
cd E:\AgentProject\WildAgent\wild-server
.venv\Scripts\python.exe -B tests\misc\show_langgraph_graph.py
```

只生成 Mermaid 和 HTML 并检查节点，适合 CI：

```powershell
.venv\Scripts\python.exe -B tests\misc\show_langgraph_graph.py --no-serve
```

常用参数：

- `--no-callback`：隐藏校验失败后的 callback 回路。
- `--port 8765`：指定本地展示端口。
- `--output-dir <目录>`：指定 Mermaid 和 HTML 输出目录；默认写入系统临时目录。
- HTML 使用 Mermaid CDN 渲染，浏览器离线时仍可查看生成的 `.mmd` 源码，但图形页面可能无法渲染。

## 5. RAG 专项评测

文件：`wild-server/scripts/rag/eval_retrieval.py`。

```powershell
cd E:\AgentProject\WildAgent\wild-server
.venv\Scripts\python.exe -B scripts\rag\eval_retrieval.py --embedding hash
```

该命令使用当前统一评测集、临时 Chroma 集合和本地 HashEmbeddingFunction，检查真实分片、metadata 过滤和评测流程；不需要 API Key，也不会修改 `storage/chroma`。Hash 模式不代表真实语义召回质量；需要评估真实召回率时，按 `scripts/rag/README_EVAL_RETRIEVAL.md` 使用默认模式或真实 embedding 临时索引。

## 6. 后端根目录人工模型脚本

这些文件不属于自动化套件，不应被无路径 `pytest` 收集。

| 文件 | 原始作用与运行方式 | 当前状态 |
|---|---|---|
| `wild-server/test_graph_minimal.py` | 在 `wild-server` 执行 `.venv\Scripts\python.exe -B test_graph_minimal.py`，调用真实模型跑完整图，并可能写出 `test_output_blueprint.json`。 | 可作为人工模型冒烟；需要有效 `.env`，会产生模型费用，异常被脚本捕获后未必返回非零退出码，不能作为 CI 门禁。 |
需要真实模型的当前验证可使用保留的完整图冒烟脚本，或优先从 WebSocket 精密模式发起；后者与生产使用同一 runtime callback、checkpointer 和事件协议。

## 7. 前端自动检查逐文件说明

### `wild-web/scripts/check-wild-core.mjs`

运行：

```powershell
cd E:\AgentProject\WildAgent\wild-web
npm run check:core
```

作用：临时编译并加载 Wild Core，重建 `lantu/*.wild` 全部样本；检查 mesh、索引、法线、UV、包围盒、版本迁移、primitive box、profile sweep、斜梁方向、侧墙开口、直角墙角、建筑墙属性、程序化红砖参数透传和非法材质回退。临时构建目录在结束时删除。

### `wild-web/scripts/check-component-compiler.mjs`

运行：

```powershell
cd E:\AgentProject\WildAgent\wild-web
npm run check:compiler
```

作用：临时编译组件编译器和前端集成模块，覆盖组件能力、几何评测样本、门窗深度、可交互窗扇与灯具、坡道/檐口/曲墙、缓存、Schema 拒绝、渲染、ScenePatch、材质优化、PBR、撤销历史、Worker 传输、拖拽、生成文件无缓存加载、Presence 和显式保存。

### `wild-web/scripts/check-rendering-pipeline.mjs`

运行：

```powershell
cd E:\AgentProject\WildAgent\wild-web
npm run check:rendering
```

作用：通过 Vite 加载真实渲染模块，验证历史构件兼容模式默认 DoubleSide、已验证封闭实体可显式使用 FrontSide、玻璃使用 `MeshPhysicalMaterial` 及受控 transmission/IOR/thickness、AO 所需 UV，以及程序化红砖 Shader 注入、uniform、材质签名和 Program cache key。

### 生产构建检查

`npm run build` 虽然不对应单一测试文件，但必须与上面两个脚本一起运行。它执行 `vue-tsc -b` 和 Vite 生产构建，用于发现类型错误、模块引用错误和生产打包失败。

## 8. 变更类型与最低测试

| 变更范围 | 最低测试 |
|---|---|
| LangGraph 节点、路由、State | 后端完整回归 + `tests/misc/show_langgraph_graph.py --no-serve` |
| checkpointer、WebSocket、断线恢复 | `tests/network/test_generation_job_service.py`、`tests/misc/test_langgraph_checkpoint_resume.py`、`tests/network/test_ws_agent_disconnect.py` |
| FloorPlanIR、Plan2Build、两次确认 | `tests/components/test_spatial_plan.py`、`tests/components/test_floor_plan_design.py`、`tests/components/test_floor_plan_review.py`、`tests/components/test_style_review.py`、`tests/components/test_plan2build_pipeline.py` |
| Blueprint Schema、空间与校验 | `tests/blueprint/test_blueprint_material_validation.py`、`tests/validators/test_spatial_validation.py`、`tests/repair/test_merge_precision.py`、`npm run check:core` |
| 组件或渲染 | 相关后端组件测试 + `npm run check:compiler` + `npm run check:core` + `npm run check:rendering` |
| RAG 文档、分片、metadata | 两个 RAG 自动测试 + `eval_retrieval.py` |
| 前端 Agent 协议或状态 | 后端 WebSocket 测试 + `npm run build` + `npm run check:compiler` |
| 部署就绪与模型响应兼容 | `tests/misc/test_deployment_preflight.py`、`tests/misc/test_readiness.py`、`tests/assets/test_model_client_compat.py` |

## 9. Checkpointer 部署说明

LangGraph SQLite 文件由服务首次启动自动创建在：

```text
wild-server/storage/sessions/langgraph_checkpoints.sqlite3
```

无需新增环境变量或部署参数。生产 Jenkins 已创建并挂载 `/app/storage/sessions`，本地 Compose 也持久化 `storage`，因此正常进程重启和使用同一数据卷的容器重建都能读取 checkpoint。备份与迁移时应把该 SQLite 文件和对应的 `-wal`、`-shm` 文件视为同一组数据；丢失持久卷后无法恢复未完成任务。
*（内容由AI生成，仅供参考）*
