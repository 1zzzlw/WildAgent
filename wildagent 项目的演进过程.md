# wildagent 项目的演进过程

## RAG 知识库设计

### 知识库的设计

首版的 RAG 知识库中混合了建筑百科、实现规则、风格建议和坐标完备的建筑实例。它们经过检索后一起进入提示词， 大模型很难分清哪些是必须遵守的引擎约束，哪些只是某个案例的选择。 

例如，某篇别墅文档包含固定长宽、楼层、窗位、屋顶和材料。它被检回后，模型可能直接修改这份蓝图，而不再根据本次需求重新组织空间。多个请求反复遇到同一案例，就容易得到相似建筑。 

代码也会强化这种倾向：如果精密模式默认提高体量数量，或风格名称自动触发阳台、凸窗、雨棚组合，即使删掉文档中的模板，生成结果仍可能固定。因此必须一起调整知识内容、检索方式、方案约束和扩库流程。 

因此根据大模型的能力来进行取长补短，大模型已经有了足够的知识储备，那么知识库中就可以不加入建筑百科。模型可能掌握建筑常识，但不了解 WILD 的输入字段、引用与坐标语义，也不了解当前引擎能够可靠表达的构件及其边界。知识库应保留这些项目专属表达规则，不应收录渲染引擎内部实现细节。 总结就是： `知识声明不能代替确定性执行。多样性应来自未限定变量的合理设计，而不能破坏已批准条件。` 

所以知识库应该保留什么，我的思路也就是基于大模型的缺点来对知识库进行设计。核心思路就是： **知识库只保留“模型不能可靠掌握、业务又必须遵守、且能结构化检索”的那部分知识；模型已经会的通用知识不放，模型不需要的引擎细节也不放。** 

以下举出几个内容来一一分析：

1. WILD 协议：告诉大模型，WILD语言应该怎么写

   比如当模型想要生成窗户时，大模型就需要知道，窗户对应的WILD语言的什么字段，坐标，朝向，材质等字段的使用方法

2. 当前的构件能力：告诉大模型，系统现在能生成什么

   比如窗户，阳台，栏杆等构件。但是这里是否和大模型知识库冲突，因为大模型知识库本身肯定就具备了这就构件的描述。不冲突的原因是：大模型知道这些构件的样子，知道怎么描述，但也只是文本语言的描述，如果个别的大模型能力比较弱，那么他就无法独自设计出由WILD语言来表示的这些构件，所以需要一些简单的json示例，来描述一下在这些构件由WILD语言构成是什么样的，但是需要注意的是，知识库中的所有json示例，只能作为示例，不能直接用到创作中。总结就是： `局部 JSON 可以解释字段和引用，但不能以局部示例的名义附带整栋布局。` 

3. 条件组装关系：告诉大模型，选了某个东西后，相关部分怎么组合

   这个主要是为了减少组件的坐标偏移的概率，如：窗户必须在墙上，使用 parentWall 来进行引用。

4. 建筑类型和风格语义、普通百科与风格套话、完整实例与风格策略： 建筑类型与风格语义和普通百科多为模型已知或无法直接指导 WILD 生成的内容，会增加上下文负担；完整实例与固定策略又过于具体，容易被模型照搬，导致建筑模板化，因此三者均应移出活动知识库。 

最后总结：

> 知识内容

1. **操作协议**：解释 ScenePatch 操作、字段和坐标语义。当前 Blueprint 与选中对象由运行状态提供，知识库不能保存本次场景数据。
2. **复杂构件表达**：保留单个构件及必要宿主的最小 JSON，说明可替换参数和当前能力边界。重复而稳定的复杂几何应升级为参数化组件，知识只负责语义映射。
3. **确定性关系**：玻璃材质、宿主引用、楼梯与楼板、空间连通等关系需要文档解释，同时必须在 Schema、compiler、resolver 或 validator 中执行。

> 规则性质

1. **实现约束**：生成的窗必须引用有效的墙宿主，参数符合当前 WILD 契约。
2. **条件约束**：如果方案选择多层交通，就落实相应的楼层连接；如果选择阳台，就检查宿主和通行关系。
3. **设计选择**：是否采用阳台、退台、对称立面，以及使用什么材料，由需求和本次方案决定。

### 知识消费流程设计

**不要让知识库一次性把所有内容塞给模型，而是按节点、按阶段、按需拉取。每个节点只拿它当下需要的那部分知识，执行、产出、暴露缺口，下一个节点再针对缺口精准补齐。通过划分不同职责的Agent节点，明确各阶段需要消费的知识、产生的中间结果及上下游传递关系。**

> 当前仅确定按节点、按阶段、按需消费知识的方向，具体节点检索职责、过滤条件与缺口补全机制将在后续结合实际生成链路继续优化。 







### 知识库的编写方式

**知识库包含大量协议、构件能力与组装规则，人工编写难以保证完整性和一致性，因此我通过提示词设计专用 Skill，由 AI 按统一规范生成、审核和维护知识文档。**

1. 输入依据

   AI编写知识前必须读取WILD Schema、组件注册表、compiler、resolver和validator，以源码确认当前真实能力，不能凭模型自身知识猜测。 

2. 内容分类

   先判断资料属于操作协议、复杂构件表达还是确定性关系；建筑百科、完整案例、固定风格策略和未实现能力不进入活动知识库。 

3. 统一文档结构

    每份知识应说明： 

   * 适用条件
   * WILD字段映射
   * 必要宿主和组装关系
   * 当前能力边界
   * 可自由调整的参数
   * 最小局部JSON示例
   * 信息来源及实现状态

4. 代码与知识同步

    必须遵守的规则不能只写进文档，还要确认Schema、compiler、resolver或validator中存在对应实现；未实现内容进入backlog。 

5. 质量验证

    生成后运行文档检查、分片预览和检索评测，确认知识能够正确召回，不会误召回完整案例或无关风格内容，并同步向量索引。 

> 提示词示例：
>
> 根据提供的资料审查WildAgent当前知识库。先以Schema、组件注册表、compiler和validator核验真实能力，再按操作协议、复杂构件表达和确定性关系分类整理；隔离建筑百科、固定策略与完整实例。必须说明适用条件、WILD映射、能力边界和自由变量，仅保留最小局部JSON。未实现规则进入backlog，不得伪装成现有能力，最后完成分片与检索验证。 编写出一份专门用来补充该知识库的skill。

### 知识库的检索与消费设计 

**通过合理的知识分块、查询改写、检索过滤与节点级知识注入，提高RAG的召回率和准确率，使不同Agent节点能够按阶段获取并充分利用所需知识。通过知识分块、查询改写、过滤和节点级注入，让各节点准确检索并使用所需知识。**  





## Agent的设计模式

**整个项目采用 Agentic System 架构：外层由 Workflow 提供稳定、可控的流程骨架，内层由 Agent 负责灵活决策与执行；Agent 结合 Plan-and-Execute 与 ReAct，先进行粗粒度任务规划，再通过 ReAct 完成细粒度工具调用、反馈判断与动态调整。**

**版本思路设想：**







**一一分析对比：**







##  通过 LangSmith Trace 逐步修正问题判断的过程 

> 在分析 Agent 工作流与中间状态设计问题时，我最初认为问题出在节点之间的状态传递：Planner 已经理解并讨论了用户要求，但这些信息没有完整进入 GenerationState，导致下游节点无法继续使用。为了验证这个判断，我使用 LangSmith Trace 逐个对照节点输入、节点输出以及最终生成结果，并结合代码确认各字段的实际来源和消费位置。随着分析深入，我发现 dynamic_tasks 实际已经完整进入 State，真正的问题并不是“状态没有传下来”，而是这些自然语言任务没有进一步转换成下游节点可以直接消费、程序可以逐条校验的结构化业务约束。下面记录的就是我从最初判断到最终定位问题的完整思考过程。 

**以下以用户输入“生成一个别墅”所产生的一次完整 LangSmith Trace 为例，通过逐步分析各节点的输入、输出与状态变化，验证并定位当前 Agent 工作流中存在的问题。** 

**优化前的完整图流程：**

