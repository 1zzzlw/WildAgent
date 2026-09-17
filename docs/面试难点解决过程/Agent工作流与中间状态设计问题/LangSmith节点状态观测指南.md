# 一个完整 Thread 的三段 Trace 与 State 累加过程

> 版本说明：本文主体保留了 2026-09-15 改造前 Trace 的逐节点证据，因此其中的 `execution_plan.steps`、`plan_executor`、`current_plan_step_id` 和 `plan_next_node` 用于解释旧问题，不代表当前代码结构。
>
> 改造后的 Plan Mode 主链为：`planning_research → planner → plan_validator → plan_review → architecture → material_plan → design_review → skeleton → 动态组件 → merge → final_validate → END`。阅读新 Trace 时，重点跟踪 `dynamic_tasks → structured_requirements → 节点业务产物 → acceptance_results`，并用 `execution_progress` 查看固定阶段进度。
>
> **后续结论（2026-09-17）**：本文 §8.3 记录的「批准文本进入 Prompt，但候选由评分选择」已不再是当前行为——
> 候选数组、评分选择与违规检查已整体删除，`architecture` 只输出唯一最终方案。该节保留为问题现场证据。
> 详见同目录《候选机制清理与proposal节点处置方案.md》。

同一次 LangGraph Thread 因为两次人工审核，被分成了三份 Trace：

```text
第一段：trace-01a0a28f-21f2-7892-8b76-32840a0f15e0.json
第二段：trace-01a0a295-09c0-7190-bb1f-99c44d28d353.json
第三段：trace-01a0a299-4c2b-7b22-85fd-1b735b53dc03.json
```

目标不是介绍整个 LangSmith，而是看懂这次执行中：**每个节点收到了什么、产生了什么，
这些字段又为什么会进入 `GenerationState`。**

## 1. 一眼看完整流程

本次输入：

```yaml
user_message: 生成一个别墅
plan_mode: true
thinking_mode: true
```

本次 Trace 实际执行的主路径：

```text
classifier
  → planning_research
  → planner
  → plan_validator
  → plan_review（第一次暂停）
  → plan_executor
  → architecture
  → plan_executor
  → material_plan
  → design_review（第二次暂停）
  → plan_executor
  → skeleton
  → door/window/roof 并行生成与校验
  → merge
  → plan_executor
  → final_validate
  → plan_executor
  → __end__
```

这只是本次 Trace 真正走过的路径，不等于 `graph.py` 中所有可能分支。本次本地知识已经满足
规划需要，所以没有进入 `web_research`；两次人工审核都被批准，因此没有走修改回路；最终校验
直接通过，所以没有进入 `callback`。

当前开启 Plan Mode 后的完整业务流程还包括以下条件分支和回路：

```text
classifier
  → planning_research
      ├─ 本地知识充分 → planner
      ├─ 需要联网补充 → web_research → planner
      └─ 失败 → END
  → planner
  → plan_validator
      ├─ 校验失败 → END
      └─ 校验通过 → plan_review（人工暂停）
  → plan_review
      ├─ 批准 → plan_executor
      ├─ 要求修改 → planner
      └─ 终止 → END
  → plan_executor
      ├─ 收到执行中反馈 → planner
      ├─ step 失败、依赖不满足或能力未注册 → END
      ├─ steps 全部完成 → END
      └─ 选择下一条固定 step
           ├─ architecture → plan_executor
           ├─ material_plan → design_review
           │    ├─ 修改方案 → architecture
           │    ├─ 审核通过 → plan_executor
           │    └─ 终止 → END
           ├─ skeleton
           │    → 根据 suggested_components 动态派发组件
           │    → 各组件 gen → val
           │    → merge → plan_executor
           ├─ merge → plan_executor
           └─ final_validate
                ├─ 存在可修复问题 → callback → final_validate
                └─ 校验结束 → plan_executor
```

