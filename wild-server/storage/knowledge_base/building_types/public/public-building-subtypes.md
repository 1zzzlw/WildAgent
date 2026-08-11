---
doc_type: building_type
doc_scope: generation
knowledge_layer: architecture
entity_type: building
entity_name: public_building_subtypes
topic: assembly
wild_version: "1.1"
status: experimental
authority: domain_reference
source: building_types/public/public-building-subtypes.md
keywords:
  - 公共建筑细分类型
  - public building subtype
  - 建筑视觉特征
  - 最小构件组合
  - WILD降级表达
---

# 公共建筑细分类型的视觉特征与最小组装语义

> 资料来源：用户提供的《WILD蓝图AI提示词与构件规则_公共建筑_当前规范版》。本文只提炼建筑识别特征和 WILD v1.1 可表达的最小几何语义，不收录原文中未通过校验的 JSON、结构计算值或规范合规数值。
>
> 使用边界：以下内容用于概念生成和视觉近似，不能替代结构、防火、疏散、无障碍、医疗工艺或交通工艺设计。`wall`、`floor`、`column`、`beam`、`roof` 等是几何表达，不证明真实工程体系成立。

## 园区独栋办公楼

<!-- rag-meta
entity_type: building
entity_name: park_detached_office
topic: assembly
status: experimental
authority: domain_reference
keywords: 园区独栋办公, park office, 独栋办公楼, office building
-->

园区独栋办公楼以低层独立体量、清晰主入口、规则办公窗和周边景观界面为主要识别特征。最小表达使用 `floor`、外围 `wall`、按开间布置的 `column`/`beam`、平屋顶 `roof`、规则 `window` 和入口 `door`；入口挑檐可用 `canopy`。复杂玻璃幕墙和景观水体只做薄墙、窗或基础几何近似。

## 商务写字楼标准层

<!-- rag-meta
entity_type: building
entity_name: business_office_standard_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 商务写字楼, office tower, 标准层, 核心筒, curtain wall
-->

商务写字楼标准层强调规则柱网、中央服务核心和重复立面模数。最小表达以 `column`、`beam`、`floor` 建立标准层骨架，用内部 `wall` 表示核心筒，用外围 `wall` 与连续 `window` 表示玻璃立面，再通过模板实例重复楼层。当前没有原生幕墙系统，连续玻璃只能作为窗带或薄墙近似。

## 超高层写字楼加强层

<!-- rag-meta
entity_type: building
entity_name: supertall_office_outrigger_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 超高层写字楼, supertall office, 加强层, 核心筒, 外伸臂
-->

超高层写字楼的视觉语义是高宽比较大的塔楼、连续核心筒、周边竖向构件和少量明显加强层。WILD 可用重复 `floor`、周边 `column`、环向 `beam`、核心筒 `wall` 和平屋顶表达体量，并用加密梁或 `primitive` 表示加强带。该表达只提供外观，不代表抗侧力体系、外伸臂或巨型结构已经完成工程计算。

## 幼儿园活动室单元

<!-- rag-meta
entity_type: building
entity_name: kindergarten_activity_unit
topic: assembly
status: experimental
authority: domain_reference
keywords: 幼儿园, kindergarten, 活动室, 低窗台, 雨棚
-->

幼儿园活动室以低层、小尺度、充足采光、直接联系室外和友好的入口雨棚为主要特征。最小表达使用 `floor`、围护 `wall`、较低窗台的 `window`、通往室外的 `door`、入口 `canopy` 和简单坡屋顶或平屋顶。儿童安全、疏散距离和栏杆尺寸必须由外部规范校验，不能从概念模型直接推断合规。

## 中小学教学楼标准层

<!-- rag-meta
entity_type: building
entity_name: school_teaching_standard_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 中小学教学楼, school building, 标准教室, 外廊, 内廊
-->

中小学教学楼由重复教室开间、连续走廊、规则采光窗和明确楼梯节点形成识别特征。最小表达以 `wall` 划分教室与走廊，用重复 `window`/`door` 建立模数，以 `floor`、`column`、`beam` 和 `stair` 组织层间关系。疏散楼梯数量、教室面积和走廊净宽不在本知识块中给出固定值，生成后必须另行校验。

