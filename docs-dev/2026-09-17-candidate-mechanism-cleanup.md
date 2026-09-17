# 候选机制清理与 proposal 节点删除

**日期**: 2026-09-17
**状态**: 已完成
**类型**: 回滚 + 缺陷修复（删除半途重构的候选机制）
**前置**: `docs-dev/2026-09-17-architecture-candidate-mechanism-refactor.md`（本文回滚的对象）

---

## 背景

`2026-09-17` 上午的《方案候选机制重构》只完成了一半，留下三个叠加缺陷：

1. **`proposal_review` 的 `interrupt()` 没有消费方** —— 后端只识别 `plan_review` / `design_review`，
   前端只处理 `execution_plan_review_required` / `design_review_required`，resume 通道也只认
   `_execution_plan_review` / `_design_review`。计划模式下生成请求必然走到
   `ws_agent.py:1338` 报"未返回结果"。
2. **`architecture` 提示词仍索要 `candidates` 数组，但选候选的代码已删** —— 归一化只读顶层
   `massing / volumes / facades / roof / component_quota`，拿到 `{"candidates":[...]}` 后
   每个字段都退回 `_fallback_plan`，**LLM 生成的方案被整体丢弃**。
3. **非计划模式下 proposal 不在链路上** —— `graph.py` 的 classifier 让 `generate` 直连
   `architecture`，只有 `plan_review` 批准才进 `architecture_proposal`。

处置决策：**候选机制整体删除，用户参与能力交还已连通的 `design_review` 链路**（方案甲）。

---

## 实施内容

### 1. 删除新建的两个节点文件

- `app/agent/generation/architecture/proposal.py`（385 行）
- `app/agent/nodes/architecture_proposal_node.py`（126 行）

### 2. 图与路由回滚

**`app/agent/graph.py`**
- 删除 `architecture_proposal` / `proposal_review` 的 import
- 删除 `_after_proposal_review()` 路由函数
- 删除两个 `add_node` 及 `add_edge("architecture_proposal", "proposal_review")`
- `plan_review` 条件边移除 `architecture_proposal` 分支
- 删除 `proposal_review` 条件边
- 顶部流程注释 `architecture (总体方案候选)` → `architecture (总体方案)`

**`app/agent/planning/workflow.py:386-392`**
- `route_execution_plan_review` 恢复 `return "patch" if intent == "edit" else "architecture"`

### 3. State 字段清理

**`app/agent/state.py`**
删除 `architecture_proposals` / `selected_proposal` / `proposal_review_status` / `proposal_feedback`，
并把 `architecture_diag` 的注释从"总体方案候选、评分、选中序号"改为实际语义。

### 4. architecture 改回单方案协议（本次最关键的一步）

**`app/agent/prompts/planning.py`**
- `- 给出 2 个可实施候选，差异必须体现在体量比例、立面节奏或屋顶上。`
  → `- 只输出 1 个可实施方案，即本次交付的唯一最终方案；不要输出备选或并列方案。`
- `除 simple/minimal 外，两个候选中至少一个应通过...` → `除 simple/minimal 外，该方案应通过...`
- `只输出包含 candidates 数组的 JSON 对象，数组中给出两个完整候选。`
  → `只输出一个 JSON 对象，顶层直接给出唯一最终方案的字段；不要输出 candidates 数组、备选方案或方案对比。`
- 修订分支 `仍需输出两个完整候选` → `仍需输出一份完整方案`

**`app/agent/generation/architecture/workflow.py`**
- 去掉 `selected_proposal` 依赖；`normalize_architecture_plan` 的 `user_message` 改回**真实 `user_message`**
  （原来传的是 `selected_proposal["concept"]`，会把 `"三层对称欧式别墅"` 喂给层数/宽深解析函数，污染结果）
- `selection_diag` 去掉硬编码的 `candidate_count=1` / `selected_index=0`，只留
  `profile` / `profile_label` / `used_fallback`
- 回调文案"正在生成并比较候选方案"→"正在生成总体方案"；
  "基于您选择的方案生成详细设计"→"总体建筑方案"
- 已批准指导语结尾"候选选择会再次执行确定性约束检查"→"由真实槽位数量与配额一致性在
  DesignDocument 契约处校验"

### 5. 删除废弃函数与孤儿