这里需要特别区分：最终 Blueprint 仍由 `architecture`、`material_plan`、`design_review`、
`skeleton`、动态组件 `gen → val`、`merge`、`final_validate` 和 `callback` 等业务节点完成。
Plan Mode 增加的是研究、计划审核、固定 step 调度和执行中反馈重规划，并没有替换这套生成能力。

`dynamic_tasks` 也不是完全没有被使用：architecture 和 material_plan 会把相应 phase 的任务文本
加入 Prompt。但是它不参与节点调度，skeleton 和组件链也没有稳定地逐条消费它，最终校验不会
逐条执行其中的自然语言 `acceptance`。因此它当前属于“部分间接影响生成”，而不是“完整控制
执行与验收”。

下面先分析第一段 Trace 的 State 累加，后面再继续第二段和第三段。

第一段的累加过程：

| 时刻 | 新增字段 | 覆盖字段 | 累计字段数 |
|---|---|---|---:|
| 进入 `classifier` | 初始输入和两个空组件映射 | 无 | 5 |
| `classifier` 后 | 7 个意图与风格字段 | 无 | 12 |
| `planning_research` 后 | 7 个研究字段 | 无 | 19 |
| `planner` 后 | 8 个执行计划字段 | 无 | 27 |
| `plan_validator` 后 | `error`、`execution_plan_validation` | `execution_plan`、`execution_plan_status` | 29 |
| `plan_review` | 暂停，无输出 | 无 | 29 |

对应关系就是：

```text
S0 = 初始有效 State
S1 = S0 + classifier 输出
S2 = S1 + planning_research 输出
S3 = S2 + planner 输出
S4 = S3 + validator 新字段 + validator 覆盖字段
plan_review 读取 S4，然后暂停
```

下面逐个看。

## 2. S0：进入 classifier 前

根 Run 的 Input 只有用户提交的三个字段，但 `classifier` 的 Input 是：

```yaml
user_message: 生成一个别墅
plan_mode: true
thinking_mode: true
component_fragments: {}
component_diagnostics: {}
```

后两个空字典不是用户填写的。它们在
[`GenerationState`](../../../wild-server/app/agent/state.py) 中配置了 Reducer，用于后面合并
并行组件结果，所以本次运行开始时表现为空映射。

```text
S0 = 5 个字段
```

## 3. classifier：模型分类，代码补充来源和风格

### 模型的判断

模型 `reasoning_content` 的核心意思是：

```text
“生成”直接匹配 GENERATE；当前没有可编辑场景，所以不是 EDIT；
用户也不是在询问知识，所以不是 CHAT。
```

模型最终 `content` 只返回：

```json
{
  "intent": "generate",
  "confidence": 0.9,
  "target": "别墅",
  "requires_scene": false,
  "reason": "用户要求生成一个新建筑，匹配GENERATE关键词且无现有场景。"
}
```

### 节点写入 State

[`classifier_node`](../../../wild-server/app/agent/nodes/classifier_node.py) 把模型字段转换成
State 字段，并用后端代码补充两项：

```yaml
intent: generate                         # 来自模型 intent
intent_confidence: 0.9                   # 来自模型 confidence
intent_target: 别墅                      # 来自模型 target
intent_requires_scene: false             # 来自模型 requires_scene
intent_reason: 用户要求生成一个新建筑……  # 来自模型 reason
intent_source: llm                       # 后端记录结果来源
style_preference:                        # 后端风格注册表推荐，不是模型输出
  - modern
  - chinese
  - eco_contemporary
```

用户没有指定风格。`modern/chinese/eco_contemporary` 只是风格注册表给出的候选，其中
`modern` 是无关键词命中时的默认优先项，不能理解成用户已经批准了这些风格。

```text
S1 = S0 + 上面 7 个字段 = 12 个字段
```

### 为什么进入 planning_research

路由 `_classifier_dispatch` 读取：

```yaml
intent: generate
plan_mode: true
```

因此返回 `planning_research`。路由结果只代表下一个节点，不会写入 State。

