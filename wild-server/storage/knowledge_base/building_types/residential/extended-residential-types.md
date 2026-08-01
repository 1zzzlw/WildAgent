---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: extended_residential_building_family
topic: definition
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/residential/extended-residential-types.md
keywords:
  - 居住建筑
  - residential building
  - 联排别墅
  - 叠拼别墅
  - 保障性住房
  - 公寓
  - 乡土民居
  - 宿舍
  - 民宿
---

# 居住建筑扩展类型：描述词、构件意图与当前引擎降级

> 来源资料：用户提供的《WILD蓝图AI描述词与构件组合规则_居住建筑.md》；原始文件保持不变。
> 用途：补充现有知识库尚未详细覆盖的居住建筑类型，并把领域描述转换成 WILD v1.1 当前能力可表达的组合意图。
> 本文不复制原文中的伪蓝图指令；尺寸只作为来源建议，不是结构设计、消防、无障碍或合规结论。

## 居住建筑扩展规则的引擎适配总则

<!-- rag-meta
entity_type: building
entity_name: residential_engine_adaptation_rules
topic: constraints
status: supported
authority: engine
keywords: 居住建筑降级, residential fallback, WILD v1.1, opening, primitive
-->

当前正式元素类型以引擎注册表为准。居住建筑外壳优先使用 `floor`、`wall`、`opening`、`roof`，骨架使用 `column`、`beam`，层间交通使用 `stair`，特殊静态外形使用 `primitive`。门窗都先表达为引用 `parentWall` 的 `opening`；需要门扇、窗框、格栅、栏杆、雨棚、烟囱或坡道外观时，用 `primitive`、`beam`、`column` 组合近似，不能输出不存在的专用类型。

原文中的 `terrain`、`door`、`window`、`mullion`、`railing`、`ramp`、`canopy`、`chimney` 和 `cornice` 均不能写入当前 `geometry.elements`。`column` 只有圆形参数化柱，方柱改用 `primitive.shape: box`；`roof` 用 `height` 表达起坡高度，不使用不存在的 `slope` 字段；`floor.autoRailing`、`stair.autoRailing` 也不是当前字段。涉及电梯、消防、无障碍、挡土、隔声、防爆或设备工艺时，只能表达空间外形，不得声称完成专业设计。

## 联排别墅

<!-- rag-meta
entity_type: building
entity_name: row_house
topic: definition
status: experimental
authority: domain_reference
keywords: 联排别墅, row house, townhouse, 共用山墙, 前后院
-->

联排别墅是多个窄面宽、较大进深的低层住宅单元沿横向连续排列，视觉关键词是重复开间、共用山墙、独立前后入口、统一坡屋顶节奏和可选阳台。来源资料建议单元约 2～4 层、面宽约 6～9m、进深约 10～15m；这些范围只用于体量初始化，不能替代当地规范和结构计算。

### 联排别墅的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: row_house
topic: assembly
status: experimental
authority: maintainer
keywords: 联排别墅组合, row house assembly, wall, floor, opening, roof
-->

先为单元生成 `floor`，再用连续的 `wall` 表达左右山墙和前后围护；逐层添加 `floor`、本层 `wall` 与引用外墙的 `opening`，用 `stair` 连接相邻标高，最后用一个连续 `gable` 屋顶或各单元独立 `gable` 屋顶形成重复节奏。阳台使用悬挑 `floor`，栏杆用细 `primitive box` 或 `beam` 显式排列。需要批量复制单元时使用合法的 `geometry.templates` 字典和带 `ref` 的 `geometry.instances`，不要沿用原文中的数组式模板伪语法。

### 联排别墅的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: row_house
topic: constraints
status: supported
authority: engine
keywords: 联排别墅降级, shared wall, balcony fallback, primitive
-->

当前引擎不会理解“共用山墙”的产权或结构语义，只会渲染输入墙体；相邻单元应复用同一条边界墙坐标，避免生成两面重叠墙。车库门、院门和住宅门均先用 `opening` 表达，门扇外观用 `primitive` 近似。玻璃栏杆、屋面烟囱和入口雨棚没有自动 resolver，必须显式组合或省略，且不能使用 `autoRailing`、`penetrateRoof`、`parentOpening` 等未支持字段。

