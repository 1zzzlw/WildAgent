# LangGraph 图清理勘察报告（只读分析，未改任何源码）

勘察范围：`wild-server/app/agent/graph.py`、`graph_state.py`、`nodes/*`、`execution_plan.py`、`validators/*`、`services/generation_job_service.py`、`api/ws_agent.py`，及 `wild-web/src`（前端 plan_mode 开关）与 `wild-server/tests` 引用关系。结论性前提：生产图由 `ws_agent.py:750` 以 `enable_callback=True` + SQLite checkpointer 编译；`plan_mode` 由前端 localStorage `wild_plan_mode` 决定且**新用户默认开启**（`wild-web/src/stores/agentStore.ts:85-88`），因此“计划层”是当前主流程而非死代码。

## 1. 编译后节点清单与可达性

节点全集（enable_callback=True 时）：classifier、chat、patch、planning_research、web_research、planner、plan_validator、plan_review、plan_executor、architecture、floor_plan_design、floor_space_analysis、floor_layout、floor_openings、floor_validate、floor_plan_review、material_plan、skeleton、style_review、decor_assembly、merge、final_validate、callback，外加 11 种组件各 `*_gen`/`*_val` 动态节点（graph.py:320-337，共 22 个）。

- **入口**：classifier（graph.py:353）。失败/terminal_model_error 一律 `__end__`（graph.py:134-136）。
- **chat 链**：classifier→chat→END（意图 chat 恒先于 plan_mode 判断，graph.py:142-143）。
- **edit 链**：patch（非 plan 直连 graph.py:146-147；plan 模式经 planning_research→plan_executor 分派，同走 patch 步骤）。
- **plan 层（仅 plan_mode 且意图非 chat）**：classifier→planning_research→(coverage 不足且网络可用时 web_research，graph.py:153-165)→planner→plan_validator→plan_review(interrupt)→plan_executor→白名单节点。**条件可达**：web_research 仅当 `plan_research_diag.coverage.trigger_web_research` 为真。
- **generate 主链（plan 模式经 plan_executor 逐步骤跳动，非 plan 快速链直连，二者节点集合相同）**：architecture→floor_space_analysis→floor_layout→floor_openings→floor_validate→floor_plan_review(interrupt 确认)→material_plan→skeleton（**实为 approved_plan_assembler**，见 §2）→style_review(interrupt)→decor_assembly→merge→final_validate；校验 partial 且存在未达上限的失败组件时进入 callback（graph.py:510-519，callback→final_validate 复核，graph.py:350）。
- **不可达/仅兼容节点**：
  - `floor_plan_design`：全图唯一入边是 plan_executor 条件表里的名字映射（graph.py:414），但 execution_plan.py 的能力表/DYNAMIC_TASK_PHASES 无该 type，executor 会对未注册能力直接判失败（execution_plan_node.py:418-426），`plan_next_node` 不可能等于它；其余分支（floor_plan_review 确认/修改）均指向 material_plan/floor_space_analysis。→ **结构上永不执行**（旧 checkpoint 恢复除外，见 §4 中风险项）。
  - 22 个 `*_gen`/`*_val` 节点：唯一入口是 skeleton 后的 `_dispatch_components` 派发 Send（graph.py:123-129）；`*_val→merge` 只作为 fan-in 边。主链上 Send 条件不成立（见 §2）。→ **新鲜运行永不可达**。
  - `legacy_skeleton_generator` 模块级别名（graph.py:69）：无任何图/调用方引用。

## 2. 已声明的“兼容/旧”内容逐项核实

- **skeleton_generator 别名（属实）**：graph.py:47 从 `app.agent.nodes` 导入旧 LLM skeleton（源自 skeleton_node.py），graph.py:69-70 先保存 `legacy_skeleton_generator` 再把模块内 `skeleton_generator` 重绑为 `approved_plan_assembler`；graph.py:316 `add_node("skeleton", …)` 取的是重绑后的确定性装配器。旧 LLM 版只在测试中仍被直接调用（见 §4 项 8）。
- **gen→val 何时触发（核实结果：主链上触发条件不可能被满足）**：`_dispatch_components`（graph.py:87-129）只有在 `deterministic_body_complete` 为 falsy 且复杂度非 minimal 且 `resolve_component_suggestions` 非空时才返回 Send 列表。而主链 skeleton=approved_plan_assembler：成功路径必写 `deterministic_body_complete: True`（approved_plan_assembler_node.py:99）→ 直接走 style_review；失败路径写 error/status=failed → 路由到 fail/END（graph.py:89-91）。旧 LLM skeleton（skeleton_node.py）成功时**不写**该字段，才会落入 minimal→merge 或 suggested→Send 分支——因此 Send 派发只在换回旧骨架实现（monkeypatch/旧 checkpoint）时可达。测试 `tests/agent/test_agent_graph_routing.py:37-50` 是直接对函数断言，不经过编译图。
- 命名分歧隐患：`app.agent.nodes.skeleton_generator` 仍是旧 LLM 实现（nodes/__init__.py:17），重绑只发生在 `app.agent.graph` 模块内。第三方若从 nodes 导入会拿到与主链完全不同的实现。