## 大学教学楼标准层

<!-- rag-meta
entity_type: building
entity_name: university_teaching_standard_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 大学教学楼, university teaching building, 合班教室, 教学楼
-->

大学教学楼通常表现为较大的教学开间、普通教室与合班教室混合、公共门厅和重复交通空间。最小表达使用框架 `column`/`beam`、多层 `floor`、教室隔墙 `wall`、规则门窗以及连接楼层的 `stair`。阶梯教室可用分级 `floor` 或连续 `stair` 近似，声学、视线和真实座席系统不属于当前引擎能力。

## 实验室单元

<!-- rag-meta
entity_type: building
entity_name: laboratory_unit
topic: assembly
status: experimental
authority: domain_reference
keywords: 实验室, laboratory, 实验单元, 服务走廊, 设备带
-->

实验室单元的识别语义是规则实验开间、实验区与辅助区分隔、连续服务走廊及密集设备带。最小表达以 `wall` 划分实验和辅助空间，以 `column`、`beam`、`floor` 形成规则网格，门窗按单元重复；实验台、管线和风柜仅用 `furniture` 或 `primitive` 占位。洁净、排风、防爆和专业设备关系不能由该几何配方保证。

## 博物馆展厅

<!-- rag-meta
entity_type: building
entity_name: museum_gallery
topic: assembly
status: experimental
authority: domain_reference
keywords: 博物馆, museum, 展厅, 大空间, 受控采光
-->

博物馆展厅强调连续展墙、较高净空、受控开口和清晰参观序列。最小表达使用 `floor`、高 `wall`、周边 `column`、大截面 `beam`、平屋顶 `roof` 和少量入口 `door`；展墙可用独立短墙组织。屋顶采光只能通过透明屋面或灯光近似，当前 `opening` 和 `window` 不能在 `roof` 上执行真实开洞。

## 剧院观众厅

<!-- rag-meta
entity_type: building
entity_name: theater_auditorium
topic: assembly
status: experimental
authority: domain_reference
keywords: 剧院, theater, 观众厅, 舞台塔, 楼座
-->

剧院观众厅以通高封闭体量、朝向舞台的座席坡面、楼座和更高的舞台塔为主要特征。WILD 可用围护 `wall`、分级 `floor` 或 `stair`、周边 `column`/`beam` 和大屋顶表现空间层次，用高盒体近似舞台塔。真实座席、声学反射面、舞台机械、乐池和大跨桁架均需降级为基础几何。

## 图书馆标准层

<!-- rag-meta
entity_type: building
entity_name: library_standard_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 图书馆, library, 阅览区, 书库, 中庭
-->

图书馆标准层由开放阅览区、规则书库区、安静的采光立面和可识别的中庭或共享空间组成。最小表达使用 `column`、`beam`、`floor` 构成开放网格，以少量 `wall` 分隔服务空间，以连续 `window` 建立采光面。书架与阅览家具使用 `furniture` 或模板实例表达，荷载、消防分区和藏书环境不由模型自动验证。

## 中小型体育馆

<!-- rag-meta
entity_type: building
entity_name: small_medium_gymnasium
topic: assembly
status: experimental
authority: domain_reference
keywords: 体育馆, gymnasium, 中小型体育馆, 大跨, 看台
-->

中小型体育馆以中央无柱比赛空间、两侧或环形看台、周边支承和完整大屋盖为主要视觉特征。最小表达使用周边 `column`、跨越场地的 `beam`、大尺度 `roof`、比赛层 `floor` 以及分级看台 `floor`/`stair`。网架、桁架和真实看台结构需要用密集梁或 `primitive` 近似，不能标成原生结构能力。

## 大型体育场看台单元

<!-- rag-meta
entity_type: building
entity_name: stadium_stand_unit
topic: assembly
status: experimental
authority: domain_reference
keywords: 体育场, stadium, 看台单元, 罩棚, 场地
-->

