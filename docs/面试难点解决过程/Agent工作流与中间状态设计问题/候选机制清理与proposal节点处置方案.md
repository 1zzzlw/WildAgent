# 候选机制清理与 proposal 节点处置方案

> **创建时间**：2026-09-17
> **状态**：✅ 已按「方案甲」落地（2026-09-17）
> **前置文档**：`方案候选机制重构方案.md`（2026-09-17 的实施方案，**结论已被本次盘点推翻，见 §6**）
> **实施记录**：`docs-dev/2026-09-17-architecture-candidate-mechanism-refactor.md`（原方案）、
> `docs-dev/2026-09-17-candidate-mechanism-cleanup.md`（本次清理）

---

## 落地结果（2026-09-17）

| 项 | 结果 |
| --- | --- |
| 删除文件 | `generation/architecture/proposal.py`(385 行)、`nodes/architecture_proposal_node.py`(126 行) |
| 图节点 | `architecture_proposal` / `proposal_review` 已从图中移除，`plan_review → architecture` 复原 |
| 提示词 | `candidates` 双候选协议改为"唯一最终方案顶层协议" |
| 废弃函数 | `select_architecture_plan`、`score_architecture_plan`、`architecture_requirement_violations`、`apply_structured_architecture_requirements` 及其孤儿 `_opening_slot_counts` / `_component_requirement_delivered` / `_PATTERN_GOVERNED_OPENINGS` 全部删除 |
| 全量导入 | 132 模块 0 失败 |
| 图编译 | `build_generation_graph()` 通过，`proposal_in_graph = False` |
| 测试 | `tests/agent` + `tests/components`：**201 passed, 1 xfailed**（另有 1 项遗留失败，非本次引入，见下方「落地结果」） |

### 落地中发现的两个额外问题

1. **architecture 节点原本把"概要 concept"当作 `user_message` 传给归一化**（旧
   `workflow.py:243`）。归一化会从 `user_message` 里解析层数与宽深要求，
   传 `"三层对称欧式别墅"` 会污染解析结果。已改回真实 `user_message`。
2. **高层兜底方案自身不自洽（遗留缺口，与本次清理无关）**：
   `normalize_architecture_plan({}, "建造二十一层办公楼")` 给出 `window` 配额 `84~84`，
   而立面 pattern 只在 `modeled_floors=10` 上展开、实际槽位 69，
   `DesignDocument` 契约直接拒绝。已在
   `tests/agent/test_architecture_quota_consistency.py` 用 `xfail(strict=True)` 固化记录，
   修复 `_fallback_plan` 后会转为 XPASS 提醒删除标记。

---


## 0. 一句话结论

候选机制不是"没删干净"，而是**半途重构留下的三个叠加缺陷**：

1. `proposal_review` 的 `interrupt()` **没有任何消费方** —— 走到这里必然报"未返回结果"；
2. `architecture` 提示词**仍在索要 2 个候选**，但选候选的代码已经删了 —— LLM 输出的方案被**整体丢弃**，实际用的是确定性兜底方案；
3. **非计划模式下 `architecture_proposal` 根本不在链路上** —— 默认模式永远看不到方案选择。

因此"删除候选相关的东西"和"proposal 节点有问题"是**同一件事的两面**：删掉候选协议的残余，`architecture` 就恢复正常；`proposal` 双节点因为链路未打通，建议直接删除（理由见 §4）。

---

## 1. 现状链路核对（先确认事实）

### 1.1 计划模式（`plan_mode=true`）

```
classifier → planning_research → planner → plan_validator → plan_review
   → architecture_proposal → proposal_review ——✗ 断在这里
```

| 位置 | 事实 |
| --- | --- |
| `app/agent/graph.py:140-141` | 非计划模式下 `intent=generate` **直接** 去 `architecture` |
| `app/agent/planning/workflow.py:389` | 只有 `plan_review` 批准才返回 `architecture_proposal` |
| `app/agent/graph.py:431` | `architecture_proposal → proposal_review` 无条件直连 |
| `app/agent/nodes/architecture_proposal_node.py:66` | `proposal_review` 内 `interrupt({type: "proposal_selection", ...})` |
| `app/api/ws_agent.py:1278` | 只判断 `"plan_review" in snapshot.next` |
| `app/api/ws_agent.py:1304` | 只判断 `"design_review" in snapshot.next` |
| `app/api/ws_agent.py:746-752` | resume 只认 `_execution_plan_review` / `_design_review` |
| `wild-web/src/agent/agentBridge.ts:682` | 只处理 `execution_plan_review_required` |
| `wild-web/src/agent/agentBridge.ts:700` | 只处理 `design_review_required` |

