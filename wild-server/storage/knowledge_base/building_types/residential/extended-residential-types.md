---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
building_category: mixed_use
entity_name: extended_residential_building_types
topic: definition
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/residential/extended-residential-types.md
keywords:
  - 居住建筑
  - residential building
  - 联排别墅
  - 保障性住房
  - 公寓
  - 乡土民居
  - 宿舍
  - 旅居住宅
---

# 居住建筑扩展类型与 WILD 1.1 生成规则

> 来源资料：用户提供的《建筑类型分类体系_1.1_居住建筑_蓝图整合版.md》；源文件保持不变。
> 本文只整合建筑类型语义、体量特征和当前引擎可表达的组合关系。源文档中的旧版 `wal/elements` 蓝图没有直接入库；尺寸是体量初始化建议，不是结构、消防、无障碍或法规合规结论。

## 居住建筑源资料的引擎适配总则

<!-- rag-meta
entity_type: building
entity_name: residential_engine_adaptation_rules
topic: constraints
status: supported
authority: engine
keywords: 居住建筑降级, residential fallback, WILD v1.1, geometry.components, balcony
-->

正式基础元素以引擎注册表为准。居住建筑外壳优先使用 `floor`、`wall`、`roof` 和 `opening`，骨架使用 `column`、`beam`，层间交通使用 `stair`，简化静态细部使用 `primitive`。门、窗、栏杆、雨棚、阳台、坡道、凸窗、檐口和烟囱写入 `geometry.components`，不得继续写成 `geometry.elements`。

源资料中的 `terrain`、独立 `mullion` 和独立 `placement` 不是当前元素类型。平整场地用 `floor` 或 `primitive.box` 近似；窗棂使用 `window.verticalMullions` 与 `horizontalMullions`；批量贴附使用合法的 `geometry.templates`、`geometry.instances` 或 `geometry.placements`。方柱没有专用 `column.crossSection`，需要方形截面时使用 `primitive.shape: box`。屋顶坡度由 `roof.height`、`span` 和 `depth` 形成，不使用 `slope`。`floor.autoRailing` 与 `stair.autoRailing` 均不存在。

阳台必须使用单个 `balcony` 组件：它已经生成悬挑板和 U 形栏杆，不能再为同一阳台添加独立 `floor` 或 `railing`。普通栏杆只生成立柱和横杆，不支持源资料中的 `infill=glass/mesh/vertical_bar` 枚举。雨棚、坡道、檐口和烟囱虽已支持组件化，但不进行结构安全、连续防水、屋顶布尔穿透或无障碍规范校核。

## 联排别墅

<!-- rag-meta
entity_type: building
entity_name: row_house
topic: assembly
status: experimental
authority: maintainer
keywords: 联排别墅, row house, townhouse, 共用山墙, 前后院
-->

联排别墅由多个窄面宽、较大进深的低层住宅单元横向连续排列。核心识别特征是重复开间、相邻单元共用山墙、独立前后入口、统一屋顶节奏和可选二层阳台。来源资料建议 2～4 层、单元面宽约 6～9m、进深约 10～15m，只用于方案初始化。

**联排别墅的当前 WILD 组合：** 先生成单元 `floor`，再用前后外墙和左右边界 `wall` 围合；相邻单元复用同一条山墙坐标，不生成两面重叠墙。逐层添加楼板、墙体、门窗组件和本层 `stair`，最后使用连续 `gable` 屋顶或多个同节奏 `gable` 屋顶。二层阳台使用 `balcony`，入口雨棚使用 `canopy`，前后院只用低矮 `wall` 与场地平板表达。

**联排别墅的能力边界：** WILD 不理解共用山墙的产权和承重语义。车库门只能用矩形 `door` 外观近似；栏杆没有玻璃填充板；烟囱可用 `chimney` 定位在屋面，但不会切开屋顶。生成结果只能证明体量和构件关系可渲染。

## 叠拼别墅

<!-- rag-meta
entity_type: building
entity_name: stacked_villa
topic: assembly
status: experimental
authority: maintainer
keywords: 叠拼别墅, stacked villa, 上叠, 下叠, 露台
-->

叠拼别墅把住宅单元竖向组合在同一建筑体量中。下叠通常强调独立庭院和低层落地开口，上叠强调独立入户、露台和多层平台；来源资料用约 4～5 层作为示意体量。生成时必须保留“上叠/下叠”的分层入口差异，不能退化成普通单户别墅。