## 3. graph_state 字段读写核实（app 全目录 grep）

- **legacy 分片字段** `door_fragments`…`light_fragments`（graph_state.py:125-135）：运行时**无写者**（base_component_node.py:30-46 只写 `component_fragments`，明确不再双写）；读侧仅兜底：merge_node.py:123、base_component_node.py:297-299、callback_node.py:437-439（均 `component_fragments` 缺失时的旧 checkpoint 回退）。仅测试/旧脚本构造这些键（test_merge_precision、test_callback_targeted_repair、根目录 `test_graph_minimal.py:41-55`）。graph_state.py:123-124 注释与代码一致。
- **逐组件 `*_gen_diag`/`*_val_diag`（graph_state.py:143-164）**：写者仅 base_component 工厂（死链内）；主链从不产生。读侧：ws_agent.py:946-950 按节点名读输出、model_errors.py:95 与 merge_node.py:56/92 从 `component_diagnostics` 取 `_gen_diag` 后缀键（该通用映射**活跃**，不可删）。
- **execution_plan_*/plan_* 字段（graph_state.py:35-54）**：全部活跃（plan 层节点、graph._planned_node、ws_agent.py:1109-1130/1684-1686），**不可删**。
- **只写不读（低风险候选）**：`spatial_invariants`/`wall_bounding_box`（graph_state.py:106-107）主链仅 approved_plan_assembler 写（approved_plan_assembler_node.py:86-95），活跃读者只有已死的 base gen 节点；`complexity_profile`（graph_state.py:66）仅 architecture_node 写（architecture_node.py:202/215），全 app 无 `state.get("complexity_profile")` 读取。
- **死字段**：`floor_plan_design_diag`（graph_state.py:68）写读都在死节点路径（floor_plan_design_node.py:218；ws_agent.py:1200-1202）。
- `suggested_components`：主链 assembler 恒写 `[]`（approved_plan_assembler_node.py:96），但 ws_agent.py:937/1748 仍按“骨架建议”展示日志；前端仅在 agent.ts:459 有可选类型引用。`component_fragments`/`component_diagnostics`/各活跃 `*_diag` 保留。
- 无名为 `diagnostics` 的字段；graph_state.py:5 注释所指即 `*_diag` 族 + `component_diagnostics`（后者活跃）。

## 4. 建议清理清单

**低风险（可直接删，无运行/测试依赖）**
1. `nodes/door_node.py ~ chimney_node.py` 共 11 个单组件模块：均 `import create_component_node`（该工厂早已不存在，base_component_node.py 只有 create_component_generator/validator）→ 一旦被 import 即 ImportError；全仓（app/tests/web）零引用，graph 与 nodes/__init__ 均不导入。docs-dev/docs/LangGraph规划/10-设计评审.md:165 已点名。无涉及测试。删除即可。
2. graph.py:18-19、531-538 中“旧 gen→val 兼容链仍为兼容路径”的注释/编译日志与事实不符（主链从不派发），建议改为明确“仅旧 checkpoint/测试保留”，防误导后续维护（只改注释）。
3. 上述只写不读状态字段（spatial_invariants、wall_bounding_box、complexity_profile）可标记移除或补写注释说明“仅 ws 展示预留”后再评估（涉及 graph_state 声明 + 写点注释；测试无引用，**待确认**前端是否有隐藏消费——目前 wild-web 无引用）。

