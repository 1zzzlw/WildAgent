---
entity_name: extended_residential_types
topic: composition
status: supported
authority: maintainer
source: building_types/residential/extended-residential-types.md
building_category: residential
primary_terms:
  - 扩展居住建筑
synonyms: []
applies_to:
  - 扩展居住建筑
---

# 扩展居住建筑：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 联排别墅

<!-- rag-meta
entity_type: building
entity_name: row_house
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 联排别墅
synonyms: []
applies_to:
  - 联排别墅
-->

- 适用条件：用户或已批准方案明确采用联排别墅；名称本身不决定全部构件。
- 类型特征：联排别墅由多个窄面宽、较大进深的低层住宅单元横向连续排列。核心识别特征是重复开间、相邻单元共用山墙、独立前后入口、统一屋顶节奏和可选二层阳台。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：先生成单元 `floor`，再用前后外墙和左右边界 `wall` 围合；相邻单元复用同一条山墙坐标，不生成两面重叠墙。逐层添加楼板、墙体、门窗组件和本层 `stair`，屋盖按本次方案确定；仅在选定双坡语汇时使用连续或分段 `gable`。二层阳台使用 `balcony`，入口雨棚使用 `canopy`，前后院只用低矮 `wall` 与场地平板表达。 WILD 不理解共用山墙的产权和承重语义。车库门只能用矩形 `door` 外观近似；栏杆没有玻璃填充板；烟囱可用 `chimney` 定位在屋面，但不会切开屋顶。生成结果只能证明体量和构件关系可渲染。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 叠拼别墅

<!-- rag-meta
entity_type: building
entity_name: stacked_villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 叠拼别墅
synonyms: []
applies_to:
  - 叠拼别墅
-->

- 适用条件：用户或已批准方案明确采用叠拼别墅；名称本身不决定全部构件。
- 类型特征：叠拼别墅把住宅单元竖向组合在同一建筑体量中。生成时按请求保留“上叠/下叠”的分层入口差异，不能退化成普通单户别墅。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：用各层 `floor` 建立竖向分界，使用连续外壳 `wall`、分户墙和楼梯间表达上下单元。下叠和上叠分别设置逐层 `stair`；下叠入口与上叠入口分别绑定对应楼层外墙。小型墙挂悬挑平台使用 `balcony`；大面积平屋面露台使用 `floor` 后，只在真实临空边生成独立 `railing`。 当前没有住户、产权单元、隔声等级和公共交通核对象。地下室、承重和分户隔声不能由场景几何证明；阳台不得重复表达为 `balcony + floor + railing`。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 公租房与廉租房

<!-- rag-meta
entity_type: building
entity_name: public_rental_housing
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 公租房与廉租房
synonyms: []
applies_to:
  - 公租房与廉租房
-->

- 适用条件：用户或已批准方案明确采用公租房与廉租房；名称本身不决定全部构件。
- 类型特征：公租房和廉租房的生成语义是紧凑、标准化、经济耐用和重复模数。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用 `wall` 表达外壳、分户墙、楼梯井和电梯井外形，使用 `floor` 表达标准层与走廊，逐层设置 `stair`。门窗按模数重复，但每个开口仍需绑定真实父墙。每户阳台使用单个 `balcony`；单元入口可使用 `canopy` 和 `ramp`。重复标准层可以用合法模板实例复用基础元素。 电梯井只是墙体围合外形，系统不生成可运行电梯。当前不验证住宅单元面积、消防疏散、预制构造、栏杆填充形式或无障碍合规。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 安置房

<!-- rag-meta
entity_type: building
entity_name: resettlement_housing
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 安置房
synonyms: []
applies_to:
  - 安置房
-->

- 适用条件：用户或已批准方案明确采用安置房；名称本身不决定全部构件。
- 类型特征：安置房的外观语义是规则开间、经济材料、重复门窗和多层到高层住宅体量。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：普通层采用 `floor → wall → door/window → stair` 的住宅基线，屋顶根据体量选择 `flat` 或 `gable`。底层商业变体用较高首层墙体、较大的临街开口、`beam` 和柱状 `primitive.box` 表达底部框架外观；上部墙体仍按楼层分段生成。 底层商业与上部住宅之间的转换梁只具有视觉几何，不执行荷载分析。门窗防盗等级、材料耐久性和住宅性能均不属于当前 Schema。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 共有产权房

<!-- rag-meta
entity_type: building
entity_name: shared_ownership_housing
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 共有产权房
synonyms: []
applies_to:
  - 共有产权房
