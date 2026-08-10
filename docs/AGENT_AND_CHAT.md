# Agent 与 AI 对话设计

最后核对：2026-08-10。

## 1. 设计目标

Agent 的价值不是单次输出 JSON，而是把不稳定的模型输出约束为可检索、可校验、可确认、可追踪的建筑操作。对话界面应像 Claude 一样把“用户消息、执行过程、正式回答/产物”放在同一时间线上，但不能混淆三类信息。

```text
用户消息
  └── 本次执行过程（可折叠，运行时展开）
        ├── 节点状态与简短说明
        ├── 模型过程或确定性进度
        ├── 校验结果
        └── 运行诊断（开发信息，二级折叠）
正式回复 / Patch 提案 / Blueprint 加载结果
```

## 2. 意图与执行路径

### 快速模式

`agent_service.query_structured()` 负责三种结果：

- `GENERATE`：完整 Blueprint，经统一校验后保存。
- `EDIT`：基于当前 Blueprint 生成 ScenePatch，经前端确认后应用。
- `CHAT`：建筑知识问答，仅返回文本。

精密模式的 `patch` 节点已经由分类器确定为 EDIT，因此会向统一入口显式声明 `expected_output=patch`，不再让模型二次猜测输出类型。Blueprint 与 ScenePatch 必须由两个独立提取器解析；禁止先以 Blueprint 提取成功作为进入 ScenePatch 分支的条件，否则合法 Patch 因没有 `meta + geometry` 会被稳定丢弃。ScenePatch 可从普通 `content` 或 `reasoning_content` 提取，并兼容 `patch/scene_patch/scenePatch/result/data/output` 包装对象及仅操作数组。首次无法提取时，只追加一次非思考格式恢复调用；恢复仍失败才返回错误。

增量编辑注入的场景摘要必须保留完整 X/Y/Z 坐标和关键尺寸，不能只给墙体 X/Y 而丢掉 Z，否则“在建筑旁边新增”无法确定真实边界。提案应用前先校验操作白名单、必填字段、目标 ID、新增 ID 唯一性以及是否产生实际变化，再在 Blueprint 副本上执行完整校验；前端仍需用户确认后才修改当前场景。模型常用的 `add_material` 会确定性归一化为正式协议的 `upsert_material`（同时兼容 `material_id/id` 到 `name`），发送给前端的始终是标准操作。`patch_diag.structured_source` 记录产物来自 `content/reasoning/recovery_*`，`structured_recovery_used` 标记是否使用了格式恢复。

### 精密模式

```text
classifier
  ├── GENERATE -> skeleton
  │                -> Send(component_gen -> component_val) × N
  │                -> merge
  │                -> final_validate
  │                -> callback（只重试仍可修复的失败组件）
  │                -> END
  ├── EDIT     -> patch -> END
  └── CHAT     -> chat  -> END
```

组件建议在派发前统一过滤：未知或未实现的类型被丢弃，用户明确否定的组件不生成，空建议保留门、窗、屋顶基础集合，阳台的内嵌栏杆不会被无意重复生成。

## 3. 生成安全闭环

```text
LLM 结构化结果
  -> Blueprint 结构预检
  -> 骨架几何预检（墙高等父级结构先修复）
  -> 组件级确定性校验/修正
  -> 合并
  -> 完整最终校验流水线
  -> 有可重试错误？结构化为 ValidationIssue
  -> 模型选择白名单局部修复工具
  -> 程序执行、完整复检、改善才提交
  -> status=complete 且 error_count=0？
       ├── 是：保存 .wild，发送 blueprint_generated
       └── 否：阻止保存和加载，返回可见错误
```

这里的关键点是“最终错误”必须来自修正后的复检结果，不能把已经修复的初检错误继续计入阻断条件。

回调不再让模型重新输出完整组件。模型只能提交类似下面的最小动作，实际修改由程序执行：

```json
{
  "tool": "move_opening",
  "arguments": {"entity_id": "door_front", "along": 3.0, "elevation": 0.0},
  "reason": "将门移动到父墙有效范围内"
}
```

当前白名单包含 `add_entity`、`remove_entity`、`move_opening`、`resize_opening`、`reparent_opening`、`set_material_reference` 和受字段白名单约束的 `patch_entity`。普通动作只允许命中本轮失败实体；已通过实体保持只读。设计错误“墙 `wall_front` 有 4 个门窗”表示该墙挂接了 4 个 `door/window`，不是把墙识别成门窗。结构化问题以墙为约束目标，同时把实际挂接的门窗列为 `related_entity_ids`，并把这些门窗的类型、父墙和几何参数一起交给模型；callback 因而可以定向移动、改挂或删除超额门窗。`remove_entity` 只能删除这个关联列表中的实体，不能删除报错墙体或任意已通过构件。`add_entity` 仅在设计校验产生 `design:<type>` 缺失配额目标时开放，而且新增类型必须与目标一致、ID 必须唯一、父墙必须真实存在。候选修改先在副本运行完整校验和设计配额复检，必须同时满足“错误数严格减少”和“没有新增错误类型/实体组合”，否则整轮回滚。确定性 `fix_*` 工具仍优先于模型，只有需要空间或设计取舍的问题才进入 callback。

