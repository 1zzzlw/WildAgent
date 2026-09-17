# WildAgent 架构设计深度解析：Agentic Workflow 的工业实践

> **文档性质**：基于真实代码的架构分析与设计思考
> 
> **创建时间**：2026-09-16
> 
> **核心价值**：理解 Agent 与 Workflow 的边界，掌握混合架构的设计哲学

---

## 一、核心认知：这是什么类型的系统？

### 1.1 第一印象的困惑

当第一次看到这个系统时，会产生疑问：

```
❓ 这是 Agent 系统吗？
   - 主链是固定的：classifier → planner → architecture → skeleton → ...
   - 感觉更像 Workflow

❓ 这是 Workflow 系统吗？
   - 每个节点都调用 LLM，有自主决策
   - 感觉又不只是固定流程
```

### 1.2 准确定位

**WildAgent 是一个 Agentic Workflow 系统**，具体来说：

```
Agentic Workflow = 
    Workflow 的可控性（固定主链、安全边界）
    + 
    Agent 的灵活性（关键决策点的自主判断）
```

这不是设计缺陷，而是**工业级 Agent 系统的最佳实践**。

---

## 二、三层架构解析

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│ 第 1 层：主链调度（Workflow）                         │
│ LangGraph 图结构：固定节点顺序 + 条件分支            │
├─────────────────────────────────────────────────────┤
│ 第 2 层：节点执行（Guided Generation）                │
│ 每个节点：确定性前处理 + LLM生成 + 确定性后处理      │
├─────────────────────────────────────────────────────┤
│ 第 3 层：内容生成（Agent 决策）                       │
│ LLM：根据上下文自主决定生成什么内容                  │
└─────────────────────────────────────────────────────┘
```

### 2.2 第一层：主链调度（Plan-and-Execute 模式）

**代码位置**：`wild-server/app/agent/graph.py`

**固定主链**：
```python
# Plan Mode 主链
classifier 
→ planning_research 
→ planner           # ← Agent 决策：生成动态任务
→ plan_validator 
→ plan_review       # ← 人工审核暂停点
→ architecture      # ← Agent 决策：生成总体方案
→ material_plan     # ← Agent 决策：选择材质
→ design_review     # ← 人工审核暂停点
→ skeleton          # ← Agent 决策：生成骨架
→ 动态组件链        # ← Agent 决策：生成细部
→ merge
→ final_validate
→ END
```

**关键设计**：
- ✅ 节点顺序固定（不能跳过关键步骤）
- ✅ 人工审核点固定（必须经过批准）
- ✅ 安全边界明确（模型不能改变流程）

**为什么不让 Agent 控制主链？**

```python
# 危险的设计（如果让 LLM 决定流程）
模型可能：
  - 跳过 plan_review（绕过人工审核）❌
  - 跳过 final_validate（不经校验就交付）❌
  - 先生成组件再生成主体（违反物理规则）❌
  - 陷入死循环（一直重新规划）❌

# 当前设计（Workflow 控制主链）
LangGraph 保证：
  - 必经审核点 ✅
  - 必经校验点 ✅
  - 正确的生成顺序 ✅
  - 有限的执行步数 ✅