大型体育场的基本识别单元是向场地展开的阶梯看台、放射状交通通道、外圈支承和局部罩棚。WILD 可用分级 `floor`、径向 `stair`、边缘 `railing`、外圈 `column`/`beam` 与悬挑 `roof` 表现一个看台扇区，再通过旋转实例形成环形近似。连续碗形曲面、索膜罩棚和疏散容量需要专门系统处理。

## 室内游泳馆

<!-- rag-meta
entity_type: building
entity_name: indoor_natatorium
topic: assembly
status: experimental
authority: domain_reference
keywords: 游泳馆, natatorium, 泳池大厅, 大跨屋顶
-->

室内游泳馆由长条泳池、连续池岸、高湿大空间和大跨屋顶形成主要特征。最小表达以 `floor` 或浅盒体塑造池岸与池槽，用透明或蓝色材质表示水面，周边 `column`、大跨 `beam` 和 `roof` 覆盖大厅。水循环、除湿、防腐、排水坡度和真实水体行为均不属于当前建筑几何能力。

## 社区医疗诊室单元

<!-- rag-meta
entity_type: building
entity_name: community_clinic_unit
topic: assembly
status: experimental
authority: domain_reference
keywords: 社区医疗, community clinic, 诊室, 候诊区
-->

社区医疗诊室单元强调可识别入口、集中候诊、重复小诊室和清晰的公共交通空间。最小表达以 `wall` 划分候诊与诊室，以 `door`/`window` 表示访问和采光，再用 `floor`、`column`、`beam` 和平屋顶完成低层体量。无障碍、感染控制、医患流线和医疗设备布置必须作为外部专业约束。

## 综合医院住院标准层

<!-- rag-meta
entity_type: building
entity_name: general_hospital_ward_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 综合医院, general hospital, 住院标准层, 病房, 护士站
-->

综合医院住院标准层通常表现为中央走廊、重复病房单元、端部或中央交通核心及可识别护士站节点。最小表达使用规则 `floor`、外围与隔断 `wall`、重复病房 `door`/`window`、框架 `column`/`beam` 和楼梯核心。洁污分流、病床电梯、防火分区、护理视线和医疗气体系统不能从该视觉配方得出。

## 专科医院设备机房单元

<!-- rag-meta
entity_type: building
entity_name: specialist_hospital_plant_unit
topic: assembly
status: experimental
authority: domain_reference
keywords: 专科医院, specialist hospital, 设备机房, 医疗设备
-->

专科医院设备机房单元的识别重点是较封闭体量、受控开口、设备占位和明确维护通道。最小表达以厚实 `wall`、较少 `door`、结构 `floor`/`beam`/`column` 及规则 `primitive` 设备块形成机房语义。屏蔽、防振、管综、设备荷载和辐射防护属于专业设计，不能写成 WILD 自动支持关系。

## 社区商业

<!-- rag-meta
entity_type: building
entity_name: community_commercial
topic: assembly
status: experimental
authority: domain_reference
keywords: 社区商业, neighborhood retail, 沿街商铺, 店面
-->

社区商业以沿街小开间、连续店面、透明橱窗、独立入口和人行尺度雨棚为主要特征。最小表达使用连续 `wall` 分隔商铺，以重复 `door`、大面积 `window` 和 `canopy` 形成街道界面，并用 `floor` 与平屋顶完成低层盒体。招牌、卷帘和室内货架可用基础几何或家具占位。

## 购物中心标准层

<!-- rag-meta
entity_type: building
entity_name: shopping_center_standard_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 购物中心, shopping mall, 中庭, 商业标准层
-->

购物中心标准层由环绕中庭的商业界面、宽公共走道、重复店铺和多层可见空间构成。最小表达使用多层 `floor`、中庭边缘 `railing`、店铺隔墙 `wall`、框架 `column`/`beam` 及连续门窗；扶梯可用倾斜 `stair` 或 `ramp` 作视觉近似。中庭防火、排烟、商业动线和真实扶梯设备需另行设计。

## 超市营业厅

