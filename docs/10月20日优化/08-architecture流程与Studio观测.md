# architecture 当前流程与 Studio 观察

> 已回退：本文所述 architecture 专用调试图和断点已撤销，当前 Studio 入口恢复原项目图。本文保留为实验历史，见[回退记录](10-代码回退记录.md)。

入口仍是 [architecture_planner](../../wild-server/app/agent/generation/architecture/workflow.py)。节点内最多三次模型调用，计算也计入，没有新增图节点。

1. 从 State 读取用户需求、粒度、类型、风格与当前思考开关，构建设计提示词。字段约束来自实际 Pydantic 类型生成的工具 Schema，不检索 WILD 规则。
2. 多层方案先调用 calculate_stair，程序返回楼梯占地尺寸和相对出口。模型据此确定位置，再布置相邻房间与墙。
3. 调用 inspect_design 提交完整图纸；程序补齐确定性默认值，检查整图并计算楼梯、洞口、楼板等。
4. 有错误则调用 revise_design，仅修改指定路径；程序装配完整候选并再次检查。未改动字段原样保留。通过后直接返回，不要求模型再复述整稿。

每轮使用当前实际图纸、最近检查和楼梯计算结果作为上下文；各轮遵守同一个 thinking_mode。首稿也可直接返回 JSON，由程序使用相同检查入口处理。达到三次调用后仍失败会保留候选与原因，不能把它作为合格图纸交付。

## Studio 入口

[studio_graph.py](../../wild-server/langsmith_tools/studio_graph.py) 仍为 classifier → architecture → END，断点为 interrupt_after=["architecture"]。图纸先写入 State 再暂停；继续也不会进入下游节点。

在 wild-server 目录运行：

    uv run langgraph dev --config langsmith_tools/langgraph.json

选择 wildagent，新建线程，使用 [输入示例](../../wild-server/langsmith_tools/studio-input.example.json)。本次协议改为 design-facts/2，不复用旧图纸线程。

| 看什么 | State 位置 |
| --- | --- |
| 最终接受图纸 | design_document |
| 程序展开结果 | resolved_design |
| 全部原始调用 | architecture_diag.rounds 中的 tool_calls / output |
| 每次提交或修订后完整候选 | architecture_diag.rounds[i].candidate |
| 每次检查、ID 修订路径、默认值与派生数据 | architecture_diag.rounds[i].inspection |
| 工具实际返回 | architecture_diag.rounds[i].tool_results |
| 当前保留候选与检查 | architecture_diag.last_candidate / last_inspection |
| 固定提示词 | architecture_diag.prompt |
| 三个工具的实际 Schema | architecture_diag.tool_schemas |
| 调用量与停止原因 | model_calls / token_usage / last_issue |

第一轮可能只有 calculate_stair，没有图纸。寻找名字为 inspect_design 的工具调用，其 args.design 才是首次完整提交；寻找 revise_design 的 args.changes 查看模型改动意图，再对照该轮 candidate。

本轮经用户授权运行离线回归及当前配置模型，记录见 [实际测试证据](architecture最后修复/README.md)。测试脚本直接调用相同 architecture_planner，没有覆盖 Studio 浏览器断点操作或后续编译渲染。
