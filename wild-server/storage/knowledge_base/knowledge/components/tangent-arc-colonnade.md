---
entity_name: tangent_arc_colonnade
entity_type: component
topic: composition
status: experimental
authority: schema
primary_terms: [古典柱廊局部构件]
synonyms: []
applies_to: [拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶]
---

# 拱圈、柱头、檐部与台基的局部组合

资料取自用户提供的《欧式建筑-古典柱廊殿宇蓝图书写规则及蓝图示范》v1.5，按当前 WILD Schema、compiler 与 resolver 核对后转换。原文整栋布局、固定柱数、坡度和“硬规则”不作为生成限制。以下是局部构件片段：elements/components 并入 geometry，materials 并入材质字典；已有宿主只替换引用，不重复创建。所有尺寸、采样数、材料和排列服从当前图纸。

## 拱形门与石拱圈

<!-- rag-meta
entity_type: door
entity_name: arched_door
topic: composition
primary_terms: ["拱形门","石拱门"]
synonyms: ["arched door"]
-->

opening 是原生门扇形体，from=[左缘沿墙距离,底部世界Y,法向偏移]。此静态示例以朱红木材表达拱顶门扇；没有 door 的开合交互。若图纸要求可开启门，可使用 door.openingStyle=arched，并核对其矩形框料与自建拱圈的重合。普通矩形门直接用 door，不借本例生成第二套洞口。

拱圈采用相切旋置 box，示例 n=24、Δ=π/n、θ=(k+0.5)Δ，中心=(rm cosθ,拱脚Y+rm sinθ)。box 的 X 为切向长轴，所以正面墙 rotation.z=θ−π/2；弦长为 2rm sin(Δ/2)，本例另加 0.007m 搭接。原资料写成 sin(π/n) 且直接旋转 θ，会把弦长翻倍、长轴转成径向，不能照抄。一般墙面先在墙局部平面布置，再整体变换到世界坐标。