<!-- rag-meta
entity_type: building
entity_name: supermarket_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 超市, supermarket, 营业厅, 大开间, 货架
-->

超市营业厅表现为规则柱网下的大开间、连续货架阵列、集中入口和相对封闭的盒式外观。最小表达使用 `column`、`beam`、大块 `floor`、外围 `wall` 和平屋顶，入口用宽 `door` 与局部 `window`；货架使用 `furniture`、模板或 `primitive` 重复。冷链、消防通道和疏散宽度不由阵列自动保证。

## 经济型酒店客房层

<!-- rag-meta
entity_type: building
entity_name: economy_hotel_guest_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 经济型酒店, economy hotel, 客房层, 双廊客房
-->

经济型酒店客房层以中央走廊、紧凑重复客房、均匀小窗和简洁立面为主要识别特征。最小表达用 `wall` 形成走廊及连续客房隔断，以重复 `door`/`window` 表示房间模数，以 `floor`、`column`、`beam` 和楼梯核心完成标准层。卫生间设备与家具可使用简化家具或盒体，不代表机电条件成立。

## 商务酒店客房层

<!-- rag-meta
entity_type: building
entity_name: business_hotel_guest_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 商务酒店, business hotel, 客房层, 电梯厅
-->

商务酒店客房层延续中央走廊和重复客房模数，但通常具有更明确的电梯厅、端部套房和较整齐的玻璃或石材立面。最小表达仍以 `wall`、`door`、`window`、`floor` 和框架构件为主，通过不同房间宽度和立面窗模数区分等级。室内精装、设备与运营分区仅做视觉占位。

## 五星级酒店客房层

<!-- rag-meta
entity_type: building
entity_name: luxury_hotel_guest_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 五星级酒店, luxury hotel, 客房层, 套房, 阳台
-->

五星级酒店客房层的视觉特征是更宽的客房模数、套房变化、较深的立面层次以及阳台或凸窗等附加构件。最小表达使用分隔 `wall`、重复 `door`/`window`，并按立面需要加入 `balcony` 或 `bay_window`，骨架仍由 `floor`、`column` 和 `beam` 组成。等级评定、服务流线和精装标准不从几何复杂度推断。

## 度假酒店客房别墅

<!-- rag-meta
entity_type: building
entity_name: resort_hotel_villa
topic: assembly
status: experimental
authority: domain_reference
keywords: 度假酒店, resort hotel, 客房别墅, terrace, villa
-->

度假酒店客房别墅以独立或半独立低层体量、面向景观的宽窗、露台、阳台和有辨识度的坡屋顶为主要特征。最小表达使用 `floor`、外围 `wall`、`door`/`window`、`balcony`、`railing` 与坡屋顶 `roof`。泳池、复杂地形和连续景观构筑物需要用基础几何近似，不能使用不存在的 `terrain` 类型。

## 汽车客运站

<!-- rag-meta
entity_type: building
entity_name: coach_station
topic: assembly
status: experimental
authority: domain_reference
keywords: 汽车客运站, coach station, 候车大厅, 发车雨棚
-->

汽车客运站由通高候车大厅、清晰主入口、面向站台的出发界面和连续发车雨棚形成识别特征。最小表达使用大块 `floor`、通高 `wall`、周边 `column`、大跨 `beam`/`roof`、宽入口 `door` 以及站台侧 `canopy`。车辆流线、安检、售检票和站台安全关系不属于当前几何编译器。

## 港口客运站

<!-- rag-meta
entity_type: building
entity_name: port_passenger_terminal
topic: assembly
status: experimental
authority: domain_reference
keywords: 港口客运站, ferry terminal, 候船厅, 登船廊桥
-->

港口客运站以面向水域的长向大厅、大面积玻璃、候船空间和连接泊位的登船廊桥体量为主要特征。最小表达使用框架 `column`/`beam`、通高围护 `wall`、连续 `window`、大屋顶和入口 `canopy`；廊桥用窄长 `floor`、`wall` 或盒体近似。潮汐、船岸接口和港口工艺不进入建筑概念配方。

## 地铁站站台层