```

### 2.3 第二层：节点执行（Guided Generation 模式）

**典型示例**：`wild-server/app/agent/generation/architecture/workflow.py::architecture_planner`

**节点内部的固定流程**：

```python
async def architecture_planner(state: GenerationState) -> dict:
    # ═══ 第 1 阶段：确定性前处理 ═══
    
    # 1.1 提取输入
    user_message = state["user_message"]
    execution_plan = state.get("execution_plan")
    
    # 1.2 RAG 检索（必须执行）
    spec_text = agent_service.spec_loader.load_many([...])
    
    # 1.3 构建 Prompt（固定模板 + 动态内容）
    prompt = build_architecture_plan_prompt(...)
    
    # 1.4 注入动态任务
    phase_guidance = execution_plan_phase_guidance(execution_plan, "architecture")
    requirement_guidance = structured_requirement_guidance(
        state.get("structured_requirements"), 
        "architecture"
    )
    prompt += guidance
    
    # ═══ 第 2 阶段：Agent 决策（单次 LLM 调用）═══
    
    # 2.1 LLM 生成唯一最终总体方案
    llm_result = await invoke_llm(llm, messages)
    # 模型自主决策：
    #   - 体量比例与层数如何落地？
    #   - 屋顶类型与立面节奏？
    #   - 用什么设计理念？
    
    # ═══ 第 3 阶段：确定性后处理 ═══
    
    # 3.1 解析 JSON
    raw_plan = extract_json_object(reply_text)
    
    # 3.2 格式恢复（如果解析失败）
    if raw_plan is None:
        raw_plan = await recover_single_json(...)
    
    # 3.3 确定性归一化（只补齐/裁剪，不改写设计意图）
    plan = normalize_architecture_plan(
        raw_plan,
        user_message=...,
        complexity_profile=...,
        profile=...,
    )
    
    # 3.4 约束检查（确定性，不是 LLM 判断的）
    violations = architecture_requirement_violations(plan, requirements)
    if violations:
        return {"status": "failed", "error": ...}
    
    # 3.5 构建设计文档
    design_document = build_design_document_or_error(plan, ...)
    
    # 3.6 返回结果
    return {
        "architecture_plan": plan,
        "design_document": design_document,
        ...
    }
```

**关键特征**：

```
┌──────────────────┐
│ 确定性前处理      │  ← 保证输入质量
│ (RAG + Prompt)   │     必须执行，不能跳过
├──────────────────┤
│ Agent 决策        │  ← 创造性生成
│ (单次 LLM)       │     自主决定内容
├──────────────────┤
│ 确定性后处理      │  ← 保证输出质量
│ (过滤 + 验证)    │     必须执行，不能跳过
└──────────────────┘
```

**为什么不用 ReAct 模式？**

```python
# 如果用 ReAct（循环 Think-Act-Observe）
async def architecture_planner_react(state):
    max_steps = 10
    
    for step in range(max_steps):
        # Think: LLM 决定下一步
        thought = llm("我应该做什么？")
        
        # Act: LLM 调用工具
        if "search_rag" in thought:
            result = rag_search()
        elif "generate" in thought:
            result = generate_candidate()
        elif "done" in thought:
            break
        
        # Observe: 观察结果

# 问题：
# ❌ 可能跳过 RAG（质量差）
# ❌ 可能循环生成浪费 Token（成本高）
# ❌ 可能跳过约束检查（不安全）
# ❌ 可能死循环（不可控）
```

**当前设计的优势**：

```python
# Guided Generation
async def architecture_planner(state):
    # RAG 必须执行
    spec_text = rag_search(...)  # ← 不能跳过
    
# LLM 只负责生成方案本体
plan = llm.generate(...)  # ← 单次调用

# 槽位与配额一致性由 DesignDocument 契约强制（不能跳过）
    
    # 优势：
    # ✅ 关键步骤不会被跳过
    # ✅ 成本可控（只调用一次 LLM）
    # ✅ 质量可控（确定性验证）
    # ✅ 可调试（每步都有日志）
```

### 2.4 第三层：内容生成（LLM 的 Agent 决策）

**在 Prompt 范围内，LLM 完全自主决策**：

```python
# architecture 节点的 LLM 决策
模型可以决定：
  ✅ 输出 1 个完整的最终总体方案
  ✅ 该方案的尺寸、层数、体量
  ✅ 屋顶类型（flat/gable/hip/...）
  ✅ 立面开间数量
  ✅ 设计理念和风格

模型不能决定：
  ❌ 要不要执行 RAG
  ❌ 要不要经过约束检查
  ❌ 下一个节点是谁
  ❌ 跳过某个步骤
