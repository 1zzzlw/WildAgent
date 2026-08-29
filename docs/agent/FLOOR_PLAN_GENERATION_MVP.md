# 建筑平面生成与确认：从空间关系到 `.wild`

> 文档分类：Agent / 建筑生成专题。返回 [正式文档入口](../README.md)。

最后核对：2026-08-25。

## 1. 这次补的是什么

原来的精密生成链更擅长回答“建筑外轮廓多大、几层、立面有什么、屋顶是什么”，对“里面有哪些空间、空间如何相连、内墙和门放在哪里”没有独立的数据协议。结果是大模型即使想到了平面，后面的骨架节点也可能重新猜一遍。

当前版本使用 `FloorPlanIR v2`，让一次平面设计同时成为预览、审核和后续几何的事实来源：

```text
用户需求
  -> architecture 只生成总体体量、立面轴网和构件配额
  -> floor_plan_design 单独调用模型生成 FloorPlanIR
  -> 确定性校验空间边界、内墙、洞口和连通图
  -> 同一份 IR + 立面轴网投影全部楼层 SVG 审核图
  -> floor_plan_review 暂停（此时不生成三维）
       ├─ 用户提交修改意见 -> 回到 floor_plan_design 生成下一版
       └─ 用户确认 -> 继续材质与确定性主体装配
  -> 同一份 IR 编译内墙、父墙局部门窗槽位和屋顶
  -> G1-G6 -> style_review 第二次确认 -> Decor IR -> G7
  -> merge / final_validate
  -> 最终 .wild Blueprint
```

这里“此时不生成三维”就是不生成、不重建、不保存任何三维建筑；审核阶段只展示由 FloorPlanIR 确定性绘制的 SVG。用户确认以后才运行正式三维链路，最终 Blueprint 通过全量校验后一次性加载到画布。

### 与《建筑平面图生成 · 通用 AI 提示词》的关系

外部方案的主方向是合适的，但项目实现不能把整段 Prompt 直接当成已经可靠的程序。初版做了以下取舍：

| 外部方案思路 | 本项目初版处理 |
|---|---|
| 先设计、再渲染、再落位 | 已采用；中间增加可校验 `FloorPlanIR` |
| 结构化文本是唯一数据源 | 已采用，但改为 JSON 协议，便于程序校验和编译 |
| 模型自行声明“校验通过” | 改为 Python 确定性演算，模型不能给自己放行 |
| 模型手写 SVG | 改为程序从 IR 绘制，避免图和数据不一致 |
| 墙黄、门红、窗蓝、深色背景、gap 洞口 | 初版已采用，并补有北向、图例和比例尺 |
| 用户确认后才生成三维 | 已实现；LangGraph 在 `floor_plan_review` 持久化暂停，可反复修改 |
| 楼梯、电梯、坡道、阳台、柱网等 11 项校验 | 已补电梯井、疏散、采光、对称、洞口距墙角和声明式功能流线；其余仍按真实引擎能力逐项扩展 |

原方案使用平面 X/Y，同时写了“原点在西南、Y 向北”和“南墙 Y 最大”，两句话相互冲突。WildAgent 已统一改为 X/Z 平面轴：`min Z` 是南侧/主前方，`max Z` 是北侧，Y 只负责高度。

## 2. v2 当前能力边界

当前已实现：

- 快速和精密模式中的新建筑生成，都先独立规划平面并等待确认；
- 同层多个矩形体量组成的 L/U 形、退台和正交回字形轮廓；
- 矩形空间、任意简单多边形空间，以及由多个多边形区域组成的同一功能空间；
- 任意方向直墙，以及 WILD 原生 `arc/ellipse/catenary` 曲墙；
- 内门、内窗的宿主墙和父墙局部位置；
- `outside` 室外连接，以及沿曲墙弧长计算的洞口位置；
- 从入口空间出发的空间连通性检查；
- 中庭、庭院、挑空、竖井等跨层洞口；
- `elevator/stair` 垂直交通语义，电梯确定性编译为各层一致的井道墙；
- 中庭或井道洞口所在标高会把原楼板拆成不覆盖洞口的矩形楼板单元；
- 可配置的电梯覆盖、近似疏散距离、窗地面积比、轴线对称、洞口距墙角和功能流线闸门；
- 全部显式楼层的确定性 SVG 审核图；
- 室内门窗来自 FloorPlanIR，外门窗来自同一建筑方案的立面轴网投影；
- 可恢复的“确认 / 修改”人工审核循环；
- 初次平面合法时立即显示“确认平面并生成三维”，修改意见是可选项，不是开始按钮的前置条件；
- 用户确认前不运行材质、正式骨架、构件、合并、三维重建和保存；审核阶段只展示 SVG；
- 用户确认后继续展示主体装配、G1-G6、风格确认、Decor IR、G7 和合并节点的文字过程；只有最终 Blueprint 校验通过并保存后才一次性加载三维；
- 将内墙写入骨架、将洞口写入现有组件槽位；
- 模型返回不合法方案、无法解析或服务不可用时，统一生成确定性基础方案；矩形层使用两区、一面内墙和一扇连通门，L/U 组合层保留真实多区域轮廓。只要确定性校验通过就允许用户直接确认。