合并节点是确定性数据归并与关系复核，不是另一次 LLM 生成；只要输入规模不大，耗时几毫秒是正常现象。精度不能用“等待时间”衡量，而应由以下硬门禁保证：

- 门窗 `from` 的契约固定为 `[沿父墙距离, 底部世界Y, 局部法向偏移]`。第三项不是世界 X/Z，通常必须为 `0`；明显误用世界坐标时先投影回父墙，再归零法向偏移。
- `opening` 基础元素和 `door/window` 组合构件必须同时参与坐标、墙体范围和同墙重叠校验，不能因其中一类为空而跳过另一类。
- 合并结果必须满足设计清单中的组件最小/最大数量，以及每面立面的最大开口数；缺门、缺窗不能以“JSON 已合并”作为成功。
- 构件使用的 `material/frameMaterial/leafMaterial/glassMaterial` 必须存在于 `Blueprint.materials`。
- 确定性修复没有实际改变蓝图时立即停止空转，交给最终校验和按组件回调；错误归零前禁止保存与加载。
- `wall.from[1]` 是墙底、`wall.to[1]` 是墙顶。墙高为零时，在派发门窗节点前优先按上一层楼板标高或已知层高补全；不能让组件回调反复修改门窗去适配一个无效父墙。
- `floor.from/to` 必须是两个三维数组，Y 表示楼板底标高。模型输出坐标对象或漏掉坐标时，只在有效墙体能够确定 X/Z 包围盒和楼层底标高的情况下补全；例如两层墙底标高为 0/3 时，按楼板顺序补为 `[minX,0,minZ] -> [maxX,0,maxZ]` 和 `[minX,3,minZ] -> [maxX,3,maxZ]`。没有可靠墙体边界时继续阻断，禁止根据名称猜尺寸。
- 引用完整性只负责父对象、模板、行为和材质引用；门窗越界与重叠统一由开口几何校验负责，避免同一个根因重复计为两个错误。
- 流式模型若把最终 Blueprint 放入 `reasoning_content` 且普通 `content` 为空，骨架节点允许从 reasoning 兼容提取完整的 `meta + geometry` 对象；提取器同时支持 fenced、未 fenced JSON，以及 `blueprint/result/data` 等常见包装对象，并按对象结构选择 Blueprint。
- 首轮回复已经包含 DESIGN_BRIEF、但 Blueprint 缺失或 JSON 无效时，骨架节点只追加一次非思考格式恢复调用，强制模型只返回单一 Blueprint JSON；恢复仍失败才终止图。前端必须显示 skeleton 的真实错误，不能再用笼统的“最终 Blueprint 缺失”覆盖根因。
- `meta.version`、`meta.type` 和空缺的 `meta.name` 属于可确定元数据，在 Schema 校验前分别补为 `1.1`、`building` 和 `AI生成建筑`；这类非几何字段不再浪费一次模型重试。`meta` 本身不是对象时仍会被结构校验阻断。
- 骨架派发组件前修正唯一可判定的材质简称（如仅存在 `wood_oak` 时将 `wood` 映射到它）；候选不唯一则保留错误并阻断，禁止猜测。

`2026-08-08/session_1786189311071_现代别墅.wild` 是门窗坐标回归样本：`door_back_service.from=[3.4,0,6]` 会被识别为离背墙 6 米，确定性修复结果应为 `[3.4,0,0]`。原始样本还包含未定义的屋顶、门框/门扇和窗框材质引用，新的完整性门禁会阻止其直接下发。

## 4. 前端 Turn 模型

一次用户请求对应一个 `AgentTurn`，主键使用 `request_id`：

```text
AgentTurn
  request_id / session_id / user_message_id
  status / started_at / completed_at / interruption_reason
  steps[]
    node / label / stage / status / detail
    thinking / thinking_channel / diagnostic
  validation_steps[]
  metrics
```

这解决了旧实现的三个问题：

- 不再把所有用户消息排在前面、所有 AI 消息排在后面，时间顺序保持真实。
- 不再用一个绝对定位的全局思考浮层覆盖消息区。
- 用户切换会话后，旧请求的迟到事件仍回到原 session，不会污染当前对话或画布。

`AIChatPanel.vue` 负责统一时间线，`AgentExecutionPanel.vue` 负责单个 Turn 的折叠执行过程。消息、步骤和流式过程共用主时间线唯一滚动容器，步骤内容不再创建嵌套滚动条。时间线尺寸变化后在下一渲染帧贴底；用户向上滚动后自动跟随暂停，只有回到底部、点击“回到最新”、主动发送消息或切换会话时恢复。

callback 每次返回 `final_validate` 都代表一次新的完整复检。前端收到该轮摘要时先清空该 Turn 的旧 `validation_steps`，再写入最新步骤，因此 4 轮各 18 步不会累计显示成“72 步、4 个相同错误”；最终面板只呈现最后一轮的 18 步和真实剩余错误。