```

---

## 三、dynamic_tasks 的本质与作用

### 3.1 容易产生的误解

**误解 1**："dynamic_tasks 会动态调度节点"

```
❌ 错误理解：
    Planner 生成 task_1 → 执行节点 A
    Planner 生成 task_2 → 执行节点 B
    （节点由任务决定）

✅ 实际情况：
    节点顺序由 LangGraph 固定
    dynamic_tasks 只是给各节点提供业务指导
```

**误解 2**："dynamic_tasks 让 LLM 在内部分步骤执行"

```
❌ 错误理解：
    Planner 的 LLM 调用会：
      - 先执行 task_1
      - 再执行 task_2
      - 最后执行 task_3
    （一次 LLM 调用完成所有任务）

✅ 实际情况：
    Planner 只是一次性生成任务列表
    实际执行仍由固定节点各自调用 LLM 完成
```

### 3.2 dynamic_tasks 的真正作用

**代码位置**：`wild-server/app/agent/planning/workflow.py::execution_planner`

```python
# Planner 生成动态任务
async def execution_planner(state):
    # 1. 一次 LLM 调用生成所有任务
    llm_result = await invoke_llm(llm, messages)
    
    # 2. 解析任务列表
    raw_tasks = parsed_result.get("tasks", [])
    # raw_tasks = [
    #     {
    #         "title": "确定两层主体",
    #         "phase": "architecture",
    #         "objective": "设计体量与层数",
    #         "acceptance": ["建筑必须为两层"]
    #     },
    #     ...
    # ]
    
    # 3. 归一化（phase 映射、ID 生成、依赖排序）
    dynamic_tasks = normalize_dynamic_tasks(raw_tasks)
    
    # 4. 编译为结构化要求
    requirements = compile_structured_requirements(dynamic_tasks)
    
    # 5. 返回 State
    return {
        "execution_plan": {
            "dynamic_tasks": dynamic_tasks,  # ← 自然语言任务
            ...
        },
        "structured_requirements": requirements,  # ← 可验收的约束
        ...
    }
```

**dynamic_tasks 的四个作用**：

#### 1️⃣ 面向用户的计划展示

```yaml
dynamic_tasks:
  - id: task_1
    title: "确定两层主体"
    objective: "设计建筑体量与层数"
    phase: "architecture"
    acceptance:
      - "建筑必须为两层"
      - "主体尺寸约 12m × 8m"
```

**用途**：在 `plan_review` 审核时，用户能看懂"这次要做什么"

#### 2️⃣ 编译为结构化要求

```python
# 从自然语言编译为可验收的约束
compile_structured_requirements(dynamic_tasks)

# 输入：
{
    "acceptance": ["建筑必须为两层"]
}

# 输出：
{
    "id": "req_task_1_1",
    "kind": "architecture_floor_count",
    "target": "architecture.massing.floors",
    "operator": "eq",
    "expected": 2,  # ← 从"两层"提取
    "consumers": ["architecture", "skeleton", "final_validate"],
    "validator": "architecture_floor_count",  # ← 注册的检查器
    "severity": "error"
}
```

**用途**：节点用确定性约束指导生成，最终可以逐条验收业务要求

#### 3️⃣ 生成动态 Guidance

```python
# architecture 节点读取相关任务
phase_guidance = execution_plan_phase_guidance(execution_plan, "architecture")
# 返回：
# "- 确定两层主体：设计体量与层数；验收：建筑必须为两层"

requirement_guidance = structured_requirement_guidance(requirements, "architecture")
# 返回：
# "- [req_task_1_1] 建筑必须为两层；target=massing.floors；expected=2"

# 拼接到 Prompt
prompt += phase_guidance + requirement_guidance
```

**用途**：让节点的 LLM 知道"这次具体要完成什么"

#### 4️⃣ 追踪执行状态

```python
# 阶段完成后执行验收
acceptance_results = evaluate_acceptance_results(
    state=state,
    result=architecture_result,
    phase="architecture"
)
# {
#     "acc_task_1_1": {
#         "status": "passed",
#         "expected": 2,
#         "observed": 2,  # ← 实际层数
#         "validator": "architecture_floor_count"
#     }
# }