**叠拼别墅的当前 WILD 组合：** 用各层 `floor` 建立竖向分界，使用连续外壳 `wall`、分户墙和楼梯间表达上下单元。下叠和上叠分别设置逐层 `stair`；下叠入口与上叠入口分别绑定对应楼层外墙。上叠露台或悬挑平台优先使用 `balcony`；大面积平屋面露台使用 `floor` 后，只在真实临空边生成独立 `railing`。

**叠拼别墅的能力边界：** 当前没有住户、产权单元、隔声等级和公共交通核对象。地下室、承重和分户隔声不能由场景几何证明；阳台不得重复表达为 `balcony + floor + railing`。

## 公租房与廉租房

<!-- rag-meta
entity_type: building
entity_name: public_rental_housing
topic: assembly
status: experimental
authority: maintainer
keywords: 公租房, 廉租房, public rental housing, 标准化开间, 内廊
-->

公租房和廉租房的生成语义是紧凑、标准化、经济耐用和重复模数。立面应使用规整门窗、简洁墙面、连续走廊节奏和数量受控的阳台；来源资料中的层数和规范尺寸只作为参考，不自动成为合规结论。

**公租房与廉租房的当前 WILD 组合：** 使用 `wall` 表达外壳、分户墙、楼梯井和电梯井外形，使用 `floor` 表达标准层与走廊，逐层设置 `stair`。门窗按模数重复，但每个开口仍需绑定真实父墙。每户阳台使用单个 `balcony`；单元入口可使用 `canopy` 和 `ramp`。重复标准层可以用合法模板实例复用基础元素。

**公租房与廉租房的能力边界：** 电梯井只是墙体围合外形，系统不生成可运行电梯。当前不验证住宅单元面积、消防疏散、预制构造、栏杆填充形式或无障碍合规。

## 安置房

<!-- rag-meta
entity_type: building
entity_name: resettlement_housing
topic: assembly
status: experimental
authority: maintainer
keywords: 安置房, resettlement housing, 多层住宅, 底层商铺
-->

安置房的外观语义是规则开间、经济材料、重复门窗和多层到高层住宅体量。来源资料还给出带底层沿街商业的变体；该变体应表现首层层高和柱网变化，而不是声称已完成结构转换设计。

**安置房的当前 WILD 组合：** 普通层采用 `floor → wall → door/window → stair` 的住宅基线，屋顶根据体量选择 `flat` 或 `gable`。底层商业变体用较高首层墙体、较大的临街开口、`beam` 和柱状 `primitive.box` 表达底部框架外观；上部墙体仍按楼层分段生成。

**安置房的能力边界：** 底层商业与上部住宅之间的转换梁只具有视觉几何，不执行荷载分析。门窗防盗等级、材料耐久性和住宅性能均不属于当前 Schema。

## 共有产权房

<!-- rag-meta
entity_type: building
entity_name: shared_ownership_housing
topic: assembly
status: experimental
authority: maintainer
keywords: 共有产权房, shared ownership housing, 标准层, 规整立面
-->

共有产权房采用标准层住宅语义，体量通常规整，立面以重复开间、统一门窗和数量受控的阳台形成节奏。产权属性不转化为 WILD 字段。

**共有产权房的当前 WILD 组合：** 用外墙、核心筒外形、标准层楼板和逐层楼梯建立主体；门窗组件按明确立面槽位生成。阳台使用单个 `balcony`，入口使用 `canopy`，需要坡面时使用 `ramp`。

**共有产权房的能力边界：** 系统不表达产权比例、住房政策、真实电梯和住宅规范校核；只能生成可渲染的标准层建筑外观与空间骨架。

## 商务公寓

<!-- rag-meta
entity_type: building
entity_name: business_apartment
topic: assembly
status: experimental
authority: maintainer
keywords: 商务公寓, business apartment, 高层高, 玻璃立面, LOFT
-->

商务公寓强调居住与办公混合的外观语义、高层高、现代玻璃立面和可选夹层。来源资料建议层高约 3.6～4.5m，仅用于体量初始化。

**商务公寓的当前 WILD 组合：** 使用围合 `wall` 表达核心筒外形，外框架使用 `beam` 和柱状 `primitive.box`，标准层使用 `floor`。立面玻璃以大面积 `window` 和细 `primitive` 框架近似；夹层使用中间标高 `floor` 与短 `stair`。入口大雨棚使用 `canopy`。

**商务公寓的能力边界：** 当前没有真实幕墙系统、办公许可、运营属性或电梯。玻璃材质和重复窗框只形成视觉近似。

## 酒店式公寓