<!-- rag-meta
entity_type: building
entity_name: metro_platform_level
topic: assembly
status: experimental
authority: domain_reference
keywords: 地铁站, metro station, 站台层, 屏蔽门, 地下空间
-->

地铁站站台层表现为狭长地下空间、连续站台边、规则柱列、轨行区和多组垂直交通节点。最小表达使用长条 `floor`、侧墙 `wall`、重复 `column`、梁板和连接站厅的 `stair`；屏蔽门与轨道可用重复窗框、梁或 `primitive` 近似。地下开挖、通风、疏散和列车系统不能由该模型验证。

## 高铁站候车大厅

<!-- rag-meta
entity_type: building
entity_name: high_speed_rail_waiting_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 高铁站, high-speed rail station, 候车大厅, 大跨屋盖
-->

高铁站候车大厅以超大通高空间、长向结构节奏、大面积采光立面和覆盖站台的整体大屋盖为主要视觉特征。最小表达用周边及少量内部 `column`、跨向 `beam`、大尺度 `roof`、连续 `window` 和多层 `floor` 建立大厅。真实网架、站台雨棚、检票设备和铁路工艺只能以基础几何降级表示。

## 航站楼办票大厅

<!-- rag-meta
entity_type: building
entity_name: airport_checkin_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 航站楼, airport terminal, 办票大厅, check-in hall, curtain wall
-->

航站楼办票大厅通常具有宽阔无柱或少柱空间、长向值机岛阵列、连续玻璃立面和轻盈的大跨屋顶。最小表达以 `column`/`beam`、大 `floor`、高 `wall`、连续 `window` 和整体 `roof` 构成大厅，值机岛用模板化家具或盒体重复。行李、安检、登机桥和复杂曲面屋盖没有原生业务组件。

## 法院审判楼

<!-- rag-meta
entity_type: building
entity_name: courthouse_building
topic: assembly
status: experimental
authority: domain_reference
keywords: 法院, courthouse, 审判楼, 门廊, 纪念性入口
-->

法院审判楼强调对称或稳定的公共立面、抬高基座、庄重入口门廊和可辨识的审判厅大体量。最小表达使用平台 `floor`、规则 `column`/`beam`、围护 `wall`、高入口 `door` 与平屋顶或坡屋顶，门廊可用柱列和 `canopy`。公众、审判和羁押流线以及安全分区必须作为独立专业约束。

## 监狱监舍单元

<!-- rag-meta
entity_type: building
entity_name: prison_cell_unit
topic: assembly
status: experimental
authority: domain_reference
keywords: 监狱, prison, 监舍单元, 围墙, 监控走廊
-->

监舍单元以高度重复的小房间、连续管理走廊、受控小开口和外围安全边界形成识别语义。最小表达用 `wall`、重复 `door`/小 `window`、多层 `floor`、结构框架及外围高墙表达基本体量。门禁、监控、防攀爬、防冲撞和监管流程没有可验证的 WILD 专用语义，不应从普通门窗构件推断安全等级。

## 养老院居室层

<!-- rag-meta
entity_type: building
entity_name: eldercare_residential_floor
topic: assembly
status: experimental
authority: domain_reference
keywords: 养老院, eldercare, 居室层, 护理单元, 阳台
-->

养老院居室层通常由重复居室、连续且易识别的走廊、公共起居节点、充分采光和可选阳台组成。最小表达以 `wall`、`door`、`window`、`floor`、`stair` 和局部 `balcony`/`railing` 形成护理单元视觉结构。无障碍回转、扶手、护理距离、避难与消防要求必须引用现行规范另行校验。

## 佛寺大雄宝殿

<!-- rag-meta
entity_type: building
entity_name: buddhist_temple_main_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 佛寺, Buddhist temple, 大雄宝殿, 台基, 中式屋顶
-->

佛寺大雄宝殿以中轴对称、抬高台基、前廊木柱、深远出檐和中式曲面屋顶为主要特征。最小表达使用台基 `floor`、`chinese_wooden` 柱列、矩形 `beam`、围护 `wall`、门窗以及 `chinese_curved` 屋顶。斗拱、瓦作、举折和真实木构节点只能用简化梁柱或 `primitive` 表示。