## 4. planning_research：本地检索，不调用模型

这个节点没有 LLM 子 Run。它读取用户需求和当前场景，然后查询本地 WILD 知识。

本次没有 `current_blueprint`，因此场景统计为：

```yaml
element_count: 0
component_count: 0
```

本地检索获得了 11175 个字符，但代码只把前 6000 个字符写入 State：

```yaml
plan_research_context: <6000 字符的知识上下文>
plan_research_summary: 知识上下文 11175 字；当前场景 0 个结构元素、0 个组件
plan_research_diag:
  rag_chars: 11175
  rag_error: null
  element_count: 0
  component_count: 0
  total_ms: 349
  coverage:
    coverage_ratio: 0.0
    sufficient: false
    missing_required:
      - component.parameters
      - recipe.assembly
    trigger_web_research: false
research_missing_topics: []
research_queries: []
web_research_context: ""
web_research_diag: null
```

`11175` 和 `6000` 不矛盾：前者是原始检索长度，后者是实际保存到 State 的截断长度。

`sufficient=false` 但 `trigger_web_research=false` 也不是状态丢失。当前代码认为缺少的是本地
WILD 实现规则，网络资料不能替代引擎自身能力，所以不会自动联网，也就没有生成
`research_queries`。

```text
S2 = S1 + 上面 7 个研究字段 = 19 个字段
```

路由 `_planning_research_dispatch` 看到 `trigger_web_research=false`，所以直接进入
`planner`。State 不变。

## 5. planner：模型提议任务，后端编译计划

这是本次 Trace 最重要的节点。

### 5.1 先分清 `reasoning_content` 和 `content`

用户贴出的：

```json
[{"type": "text", "text": "{...summary...tasks...}"}]
```

是模型最终 `content` 的消息包装，不是 `reasoning_content`。真正的思考内容在 Trace 的
`additional_kwargs.reasoning_content` 中。

之前文档把两个位置合在一句话里说明，导致“花园”看起来没有依据。准确说法是：

- `reasoning_content` 中出现了“经典的两层别墅，带有一个车库和花园”；
- 最终 `content` 没有“花园”，而是把它具体写成了“后院”；
- 后续判断应以最终 `content` 和节点 Output 为准，而不是以思考草稿为准。

### 5.2 这些设计内容实际写在哪里

它们确实进入了最终 `content`，只是分散在嵌套字段中：

| 内容 | 最终模型输出中的位置 |
|---|---|
| 两层、车库、现代住宅 | `summary` |
| 两层主体、车库、后院 | 第一个任务的 `acceptance[0]` |
| 前廊、屋顶、车库顶 | 第一个任务的 `acceptance[2]` |
| 家具 | `material_plan` 任务的 `objective` 和 `acceptance[1]` |
| 照明 | `material_plan` 任务的 `objective` 和 `acceptance[2]` |
| 阳台或雨篷 | 第二个 `skeleton` 任务的 `acceptance[2]` |

这些都不是用户“生成一个别墅”直接提供的，而是 planner 模型补充的设计假设。

### 5.3 模型真正返回什么

模型最终只返回两个顶层字段：

```yaml
summary: 功能定义-骨架生成-细节填充-规范校验……
tasks:
  - architecture: 功能布局与主体结构设计
  - skeleton: 建筑骨架生成
  - architecture: 屋顶与竖向交通设计
  - skeleton: 门窗与建筑细部添加
  - material_plan: 材料规划与内部配置
  - final_validate: 全面规范性校验与修正
```

每个任务中有：

```text
title、objective、phase、acceptance、basis
```

模型没有返回 `plan_id`、状态、版本、依赖、权限、固定步骤和安全约束。

### 5.4 后端如何加工模型输出

[`normalize_dynamic_tasks()`](../../../wild-server/app/agent/planning/execution.py) 会：

1. 过滤非法阶段和不完整任务；
2. 按 `architecture → material_plan → skeleton → final_validate` 重新排序；
3. 生成任务 ID 和前后依赖；
4. 补充 `status=pending` 和 `result_ref=null`。