## 叠拼别墅

<!-- rag-meta
entity_type: building
entity_name: stacked_villa
topic: definition
status: experimental
authority: domain_reference
keywords: 叠拼别墅, stacked villa, 上叠, 下叠, 露台
-->

叠拼别墅把多个住宅单元竖向组合在同一建筑体量中。描述词应突出下叠庭院和落地洞口、上叠露台、分层入户、竖向分户与多层平台，而不是把它误解为普通单户别墅。来源资料使用约 4～5 层作为示意体量；实际层数、分户和疏散要求需要独立确认。
召回该实体时应同时保留“上叠”和“下叠”关键词，避免只生成普通多层住宅外壳。

### 叠拼别墅的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: stacked_villa
topic: assembly
status: experimental
authority: maintainer
keywords: 叠拼别墅组合, stacked villa assembly, floor, wall, stair, opening
-->

以 `floor` 建立各层和上下户分界，用 `wall` 表达连续外壳、分户墙和楼梯间，用 `opening` 区分下叠庭院入口、上叠公共入口和各层采光洞口。下叠与上叠分别设置 `stair`，避免用一条跨越多个楼层的楼梯代替真实层间关系。上叠露台使用独立 `floor`，四周防护外观用 `primitive` 或 `beam` 逐段搭建；屋顶只选择当前支持的 `flat`、`gable` 或 `hip`。

### 叠拼别墅的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: stacked_villa
topic: constraints
status: supported
authority: engine
keywords: 叠拼别墅降级, dwelling unit, terrace fallback, WILD
-->

WILD 当前没有户、产权单元、隔声等级和公共交通核的业务对象，墙和楼板只表达几何。露台防护不能写成 `floor.autoRailing`，门窗不能拆成 `door`、`window` 元素。来源资料中的地下室、结构承重和分户隔声均不能由当前渲染结果证明；生成结果必须标注为体量与构件组合近似。

## 保障性住房

<!-- rag-meta
entity_type: building
entity_name: affordable_housing
topic: definition
status: experimental
authority: domain_reference
keywords: 保障性住房, affordable housing, 公租房, 廉租房, 安置房, 共有产权房
-->

保障性住房的描述重点是紧凑、标准化、经济耐用和重复模数，可覆盖公租房、廉租房、安置房与共有产权房等用户名称。外观通常采用规整门窗、简洁墙面、重复阳台或走廊节奏。来源文档中的层数、走廊宽度和无障碍尺寸不作为强制规范写入；生成前应由用户或有效规范确定规模。

### 保障性住房的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: affordable_housing
topic: assembly
status: experimental
authority: maintainer
keywords: 保障房组合, affordable housing assembly, templates, instances, multi storey
-->

采用多层建筑基线：用 `wall` 围合外壳、分户和楼梯井，用 `floor` 建立标准层与走廊，用 `opening` 重复门窗洞口，用逐层 `stair` 连接相邻楼板，最后使用 `flat` 或 `gable` 屋顶。重复标准层可以通过 `geometry.templates` 和 `geometry.instances` 减少冗余，但每个实例必须使用 `ref` 指向单个合法元素模板；如果一个住宅单元包含多个元素，应分别建模板并以相同偏移实例化。

### 保障性住房的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: affordable_housing
topic: constraints
status: supported
authority: engine
keywords: 保障房降级, elevator fallback, corridor, WILD constraints
-->

当前没有电梯、管井设备、预制叠合板、消防分区、避难层或住宅单元语义。可以用 `wall` 表达电梯井和管井外壳，但不能声称电梯可运行。重复阳台的栏杆需显式使用受支持构件近似；防盗门、推拉窗和玻璃栏板只是视觉需求，不是可直接写入的 `type` 或枚举。

## 公寓系列

<!-- rag-meta
entity_type: building
entity_name: apartment_family
topic: definition
status: experimental
authority: domain_reference
keywords: 公寓, apartment, 商务公寓, 酒店式公寓, 青年公寓, Loft, 老年公寓
-->