-->

- 适用条件：用户或已批准方案明确采用共有产权房；名称本身不决定全部构件。
- 类型特征：共有产权房采用标准层住宅语义，体量通常规整，立面以重复开间、统一门窗和数量受控的阳台形成节奏。产权属性不转化为 WILD 字段。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：用外墙、核心筒外形、标准层楼板和逐层楼梯建立主体；门窗组件按明确立面槽位生成。阳台使用单个 `balcony`，入口使用 `canopy`，需要坡面时使用 `ramp`。 系统不表达产权比例、住房政策、真实电梯和住宅规范校核；只能生成可渲染的标准层建筑外观与空间骨架。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 商务公寓

<!-- rag-meta
entity_type: building
entity_name: business_apartment
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 商务公寓
synonyms: []
applies_to:
  - 商务公寓
-->

- 适用条件：用户或已批准方案明确采用商务公寓；名称本身不决定全部构件。
- 类型特征：商务公寓强调居住与办公混合的外观语义、高层高、现代玻璃立面和可选夹层。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用围合 `wall` 表达核心筒外形，外框架使用 `beam` 和柱状 `primitive.box`，标准层使用 `floor`。立面玻璃以大面积 `window` 和细 `primitive` 框架近似；夹层使用中间标高 `floor` 与短 `stair`。入口大雨棚使用 `canopy`。 当前没有真实幕墙系统、办公许可、运营属性或电梯。玻璃材质和重复窗框只形成视觉近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 酒店式公寓

<!-- rag-meta
entity_type: building
entity_name: serviced_apartment
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 酒店式公寓
synonyms: []
applies_to:
  - 酒店式公寓
-->

- 适用条件：用户或已批准方案明确采用酒店式公寓；名称本身不决定全部构件。
- 类型特征：酒店式公寓的识别特征是重复居住单元、集中交通、统一门窗和可选独立阳台。酒店式管理、厨卫设备和运营能力不属于蓝图几何。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：按标准层生成外壳、走廊、单元隔墙、楼板和逐层楼梯，使用门窗组件重复立面节奏。每户阳台使用单个 `balcony`；厨房隔断只用薄墙、开放洞口或 `primitive` 格栅表达，不生成独立 `mullion` 元素。 系统不生成厨卫设备、酒店服务、电梯和客房性能。门窗材质只能近似装修档次。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 青年公寓

<!-- rag-meta
entity_type: building
entity_name: youth_apartment
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 青年公寓
synonyms: []
applies_to:
  - 青年公寓
-->

- 适用条件：用户或已批准方案明确采用青年公寓；名称本身不决定全部构件。
- 类型特征：青年公寓强调紧凑开间、较高层高、可选 LOFT 夹层和共享空间。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：用中间标高 `floor` 表达夹层，用直跑 `stair` 连接；落地采光使用大尺寸 `window`。共享区域可使用 `furniture` 的 `table`、`chair`、`bookshelf`、`bed` 和静态 `lamp`；需要真实照明时另用 `light` 组件。屋顶共享平台使用 `floor` 和仅沿临空边的 `railing`。 当前楼梯仅支持直跑，不能生成旋转楼梯。共享运营、房间面积、消防和屋顶花园植物不属于当前能力。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## Loft 公寓

<!-- rag-meta
entity_type: building
entity_name: loft_apartment
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - Loft 公寓
synonyms: []
applies_to:
  - Loft 公寓
-->

- 适用条件：用户或已批准方案明确采用Loft 公寓；名称本身不决定全部构件。
- 类型特征：Loft 公寓的关键语义是高层高大开间、局部夹层、通高采光和开放空间。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：外壳采用单层高墙体和楼板，夹层使用局部 `floor`，直跑 `stair` 连接夹层。通高立面使用一个或分段的大尺寸 `window`，夹层临空边使用显式路径 `railing`。 夹层只表达几何，不验证结构承载；楼梯不能旋转；栏杆不支持玻璃或网状填充板。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 老年公寓

<!-- rag-meta
entity_type: building
entity_name: senior_apartment
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 老年公寓
synonyms: []
applies_to:
  - 老年公寓
-->

- 适用条件：用户或已批准方案明确采用老年公寓；名称本身不决定全部构件。
- 类型特征：老年公寓的生成意图是低层、宽通道、低窗台、平缓入口和连续扶手。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：用较低标高的 `window` 表达低窗台；入口使用 `ramp`，并根据需要设置 `railingSides`。走廊扶手可用两条不同 `railLevels` 的 `railing` 近似。房门仍用标准 `door`，电梯井只用墙体围合。 系统没有无障碍规范校核、可运行电梯、紧急呼叫设备、圆角墙体处理或卫生间设备。坡道几何通过不等于通行合规。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 农村自建房