<!-- rag-meta
entity_type: building
entity_name: serviced_apartment
topic: assembly
status: experimental
authority: maintainer
keywords: 酒店式公寓, serviced apartment, 重复客房, 独立厨卫
-->

酒店式公寓的识别特征是重复居住单元、集中交通、统一门窗和可选独立阳台。酒店式管理、厨卫设备和运营能力不属于蓝图几何。

**酒店式公寓的当前 WILD 组合：** 按标准层生成外壳、走廊、单元隔墙、楼板和逐层楼梯，使用门窗组件重复立面节奏。每户阳台使用单个 `balcony`；厨房隔断只用薄墙、开放洞口或 `primitive` 格栅表达，不生成独立 `mullion` 元素。

**酒店式公寓的能力边界：** 系统不生成厨卫设备、酒店服务、电梯和客房性能。门窗材质只能近似装修档次。

## 青年公寓

<!-- rag-meta
entity_type: building
entity_name: youth_apartment
topic: assembly
status: experimental
authority: maintainer
keywords: 青年公寓, youth apartment, 紧凑型, LOFT, 共享空间
-->

青年公寓强调紧凑开间、较高层高、可选 LOFT 夹层和共享空间。来源资料给出约 3.9～4.5m 层高作为示意；共享空间应通过家具和开放体量表达。

**青年公寓的当前 WILD 组合：** 用中间标高 `floor` 表达夹层，用直跑 `stair` 连接；落地采光使用大尺寸 `window`。共享区域可使用 `furniture` 的 `table`、`chair`、`bookshelf`、`bed` 和静态 `lamp`；需要真实照明时另用 `light` 组件。屋顶共享平台使用 `floor` 和仅沿临空边的 `railing`。

**青年公寓的能力边界：** 当前楼梯仅支持直跑，不能生成旋转楼梯。共享运营、房间面积、消防和屋顶花园植物不属于当前能力。

## Loft 公寓

<!-- rag-meta
entity_type: building
entity_name: loft_apartment
topic: assembly
status: experimental
authority: maintainer
keywords: Loft 公寓, loft apartment, 高层高, 夹层, 通高窗
-->

Loft 公寓的关键语义是高层高大开间、局部夹层、通高采光和开放空间。来源资料建议约 4.5～5.4m 层高，夹层只占局部平面，不应错误覆盖整个挑空区。

**Loft 公寓的当前 WILD 组合：** 外壳采用单层高墙体和楼板，夹层使用局部 `floor`，直跑 `stair` 连接夹层。通高立面使用一个或分段的大尺寸 `window`，夹层临空边使用显式路径 `railing`。

**Loft 公寓的能力边界：** 夹层只表达几何，不验证结构承载；楼梯不能旋转；栏杆不支持玻璃或网状填充板。

## 老年公寓

<!-- rag-meta
entity_type: building
entity_name: senior_apartment
topic: assembly
status: experimental
authority: maintainer
keywords: 老年公寓, senior apartment, 无障碍意图, 低窗台, 连续扶手
-->

老年公寓的生成意图是低层、宽通道、低窗台、平缓入口和连续扶手。来源资料中的门宽、坡度、楼层限制和电梯要求只能作为待确认设计输入，不能由渲染结果证明合规。

**老年公寓的当前 WILD 组合：** 用较低标高的 `window` 表达低窗台；入口使用 `ramp`，并根据需要设置 `railingSides`。走廊扶手可用两条不同 `railLevels` 的 `railing` 近似。房门仍用标准 `door`，电梯井只用墙体围合。

**老年公寓的能力边界：** 系统没有无障碍规范校核、可运行电梯、紧急呼叫设备、圆角墙体处理或卫生间设备。坡道几何通过不等于通行合规。

## 农村自建房

<!-- rag-meta
entity_type: building
entity_name: rural_self_built_house
topic: assembly
status: experimental
authority: maintainer
keywords: 农村自建房, rural self-built house, 砖混, 坡屋顶, 院墙
-->

农村自建房通常为 1～3 层低层住宅，视觉特征是规整砖墙、构造柱或框架外观、双坡屋顶、院墙、大院门和可选厨房烟囱。

**农村自建房的当前 WILD 组合：** 使用低层住宅基线生成楼板、墙体、门窗、逐层楼梯和 `gable` 屋顶。圆形构造柱可用 `column`，方形构造柱用 `primitive.box`；圈梁用 `beam`。院墙用矮 `wall`，院门用 `door`，厨房烟囱用 `chimney`。

**农村自建房的能力边界：** 砖混、构造柱和圈梁只有视觉语义，不执行抗震或结构计算。烟囱不会在屋顶创建真实穿孔。

