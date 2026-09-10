# 平面分析多步 Plan 模式设计

> 目标：把"生成建筑模型"改为两个明确阶段。阶段1（平面分析）做成多步骤 plan 模式，
> 用 SVG 展示平面图供用户提前审核修改，强制规范，并把完整信息传递给阶段2（蓝图生成）。

## 1. 现状与差距

当前流程已接近两阶段：
- 阶段1：`architecture → floor_plan_design（单次LLM调用）→ floor_plan_review（用户确认）`
- 阶段2：`material_plan → skeleton（ApprovedPlanAssembler确定性装配）→ 组件 → merge → final_validate`

差距：`floor_plan_design` 单次 LLM 调用一次生成整个 FloorPlanIR，不精细、不可分步审阅。

## 2. 目标架构

阶段1 拆为 4 个独立 LangGraph 节点：

```
architecture
  → floor_space_analysis  (空间需求分析：建筑类型→功能分区清单)
  → floor_layout          (空间布局：在体量内分配空间位置/多边形)
  → floor_openings        (门窗与流线：内墙、门、窗、垂直交通)
  → floor_validate        (完整校验 + SVG 审核图)
  → floor_plan_review     (用户确认/修改)
  → material_plan         (阶段2入口，消费完整 floor_plan)
```

### 状态传递
- 新增 `floor_analysis_result`、`floor_layout_result`、`floor_openings_result` 中间字段。
- 第 4 步综合前三步产出完整 FloorPlanIR，最终 `floor_plan` 与现有协议一致。

### 快速/Plan 双模式
- Plan 模式：plan_executor 按 ExecutionPlan 的 4 个子 step 依次调度。
- 快速模式：图内 architecture → 4节点串联 → floor_plan_review。

## 3. 改动清单
1. graph_state.py：新增中间字段。
2. 4 个新节点文件。
3. prompts.py：新增分步 Prompt。
4. execution_plan.py：注册 capability + steps。
5. execution_plan_node.py：complete_execution_step 映射。
6. graph.py：节点注册 + 接线。
