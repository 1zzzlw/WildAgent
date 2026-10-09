---
entity_name: architecture_design_expression
topic: composition
status: supported
authority: maintainer
primary_terms:
  - 建筑设计表达
  - 设计意图
  - 体量立面屋面
synonyms: []
---

# 建筑方案的设计表达与当前边界

本条回答 architecture 在当前设计链能表达什么，不提供某类建筑的固定设计。依据为 app/design/contracts.py、app/design/resolver.py、app/agent/compiler/compile.py 与 architecture 的设计块协议。用户提供的《WILD 蓝图设计语言 v2.0》中的“先设计再书写、尺寸推导、依附联动”按当前实现转写；其字段与数值不直接视为引擎事实。

## 整体设计意图与参数表达

DesignDocument.decisions.design_intent 保存 goals、assumptions、spatial_strategy、composition、material_strategy 与 selected_systems。它们说明空间、形态和材料的设计方向，不生成网格，也不证明功能、荷载或法规合规。design_rationale 记录实际方案的选择依据与表达限制，保留给图纸审核、材质和执行计划使用。概念、风格与构件数量不能代替这些关系；几何有效也不能证明建筑审美成立。

## 体量、楼层与交通

massing 与 volumes 表达整体尺寸、逐层体量范围和主次关系；体量起点为世界平面 x/z，可整体平移，不强制西南角原点或固定模数。structural_grid 表达结构系统及开间数；circulation.vertical_strategy 表达 none、stair 或 core_and_stair。多层交通由下游求解，贯通构件需位于经过各层的共同轮廓内。当前方案没有房间坐标、室内功能分区或逐层平面布置字段；空间使用描述属于待核对的设计意图，不能把楼梯策略等同于完整室内设计。

## 立面与开口

facades 的 front/back/left/right 是最小/最大 Z 和最小/最大 X，不自动代表地理南北。每面 bays 对应同长度的 ground_pattern 与 upper_pattern；入口索引 entrance_bay 从 1 开始。door/window 表示开口，empty 为实墙无洞，open 为开敞无墙且当前只能整面使用。首层使用 ground，建模上层重复 upper；当前上层不支持 door，也没有逐层不同 pattern 通道。门窗尺寸与位置由槽位解算，设计需要的采光或交通仍要结合实际图纸判断，不能从开口数量推断已满足。

## 屋面与附属件

roof 是整体模板对象，可选 flat、gable、hip、dome、chinese_curved、chinese_pagoda；可用 roof.volumes 按已声明体量选择屋型和出檐。ridge_axis 只控制 gable。当前多体量分段仅支持 flat/gable/hip，上层部分覆盖下层的剩余局部屋面不保证表达。引擎支持 cornice 不等于设计链对所有屋型都能派生它：cornice/chimney 的自动模板当前只覆盖 flat/gable/hip。选择其它屋型时不要承诺此类附件已落地，需保留表达缺口或修订未批准设计。

## 实例宿主与材料

components 可记录实例 id、type、host、size、form、material_role。墙宿主用体量、立面和楼层组成的设计引用；屋面宿主可用体量 id，由编译器解析实际元素。关系柱可声明 relation.kind=supports 并引用雨棚实例，不能用柱数量替代支撑关系。materials.regions 表达材质角色与实体类型绑定；材质节点落实整体材料方向，缺少图片资产时仍可用真实参数材质。宿主或目标未解析时保留缺口，不能编造对象或改变设计意图来掩盖。
