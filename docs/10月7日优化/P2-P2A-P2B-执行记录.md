# P2 / P2A / P2B 执行记录

日期：2026-10-08。实现状态：代码完成。运行验收：用户待测。没有运行 pytest、构建、类型检查、真实生成或渲染。仅核对源码调用、文档和 git diff；未提交、推送或部署。

P1 保持已完成状态。原有未提交的 design_blocks.py / design_workflow.py 改动已保留，在其上接入本轮能力。

## 架构重构后的补充核对（2026-10-08）

当前仓库已包含结构调整提交 `4a1cc96`。上文“未提交”描述的是 Agent 未执行提交操作，不代表这些实现仍未进入用户的提交历史。此次保留工作区已有的形制标签、实例宿主、材质角色及编译器修改。

按现行源码重新核对：`graph.py` → `nodes/*` 薄入口 → `design_flow/review.py`、`compile.py`、`convergence.py`。共享编译仍在 `app/design/compilation.py`；完善实现仍在 `generation/architecture/completion.py`，模型批次边界为 `revision_task.py`；最终一致性检查仍在 `validation/workflow.py`，位于几何缓存之外。审核版本和收敛回归用例的替换目标已指向 `design_flow` 实现模块。

补充修复：SVG 中斜向墙开口的显示宽度改为世界坐标两端在对应立面轴上的距离，保留原始物理宽度作为提示信息；此前直接显示物理宽度会使斜墙开口画得过宽。`test_compiled_review.py` 增加 front/left 两个投影方向的回归用例。

结论：P2、P2A、P2B 的代码交付已具备，重构后的入口仍连通。此结论来自源码和差异核对；未运行任何测试、构建、类型检查或真实生成，运行验收及视觉效果仍待用户确认。

## P2：审核与编译共用解释

建筑链：DesignDocument → design/compilation.py::compile_document → 原 compile_design → project_compilation → ResolvedDesign/SVG。正式 compile_node 使用同一 document 编译适配，不再读取另一份 plan 重新决定审核尺寸。旧无文档 checkpoint 保留原编译入口。

- facade_slots 使用实际 door/window/bay_window 实体 ID、parent_wall、local_from、world_from、宽高和绝对标高。局部 X 沿父墙，Y 为绝对标高；负向墙段投影使用两端最小值。
- projection_elements 是仅供服务器 SVG 使用的临时编译投影子集，序列化时排除，不把一份主体几何再塞入 State/前端响应，也不是第二份设计输入。SVG 从实际墙、屋顶参数和开口投影，不再按 shape 自行发明收分轮廓。
- 屋顶虚线是编译参数范围示意，不是引擎曲面渲染。底层平面和两面立面保留设计路径锚点。
- resolver_version=compiler-projection/1。渲染时不复用不同文档 hash 或旧 resolver 版本的数据。预览 API 每次从当前文档生成，revision 不符返回 409，不再直接返回旧 SVG 文件。
- design_review 先保存完善后的最新草稿再展示；中断重放时保留仓库中更新的用户 Patch，避免批准旧材质阶段文档。旧审批若缺解析版本或 hash 不匹配，compile 回到既有 design_review 重新审核当前解释。
- final_validate 在几何校验缓存之外重做审核开口一致性检查；类型、宿主、位置、尺寸和缺失均会报告。它只覆盖本阶段开口保真，不替代 P4 的完整履约。
- 文档中的材质是审核/编译共同输入；有文档时不以未写入文档的 State 材质覆盖已审视图。没有材质方案则两端都使用编译默认材质。

## P2A：决定、缺口与责任

复用 DesignConstraint，不另建一个设计真相对象：新增 expected、check、adoption、source_quote、supersedes；旧文档默认 manual，不假装可自动验证。

| 数据 | 写入方 | 读取方 | 版本/失效 |
|---|---|---|---|
| architecture 原始 design_constraints | massing 块抽取用户要求和采用决定 | build_design_document | 与本次设计一同归档 |
| document.constraints | 领域合并函数；用户明确修订/既有 Patch | 缺口评价、设计任务、审核 | 纳入 design_hash；补全循环不能改目标 |
| document.decisions | 初始设计、受限设计块修订、用户 Patch | 编译、审核、评价 | 有效修订增加 revision |
| resolved_design | 共享编译投影 | SVG、审核、最终开口检查 | hash + resolver_version；不信任旧缓存 |
| resolved.design_gaps | evaluate_design | 设计任务调度、审核问题列表 | 每次重评，携带当前 hash |
| design_convergence.tasks/rounds | 审核前完善循环 | State/trace 诊断 | 基准 hash、结果 hash、完成证据，不进入 state.plan |
| state.plan | 原审核后执行节点 | 构件执行与异常重规划 | 职责不扩展为修改批准设计 |

初始原始方案中的可执行结构化选择在归一化前保留为 architecture_draft 来源；不伪称用户要求。显式用户要求优先于重叠的模型偏好。用户硬要求必须有原文片段，否则降为待审。原文片段检查不是自然语言含义正确性的完整证明，语义提取仍需真实测试。