```
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

**问题描述：**

* 看到 plan mode 的结构后，我最初的理解是： 
  
  * planner 根据用户需求动态解析拆解本次任务；
  
* plan_validator 检查计划是否合法、是否超出系统能力；
  
  * 用户通过 plan_review 审核别墅生成的计划；
  
* plan-executor 按照审核后的计划选择和调度业务节点；
  * 不同用户需求可以形成不同的执行步骤、依赖关系和收验条件；

  `Plan Mode 理论上不只是“在固定流程前展示一次计划”，而应该让审核后的计划对后续执行过程产生真实影响。` 

* 初步发现的问题：

  在阅读当前 LangGraph 图时，我发现 architecture、material_plan、skeleton、merge 和 final_validate 等业务节点的顺序已经由 graph.py 中的节点连接和条件路由确定。 
  
  与此同时，execution_plan 中又保存了一组 steps；plan_executor 会读取这些 steps，选择下一条依赖已经满足的步骤，再将对应节点名称写入 plan_next_node。从而导致系统可能存在两套执行顺序：
  
  ```
  LangGraph 图结构
  负责定义节点之间的固定连接关系
  
  execution_plan.steps
  负责描述步骤、依赖和执行状态
  ```
  
  但这两套顺序看起来高度相似。无论 Planner 为本次需求生成了什么 dynamic_tasks，真正能够执行的业务节点似乎仍然是 LangGraph 中已经注册并连接好的固定节点。 
  
  因此产生了一个疑问：
  
  > Plan Mode 是否真的根据模型生成的计划动态调度业务能力，还是只在固定 LangGraph 工作流外增加了一层计划展示和进度控制？ 
  
  当前 plan_executor 确实按照 execution_plan.steps 选择主业务节点，但 steps 本身不是模型动态生成的，而是后端固定构建的。 

**根据源码分析：**

```python
class ExecutionPlan(TypedDict):
    """经过服务端构建和校验、可由 LangGraph 持久化的执行计划。"""

    plan_id: str  # 由 request_id 生成的计划 ID。
    version: int  # 每次重新规划后递增的版本号。
    intent: PlanIntent  # 当前计划服务的用户意图。
    goal: str  # 结合用户消息生成的总体目标。
    status: ExecutionPlanStatus  # 计划整体执行状态。
    valid: bool  # 是否通过服务端结构与白名单校验。
    review_status: ExecutionPlanReviewStatus  # 用户对当前计划的审核结果。
    constraints: list[str]  # 整个执行计划必须遵守的安全约束。
    assumptions: list[str]  # 对计划含义和执行边界的公开说明。
    planner_source: PlannerSource  # 动态任务来自模型还是确定性回退。
    planner_summary: str  # 模型或回退逻辑给出的计划摘要。
    feedback: str  # 生成当前版本时采用的用户修改意见。
    change_summary: list[str]  # 相对上一版本增加、删除或保留了哪些任务。
    dynamic_tasks: list[ExecutionDynamicTask]  # 本次需求特有、经白名单归一化的任务。
    steps: list[ExecutionStep]  # 服务端固定构建、供执行器调度的安全步骤。
```

ExecutionPlan 是执行计划的结构化类型定义，用于约束 Planner 节点最终写入 GenerationState 的计划对象需要包含哪些字段，以及各字段的数据类型。它只定义计划的数据结构，本身不负责创建计划；具体内容由 build_execution_plan() 构建。 

整体流程大概为：

```
LangGraph 进入 planner 节点
→ execution_planner(state)
→ 调用大模型生成 summary 和 tasks
→ build_execution_plan(...)
→ 构建并返回 ExecutionPlan 类型的 plan 对象
→ execution_planner 返回 {"execution_plan": plan}
→ LangGraph 将结果合并进 GenerationState
→ 进入 plan_validator 节点
→ execution_plan_validator(state)
```

对应的注册节点：

```
graph.add_node("planner", execution_planner)
graph.add_node("plan_validator", execution_plan_validator)
```

这两个节点的调用流程：

```
planner 节点
  └─ execution_planner()
       ├─ 调用 LLM 生成动态 tasks
       ├─ 调用 build_execution_plan()
       └─ 返回 {"execution_plan": plan}

LangGraph 合并 State
  ↓
plan_validator 节点
  └─ execution_plan_validator(state)
```

真正的 plan 执行方法：

```python
async def execution_plan_executor(state: GenerationState) -> dict:
    """在节点边界吸收用户意见，并选择下一条依赖已满足的白名单步骤。"""

    plan = deepcopy(state.get("execution_plan") or {})
    # 执行过程中接收用户追加修改意见的轮询机制
    poller = get_execution_feedback_poller()
    pending_feedback: list[str] = []
    if poller is not None:
        pending_feedback = [
            str(item).strip() for item in await poller() if str(item).strip()
        ]
    if pending_feedback:
        replan_count = int(state.get("plan_replan_count") or 0)
        max_replans = max(0, int(state.get("max_plan_replans") or 3))
        if replan_count >= max_replans:
            plan["status"] = "failed"
            return {
                "execution_plan": plan,
                "execution_plan_status": "failed",
                "plan_next_node": "__end__",
                "error": f"执行计划已达到最大重规划次数 {max_replans}",
            }
        feedback = "；".join(pending_feedback)
        plan["status"] = "revising"
        return {
            "execution_plan": plan,
            "execution_plan_status": "revising",
            "execution_plan_review_status": "revise",
            "plan_feedback": feedback,
            "plan_replan_count": replan_count + 1,
            "plan_next_node": "planner",
            "current_plan_step_id": "",
        }

    if any(
        isinstance(step, dict) and step.get("status") == "failed"
        for step in plan.get("steps", [])
    ):
        plan["status"] = "failed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "failed",
            "plan_next_node": "__end__",
            "error": state.get("error") or "执行计划存在失败步骤",
        }
    if plan_is_complete(plan):
        plan["status"] = "completed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "completed",
            "plan_next_node": "__end__",
            "current_plan_step_id": "",
        }
    step = next_ready_step(plan)
    if step is None:
        plan["status"] = "failed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "failed",
            "plan_next_node": "__end__",
            "error": "执行计划没有可运行步骤，可能存在未满足依赖",
        }
    capability = CAPABILITY_REGISTRY.get(str(step.get("type") or ""))
    if capability is None or str(step.get("node") or "") != capability.node:
        plan["status"] = "failed"
        return {
            "execution_plan": plan,
            "execution_plan_status": "failed",
            "plan_next_node": "__end__",
            "error": "执行计划引用了未注册能力",
        }
    plan = update_plan_step(
        plan,
        capability.type,
        "in_progress",
        detail=f"正在执行：{capability.label}",
    )
    plan["status"] = "executing"
    return {
        "execution_plan": plan,
        "execution_plan_status": "executing",
        "plan_next_node": capability.node,
        "current_plan_step_id": str(step.get("id") or ""),
    }