仍需说明的真实边界：

- “规范审查”是通用方案预审配置，不是某城市、某建筑类别的法定审图结论；采用中国或地方规范前还需要建立对应规则包、适用条件和版本号。
- 当前 WILD 没有电梯轿厢构件，v2 落实的是可校验、可编译的井道和跨层服务关系，轿厢、门机及动画属于后续构件能力。
- 楼板原语仍为矩形；正交 L/U/回字形和正交洞口可精确拆板，斜边洞口会按顶点网格保守拆分，不会生成 Schema 不支持的假多边形楼板。
- 疏散距离按空间中心和门连接图计算，是方案阶段近似值；正式审查还需要最不利点、实际行走线、防火分区和出口数量等数据。

知识问答和现有场景的 ScenePatch 修改仍走各自分支；只有分类为新建筑生成的请求进入平面审核。

## 3. 坐标怎么读

WILD 的坐标约定是：

- `X`：平面左右；
- `Z`：平面前后；
- `Y`：高度和楼层标高；
- `front = min Z`；
- SVG 中北向为 `max Z`，显示在画面上方。

平面中的二维点始终写作 `[x, z]`。例如内墙：

```json
{"from": [7, 0], "to": [7, 9]}
```

表示一面位于 `X=7m`、从 `Z=0m` 延伸到 `Z=9m` 的竖向分隔墙。编译到 Blueprint 后才加入 Y：

```json
{"from": [7, 0, 0], "to": [7, 3.2, 9]}
```

这里两个端点的 Y 分别是墙底和墙顶，不要把平面图常见的 X/Y 二维习惯直接套进 WILD。

## 4. FloorPlanIR v2 最小示例

```json
{
  "levels": [{
    "level": 1,
    "entrance_space_id": "living",
    "spaces": [
      {"id": "living", "name": "起居室", "space_type": "living", "bounds": [0, 0, 7, 9]},
      {"id": "service", "name": "服务空间", "space_type": "service", "bounds": [7, 0, 12, 9]}
    ],
    "walls": [
      {"id": "partition", "from": [7, 0], "to": [7, 9], "thickness": 0.12}
    ],
    "openings": [{
      "id": "door_connection",
      "type": "door",
      "host_wall_id": "partition",
      "offset": 3.8,
      "width": 0.9,
      "height": 2.1,
      "sill_height": 0,
      "connects": ["living", "service"]
    }]
  }]
}
```

字段可以这样理解：

| 字段 | 小白解释 |
|---|---|
| `bounds` | 房间左下角和右上角，顺序为 `[x0,z0,x1,z1]` |
| `host_wall_id` | 门窗安装在哪一面墙上 |
| `offset` | 从宿主墙 `from` 端开始，沿墙走多少米后开始放洞口 |
| `connects` | 这扇门连接哪两个空间，供连通图校验使用 |
| `entrance_space_id` | 进入本层后首先到达的空间，是可达性搜索起点 |
| `polygon` | 任意简单房间轮廓，点按 `[x,z]` 顺序排列 |
| `envelope_regions` | 程序根据同层 volumes 算出的互不重叠矩形单元；L/U 形不再被压成外包矩形 |
| `curve` | 墙路径；可选 `arc`、`ellipse` 或 `catenary` |
| `vertical_spaces` | 中庭、庭院、挑空和竖井的跨层洞口 |
| `vertical_circulation` | 电梯或楼梯服务的楼层与井道轮廓 |
| `review_rules` | 需要启用的工程预审闸门及阈值 |

跨层电梯井的核心写法：

```json
{
  "vertical_circulation": [{
    "id": "lift_core",
    "type": "elevator",
    "polygon": [[4, 4], [6, 4], [6, 6], [4, 6]],
    "serves_levels": [1, 2, 3, 4]
  }],
  "review_rules": {
    "enabled": ["elevator", "egress", "opening_corner"],
    "require_elevator_from_floors": 4,
    "max_egress_distance": 30,
    "min_opening_corner_clearance": 0.3
  }
}
```

