# architecture：模型做设计，程序推导参数

本轮仅收敛 architecture 及其使用的设计契约、解析入口；没有修改 plan、图路由、预算、知识库或模型配置。沿用现有 DesignDocument，后续仍接收既有格式的图纸标记。

## 现在的填写责任

| 模型填写 | 程序推导 |
|---|---|
| 体量的位置、宽深、楼层和层高 | 总体包络；完整建模时的 modeled_floors |
| 同一开间的 ground / upper 布局 | bays、ground_pattern、upper_pattern |
| 房间、门洞、通路、楼梯形式/方向/占地 | 引用解析与空间检查；存在设计矛盾仍退回修订 |
| 等高分跑的跑数与步高上限，或明确的每跑级数 | 楼面高差、每跑级数、实际步高、楼梯高度 |
| 等高楼梯 placement.center_xz | 根据连接楼面计算中心 Y |

显式填写的总体尺寸控制继续保留；与体量矛盾时失败，不扩大上限。旧楼梯数据的显式数值不自动改写；新计算结果与已有显式值冲突时仍拒绝。

## 新输入示例

立面把同一开间的两层信息放在一起，不再分别填写数量和两组数组：

```json
{"front":{"layout":[{"ground":"window","upper":"window"},{"ground":"door","upper":"empty"}]}}
```

程序将其转换为现有文档中的 bays=2 和对应的两组数组。其他立面同理，逐体量覆盖也支持该表达。

等高楼梯的设计输入可写：

```json
{
  "id":"stair_main", "type":"stair", "host":"main",
  "floor_connections":[{"from_floor":1,"to_floor":2}],
  "placement":{"center_xz":[6,5]},
  "size":{"width":3,"depth":4},
  "form":{"shape":"U","span_direction":"+z","flight_width":1.2,"landing_depth":1.2},
  "step_design":{"flights":2,"max_riser_height":0.2}
}
```

若楼面是 0 和 3.2 米，解析结果得到 height=3.2、每跑 8 级、实际步高 0.2、中心 Y=1.6。若楼面是 0.36 和 3.78 米，中心 Y 为 2.07。

`step_design` 表示已经选择等高分跑；`max_riser_height` 是本次设计条件，不是规范引用。程序选满足上限的最少整级数。若明确指定每跑级数，则改用 `steps_per_flight`，二者不能同时填写。非等高、特殊楼梯保留原有设计表达，本轮不自动计算其踏步分配。

## 删除与保留

- 删除 architecture 的固定多路检索、错误修订时的追加检索，粒度只取代码中的 DETAIL_LEVEL_GUIDANCE。
- architecture 提示词不再注入构件资料目录、WILD 实现字段和设计程序源码协议；明确独立输入与计算结果的分工。
- validate 删除重复的必填字段枚举；先构造统一契约，再做派生计算、引用和空间检查。错误翻译只输出字段路径与契约原因。
- 保留真正的设计冲突检查、局部补丁修订及原有尝试上限，不删除要求、不移动通路来制造通过。

## 验证结果

27 项本地回归通过，其中新增 13 项覆盖新图纸输入、不同体量起点与层高、显式约束保留、踏步推导、文档往返、局部修订和既有 plan 入口兼容。模型接口使用桩验证调用边界，不等于真实模型成功率。

[历史参数回放](architecture职责收敛证据/05-回放摘要.json)重现旧 trace 的 6.4 米踏步总高错误，再以新设计输入得到 3.2 米高差、每跑 8 级，无新增模型调用。立面设计取自历史最终稿，不宣称原始首稿因此整体一次通过。

[真实单节点试跑](architecture职责收敛证据/06-试跑摘要.json)发起 3 次实际模型请求，零知识检索；仍因字段取值和通路/门墙关系未解决而失败。该轮没有报立面数组长度或楼梯乘法错误，但不能据此认定整体生成已稳定。没有运行材质、构件生成、完整 WILD 交付或渲染。

读取入口：`architecture/workflow.py::architecture_planner` 的 validate；`resolver.py::prepare_architecture_plan`；`coordinates.py::resolve_stair_steps`；`prompts/planning.py::build_architecture_plan_prompt`。

修改前副本、独立差异、源码指纹、原始模型记录和测试命令均保存在本目录的 `architecture职责收敛证据/`；[最终核对](architecture职责收敛证据/09-最终核对.json)以本轮修改前副本为基准，不把已有未提交工作算成本轮改动。
