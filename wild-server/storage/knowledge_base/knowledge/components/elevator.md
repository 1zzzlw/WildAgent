---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: elevator
entity_name: elevator_component
topic: parameters
status: supported
authority: engine
primary_terms:
  - 电梯
  - elevator
  - 轿厢
  - 电梯井
  - 井道
  - 呼梯按钮
  - 垂直交通
synonyms:
  - 升降梯
  - 观光梯
---

# 电梯（elevator）组件参数契约

> 来源：引擎 elevator 组件实现 + 用户提供的电梯设计图纸（双联/单梯电梯井布置平面与详图）核对。
> 用途：定义井道内可运行轿厢 `elevator` 组件的参数与约束。用户要求电梯、升降梯或垂直交通时使用本组件；
> 井道围合本身由骨架的 `wall_core_*` 混凝土墙表达，本组件只负责"会动的部分"：轿厢、导轨与呼梯按钮。

## 基本定义

`elevator` 是 `geometry.components` 中的组合组件：

```json
{
  "type": "elevator",
  "id": "elevator_main",
  "position": [5.0, 0.0, 3.0],
  "dimensions": { "width": 1.4, "depth": 1.6, "height": 2.2 },
  "floorHeight": 3.3,
  "floorCount": 3,
  "initialFloor": 0,
  "material": "metal",
  "frameMaterial": "metal"
}
```

## 必填与可选字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | ✓ | `"elevator"` |
| `id` | ✓ | 稳定唯一 ID |
| `position` | ✓ | **当前停靠层的轿厢地板中心** `[x, y, z]`；`y` 取该层地面标高（底层即 0） |
| `dimensions` | ✓ | `{ width, depth, height }` 轿厢外廓（米），均 >0；宽/深须小于井道净空，`height` 必须小于 `floorHeight` |
| `floorHeight` | ✓ | 单层行驶距离（米），与建筑层高一致（如 3.3） |
| `floorCount` | ✓ | 井道跨越的层数（含底层），≥1 整数 |
| `initialFloor` | ✗ | 初始停靠楼层（0 基），默认 0（底层）；必须落在 `[0, floorCount)` |
| `material` | ✗ | 轿厢材质，默认金属语义材质 |
| `frameMaterial` | ✗ | 门框/导轨金属件材质 |

## 约束

- **井道围合不由本组件生成**：井壁、分隔墙用 `wall_core_*` 命名的 `wall`（厚 0.2 混凝土）表达；
  骨架 `core_and_stair` 策略已自动生成带逐层门洞的核心筒，此时**不要再手写井道墙**，只补轿厢。
- 🔴 **必须有井道围合**：电梯必须与骨架的 `core_and_stair` 配套。骨架没有 `wall_core_*` 时
  轿厢无处可停，校验只报 ⚠️（能力缺失不阻断），但生成侧不应在这种前提下派发电梯 ——
  用户点名电梯时，规划阶段会把 `vertical_strategy` 升到 `core_and_stair`。
- 🔴 **井道尺寸是设备尺寸，不是比例推导**：单井外廓 2.4×2.6m（净空约 2.0×2.2m）；
  建筑面宽放得下双联时取 4.6×2.6m（两格井 + 中间 0.2m 分隔墙）。早期实现按建筑宽深的
  0.24/0.28 倍推导，得到 2.1m 宽 × 4.8m 深的长条井道 —— 既不像电梯，又会在 L/U 形平面
  上把井壁推到建筑轮廓之外。井道与楼梯沿各层公共投影区的长轴分工排布，两者不重叠。
- 🔴 **轿厢必须落在「某一格」井的净空内**：双联井的分隔墙把井道切成左右两格，
  骑在分隔墙上的轿厢等于装不进去。停靠口径是 `position` 的 X/Z 取该格井中心、
  `position[1] = initialFloor × floorHeight`。组件与骨架是**两条独立生成的路径**，
  所以 `app/tools/component_tools.py` 的电梯修复器会从 `wall_core_*` 反推井格，
  把 `position`、`dimensions`、`floorHeight`、`floorCount` 一并对齐到骨架，
  不依赖模型算出坐标。
- **轿厢必须装得进井道**：`dimensions.width/depth` 小于井道内净空（两侧各留导轨与间隙约 0.15m）；
  `dimensions.height` 必须小于 `floorHeight`，否则编译器自动压缩到 `floorHeight - 0.15`。
- 🔴 **`floorHeight` / `floorCount` 必须与骨架一致**：`floorHeight` 取骨架层高（相邻楼层标高差），
  `floorCount` 取井道真实跨越的层数（含底层）。写错会让轿厢停在两层楼板之间、或顶层呼不到梯。
- **停靠位置恒为层高整数倍**：轿厢地板对齐各层地面标高；`position[1]` 是初始停靠层的地面标高。
- **底层不开门洞**：电梯不向基坑开门；骨架生成的核心筒在底层前墙无洞，二层起每层开门洞
  （宽 0.9m、高约 2.1m）：双联井两个（各占井格开间中心），单井一个（居中）。
