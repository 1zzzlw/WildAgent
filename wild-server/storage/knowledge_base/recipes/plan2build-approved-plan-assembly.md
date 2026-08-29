---
knowledge_layer: constraint
entity_type: assembly
entity_name: plan2build_approved_plan_assembly
topic: assembly
status: supported
authority: engine
source: recipes/plan2build-approved-plan-assembly.md
primary_terms:
  - Plan2Build
  - FloorPlanIR
  - ApprovedPlanAssembler
  - Decor IR
  - GateReport
  - StylePackage
synonyms:
  - 已确认平面装配
  - 建筑分阶段生成
  - 风格包装配
---

# Plan2Build 已确认平面与风格装配配方

## Plan2Build 分阶段生成顺序

<!-- rag-meta
entity_name: plan2build_generation_sequence
topic: assembly
primary_terms:
  - Plan2Build
  - FloorPlanIR
  - ApprovedPlanAssembler
  - Decor IR
synonyms:
  - 已确认平面装配
  - 建筑分阶段生成
-->

当前新建筑生成必须按以下顺序执行：总体方案生成 FloorPlanIR，程序从同一 FloorPlanIR 绘制 SVG，用户确认平面后由 `ApprovedPlanAssembler` 装配主体，G1-G6 全部通过后等待用户确认风格，最后由 `StylePackage` 生成 Decor IR、执行装饰装配和 G7。最终 Blueprint 仍需通过完整校验才能保存。

平面审核前不能生成、发送、保存或加载中间 Blueprint。相同的已确认 FloorPlanIR、材质方案和风格包必须得到相同坐标、稳定 ID 和相同组合关系。

## ApprovedPlanAssembler 主体装配合同

<!-- rag-meta
entity_name: approved_plan_assembler_contract
topic: assembly
primary_terms:
  - ApprovedPlanAssembler
  - opening_slots
  - parentWall
  - roof_slots
synonyms:
  - 已确认方案装配器
  - 主体装配器
-->

`ApprovedPlanAssembler` 只消费已经通过人工确认的建筑方案和 FloorPlanIR。它确定性生成墙、楼板、楼梯、电梯井道墙、门、窗和屋顶：立面轴网先提供候选 `opening_slots`，程序按 `component_quota` 跨楼层均匀选择，并优先保留平面内门和阳台入口；只有选中项才成为已批准槽位。门窗必须来自这个批准子集，并写入真实 `parentWall` 与父墙局部 `from`；屋顶必须位于最高承托墙顶并覆盖对应顶层占用范围。

示意高层把 `floors` 作为语义总层数，把 `modeled_floors` 作为真实展开的代表层数。立面洞口沿建筑全高均匀落在代表层，竖向交通可由楼梯模板和逐层 `instances` 表达；不能给连续通高外壳复制每个语义层的全部窗洞。通高无洞口墙的表面细分还必须服从 Core 顶点预算，避免固定采样密度随墙高平方级放大网格。

L 形、U 形、多矩形组合轮廓和中庭顶层不能用外包矩形屋顶填平凹口或洞口。存在多个顶层占用区域或楼板 void 时，屋顶按实际矩形单元分段生成。程序可以使用逻辑完整墙加门窗组件表达洞口，不能为了让模型摆放门窗而随机切碎墙段。

新建筑主体装配完成后禁止再次派发自由门、窗和屋顶模型节点改写坐标。大模型额度耗尽属于模型服务问题，不能被当成建筑几何修复任务。

## G1-G6 主体质量闸门

<!-- rag-meta
entity_name: plan2build_body_gates
topic: constraints
primary_terms:
  - GateReport
  - G1
  - G2
  - G3
  - G4
  - G5
  - G6
synonyms:
  - 主体质量闸门
  - 建筑装配门禁
-->

G1 检查 FloorPlanIR 的空间、墙、洞口、连通性和已启用工程预审规则；G2 检查主体是否有墙、有楼板且 ID 唯一；G3 检查每个批准门窗槽位是否落实为宿主墙范围内的组件；G4 检查多层建筑的楼梯或电梯竖向连续性，并同时识别显式楼梯与 `templates + instances` 标准层楼梯；G5 检查屋顶承托标高与覆盖；G6 检查父墙、父楼板、父屋顶和材质引用是否闭合。

闸门统一返回 `GateReport`，问题使用稳定错误码、相关实体 ID、严重程度和可修复标记。任一 error 未解决时不得进入风格确认。闸门只报告问题，不调用大模型，也不在检查过程中偷偷修改 Blueprint。

## StylePackage 与 Decor IR 装配合同

<!-- rag-meta
entity_name: style_package_decor_ir_contract
topic: assembly
primary_terms:
  - StylePackage
  - Decor IR
  - set_roof
  - sweep
  - anchor
  - array
  - set_material
synonyms:
  - 风格包
  - 装饰中间表示
  - 参数化装饰装配
-->

当前风格必须来自受控 `StylePackage`，不能由模型自由发明 WILD 字段。支持的 Decor IR 操作为：`set_roof` 修改已有屋顶的受控外观参数，`sweep` 沿屋顶路径生成 `cornice`，`anchor` 把 `canopy` 锚定到主入口真实父墙，`array` 按稳定顺序放置支持的 `column`，`set_material` 修改受控材质色板。

现代简约、新中式和欧式古典风格包只能使用当前 Schema 支持的 `roofType`、`column.style`、组合组件和材质字段。新增风格必须先验证数值范围、构件宿主、Schema 和编译器支持，不能只增加形容词或 Prompt。

## G7 风格与装饰闸门

<!-- rag-meta
entity_name: plan2build_style_gate
topic: constraints
primary_terms:
  - G7
  - StylePackage
  - Decor IR
  - parentRoof
  - parentWall
synonyms:
  - 风格装饰门禁
  - 装饰闭环校验
-->

G7 检查已确认风格包的屋顶类型是否实际应用、装饰构件 ID 是否唯一、`parentWall`/`parentRoof` 和材质引用是否存在，并重新执行屋顶承托与引用闭环检查。带 `parentRoof` 的檐口路径必须是以屋顶中心为原点的局部坐标且位于 `span/depth` 范围内；当前 `chinese_curved` 檐口使用不带 `parentRoof` 的世界路径。G7 未通过时不能合并和保存；修复装饰后必须重跑 G7 和最终全量校验。

风格确认只决定受控外观参数，不能越权改变用户已经确认的空间、墙线、楼层数量、门窗宿主或竖向交通关系。

## Plan2Build 失败与降级方式

<!-- rag-meta
entity_name: plan2build_failure_fallback
topic: fallback
primary_terms:
  - deterministic_template
  - ApprovedPlanAssembler
  - StylePackage
  - final_validate
synonyms:
  - 确定性基础方案
  - 生成失败降级
-->

平面模型无法返回可验证结果时，系统生成可审核的 `deterministic_template`，但仍需用户第一次确认。材质模型失败时使用受控材质角色。主体或装饰闸门失败时流程有限终止并报告具体 GateIssue，不能进入无限回调。最终全量校验失败时禁止保存或加载 `.wild`。

当前不把生成中的 Blueprint 动态加载到三维画布；节点只展示公开执行说明，最终零错误 Blueprint 才一次性加载。该限制避免半成品覆盖正式场景和异步重建乱序。