```

从这里就可以看出来： execution_plan_executor() 不会读取或逐条调度 Planner 生成的 dynamic_tasks。它只根据后端固定构建的 steps 检查失败、判断完成、处理依赖并选择下一业务节点。 而它的主要作用方式就是： `通过自然语言 Prompt 间接影响部分节点，不具备节点调度权，也没有形成贯穿全部生成节点和最终校验的可靠执行契约。` 

```python
phase_guidance = execution_plan_phase_guidance(execution_plan, "architecture")
prompt = append_approved_phase_guidance(
    prompt,
    phase_guidance,
    "这些是公开的任务目标和验收条件。总体方案必须落实它们，"
    "但仍须服从本提示中的结构化输出协议和安全约束。",
)
```

以上是我通过 langsmith trace 发现了 steps 和 dynamic_tasks 两个任务列表，但是后续节点并没有执行 dynamic_tasks ，因为 dynamic_tasks 里面实际上已经包含了大模型总结的内容

```json
{
  "dynamic_tasks": [
    {
      "id": "task_1",
      "basis": "用户未指定具体风格与参数，故设计一个经典的两层带车库别墅，以满足通用居住与审美需求。设计需考虑清晰的动静分区与合理的流线。",
      "objective": "设计别墅的整体空间布局和主体结构，确定层数、主要功能房间位置及大致尺寸，为后续建模提供蓝图。",
      "phase": "architecture",
      "status": "pending",
      "title": "功能布局与主体结构设计",
      "acceptance": [
        "完成包含两层主体、车库及后院的整体功能分区平面草图",
        "确定所有主要墙体的轴线位置和关键高度参数",
        "设计出包含前廊、屋顶和车库顶等特征的建筑体量轮廓"
      ],
      "depends_on": [],
      "result_ref": null
    },
    {
      "id": "task_2",
      "basis": "屋顶是建筑的关键封顶构件，楼梯是两层别墅必需的竖向交通，均为架构阶段核心内容。",
      "objective": "生成别墅的屋顶结构，并规划连接上下层的楼梯，完成建筑的竖向封闭与交通。",
      "phase": "architecture",
      "status": "pending",
      "title": "屋顶与竖向交通设计",
      "acceptance": [
        "生成一个符合规范的屋顶（如gable类型），其span/depth完全覆盖墙体范围",
        "楼梯from坐标Y值小于to坐标Y值，且位置合理连接一层与二层"
      ],
      "depends_on": [
        "task_1"
      ],
      "result_ref": null
    },
    {
      "id": "task_3",
      "basis": "材料定义建筑外观与质感，家具与照明赋予空间生活气息，此阶段集中处理非结构性的视觉与功能填充。",
      "objective": "系统规划建筑外立面、内部地面及家具的材料，并添加必要的室内家具和照明组件。",
      "phase": "material_plan",
      "status": "pending",
      "title": "材料规划与内部配置",
      "acceptance": [
        "为所有墙体、楼板、屋顶、门窗等指定明确的material值",
        "在至少两个房间内布置table、chair等furniture组件",
        "在室内外关键位置添加light组件，并设置基本属性"
      ],
      "depends_on": [
        "task_2"
      ],
      "result_ref": null
    },
    {
      "id": "task_4",
      "basis": "遵循BLUEPRINT-SPEC-MINIMAL中关于全局空间规则和墙体、楼板、柱、梁等基础构件必填字段的要求。",
      "objective": "基于设计布局，精确生成所有基础结构元素（墙体、楼板、柱、梁），确保坐标闭合与尺寸准确。",
      "phase": "skeleton",
      "status": "pending",
      "title": "建筑骨架生成",
      "acceptance": [
        "所有墙体转角处坐标精确共享，无近似值",
        "一层、二层楼板及屋顶范围完整覆盖墙体包围盒",
        "生成所有必要的承重柱和联系梁"
      ],
      "depends_on": [
        "task_3"
      ],
      "result_ref": null
    },
    {
      "id": "task_5",
      "basis": "门窗是建筑功能与立面的重要组成部分，阳台、雨篷等是别墅常见细部，需在骨架基础上进一步细化。",
      "objective": "在主要墙体上生成门和窗户，并添加阳台、雨篷等组合构件，丰富建筑立面与功能。",
      "phase": "skeleton",
      "status": "pending",
      "title": "门窗与建筑细部添加",
      "acceptance": [
        "所有opening和door的`from[0]`参数均为沿墙距离而非世界坐标",
        "窗户和门的尺寸、位置与所在墙面匹配，风格统一",
        "成功添加至少一个balcony或canopy组件"
      ],
      "depends_on": [
        "task_4"
      ],
      "result_ref": null
    },
    {
      "id": "task_6",
      "basis": "这是交付前的强制质检步骤，旨在消除所有Schema枚举陷阱和结构性错误，保证文件可被正确解析和渲染。",
      "objective": "对生成的全部几何与数据进行最终检查，确保其完全符合BLUEPRINT-SPEC-MINIMAL的所有硬性规定。",
      "phase": "final_validate",
      "status": "pending",
      "title": "全面规范性校验与修正",
      "acceptance": [
        "验证roof.roofType为枚举的6个合法值之一",
        "验证所有geometry.components中的类型均为10种组合构件之一",
        "确认不存在任何非法枚举值（如hipped、pitched等）"
      ],
      "depends_on": [
        "task_5"
      ],
      "result_ref": null
    }
  ]
}
```

**总结：**

Planner 生成的动态任务已经进入 State，也会通过 Prompt 间接影响部分设计节点，但没有形成 architecture、material_plan、skeleton、组件生成和最终校验共同遵守的结构化业务契约，导致计划中的要求可能在跨阶段传递、候选选择或最终验收过程中失效。 以上均是未开始优化时的代码，主要展示思考过程，分析过程，更便于后续优化后的代码理解。

**优化之后：**

> 核心思路：从固定步骤到动态任务驱动，保持稳定架构的同时实现精准规划
>
> 优化之前，系统存在两套流程描述：LangGraph 定义固定节点顺序，execution_plan.steps 又重复维护相同流程，而 dynamic_tasks 只作为自然语言提示词注入到节点，无法形成可追踪的业务验收闭环。节点执行完成后，同一 phase 的多个动态任务会被批量标记为完成，系统无法证明每条验收条件是否真正实现。
>
> 本次优化的核心是删除冗余的 steps 调度，将 dynamic_tasks 从软提示升级为硬约束。具体做法是：将 Planner 生成的自然语言任务编译为 structured_requirements（结构化业务约束），明确指定消费节点、校验器和期望值；让 architecture、material_plan、skeleton 等节点直接消费这些约束，而不仅仅是作为参考；在候选选择、归一化和最终校验阶段执行确定性验证，用 acceptance_results 逐条记录实际值与证据；将节点运行进度（execution_progress）与业务验收状态分离，阻止"节点完成但业务要求未满足"的错误交付。
>
> 为了生成建筑的稳定性、可控性和安全性，当前架构仍整体保留 LangGraph 的固定节点设计理念——LangGraph 是唯一的流程事实源，负责安全的执行顺序、条件分支和异常处理。后续的 architecture、skeleton、组件生成等节点并没有重构，而是通过将动态任务的结构化约束注入到各节点的输入中，让节点在执行时能够精准落实已批准的业务要求，并实时追踪每条验收条件的完成情况，将进度和验收结果推送到前端界面。
>
> 这样既保留了固定节点的稳定性和可测试性，又实现了动态任务的精准规划与逐条验收，解决了"上游决定如何稳定传递到下游执行和最终证明"的核心问题。

关键源码：

```python
# 位置：WildAgent\wild-server\app\agent\planning\workflow.py execution_planner

# 把 LLM 的原始输出（可能不规范）转换成标准的 ExecutionPlan 对象。
plan = build_execution_plan(
    request_id=str(state.get("request_id") or "unknown"),
    intent=intent,
    user_message=str(state.get("user_message") or ""),
    research_summary=str(state.get("plan_research_summary") or ""),
    feedback=feedback,
    previous_plan=previous,
    planned_tasks=(raw_payload or {}).get("tasks"),
    planner_source="llm",
    planner_summary=str((raw_payload or {}).get("summary") or ""),
)
# 把自然语言任务编译成结构化约束
requirements = compile_structured_requirements(plan)
# 初始化验收结果
acceptance_results = initialize_acceptance_results(requirements)

# 关键逻辑
def build_execution_plan(...):
    # 1. 版本管理
    version = previous_version + 1  # 每次重规划版本号+1
    
    # 2. 设定安全约束（硬性规则）
    constraints = [
        "实际节点顺序只能由 LangGraph 定义",  # ← 防止模型生成节点
        "完整校验未通过不得保存"
    ]
    
    # 3. 生成计划目标
    goal = f"生成建筑：{user_message}"
    
    # 4. **核心转换**：normalize_dynamic_tasks()
    dynamic_tasks, used_fallback = normalize_dynamic_tasks(
        planned_tasks,  # ← LLM 原始输出
        user_message, 
        intent
    )
    # → 输出规范的任务列表
    
    # 5. 记录变更（如果是重规划）
    if previous_plan:
        change_summary = ["新增任务: ...", "移除任务: ..."]
    
    # 6. 返回完整 ExecutionPlan
    return {
        "plan_id": "plan_xxx",
        "version": 1,
        "intent": "generate",
        "goal": "...",
        "status": "draft",
        "dynamic_tasks": dynamic_tasks,  # ← 规范化后的任务
        "constraints": constraints,
        ...
    }


def normalize_dynamic_tasks(raw_tasks, user_message, intent):
    # ========== 第 1 步：设定规则 ==========
    allowed_phases = {
        "architecture", 
        "material_plan", 
        "skeleton", 
        "final_validate"
    }  # ← 白名单：只允许这些阶段
    
    minimum = 3  # 最少 3 个任务
    maximum = 8  # 最多 8 个任务
    
    # ========== 第 2 步：逐个检查 LLM 输出 ==========
    normalized = []
    for raw in raw_tasks:
        phase = raw["phase"]
        title = raw["title"]
        objective = raw["objective"]
        
        # 检查 1：phase 在白名单内吗？
        if phase not in allowed_phases:
            continue  # ← 跳过不合法的任务
        
        # 检查 2：必填字段都有吗？
        if not title or not objective:
            continue  # ← 跳过不完整的任务
        
        # 检查 3：acceptance 是列表吗？
        acceptance = raw.get("acceptance", [])
        if not acceptance:
            acceptance = ["完成对应校验"]  # ← 兜底
        
        # 通过检查，加入规范列表
        normalized.append({
            "title": title,
            "objective": objective,
            "phase": phase,
            "acceptance": acceptance,
            "basis": raw.get("basis", "用户需求")
        })
    
    # ========== 第 3 步：判断是否需要 fallback ==========
    required_phases = {"architecture", "final_validate"}  # 必须有的阶段
    phases = {task["phase"] for task in normalized}
    
    # 条件 1：任务数量太少？
    # 条件 2：缺少必需阶段？
    used_fallback = (
        len(normalized) < minimum or 
        not required_phases.issubset(phases)
    )
    
    if used_fallback:
        # 放弃 LLM 输出，使用确定性生成
        normalized = fallback_dynamic_tasks(user_message, intent)
    
    # ========== 第 4 步：排序（按阶段固定顺序） ==========
    phase_order = {
        "architecture": 0,
        "material_plan": 1,
        "skeleton": 2,
        "final_validate": 3
    }
    normalized.sort(key=lambda task: phase_order[task["phase"]])
    
    # ========== 第 5 步：生成稳定 ID 和依赖关系 ==========
    tasks = []
    for index, task in enumerate(normalized, start=1):
        task_id = f"task_{index}"
        tasks.append({
            "id": task_id,  # ← 稳定 ID
            **task,
            "depends_on": [f"task_{index-1}"] if index > 1 else [],
            "status": "pending",
            "result_ref": None
        })
    
    return tasks, used_fallback

该方法经过了层层检查，主要是预防 llm 出现以下问题，主要是为了防止大模型的幻觉产生
问题 1：LLM 可能生成 "phase": "render"，但系统没有这个节点？ → 白名单拦截
问题 2：LLM 可能漏掉 objective 字段？ → 质量检查过滤
问题 3：LLM 完全失败，返回空列表？ → Fallback 保底
问题 4：任务顺序错乱？ → 固定排序



def compile_structured_requirements(plan):
    requirements = []
    
    # 遍历每个任务的每条验收条件
    for task in plan["dynamic_tasks"]:
        for acceptance in task["acceptance"]:
            # 核心：编译单条 acceptance
            req = _compile_acceptance(
                task_id, 
                description,  # ← "至少两个房间有家具"
                phase
            )
            requirements.append(req)
    
    return requirements