**推论**：`snapshot.next = {"proposal_review"}` 时两个 `if` 都不命中 → `final_state is None`
→ `ws_agent.py:1338` 发出 `"未返回结果"` + `send_step(... "处理失败")`。

即 **计划模式下的生成请求 100% 失败**，前端也**没有任何途径**渲染或恢复这个中断。

### 1.2 非计划模式（默认）

`classifier` → `architecture`，`state["selected_proposal"]` 恒为空 dict。
`architecture_proposal` 节点在该模式下**从未执行**。

---

## 2. 缺陷二：architecture 节点丢弃 LLM 输出（🔴 最高优先级）

**这是比 proposal 断链更隐蔽、影响更大的问题。**

| 环节 | 内容 |
| --- | --- |
| `app/agent/prompts/planning.py:179` | `- 给出 2 个可实施候选，差异必须体现在体量比例、立面节奏或屋顶上。` |
| `app/agent/prompts/planning.py:185` | `- 除 simple/minimal 外，两个候选中至少一个应通过...` |
| `app/agent/prompts/planning.py:199` | `只输出包含 candidates 数组的 JSON 对象，数组中给出两个完整候选。` |
| `app/agent/prompts/planning.py:171` | 修订分支同样要求 `仍需输出两个完整候选` |
| `app/agent/generation/architecture/workflow.py:241` | `normalize_architecture_plan(raw_plan or {}, ...)` —— 直接把 `{"candidates": [...]}` 传进去 |
| `app/agent/generation/architecture/planning.py:465` | `massing_raw = source.get("massing")` → `None`（顶层没有 `massing`） |
| `app/agent/generation/architecture/planning.py:462` | `fallback = _fallback_plan(user_message, complexity, profile)` |

**结论**：`source.get("massing") / volumes / facades / roof / component_quota` 全部取不到，
`normalize_architecture_plan` 的每一个字段都走 `fallback`。
**LLM 生成的体量、立面轴网、屋顶、构配件配额全部被丢弃**，最终蓝图由 `_fallback_plan` 决定。

> 这也解释了"生成的建筑总是差不多"这类现象：模型再努力，也只影响 `concept` 之外的 0 个字段。

原 `select_architecture_plan`（`planning.py:904`）里有一句
`candidates_raw = source.get("candidates") if ... else [source]` —— 正是它把 `candidates[0]`
摊平成顶层对象。删掉它但没有同步改提示词，就留下了这个空洞。

---

## 3. 需要删除的东西（全清单）

优先级：🔴 必须删（不删就坏） / 🟡 应删（死代码） / ⚪ 需同步改（文案、文档）

### 3.1 🔴 整文件删除（新建即废弃）

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `wild-server/app/agent/generation/architecture/proposal.py` | 385 | 方案概要生成 + 兜底候选 |
| `wild-server/app/agent/nodes/architecture_proposal_node.py` | 126 | `architecture_proposal` / `proposal_review` 双节点 |

### 3.2 🔴 图与路由回滚

| 文件 | 位置 | 动作 |
| --- | --- | --- |
| `app/agent/graph.py` | 33-36 | 删除 import |
| `app/agent/graph.py` | 182-200 | 删除 `_after_proposal_review()` |
| `app/agent/graph.py` | 320-321 | 删除两个 `add_node` |
| `app/agent/graph.py` | 423-424 | `plan_review` 条件边去掉 `architecture_proposal` 分支 |
| `app/agent/graph.py` | 431 | 删除 `add_edge("architecture_proposal","proposal_review")` |
| `app/agent/graph.py` | 433-441 | 删除 `proposal_review` 条件边 |
| `app/agent/graph.py` | 7 / 318-321 / 498-505 | 回滚流程注释、编译日志中的"方案 → "顺序说明 |
| `app/agent/planning/workflow.py` | 386-392 | `route_execution_plan_review` 恢复 `return "patch" if intent=="edit" else "architecture"` |

### 3.3 🔴 状态字段

| 文件 | 位置 | 动作 |
| --- | --- | --- |
| `app/agent/state.py` | 96-99 | 删 `architecture_proposals` / `selected_proposal` / `proposal_review_status` / `proposal_feedback` |
| `app/agent/state.py` | 104 | `architecture_diag` 注释里的"候选、评分、选中序号"改为实际语义 |

### 3.4 🔴 architecture 节点去候选化