因此模型任务最后变成：

```text
task_1  architecture     功能布局与主体结构设计   depends=[]
task_2  architecture     屋顶与竖向交通设计       depends=[task_1]
task_3  material_plan    材料规划与内部配置       depends=[task_2]
task_4  skeleton         建筑骨架生成             depends=[task_3]
task_5  skeleton         门窗与建筑细部添加       depends=[task_4]
task_6  final_validate   全面规范性校验与修正     depends=[task_5]
```

随后 `build_execution_plan()` 再补充完整计划：

| `execution_plan` 内容 | 来源 |
|---|---|
| `planner_summary` | 模型的 `summary` |
| `dynamic_tasks` | 模型 `tasks` 经后端整理后的结果 |
| `plan_id/version/goal` | 后端生成 |
| `constraints/assumptions` | 后端固定内容 |
| `steps` | 后端固定白名单，不由模型决定 |
| `status/valid/review_status` | 后端初始状态 |

本次没有传 `request_id`，所以计划 ID 使用兜底值：

```yaml
plan_id: plan_unknown
version: 1
```

后端固定生成的可执行步骤是：

```text
planning_research(completed)
  → architecture(pending)
  → material_plan(pending)
  → skeleton(pending)
  → merge(pending)
  → final_validate(pending)
```

这里要区分：

- `dynamic_tasks`：模型针对本次需求提议的任务；
- `steps`：后端真正允许调度的节点。

### 5.5 planner 最终写入 State

```yaml
execution_plan: <编译后的完整计划>
execution_plan_status: draft
execution_plan_review_status: pending
execution_plan_history: []
execution_plan_diag:
  source: llm
  task_count: 6
  prompt_chars: 6776
  recovery: null
  error: null
  token_usage: {input: 3109, output: 1810, total: 4919}
  total_ms: 45173
plan_feedback: ""
current_plan_step_id: ""
plan_next_node: ""
```

空值的原因：这是第一版计划，没有旧计划和修改意见，也还没有进入 `plan_executor` 开始
调度，所以历史、反馈、当前步骤和下一节点都是空的。

```text
S3 = S2 + 上面 8 个计划字段 = 27 个字段
```

模型调用没有失败，因此 `_after_execution_planner` 返回 `plan_validator`。State 不变。

### 5.6 planner 到 State 这一步没有丢内容

对照模型 `content` 和 `execution_plan.dynamic_tasks` 可以确认：`title`、`objective`、
`phase`、`acceptance`、`basis` 都进入了 State。后端只是重新排序，并补充 ID、依赖和状态。

所以问题不是“GenerationState 顶层字段太少”，也不是“planner Output 没有输出所有真实
LangGraph 节点”。State 本来就应该保存业务数据，而不是让模型自由声明代码节点；真正节点
由 LangGraph 图结构和后端 `steps` 白名单共同限制。

到这里能确定的只有：Planner 到 State 之间没有发生任务内容的整体丢失。此时还不能直接判断
这些任务最终是否落实，需要继续沿 Trace 观察：

```text
architecture 是否读取并落实 architecture 阶段任务
→ material_plan 是否落实材质、家具和照明要求
→ skeleton 与组件链是否读取各自任务
→ 任务在什么条件下被标记 completed
→ final_validate 是否逐条检查 acceptance
→ 最终 Blueprint 是否能够提供对应证据
```

因此，接下来的调查问题从“Planner 有没有把内容写入 State”转变为：

> 已经进入 State 的自然语言任务，后续究竟由谁消费，又是根据什么证据判定完成？

## 6. plan_validator：新增校验结果，覆盖计划状态

这个节点不调用模型，只用后端代码检查计划字段、任务数量、阶段、依赖和节点白名单。

本次没有发现问题：

```yaml
execution_plan_validation: []   # 新增字段
error: null                     # 新增字段
```