# _compile_acceptance() 做什么？
输入：自然语言描述
"至少两个房间包含家具"
输出：结构化约束 StructuredRequirement(TypedDict)
{
    "id": "req_furniture_room_count",
    "source_task_id": "task_3",
    "source_acceptance_id": "acc_3_2",
    "description": "至少两个房间包含家具",
    "phase": "component_generation",
    "kind": "component_all",  # ← 约束类型
    "target": "blueprint.components.furniture",
    "operator": "gte",  # ← 大于等于
    "expected": {"types": ["furniture"], "minimum": 2},
    "consumers": ["furniture_generator", "final_validate"],
    "validator": "furniture_room_count",  # ← 校验器名称
    "severity": "error",
    "support_status": "supported"  # ← 当前系统支持
}

# 关键词匹配 + 白名单
def _compile_acceptance(task_id, index, description, phase):
    # 1. 关键词识别
    if "家具" in description or "furniture" in description:
        kind = "component_all"
        target = "furniture"
    
    if "至少" in description and "房间" in description:
        operator = "gte"
        expected = {"types": ["furniture"], "minimum": 2}
    
    # 2. 查白名单，确定消费者和校验器
    if kind == "component_all" and target == "furniture":
        consumers = ["furniture_generator", "final_validate"]
        validator = "furniture_room_count"
        support_status = "unsupported"  # ← 当前不支持家具
    
    # 3. 如果无法编译
    if not validator:
        support_status = "unsupported"
        validator = "none"
    
    return StructuredRequirement(...)

# 为每条结构化约束创建一个待验收的结果记录。
def initialize_acceptance_results(requirements):
    results = {}
    
    for requirement in requirements:
        # 根据支持状态，初始化不同状态
        if requirement["support_status"] == "unsupported":
            status = "unsupported"
            message = "当前系统不支持"
        elif requirement["support_status"] == "needs_review":
            status = "not_checked"
            message = "需要人工确认"
        else:
            status = "pending"
            message = "等待执行"
        
        # 创建验收记录
        results[requirement["source_acceptance_id"]] = {
            "acceptance_id": "acc_3_2",
            "task_id": "task_3",
            "requirement_id": "req_furniture_room_count",
            "status": status,  # ← 初始状态
            "expected": requirement["expected"],  # ← 期望值
            "observed": None,  # ← 实际值（还没验证）
            "validator": "furniture_room_count",
            "evidence_refs": [],
            "message": message
        }
    
    return results

三者流程图：
LLM 原始输出
    ↓
【A】build_execution_plan()
    ├─ normalize_dynamic_tasks()
    └─ 生成规范的 dynamic_tasks
    ↓
【B】compile_structured_requirements()
    ├─ _compile_acceptance()（关键词匹配 + 白名单）
    └─ 生成 structured_requirements
    ↓
【C】initialize_acceptance_results()
    └─ 为每条要求创建初始验收记录
    ↓
各节点消费约束 → 执行 → 更新 observed → 验证
```

已理解 plan 的制定流程，接下来学习 plan 如何被执行：各业务节点如何消费结构化约束，以及如何验收结果。

```python
# 主要的包装函数
def _planned_node(step_type: str, node):
    """在业务节点边界记录展示进度并执行结构化验收。"""

    async def run(state: GenerationState) -> dict:
        # 执行原始业务节点
        result = node(state)
        if inspect.isawaitable(result):
            result = await result
        result = dict(result or {})
        # 完整阶段验收
        result.update(await complete_execution_stage(state, step_type, result))
        return result

    run.__name__ = f"planned_{step_type}"
    return run

# 路由开始节点，从 architecture 节点开始，因为 plan 模式生成的动态任务也是按照节点的顺序来排序的。
graph.add_conditional_edges(
    "plan_review",
    route_execution_plan_review,
    {
        "__end__": END,
        "architecture": "architecture",
        "patch": "patch",
        "planner": "planner",
    },
)

# architecture 节点的关键函数，分为4个阶段来看
async def architecture_planner(state: GenerationState) -> dict:
    # 第一阶段：理解输入
    user_message = state["user_message"] # 获得用户的原始需求
    revision_feedback = str(
        # state.get("design_feedback")
        # 触发节点：architecture → material_plan → design_review → 回到 architecture
        # state.get("plan_feedback")
        # 触发节点：planner → plan_review → 回到 planner
        # plan_feedback 也就是 execution_plan["feedback"]，和 state.get("plan_feedback") 的不同就是		   他可以保存历史记录
        state.get("design_feedback") or state.get("plan_feedback") or plan_feedback or ""
    ).strip() # 获得用户的修改建议，其中包含了 plan 规划任务时以及 design 设计图时的用户建议
    
    # 判断复杂度
	# 如果用户说"简单"/"复杂" → 解析复杂度
	# 否则用之前的复杂度
	complexity_profile = resolve_complexity_profile(...)
    
    # 判断建筑类型（profile）
	# "别墅" → villa_profile
	# "高层住宅" → residential_tower_profile
	profile = detect_architecture_profile(...)
    
    # 第二阶段：RAG 检索 获取知识
    # 从知识库检索相关规则
	spec_text = agent_service.spec_loader.load_many([
    	"当前引擎已实现的宿主、连接与空间解析关系",
    	"当前 WILD 引擎能力边界"
	])

	# 如果检索失败，用空字符串（不中断流程）
	except Exception:
    	spec_text = ""
    	rag_error = str(exc)
        
    
    # 第三阶段：LLM 调用
    # 构建 Prompt
	prompt = build_architecture_plan_prompt(
    	spec_text,           # RAG 检索的知识
    	profile,             # 建筑类型
    	complexity_profile,  # 复杂度
    	revision_feedback,   # 修订意见
	)

	# 加入已批准的约束
	prompt += 已批准任务指导 + 结构化业务要求

	# 调用 LLM
	llm_result = await invoke_llm(llm, messages)
	raw_plan = extract_json_object(llm_result.content)

	# 如果格式错误，尝试恢复
	if raw_plan is None:
    	raw_plan = recover_single_json(...)
	
    # 第四阶段：生成设计文档
    # 构建设计文档（包含方案详情、SVG 等）
	design_document = build_design_document_or_error(
    	plan,
    	building_type=...,
    	style_intent=...,
	)

	# 解析设计（生成可渲染的数据）
	resolved_design = resolve_design(design_document)

	# 返回结果
	return {
    	"architecture_plan": plan,          # 给下游节点用
    	"design_document": design_document, # 可交付文档
    	"resolved_design": resolved_design, # 可渲染数据
    	...
	}
```

## vibecoding 的瓶颈

> 该项目使用 Codex 搭配 GPT-5.6 Sol 从零搭建，期间尝试了多种 AI 辅助优化方式

**AI 辅助优化的尝试**

1. Bug 驱动优化：

   发现 Blueprint 生成有问题（比如门窗重叠，构件超出边界），将错误日志和 Blueprint JSON 发给 AI，让他修复

2. 架构优化：

   让 AI 扫描整个项目，提出优化建议（比如改进验收机制、优化 Prompt）。

3. 方案讨论：

   和 AI 讨论当前架构的设计权衡，探索更好的方案

**遇到的三大瓶颈**

1. 空间推理能力不足：

   最大的问题是 Blueprint 的空间几何错误——门窗重叠、坐标超出墙边界、构件遮挡。

   AI 的建议通常是'改进 Prompt'或'增加示例'，但这解决不了根本问题：LLM 不擅长 3D 空间推理，它无法理解'门在墙上的 x=5m 位置，宽度 1.2m，是否会和 x=5.5m 的窗户碰撞'。

2. 缺少领域约束：

   AI 不知道 WILD Blueprint 的隐含规则：

   * 门必须在墙上，且不能超出墙边界
   * 窗户高度必须离地 > 0.8m
   * 阳台必须有护栏

   这些规则在代码里没有明确检查，AI 也不会主动加。它的优化往往是表面的（调整 Prompt、重构函数），而不是设计硬约束机制。

3. 无法定位根因：

   因为我当时只了解架构，不懂具体实现，AI 也只能基于代码表面分析。

   比如'为什么生成的建筑总是类似？'AI 会说'增加候选数量'或'调整 Temperature'，但真正的原因是 RAG 召回了完整案例，模型照搬了。

   这需要深入理解 RAG 检索逻辑、知识库内容、候选选择机制，AI 做不到这种系统性分析。

**认识到的 AI 能力边界**

AI 擅长：

* 代码生成、重构、格式化
* 简单 Bug 修复

AI 不擅长：

* 深度根因分析
* 领域知识建模
* 复杂约束设计

**这个过程让我理解了 VibeCoding 的能力边界：**

快速搭建原型可以依赖 AI，但生产级优化必须人工深度介入——理解代码实现、定位根本原因、设计约束机制、验证优化效果。

## 最终架构设计思路

**大模型的能力边界：**

1. 大模型擅长：
   * 理解自然语言需求；
   * 发散式设计；
   * 生成建筑方案、空间布局、风格描述；
   * 根据错误信息推理可能的修复方式；
   * 结合知识库里的协议规范调整输出；
2. 大模型不擅长：
   * 严格保证输出符合复杂协议；
   * 精确控制三维结构、坐标、层级关系；
   * 保证每次生成结果可复现；
   * 避免细微格式错误；
   * 直接生成大型复杂资产的最终文件；

由此，我总结成该项目的核心思想：大模型只写“设计图纸”，而不是直接生成最终蓝图。

> 大模型不直接生成最终蓝图文件，而是生成一层结构化、可校验、可编译的“设计图纸”。
> 最终蓝图文件由确定性脚本/编译器生成。
> 大模型主要负责创意设计和错误修复，不直接参与确定性编译流程。 

## Prompt 的设计

>  项目的提示词都是由agent自主设计，但经 LangSmith trace 追踪发现，提示词与实际节点职责不匹配。以下结合示例与分析，说明优化理由。 
>

**architecture 节点的 prompt**

```
你是建筑方案主创建筑师。只做体量、立面轴网和构件配额，不生成 WILD Blueprint，也不设计房间布局。