| 文件 | 位置 | 动作 |
| --- | --- | --- |
| `app/agent/prompts/planning.py` | 171 / 179 / 185 / 199 | "2 个候选 / candidates 数组" → "1 个最终方案，顶层直接输出 massing/volumes/facades/roof/component_quota" |
| `app/agent/generation/architecture/workflow.py` | 237, 241-246 | 去掉 `selected_proposal` 依赖，`normalize_architecture_plan` 的 `user_message` 用**真实 `user_message`**（当前传的是概要 concept，会污染 `_requested_floors` 等解析） |
| `app/agent/generation/architecture/workflow.py` | 249-255 | `selection_diag` 硬编码 `candidate_count=1 / selected_index=0` → 精简为真实字段 |
| `app/agent/generation/architecture/workflow.py` | 143 | 回调文案"正在生成并比较候选方案" |
| `app/agent/generation/architecture/workflow.py` | 176-178 | `append_approved_phase_guidance` 结尾"候选选择会再次执行确定性约束检查" |
| `app/agent/generation/architecture/workflow.py` | 215-227 | 格式恢复的 `extra_instruction` 已写明"不要输出候选数组"，与 199 行协议自相矛盾，统一为一 |

### 3.5 🟡 废弃函数与孤儿

| 文件 | 位置 | 动作 |
| --- | --- | --- |
| `app/agent/generation/architecture/planning.py` | 797-870 | 删 `score_architecture_plan` |
| `app/agent/generation/architecture/planning.py` | 873-973 | 删 `select_architecture_plan` |
| `app/agent/generation/architecture/__init__.py` | 13-14, 31-32 | 删两个导出 |
| `app/agent/planning/requirements.py` | 606-661 | 删 `apply_structured_architecture_requirements` |
| `app/agent/planning/requirements.py` | 678-723 | 删 `architecture_requirement_violations` |
| `app/agent/planning/requirements.py` | 664-675 | 删孤儿 `_opening_slot_counts`（仅被上一个函数调用） |
| `app/agent/planning/requirements.py` | 726-752 | 删孤儿 `_component_requirement_delivered`（仅被 715 行调用） |
| `app/agent/planning/requirements.py` | 67 | `_PATTERN_GOVERNED_OPENINGS` 仅在 647 / 745 两处废弃函数体内使用，随之删除 |

> ⚠️ **不要动** `_check_requirement`（770）与 `evaluate_acceptance_results`（927）：它们走
> `update_dynamic_task_statuses` → 活链路，验收闭环依赖它们。
> 删除前必须复核 `_check_requirement` 是否内联了同名逻辑（当前 grep 显示无共用）。

### 3.6 🟡 测试

| 文件 | 位置 | 动作 |
| --- | --- | --- |
| `tests/components/test_architecture_plan.py` | 15 | 删 import |
| 同上 | 242-285, 456-469, 472-498, 501-..., 592-596, 1088-1094 | 6-8 个 `@pytest.mark.skip` 用例整体删除 |
| 同上 | 289, 459, 475, 504, 594, 1091 | 这些用例本身测的是 facade/conform 逻辑，只是**借** `select_architecture_plan({}, msg)` 取默认 plan；应改调 `normalize_architecture_plan({}, msg)` 后**取消 skip**，避免真实覆盖丢失 |
| 同上 | 577-580 | 删除注释掉的死断言 |
| `tests/agent/test_architecture_quota_consistency.py` | 20-23, 72, 92, 113, 130, 139 | 删 import 与 5 处调用（该文件核心是 DesignDocument 配额一致性，需重写为直接构造 plan） |
| `tests/agent/test_execution_plan.py` | 13, 139-142 | 删 import 与用例（验收断言由 `evaluate_acceptance_results` 覆盖） |

### 3.7 ⚪ 文档同步

| 文件 | 位置 | 动作 |
| --- | --- | --- |
| `docs/项目索引.md` | 33 | "总体方案生成与候选选择用例" → 去候选 |
| `docs/项目索引.md` | 144 | `architecture_requirement_violations` 标注为"当前主链"，实际已删除 |
| `docs/项目索引.md` | 176 | `score_architecture_plan` / `select_architecture_plan` 条目与行号（781/845 已过期）删除 |
| `docs/面试难点解决过程/WildAgent架构设计深度解析.md` | 71, 134-150, 223, 243, 370, 431, 718-720, 808, 1002 | 面试叙事中"生成 1-4 个候选 / 确定性约束过滤候选"的表述需改写 |
| `docs/.../Agent工作流与中间状态设计问题/解决思路.md` / `当前遇到的问题.md` | — | 候选机制相关段落同步 |
| `docs/.../Agent工作流与中间状态设计问题/方案候选机制重构方案.md` | 全文 | 该文档"预期收益"未达成，**需标注为已废弃或改写为实际结论** |
| `docs-dev/2026-09-17-architecture-candidate-mechanism-refactor.md` | 全文 | 回滚后补一份实施回滚记录 |