同时覆盖原来的计划状态：

```yaml
execution_plan.status: reviewing       # draft → reviewing
execution_plan.valid: true             # false → true
execution_plan.review_status: pending  # 不变
execution_plan_status: reviewing       # draft → reviewing
```

所以：

```text
S4 = S3
   + error
   + execution_plan_validation
   + 覆盖 execution_plan
   + 覆盖 execution_plan_status
   = 29 个字段
```

校验通过只说明计划结构和白名单合法，不代表“两层、车库、屋顶”等设计内容已经被建筑
节点执行。

因为没有错误，`_after_execution_plan_validator` 返回 `plan_review`。State 不变。

## 7. plan_review：读取 S4，然后暂停

`plan_review` 收到的关键状态是：

```yaml
execution_plan.status: reviewing
execution_plan.valid: true
execution_plan.review_status: pending
execution_plan_status: reviewing
execution_plan_review_status: pending
execution_plan_validation: []
error: null
```

计划有效，因此节点调用 `interrupt()` 等待：

```json
{"action": "confirm"}
```

或者：

```json
{"action": "revise", "feedback": "需要修改的内容"}
```

这份 Trace 停在用户选择之前，所以：

```text
plan_review.outputs = {}
plan_review Run.error = GraphInterrupt(...)
GenerationState.error = null
```

`GraphInterrupt` 是正常暂停，不是业务失败。由于节点还没有恢复，它没有写入新 State，
根 Run 的最终 Output 就是 S4 的 29 个字段。

### 没看到 END，不等于执行失败

`END` 是 LangGraph 的虚拟终点，通常不会像 `classifier`、`planner` 一样产生一个可展开的
业务 Run。因此不能用“Trace 里有没有 END 节点”判断成功或失败。

如果 Resume 后的新 Trace 最后显示在 `plan_executor`，需要查看它的 Output：

| `execution_plan_status` | `plan_next_node` | 含义 |
|---|---|---|
| `executing` | `architecture` 等业务节点 | 执行器已选出下一节点；如果 Trace 真正终止在这里，需要继续查异常或取消原因 |
| `revising` | `planner` | 收到了新反馈，进入重新规划，不是建筑生成重试 |
| `completed` | `__end__` | 所有计划步骤已完成，正常结束 |
| `failed` | `__end__` | 计划失败，同时应存在具体 `error` |

按照本次计划，`planning_research` 已经是 `completed`，用户批准后第一个可执行步骤应该是
`architecture`。所以正常的首次 `plan_executor` Output 应包含：

```yaml
execution_plan_status: executing
plan_next_node: architecture
current_plan_step_id: step_architecture
```

后续两份 Trace 已经确认，首次 `plan_executor` 的实际输出正是上述三个值。

## 8. 第二段 Trace：批准计划后运行到设计审核

文件：

```text
trace-01a0a295-09c0-7190-bb1f-99c44d28d353.json
```

根 Input 只有一条 Resume 命令，但 checkpoint 恢复了第一段结尾的 29 个 State 字段。因此
`plan_review` 仍能收到完整 S4，不需要用户重新提交之前的 State。

本段累加过程：

| 节点 | State 变化 | 累计字段数 |
|---|---|---:|
| `plan_review` 恢复 | 覆盖 4 个计划审核字段 | 29 |
| `plan_executor` | 覆盖 4 个调度字段 | 29 |
| `architecture` | 新增 8 个建筑设计字段，覆盖 3 个计划字段 | 37 |
| `plan_executor` | 覆盖 4 个调度字段 | 37 |
| `material_plan` | 新增 2 个材质字段，覆盖 5 个已有字段 | 39 |
| `design_review` | 第二次暂停，没有输出 | 39 |

### 8.1 plan_review 恢复

Resume 输入是：

```json
{"action": "confirm"}
```

因此节点把计划改为：

```yaml
execution_plan.status: approved
execution_plan.review_status: approved
execution_plan_status: approved
execution_plan_review_status: approved
plan_feedback: ""
```