# 任务

- 只输出 1 个可实施方案，即本次交付的唯一最终方案；不要输出备选或并列方案。
- 方案服从用户需求和已批准决定；知识库补充能力与条件关系，不能决定默认造型。复杂度落实为本次所需空间与细节，不靠重复构件凑数。
- 当前引擎物理边界是：{"id": "villa", "width_range": [4.0, 300.0], "depth_range": [4.0, 300.0], "floor_range": [1, 200], "max_explicit_floors": 12, "shapes": ["basilica", "bowl", "centralized", "circle", "courtyard", "l_shape", "linear", "pavilion", "radial", "rectangle", "stepped", "terminal", "tower", "twin_tower", "u_shape", "underground"], "base_components": ["door", "window", "roof"], "require_front_entrance": true}。它只描述本次可表达的范围（尺寸/层数/形状/构件），**不含任何默认建筑，也没有"档位"概念**——建筑类型、风格、形态完全由用户需求与知识库形制资料决定。明确需求超出范围时报告限制，不能静默改写。
- 本次复杂度目标是：{"min_volumes": 1, "min_detail_packages": 0, "target_structural_elements": 10, "grid_bays": [2, 2]}。
- 完整落实用户选择的关系并明确 structural_grid；仅当用户要求多体量时满足相应 min_volumes。细部包按功能选择，不强制退台、侧翼或固定套餐。
- 该方案应通过非矩形或多体量关系、屋顶层次、或一个有功能依据的进深细部形成真实轮廓与阴影；具体策略由本次需求决定，不套建筑类型默认组件。
- front 是最小 Z 的主立面，back 是最大 Z，left/right 分别是最小/最大 X。
- ground_pattern / upper_pattern 的数组长度必须等于 bays。每个槽位是开口 token：`door`／`window`／`empty`／`open`，或写成 `类型:形态` 显式指定形态（如 `door:slide`、`window:fixed`）。形态闭集：门 swing／slide／lift，窗 swing／slide／fixed（fixed = 固定窗，不可开启；门不许写 fixed、窗不许写 lift，写错会被退回纯类型）。不写冒号时形态由系统派生。upper_pattern 只能用 window／empty／open，即使建筑只有一层也禁止填写 door。
- `empty` 与 `open` 语义不同，不能混用：`empty` = **有墙、这一格不开洞**；`open` = **这一面这一层不生成墙**（开敞面，由柱承重）。要开敞的面写 `open`；要实墙只是某格没洞，写 `empty`。
- 要保留实墙的面至少给一个开口槽位；开敞形制（亭/廊）把不要墙的面全写 open。
- 门只能出现在 ground_pattern。仅当 profile.require_front_entrance=true 时，front 才必须有且只有一个主门槽位。
- ground_pattern 会在首层执行一次，upper_pattern 会在每个建模上层重复执行；其中每个 door/window 都会成为真实组件。component_quota 必须等于这些逐层 pattern 的实际总数，不能先画密集 pattern 再用较小配额抽样删减。
- 方案至少建立一种可执行的构图关系，例如入口主次、上下层开口对位、成组对称或有理由的非对称、体量转折、屋顶层次、或与功能相符的进深细部。关系由本次需求选择，不绑定固定建筑类型和固定构件套餐。
- required_components 以 profile.base_components 为基础；示例中的门窗屋顶不是所有 profile 的固定要求。
- `floors` 表示建筑语义总层数；复杂高层可用较小的 `modeled_floors` 做示意表达，并把 `representation_mode` 设为 `schematic`。
- 本节点不设计房间坐标和内部隔墙；骨架节点直接依据总体体量、立面和结构约束生成 Blueprint 主体。

# 候选建筑风格（由系统根据需求预选）

总体方案和材质方案应优先服从以下候选的屋顶、体量与色彩倾向：
modern, chinese, eco_contemporary。不要虚构候选之外的风格细节。

# 输出协议

只输出一个 JSON 对象，顶层直接给出唯一最终方案的字段；不要输出 candidates 数组、备选方案或方案对比。下列是字段契约，不是可以照抄的建筑：
- concept：本次方案概念字符串。
- massing：shape 使用 profile 允许值；width/depth/floor_height 为正数，floors/modeled_floors 为正整数；representation_mode 为 full 或 schematic；symmetry 为布尔值。
- volumes：按本次方案输出体量数组，每项包含 id、role(primary/secondary)、x、z、width、depth、start_floor、end_floor；单体也需明确一个完整体量，多层单体不必拆成退台。
- structural_grid：system 为 wall_bearing/frame/hybrid/long_span/shell；x_bays/z_bays 为正整数。
- circulation：vertical_strategy 为 none/stair/core_and_stair；核心筒方案必须同时包含楼梯，多层建筑不能为 none。
- 体量是逐层外轮廓的唯一来源：某层外轮廓只由覆盖该层的体量决定。规划退台时，任何跨越多个楼层的贯通构件（核心筒、电梯井、贯通竖向交通或通高墙体）都必须落在它经过的**每一层**体量并集之内，即收进 `start_floor..end_floor` 上全部存在的体量交集；不得伸进只存在于低楼层的退台翼，否则它在退台层会成为外凸的独立体块。必要时宁可让该体量贯通到顶层，也不要让核心筒跨进退台翼。
- detail_packages：实际选用的附属组件名称数组，允许为空；只能用当前支持类型。
- facades：front/back/left/right 每面包含 bays、ground_pattern、upper_pattern，槽位数量与 bays 一致。entrance_bay 与 door 槽位**只在用户要求入口/门或形制确有门时才写**；形制知识命中开敞建筑（亭/廊/榭等）时四面 pattern 全写 open、不写 entrance_bay、任何面不写 door——全空声明会被系统自动豁免主入口强制，不要用 door 去"满足"入口要求。
- roof：**只给一块**屋顶的风格模板——type 使用当前六种 roofType；ridge_axis 为 x 或 z；overhang 为非负数。不要写成数组，也不要写 id/span/depth/position：多体量（L/U 形）与退台的分段屋面、出檐、贴合墙体并避开内院/天井，全部由系统按 volumes 自动派生。确实需要"主楼坡顶 + 侧翼平顶"这类差异时，在 roof 里**额外**加一个 volumes 数组，每条形如「volume: 体量 id，type: 六种之一，overhang: 非负数」；体量 id 必须与 volumes 里的 id 完全一致，未列出的体量继承上面的模板。
- materials：可选。`regions` 是「哪一类实体用哪种材质」的绑定数组，每条形如「role: 材质角色名，type: 目标实体类型」——role 用材质方案里已有的角色（roof／structure／facade_primary／floor 等），type 用实体类型（wall／floor／roof／column／light／railing 等）。默认同类型实体共用一种材质；只有当本次需求真的要求"某类实体与同类不同材质"（例如屋面要与外墙明显区分、灯具要金属感）时才写，不要为了凑字段而给全类型逐条绑定。没这个需求就整个不写 materials。
- component_quota：按实际组件类型提供 min/max 整数及 note；如指定屋型可提供 type，不给未选择的组件硬配额。
- required_components：本次真正需要的组件名称数组。
- design_rationale：说明体量、入口、交通与构件选择如何满足用户要求的字符串数组。
所有数值都必须由本次需求推导；不要输出类型说明文字代替数值。

# 知识库参考

## blueprint-skeleton

---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_skeleton
topic: structure
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 蓝图顶层结构
  - blueprint top level
  - meta
  - geometry
  - materials
  - assets
  - materialLibraries
  - renderProfile
  - behaviors
synonyms: []
---

# 蓝图骨架

原语蓝图使用 JSON 编码，文件扩展名 `.wild`。

## 顶层结构

必须包含 `meta` 和 `geometry`，可选 `materials`、`assets`、`materialLibraries`、`renderProfile` 和 `behaviors`。

​```jsonc
{
  "meta": { ... },
  "geometry": { ... },
  "materials": { ... },
  "assets": { ... },
  "materialLibraries": [ ... ],
  "renderProfile": "builtin:default",
  "behaviors": { ... }
}
​```

| 字段 | 必需 | 说明 |
|------|------|------|
| `meta` | 是 | 版本、类型、名称等元数据 |
| `geometry` | 是 | 几何定义 |
| `materials` | 否 | 材质字典，键为材质名 |
| `assets` | 否 | PBR 纹理集资产清单，键为 `assetId` |
| `materialLibraries` | 否 | 全局材质库引用；蓝图只存引用，不复制全局资产 |
| `renderProfile` | 否 | 世界光影配置引用；省略时使用 `builtin:default` |
| `behaviors` | 否 | 物理、脚本与动画 |

## 元数据 (meta)

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | 是 | `"1.0"` 或 `"1.1"`；使用 `primitive`/PBR 纹理时必须为 `"1.1"` |
| `type` | string | 是 | `"building"`、`"avatar"`、`"asset"` 或 `"scene"` |
| `name` | string | 是 | 实体名称 |
| `author` | string | 否 | 创建者地址 |
| `createdAt` | number | 否 | 创建时间戳 |
| `style` | string | 否 | 语义风格标识，如 "east-asian-tower" |
| `seed` | number | 否 | 随机种子，用于微调细节 |