# 根据验收结果更新任务状态
update_dynamic_task_statuses(plan, acceptance_results, ...)
# task_1.status: "pending" → "completed"
```

**用途**：前端显示任务进度，证明业务要求已实现

### 3.3 完整链路

```
用户需求："生成一个两层别墅"
    ↓
Planner 一次 LLM 调用
    ↓
dynamic_tasks: [
    {title: "确定两层主体", acceptance: ["建筑必须为两层"]}
]
    ↓ 编译
structured_requirements: [
    {operator: "eq", expected: 2, validator: "floor_count"}
]
    ↓ 注入 Prompt
architecture 节点 LLM
    输出唯一最终方案（2层）
    ↓ 确定性归一化
normalize_architecture_plan
    裁剪到 profile 允许范围，补齐派生值
    ↓ DesignDocument 契约校验
    槽位数量必须落在配额内
    ↓ 阶段完成验收
evaluate_acceptance_results
    检查：实际层数 = 2
    结果：acc_task_1_1 = "passed"
    ↓ 更新任务状态
update_dynamic_task_statuses
    task_1.status = "completed"
    ↓
前端显示：✅ 任务 1 已完成
```

---

## 四、Agent 与 Workflow 的边界

### 4.1 系统各部分的职责

```
┌─────────────────────────────────────────────────────┐
│ LangGraph 图结构 (Workflow)                          │
│ - 负责：固定节点顺序、安全边界、人工审核点            │
│ - 不负责：业务内容生成、具体参数决定                  │
├─────────────────────────────────────────────────────┤
│ dynamic_tasks (Plan)                                │
│ - 负责：描述本次需求要完成什么                        │
│ - 不负责：决定节点顺序、控制执行流程                  │
├─────────────────────────────────────────────────────┤
│ structured_requirements (Constraints)               │
│ - 负责：可验收的业务约束                              │
│ - 不负责：如何生成内容                                │
├─────────────────────────────────────────────────────┤
│ 节点函数 (Workflow Steps)                            │
│ - 负责：确定性前后处理、调度 LLM                      │
│ - 不负责：决定生成什么内容（交给 LLM）               │
├─────────────────────────────────────────────────────┤
│ LLM (Agent)                                         │
│ - 负责：在 Prompt 范围内自主决定生成内容              │
│ - 不负责：改变流程、跳过步骤、调用未注册工具          │
└─────────────────────────────────────────────────────┘
```

### 4.2 为什么不是纯 Agent？

**纯 Agent 系统（如 AutoGPT）**：

```python
while not done:
    # 模型完全自主决策
    action = llm.decide_next_action([
        "search_web",
        "write_code",
        "run_tests",
        "done"
    ])
    
    if action == "search_web":
        search_web()
    elif action == "write_code":
        write_code()
    # ...模型决定循环次数和顺序
```

**问题**：
- ❌ 可能陷入死循环
- ❌ 可能跳过关键步骤（如测试、审核）
- ❌ 成本不可控（无限调用 LLM）
- ❌ 质量不稳定（无确定性保障）

**WildAgent 的设计**：

```python
# 主链固定
for stage in [architecture, material_plan, skeleton, ...]:
    # 节点内 Agent 自主决策内容
    result = stage.agent_generate(guidance=dynamic_tasks[stage])
    
    # 但必须经过这个节点，不能跳过
    validate(result)
```

**优势**：
- ✅ 关键步骤不会被跳过
- ✅ 成本可控（节点数固定）
- ✅ 质量可控（确定性验证）
- ✅ 人工审核点可靠

### 4.3 为什么不是纯 Workflow？

**纯 Workflow 系统**：

```python
# 所有逻辑都是确定性的
def generate_building(user_input):
    # 固定参数
    floors = 2
    width = 12
    depth = 8
    roof_type = "gable"
    
    # 固定模板
    building = create_building(floors, width, depth, roof_type)
    return building