<!-- rag-meta
entity_type: building
entity_name: rural_self_built_house
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 农村自建房
synonyms: []
applies_to:
  - 农村自建房
-->

- 适用条件：用户或已批准方案明确采用农村自建房；名称本身不决定全部构件。
- 类型特征：农村自建房可采用 由方案确定的尺度低层住宅，视觉特征是规整砖墙、构造柱或框架外观、双坡屋顶、院墙、大院门和可选厨房烟囱。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用低层住宅基线生成楼板、墙体、门窗、逐层楼梯和 `gable` 屋顶。圆形构造柱可用 `column`，方形构造柱用 `primitive.box`；圈梁用 `beam`。院墙用矮 `wall`，院门用 `door`，厨房烟囱用 `chimney`。 砖混、构造柱和圈梁只有视觉语义，不执行抗震或结构计算。烟囱不会在屋顶创建真实穿孔。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 窑洞

<!-- rag-meta
entity_type: building
entity_name: yaodong_cave_dwelling
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 窑洞
synonyms: []
applies_to:
  - 窑洞
-->

- 适用条件：用户或已批准方案明确采用窑洞；名称本身不决定全部构件。
- 类型特征：窑洞强调厚重土体、重复拱形立面洞口和半地下或靠崖视觉，可分为靠崖式、下沉式和独立式语义。源资料中的竖向拱顶不能直接转换为 `wall.curve`。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用厚 `wall` 与 `arched` 的 `opening` 建立立面，门窗组件继承拱形洞口样式；拱顶和覆土体量使用土色 `primitive` 组合近似。多个窑洞并联时保持开间、拱顶高度和侧墙节奏一致。 `wall.curve` 是 XZ 平面路径，不能生成竖向拱券。当前没有地形 heightmap、覆土布尔和地下空间求解，因此窑洞只能是立面与体量近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 吊脚楼

<!-- rag-meta
entity_type: building
entity_name: diaojiaolou_stilt_house
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 吊脚楼
synonyms: []
applies_to:
  - 吊脚楼
-->

- 适用条件：用户或已批准方案明确采用吊脚楼；名称本身不决定全部构件。
- 类型特征：吊脚楼是依坡架空的木构住宅语义，核心特征是不等高支柱、高位木楼板、轻质围护、前廊和大出檐坡屋顶。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：用不同 `base[1]` 和 `height` 的 `column` 支撑高位 `floor`，用 `beam` 表达穿枋和挑梁，再添加木色 `wall`、门窗、直跑 `stair` 与 `gable` 或 `chinese_curved` 屋顶。前廊使用扩展楼板和显式路径 `railing`。 当前没有真实山坡地形、榫卯节点、竹木材料构造和架空结构安全分析。不同柱底标高只近似地形适配。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 职工宿舍

<!-- rag-meta
entity_type: building
entity_name: worker_dormitory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 职工宿舍
synonyms: []
applies_to:
  - 职工宿舍
-->

- 适用条件：用户或已批准方案明确采用职工宿舍；名称本身不决定全部构件。
- 类型特征：职工宿舍偏向单元式重复房间、连续内廊、独立卫生空间外形和统一阳台节奏。房间人数和卫生设备不是几何字段。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：先生成走廊两侧外墙和隔墙，再按开间重复门窗组件，逐层添加楼板和所需楼梯。每个阳台只用一个 `balcony`；入口使用 `canopy`。 系统不表达住宿人数、独立卫生间设备、隔声和消防性能。重复房间只是墙体与门窗布局。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 校园宿舍

<!-- rag-meta
entity_type: building
entity_name: campus_dormitory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 校园宿舍
synonyms: []
applies_to:
  - 校园宿舍
-->

- 适用条件：用户或已批准方案明确采用校园宿舍；名称本身不决定全部构件。
- 类型特征：校园宿舍以密集重复房间、外廊或内廊、集中卫生空间和建筑两端交通为主要识别特征。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：按统一模数布置隔墙、门和窗，按交通方案设置逐层直跑 `stair`。外廊楼板临空边使用显式路径 `railing`，顶层外廊雨棚使用依附外墙的 `canopy`，无障碍入口外形使用 `ramp`。 栏杆不支持玻璃或竖杆填充枚举；集中卫生设备、住宿人数和疏散合规不在当前能力内。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 军营宿舍