归一化后，模型给出的短 ID 会加上楼层命名空间，例如 `living` 变成 `space_1_living`，防止不同楼层重名。

## 5. 程序会检查什么

`validate_spatial_plan()` 当前执行以下硬检查：

1. 平面是否明确使用 X/Z；
2. 楼层边界是否有效；
3. 房间是否太小、越界、相互重叠，以及是否完整覆盖楼层；
4. 直墙/曲墙是否过短、越界，内墙是否位于两个空间的公共边界；
5. 门窗引用的宿主墙是否存在；
6. 洞口是否在墙长和墙高范围内，同墙洞口是否重叠；
7. 门是否连接两个存在且不同的空间，并且实际洞口位置是否落在这两个空间的相邻区段；
8. 所有空间能否从入口空间沿门的连接关系到达。

`review_rules.enabled` 还可按项目需要开启六类闸门：

| 闸门 | 计算内容 | 关键配置 |
|---|---|---|
| `elevator` | 达到指定楼层数时，是否存在覆盖全部显式楼层的电梯井 | `require_elevator_from_floors` |
| `egress` | 空间中心经门连接图到入口/室外的近似最短距离 | `max_egress_distance` |
| `daylight` | 连接室外的窗洞面积 ÷ 房间平面面积 | `min_daylight_ratio` |
| `symmetry` | 同类型空间的镜像中心与面积是否匹配 | `symmetry_axis`, `symmetry_tolerance` |
| `opening_corner` | 门窗两侧到宿主墙端点的最小净距 | `min_opening_corner_clearance` |
| `functional_flow` | 声明的空间类型序列是否逐段有直接门连接 | `required_flows` |

未启用的规则不会偷偷阻断方案。审核面板会逐条显示实测值、限制值和是否通过，并始终标注“方案预审，不替代法定审图”。

上述 8 项核心几何/拓扑检查任一失败，系统不会把原始细分方案冒充为通过，而是记录第一个 `fallback_reason`，再生成可校验的确定性基础方案。基础方案通过后会直接显示确认按钮。工程预审失败也不会先暂停并要求用户点击“重新生成”：缺少全层电梯井这类无需设计取舍的问题由程序确定性补全并立即复检；采光、流线、对称等需要重新布局的问题会把实测原因自动交回平面节点，最多重画两轮。只有两轮后仍无法兼容约束时，才保留审核图并暂停，请用户决定如何取舍。

确定性基础方案不宣称理解了精细功能需求，也不会伪造模型思考；用户可以直接确认后继续正式三维，也可以继续提交自然语言修改。

## 6. 界面的平面预览怎么看

- 黄色粗线：建筑真实组合外轮廓和内墙，L/U 凹口不会再被假墙封住；
- 红线：门洞，包括内门和立面主入口；
- 蓝线：窗洞，包括内窗和立面窗；
- 灰色文字：空间名称；
- 紫色虚线：中庭、井道或跨层挑空；
- 顶部“北 ↑”：`max Z` 方向；
- “模型方案”：模型给出的细分通过了校验；
- “确定性基础方案”：模型服务没有返回内容，程序生成了可校验、可确认的通用两区平面；
- “安全回退”：模型没有给出可靠细分，当前只保留单一主要空间。

预览出现在本轮 Agent 执行面板中，多层建筑可切换楼层。看到“等待确认平面”时：

1. 发现问题：可以在审核图下方的“修改意见”输入框写清楚，也可以直接在聊天输入框发送，例如“二层主卧增加一扇朝南窗，卫生间缩小 0.8 米”；两种入口都会恢复同一个 LangGraph 任务，把意见交回 `floor_plan_design`，生成新版后再次暂停。
2. 可以继续修改：每一版都有版本号，直到空间、门窗和轮廓满足需求。
3. 确认无误：点击“确认平面并生成三维”；随后先确定性装配主体并通过 G1-G6，再由用户第二次确认风格，最后执行 Decor IR、G7 和最终 `.wild` 保存。

完整的确认后链路、G1-G7 和按方案动态推荐的风格包见 [Plan2Build 建筑生成链路](PLAN2BUILD_PIPELINE.md)。

“总体建筑方案”和“平面设计”是两个独立步骤。两者都会实时展示可公开、可复现的执行摘要；开启思考模式后，`floor_plan_design` 还会把模型供应商实际返回的 `reasoning_content` 流式归入“模型过程”。程序不会伪造或补写供应商没有返回的内部推理。