```

**问题**：
- ❌ 无法适应不同需求（所有别墅都一样）
- ❌ 缺乏创造性（只能套模板）
- ❌ 无法理解自然语言（"现代感强"、"简约风格"无法解析）

**WildAgent 的设计**：

```python
# 关键决策点由 Agent 完成
def generate_building(user_input):
    # LLM 理解需求
    plan = planner_agent.generate_plan(user_input)
    
    # LLM 生成创意方案
    candidates = architecture_agent.generate_candidates(plan)
    
    # 确定性过滤
    selected = filter_by_constraints(candidates, plan.requirements)
    
    return selected
```

**优势**：
- ✅ 适应不同需求（每次方案不同）
- ✅ 有创造性（LLM 自主设计）
- ✅ 理解自然语言（提取意图和约束）

---

## 五、三种 Agent 模式在项目中的应用

### 5.1 ReAct（Reasoning + Acting）

**定义**：循环执行 Think → Act → Observe，模型决定每步做什么

**WildAgent 中的使用**：❌ 未使用

**原因**：建筑生成有明确的必经步骤（RAG → 生成 → 验证），不能让模型决定跳过

### 5.2 Plan-and-Execute

**定义**：先规划所有步骤，再按计划执行

**WildAgent 中的使用**：✅ 系统层使用

**代码位置**：
- Plan：`execution_planner` 生成 `dynamic_tasks`
- Execute：LangGraph 固定节点执行

```python
# Plan 阶段
planner → dynamic_tasks = [task_1, task_2, task_3]

# Execute 阶段
architecture → 执行（读取 task_1 guidance）
skeleton → 执行（读取 task_2 guidance）
final_validate → 执行（读取 task_3 guidance）
```

**特点**：
- ✅ 规划与执行分离
- ✅ 成本可控（只规划一次）
- ✅ 可预测（知道会做哪些任务）

### 5.3 Reflexion（反思模式）

**定义**：生成 → 评价 → 反思 → 改进 → 重新生成

**WildAgent 中的使用**：✅ Callback 节点使用

**代码位置**：`wild-server/app/agent/repair/workflow.py::callback_node`

```python
async def callback_node(state):
    # 1. 获取失败组件
    failed_components = state.get("failed_components", [])
    
    # 2. LLM 生成修复动作
    repair_actions = llm.generate_repairs(failed_components)
    
    # 3. 执行修复
    candidate_blueprint = execute_repair_actions(repair_actions, ...)
    
    # 4. 重新校验
    new_results = validate_blueprint(candidate_blueprint)
    
    # 5. 比较错误数
    if new_errors < old_errors:
        # 接受修复
        return {"status": "improved", ...}
    else:
        # 拒绝修复，可能再次重试
        return {"status": "rejected", ...}
```

**特点**：
- ✅ 自我改进能力
- ✅ 有限次数重试（避免死循环）
- ✅ 基于实际错误反馈改进

### 5.4 Guided Generation（引导式生成）

**定义**：确定性前处理 + 单次 LLM 生成 + 确定性后处理

**WildAgent 中的使用**：✅ 所有业务节点使用

**代码模式**：

```python
async def node_function(state):
    # ═══ 确定性前处理 ═══
    rag_context = rag_search(...)
    guidance = get_dynamic_guidance(state)
    prompt = build_prompt(rag_context, guidance)
    
    # ═══ Agent 决策（单次 LLM）═══
    result = await llm.generate(prompt)
    
    # ═══ 确定性后处理 ═══
    parsed = parse_result(result)
    normalized = normalize(parsed)
    violations = check_constraints(normalized)
    if violations:
        return {"status": "failed"}
    
    return {"output": normalized}