**`app/agent/generation/architecture/planning.py`**
- 删除 `score_architecture_plan`（74 行）、`select_architecture_plan`（101 行）
- 删除随之失效的 import：`StructuredRequirement`、`apply_structured_architecture_requirements`、
  `architecture_requirement_violations`
- 模块 docstring `建筑方案回退、归一化、评分与候选选择。` → `建筑方案回退与归一化。`

**`app/agent/generation/architecture/__init__.py`**
- 移除两个导出

**`app/agent/planning/requirements.py`**
- 删除 `apply_structured_architecture_requirements`
- 删除 `architecture_requirement_violations`
- 删除孤儿 `_opening_slot_counts`、`_component_requirement_delivered`、`_PATTERN_GOVERNED_OPENINGS`
- **未动** `_check_requirement` / `evaluate_acceptance_results` / `update_dynamic_task_statuses`：
  它们走活链路，验收闭环依赖它们

### 6. 测试调整

**`tests/components/test_architecture_plan.py`**
- 删除纯候选用例 `test_candidate_selection_respects_explicit_floor_count`、
  `test_standard_candidate_scoring_prefers_real_articulation_without_fixed_package`
- 其余 6 个被 skip 的用例其实只把 `select_architecture_plan({}, msg)` 当"取默认 plan"的快捷方式，
  已改为 `normalize_architecture_plan({}, msg)` 并**取消 skip**，找回真实覆盖：
  `test_facade_layout_resolves_exact_non_overlapping_slots`、
  `test_merge_conformance_snaps_and_fills_minimum_openings`、
  `test_bay_window_claims_a_window_slot_without_duplicate_plain_window`、
  `test_required_bay_window_is_synthesized_from_an_approved_window_slot`、
  `test_chinese_floor_count_does_not_confuse_twenty_one_with_one`、
  `test_regular_balcony_slot_is_centered_on_an_upper_facade_opening`

**`tests/agent/test_architecture_quota_consistency.py`**
- 重写为「归一化产物必须始终满足 DesignDocument 契约」+ 契约错误转译的断言
- 新增 `xfail(strict=True)` 用例记录高层兜底配额不自洽的遗留缺口

**`tests/agent/test_execution_plan.py`**
- 删除 `test_architecture_constraints_participate_in_candidate_gate` 及 import

### 7. 文档同步

- `docs/项目索引.md`：去掉"候选选择"表述，删除已不存在函数的 3 行条目
- `docs/面试难点解决过程/Agent工作流与中间状态设计问题/`
  - `方案候选机制重构方案.md`：加废弃声明与"预期 vs 实际"对照表
  - `解决思路.md`、`当前遇到的问题.md`、`LangSmith节点状态观测指南.md`、`后续设想.md`：
    加「后续结论（2026-09-17）」标注，保留历史现场
  - `代码学习反思.md`：修正描述当前代码的两处（"生成多个候选方案/选择最佳候选"、"动态调整候选数量"）
  - 新增 `候选机制清理与proposal节点处置方案.md`（盘点 + 处置 + 落地结果）

---

## 验证

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 全量导入 | `pkgutil.walk_packages` 遍历 `app` + `app.agent` | 132 checked, **0 failures** |
| LangGraph 图 | `build_generation_graph()` | 编译通过，`proposal_in_graph = False` |
| 相关测试 | `pytest tests/components/test_architecture_plan.py tests/agent/test_architecture_quota_consistency.py tests/agent/test_execution_plan.py` | 78 passed, 1 xfailed |
| 套件回归 | `pytest tests/agent tests/components tests/test_requirements_floor_count_fix.py` | **201 passed, 1 xfailed, 1 failed** |

### 唯一的一项失败（非本次引入）

`tests/agent/test_execution_plan.py::test_model_tasks_compile_to_stable_traceable_requirements`
断言 `"建筑必须为两层"` 应编译出 `kind="architecture_floor_count"`，但
`_compile_acceptance`（`requirements.py` 中本次未改动）只识别"共/总共/分为"、"X层几何/结构"、
"单层/多层"三类总层数表达 —— 这是同一工作区里另一条在途工作（层数识别修复，
见 `docs-dev/2026-09-16-langsmith-floor-count-bug-fix.md` 与 `tests/test_requirements_floor_count_fix.py`）
尚未对齐的期望。**本次未修改该逻辑，也未改动该测试的这条断言。**