## 窑洞

<!-- rag-meta
entity_type: building
entity_name: yaodong_cave_dwelling
topic: assembly
status: experimental
authority: maintainer
keywords: 窑洞, yaodong, cave dwelling, 拱形洞口, 厚土墙
-->

窑洞强调厚重土体、重复拱形立面洞口和半地下或靠崖视觉，可分为靠崖式、下沉式和独立式语义。源资料中的竖向拱顶不能直接转换为 `wall.curve`。

**窑洞的当前 WILD 组合：** 使用厚 `wall` 与 `arched` 的 `opening` 建立立面，门窗组件继承拱形洞口样式；拱顶和覆土体量使用土色 `primitive` 组合近似。多个窑洞并联时保持开间、拱顶高度和侧墙节奏一致。

**窑洞的能力边界：** `wall.curve` 是 XZ 平面路径，不能生成竖向拱券。当前没有地形 heightmap、覆土布尔和地下空间求解，因此窑洞只能是立面与体量近似。

## 吊脚楼

<!-- rag-meta
entity_type: building
entity_name: diaojiaolou_stilt_house
topic: assembly
status: experimental
authority: maintainer
keywords: 吊脚楼, diaojiaolou, stilt house, 干栏式, 穿斗木构架
-->

吊脚楼是依坡架空的木构住宅语义，核心特征是不等高支柱、高位木楼板、轻质围护、前廊和大出檐坡屋顶。

**吊脚楼的当前 WILD 组合：** 用不同 `base[1]` 和 `height` 的 `column` 支撑高位 `floor`，用 `beam` 表达穿枋和挑梁，再添加木色 `wall`、门窗、直跑 `stair` 与 `gable` 或 `chinese_curved` 屋顶。前廊使用扩展楼板和显式路径 `railing`。

**吊脚楼的能力边界：** 当前没有真实山坡地形、榫卯节点、竹木材料构造和架空结构安全分析。不同柱底标高只近似地形适配。

## 职工宿舍

<!-- rag-meta
entity_type: building
entity_name: worker_dormitory
topic: assembly
status: experimental
authority: maintainer
keywords: 职工宿舍, worker dormitory, 单元式, 独立卫生间, 内廊
-->

职工宿舍偏向单元式重复房间、连续内廊、独立卫生空间外形和统一阳台节奏。房间人数和卫生设备不是几何字段。

**职工宿舍的当前 WILD 组合：** 先生成走廊两侧外墙和隔墙，再按开间重复门窗组件，逐层添加楼板和两端楼梯。每个阳台只用一个 `balcony`；入口使用 `canopy`。

**职工宿舍的能力边界：** 系统不表达住宿人数、独立卫生间设备、隔声和消防性能。重复房间只是墙体与门窗布局。

## 校园宿舍

<!-- rag-meta
entity_type: building
entity_name: campus_dormitory
topic: assembly
status: experimental
authority: maintainer
keywords: 校园宿舍, campus dormitory, 外廊式, 内廊式, 密集开间
-->

校园宿舍以密集重复房间、外廊或内廊、集中卫生空间和建筑两端交通为主要识别特征。来源资料建议开间和层数只作为示意。

**校园宿舍的当前 WILD 组合：** 按统一模数布置隔墙、门和窗，两端设置逐层直跑 `stair`。外廊楼板临空边使用显式路径 `railing`，顶层外廊雨棚使用依附外墙的 `canopy`，无障碍入口外形使用 `ramp`。

**校园宿舍的能力边界：** 栏杆不支持玻璃或竖杆填充枚举；集中卫生设备、住宿人数和疏散合规不在当前能力内。

## 军营宿舍

<!-- rag-meta
entity_type: building
entity_name: barracks_dormitory
topic: assembly
status: experimental
authority: maintainer
keywords: 军营宿舍, barracks, 营房式, 标准开间, 集合广场
-->

军营宿舍强调标准化营房体量、大房间、统一窗列、集中功能空间和室外集合场地。安全等级和军用功能不转化为 WILD 字段。

**军营宿舍的当前 WILD 组合：** 使用规整楼板、外墙、隔墙、柱梁外观和统一门窗形成营房；两端设置楼梯。集合广场使用大面积 `floor`，营区围墙使用矮 `wall`，大门使用双开 `door` 外观。

**军营宿舍的能力边界：** 系统不表达军械存储、防爆、防盗和营区安全，也不验证房间人数和疏散性能。

## 工地临建宿舍