### 3.8 ⚪ 无需改动的（避免误删）

- `patch_proposal`（`ws_agent.py:1407/1785`、`generation_job_service.py:34/40`）：这是 **ScenePatch 提案**，与建筑候选无关。
- `app/agent/{facade,profile,skeleton,planning}.py`、`repair/**`、`validation/**`、`spec/loader.py` 里的 `candidate(s)`：均为局部变量或 RAG/修复语境，与候选机制无关。

---

## 4. proposal 节点怎么处置（三选一）

### 方案 甲：整体删除，用户参与交给已有 `design_review`（✅ 推荐）

- 删除 §3.1 两个文件，`plan_review approved → architecture` 复原；
- `design_review` 已具备完整且**已验证连通**的用户参与链路：
  `interrupt`（`design_review_node.py:33`）→ `design_review_required` 事件（`ws_agent.py:1304-1327`）
  → 前端 UI（`agentBridge.ts:700`）→ `_design_review` resume（`ws_agent.py:750`）
  → 修改意见回 `architecture`（`graph.py:399-407`）；
- 它展示的内容（DesignDocument + SVG 预览 + 体量/立面）比 proposal 的 4 个数字预览**信息量更大**，
  用户改一次方案的体验已闭环。

**为什么推荐**：proposal 层是**重复建设**——它想提供的"用户参与"能力 `design_review` 已经有了，
只是多插了一层弱契约（概要 preview 与最终体量之间没有任何强制对应关系）。
先删掉它，`plan_mode` 立刻恢复正常，同时 §2 的输出丢弃问题一并修好。

### 方案 乙：不新增节点，把"多方案"并入 `design_review`

- `architecture` 一次生成 N 个**完整**候选（保留 `candidates` 协议），后端把 N 份 DesignDocument
  都算出来，通过 `design_review` 的既有 interrupt **并列展示**；
- 前端复用已有设计审核面板，改成 tab / 卡片组；
- 零新增节点、零新增 interrupt 类型、零新增 resume 通道。

成本约 2-3 天（主要在 `design_review_node.py` + 前端面板）。适合"确实想保留多方案对比"的产品诉求。

### 方案 丙：保留双节点，补齐链路

需要补：`ws_agent` 新增 `proposal_review_required` 事件 + `_proposal_selection` resume 分支、
前端 UI + types、`docs` 协议段。成本 3-5 天，且要长期维护"概要提示词 + 详设提示词"两套协议，
而概要无法对最终体量做强约束。

### 建议

**先走甲**恢复可用（约半天，含 §2 提示词修复与测试调整）；
若确认要"多方案对比"体验，再以**乙**的形式补，而不是复活 proposal 这层。

---

## 5. 执行顺序建议

1. **先建基线**：当前所有改动（`graph.py` / `workflow.py` / `planning.py` / `requirements.py` /
   `state.py` / `prompts/planning.py` / `tests/**`）**均未提交**，动手前必须先 commit，否则回滚无安全网。
2. 删 §3.1 两个文件 + §3.2 图路由回滚 → 跑 `tests/agent/test_agent_graph_routing.py`。
3. 修 §3.4 提示词（这是让 LLM 输出真正生效的关键一步）→ 用 `.workbuddy/diag/` 的离线链路脚本
   跑一次 `ssrLoadModule` 重建，确认 `architecture_diag.used_fallback == False`。
4. 删 §3.5 废弃函数与孤儿 → 跑 `tests/agent/test_architecture_quota_consistency.py`、`test_execution_plan.py`。
5. 改 §3.6 测试（把"借默认 plan"的用例改为直调 `normalize_architecture_plan` 并取消 skip）。
6. 同步 §3.7 文档。

---

## 6. 对前置文档的修正说明

`方案候选机制重构方案.md` 的 §1.2 与 §六 断言了三项收益：

| 原预期 | 实际 |
| --- | --- |
| 删除 500+ 行复杂代码 | ❌ 仅标记 DEPRECATED，代码全部保留且仍是 §2 缺陷的成因 |
| 不再出现"所有候选均违规" | ✅ 该错误确实消失（因为检查被删了），代价是**约束校验整体失效** |
| 用户参与决策、体验提升 | ❌ 中断无人消费，计划模式下请求直接失败，用户**看不到任何方案** |

`docs-dev/2026-09-17-architecture-candidate-mechanism-refactor.md` 标注"状态：已完成"，
实际是"未连通"。两份文档都需要在落地后一并修正，否则会误导后续排查。