---

## 遗留与后续建议

1. **高层兜底方案配额不自洽**（已用 xfail 固化）：
   `_fallback_plan` 按 `floors=21` 给出 `window` 配额 84，立面 pattern 只在 `modeled_floors=10`
   展开、实际槽位 69 → `DesignDocument` 拒绝。修 `_fallback_plan` 后 xfail 会转 XPASS。
2. **层数识别期望不一致**（上述 1 failed）：需在 `_compile_acceptance` 与
   `test_execution_plan.py` 之间对齐，属另一条工作线。
3. **本次改动前未建立 git 基线**：工作区在该次清理前已有大量未提交改动，
   清理与既有 WIP 混在同一工作区。建议尽快提交一次基线。
4. 若后续确实要做"多方案对比"，正确做法**不是**复活 proposal 节点，而是让 `architecture`
   生成 N 个完整候选、由 `design_review` 的既有中断并列展示（复用已有事件与 UI，零新增协议）。

---

## 追加任务：能力闸门分级（同日，清理后由用户报错引出）

清理落地后用户在 Agent 模式复现：

```text
执行计划校验失败：当前 Agent 能力无法执行：生成一份明确的建筑平面草图，标注出主楼的宽度、进深尺寸（例如：宽约12米，深约10米）
```

- **判定点不在 `execution_plan_validator`**，而在 `requirements.py::_compile_acceptance`
  的关键词表——"平面草图"与"房间布局"被塞进同一个 `_contains_any`，
  都判成 `support_status="unsupported"`。
- 改造：关键词按语义分表（interior / site / presentation_medium）；媒介类降级为
  `needs_review`（warning）；`PlanValidationIssue` 增加 `severity`；
  `execution_plan_validator` 只把 `error` 计入失败。
- 附带修复：尺寸抽取只认 `a×b`，`宽12米深10米` 这类表述落不进 `architecture_dimensions`；
  新增 `_extract_plan_dimensions`，并豁免"例如/如"引导的示例值。
- 验证：`.workbuddy/diag/check_plan_gate_2026-09-17.py` 全绿；用户原句 `blocking=0`；
  `pytest tests/agent tests/components` → 199 passed / 1 xfailed / 1 failed（仍是上表第 2 条）。

完整方案与判断准则见
[`docs/面试难点解决过程/Agent工作流与中间状态设计问题/能力闸门分级与交付媒介降级方案.md`](../docs/面试难点解决过程/Agent工作流与中间状态设计问题/能力闸门分级与交付媒介降级方案.md)。

---

## 追加缺陷：本次清理把调用点写成了不存在的关键字参数（同日修复）

闸门分级落地后，用户再跑一次生成，报：

```text
错误: normalize_architecture_plan() got an unexpected keyword argument 'profile'
```

### 根因：是我这次清理引入的，不是模型幻觉

`normalize_architecture_plan` 的签名（改动前后一致）第 4 个参数叫 **`architecture_profile`**：