公寓系列包含不同使用侧重点：商务公寓强调办公居住混合和现代玻璃立面；酒店式公寓强调重复客房单元；青年或 Loft 公寓强调较高层高、夹层和共享空间；老年公寓强调低层、连续通行和低窗台等无障碍意图。这些描述词帮助选择体量和立面，不等于旅馆经营、办公许可或无障碍合规结论。

### 公寓系列的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: apartment_family
topic: assembly
status: experimental
authority: maintainer
keywords: 公寓组合, apartment assembly, loft, opening, stair, furniture
-->

公寓主体使用 `wall`、`floor`、`opening` 和逐层 `stair`；核心筒仅以围合 `wall` 表达。商务公寓可用玻璃材质的 `opening` 平面和细 `primitive` 框架近似幕墙；Loft 用中间标高的 `floor` 表达夹层，并用短 `stair` 连接。公共空间可使用 `furniture` 的 `table`、`chair`、`bed`、`lamp` 等当前支持子类型，原文“禁用 table/chair”的说法与当前引擎不一致，不应保留。

### 公寓系列的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: apartment_family
topic: constraints
status: supported
authority: engine
keywords: 公寓降级, curtain wall fallback, accessible design, furniture
-->

当前没有电梯、旋转楼梯、推拉门、卫生间设备、双层扶手、紧急呼叫按钮和真实幕墙系统。老年公寓的通行、坡度和扶手要求只能记录为用户意图；用 `primitive` 近似坡面或扶手并不能证明无障碍合规。窗扇类型、开启方式和 Low-E 性能不属于 `opening` 当前字段。

## 乡土民居系列

<!-- rag-meta
entity_type: building
entity_name: vernacular_residence_family
topic: definition
status: experimental
authority: domain_reference
keywords: 乡土民居, vernacular residence, 农村自建房, 农家宅院, 窑洞, 吊脚楼
-->

乡土民居系列包括农村自建房、农家宅院、窑洞和吊脚楼。农村自建房通常表现为砖墙、规整坡顶和院墙；农家宅院强调正房、厢房与院落围合；窑洞强调厚重土体、拱形立面洞口和半地下感；吊脚楼强调依坡架空、木柱梁、前廊和大出檐。农家宅院的轻量默认语义已在 `catalog/courtyards.md`，本文不重复其详细院落配方。

### 乡土民居的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: vernacular_residence_family
topic: assembly
status: experimental
authority: maintainer
keywords: 乡土民居组合, vernacular assembly, arched opening, stepped floor, column
-->

农村住宅可直接采用低层 `floor → wall → opening → stair → roof` 基线。院落由多个低层房屋体量与围合 `wall` 组成。窑洞只做立面和体量近似：用厚 `wall`、`arched` 的 `opening` 与覆盖其上的 `primitive` 或土色体块表达拱洞观感。吊脚楼用不同 `base[1]` 和 `height` 的圆形 `column` 支撑高位 `floor`，再添加 `beam`、木色 `wall`、`opening` 与 `chinese_curved` 或 `gable` 屋顶。

### 乡土民居的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: vernacular_residence_family
topic: constraints
status: supported
authority: engine
keywords: 窑洞降级, 吊脚楼降级, terrain fallback, catenary
-->

`wall.curve` 描述墙在 XZ 平面中的路径，不能把 `catenary` 当成竖向窑洞拱顶布尔体；`arched opening` 只能裁切父墙。当前没有山坡 `terrain`、悬柱装饰、竹篾墙或真实覆土系统，坡地只能通过错台 `floor`、不同柱底标高和背景体块近似。曲面屋顶能力为 partial，生成后仍需检查包围盒和构件穿插。

## 集体宿舍变体

<!-- rag-meta
entity_type: building
entity_name: dormitory_variants
topic: definition
status: experimental
authority: domain_reference
keywords: 宿舍, dormitory, 职工宿舍, 校园宿舍, 军营宿舍, 工地临建宿舍
-->

集体宿舍的共同描述词是重复房间、连续走廊、集中或独立卫生空间和两端交通。职工宿舍偏单元式与独立卫生间，校园宿舍偏密集房间和公共卫生间，军营宿舍偏大房间与标准化营房，工地临建宿舍偏轻型模块和快速装配。现有 `housing-dormitories-hotels.md` 提供通用宿舍入口，本文只补充变体差异。

