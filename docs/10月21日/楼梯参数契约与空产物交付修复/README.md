# 楼梯参数契约与空产物交付修复

本轮依据用户报告的真实失败修复源码。没有重新生成建筑，也没有运行回归、构建、服务、Embedding 或渲染。已做的检查仅为 Schema 导出、文本 AST/JSON 解析和差异检查；运行效果待用户验证。

## 对应运行

- 会话：`session_1792543699639`。
- 请求：`req_1792560785713_3wneso5nd`，用户需求为“生成一个新中式别墅”。
- 原始会话：[session JSON](../../../wild-server/storage/sessions/session_1792543699639.json)。
- 本次请求的消息、节点诊断、三次模型原始输出及最后候选：[修复前运行证据](修复前运行证据.json)。
- 修改基准：[修改前源码](修改前.zip)。本轮差异以该快照为准，保留此前尚未提交的修改。

本轮只到达 classifier、architecture；`plan_items=0`、`plan_iterations=0`、`fragment_total=0`。因此错误发生在建筑图纸阶段，没有进入 plan、构件实现或渲染。

## 错误经过及原因

1. 首稿在 16 个构件中写入 `structure`、`frame`、`panel` 等材质绑定键，契约要求的是 `material` 或以 `Material` 结尾的真实字段。旧 Schema 只声明了字符串字典，这个限制藏在手写 Python 校验器中，没有体现在模型输入协议。
2. 第一次修订修改了材质键，之后才暴露楼梯的错误。首稿楼梯为 `type="staircase"`，`form={"layout":"U","directions":2}`，平面中心 `[4.5,6.5]`、占地 `4×2.8` 米，连接 1～2 层。程序需要规范形态、第一跑方向、梯宽和平台深度，不能从上述数据唯一推导。
3. 最后一次修订向 placement 加入了 `direction="south"`、`turn_side="left"`，程序并不读取这两个参数，因此仍失败。旧错误只指向 plan_position，泛称“需要完整参数”；同时修订提示已丢失首稿的输入 Schema，使模型继续猜字段。
4. architecture 返回 failed 后，交付函数把空白 current_blueprint 当成可恢复结果，再执行最终校验并保存。这才产生了“0 元素 + 0 组件、12 项通过”的回复。空几何是上游失败后的后续现象，12 项通过不能说明建筑已生成。

这些证据说明本轮系统暴露给模型的协议不完整，不能据此归结为模型能力不足。上一轮删减了重复提示，但也删掉了必要字段语义，未同步补上可计算入口的正式参数契约。

## 本轮修改

- [contracts.py](../../../wild-server/app/design/contracts.py)：增加 `PlanStairForm`，仅约束使用 plan_position 的 U 形双跑输入。必须明确 `shape="U"`、`span_direction`、`flight_width`、`landing_depth`；双跑数由 U 形入口固定为 2，可省略 flights，显式冲突仍拒绝。级数、最大级高、级高和踏步进深仍是可选约束，没有要求模型重算中心 Y、总高或梯段端点。
- 同一契约生成条件 Schema：声明 plan_position 时，展示 form 参数、世界 X/Z 占地 width/depth 及单连接要求；未使用该入口的其他构件继续保留开放 form。材质绑定键用可导出的 pattern 约束，删除原手写检查；字段描述中的坐标含义保留在模型输入中。
- [design_workflow.py](../../../wild-server/app/agent/generation/architecture/design_workflow.py)：修订时投影同一个正式 Schema，只提供允许修订的顶层字段及其引用定义。未增加楼梯错误专项教程、字段别名映射、节点、重试次数或模型调用上限。
- [coordinates.py](../../../wild-server/app/design/coordinates.py)：原始参数入口复用同一个 form 契约，缺项定位到 `/form/<字段>`、`/size/<字段>` 或 `/floor_connections`；无效楼层引用保留原路径与原因，替代笼统的 plan_position 错误。梯宽、平台深度和方向属于设计选择，不从占地中猜值或改写显式选择。
- [agent_delivery.py](../../../wild-server/app/services/agent_delivery.py)：只恢复包含实际元素或组件的产物，空白占位对象返回 None，沿现有 WebSocket 生成失败分支报告上游原因；保存入口再次拒绝空几何，避免作为新产物保存和发布。包含实际构件的失败草稿及失败片段继续保留。
- 正式 [DesignDocument Schema](../../9月9日优化/design-document.schema.json) 已重新导出。本轮模型使用的 [完整输入协议](模型设计输入.schema.json) 和 [仅构件修订协议](构件修订输入.schema.json) 单独归档；上一轮目录中的 Schema 保持其历史版本。

原失败 `.wild` 与会话记录没有被修写或删除。没有自动补齐这张失败图纸，因为缺少的方向、梯宽和平台深度并非唯一可计算的派生量。

## 回归定义与验证边界

[参数回归](../../../wild-server/scripts/ci/test_design_parameter_realization.py) 补充缺项与材质错误同时反馈、U 形省略重复跑数、输入 Schema 与运行流程一致性、其他 form 不受影响、占地/连接错误路径及材质键约束。

[修订反馈回归](../../../wild-server/scripts/ci/test_design_revision_feedback.py) 补充修订消息仍携带相关正式参数协议的检查。

[交付回归](../../../wild-server/scripts/ci/test_agent_delivery.py) 定义空占位对象不可保存、实际失败分片继续保存且维持失败状态的边界。以上回归均未运行。

后续验收应区分：回归是否通过、同一项目模型的完整生成是否成功、渲染是否符合图纸。当前只能确认源码改动、Schema 导出和静态检查完成，不能声明本次图纸已通过或生成成功率已提高。
