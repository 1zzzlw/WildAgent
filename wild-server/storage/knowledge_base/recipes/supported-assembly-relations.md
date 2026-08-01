---
doc_type: recipe
doc_scope: generation
knowledge_layer: constraint
entity_type: assembly
entity_name: supported_assembly_relations
topic: assembly
wild_version: "1.1"
status: supported
authority: engine
source: wild-web/src/wild-core/src/primitive/resolver.ts
keywords:
  - 构件组合
  - assembly relation
  - resolver
  - wall opening
  - column beam
---

# WILD v1.1 已实现的构件组合关系

> 依据：当前 `resolver.ts` 与 `expander.ts`。本文只记录可以由引擎实际执行的关系；建筑设计建议另见建筑类型文档。

## 墙体与开口

<!-- rag-meta
entity_type: opening
entity_name: wall_opening_relation
topic: assembly
status: supported
authority: engine
keywords: wall, opening, parentWall, resolveOpenings, 墙体, 洞口
-->

`opening.parentWall` 必须引用已存在的 `wall.id`。直墙上 `opening.from[0]` 表示洞口左边缘沿墙方向的距离，`from[1]` 是洞口底部世界 Y；弧墙上 `from[0]` 仍按弧长解释，但 `from[1]` 按相对墙底偏移处理。引擎把洞口写入父墙切口并计算覆盖几何位置。

## 墙角闭合

<!-- rag-meta
entity_type: wall
entity_name: wall_joint_relation
topic: assembly
status: supported
authority: engine
keywords: wall joint, resolveWallJoints, 墙角闭合, XZ
-->

两面墙的端点 XZ 距离小于 0.01m 时，`resolveWallJoints` 会把对应端点的 XZ 取平均；Y 值各自保留。输入仍应尽量提供一致端点，不要依赖解析器修正明显错位。

## 柱与梁

<!-- rag-meta
entity_type: structural_component
entity_name: column_beam_relation
topic: assembly
status: supported
authority: engine
keywords: column, beam, resolveBeamSupports, 柱梁吸附
-->

梁端在 XZ 平面接近柱顶、且距离小于 `column.bottomRadius + 0.05` 时，`resolveBeamSupports` 会把该梁端的 XYZ 对齐到柱顶。当前逻辑只处理 `beam`，不会处理不存在的 `truss` 类型。

## 墙体、楼板与屋顶补全

<!-- rag-meta
entity_type: building
entity_name: envelope_boundary_completion
topic: assembly
status: supported
authority: engine
keywords: floor, roof, wall, resolveFloorRegions, resolveRoofBoundary, 楼板, 屋顶
-->

- 蓝图完全没有 `floor` 且至少有三面墙时，引擎会按全部墙体 XZ 包围盒补一个厚 0.2m 的矩形楼板；已有任意楼板时不再补全。
- 至少有三面墙时，引擎会按有效高墙扩大 `roof.span`、`roof.depth`，并在 `roof.position` 缺失时将屋顶居中放到最高墙顶。显式位置不会被覆盖。
- 楼板与墙、柱与楼板、楼梯与楼板之间的其他标高关系需要蓝图作者显式给出，引擎不会完成结构设计推导。

## 模板实例与表面排布

<!-- rag-meta
entity_type: assembly
entity_name: template_and_placement_relation
topic: assembly
status: supported
authority: engine
keywords: templates, instances, placements, expandTemplates, expandPlacements, 模板, 排布
-->

`geometry.instances` 可引用 `geometry.templates`，引擎为实例保存 position、rotation、scale 变换并允许材质覆盖。`geometry.placements` 也引用模板，但当前表面查询只支持 `gable` 屋顶的 `left` 和 `right`；墙、楼板、梁以及其他屋顶面的通用排布仍未实现。