```json
{"elements":[{"type":"wall","id":"arch_host","from":[-2,0.9,0],"to":[2,4,0],"thickness":0.3,"material":"stone"},{"type":"opening","id":"arched_door","parentWall":"arch_host","from":[1.25,0.9,0],"width":1.5,"height":2.55,"style":"arched","depth":0.04,"material":"wood"},{"type":"primitive","id":"jamb_0","shape":"box","position":[-0.87,1.8,-0.18],"dimensions":[0.2,1.8,0.24],"material":"stone"},{"type":"primitive","id":"jamb_1","shape":"box","position":[0.87,1.8,-0.18],"dimensions":[0.2,1.8,0.24],"material":"stone"},{"type":"primitive","id":"arch_stone_0","shape":"box","position":[0.868137,2.756901,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-1.505346],"material":"stone"},{"type":"primitive","id":"arch_stone_1","shape":"box","position":[0.853283,2.869729,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-1.374447],"material":"stone"},{"type":"primitive","id":"arch_stone_2","shape":"box","position":[0.823829,2.979652,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-1.243547],"material":"stone"},{"type":"primitive","id":"arch_stone_3","shape":"box","position":[0.780279,3.084791,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-1.112647],"material":"stone"},{"type":"primitive","id":"arch_stone_4","shape":"box","position":[0.723379,3.183346,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.981748],"material":"stone"},{"type":"primitive","id":"arch_stone_5","shape":"box","position":[0.654101,3.273631,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.850848],"material":"stone"},{"type":"primitive","id":"arch_stone_6","shape":"box","position":[0.573631,3.354101,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.719948],"material":"stone"},{"type":"primitive","id":"arch_stone_7","shape":"box","position":[0.483346,3.423379,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.589049],"material":"stone"},{"type":"primitive","id":"arch_stone_8","shape":"box","position":[0.384791,3.480279,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.458149],"material":"stone"},{"type":"primitive","id":"arch_stone_9","shape":"box","position":[0.279652,3.523829,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.327249],"material":"stone"},{"type":"primitive","id":"arch_stone_10","shape":"box","position":[0.169729,3.553283,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.19635],"material":"stone"},{"type":"primitive","id":"arch_stone_11","shape":"box","position":[0.056901,3.568137,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,-0.06545],"material":"stone"},{"type":"primitive","id":"arch_stone_12","shape":"box","position":[-0.056901,3.568137,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.06545],"material":"stone"},{"type":"primitive","id":"arch_stone_13","shape":"box","position":[-0.169729,3.553283,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.19635],"material":"stone"},{"type":"primitive","id":"arch_stone_14","shape":"box","position":[-0.279652,3.523829,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.327249],"material":"stone"},{"type":"primitive","id":"arch_stone_15","shape":"box","position":[-0.384791,3.480279,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.458149],"material":"stone"},{"type":"primitive","id":"arch_stone_16","shape":"box","position":[-0.483346,3.423379,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.589049],"material":"stone"},{"type":"primitive","id":"arch_stone_17","shape":"box","position":[-0.573631,3.354101,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.719948],"material":"stone"},{"type":"primitive","id":"arch_stone_18","shape":"box","position":[-0.654101,3.273631,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.850848],"material":"stone"},{"type":"primitive","id":"arch_stone_19","shape":"box","position":[-0.723379,3.183346,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,0.981748],"material":"stone"},{"type":"primitive","id":"arch_stone_20","shape":"box","position":[-0.780279,3.084791,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,1.112647],"material":"stone"},{"type":"primitive","id":"arch_stone_21","shape":"box","position":[-0.823829,2.979652,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,1.243547],"material":"stone"},{"type":"primitive","id":"arch_stone_22","shape":"box","position":[-0.853283,2.869729,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,1.374447],"material":"stone"},{"type":"primitive","id":"arch_stone_23","shape":"box","position":[-0.868137,2.756901,-0.18],"dimensions":[0.120801,0.24,0.24],"rotation":[0,0,1.505346],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"wood":{"baseColor":[0.38,0.15,0.1],"roughness":0.65,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

能力边界：24 段为多边形近似，不是数学光滑圆环；样例为外侧石材拱圈。当前墙裁洞仍是矩形，opening 面板呈拱形，斜视角可见拱肩空角。完整石砌真拱洞需要另按几何填补拱肩，不能把这份近似标成精确拱洞。

依据：`wild-core/schema.json`、`src/compiler/components/door.ts`、`window.ts`、`src/primitive/resolver.ts`、`geometry/column.ts`、`roof.ts`。已按该版片段进行 Schema、实现检查及真实渲染；外观仍需用户确认，未标为 verified_example。

## 拱形窗与石拱圈

<!-- rag-meta
entity_type: window
entity_name: arched_window
topic: composition
primary_terms: ["拱形窗","石拱窗"]
synonyms: ["arched window"]
-->

当前 window 没有 openingStyle；本例直接用 arched opening 的面板作玻璃，材质 transmission=0.92、ior=1.5、opacity=1。不要叠加矩形 window 或另一片玻璃充当窗框。石拱圈是外围 primitive，尺寸随洞口宽高和拱脚标高变化；本例左缘沿墙 1.4m、窗底世界Y=1.8m，宿主墙底0.9m。

```json
{"elements":[{"type":"wall","id":"arch_host","from":[-2,0.9,0],"to":[2,4,0],"thickness":0.3,"material":"stone"},{"type":"opening","id":"arched_window","parentWall":"arch_host","from":[1.4,1.8,0],"width":1.2,"height":2.1,"style":"arched","depth":0.012,"material":"glass"},{"type":"primitive","id":"jamb_0","shape":"box","position":[-0.72,2.55,-0.18],"dimensions":[0.2,1.5,0.24],"material":"stone"},{"type":"primitive","id":"jamb_1","shape":"box","position":[0.72,2.55,-0.18],"dimensions":[0.2,1.5,0.24],"material":"stone"},{"type":"primitive","id":"arch_stone_0","shape":"box","position":[0.718458,3.34709,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-1.505346],"material":"stone"},{"type":"primitive","id":"arch_stone_1","shape":"box","position":[0.706165,3.440465,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-1.374447],"material":"stone"},{"type":"primitive","id":"arch_stone_2","shape":"box","position":[0.68179,3.531436,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-1.243547],"material":"stone"},{"type":"primitive","id":"arch_stone_3","shape":"box","position":[0.645748,3.618448,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-1.112647],"material":"stone"},{"type":"primitive","id":"arch_stone_4","shape":"box","position":[0.598658,3.700011,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.981748],"material":"stone"},{"type":"primitive","id":"arch_stone_5","shape":"box","position":[0.541325,3.774729,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.850848],"material":"stone"},{"type":"primitive","id":"arch_stone_6","shape":"box","position":[0.474729,3.841325,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.719948],"material":"stone"},{"type":"primitive","id":"arch_stone_7","shape":"box","position":[0.400011,3.898658,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.589049],"material":"stone"},{"type":"primitive","id":"arch_stone_8","shape":"box","position":[0.318448,3.945748,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.458149],"material":"stone"},{"type":"primitive","id":"arch_stone_9","shape":"box","position":[0.231436,3.98179,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.327249],"material":"stone"},{"type":"primitive","id":"arch_stone_10","shape":"box","position":[0.140465,4.006165,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.19635],"material":"stone"},{"type":"primitive","id":"arch_stone_11","shape":"box","position":[0.04709,4.018458,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,-0.06545],"material":"stone"},{"type":"primitive","id":"arch_stone_12","shape":"box","position":[-0.04709,4.018458,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.06545],"material":"stone"},{"type":"primitive","id":"arch_stone_13","shape":"box","position":[-0.140465,4.006165,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.19635],"material":"stone"},{"type":"primitive","id":"arch_stone_14","shape":"box","position":[-0.231436,3.98179,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.327249],"material":"stone"},{"type":"primitive","id":"arch_stone_15","shape":"box","position":[-0.318448,3.945748,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.458149],"material":"stone"},{"type":"primitive","id":"arch_stone_16","shape":"box","position":[-0.400011,3.898658,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.589049],"material":"stone"},{"type":"primitive","id":"arch_stone_17","shape":"box","position":[-0.474729,3.841325,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.719948],"material":"stone"},{"type":"primitive","id":"arch_stone_18","shape":"box","position":[-0.541325,3.774729,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.850848],"material":"stone"},{"type":"primitive","id":"arch_stone_19","shape":"box","position":[-0.598658,3.700011,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,0.981748],"material":"stone"},{"type":"primitive","id":"arch_stone_20","shape":"box","position":[-0.645748,3.618448,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,1.112647],"material":"stone"},{"type":"primitive","id":"arch_stone_21","shape":"box","position":[-0.68179,3.531436,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,1.243547],"material":"stone"},{"type":"primitive","id":"arch_stone_22","shape":"box","position":[-0.706165,3.440465,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,1.374447],"material":"stone"},{"type":"primitive","id":"arch_stone_23","shape":"box","position":[-0.718458,3.34709,-0.18],"dimensions":[0.101181,0.24,0.24],"rotation":[0,0,1.505346],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},"glass":{"baseColor":[0.85,0.93,0.98],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.92,"ior":1.5,"opacity":1}}}
```

能力边界：这是静态玻璃与石材拱圈的组合近似；墙洞仍是矩形，拱肩空角没有填补，没有窗扇开合语义。棂条等附加细节可由 primitive 表达，但本例没有这些构件。

依据：`wild-core/schema.json`、`src/compiler/components/door.ts`、`window.ts`、`src/primitive/resolver.ts`、`geometry/column.ts`、`roof.ts`。已按该版片段进行 Schema、实现检查及真实渲染；外观仍需用户确认，未标为 verified_example。

## 罗马柱与柱头承接

<!-- rag-meta
entity_type: column
entity_name: roman_column
topic: composition
primary_terms: ["罗马柱","柱头垫块"]
synonyms: ["roman column","abacus"]
-->

原生 column 位于 elements，base 是柱底世界中心。本例台座顶0.3m，柱顶3.3m，垫块底3.3m、顶3.42m，额枋底3.42m。根据本次设计决定是否需要额外垫块；当前柱引擎已有简化柱式细部，不应照资料宣称“原生完全没有柱头”。单柱任务只生成当前柱及其已选附件，跨柱额枋若属于独立檐部任务便只参考承接标高，不重复搭建。

```json
{"elements":[{"type":"primitive","id":"support_plinth","shape":"box","position":[0,0.15,0],"dimensions":[1,0.3,1],"material":"stone"},{"type":"column","id":"classical_column","base":[0,0.3,0],"height":3,"bottomRadius":0.25,"topRadius":0.2,"style":"doric","flutes":20,"material":"stone"},{"type":"primitive","id":"abacus","shape":"box","position":[0,3.36,0],"dimensions":[0.66,0.12,0.66],"material":"stone"},{"type":"primitive","id":"architrave","shape":"box","position":[0,3.57,0],"dimensions":[2.4,0.3,0.7],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

能力边界：doric/ionic/corinthian 是引擎简化柱式，不能当作精确历史柱头雕刻。柱距、根数、收分与小量嵌入均由图纸和实际衔接决定，不要求所有柱一律过盈。

依据：`wild-core/schema.json`、`src/compiler/components/door.ts`、`window.ts`、`src/primitive/resolver.ts`、`geometry/column.ts`、`roof.ts`。已按该版片段进行 Schema、实现检查及真实渲染；外观仍需用户确认，未标为 verified_example。

## 古典檐部：额枋、饰带与檐口

<!-- rag-meta
entity_type: cornice
entity_name: classical_entablature
topic: composition
primary_terms: ["古典檐部","三段檐部"]
synonyms: ["entablature","classical entablature"]
-->

以三条 primitive.box 表达一段檐部：额枋Y[3.3,3.6]、饰带Y[3.6,3.9]、檐口Y[3.9,4.14]；檐口向两侧及法向出挑。这里仅示范一段，不包含宿主柱和屋顶；安装时沿本次柱网边界旋转并闭合转角，避免各边重建同一转角体。不能把这三层示例高度当作所有古典建筑的比例限制。

```json
{"elements":[{"type":"primitive","id":"architrave","shape":"box","position":[0,3.45,0],"dimensions":[3,0.3,0.7],"material":"stone"},{"type":"primitive","id":"frieze","shape":"box","position":[0,3.75,0],"dimensions":[3,0.3,0.7],"material":"stone"},{"type":"primitive","id":"cornice","shape":"box","position":[0,4.02,0],"dimensions":[3.2,0.24,1],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

能力边界：这是静态分层形体，不含雕刻、三陇板或承重验算。已经由主体或另一任务实现的檐部不再次叠加。

依据：`wild-core/schema.json`、`src/compiler/components/door.ts`、`window.ts`、`src/primitive/resolver.ts`、`geometry/column.ts`、`roof.ts`。已按该版片段进行 Schema、实现检查及真实渲染；外观仍需用户确认，未标为 verified_example。

## 踏步台基

<!-- rag-meta
entity_type: floor
entity_name: stepped_plinth
topic: composition
primary_terms: ["踏步台基","三级台基"]
synonyms: ["stepped plinth","crepidoma"]
-->

独立台基用逐层内收的 primitive.box 表达。position 为实体中心，本例三层标高[0,0.3]、[0.3,0.6]、[0.6,0.9]，最上层承托面Y=0.9。内殿 floor 按殿身体量分片；外围台基不改写为主体的整栋 floor，更不能用一个包围盒填满庭院。层数、宽深、踏步高度和承托标高均为本次图纸变量。

```json
{"elements":[{"type":"primitive","id":"step_base","shape":"box","position":[0,0.15,0],"dimensions":[4.2,0.3,3.2],"material":"stone"},{"type":"primitive","id":"step_middle","shape":"box","position":[0,0.45,0],"dimensions":[3.6,0.3,2.6],"material":"stone"},{"type":"primitive","id":"step_top","shape":"box","position":[0,0.75,0],"dimensions":[3,0.3,2],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

能力边界：样例表达实体台阶外形，不含栏杆、无障碍或专业安全规范判断；这些内容按用户要求另行设计。

依据：`wild-core/schema.json`、`src/compiler/components/door.ts`、`window.ts`、`src/primitive/resolver.ts`、`geometry/column.ts`、`roof.ts`。已按该版片段进行 Schema、实现检查及真实渲染；外观仍需用户确认，未标为 verified_example。

## 双坡屋顶与山花端面

<!-- rag-meta
entity_type: roof
entity_name: gable_roof
topic: composition
primary_terms: ["双坡屋顶","人字屋顶"]
synonyms: ["gable roof","gable"]
-->

原生 roofType=gable 以 position 的Y作支承标高，span/depth为覆盖尺寸，height为檐口到屋脊的高差。ridgeAxis 写实际世界屋脊轴 x 或 z，必须与图纸 roof.ridge_axis 一致，不能只在文字中说明方向。本例墙顶3m、屋脊3.9m；两面支承墙只为解释安装，实际安装保留已有宿主。当前引擎已经生成山墙端板，不能因旧资料写“无山墙体块”而重复填满同一端面。额外坡檐口、浮雕或山花饰件只在图纸选中时添加。

```json
{"elements":[{"type":"wall","id":"support_front","from":[-2,0,0],"to":[2,3,0],"thickness":0.3,"material":"stone"},{"type":"wall","id":"support_back","from":[2,0,3],"to":[-2,3,3],"thickness":0.3,"material":"stone"},{"type":"roof","id":"gable_roof","roofType":"gable","span":4.4,"depth":3.4,"height":0.9,"thickness":0.12,"position":[0,3,1.5],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

能力边界：这是原生双坡屋面与端板示例，没有新增雕塑山花；坡度不是固定15°，也不禁止25°以上。

依据：`wild-core/schema.json`、`src/compiler/components/door.ts`、`window.ts`、`src/primitive/resolver.ts`、`geometry/column.ts`、`roof.ts`。已按该版片段进行 Schema、实现检查及真实渲染；外观仍需用户确认，未标为 verified_example。

## 开敞柱廊的一跨承接

<!-- rag-meta
entity_type: column
entity_name: colonnade
topic: composition
primary_terms: [柱廊, 开敞柱廊]
synonyms: [colonnade, peristyle]
applies_to: [柱廊, 开敞柱廊, colonnade, peristyle]
-->

局部参考取自用户已渲染认可的欧式古典殿宇：台基顶面、两根相邻柱和柱顶檐部，平移到局部坐标后保留柱高与柱距。两柱之间是通行的开敞跨，不因投影框自动建实墙；内殿围护是另一条实际墙线，不能与外圈柱轴线混为一个封闭矩形。

```json
{"elements":[{"type":"floor","id":"colonnade_support","from":[-0.6,0.7,-0.6],"to":[2.1,0.7,0.6],"thickness":0.18,"material":"stone"},{"type":"column","id":"bay_column_0","base":[0,0.88,0],"height":3.24,"bottomRadius":0.25,"topRadius":0.2,"style":"doric","material":"stone"},{"type":"column","id":"bay_column_1","base":[1.5,0.88,0],"height":3.24,"bottomRadius":0.25,"topRadius":0.2,"style":"doric","material":"stone"},{"type":"primitive","id":"bay_entablature","shape":"box","position":[0.75,4.21,0],"dimensions":[2.04,0.18,0.62],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

本例台基顶0.88m，柱底0.88m、柱高3.24m、柱顶4.12m；檐部底4.12m、顶4.30m。外圈柱廊与内殿尺寸、顶面标高和屋顶覆盖分别从图纸读取。以上数字是局部安装示例，不要求固定柱数、柱距或整栋缩放比例。已有台基或独立檐部任务时只引用这些定位，不重建其他任务的实体；只有属于当前组合的构件才写进片段。字段依据当前 column/floor/primitive Schema，简化柱式不是精确历史雕刻。

## 山花面板与斜边框料

<!-- rag-meta
entity_type: primitive
entity_name: pediment
topic: composition
primary_terms: [山花, 三角山花]
synonyms: [pediment, triangular pediment]
-->

山花是正立面的三角面与斜边框料，区别于横向的古典檐部 classical_entablature。以下面板采用 box 分片的阶梯近似，斜边采用两条旋置 box；它不是精确三角形实面。原始殿宇通过原生 gable 表达屋面和端板；该方案应优先复用端板，以下仅用于图纸要求独立山花的局部表达。

```json
{"elements":[{"type":"primitive","id":"pediment_fill_0","shape":"box","position":[0,0.03,0],"dimensions":[3.8,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_1","shape":"box","position":[0,0.09,0],"dimensions":[3.6,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_2","shape":"box","position":[0,0.15,0],"dimensions":[3.4,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_3","shape":"box","position":[0,0.21,0],"dimensions":[3.2,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_4","shape":"box","position":[0,0.27,0],"dimensions":[3,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_5","shape":"box","position":[0,0.33,0],"dimensions":[2.8,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_6","shape":"box","position":[0,0.39,0],"dimensions":[2.6,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_7","shape":"box","position":[0,0.45,0],"dimensions":[2.4,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_8","shape":"box","position":[0,0.51,0],"dimensions":[2.2,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_9","shape":"box","position":[0,0.57,0],"dimensions":[2,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_10","shape":"box","position":[0,0.63,0],"dimensions":[1.8,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_11","shape":"box","position":[0,0.69,0],"dimensions":[1.6,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_12","shape":"box","position":[0,0.75,0],"dimensions":[1.4,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_13","shape":"box","position":[0,0.81,0],"dimensions":[1.2,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_14","shape":"box","position":[0,0.87,0],"dimensions":[1,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_15","shape":"box","position":[0,0.93,0],"dimensions":[0.8,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_16","shape":"box","position":[0,0.99,0],"dimensions":[0.6,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_17","shape":"box","position":[0,1.05,0],"dimensions":[0.4,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_fill_18","shape":"box","position":[0,1.11,0],"dimensions":[0.2,0.06,0.2],"material":"stone"},{"type":"primitive","id":"pediment_edge_w","shape":"box","position":[-1,0.6,0],"dimensions":[2.33238075793812,0.12,0.28],"rotation":[0,0,0.5404195002705842],"material":"stone"},{"type":"primitive","id":"pediment_edge_e","shape":"box","position":[1,0.6,0],"dimensions":[2.33238075793812,0.12,0.28],"rotation":[0,0,-0.5404195002705842],"material":"stone"}],"components":[],"materials":{"stone":{"baseColor":[0.85,0.82,0.75],"roughness":0.75,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}}
```

本例位于 XY 立面，基线Y=0、宽4m、高1.2m、板厚0.2m。每层填板上缘宽=4×(1-上缘高度/1.2)，position 是该层中点；上缘收分保证填板不超出三角轮廓。离散近似在边缘与顶角有小空隙，可按当前粒度增加分片或使用原生端板，不把样例分片数提升为规则。整体平移到实际檐部顶或屋面端部，随朝向旋转。不能把整个三角 profile 沿立面 X 轴扫掠成悬挑屋面；closedProfile 不会补路径端盖。已有屋顶端板时不再叠加此面板。
