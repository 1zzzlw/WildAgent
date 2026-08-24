---
knowledge_layer: constraint
entity_type: assembly
entity_name: supported_assembly_relations
topic: assembly
status: supported
authority: engine
source: wild-web/src/wild-core/src/primitive/resolver.ts
primary_terms:
  - 构件组合
  - assembly relation
  - resolver
  - wall opening
  - column beam
synonyms: []
---

# WILD v1.1 已实现的构件组合关系

> 依据：当前 `resolver.ts`、`wild-compiler/index.ts`、`componentRegistry.ts` 与各组件编译器。本文只记录可以由引擎实际执行的关系；建筑设计建议另见建筑类型文档。

## 组合构件解析顺序

<!-- rag-meta
entity_type: assembly
entity_name: component_reference_order
topic: constraints
status: supported
authority: engine
primary_terms:
  - geometry.components
  - geometry.elements
  - reference order
  - parentWall
  - 引用顺序
synonyms: []
-->

`geometry.components` 编译时会在完整的 `geometry.elements` 数组中查找父元素，因此组件引用不要求父元素在数组中先出现。引用目标仍必须存在、`id` 必须唯一且类型必须匹配；组件之间不能把另一个组件的编译产物当作父元素。把结构元素写在组件之前可以提高人工可读性，但不是当前编译器的执行约束。

## 墙体与开口

<!-- rag-meta
entity_type: opening
entity_name: wall_opening_relation
topic: assembly
status: supported
authority: engine
primary_terms:
  - wall
  - opening
  - parentWall
  - resolveOpenings
  - 墙体
  - 洞口
synonyms: []
-->

`opening.parentWall` 必须引用已存在的 `wall.id`。直墙上 `opening.from[0]` 表示洞口左边缘沿墙方向的距离，`from[1]` 是洞口底部世界 Y；弧墙上 `from[0]` 仍按弧长解释，但 `from[1]` 按相对墙底偏移处理。引擎把洞口写入父墙切口并计算覆盖几何位置。

## 门窗、凸窗与墙挂组件

<!-- rag-meta
entity_type: assembly
entity_name: wall_attached_component_relation
topic: assembly
status: supported
authority: engine
primary_terms:
  - door
  - window
  - bay_window
  - canopy
  - balcony
  - parentWall
  - 墙挂组件
synonyms: []
-->

- `door`、`window` 和 `bay_window` 必须通过 `parentWall` 引用 `wall`，并在父墙上生成开口及附属几何；会形成开口的组件当前只支持直线墙或单段圆弧墙。
- `canopy` 和 `balcony` 也必须引用 `parentWall`，用于确定沿墙方向、安装高度和墙体法向；二者不会把梁柱连接自动推导为真实结构节点。
- 墙挂组件的 `from` 解释为 `[沿父墙距离, 世界 Y, 墙体法向偏移]`。组件宽度必须落在父墙水平范围内；带 `height` 的门、窗和凸窗还必须落在父墙垂直范围内。
- `parentWall` 只能引用原生 `geometry.elements` 中的墙，不能引用另一个组合组件生成的临时元素。

## 墙角闭合

<!-- rag-meta
entity_type: wall
entity_name: wall_joint_relation
topic: assembly
status: supported
authority: engine
primary_terms:
  - wall joint
  - resolveWallJoints
  - 墙角闭合
  - XZ
synonyms: []
-->

两面具有重叠竖向范围的墙，其端点 XZ 距离小于 0.01m 时，`resolveWallJoints` 会把对应端点的 XZ 取平均；Y 值各自保留。若两墙接近直角，引擎还会把每面墙的端部沿自身方向延伸另一面墙厚度的一半，以减小直角墙角缝隙。该逻辑只处理端点相交，不会自动解决 T 形中接或任意交叉墙。

## 柱与梁

<!-- rag-meta
entity_type: structural_component
entity_name: column_beam_relation
topic: assembly
status: supported
authority: engine
primary_terms:
  - column
  - beam
  - resolveBeamSupports
  - 柱梁吸附
synonyms: []
-->

梁端在 XZ 平面接近柱顶、且距离小于 `column.bottomRadius + 0.05` 时，`resolveBeamSupports` 会把该梁端的 XYZ 对齐到柱顶。当前逻辑只处理 `beam`，不会处理不存在的 `truss` 类型。

## 墙体、楼板与屋顶补全

<!-- rag-meta
entity_type: building
entity_name: envelope_boundary_completion
topic: assembly
status: supported
authority: engine
primary_terms:
  - floor
  - roof
  - wall
  - resolveFloorRegions
  - resolveRoofBoundary
  - 楼板
  - 屋顶
synonyms: []
-->

- 蓝图完全没有 `floor` 且至少有三面墙时，引擎会按全部墙体 XZ 包围盒补一个厚 0.2m 的矩形楼板；已有任意楼板时不再补全。
- 至少有三面墙时，引擎会按有效高墙扩大 `roof.span`、`roof.depth`，并在 `roof.position` 缺失时将屋顶居中放到最高墙顶。显式位置不会被覆盖。
- 楼板与墙、柱与楼板、楼梯与楼板之间的其他标高关系需要蓝图作者显式给出，引擎不会完成结构设计推导。

## 路径、楼板与屋顶挂接组件

<!-- rag-meta
entity_type: assembly
entity_name: surface_attached_component_relation
topic: assembly
status: supported
authority: engine
primary_terms:
  - railing
  - ramp
  - chimney
  - parentFloor
  - parentRoof
  - 栏杆
  - 坡道
  - 檐口
  - 烟囱
  - cornice
synonyms: []
-->

- `railing` 通过世界坐标 `path` 生成立柱与横杆；提供 `parentFloor` 时，路径以父楼板左下角和顶面为局部原点。
- `ramp` 通过 `from`、`to` 生成直线斜面，可选生成一侧或两侧栏杆；`parentFloor` 是可选局部坐标参考，并非必填父元素。
- `cornice` 通过 `path` 与二维 `profile` 扫掠；提供 `parentRoof` 时，路径挂接到当前支持的屋面坐标。
- `chimney` 可通过 `parentRoof` 确定基点并生成薄壁筒体，但当前不会对屋顶执行布尔穿透或自动生成防水节点。
- `light` 使用世界坐标 `position` 独立放置，不要求父墙、父楼板或父屋顶。

## 模板实例与表面排布

<!-- rag-meta
entity_type: assembly
entity_name: template_and_placement_relation
topic: assembly
status: supported
authority: engine
primary_terms:
  - templates
  - instances
  - placements
  - expandTemplates
  - expandPlacements
  - 模板
  - 排布
synonyms: []
-->

`geometry.instances` 可引用 `geometry.templates`，引擎为实例保存 position、rotation、scale 变换并允许材质覆盖。`geometry.placements` 也引用模板，但当前表面查询只支持 `gable` 屋顶的 `left` 和 `right`；墙、楼板、梁以及其他屋顶面的通用排布仍未实现。