## 道观三清殿

<!-- rag-meta
entity_type: building
entity_name: taoist_temple_main_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 道观, Taoist temple, 三清殿, 山门, 中式木构
-->

道观三清殿与传统中轴殿堂共享台基、柱廊和大屋顶语义，但整体可更强调院落层次、山门序列与灰瓦木色。最小表达用 `floor`、木柱 `column`、`beam`、围护 `wall`、入口 `door` 和 `chinese_curved` 屋顶组织单殿，再以多个体量形成院落。宗教陈设和传统节点只作视觉占位。

## 清真寺礼拜大殿

<!-- rag-meta
entity_type: building
entity_name: mosque_prayer_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 清真寺, mosque, 礼拜大殿, 穹顶, 宣礼塔
-->

清真寺礼拜大殿的视觉特征包括面向明确的整体礼拜空间、重复拱廊、穹顶或坡屋顶以及可选宣礼塔。最小表达使用大 `floor`、周边 `wall`、规则 `column`/`beam` 和 `dome` 屋顶，塔体可用圆柱与锥体 `primitive` 组合。拱券、纹样、朝向和礼仪空间必须按项目语境细化，不能由默认组件自动生成。

## 哥特式教堂中殿

<!-- rag-meta
entity_type: building
entity_name: gothic_church_nave
topic: assembly
status: experimental
authority: domain_reference
keywords: 哥特式教堂, Gothic church, 中殿, 尖拱, 飞扶壁
-->

哥特式教堂中殿以高耸纵向空间、连续柱列、尖拱节奏、高窗和塔尖为主要识别特征。最小表达使用高 `column`、纵向 `beam`、高 `wall`、陡坡 `roof` 与细长 `window`，扶壁和塔尖用 `primitive` 补充。当前窗组件没有原生尖拱窗型，彩窗、肋拱和飞扶壁只能做几何近似。

## 苏州园林水榭

<!-- rag-meta
entity_type: building
entity_name: suzhou_garden_waterside_pavilion
topic: assembly
status: experimental
authority: domain_reference
keywords: 苏州园林, Suzhou garden, 水榭, 白墙灰瓦, 漏窗
-->

苏州园林水榭以临水平台、轻巧柱廊、白墙灰瓦、不对称开敞界面和与游廊衔接为主要特征。最小表达使用临水 `floor`、木柱 `column`、细 `beam`、局部白色 `wall`、重复门窗和 `chinese_curved` 屋顶；水面用带材质的薄几何表示。漏窗、花格和复杂园林路径需要基础几何或纹理近似。

## 皇家园林大殿

<!-- rag-meta
entity_type: building
entity_name: imperial_garden_main_hall
topic: assembly
status: experimental
authority: domain_reference
keywords: 皇家园林, imperial garden, 大殿, 轴线, 琉璃瓦
-->

皇家园林大殿强调轴线秩序、较高台基、成组木柱、深远出檐和高等级色彩对比。最小表达由台基 `floor`、`chinese_wooden` 柱列、矩形 `beam`、殿身 `wall`、门窗和大型 `chinese_curved` 屋顶组成。琉璃瓦、彩画、斗拱及等级制度只作为材质和简化几何语义，不应写成引擎结构规则。

## 岭南园林水榭

<!-- rag-meta
entity_type: building
entity_name: lingnan_garden_waterside_pavilion
topic: assembly
status: experimental
authority: domain_reference
keywords: 岭南园林, Lingnan garden, 水榭, 满洲窗, 灰塑
-->

岭南园林水榭通常表现为临水开放、轻巧柱廊、较缓屋面、通透门窗以及灰塑和彩色玻璃等细部。最小表达使用平台 `floor`、细柱 `column`、`beam`、局部 `wall`、大面积 `window`、`railing` 和中式屋顶；满洲窗以分格和彩色玻璃材质近似。灰塑、砖雕和水岸曲线需要纹理或 `primitive` 补充。
