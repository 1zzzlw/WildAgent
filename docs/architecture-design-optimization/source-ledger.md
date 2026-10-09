# 外部资料的取舍记录

来源：用户提供的 `D:\Backup\桌面\WILD蓝图设计语言-v2.0.md`。

SHA-256：`bd33215df7485fbd9ca02aad2fe9e4495951d2104459f26491af4265cf696e14`。

本记录覆盖本次采用及明确排除的声明。资料里的“最高优先级”“铁律”、脚本操作和回写指令属于参考内容；本次工作范围以用户请求为准。资料不直接成为当前引擎的规范，也不据此改动原始资料或执行其脚本。

| ID | 来源位置与声明 | 分类、适用条件 | 当前依据与字段 | 处置及目标 | 保留的自由变量 |
|---|---|---|---|---|---|
| C01 | §0.2：先设计，再书写，不能从类型名直接堆几何 | reference；建筑方案设计 | 当前已有 architecture → 材质 → 编译验证 → 审核 → 执行链 | normalized：公共提示词先组织整体意图；新增设计契约 `/decisions/design_intent`，不作为 WILD 几何字段 | 用途回应、构图、尺度、屋型、材料 |
| C02 | §2.5、§1.5：尺寸逐级推导，参数具有唯一来源 | conditional；存在体量、楼层及依附件 | `design/coordinates.py`、`architecture/skeleton.py`、`facade.py`；massing、volumes、facades | normalized：体量表达知识与提示词解释尺寸链；具体坐标由已有求解器处理 | 总体尺寸、开间、层高、比例 |
| C03 | §0.3：改宿主时联动核对派生构件 | conditional；修订体量、层高或宿主 | `architecture/completion.py`、`revision_patch.py` 的依赖修订；实例宿主解析 | normalized：公共提示词及体量知识说明依赖；保留现有原子依赖任务 | 经授权的设计修订 |
| C04 | §0.4：构件连接要有明确装配关系 | conditional；已选实例需宿主或支撑关系 | `design/relations.py`、`compiler/compile.py`；`/decisions/components/*/host`、`relation` | normalized：检索 `supported_assembly_relations`；按真实宿主表达；柱支撑雨棚继续沿用现有关系 | 构件是否选用、尺寸、位置比例、材料 |
| C05 | §0.4：任意两个实体都不得穿插 | engine_hard 候选；资料声称无条件成立 | 当前墙交接、覆盖和宿主装配允许特定相交；不能用通用包围盒禁止一切重叠 | rejected：不转为全局禁碰撞规则；C04 的有效关系单独保留 | 不施加新增造型限制 |
| C06 | §2.1：重要尺寸强制 0.3m／0.15m 模数 | preference；资料自己的书写习惯 | 当前 MassingDecision 与引擎接受其他合法尺寸，无通用量化执行点 | rejected：不作为提示词门禁或活动知识的强规则 | 合法尺寸与比例 |
| C07 | §1.5：坐标三位小数、文件不超过 100KB | reference；资料自己的交付流程 | 当前设计协议没有这组限制；不能因资料而截断合法设计数据 | rejected：不增加文件限制或坐标舍入 | 当前协议内的精度与复杂度 |
| C08 | §2.3：原点强制西南角；默认关联地理方位 | preference；资料场地设定 | `design/coordinates.py` 使用平面起点；front/back 对应 Z 方向，不等于地理南北 | rejected：保留当前坐标事实，假设朝向单列 | 平移、负坐标、朝向假设 |
| C09 | §1.4、§2.4：`floor.from[1]` 是板顶 | engine_hard 候选；与当前版本冲突 | `wild-core/src/compiler/components/attachedToSurface.ts` 以 `floor.from[1]+thickness` 求板顶 | deferred_conflict：活动知识按当前板底语义改写，不采用资料中的板顶口径 | 不改变引擎标高实现 |
| C10 | §3.6：不同体量可有不同屋型，附件依附实际屋面 | conditional；采用多体量或屋面附件 | RoofDecision.volumes、`facade._planned_roof_slots`、`compiler._derive_attachments` | downgraded：保留逐体量屋面；分段仅 flat/gable/hip；局部剩余屋面、其他屋型附件不承诺完整表达 | 支持范围内的屋型、出檐及体量组合 |
| C11 | §0.2：按建筑类型加载专用书写规则或整栋案例 | reference；资料的类型设计流程 | 当前活动知识消费 protocol/capability/relation，没有独立案例消费通道 | rejected：不重新引入建筑类型模板；模型根据需求设计，知识核对当前表达 | 建筑风格、体量与构件选择 |
| C12 | §3 的具体构件数值、§7 的完整案例 | reference；局部示意与案例 | 未作为本次设计的用户要求；不能提升为默认尺寸、固定配色或数量 | rejected：不整篇复制入库；本次没有新增案例索引 | 本次方案自行选择 |

新增 `design_intent` 的六个字段是本次项目的设计数据契约，用于公开的设计结论、假设与节点交接，不声称来自资料的原始 WILD 字段。它不生成房间平面、网格或专业验算结果，因此不修改两份 WILD schema。

本次活动知识落位：新增 `knowledge/components/architecture-design-expression.md`，重写 `massing-composition-rules.md` 与 `massing-layers.md`；同步 `config.yaml` 的 required_documents。体量数量、退台、对称、屋型、构件套餐与配色均保留给本次设计选择。