这些都是覆盖原值，没有增加顶层字段。路由随后进入 `plan_executor`。

### 8.2 第一次 plan_executor

执行器发现 `planning_research` 已完成，下一个依赖已满足的固定步骤是
`architecture`，因此输出：

```yaml
execution_plan_status: executing
plan_next_node: architecture
current_plan_step_id: step_architecture
```

这一步证明批准后的计划确实传到了执行器，而且执行器正常选择了建筑方案节点。

### 8.3 architecture：批准文本进入 Prompt，但候选由评分选择

模型的 `reasoning_content` 明确读到了计划中的信息：

```text
两层主体、车库及后院
屋顶与竖向交通设计
候选风格 modern、chinese、eco_contemporary
```

模型生成了两个候选：

| 候选 | 主要结果 | 分数 |
|---|---|---:|
| 0 | 现代矩形，`12m×10m`，2 层，平屋顶 | 81 |
| 1 | 新中式 L 形，`14m×12m`，2 层，中式曲面屋顶 | 86 |

后端记录：

```yaml
architecture_diag.selected_index: 1
architecture_diag.candidate_scores: [81, 86]
```

因此最终 `architecture_plan` 是第二个候选：

```yaml
profile: residential_lowrise
concept: 新中式院落别墅
massing:
  shape: l_shape
  width: 14.0
  depth: 12.0
  floors: 2
  floor_height: 3.2
roof:
  type: chinese_curved
  overhang: 1.2
required_components: [door, window, roof]
```

`architecture` 新增的八个顶层字段是：

```text
architecture_plan、complexity_profile、architecture_diag、design_document、
resolved_design、design_review_status、design_feedback、design_material_refresh
```

同时 `_planned_node` 把 `architecture` 计划步骤标记为 `completed`，并将结果引用记录为
`architecture_plan`。

这里可以直接看到第一个难点的具体表现：批准计划中的两层和车库进入了模型 Prompt，最终
方案也保留了它们；但“现代住宅”“如 gable 类型”等文字没有形成确定性选择约束，评分器
最终选择了分数更高的新中式曲面屋顶方案。上游文本没有丢失，但它没有全部变成候选选择时
必须执行的结构化条件。

### 8.4 第二次 plan_executor 与 material_plan

`architecture` 完成后，执行器选择：

```yaml
plan_next_node: material_plan
current_plan_step_id: step_material_plan
```

本次材质节点没有调用 LLM。诊断值是：

```yaml
catalog_count: 0
procedural_catalog_count: 0
skipped_llm: true
used_fallback: true
error: null
total_ms: 3
```

因此 `material_plan` 来自确定性回退方案，而不是模型输出。它新增：

```text
material_plan
material_diag
```

并同步更新 `design_document`、`resolved_design` 以及计划步骤状态。生成的材质角色包括墙面、
结构、地板、门、玻璃和屋顶等，其中玻璃使用了 `transmission/ior/thickness` 等物理字段。

### 8.5 design_review 第二次暂停

材质完成后进入 `design_review`。此时设计文档仍是：

```yaml
revision: 1
status: draft
design_review_status: pending
```

节点再次调用 `interrupt()`，所以第二段 Trace 正常停在这里；根 Run 没有错误，累计 State
为 39 个字段。

## 9. 第三段 Trace：批准设计后运行到 END

文件：

```text
trace-01a0a299-4c2b-7b22-85fd-1b735b53dc03.json
```

本段从确认 `design_review` 开始，最终正常结束：

| 节点 | State 变化 | 累计字段数 |
|---|---|---:|
| `design_review` 恢复 | 只覆盖设计审核字段 | 39 |
| `plan_executor` | 选择 `skeleton` | 39 |
| `skeleton` | 新增 7 个骨架字段 | 46 |
| 三个组件生成节点 | 新增 3 个生成诊断，Reducer 合并分片 | 49 |
| 三个组件校验节点 | 新增 3 个校验诊断，Reducer 更新分片 | 52 |
| `merge` | 新增 `merged_blueprint`、`merge_diag` | 54 |
| `final_validate` | 新增 12 个最终校验和结果字段 | 66 |
| 最后一次 `plan_executor` | 覆盖计划状态并路由 `__end__` | 66 |