```

**特点**：
- ✅ 关键步骤不会被跳过
- ✅ 成本可控（单次 LLM 调用）
- ✅ 质量可控（确定性验证）

---

## 六、核心设计决策的理由

### 6.1 为什么主链必须是固定的 Workflow？

**如果让 Agent 控制主链**：

```python
# 危险示例
while not done:
    next_action = llm("下一步应该做什么？")
    
    if next_action == "skip_review":
        # 绕过人工审核 ❌
        pass
    elif next_action == "skip_validation":
        # 跳过校验直接交付 ❌
        pass
```

**当前设计的保障**：

```python
# 必经审核点
plan_review → 人工批准才能继续
design_review → 人工批准才能继续

# 必经校验点
final_validate → 零错误才能交付

# 物理顺序约束
必须：skeleton → components
不能：components → skeleton（先有主体才能加细部）
```

### 6.2 为什么节点内部不用 ReAct？

**ReAct 的问题**：

```python
# 可能的执行路径
步骤1: 模型决定"跳过 RAG，直接生成"
  → 结果质量差 ❌

步骤2: 模型决定"先出第一版方案"
步骤3: 模型决定"再出第二版方案"  
步骤4: 模型决定"再出第三版方案"
  → Token 浪费 ❌

步骤5: 模型决定"不检查约束，直接返回"
  → 违反业务规则 ❌
```

**Guided Generation 的保障**：

```python
# 固定流程
1. RAG 检索（必须执行）
2. 构建 Prompt（必须执行）
3. 调用 LLM（单次）
4. 解析结果（必须执行）
5. 约束检查（必须执行）

# 每步都可审计、可调试、成本可控
```

### 6.3 为什么需要 dynamic_tasks？

**如果没有 dynamic_tasks**：

```python
# 所有节点使用相同的固定 Prompt
architecture_prompt = """
生成一个建筑方案，包含：
- 2层
- 12m × 8m
- gable 屋顶
"""

# 问题：
# ❌ 所有别墅都一样（无差异化）
# ❌ 无法适应不同需求
# ❌ 用户无法审核和调整计划
```

**有 dynamic_tasks 的优势**：

```python
# 针对不同需求生成不同任务
需求 A: "两层别墅" → task: 确定两层主体
需求 B: "三层办公楼" → task: 确定三层主体、设计电梯井

# 用户可审核
plan_review → 用户看到任务列表 → 可以要求修改