检查支持 equals、contains、minimum、absent；目标路径依据实际契约定位。不存在的字段/未知枚举标 unsupported，模糊或无可靠检查的关系标 needs_review。设计层 satisfied 只证明设计字段满足，不代表成品或美观通过。

旧文档缺可执行意图时保留 needs_review，不凭空补成用户目标。未满足/未确认决定时，设计说明标记“待核对”。补全不能清空目标；明确用户反馈引用及同目标 supersedes 才能替换旧决定，旧记录保留 superseded。

## P2B：审核前有界设计完善

沿现有 design_convergence 接入 completion.py，未增加主图节点：

用户意图 → architecture → material_plan → 设计缺口/编译检查 → 设计块任务与修订循环 → design_review → compile → 原 plan/execute/replanner → final_validate。

设计任务由证据确定性展开，模型负责选择具体设计修改。可定位的设计缺口与编译 error 都能创建任务；unknown/unsupported 不消失，也不派发虚假任务。体量修订会安排结构、立面、屋顶和实例关联块，仍由原 design_plan 依赖调度。

每批补丁检查：基准 hash、允许写入范围、已有 locks、当前文档契约、共享编译、缺口重评。模型说成功不等于完成。配额/required_components 等既有派生变化单独留证据；其他未授权语义修改被拒绝。新编译错误或破坏已满足决定时回退。

材质角色与绑定在每次候选编译时重新应用，实例角色仍由文档契约检查。不会在此新增资产或材质设计能力；需要新材质决策而无设计块可处理时保留缺口，P6 继续扩展。

| 限制 | 当前值/行为 |
|---|---|
| 最多修订轮数 | 沿用 3 轮 |
| 模型调用预算 | 每轮按块预留，总计最多 9 次块调用 |
| 块内重试/试算 | 每块 1 次尝试，补全环关闭额外 probe 调用 |
| 任务数 | 最多 9 个已派发块任务 |
| 连续无进展 | 2 轮后停止；按具体缺口关闭与设计变化判断 |
| 服务故障 | 停止本轮完善，保留最后有效设计与原因 |
| 回到旧设计/越权/非法补丁 | 拒绝，记录失败证据，计入无进展 |
| 没有可处理任务 | needs_review，不等于全部满足 |
| 已批准文档 | approval_boundary，不进入自动完善 |

预算是应用层块调用数，供应商 SDK 内部网络重试不在该计数中。初次起草的调用仍归原 architecture 账本，新增完善预算单列。

Graph 中模型批次使用 LangGraph task 持久化，完成的批次在同一 checkpoint 重放时复用。尚未返回/尚未持久化的请求在进程中断后仍可能重新发起；没有承诺外部模型请求 exactly-once。补丁只合入节点本地文档，整节点结果由既有 checkpoint 提交，不直接修改已批准场景。

## 用户执行的回归

新增：

- tests/design/test_compiled_review.py：真实编译与审核门窗逐项对照；修复后漂移；旧解析失效。
- tests/design/test_design_completeness.py：合法图纸仍可能缺要求；未知/不支持；禁止降低目标；明确用户修订与模型偏好的优先级。
- tests/agent/test_design_completion.py：模拟模型响应检查缺口关闭、越权拒绝、有界停止、故障、批准边界和依赖任务。此组不能证明真实模型效果。

- tests/agent/test_design_review_version.py：完善后审核持久化、保留更新的用户 Patch、历史审批返回审核。

调整：test_design_svg_silhouette.py 的验收从“固定绘制某种示意形状”改为“真实编译实体被投影且不丢开口”；保留 tiers 契约用例。test_design_blocks.py 的完整响应夹具包含新的可选决定字段。

供用户在 wild-server 执行（本轮 Agent 未运行）：

```powershell
uv run --no-sync pytest tests/design tests/agent/test_design_blocks.py tests/agent/test_design_revision_context.py tests/agent/test_design_convergence.py tests/agent/test_design_completion.py tests/agent/test_design_review_version.py tests/compiler
```

涉及前端类型和审核列表，用户另在 wild-web 执行 npm run build。

真实生成优先观察：

1. 两层 L 形建筑：同一实体在 resolved.facade_slots 和最终 Blueprint 的宿主/位置/尺寸一致。
2. 明确屋顶类型：constraints 保留要求；故意给出不同的初稿时，审核前出现关联 gap ID 的修订任务；完成后期望值不变。
3. 体量修订：下游结构/立面/屋顶/实例重新计算，旧 hash 的证据不冒充新版本。
4. 说“生成别墅”而没要求露台：不自动把无露台当成用户要求失败。
5. 不支持的逐体量屋顶或模糊审美：审核仍显示缺口，不假称设计完成。
6. 用户明确修改既有目标：新约束引用反馈并 supersedes 旧约束；批准后不被自动改回。
7. 中断恢复：已持久化模型批次不重复调用；最终设计 revision 与任务 result_hash 对应。

## 后续

下一步是 P3：归一化来源和语义改写治理。本轮对越权归一化采取拒绝/留证据，尚未重写其全部默认策略；P4 才做完整成品履约，P5 扩展几何表达，P6 扩展材质，P7 验证视觉改善。运行与效果待用户验收，不预告成功率或视觉提升幅度。
