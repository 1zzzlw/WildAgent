# 当前设计图纸：DesignFacts / 2

> 已回退：本文记录的 DesignFacts / 2 实验实现已撤销，保留作历史参考。当前代码和备份位置见[回退记录](10-代码回退记录.md)。

本轮只处理设计图纸与 architecture。后续材质、计划、编译节点尚未迁移，不以完整项目能否运行作为本轮结论。

先看三个入口：

| 内容 | 入口 |
| --- | --- |
| 图纸字段 | [facts.py](../../wild-server/app/design/facts.py) 的 DesignFacts |
| 模型怎样交付与修订 | [design_workflow.py](../../wild-server/app/agent/generation/architecture/design_workflow.py) |
| 程序怎样计算与检查 | [resolve_facts.py](../../wild-server/app/design/resolve_facts.py) |

图纸只保存设计输入，不含审核外壳、执行配额或计算结果。

| 字段 | 职责 |
| --- | --- |
| name / units / levels / slab_thickness / site | 名称、尺度、楼面基准与场地 |
| volumes / room_zones / voids | 体量、用途分区和非楼梯挑空 |
| walls / openings / stairs / roofs | 内墙、门窗、楼梯连接与设计尺度、屋面选择 |
| components / material_roles | 附属构件设计与材料意图 |
| routes / use_clearances | 本层通路与本次选择的净距 |
| features_to_verify / scope_limits | 人工待核事项与表达边界 |

所有 rect/site 改为具名边界，例如 {"west":0,"east":12,"south":0,"north":10}。不再接收四数字数组，避免把边界写成“起点＋宽深”。平面点仍为 [X,Z]，Y 向上。

楼梯不再同时输入“预留矩形”和“梯段尺寸”。模型给 origin=[占地西南角X,Z]、起止楼层、梯形、方向和梯宽等设计尺度；程序从层高与步高上限计算级数、占地、平台标高、梯井和出口。用户没有指定级数时省略 steps_each。

名称、单位、缺省的屋顶编号，以及未选择的门窗高度/style，由程序补齐并记录 defaults；明确输入的尺寸不会被裁小。这些默认值是设计约定，不是建筑规范。

模型先用 calculate_stair 取得尺度，再提交一次完整图纸；失败后用 revise_design 修改具体字段，程序保留其余内容。具体交接和检查范围见 [检查工具说明](09-architecture检查工具与修订.md)。

输出分为：design_document（当前通过已覆盖检查的图纸）、resolved_design（确定计算的几何）、architecture_diag（实际提示词、工具、逐轮候选与问题）。通过检查不代表建筑美观、全部房间可达或构造可实现。

本版与之前的数组边界、stairs.rect 输入不兼容，没有旧格式适配器。在 Studio 新建线程。此前的 [汀院转换样例](汀院别墅-新版设计图纸.json) 是旧版历史资料，不能作为本版输入；当前真实调用的输入、原始响应与结果见 [本轮证据](architecture最后修复/README.md)。

未照搬原汀院文件的全部字段：作者脚本中的墙、门窗、屋面和附属构件仍需显式设计；axes 等作者变量不进入通用图纸，楼板分片和半平台不交给模型重复填写。