## 几何条目公共字段

所有构件都具有：

- `id`：唯一标识符
- `material`：引用材质库中的材质名（可选）

## 材质与资产四字段分工

材质与纹理资产不参与几何成形，只决定表面的最终外观。

| 字段 | 类型 | 职责 |
|------|------|------|
| `materials` | object | 材质字典。键为材质名（如 `"wall_plaster"`），值为材质定义。构件的 `material` 字段引用这里的键 |
| `assets` | object | PBR 纹理集资产清单。键为不可变 `assetId`，值为 `pbr_texture_set`（含各通道的资源地址、`mimeType`、`contentHash`）。材质通过 `textureSet` 引用它 |
| `materialLibraries` | string[] | 引用全局材质库。蓝图只保存引用而不内联资产，避免同一贴图在多份蓝图里重复复制 |
| `renderProfile` | string | 引用世界光影配置（`wild.render-profile`）。省略时使用 `builtin:default` |

**引用方向**：`构件.material` → `materials[键]` → （可选）`materials[键].textureSet` → `assets[assetId]` → 资产地址。

**顺序要求**：`assets` 中的资产必须先存在，材质才能通过 `textureSet` 指向它。增量修改时先 `upsert_asset`，再 `upsert_material`。

**材质属于表现层**：纹理与效果层只影响表面着色，不改变构件的尺寸、位置或轮廓——即"画质增强，不改变几何语义"。

---

## generation-redlines

---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: generation_redlines
topic: constraints
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 生成红线
  - always-on rules
  - 坐标红线
  - 材质格式铁律
  - 屋顶枚举
synonyms: []
---

# 生成红线（始终注入）

本文件**每轮完整注入提示词**，因此只放"模型不看到就一定会写错、且写错后无法靠常识补救"的条目。
其余字段细节走检索，不在这里重复。新增条目请保持一句话一条。

## 坐标与几何

- 两面墙在转角处相接时必须**共享完全相同的端点坐标**，不能使用近似值。
- 生成屋顶前先用 `get_wall_bounding_box` 取得墙体包围盒，不要猜测尺寸。
- 组合构件挂在墙上的水平定位是 **`from[0] = 沿墙距离`**（从 `parentWall.from` 沿墙方向量起，单位米）。
- `roof.span` / `roof.depth` 按其负责的**体量轮廓**取尺寸，出檐时两侧加余量；
  **不得**用整栋外包络当屋顶范围。多体量（L 形 / U 形 / 退台）各生成一块屋顶，或贴合墙体留出内院 / 天井。
  （这三项 `span` / `depth` / `position` 是**蓝图屋顶元素**的字段；
  **设计层** `decisions.roof` 没有它们，只写一块风格模板 `type` / `ridge_axis` / `overhang`——
  逐体量分段由编译器派生；需要"主楼坡顶 + 侧翼平顶"这类差异时在模板里加
  `volumes: [{"volume": "<体量 id>", "type": "...", "overhang": 0.3}]`，
  体量 id 必须与 `decisions.volumes` 一致。见《构件参数》§roof 的分层说明。）
- `roof.position` 位于墙体 XZ 中心与墙顶高度。

## 枚举陷阱

- `roof.roofType` 只有 **6 个合法值**：`gable` / `hip` / `dome` / `flat` / `chinese_curved` / `chinese_pagoda`。
- **严禁** `pitched`、`sloped`、`gabled`、`hipped`、`shed`、`mono-pitch` —— 它们是建筑学术语，不是 WILD 枚举值。
- 组合构件只能写入 `geometry.components`，不能写进 `geometry.elements`；严禁发明不存在的类型值。

## 材质

- baseColor 必须是 [R, G, B] 数组（各分量 0.0–1.0）；绝对禁止写成 `"#RRGGBB"` 字符串。
- 数值颜色（`baseColor`、`emissive`、效果层颜色、程序化顶点色）统一按 sRGB authored value 表达，
  由渲染器转换到线性工作空间。
- 墙、楼板、屋顶、门、玻璃按实际角色引用各自独立的材质名，不要全部指向同一个 `concrete`。
- 物理玻璃必须给出 `materialClass: "glass"`、`transmission > 0` 和 `ior`，`opacity` 必须为 `1` 或省略。

---

## RAG 检索到的相关规范片段

知识使用约定：
- protocol/capability/relation 说明当前 WILD 能力与已选择构件的正确关系。
- 建筑类型与风格语义由模型理解；知识库不提供建筑百科或类型模板。
- 用户明确需求与已批准方案决定层数、轮廓、尺寸、材质和构件选择；参考知识不能静默改写这些决定。
- 未指定的设计变量由本次方案推导，不套用案例尺寸、固定配色、默认退台或固定构件套餐。
- 数值示例只解释局部字段；可渲染、几何校验通过不代表结构或专业规范合规。

### 片段 1: assembly-relations.md / 构件组装关系约束, distance=1.1312

[chunk_id=wild_spec:ae57e8b0a764:section:a8f0458b4ab8ae73:0:94bf62109495ee98]

> metadata: doc_type=recipe, entity_name=supported_assembly_relations, topic=assembly, knowledge_role=relation, status=supported, authority=engine

> 知识路径：构件组装关系约束

# 构件组装关系约束  
> 基于 WILD v1.1 引擎实现的实际组装能力
> 来源：`wild-core/resolver.ts`、`wild-compiler/index.ts`、组件编译器  
本文档只记录**引擎当前能够执行**的组装关系。未实现的设计不变量应移至 backlog。  
---

### 片段 2: assembly-relations.md / 构件组装关系约束 > 6. 楼板与屋顶自动补全 > 限制, distance=1.1915

[chunk_id=wild_spec:ae57e8b0a764:section:3eb1ee26662fdde1:0:af48b557e4c44288]

> metadata: doc_type=recipe, entity_name=supported_assembly_relations, topic=assembly, knowledge_role=relation, status=supported, authority=engine

> 知识路径：构件组装关系约束 > 6. 楼板与屋顶自动补全 > 限制

### 限制  
- 其他标高关系需显式给出
- 引擎不完成结构设计推导  
---

### 片段 3: composite-components-second-batch.md / WILD 第二批组合构件 > 第二批组件能力边界, distance=0.9498

[chunk_id=wild_spec:bd304ff8e9da:section:fe85ff914b789cd3:0:c8e935490926a837]

> metadata: doc_type=component, entity_name=second_batch_component_boundaries, topic=constraints, knowledge_role=capability, status=supported, authority=engine

> 知识路径：WILD 第二批组合构件 > 第二批组件能力边界

## 第二批组件能力边界  
第二批组件只使用当前 Core 的 `opening`、`primitive`、`beam` 和 `profile_sweep`。当前没有通用 CSG、屋顶真实穿透、复杂曲面屋顶依附、地形贴合、中间坡道平台或结构安全计算。不得把烟囱外观误述为屋顶已开孔，也不得把栏杆参数误述为符合建筑规范。

### 片段 4: column.md / 柱（column）组件参数契约 > 能力边界, distance=1.1571

[chunk_id=wild_spec:e0ac839fbd4b:section:c282200233b2fc9c:0:060c721176855d1e]

> metadata: doc_type=component, entity_name=column_component, topic=parameters, knowledge_role=capability, status=supported, authority=engine

> 知识路径：柱（column）组件参数契约 > 能力边界

## 能力边界  
- 没有 `abacus`（柱头垫块）字段——垫块用独立 `primitive` 补。
- 没有柱间横梁/额枋字段——用 `beam` 元素或 `primitive` 表达。
- 不做墙体一体化柱（壁柱/扶壁）——那是墙体几何的事，用墙的凸出体量表达。

知识使用约定：
- protocol/capability/relation 说明当前 WILD 能力与已选择构件的正确关系。
- 建筑类型与风格语义由模型理解；知识库不提供建筑百科或类型模板。
- 用户明确需求与已批准方案决定层数、轮廓、尺寸、材质和构件选择；参考知识不能静默改写这些决定。
- 未指定的设计变量由本次方案推导，不套用案例尺寸、固定配色、默认退台或固定构件套餐。
- 数值示例只解释局部字段；可渲染、几何校验通过不代表结构或专业规范合规。

# 本轮只写一个设计块

本轮是**分块起草**，你这一轮只负责 `massing` 块。

## 输出形态（先看这一条）

只输出**一个** JSON 对象，顶层键**恰好**是这 4 个：`concept`、`massing`、`volumes`、`design_constraints`。下面 `- 键名：…` 说的是**那个键里面**该写什么，不是让你把它的内容平铺到顶层——某个键的值是对象/数组时，子字段必须留在那个对象/数组里；也不要另起一行写成 `键名: 值`，那不是 JSON。顶层出现清单之外的键，这一轮就会被判未通过并点名缺了哪些键。

## 本轮必须输出这些字段（且只输出这些）