# 可追踪验收
每个任务 → 结构化要求 → 逐条验收 → 证明完成
```

---

## 七、面试时的表达框架

### 7.1 系统定位

**❌ 错误说法**：
- "这是一个 Workflow 系统"
- "这是一个 Agent 系统"
- "节点用的是 ReAct 模式"

**✅ 正确说法**：

> "WildAgent 是一个 **Agentic Workflow 系统**，采用分层架构：
> 
> - **系统层**：Plan-and-Execute 模式，Planner 规划动态任务，LangGraph 固定主链执行，保证安全边界和人工审核点
> 
> - **节点层**：Guided Generation 模式，确定性前后处理 + 单次 LLM 生成，保证质量和成本可控
> 
> - **修复层**：Reflexion 变体，Callback 节点的有限次数自我修正
> 
> 这种混合架构结合了 Workflow 的可控性和 Agent 的灵活性，是工业级 Agent 系统的最佳实践。"

### 7.2 dynamic_tasks 的作用

**❌ 错误说法**：
- "dynamic_tasks 控制节点执行顺序"
- "dynamic_tasks 让 LLM 分步骤执行任务"

**✅ 正确说法**：

> "dynamic_tasks 是 Planner 的一次性规划输出，它的作用是：
> 
> 1. **面向用户**：在 plan_review 时展示可审核的任务清单
> 
> 2. **编译为约束**：转换为 structured_requirements，作为 Guidance 注入节点 Prompt，并由验收闭环逐条核对
> 
> 3. **生成 Guidance**：拼接到节点 Prompt，让 LLM 知道本次要完成什么
> 
> 4. **追踪验收**：逐条验收业务要求，证明任务完成
> 
> 节点顺序由 LangGraph 固定，dynamic_tasks 不控制执行流程。"

### 7.3 为什么不用纯 Agent？

**✅ 正确说法**：

> "建筑生成有明确的物理约束和安全要求：
> 
> - **物理约束**：必须先有主体再加细部，不能颠倒
> 
> - **安全要求**：必须经过人工审核和完整校验，不能跳过
> 
> - **成本控制**：需要预测执行步数和 Token 消耗
> 
> 纯 Agent 可能跳过关键步骤、陷入死循环、成本不可控。我们用 Workflow 控制主链，在安全边界内给 Agent 自主决策空间。"

### 7.4 节点内部为什么不用 ReAct？

**✅ 正确说法**：

> "每个业务节点（如 architecture）有明确的必经步骤：
> 
> 1. RAG 检索（保证知识覆盖）
> 2. 构建 Prompt（注入动态约束）
> 3. LLM 生成（Agent 创造性发挥）
> 4. 约束过滤（确定性质量保障）
> 5. 设计文档构建（契约校验）
> 
> 如果用 ReAct 让 LLM 决定这些步骤，可能跳过 RAG 或约束检查，导致质量不稳定。
> 
> 我们用 Guided Generation 模式：固定前后处理保证质量，单次 LLM 调用保证成本可控。"

---

## 八、与其他 Agent 系统的对比

### 8.1 AutoGPT / BabyAGI（纯 Agent）

```
特点：
  ✅ 完全自主，可以处理开放式任务
  ❌ 可能陷入死循环
  ❌ 成本不可控
  ❌ 质量不稳定

适用场景：
  - 探索性任务
  - 对质量要求不高
  - 允许多次尝试
```

### 8.2 LangChain Sequential Chain（纯 Workflow）

```
特点：
  ✅ 完全可控，成本可预测
  ❌ 缺乏灵活性
  ❌ 无法适应不同需求
  ❌ 只能套用固定模板

适用场景：
  - 固定流程任务
  - 对输出格式要求严格
  - 不需要创造性
```

### 8.3 WildAgent（Agentic Workflow）

```
特点：
  ✅ 可控的主链（Workflow）
  ✅ 灵活的内容生成（Agent）
  ✅ 成本可预测
  ✅ 质量有保障

适用场景：
  ✅ 专业领域生成任务（建筑、代码、设计）
  ✅ 需要人工审核点
  ✅ 有明确的质量标准
  ✅ 需要适应不同需求