<!-- rag-meta
entity_type: building
entity_name: construction_site_dormitory
topic: assembly
status: experimental
authority: maintainer
keywords: 工地临建宿舍, construction dormitory, 活动板房, 轻钢, 外廊
-->

工地临建宿舍采用轻型模块化外观，重点是细柱梁、薄围护、重复门窗、二层外廊和室外楼梯。材料名称只表达视觉，不证明可拆装或防火性能。

**工地临建宿舍的当前 WILD 组合：** 使用细 `beam` 与 `primitive.box` 表达轻钢方管骨架，使用薄 `wall` 和 `floor` 表达夹芯板外形，屋面选 `gable`。二层外廊使用楼板和显式路径栏杆，室外交通使用直跑 `stair`。

**工地临建宿舍的能力边界：** 当前没有单坡屋顶枚举、装配连接节点、夹芯板性能和临建设计校核。材质颜色不能证明耐火、保温或可拆卸。

## 民宿

<!-- rag-meta
entity_type: building
entity_name: homestay_guesthouse
topic: assembly
status: experimental
authority: maintainer
keywords: 民宿, homestay, guesthouse, 地域材料, 庭院, 观景窗
-->

民宿强调地域材料、院落、观景开口和不同于标准酒店的低层体量。既有建筑改造只是设计语义，不能据此推断原构件真实状态。

**民宿的当前 WILD 组合：** 使用低层 `floor → wall → door/window → roof` 基线，通过石、砖、木和灰瓦角色材质形成地域差异。L 形或围合体量用多个墙体组组合；公共区使用宽 `window`，观景平台使用 `balcony` 或楼板加真实临空边栏杆，壁炉外形使用 `chimney`。

**民宿的能力边界：** 系统没有既有建筑调查、保护评估、景观植物和民俗装饰资产。地域材料只通过材质参数近似。

## 康养小院

<!-- rag-meta
entity_type: building
entity_name: wellness_courtyard
topic: assembly
status: experimental
authority: maintainer
keywords: 康养小院, wellness courtyard, 围合庭院, 回廊, 连续通行
-->

康养小院强调围绕安静庭院布置的低层体量、连续回廊、低窗台和平缓通行。药草园、康复和疗愈效果属于场景意图，不是可验证的建筑性能。

**康养小院的当前 WILD 组合：** 用多个低层房屋体量围合庭院，回廊使用 `column`、`beam` 和窄 `floor` 组合；低窗台通过 `window.from[1]` 表达，入口使用 `ramp`。庭院地面使用不同材质的 `floor` 分区，小亭使用柱、梁和小型 `roof`。

**康养小院的能力边界：** 当前没有植物、中草药庭院、连续扶手规范校核和康复设计验证。坡道和低窗台只表达几何意图。

## 山地旅居住宅

<!-- rag-meta
entity_type: building
entity_name: mountain_travel_residence
topic: assembly
status: experimental
authority: maintainer
keywords: 山地旅居住宅, mountain residence, 错层, 退台, 观景窗
-->

山地旅居住宅强调依坡错层、逐层退台、不等高支撑和面向景观的宽开口。来源资料中的挡土、抗滑和抗倾覆要求不能由 WILD 几何证明。

**山地旅居住宅的当前 WILD 组合：** 使用不同标高的 `floor`、不同柱底标高和逐层退后的 `wall` 形成错台；观景面使用宽 `window`。小型悬挑观景台使用 `balcony`，大退台平台使用 `floor` 并只在临空边生成 `railing`；外部交通使用逐层直跑 `stair`。

**山地旅居住宅的能力边界：** 当前没有山地 heightmap、挡土结构分析、边坡稳定和结构抗滑计算。错台楼板与不等高柱只是确定性视觉近似。

## 已去重的居住建筑知识路由

<!-- rag-meta
entity_type: building
entity_name: residential_deduplication_routes
topic: constraints
status: supported
authority: maintainer
keywords: 居住建筑去重, residential routing, villa, housing, cabin, courtyard
-->

现代别墅、中式传统别墅和新中式别墅继续以 `residential/villas.md` 为详细配方；普通多层和高层住宅继续使用 `residential/housing-dormitories-hotels.md`；农家宅院的轻量入口使用 `catalog/courtyards.md`；度假木屋的轻量入口使用 `catalog/cabins.md`。本文件不复制这些实体的完整配方和 JSON，避免竞争性重复。当前引擎边界以 `components/engine-capability-boundaries.md`、`components/composite-components-second-batch.md`、TypeScript 类型和 Schema 为准。