- concept：从**用户需求原文**提炼的方案名（如「四角亭子」「临水茶室」），不超过 16 字。这是蓝图文件名与图纸标题；不要写风格档位词、不要写「比例清晰」这类空话，也不要复读整个请求句子。
- massing：shape **优先从这些值里选**：rectangle、l_shape、u_shape、stepped、courtyard、circle、linear、radial、bowl、terminal、tower、twin_tower、pavilion、basilica、centralized、underground。其中 l_shape、u_shape、stepped、courtyard 有专门的体量派生（你没给 volumes 时按它生成）；其余（形制名，如 pavilion／tower／circle）的体量构成由你给的 volumes 表达。写了表外的名字不会被拦，但也不会有专门的几何行为。width/depth 是总体包络尺寸控制上限（米），不是以世界原点为边界的场地；floor_height 为正数；floors/modeled_floors 为正整数；representation_mode 为 full 或 schematic；symmetry 为布尔值。
- 塔形/退台轮廓用 massing.tiers 表态：从底到顶逐段给 floors、width_ratio、depth_ratio（比例相对 massing.width/depth，0~1）；各段 floors 之和必须等于 massing.floors。
  电视塔、宝塔、阶梯收分的高层**务必**用它表达轮廓收放，不要把整栋楼画成一个矩形体量。
- volumes：体量数组，每项含 id、role(primary/secondary)、x、z、width、depth、start_floor、end_floor。x/z 是世界平面起点，不是中心；矩形覆盖 [x,x+width]×[z,z+depth]。允许整体平移及负坐标；体量并集跨度不得超出 massing.width/depth。坐标歧义必须显式纠正，不能裁剪。单体也要明确一个完整体量；多层单体不必拆成退台。
- 体量之间**不得重叠**，同层投影必须覆盖建筑轮廓（这是硬约束，不是审美）。
- complexity 由系统按档位给出，**本块不要写 complexity**。
- design_constraints：列出用户明确要求以及本方案采用的关键决定，不能只留在文案中。每条含 id(稳定标识)、kind(user_hard 或 preference)、target(/decisions/... JSON Pointer)、expression(简短目标)、source(user_request 或 architecture_draft)、source_quote(用户要求须逐字引用原文)、expected(目标值)、check(equals/contains/minimum/absent/manual)、adoption(adopted/proposed)。无法可靠映射的要求仍保留并用 manual，不得自行发明用户硬要求。列表成员用 contains/absent；屋顶类型指向 /decisions/roof/type；层数指向 /decisions/massing/floors。不支持的形态保留目标路径和说明，不可偷偷换成支持的形态。修订时继承已有要求，不能删掉或降低 expected 以消除缺口。用户明确改变要求时才用新 id、supersedes=旧 id，source_quote 引用本次修改原文。

其余字段**已定稿**，由系统提供；写它们会被忽略，且浪费你的注意力。

# 本块专属知识库参考

以下是检索到的与本块相关的 WILD 规范/形制/组装知识。字段写法与组装关系**以此为准**；造型取向仍由用户需求决定，知识不得静默改写用户已定的尺寸与风格：

## blueprint-skeleton

---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_skeleton
topic: structure
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 蓝图顶层结构
  - blueprint top level
  - meta
  - geometry
  - materials
  - assets
  - materialLibraries
  - renderProfile
  - behaviors
synonyms: []
---

# 蓝图骨架

原语蓝图使用 JSON 编码，文件扩展名 `.wild`。

## 顶层结构

必须包含 `meta` 和 `geometry`，可选 `materials`、`assets`、`materialLibraries`、`renderProfile` 和 `behaviors`。

​```jsonc
{
  "meta": { ... },
  "geometry": { ... },
  "materials": { ... },
  "assets": { ... },
  "materialLibraries": [ ... ],
  "renderProfile": "builtin:default",
  "behaviors": { ... }
}
​```

| 字段 | 必需 | 说明 |
|------|------|------|
| `meta` | 是 | 版本、类型、名称等元数据 |
| `geometry` | 是 | 几何定义 |
| `materials` | 否 | 材质字典，键为材质名 |
| `assets` | 否 | PBR 纹理集资产清单，键为 `assetId` |
| `materialLibraries` | 否 | 全局材质库引用；蓝图只存引用，不复制全局资产 |
| `renderProfile` | 否 | 世界光影配置引用；省略时使用 `builtin:default` |
| `behaviors` | 否 | 物理、脚本与动画 |

## 元数据 (meta)

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | 是 | `"1.0"` 或 `"1.1"`；使用 `primitive`/PBR 纹理时必须为 `"1.1"` |
| `type` | string | 是 | `"building"`、`"avatar"`、`"asset"` 或 `"scene"` |
| `name` | string | 是 | 实体名称 |
| `author` | string | 否 | 创建者地址 |
| `createdAt` | number | 否 | 创建时间戳 |
| `style` | string | 否 | 语义风格标识，如 "east-asian-tower" |
| `seed` | number | 否 | 随机种子，用于微调细节 |

## 几何条目公共字段

所有构件都具有：

- `id`：唯一标识符
- `material`：引用材质库中的材质名（可选）

## 材质与资产四字段分工

材质与纹理资产不参与几何成形，只决定表面的最终外观。

| 字段 | 类型 | 职责 |
|------|------|------|
| `materials` | object | 材质字典。键为材质名（如 `"wall_plaster"`），值为材质定义。构件的 `material` 字段引用这里的键 |
| `assets` | object | PBR 纹理集资产清单。键为不可变 `assetId`，值为 `pbr_texture_set`（含各通道的资源地址、`mimeType`、`contentHash`）。材质通过 `textureSet` 引用它 |
| `materialLibraries` | string[] | 引用全局材质库。蓝图只保存引用而不内联资产，避免同一贴图在多份蓝图里重复复制 |
| `renderProfile` | string | 引用世界光影配置（`wild.render-profile`）。省略时使用 `builtin:default` |

**引用方向**：`构件.material` → `materials[键]` → （可选）`materials[键].textureSet` → `assets[assetId]` → 资产地址。

**顺序要求**：`assets` 中的资产必须先存在，材质才能通过 `textureSet` 指向它。增量修改时先 `upsert_asset`，再 `upsert_material`。

**材质属于表现层**：纹理与效果层只影响表面着色，不改变构件的尺寸、位置或轮廓——即"画质增强，不改变几何语义"。

---

## generation-redlines

---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: generation_redlines
topic: constraints
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 生成红线
  - always-on rules
  - 坐标红线
  - 材质格式铁律
  - 屋顶枚举
synonyms: []
---

# 生成红线（始终注入）

本文件**每轮完整注入提示词**，因此只放"模型不看到就一定会写错、且写错后无法靠常识补救"的条目。
其余字段细节走检索，不在这里重复。新增条目请保持一句话一条。

## 坐标与几何

- 两面墙在转角处相接时必须**共享完全相同的端点坐标**，不能使用近似值。
- 生成屋顶前先用 `get_wall_bounding_box` 取得墙体包围盒，不要猜测尺寸。
- 组合构件挂在墙上的水平定位是 **`from[0] = 沿墙距离`**（从 `parentWall.from` 沿墙方向量起，单位米）。
- `roof.span` / `roof.depth` 按其负责的**体量轮廓**取尺寸，出檐时两侧加余量；
  **不得**用整栋外包络当屋顶范围。多体量（L 形 / U 形 / 退台）各生成一块屋顶，或贴合墙体留出内院 / 天井。
  （这三项 `span` / `depth` / `position` 是**蓝图屋顶元素**的字段；
  **设计层** `decisions.roof` 没有它们，只写一块风格模板 `type` / `ridge_axis` / `overhang`——
  逐体量分段由编译器派生；需要"主楼坡顶 + 侧翼平顶"这类差异时在模板里加
  `volumes: [{"volume": "<体量 id>", "type": "...", "overhang": 0.3}]`，
  体量 id 必须与 `decisions.volumes` 一致。见《构件参数》§roof 的分层说明。）
- `roof.position` 位于墙体 XZ 中心与墙顶高度。

## 枚举陷阱

- `roof.roofType` 只有 **6 个合法值**：`gable` / `hip` / `dome` / `flat` / `chinese_curved` / `chinese_pagoda`。
- **严禁** `pitched`、`sloped`、`gabled`、`hipped`、`shed`、`mono-pitch` —— 它们是建筑学术语，不是 WILD 枚举值。
- 组合构件只能写入 `geometry.components`，不能写进 `geometry.elements`；严禁发明不存在的类型值。

## 材质

- baseColor 必须是 [R, G, B] 数组（各分量 0.0–1.0）；绝对禁止写成 `"#RRGGBB"` 字符串。
- 数值颜色（`baseColor`、`emissive`、效果层颜色、程序化顶点色）统一按 sRGB authored value 表达，
  由渲染器转换到线性工作空间。
- 墙、楼板、屋顶、门、玻璃按实际角色引用各自独立的材质名，不要全部指向同一个 `concrete`。
- 物理玻璃必须给出 `materialClass: "glass"`、`transmission > 0` 和 `ior`，`opacity` 必须为 `1` 或省略。

## 这是第一块