```python
def normalize_architecture_plan(
    raw: object,
    user_message: str = "",
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

而被删掉的 `select_architecture_plan` 第 4 个参数叫 `profile`。清理时把

```python
plan, selection_diag = select_architecture_plan(raw_plan, normalization_request, complexity_profile, profile)
```

改写成 `normalize_architecture_plan(...)` 时，把位置参转成关键字参，顺手沿用了旧名字
→ `profile=profile`。异常在 `try` 块之外（第 237 行），直接终止整轮生成。

### 连带发现的真问题：两侧尺寸解析对同一句话给出不同答案

线索来自核实上面那段文字时的实测（原本想写"架构侧不认宽深写法"，一测发现说法不准确，
真实情况更糟）：

| 输入 | 验收侧 `_extract_plan_dimensions` | 架构侧 `normalize_architecture_plan` |
| --- | --- | --- |
| 生成两层住宅，宽17米深23米 | (17, 23) | (17, 23) |
| 生成两层住宅，宽度为17米，进深为23米 | (17, 23) | (17, 23) |
| **生成两层住宅，宽约17米，深约23米** | **(17, 23)** | **(12, 9)** ← 默认值 |

根因：`profile.py::_requested_dimension` 的两条正则
（`{label}\s*{number}` / `{number}\s*{label}`）中间不允许"约/为/是/在"这类限定词，
`宽约17米` 里"宽"和"17"之间夹了"约"就整条不匹配，`requested_width` 直接返回 `None`
→ 落回 profile 默认 12×9。

危害不是"尺寸没生效"这么轻：验收侧认 17×23、生成侧给 12×9，容差 1.5 也救不回来
→ `architecture_dimensions` 校验失败 → **阻断交付**。
而这个组合之所以现在才暴露，是因为分级改造（本文件上一节）刚让
`宽约X米，深约Y米` 能编译出尺寸要求——**属于半修复**：只补了验收侧，没补架构侧。

修法：抽 `_DIMENSION_QUALIFIERS = r"(?:约|大约|大概|为|是|在)?\s*"` 并入两条正则。
已验证两侧对上述四种说法完全一致；无尺寸表述时验收侧返回 `None`、架构侧走默认，也同样一致。

新增回归：`tests/agent/test_architecture_quota_consistency.py` 中的
`test_acceptance_and_architecture_agree_on_plan_dimensions`（4 个参数化用例）
+ `test_no_dimension_request_keeps_architecture_defaults`。
**两个解析器各写各的，就必须有测试钉住它们的一致性**——这也是"重复即复杂度"的一个实例：
`app/agent/generation/architecture/profile.py` 与 `app/agent/planning/requirements.py`
各自维护了一份平面尺寸解析。

### 为什么现有验证全都漏掉了它

| 验证手段 | 为什么漏 |
| --- | --- |
| 全量导入扫描 | 不是导入错误，函数体和调用点都能正常 import |
| `build_generation_graph()` | 只编译图，从不执行节点函数体 |
| 单元测试 | 直接按位置参调用 `normalize_architecture_plan`，从不经过节点里的真实调用点 |
| `test_agent_graph_execution.py` | 把每个节点都替换成桩函数，节点内部永远不执行 |

**共同盲区：没有任何一道验证真正执行过"真实 architecture 节点"。**

### 补的两道验证

1. **静态门禁 `scripts/audit_keyword_calls.py`**（退出码即结果）：
   AST 扫描 `app/**` 中所有跨模块函数调用，用真实签名 `signature.bind()` 试绑实参，
   覆盖"未知关键字参数 / 参数过少 / 参数过多 / 参数重复"。
   本次基线：**368 个调用点、0 问题**。
   反向验证：把 `profile=profile` 放回去 → 门禁报
   `FAIL app\agent\generation\architecture\workflow.py:237 normalize_architecture_plan() -> 未知关键字参数 'profile'`。

2. **真实节点冒烟 `tests/agent/test_architecture_node_smoke.py`**：
   只打桩模型服务与检索，其余走真实代码路径（归一化 → DesignDocument 契约 → `resolve_design`）。
   反向验证：把 bug 放回去 → 两个用例都以用户看到的同一条 `TypeError` 失败。

### 门禁自身也踩过一次坑（记录备查）

第一版手写规则只检查"未知关键字"和"位置参数过多"，于是：
- 把 `def f(*usages)` 误报成"位置参数过多"（没处理 `VAR_POSITIONAL`）；
- 漏掉"缺少必填参数"这类（`structured_requirement_guidance(reqs, consumer)` 少传 consumer 查不出来）。

改为 `signature.bind()` 统一判定后两类问题一起消失。**门禁只查自己想到的类别，等于给自己留盲区。**
另外第一版因为 `sys.path[0]` 是脚本目录而 import 失败，静默跳过后报"0 个调用点、0 问题"——
所以加了 `checked == 0 → FATAL` 兜底：门禁扫不到东西绝不能算通过。

---

## 追加决策：能力缺失改为"只标记不阻断"（同日，用户明确要求）

用户又一次撞到阻断，这次四条验收条件全因句中含"车库"：

```text
执行计划校验失败：当前 Agent 能力无法执行：建筑主体为两层矩形体量（约10x12米），
附带一个一层矩形车库体量（约6x6米）；……车库位于主楼侧翼；……
```

用户随即给出产品原则（原文）：

> "就让他正常生成就行，只要他能生成出蓝图文件就可以……就算他没有能力生成车库也没关系……
> 为什么要有阻断呢？这个阻断会导致他无法生成。"

**这个判断是对的**，理由不是"用户说了算"，而是失败代价不对称：阻断 → 一张图都没有；
不阻断 → 拿到楼 + 缺的能力写在验收结果里。原设计的初衷（不许静默显示 completed）没错，
但它把**诚实**实现成了**终止**，两件事被同一个杠杆绑住了。

### 改动

| 文件 | 改动 |
| --- | --- |
| `planning/requirements.py` | 三条 `unsupported_capability` 分支补 `severity="warning"`；`validate_structured_requirements` 不再写死 `error` |
| `prompts/planning.py` 第 6 条 | 补明"服务端会标记但不会终止本轮"，避免 Planner 为绕开它而改写/重复表述 |
| `app/agent/README.md` | 同步为"两者都只标记不阻断"；写明真正会失败的只剩两类 |
| `tests/agent/test_execution_plan.py` | 两个断言旧行为的用例重写为 `..._is_reported_without_blocking` / `..._never_blocks_delivery` |

保留阻断的只有：**计划对象本身不合法**（缺字段/ID 重复/引用被篡改）与
**模型服务终态错误**。前者是数据损坏不是能力不足，放过去下游必崩。

### 验证

`.workbuddy/diag/check_no_block_2026-09-17.py` 用用户原话四条跑完整链路：
`blocking=0`、交付阶段无缺能力阻断项、真实节点 `execution_plan_status=reviewing`、
`error=None`、路由 `plan_review`（原来是 `failed` → `__end__`）。

### 顺带查清一件事：`车库` 其实不完全是"缺能力"

`.workbuddy/diag/check_garage_volume_2026-09-17.py` 喂一份
"主体 10x12 两层 + 车库 6x6 一层 + L 形相连 + hip"的方案跑真实确定性骨架：

```text
floor_1_main / floor_1_garage              车库体量有自己的楼板
wall_right_1_1 / wall_right_1_2            一层墙按 L 形缺口分段
wall_back_1_1  / wall_back_1_2
二层只剩 4 面墙                            车库只有一层，二层收窄——正是要的形状
stair_1_2                                  主楼竖向交通
```

引擎能建出车库体量（`volumes` 支持 `role=secondary` + `x/z` + `start_floor/end_floor`）。
缺的只是车库**语义**（车库门、坡道、地面坡度）。

**但没有顺手把"车库"从关键字表删掉**，因为会踩更深的坑：
`architecture_dimensions` 比对的是 `massing.width/depth`（**总轮廓**），
而用户说的是**主体尺寸**。正确 L 形方案总轮廓是 16x12，把该条编译成
`architecture_dimensions=10x12` 会让验收必然失败 → 事前阻断变成**事后阻断**，更糟。
前置条件是先把"主体尺寸 / 总轮廓尺寸"分开表达。已记入方案文档 §8。

（补记：同日复核时修正了该脚本的判据。它原先要求"墙 id 里含 `garage`"，
所以一直误报"建不出"——骨架实际是用**墙环开缺口**表达附属体量的。
改用"`floor_1_garage` 存在 + 一层墙环 >4 段 + 二层墙环 =4 段"三条证据后，
变体 A/B 均判定可建。另外顺手把 `check_plan_gate` 里两条旧期望
（缺能力 = 阻断）改为不阻断，与第 7 节政策对齐。）

---

## 追加事故：验收编译的"量词盲区"把已合并的蓝图判死（同日，用户报错引出）

用户新的报错：

```text
错误: 业务验收未通过：实际数量：{'door': 1, 'window': 13, 'roof': 1}
[1] ~ [10.2] 全部 20 个结构校验器【全部通过】
```

用户的第一反应是"合并都成功了啊，这又是什么错误"——**判断准确**，
合并确实成功了。

### 诊断入口：从持久化检查点取真实状态

这次没有再靠猜验收文本。每次运行的状态都躺在
`storage/sessions/langgraph_checkpoints.sqlite3` 里：

```python
thread_id = f"generation:{request_id}"      # 裸 request_id 查出 0 行
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
cv = SqliteSaver(conn).get_tuple({...,"checkpoint_id": ids[-1]}).checkpoint["channel_values"]
```

三个坑：`thread_id` 必须带 `generation:` 前缀；**venv 里没有 `msgpack`**，
必须用 `SqliteSaver` 走项目 serde；必须只读打开。
失败清单在 `generation_jobs`（含 `error` 原文）。

取出来的现场：

```text
user_message          = '生成一个别墅'
merged_blueprint      = dict（23 个元素）   ← 蓝图早就合并出来了
final_blueprint       = None               ← 被丢弃
material_plan.roles   = 9 个
```

### 死因

执行计划 task_4 的验收原文：**"材质方案包含墙体、屋顶、门窗至少3种材质"**。
语义是"材质至少 3 **种**"，但构件分支先命中，编译成
`{"types": ["door","window","roof"], "minimum": 3}` ——
"门窗屋顶**每种至少 3 个**"。实际 `door=1`、`roof=1` → failed
（`severity=error`）→ 阻断 → `final_blueprint = None`。

`_minimum_count` 只认「至少N」，**不区分量词**，这是根因。

### 连带查出

| 级别 | 问题 |
| --- | --- |
| 🔴 | 量词盲区：「种/类/款/类型」被当成实例量词 |
| 🔴 | `validator="material_plan_exists"` 在全仓**无任何分支产出**（死代码），且只判 `roles>0`，不读 `expected.minimum`——所以材质要求只能被构件分支抢走 |
| 🟡 | 「不少于/不低于N」完全不认 → 整条要求掉进 `phase_outcome` 兜底，退化成"检查产物存在"，**永远通过**（那次计划里「窗户数量不少于6个」「墙体数量不少于8个」都是这个下场） |
| 🟡 | 数量词不绑定名词：全句抓「至少N」后统一套到所有匹配类型 |

### 改动

`app/agent/planning/requirements.py`：

1. 量词感知：`_quantified_minimum` 返回 `(数量, 是否种类量词)`；
   `_minimum_count` 遇种类量词退回 1；新增 `_minimum_kind_count`。
   （长量词必须先匹配：`类型` 排在 `类` 前，否则被吃掉。）
2. 材质分支**前置**到构件分支之前：`_MATERIAL_TERMS` + 种类量词 →
   `kind="material_role_count"`、`validator="material_plan_exists"`、
   `expected={"minimum": N}`。
3. `material_plan_exists` 支持 `expected.minimum`（缺省 1，与旧行为等价）。
4. 两处与新政策矛盾的文案（"当前系统不支持该要求"）改为
   "当前 Agent 不具备该能力，将按可达范围生成并在交付结果中标记"。

**核心教训是分支优先级**：更具体的语义（材质）必须排在更泛的分支（构件）之前。
与之前「媒介降级分支必须放在量化抽取之后」是同一条规律的两个方向。

### 验证

- 新增 `tests/agent/test_material_kind_requirement.py`（16 项），
  含事故场景端到端放行 + 反向约束「真·实例要求不能被放水」。
- **反向证明**：临时禁用材质分支 → 精确复现事故
  （`observed` 变回 `{'door': 1, 'window': 13, 'roof': 1}`，4 项失败）；
  恢复后 16 项全过。
- 真实状态重放：`.workbuddy/diag/check_material_kind_2026-09-17.py`
  → `passed`（9 ≥ 3）、`blocking=0`。
- 全集 282 passed / 1 failed（既有层数用例）/ 1 xfailed；
  静态门禁 368 调用点 0 问题；图 38 节点。

### 没动、但必须说清的三件事

1. **「不少于/不低于」仍然不认。** 补上它会把"永远通过"变成"可能失败"，
   **新增阻断点**，与"只标记不阻断"的政策方向相反，需要先定口径。
2. **数量词仍不绑定名词。**
3. **验收失败仍会丢弃 `final_blueprint`。** 第 7 节的政策只覆盖了"编译期阻断"，
   没覆盖"交付期判死"——蓝图已产出却被一条验收判定扔掉。

### 方法论缺口（比这个 bug 本身更重要）

第 7 节的四道验证（导入扫描 / 图编译 / 单测 / 真实节点冒烟）**全绿，
这次事故依然发生**。它们用的验收文本都是我们**自己手写的**；
线上崩的是 **LLM 自己写的**验收文本。

> 验收编译器的回归输入必须来自**真实运行的计划**。
> 持久化检查点里躺着每一次真实运行的 `structured_requirements` 与
> `acceptance_results`，那才是回归集的正确来源。