<!-- rag-meta
entity_type: building
entity_name: barracks_dormitory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 军营宿舍
synonyms: []
applies_to:
  - 军营宿舍
-->

- 适用条件：用户或已批准方案明确采用军营宿舍；名称本身不决定全部构件。
- 类型特征：军营宿舍强调标准化营房体量、大房间、统一窗列、集中功能空间和室外集合场地。安全等级和军用功能不转化为 WILD 字段。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用规整楼板、外墙、隔墙、柱梁外观和统一门窗形成营房；按交通方案设置楼梯。集合广场使用大面积 `floor`，营区围墙使用矮 `wall`，大门使用双开 `door` 外观。 系统不表达军械存储、防爆、防盗和营区安全，也不验证房间人数和疏散性能。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 工地临建宿舍

<!-- rag-meta
entity_type: building
entity_name: construction_site_dormitory
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 工地临建宿舍
synonyms: []
applies_to:
  - 工地临建宿舍
-->

- 适用条件：用户或已批准方案明确采用工地临建宿舍；名称本身不决定全部构件。
- 类型特征：工地临建宿舍采用轻型模块化外观，重点是细柱梁、薄围护、重复门窗、二层外廊和室外楼梯。材料名称只表达视觉，不证明可拆装或防火性能。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用细 `beam` 与 `primitive.box` 表达轻钢方管骨架，使用薄 `wall` 和 `floor` 表达夹芯板外形，屋型按本次方案确定，选择双坡时用 `gable`。二层外廊使用楼板和显式路径栏杆，室外交通使用直跑 `stair`。 当前没有单坡屋顶枚举、装配连接节点、夹芯板性能和临建设计校核。材质颜色不能证明耐火、保温或可拆卸。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 民宿

<!-- rag-meta
entity_type: building
entity_name: homestay_guesthouse
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 民宿
synonyms: []
applies_to:
  - 民宿
-->

- 适用条件：用户或已批准方案明确采用民宿；名称本身不决定全部构件。
- 类型特征：民宿强调地域材料、院落、观景开口和不同于标准酒店的低层体量。既有建筑改造只是设计语义，不能据此推断原构件真实状态。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用低层 `floor → wall → door/window → roof` 基线，通过石、砖、木和灰瓦角色材质形成地域差异。L 形或围合体量用多个墙体组组合；公共区使用宽 `window`，观景平台使用 `balcony` 或楼板加真实临空边栏杆，壁炉外形使用 `chimney`。 系统没有既有建筑调查、保护评估、景观植物和民俗装饰资产。地域材料只通过材质参数近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 康养小院

<!-- rag-meta
entity_type: building
entity_name: wellness_courtyard
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 康养小院
synonyms: []
applies_to:
  - 康养小院
-->

- 适用条件：用户或已批准方案明确采用康养小院；名称本身不决定全部构件。
- 类型特征：康养小院强调围绕安静庭院布置的低层体量、连续回廊、低窗台和平缓通行。药草园、康复和疗愈效果属于场景意图，不是可验证的建筑性能。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：用多个低层房屋体量围合庭院，回廊使用 `column`、`beam` 和窄 `floor` 组合；低窗台通过 `window.from[1]` 表达，入口使用 `ramp`。庭院地面使用不同材质的 `floor` 分区，小亭使用柱、梁和小型 `roof`。 当前没有植物、中草药庭院、连续扶手规范校核和康复设计验证。坡道和低窗台只表达几何意图。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 山地旅居住宅

<!-- rag-meta
entity_type: building
entity_name: mountain_travel_residence
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 山地旅居住宅
synonyms: []
applies_to:
  - 山地旅居住宅
-->

- 适用条件：用户或已批准方案明确采用山地旅居住宅；名称本身不决定全部构件。
- 类型特征：山地旅居住宅强调依坡错层、逐层退台、不等高支撑和面向景观的宽开口。
- 条件关系：仅当方案选择下列系统时应用这些组装关系；不把某一变体当作类型默认结果。
- WILD 映射与边界：使用不同标高的 `floor`、不同柱底标高和逐层退后的 `wall` 形成错台；观景面使用宽 `window`。小型悬挑观景台使用 `balcony`，大退台平台使用 `floor` 并只在临空边生成 `railing`；外部交通使用逐层直跑 `stair`。 当前没有山地 heightmap、挡土结构分析、边坡稳定和结构抗滑计算。错台楼板与不等高柱只是确定性视觉近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