没有任何前序内容可引用；本块的尺寸将决定后面所有块的坐标。
```

该 prompt 一共分为了以下几块：

1. 模型职责
2. 模型任务
3. 建筑风格
4. 输出格式
5. RAG知识库

模型职责没什么要说的，只需要具体的指出 architecture 的职责就是建筑的图纸设计师就可以了

模型任务该提示词写的不是很好，首先是有强制性的限制，比如模型物理边界



## 项目的主要设计思路梳理

**核心命题**

> **大模型掌握了 wild 语言规则，可以直接生成 wild 文本，但“生成容易、生成正确很难”。**  
> 正确路线是：**设计文档做“可编译规则源 + 参数快照 + 校验契约”，脚本做确定性展开，大模型只做语义补全，wild 是编译产物。**

---

**一、为什么不能让大模型直接手写 wild**

wild 里大量内容是坐标、锚点、宿主关系和重复构件，正好是“人读起来累、脚本算起来稳、大模型手写容易漂”的部分。

以典型 wild 为例，证据如下。

**1. 同一文件混用多种锚点语义**

| 类型            | 字段                                 | 锚点语义                                                 |
| --------------- | ------------------------------------ | -------------------------------------------------------- |
| `floor`         | `from/to + thickness`                | `from/to` 的 Y 是**板底**，板顶 = Y + thickness          |
| `primitive` box | `position + dimensions`              | `position` 是**中心点**                                  |
| `furniture`     | `position`                           | `position` 是**底面中心**，如 `living_sofa` 的 Y=0.45=F0 |
| `window/door`   | `parentWall + from:[along,bottom,0]` | `along` 是**沿宿主墙局部坐标**，`bottom` 是标高          |
| `railing`       | `path`                               | 三维点列，不是中心/底面                                  |
| `stair`         | `from/to`                            | 起止点，踏步由 `stepCount/stepDepth/stepHeight` 展开     |

例如：

```json
"parentWall": "living_front",
"from": [0.6, 0.8, 0],
"width": 4.8,
"height": 5.65
```

而宿主墙是：

```json
"from": [0, 0.45, 6],
"to": [6, 7.05, 6]
```

窗的 `along=0.6` 是相对墙起点的局部坐标，不是世界坐标 `x=0.6`。大模型直接写世界坐标，很容易把窗放到墙外或穿墙。**这正是应该由编译器根据宿主墙展开的部分。**

**2. 门窗依赖宿主墙 ID，天然需要校验**

每个窗/门都有 `parentWall`：

- `living_courtyard_glass` → `living_front`
- `main_entry` → `entry_front`
- `terrace_door` → `upper_front`
- `bathroom_door` → `bathroom_front`

如果大模型改了墙 ID 或墙范围，门窗不会自动跟着走。宿主关系必须由编译规则生成，并由校验器检查“宿主存在、开口不越界、门底=楼面顶”。

**3. 楼梯斜梁角度是手算结果，不该让大模型写**

```json
"id": "stair_first_stringer",
"rotation": [-0.5485, 0, 0]
```

这个角度来自梯段坡度，应该由 `from/to + stepCount` 算出来。wild 里直接写死，说明它是“作者脚本算完的产物”，不是“设计文档直接表达的意图”。大模型手写极易错。

**4. 重复构件是脚本循环的产物**

典型 wild 里有大量阵列：

- `entry_oak_fin_0..5`
- `upper_oak_fin_0..5`
- `wing_east_fin_0..6`
- `pergola_slat_0..12`
- `bar_stool_base_0..2` / `bar_stool_seat_0..2`
- 多处 `canopy_0..4`、`shrub_0..9`

最终产物栖光 wild 里也有：

- `wood_fin_w_01..03`
- `wood_fin_e_01..03`
- `win_l1_w_01..03`、`win_l2_e_01..03`、`win_l3_n_01..04`

这些让大模型逐条写，容易出现数量不对、间距不匀、漏项、ID 冲突。设计文档应表达“这里有几根、间距多少”，由编译器循环生成。**这正好证明“参数和坐标交给脚本”是对的。**

**5. wild 里有大量设计文档没表达的细节**

以典型 wild 为例：

| wild 有                                                      | 典型设计文档有吗 |
| ------------------------------------------------------------ | ---------------- |
| 窗的 `verticalMullions/horizontalMullions/frameWidth/frameDepth` | 没有             |
| 门的 `doorStyle/hingeSide/leafMaterial`                      | 没有             |
| 栏杆 `postSpacing/railLevels/infillType`                     | 没有             |
| 家具 `subtype/rotation/dimensions`                           | 没有             |
| 灯具位置和强度                                               | 没有             |
| 植物球体组合                                                 | 没有             |
| PBR `baseColor/roughness/metallic/transmission`              | 只有角色名       |
| 屋顶 `roofType/ridgeAxis/span/depth`                         | 没有             |
| 雨棚、木鳍、格栅、栏板                                       | 没有             |

所以，**设计文档不能唯一编译出 wild，缺的是“生成规则 + 默认值 + 资产库”，而不是设计意图。**

---

**二、最终产物自带的“编译元数据”是最硬证据**

栖光庭院住宅 wild 的 `editor` 字段直接证明“规则 → 脚本 → 产物”路线成立：

```json
"editor": {
  "revision": 1,
  "generator": "generate_qiguang.cjs",
  "ruleFile": "栖光庭院住宅-建筑规则.md",
  "ruleSha256": "90f70210...",
  "params": { ... },
  "design": {
    "levels": [0.45, 4.05, 7.65, 11.25],
    "wallOutlines": [ ... ],
    "stairWell": [0.24, 9, 2.94, 12.6],
    "validationBoundary": "写盘断言及独立静态校验；未运行真实编译器与渲染器。"
  }
}
```

| 字段                  | 作用                         |
| --------------------- | ---------------------------- |
| `generator`           | 哪个脚本生成                 |
| `ruleFile`            | 哪份规则/设计文档作为源      |
| `ruleSha256`          | 规则文件指纹，可追溯、可重放 |
| `params`              | 本次生成的全部参数快照       |
| `design.levels`       | 设计标高边界                 |
| `design.wallOutlines` | 设计墙轮廓                   |
| `design.stairWell`    | 楼梯井边界                   |
| `validationBoundary`  | 校验范围声明                 |

这不是“大模型直接写 wild”，而是**规则文档 + 编译脚本 + 参数快照 + 产物元数据**。`params` 里的 `module / axisX / axisZ / storeyHeights / wallThickness / stair / windows / guard / canopy / woodFins` 就是设计文档应该长成的样子。

注意 `validationBoundary` 也说明：它只做了写盘断言和静态校验，没有真实渲染校验。所以设计文档还要配独立校验器。

---

**三、设计文档应该承担什么**

**1. 说明书：让人读懂 wild 的设计思路**

设计文档应该解释：

- 轴网和标高怎么定；
- 体量怎么围合院落；
- 楼板怎么扣洞；
- 楼梯怎么组织；
- 门窗怎么挂在宿主墙上；
- 家具和材质按什么规则放置。

**2. 降低大模型负担：把坐标计算交给脚本**

这些应该由编译器算，不该让大模型算：

- 墙段起止点和厚度；
- 楼板扣洞后的矩形；
- 楼梯踏步、斜梁角度、平台标高；
- 门窗沿墙局部坐标；
- 栏杆路径和立柱间距；
- 重复构件的数量、间距、阵列；
- 家具落地标高和朝向约束；
- 材质角色到 PBR 的映射。

大模型只做它擅长的：语义补全、风格选择、资产命名、把自然语言验收项转成断言。

**3. 可编译：设计文档要能驱动生成 wild**

“可编译”不等于“设计文档直接变 wild”，需要三层：

```text
L0 设计事实 + 约束（设计文档）
   ↓ 编译器：确定性几何 + 规则展开
L1 几何/构件 IR：墙、板、洞、楼梯、门窗、栏杆
   ↓ 资产库 + 大模型语义补全
L2 wild 场景 JSON
   ↓ 校验器
通过 / 补丁循环
```

设计文档里要补的编译信息：

- `rect` 的坐标语义；
- 墙的生成规则（外墙/内墙/共享界面只建一面）；
- 门窗宿主和局部坐标规则；
- 楼板拆分规则；
- 楼梯生成规则；
- 重复构件的阵列规则；
- 材质角色到 PBR 的映射表；
- 家具/灯具/植物资产库；
- 默认值和确定性 ID 规则；
- 产物元数据：`generator / ruleFile / ruleSha256 / params / design / validationBoundary`。

**4. 可校验：设计文档要能转成断言**

`features_to_verify` 和 `use_clearances` 是校验契约的雏形，但要从自然语言转成可执行断言。至少覆盖：

- **宿主校验**：门窗 `parentWall` 是否存在；开口是否在宿主墙范围内；
- **标高校验**：门底是否等于楼面顶；楼梯总高是否等于层高；平台标高是否等于 `half_landing`；
- **洞口校验**：梯井是否与楼板冲突；通高客厅是否无二层楼板且有屋面；
- **栏杆校验**：路径是否闭合；入口是否留空；高度/立柱间距是否符合参数；
- **路线校验**：所列路线净宽/净高是否满足 `use_clearances`；
- **材质校验**：所有 `material` 引用是否在 `materials` 中；
- **边界声明**：`validationBoundary` 要明确“做了哪些校验、没做哪些校验”，避免把静态校验当成渲染/结构验证。

---

**四、一句话结论**

> **设计文档不是 wild 的“文字说明书”，而是“可编译规则源 + 参数快照 + 校验契约”；脚本是编译器；wild 是编译产物，并自带 `generator / ruleFile / ruleSha256 / params / design / validationBoundary` 作为可追溯元数据；大模型只做规则补全、语义选择、断言生成，不手写坐标。**