### 集体宿舍变体的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: dormitory_variants
topic: assembly
status: experimental
authority: maintainer
keywords: 宿舍组合, dormitory assembly, repeated rooms, corridor, opening
-->

先用外墙和走廊两侧 `wall` 建立重复开间，再用较薄 `wall` 分隔房间与卫生空间，用 `floor` 建立楼层和走廊，用 `opening` 按相同间距布置门窗洞口，并在建筑两端设置逐层 `stair`。工地临建可用细 `beam` 与 `primitive box` 模拟轻型方管骨架，围护仍用薄 `wall`；屋面选择受支持的 `gable` 或 `flat`，不输出未支持的单坡屋顶枚举。

### 集体宿舍变体的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: dormitory_variants
topic: constraints
status: supported
authority: engine
keywords: 宿舍降级, bathroom equipment, railing fallback, temporary building
-->

当前 WILD 不表达房间人数、隔声分贝、洁具、防水构造、军械存储安全或临时结构连接节点。外廊栏杆和雨棚需要用 `primitive`、`beam`、`column` 显式近似，门窗开启方式不受支持。工地临建的材料名只控制视觉参数，不能证明夹芯板耐火、保温或可拆装性能。

## 旅居度假居住系列

<!-- rag-meta
entity_type: building
entity_name: travel_residence_family
topic: definition
status: experimental
authority: domain_reference
keywords: 旅居住宅, travel residence, 度假木屋, 民宿, 康养小院, 山地旅居住宅
-->

旅居度假系列包括度假木屋、民宿、康养小院和山地旅居住宅。度假木屋强调木材、陡坡屋顶、观景洞口和前廊，其默认入口已在 `catalog/cabins.md`；民宿强调地域材料、庭院和观景窗；康养小院强调围绕庭院的安静低层体量与连续通行意图；山地旅居住宅强调错台、退台、不同标高支撑和面向景观的宽洞口。

### 旅居度假居住的当前 WILD 组合基线

<!-- rag-meta
entity_type: building
entity_name: travel_residence_family
topic: assembly
status: experimental
authority: maintainer
keywords: 旅居住宅组合, cabin, homestay, stepped residence, primitive
-->

木屋和民宿使用低层建筑基线，并通过木、石、灰瓦等角色独立材质形成差异；观景面使用较宽的 `opening`。康养小院用多个低层房屋体量围合庭院，回廊以 `column`、`beam`、`floor` 组合。山地住宅不生成虚构地形类型，而是用不同标高的 `floor`、不同柱底标高与逐层退后的墙体形成错台；露台防护和烟囱外形使用显式 `primitive`。

### 旅居度假居住的当前能力降级

<!-- rag-meta
entity_type: building
entity_name: travel_residence_family
topic: constraints
status: supported
authority: engine
keywords: 旅居住宅降级, terrain fallback, accessibility, retaining wall
-->

当前没有坡地 heightmap、水景、植物、中草药庭院、挡土结构分析、烟囱穿屋顶布尔、坡道或连续扶手。山地和康养场景只能表达可验证的建筑体量与静态近似构件，不能声称完成边坡稳定、无障碍或康复设计。民宿的“保留老建筑”也只是描述意图，系统没有既有构件调查和保护评估能力。

## 已去重的居住建筑知识路由

<!-- rag-meta
entity_type: building
entity_name: residential_deduplication_routes
topic: constraints
status: supported
authority: maintainer
keywords: 居住建筑去重, residential routing, villa, housing, cabin, courtyard
-->

现代别墅、中式传统别墅和新中式别墅继续以 `residential/villas.md` 为详细来源；普通多层、高层住宅和通用宿舍继续使用 `residential/housing-dormitories-hotels.md`；度假木屋的轻量默认入口使用 `catalog/cabins.md`，农家宅院使用 `catalog/courtyards.md`。本文不重复这些文件的尺寸表和构件表，避免同一实体在向量召回中产生竞争性副本；当前引擎边界始终以 `components/engine-capability-boundaries.md` 为准。
