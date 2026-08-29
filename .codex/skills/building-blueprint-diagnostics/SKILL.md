---
name: building-blueprint-diagnostics
description: Diagnose architectural Blueprint and rendering defects from a .wild JSON file, approved design/material plans, model reasoning, screenshots, or reconstruction diagnostics. Use for gaps between roofs and walls, floating or intersecting components, wrong levels, invalid local coordinates, missing hosts, unsupported structural output, and for converting repeated building defects into shared validators, deterministic repairs, prompts, regression fixtures, or compact rules instead of per-building hardcoded patches.
---

# 建筑 Blueprint 诊断

把建筑问题当作可复现的几何关系问题处理。输入可以只有 Blueprint，也可以附带批准方案、材质方案、模型思考过程、截图、服务端日志或重建报告。输出必须区分“证据确认的问题”和“尚需运行验证的假设”。

## 工作流

1. **收集事实**
   - 读取 Blueprint 的 `meta`、`geometry.elements`、`geometry.components`、`materials`、`assets`。
   - 对照批准的建筑方案、材质方案和结构骨架约束；批准内容优先于模型自由发挥。
   - 记录截图只证明视觉结果，不把截图中的尺寸当作事实；从 JSON 计算包围盒、标高、方向、父子引用和覆盖关系。
   - 在 WildAgent 中优先查看 `sceneValidator`、`spatial_tools`、`architecture_plan`、`merge_node`、`wildCoreAdapter`、`reconstructionDiagnostics` 及相关测试。

2. **按通性检查，不先写特判**
   - **结构契约**：骨架阶段只能包含批准允许的基础类型；后续组件不能被错误地提前写入骨架。
   - **坐标契约**：墙的 `from/to` 是三维端点，竖向范围由 Y 表示；门窗 `from[0]` 是父墙局部沿线距离，`from[2]` 通常为局部法向偏移；楼板 `from/to` 必须是同 Y 的三维数组。
   - **标高连续性**：上层墙底、下层墙顶、楼板支承面和屋顶 `position.y` 必须落在同一承托关系上；允许退台，但退台必须生成可解释的露台/楼板。
   - **宿主关系**：门窗、阳台、檐口、雨棚等必须引用真实父墙；屋顶必须覆盖实际最高承托墙体，而不是只覆盖固定尺寸或模型猜测的中心。
   - **包围盒关系**：计算墙体、楼板、屋顶及组合构件的世界包围盒，检查覆盖、间隙、过度悬挑、穿插和分离。对坡屋顶/曲屋顶，不能只比较平面 X/Z，还要比较屋面在檐口、山墙和脊线处的 Y 范围。
   - **FloorPlanIR v2 契约**：新建筑先检查已批准平面的 `envelope_regions`、多边形空间、直/曲墙、`vertical_spaces`、`vertical_circulation` 和 `review_rules`。L/U 轮廓必须按矩形并集判断；中庭/井道所在标高不得仍有楼板覆盖；曲墙洞口的 `from[0]` 按路径弧长而不是端点弦长计算。快速与精密模式都必须在用户确认后才进入三维。
   - **生成顺序**：确认 `architecture -> floor_plan_design -> floor_plan_review -> approved_plan_assembler -> G1-G6 -> style_review -> decor_assembly -> G7 -> merge -> final_validate -> delivery` 中每一层的职责没有越界；审核前只允许输出由 FloorPlanIR 绘制的 SVG，不能生成、发送或保存中间 Blueprint。
   - **Plan2Build 闸门**：主体问题优先定位到 G1 平面、G2 主体、G3 洞口宿主、G4 竖向交通、G5 屋顶承托、G6 引用闭环；风格/装饰问题定位到 G7。修复后必须重跑对应 GateReport 和最终全量校验。
   - **模板实例**：检查 G4 或统计构件时，同时解析 `geometry.templates` 与 `geometry.instances`；不能因为楼梯不在 `geometry.elements` 就判定示意高层没有竖向交通。
   - **屋面依附坐标**：带 `parentRoof` 的檐口 `path` 是屋顶中心局部坐标。先区分 local/world，再判断 `span/depth`；不要把世界坐标直接与局部半宽、半深比较。对编译器不支持局部依附的曲面屋顶，使用受控世界路径且省略 `parentRoof`。
   - **渲染与语义分离**：若 Blueprint 关系正确但画面错误，检查 `wild-core` 几何生成、transform、材质/法线和 renderer；不要为了视觉补丁修改 Blueprint 中心线。