### 9.1 design_review 恢复与 skeleton 调度

用户再次提交 `{"action":"confirm"}` 后：

```yaml
design_document.status: approved
design_review_status: approved
design_feedback: ""
```

执行器随后选择：

```yaml
plan_next_node: skeleton
current_plan_step_id: step_skeleton
```

### 9.2 skeleton：发生了确定性回退，但不是重试

skeleton 模型的思考内容正确识别了：

```text
新中式 L 形布局
2 层，层高 3.2m
西翼、南翼和车库三个体量
材质 ID 与门窗、屋顶职责边界
```

模型返回了一个包含 36 个结构元素的 Blueprint，但后端判断它没有满足结构与方案约束，
于是改用确定性骨架：

```yaml
skeleton_diag.deterministic_fallback: true
skeleton_diag.deterministic_fallback_reason: 模型骨架未满足结构与方案约束
```

从模型输出可以看到，它只生成了 3 块大楼板，而批准方案按三个体量及楼层范围应形成 6 个
体量楼层布局；这能够解释为什么触发方案一致性回退。不过 Trace 只保存了统一的回退原因，
没有保留回退前每一项失败检查，不能把某一项断言为唯一原因。

最终写入 State 的确定性骨架是：

```yaml
结构元素: 22
墙体: 15
楼板: 6
楼梯: 1
墙体包围盒: 14.0m × 6.4m × 12.0m
suggested_components: [door, window, roof]
```

同时生成的 `design_brief` 给出确定性配额：

```yaml
door: 4
window: 22
roof: 1
roof.type: chinese_curved
opening_slots: 26
```

这属于同一个节点内部的“模型结果不合格 → 确定性实现接管”，不是 LangGraph 重试。Trace
中没有第二次 skeleton Run，也没有增加 `retry_count`。

### 9.3 组件并行生成与 Reducer 累加

`_after_skeleton` 根据 `suggested_components` 并行发送三个任务：

```text
door_gen
window_gen
roof_gen
```

三个模型都在思考内容中读取了确定性槽位和配额：

| 节点 | 模型依据 | 输出 |
|---|---|---:|
| `door_gen` | 4 个门槽位，坐标必须原样使用 | 4 个门 |
| `window_gen` | 22 个窗槽位，禁用内部墙开口 | 22 个窗 |
| `roof_gen` | 墙体包围盒和 `chinese_curved` 配额 | 1 个屋顶 |

它们都写 `component_fragments` 和 `component_diagnostics`。Reducer 将三个并行输出合并，
而不是互相覆盖。各自还新增 `door_gen_diag`、`window_gen_diag`、`roof_gen_diag`。

随后三个校验节点全部通过：

```yaml
door_val:   4 个，通过，未修正
window_val: 22 个，通过，未修正
roof_val:   1 个，通过，未修正
```

因此又新增三个 `*_val_diag`，没有触发组件重试。

### 9.4 merge：把骨架和组件合成 Blueprint

合并结果：

```yaml
elements: 23       # 原 22 个骨架元素 + 1 个屋顶元素
components: 26     # 4 个门 + 22 个窗
fragment_summary: 门×4、窗×22、屋顶×1
validation_steps: 20/20 通过
warnings: 0
errors: 0
```

`merge` 新增 `merged_blueprint` 和 `merge_diag`，并把计划中的 `merge` 步骤标记为完成。
随后执行器选择 `final_validate`。

### 9.5 final_validate 与最后一次 plan_executor

最终校验结果：

```yaml
status: complete
error: null
validation_error_count: 0
validation_warning_count: 0
failed_components: []
retry_count: 0
max_retries: 3
final_blueprint:
  elements: 23
  components: 26
```