每条 ScenePatch 提案消息保存 `pending/applying/applied/rejected/expired` 状态。点击应用时先同步切换为 `applying` 以阻止双击；场景重建成功后标记为 `applied`，按钮显示“已应用”并永久禁用；应用失败才恢复为 `pending`。拒绝或被新提案取代的消息分别标记为 `rejected/expired`，历史消息不能再次应用。

Turn 同时写入浏览器本地副本和 `/api/sessions/{session_id}/turns`。前端按 `request_id` 合并两端快照；同一会话的 PUT 串行执行，保证完成态不会被较早发出的运行态覆盖。页面刷新时，本地未完成 Turn 显示为“已中断”；服务重启后，服务端也会清理不属于当前服务实例的遗留运行态。

## 5. WebSocket 事件契约

当前协议版本为 `1.0`。前后端消息 envelope 都携带 `protocol_version`；服务端拒绝显式声明的不兼容版本，暂时只对未声明版本的旧客户端保留滚动升级兼容。所有请求相关事件必须携带 `request_id`，服务端同时携带 `session_id`。

| 事件 | 角色 | 关键字段 |
|---|---|---|
| `agent_step` | 可见执行步骤 | `stage`, `node`, `status`, `label`, `detail` |
| `thinking_delta` | 流式过程 | `node`, `channel=reasoning|progress`, `delta` |
| `thinking_status` | 过程生命周期 | `status`, `content` |
| `debug_log` | 开发诊断 | `category=node|error|session_metrics`, `data` |
| `patch_proposal` | 增量编辑产物 | `patch` |
| `blueprint_generated` | 完整蓝图引用 | `filename`, `file_url`，不内嵌整份 Blueprint |
| `agent_reply` | 正式回答 | `content` |
| `error` | 请求失败 | `code`, `error` |

`agent_step` 的协议语义只来自 `stage/node/status/label/detail`。`content` 仅保留同义的人类可读文本，前端不再拆分 `node:status:detail` 之类的展示字符串。`blueprint_generated` 只发送文件引用；前端完成拉取和场景重建后，才把本轮正式回复视为完成。

## 6. 内容展示分层

- 默认可见：正在做什么、完成/失败状态、耗时、正式答复。
- 一次展开：每个节点的过程内容和校验摘要。
- 二次展开：RAG 字符数、LLM 耗时、token、重试次数等开发诊断。
- 禁止：把最终回答重复显示在过程区；把确定性工具进度伪装成模型思考；在主时间线上直接输出大段 Blueprint JSON。

模型接口提供 `reasoning_content` 时可以归入 `reasoning` 通道；生产环境更稳妥的做法是保存模型提供的过程摘要，不依赖或强制暴露内部推理。工具校验、合并、保存等内容一律归入 `progress` 通道。

## 7. 失败与竞态规则

- `patch_proposal` 必须等待用户确认，拒绝后不得改动 Blueprint。
- `blueprint_generated` 到达后，前端先拉取并重建场景，再完成正式回复和消息同步。
- 用户在生成期间切换会话时，产物只更新目标会话，不覆盖当前画布。
- 保存失败、文件加载失败、校验未通过都必须把 Turn 标为失败。
- callback 工具动作被拒绝、复检未改善或引入新错误时不得写回源分片；`repair_audit` 必须记录动作、前后错误数和回滚原因。
- WebSocket 中断会把当前连接上的活动 Turn 标为失败并同步；页面刷新或服务重启遗留的运行态恢复为“已中断”。
- 同一会话的 Turn 服务端快照必须串行提交，禁止旧状态覆盖新状态。

## 8. 本地与生产输出一致性

“同一个 Chat 模型和同一句输入”不代表 Agent 的实际输入相同。骨架 System Prompt 还包含 RAG 召回内容，生产与本地必须同时核对：运行镜像提交、`CHAT__NAME/BASE_URL`、`EMBEDDING__NAME/BASE_URL`、`RAG__ENABLED`、`RAG__ALLOW_HASH_FALLBACK`、collection、分块参数和持久化 Chroma 索引。任何一项不同都可能让模型稳定输出不同的几何表达。

骨架日志必须记录 `rag_chars`、实际命中的 `source/heading/doc_type/entity_type`，以及规范化后的每个 floor `from/to`。若本地成功而生产稳定失败，先比较这些确定性诊断；生产 RAG 字符数明显偏小或命中为空时，应检查 Embedding 配置与索引同步，不能仅用“模型名相同”排除环境差异。

生产镜像必须包含 `storage/knowledge_base`。曾经使用整目录 `.dockerignore: storage` 时，Jenkins 虽然上传了 Git 中的 37 个知识文件，Docker 构建仍会把它们全部排除；容器启动后扫描到空知识库，并把持久化 Chroma 旧分片作为 stale 删除，最终只向骨架 Prompt 注入约百字符的“规范文件缺失”提示。本地不经过 Docker 构建所以不会复现。现在只忽略四个运行时子目录，并在镜像构建和部署预检中强制核对知识库数量。