3. **归类根因**
   使用一个主类别，必要时附加次类别：
   - `schema_contract`：字段、类型、阶段输出越界。
   - `coordinate_frame`：世界坐标/父墙局部坐标混用，方向或法向错误。
   - `level_continuity`：墙、板、柱、梁、屋顶承托标高不连续。
   - `host_relation`：父对象缺失、错误或宿主范围不匹配。
   - `coverage_geometry`：屋顶/楼板/阳台覆盖不足、悬空或穿插。
   - `compiler_geometry`：组合构件展开后几何不成立。
   - `core_geometry`：确定性几何原语或 mesh transform 错误。
   - `renderer_only`：网格已正确但 Three.js 显示、材质或取景错误。
   - `model_instruction`：模型违反已批准规则，但程序缺少可判定门禁。

4. **选择最小修复层级**
   按以下优先级决策：
   - 能由几何关系确定的，加入共享 validator/fix 工具；例如屋顶支承墙包围盒、屋顶标高、墙顶覆盖、槽位吸附。
   - 能在生成前阻止的，修正 architecture/skeleton/component Prompt 或结构预检。
   - 只有需要用户取舍的内容才生成 `ScenePatch` proposal；不得让 Agent 直接覆盖 Blueprint。
   - 只有确认 Blueprint 正确而渲染错误时，才改 `wild-core`/compiler/renderer。
   - 不为单个建筑 ID、单组坐标或截图建立永久 if/else。若必须临时兼容，先写成带明确条件、误差和回归测试的通用规则，并记录为何不是特判。

5. **输出诊断报告**
   使用以下结构，缺证据时明确标记：

   ```text
   结论：一句话描述最可能的通性根因
   证据：实体 ID、字段、计算出的数值/包围盒、对应源码入口
   影响：视觉、结构语义、后续组件生成或保存门禁
   分类：上述根因类别
   修复层级：validator / deterministic fix / prompt / compiler / core / renderer
   建议：最小改动与需要补充的测试
   未确认：需要运行构建、重建或浏览器验收的部分
   ```

## 屋顶与墙体间隙的专门判断

看到“屋顶和墙之间有空隙”时，按顺序判断：

1. 找最高承托墙体的顶标高 `wall_top_y`，以及屋顶的 `position.y`（支承标高）和实际网格最低 Y。
2. 对 `gable/hip/chinese_curved/chinese_pagoda`，分别计算檐口、坡面、山墙/端面的实际最低高度；不能用 `position.y + height` 代替所有位置。
3. 检查屋顶的 X/Z 覆盖是否包含承托墙体，并考虑墙厚、屋檐外挑和允许误差。
4. 若屋顶网格的檐口最低 Y 高于墙顶，属于 `coverage_geometry` 或 `core_geometry`；若墙顶低于已批准体量应有的层高，属于 `level_continuity`；若屋顶只生成了结构骨架禁止的类型，属于 `schema_contract`。
5. 对中国曲面屋顶，重点检查 `buildChineseCurved` 的曲线端部、`position.y` 语义、墙顶是否需要山墙填充。不要把“增加屋顶高度”作为默认修复；这可能扩大间隙。
6. 输出修复建议时区分：调整 Blueprint 屋顶承托参数、补充通用屋顶-墙体覆盖校验、修改 Core 封边/山墙几何、或补充批准方案中的体量定义。先选择能覆盖同类屋顶的规则。

## 复杂度控制与知识积累

每修复一个案例，只允许新增以下一种长期资产：

- 一个可命名的通用不变量/校验规则；
- 一个确定性修复函数；
- 一个 Prompt/协议约束；
- 一个最小回归样本或参数化测试；
- 一条参考知识规则。

优先参数化测试和共享工具，避免复制整栋建筑 Blueprint。新规则必须说明适用范围、容差、不能处理的情况和回归样本。重复出现的根因应合并到已有校验器，而不是继续增加节点或模型调用。

## 与仓库边界保持一致

- `.wild` Blueprint 是事实源；批准方案和材质方案是生成约束，不是可被模型随意改写的建议。
- 已确认 FloorPlanIR 是主体装配事实源；`ApprovedPlanAssembler` 可一次性生成 `wall/floor/column/beam/stair/roof` 与有真实宿主的 `door/window`。风格装饰只能来自已确认 `StylePackage -> Decor IR`，不能由并行模型重新猜坐标。
- Agent 只提出 Blueprint 或 ScenePatch；不生成 Three.js 代码。
- 最终校验失败时禁止保存或自动加载；修复后必须重新运行同一校验器。
- 诊断不等于自动修复。未经用户确认的增量改动必须保持为 proposal。

## 参考资料

- 通用规则和输出字段：读取 [references/diagnostic-rules.md](references/diagnostic-rules.md)。
- 仓库当前实现入口：`docs/ARCHITECTURE.md`、`docs/AGENT_AND_CHAT.md`、`docs/DEVELOPMENT.md`，以及上述源码入口。