- 🔴 **井道朝向由公共区长轴决定，不要按"南北/东西"想当然**：井道放在公共区长轴的**起点端**、
  楼梯在其外侧，所以候梯面恒为**长轴起点端那面墙**（长轴沿 z 时是核心筒的 `front` 墙、
  沿 x 时是 `left` 墙）；**分隔墙垂直于候梯面**（＝垂直于轿厢并排方向），且**只在双联井里存在** ——
  单轿厢井再加一道分隔墙会把 2.4m 面宽切成两格 0.9m，而那扇居中的门恰好压在墙身上，
  井与门一起作废。这两处曾硬编码在 x 轴上，长轴沿 x 时把「进深」当「面宽」对半切，
  双联井退化成两格 1.0×4.2m 的长条（实测）。手写井道时照此约定写 `wall_core_*` 的 id 与坐标。
- **单格井净空恒为 2.0×2.2m**（双联 4.6×2.6 外廓减两侧 0.2 井壁、再减分隔墙两侧各 0.1；
  单井 2.4×2.6 外廓减两侧 0.2 井壁，无分隔墙）。住宅轿厢 1.4~1.6m 宽、配 0.15m 间隙即 1.9×2.1m，
  这是"井格装得进电梯"的下限（回归测试 `test_shaft_bays_can_hold_a_real_cab`）。
- **楼板须留井**：核心筒楼板开口由骨架 `_cut_core_shaft_openings` 统一拆板处理；手写井道时要保证
  井道投影内各层楼板开口（复用多块 floor 拼板，同楼梯井规则）。

## 编译产物与交互

- 编译后产出：`primitive.box`（轿厢）+ `primitive.box`×2（背部导轨）+ `primitive.cylinder`（呼梯按钮）。
- **呼梯**：**右键**点击轿厢或呼梯按钮，轿厢升到下一楼层；已在顶层则循环回底层。单层行程约 1.2s。（左键留给选中高亮，与门窗开合同一套右键约定。）
- 运行时消费点是 `wild-web/src/renderer/renderEntity.ts::callElevator`（由 `toggleRuntimeInteraction`
  按 `interaction.kind` 分派），目前只有**编辑器视口**（`CanvasViewport.vue`）绑定了该分派；
  单文件查看器 `lantu/viewer` 是纯展示、不响应呼梯 —— 在那里点不动是预期行为，不是蓝图缺陷。
- 楼层推进只存在于前端运行时，**不写回 Blueprint**；静态蓝图只保存 `initialFloor`，
  与门窗开合、灯具开关同一套交互原则。

## 设计图纸参考值（领域参考，非引擎硬约束）

电梯布置图纸（双联/单梯乘客电梯井道平面与详图）中的经验值，映射到本组件时按需取用，
均属**自由变量**——用户或方案点名了再对齐：

| 图纸声明 | 处置 | WILD 映射 |
|------|------|------|
| 井道墙 200 厚混凝土 | normalized | `wall_core_*` 的 `thickness: 0.2`、`material: concrete` |
| 中分门净宽 904mm | downgraded | 电梯门洞 `width: 0.9`（骨架门洞默认值一致） |
| 门洞高约 2.1m | normalized | 门洞 `height: 2.1`（层高低时收缩为 `floorHeight - 1.0` 下限 1.8） |
| 轿厢 1400×2000 级（630~1000kg） | downgraded | `dimensions` 推荐 `{width: 1.4, depth: 1.6~2.0, height: 2.2}`；住宅场景取小值 |
| 候梯厅净深 1400mm | routed | 井道前墙外需留走道——由骨架按公共投影区尺寸保证，不进组件字段：短边 ≥ 井道宽+0.4（单井 2.8m / 双联 5.0m）、长边 ≥ 井道深 2.6 + 净距 0.3 + 梯跑（≥1.6）≈ 4.5m；放不下时核心筒降级为纯楼梯（能力缺失只标记不阻断） |
| 对重后置（导轨在后侧） | normalized | 编译器导轨固定在轿厢背部两侧（`depth/2 + 0.05` 偏移），无需字段表达 |
| 双联井道外廓约 5.65m×4.33m、单梯约 2.02m×1.86m 净空 | normalized | 骨架核心筒外廓：双联 4.6×2.6m、单井 2.4×2.6m（含 0.2m 井壁）；放得下双联就取双联，由各层公共投影区尺寸决定 |

## 能力边界

- ❌ 不生成真实曳引机、缆索与配重块——导轨只是装饰性 primitive。
- ❌ 不做非线性运动（加减速曲线）——前端为恒速楼层平移。
- ❌ 单层建筑（`floorCount: 1`）没有移动意义，不要生成；多层建筑且用户提到电梯/垂直交通时才使用。
- ❌ 井道外观（门套、层显）未实现——门洞由 `opening` 切出，可自行用 `primitive` 补门套装饰。
- ⚠️ 井道尺寸不按建筑宽深缩放：单井 / 双联二选一，都取设备尺寸。平面太窄时优先保证
  井道整体落在各层公共投影区内、楼梯另占一段（骨架已自动按长轴分工），
  而不是把井道挤成不像电梯的长条。