`retry_count=0` 直接证明最终校验没有进入 callback 重试。

最后一次 `plan_executor` 发现六个固定步骤全部是 `completed`，于是输出：

```yaml
execution_plan_status: completed
plan_next_node: __end__
current_plan_step_id: ""
```

接下来的 `route_execution_plan_executor.output` 确实是 `__end__`。所以界面上最后一个业务
节点显示为 `plan_executor` 是正常的：它的职责就是确认计划完成并路由到虚拟终点。

## 10. 整个 Thread 的最终结论

这次完整执行没有失败，也没有发生 LangGraph 重试：

```text
第一次 GraphInterrupt：等待批准执行计划
第二次 GraphInterrupt：等待批准建筑设计
一次 deterministic_fallback：skeleton 模型结果不合格，由确定性骨架接管
retry_count：0
最终 status：complete
最终 execution_plan_status：completed
最终路由：__end__
```

三个概念必须区分：

| 现象 | 本次是否发生 | 含义 |
|---|---:|---|
| `GraphInterrupt` | 是，两次 | 正常人工审核暂停 |
| `deterministic_fallback` | 是，一次 | 同一节点内部用确定性结果替换模型结果 |
| retry/callback | 否 | 校验失败后重新执行修复流程 |

对于第一个难点，这三份 Trace 已经证明：批准后的 `execution_plan` 没有在节点之间丢失，
planner 的原始任务字段也完整进入了 `dynamic_tasks`。真正薄弱的位置不是 State 容量，而是
计划编译与执行契约：

沿着第二段和第三段 Trace 继续观察后，可以汇总出以下消费关系：

| 计划内容 | 实际消费情况 |
|---|---|
| `phase=architecture` 的文本 | 会追加到 architecture Prompt，但没有编译成评分必须遵守的字段 |
| `phase=material_plan` 的文本 | 会追加到 material Prompt，但材质节点本身不生成家具和灯光 |
| `phase=skeleton` 的文本 | skeleton 当前不调用 `execution_plan_phase_guidance()`，只读取 `architecture_plan` 和 `material_plan` |
| 门窗、阳台、雨篷等要求 | 组件节点只读取 `design_brief`；未进入 `required_components` 或配额的类型不会被派发 |
| `phase=final_validate` 的文本 | 最终校验运行固定校验器，不逐条解释和执行任务的自然语言 `acceptance` |

计划完成逻辑也没有逐条检查验收条件。`complete_execution_step()` 只判断节点是否返回预期
对象，然后把同 phase 的所有动态任务标记为 `completed`。将计划与最终 Blueprint 对照后，
可以看到：

```text
计划要求至少两个房间有家具、关键位置有 light
→ 最终 Blueprint 没有 furniture 和 light
→ material_plan 任务仍被标记 completed

计划要求至少一个 balcony 或 canopy
→ 最终只生成 door、window、roof
→ 对应 skeleton 任务仍被标记 completed

计划要求生成必要的承重柱和联系梁
→ 最终确定性骨架只有 floor、wall、stair
→ skeleton 任务仍被标记 completed
```

这些证据共同说明：自然语言计划成功进入了 State，但没有被完整编译为可执行能力、结构化
需求和验收器。完整过程可以概括为：

```text
丰富的自然语言任务
  → 只按 phase 附加到部分节点 Prompt
  → 没有形成 required_components、结构化设计决定和 acceptance checks
  → 节点只要返回目标对象，就把同 phase 的任务全部标记 completed
```

因此 skeleton Prompt 没有直接读取 skeleton 阶段任务，确实是一个具体缺口；但只修改
Prompt 仍不够，因为确定性回退、组件派发和最终校验也必须消费同一份结构化要求。更准确的
修复方向是把计划任务编译成后端可执行的需求契约，并让节点完成状态取决于验收结果，而不是
仅取决于“是否返回了一个对象”。