右侧画布不显示生成中的中间 Blueprint。这样审核和生成期间不会用半成品覆盖当前正式场景，也不会因为多个重建请求完成顺序不同而闪回旧版本。最终 Blueprint 通过全量校验并保存后，才一次性加载到画布。

“不可确认的降级轮廓”与“工程预审未通过”是两种情况：前者表示基础几何本身不完整，自动恢复也失败后才需要用户补充需求；后者会先走确定性修复或最多两轮自动重画，不需要用户点击重新按钮。立面门窗和已启用的工程预审配置会在自动修改中保留。审核提交被服务端拒绝时，界面会恢复为等待审核并重新显示按钮，不会卡在“正在处理”。

## 7. 不启动前后端，单独看一个示例

在 PowerShell 中执行：

```powershell
cd E:\AgentProject\WildAgent\wild-server
.\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py
```

默认结果写入：

```text
wild-server/storage/sessions/floor_plan_preview.svg
```

用浏览器打开该 SVG 即可。要测试自己的数据，准备一个包含 `massing` 和 `spatial_plan` 的 UTF-8 JSON：

```powershell
.\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py --input .\my_plan.json --output .\storage\sessions\my_plan.svg
```

控制台会打印平面来源以及“楼层/空间/内墙/洞口”数量。出现 `deterministic_fallback` 时应继续看“回退原因”，不能只看 SVG 是否成功生成。

## 8. 开发入口与测试

| 文件 | 作用 |
|---|---|
| `wild-server/app/agent/spatial_plan.py` | IR v2 归一化、校验、摘要、SVG、井道/楼板/墙和洞口槽位编译 |
| `wild-server/app/agent/spatial_geometry.py` | 多边形、矩形并集、曲线路径与楼板拆分的共享几何函数 |
| `wild-server/app/agent/floor_plan_rules.py` | 六类可配置工程预审闸门与可读报告 |
| `wild-server/app/agent/prompts.py` | 分别约束总体建筑方案和 FloorPlanIR 输出协议 |
| `wild-server/app/agent/architecture_plan.py` | 把空间方案合入建筑方案、骨架和组件配额 |
| `wild-server/app/agent/nodes/architecture_node.py` | 只生成总体体量、立面轴网和构件配额 |
| `wild-server/app/agent/nodes/floor_plan_design_node.py` | 独立生成平面、校验、兜底与 SVG |
| `wild-server/app/agent/nodes/floor_plan_review_node.py` | LangGraph 人工暂停、确认与修订路由 |
| `wild-server/app/services/generation_job_service.py` | 保存 `waiting_review` 状态，断线后仍可恢复 |
| `wild-server/app/agent/plan2build/assembler.py` | 按已确认方案确定性装配墙、板、楼梯、门窗和屋顶 |
| `wild-server/app/agent/plan2build/gates.py` | 统一 G1-G6 GateReport |
| `wild-server/app/agent/plan2build/decor_assembler.py` | Decor IR、风格装配与 G7 |
| `wild-web/src/components/panels/AgentExecutionPanel.vue` | 分节点展示模型过程、审核图与直接确认/修改操作 |
| `wild-web/src/stores/sceneStore.ts` | 管理最终 Blueprint、重建结果、revision 与编辑历史 |
| `wild-server/tests/components/test_spatial_plan.py` | 平面协议、退台楼层、外门窗 SVG 与编译回归 |
| `wild-server/tests/components/test_floor_plan_review.py` | 确认、修订和降级方案禁止确认的回归 |

运行测试：

```powershell
cd E:\AgentProject\WildAgent\wild-server
.\.venv\Scripts\python.exe -m pytest tests\components\test_spatial_plan.py -v
```

## 9. 后续扩展原则

合理顺序不是继续堆一大段提示词，而是逐层扩大可验证协议：

1. 为具体国家/城市建立带版本和适用范围的正式规则包；
2. 在疏散图中加入最不利点、走廊净宽、防火分区和多个安全出口；
3. 增加电梯轿厢、层门、门机和运行行为构件；
4. 为非正交楼板增加 WILD 原生 polygon + holes 几何，而不是长期依赖保守矩形拆分；
5. 用真实建筑任务建立平面评测集，统计有效率、连通率、规则通过率和最终编译一致率。

每一步都应同时补协议、确定性校验、编译器和回归用例。这样建筑方法会成为系统能力，而不是只存在于某一版 Prompt 中。