**中风险（需图+ws+测试联动，删除前待确认）**
4. `floor_plan_design` 图节点（graph.py:307、路径表 414、条件边 429-433）+ execution_plan_node.py:487-490 分支 + ws_agent.py:633/780/880/1200-1202 + graph_state.py:68。图侧删除后这些 ws 分支变死代码应同步清理；风险点是**旧 checkpoint 恢复**：若存储的会话 next=floor_plan_design，新图无此节点会恢复失败，需先盘点 `storage/sessions/*.sqlite3` 存量。直接相关测试无（test_agent_graph_execution.py:106 的 patch 是空挂），可安全随删。
5. 22 个 gen/val 节点注册循环（graph.py:320-337、495-497）、`_dispatch_components` Send 分支、graph.py:113 的 resolve_component_suggestions 调用、graph.py:47/69 旧骨架 import/别名。删除收益最大但风险也最大：注册表 implemented=True 全量保留、ws_agent.py:775-788 节点名集合、`component_registry.output_key`、逐组件 diag 声明和若干直接单元测试（test_component_validation_recheck、test_component_state_reducer、test_model_errors）都与之纠缠，且旧 checkpoint 的 pending Send 任务依赖同名节点与 val→merge 边。**建议做配置开关先观测**，勿直接物理删除（列“待确认/高风险”）。

**待确认（不可武断删）**
6. legacy 分片字段与逐组件 diag 状态声明：被 merge/callback/validator 的“旧 checkpoint 读兜底”和上述测试消费；删除即放弃旧会话无损恢复，需 DB/版本门禁一起决策。
7. `skeleton_node.py` 整模块：主链已弃，但 `tests/repair/test_skeleton_blueprint_recovery.py`（直接跑旧 LLM skeleton_generator 与 _recover_blueprint_json）、`tests/blueprint/test_blueprint_text_extraction.py:9-12`（_parse_components_from_reply/_parse_design_brief）仍引用；删除须先迁移用例或保留工具函数。
8. `validators/reasoning_validator.py`：**确认未接入主链**——运行时仅 validators/__init__.py:13 再导出，无 app 代码 import；引用方只有 tests/validators/test_p1_p2_implementation.py:153-294 与 examples/P0 文档。同类的 structure/tool validator 亦仅测试引用；factual_validator 已接入 agent_service.py:475-518（保留）。可在测试同步后整体归档。
9. 提醒（勿删）：web_research_node 是 plan 层活动节点，且 tests/agent/test_web_research_gate.py 直接覆盖；callback/merge/validate/execution_plan_* 全部在主链或 plan 层活跃并有 tests/repair、tests/agent/test_execution_plan.py 等覆盖。

## 5. 明显错误与不一致（文件:行）

1. graph.py:414（及 429-433）：plan_executor 路径表与条件边保留 `floor_plan_design` 目标，但 execution_plan.py 能力表无该 type，executor 判定“未注册能力”会直接失败（execution_plan_node.py:418-426）——该映射不可达，属残留。
2. door_node.py:7 ~ chimney_node.py（11 文件）：import 不存在的 `create_component_node`（base_component_node 已拆成 generator/validator 工厂）——文件既死且坏。
3. 命名分歧：`app.agent.graph.skeleton_generator`=确定性装配器（graph.py:70）而 `app.agent.nodes.skeleton_generator`=旧 LLM 实现（nodes/__init__.py:17）；测试调用的旧 LLM 版（repair/test_skeleton_blueprint_recovery）与实际主链行为完全不同，建议显式改名（nodes 侧改名 legacy_ 前缀）以消除语义割裂。
4. ws_agent.py:780/1200-1202/633/880：floor_plan_design 的节点集合项、事件名与诊断分支在主图不可达 → 死 UI 路径，与图清理须同步。
5. graph.py:18-19 与 531-538 日志：宣称组件 gen→val 链“仍为兼容路径”，与“前端默认 plan_mode、主链永不派发 Send”的实况矛盾，易造成误判。
6. ws_agent.py:937/1748：仍按旧骨架语义展示“建议组件”，但主链 assembler 恒写空列表（approved_plan_assembler_node.py:96），日志/展示失真。
7. graph_state.py:108 注释“骨架节点建议的组件列表”与现状不符（建议列表已无来源），同 6。
8. 全局只读扫描未发现“条件边返回了映射表中不存在的节点名”或“_planned_node 与 async/非 async 节点签名不匹配”（graph.py:73-85 对 awaitable 与非 awaitable 均有处理）；merge 条件边的映射键同时含 `__end__` 与 `END`（graph.py:508）合法但冗余。

（本报告仅基于静态代码与 grep 交叉核对，未执行图运行时探针；所有“待确认”项建议在改动前以 `tests/misc/show_langgraph_graph.py` + 存量 checkpoint 清单复核。）