```

### 8.4 业界类似实践

| 系统 | 架构 | 相似点 |
|---|---|---|
| **GitHub Copilot** | 固定上下文收集 + LLM 生成 + 语法检查 | Guided Generation |
| **OpenAI GPTs** | System Instructions + 单次对话 + 工具后处理 | 确定性边界 |
| **Anthropic Claude Projects** | 固定 Prompt + 生成 + 约束 | 引导式生成 |
| **Microsoft Semantic Kernel Plans** | 计划 → 固定执行器 | Plan-and-Execute |
| **CrewAI Sequential Process** | 固定节点 + 多 Agent 协作 | 分层架构 |

**共同原则**：
> **用 Workflow 控制大流程，用 Agent 处理决策点**

---

## 九、需要继续深入理解的方向

### 9.1 当前已掌握

✅ 系统整体是 Agentic Workflow，不是纯 Agent 也不是纯 Workflow
✅ 三层架构：主链调度 + 节点执行 + 内容生成
✅ dynamic_tasks 的四个作用：展示、编译、指导、验收
✅ 为什么不用 ReAct：需要保证必经步骤
✅ Guided Generation 的优势：质量和成本可控

### 9.2 需要更多实践积累

⏳ **不同 Agent 模式的适用场景判断**
- 什么时候用 ReAct？（探索性任务、工具调用密集）
- 什么时候用 Plan-and-Execute？（明确流程、成本敏感）
- 什么时候用 Reflexion？（需要自我改进、有评价标准）

⏳ **Agent 与 Workflow 的权衡**
- 哪些环节必须用 Workflow 固定？
- 哪些环节可以交给 Agent 决策？
- 如何设计安全边界？

⏳ **复杂 Agent 系统的调试技巧**
- 如何追踪 Agent 决策过程？
- 如何评估 Agent 输出质量？
- 如何控制成本和延迟？

⏳ **多 Agent 协作模式**
- 如何设计 Agent 之间的通信协议？
- 如何避免 Agent 之间的冲突？
- 如何实现 Agent 的动态调度？

### 9.3 建议的学习路径

1. **阅读更多 Agent 系统的实现**
   - LangGraph 官方示例
   - AutoGPT 源码
   - CrewAI 文档

2. **对比不同架构的优劣**
   - 自己实现一个简单的 ReAct Agent
   - 对比 ReAct 和 Guided Generation 的成本差异
   - 分析什么场景下 ReAct 更合适

3. **实践 Agent 评估**
   - 如何定义 Agent 的成功标准？
   - 如何量化 Agent 的输出质量？
   - 如何设计 Agent 的回归测试？

4. **深入 LangGraph 高级特性**
   - Subgraph 的使用场景
   - Dynamic Routing 的实现
   - State Management 的最佳实践

---

## 十、总结

### 10.1 核心认知

1. **WildAgent 是 Agentic Workflow 系统**
   - 不是纯 Agent（太自由，不可控）
   - 不是纯 Workflow（太死板，无创造性）
   - 是两者的有机结合

2. **三层架构各司其职**
   - 第 1 层：Workflow 控制主链（安全边界）
   - 第 2 层：Guided Generation 执行节点（质量保障）
   - 第 3 层：Agent 生成内容（创造性发挥）

3. **dynamic_tasks 不控制流程**
   - 作用：展示、编译、指导、验收
   - 不作用：决定节点顺序、控制执行

4. **设计决策都有明确理由**
   - 固定主链：物理约束 + 安全要求
   - 不用 ReAct：必经步骤 + 成本控制
   - 需要 dynamic_tasks：差异化 + 可验收

### 10.2 面试表达模板

> "我参与的 WildAgent 是一个建筑生成的 **Agentic Workflow 系统**。
> 
> 系统采用 **Plan-and-Execute + Guided Generation + Reflexion** 的混合架构：
> 
> - Planner 规划动态任务，但执行顺序由 LangGraph 固定，保证物理约束和安全边界
> 
> - 每个节点用 Guided Generation 模式：RAG 检索 + 单次 LLM 生成 + 确定性验证
> 
> - Callback 节点用 Reflexion 变体：有限次数的自我修正
> 
> 我重点优化了计划—约束—验收闭环：让 dynamic_tasks 从自然语言编译为 structured_requirements，作为 Guidance 注入节点 Prompt，最终逐条验收业务要求。
> 
> 这种设计既保证了质量和成本可控，又保留了针对不同需求动态调整的能力。"

### 10.3 持续学习

Agent 系统设计是一个快速发展的领域，需要：

- ✅ 多看不同系统的实现
- ✅ 多对比不同模式的优劣
- ✅ 多实践不同场景的设计
- ✅ 多总结经验和教训

**本文档会随着你的理解深入而持续更新。**

---

> **最后的建议**：
> 
> Agent 系统没有银弹，关键是理解每种模式的适用场景。
> 
> WildAgent 的设计不是唯一正确答案，但它代表了工业级 Agent 系统在质量、成本、可控性之间的一种平衡。
> 
> 随着你见到更多 Agent 系统，会逐渐形成自己的判断标准。
> 
> 保持好奇，持续学习！💪
