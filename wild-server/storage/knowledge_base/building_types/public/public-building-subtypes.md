---
entity_name: public_building_subtypes
topic: composition
status: supported
authority: maintainer
source: building_types/public/public-building-subtypes.md
building_category: public
primary_terms:
  - 公共建筑细分类型
synonyms: []
applies_to:
  - 公共建筑细分类型
---

# 公共建筑细分类型：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 园区独栋办公楼

<!-- rag-meta
entity_type: building
entity_name: park_detached_office
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 园区独栋办公楼
synonyms: []
applies_to:
  - 园区独栋办公楼
-->

- 适用条件：用户或已批准方案明确采用园区独栋办公楼；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：玻璃幕墙四立面；规整柱网；中庭玻璃栏板；入口玻璃雨棚。
- 条件关系：采用中庭时保持楼板留空和周边通行；采用幕墙时协调窗格与所选轴网；入口雨棚连接实际宿主。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`canopy`、`railing`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。方柱用 `primitive.box` 视觉近似；幕墙用 `wall + window` 或 `primitive`，禁止新增幕墙专用类型。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 商务写字楼标准层

<!-- rag-meta
entity_type: building
entity_name: business_office_standard_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 商务写字楼标准层
synonyms: []
applies_to:
  - 商务写字楼标准层
-->

- 适用条件：用户或已批准方案明确采用商务写字楼标准层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：核心筒集中交通；单元式玻璃幕墙；避难层；大堂通高入口雨棚。
- 条件关系：核心交通沿已建模楼层连续；幕墙分格与楼层对应；通高大堂不被标准层复制填满，避难空间仅按已确认需求设置。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`canopy`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。方柱用 `primitive.box` 近似；幕墙用 `wall + window` 或 `primitive`，不写未注册类型。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 超高层写字楼加强层

<!-- rag-meta
entity_type: building
entity_name: supertall_office_outrigger_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 超高层写字楼加强层
synonyms: []
applies_to:
  - 超高层写字楼加强层
-->

- 适用条件：用户或已批准方案明确采用超高层写字楼加强层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：巨型 CFT 柱；伸臂桁架加强层；单元式幕墙；塔冠天线。
- 条件关系：选择加强层时表达核心区、外框与伸臂之间的连接；塔冠及幕墙依附实际顶层与外壳，不把重复杆件当作受力验算。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`window`、`stair`、`canopy`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。CFT、桁架和塔冠无专用类型，分别用 `column/primitive`、`beam/primitive` 近似；幕墙不新增类型。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 幼儿园活动室单元

<!-- rag-meta
entity_type: building
entity_name: kindergarten_activity_unit
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 幼儿园活动室单元
synonyms: []
applies_to:
  - 幼儿园活动室单元
-->

- 适用条件：用户或已批准方案明确采用幼儿园活动室单元；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：低矮体量；圆角墙；低窗台大窗；加高栏杆；屋顶活动平台
- 条件关系：活动室、公共交通与所选室外活动空间保持联系；采用低窗台或屋顶平台时分别推导开口标高和平台边界。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`railing`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。游乐设施 无对应家具 subtype 的游乐设施 → primitive 组合；圆角/椭圆 → arc 墙段或 primitive 分段；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 中小学教学楼标准层

<!-- rag-meta
entity_type: building
entity_name: school_teaching_standard_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 中小学教学楼标准层
synonyms: []
applies_to:
  - 中小学教学楼标准层
-->

- 适用条件：用户或已批准方案明确采用中小学教学楼标准层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：规整教室单元；防眩光窗布置；走廊栏板；观察窗教室门
- 条件关系：教室、走廊与入口按本次单元组织；门上观察窗独立绑定墙体；外廊栏杆只沿实际临空边。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 大学教学楼标准层

<!-- rag-meta
entity_type: building
entity_name: university_teaching_standard_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 大学教学楼标准层
synonyms: []
applies_to:
  - 大学教学楼标准层
-->

- 适用条件：用户或已批准方案明确采用大学教学楼标准层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：规整柱网；报告厅大跨；成组教室单元
- 条件关系：普通教室按所选模数重复；报告厅需要的大空间不能被教室标准层的柱、隔墙和楼板截断。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`canopy`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（报告厅）无原生类型 → beam 组合表达；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 实验室单元

<!-- rag-meta
entity_type: building
entity_name: laboratory_unit
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 实验室单元
synonyms: []
applies_to:
  - 实验室单元
-->

- 适用条件：用户或已批准方案明确采用实验室单元；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：厚重墙；隔振台基；通风竖井；实验台排布
- 条件关系：选择实验台、竖井或隔振台基时保留它们与设备和通道的位置关系；井道逐层对齐，不能将几何外观当作性能证明。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`door`、`window`、`stair`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。placement 非当前正式业务类型 → primitive 组合表达；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 博物馆展厅

<!-- rag-meta
entity_type: building
entity_name: museum_gallery
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 博物馆展厅
synonyms: []
applies_to:
  - 博物馆展厅
-->

- 适用条件：用户或已批准方案明确采用博物馆展厅；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：少柱大跨展厅；顶部漫射天窗；通高入口大厅；可移动展墙。
- 条件关系：展厅、入口和展览路线保持联系；展墙不得阻断已选动线；采光顶独立处理屋面，不能把窗直接挂到屋顶。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`railing`、`light`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。天窗用透明 `roof/primitive`，展柜和导览设施用 `furniture/primitive` 近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 剧院观众厅

<!-- rag-meta
entity_type: building
entity_name: theater_auditorium
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 剧院观众厅
synonyms: []
applies_to:
  - 剧院观众厅
-->

- 适用条件：用户或已批准方案明确采用剧院观众厅；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：弧形声学观众厅；超高舞台塔；下沉乐池；前厅柱廊
- 条件关系：观众区、舞台、前厅和所选乐池保持空间联系；通高观众厅不得被整层楼板填满，楼座与通道连续。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`door`、`stair`、`railing`、`light`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（屋盖）无原生类型 → beam 组合；座椅 furniture 用 primitive 阵列；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 图书馆标准层

<!-- rag-meta
entity_type: building
entity_name: library_standard_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 图书馆标准层
synonyms: []
applies_to:
  - 图书馆标准层
-->

- 适用条件：用户或已批准方案明确采用图书馆标准层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：少柱阅览大厅；通高中庭；密集书库；天窗漫射光
- 条件关系：书库、阅览区与交通区按任务组织；采用中庭时楼板留空，边缘护栏与跨层交通分别定位。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`railing`、`light`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。书架、桌椅使用 furniture 对应 subtype 或 primitive 组合；原 autoRailing(中庭) → railing 组件；屋顶天窗 → 透明 roof/primitive；没有 window.parentRoof；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 中小型体育馆

<!-- rag-meta
entity_type: building
entity_name: small_medium_gymnasium
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 中小型体育馆
synonyms: []
applies_to:
  - 中小型体育馆
-->

- 适用条件：用户或已批准方案明确采用中小型体育馆；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：大跨屋盖；阶梯看台；运动木地板；疏散楼梯环绕
- 条件关系：运动区保持所需净空，支撑与看台避免侵占比赛区；看台高差、通道及屋盖支点协调。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`stair`、`canopy`、`railing`、`light`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（屋盖）无原生类型 → beam 组合；原 座椅用 furniture.chair 或 primitive 组合；方/矩形柱 → primitive.box 视觉近似；原生 column 为圆/锥柱；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 大型体育场看台单元

<!-- rag-meta
entity_type: building
entity_name: stadium_stand_unit
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 大型体育场看台单元
synonyms: []
applies_to:
  - 大型体育场看台单元
-->

- 适用条件：用户或已批准方案明确采用大型体育场看台单元；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：椭圆环墙；悬挑罩棚；阶梯看台；跑道足球场
- 条件关系：看台随本次场地轮廓分段，高差与上下通道相接；罩棚支撑避让视线和运动区，出入口连接实际路径。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`stair`、`railing`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（罩棚）无原生类型 → beam 组合；膜屋面可用多片 roof/primitive 近似所选轮廓，单块平板不能代表任意曲面；方/矩形柱 → primitive.box 视觉近似；原生 column 为圆/锥柱；圆角/椭圆 → arc 墙段或 primitive 分段；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 室内游泳馆

<!-- rag-meta
entity_type: building
entity_name: indoor_natatorium
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 室内游泳馆
synonyms: []
applies_to:
  - 室内游泳馆
-->

- 适用条件：用户或已批准方案明确采用室内游泳馆；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：下沉泳池；大跨防腐屋盖；池边玻璃栏；通风除湿竖井
- 条件关系：池体、池岸和入口标高相互匹配；屋盖支撑避开泳池净空；所选临水边界与通风竖井单独表达。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`stair`、`railing`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（warren）无原生类型 → beam 组合；方/矩形柱 → primitive.box 视觉近似；原生 column 为圆/锥柱；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 社区医疗诊室单元

<!-- rag-meta
entity_type: building
entity_name: community_clinic_unit
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 社区医疗诊室单元
synonyms: []
applies_to:
  - 社区医疗诊室单元
-->

- 适用条件：用户或已批准方案明确采用社区医疗诊室单元；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：候诊大厅；诊室单元（观察窗门）；无障碍坡道
- 条件关系：候诊区、诊室和入口按任务连接；选择坡道时起终点与通道标高匹配，观察窗归属真实门旁墙体。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 综合医院住院标准层

<!-- rag-meta
entity_type: building
entity_name: general_hospital_ward_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 综合医院住院标准层
synonyms: []
applies_to:
  - 综合医院住院标准层
-->

- 适用条件：用户或已批准方案明确采用综合医院住院标准层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：洁污分流双通道；防辐射厚墙；手术室气密门；南向病房
- 条件关系：病房与交通、护理和服务空间按任务组织；只有明确要求分流时才保留分离通道，专科防护不套用于所有病房。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`railing`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。输液轨道原 placement → primitive 组合；病床 furniture(bed)；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 专科医院设备机房单元

<!-- rag-meta
entity_type: building
entity_name: specialist_hospital_plant_unit
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 专科医院设备机房单元
synonyms: []
applies_to:
  - 专科医院设备机房单元
-->

- 适用条件：用户或已批准方案明确采用专科医院设备机房单元；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：专科差异化机房/病房；防护与隔离构造
- 条件关系：依据点名专科设备保留机房、通道与防护外形关系；设备净空不被普通柱网占用。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `wall`、`door`、`window`、`ramp`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。furniture(牙科椅等) → primitive 组合；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 社区商业

<!-- rag-meta
entity_type: building
entity_name: community_commercial
building_category: commercial
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 社区商业
synonyms: []
applies_to:
  - 社区商业
-->

- 适用条件：用户或已批准方案明确采用社区商业；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：大面积橱窗；沿街雨棚；首层高空间
- 条件关系：店面入口与街道相接，选择橱窗时适配墙面；所选雨棚与实际店面宽度和宿主匹配。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`canopy`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 购物中心标准层

<!-- rag-meta
entity_type: building
entity_name: shopping_center_standard_floor
building_category: commercial
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 购物中心标准层
synonyms: []
applies_to:
  - 购物中心标准层
-->

- 适用条件：用户或已批准方案明确采用购物中心标准层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：通高中庭 + 玻璃栏板；采光顶；自动扶梯；商铺阵列
- 条件关系：营业层围绕本次动线组织；中庭留空、周边通行连续，扶梯起终平台衔接；采光顶不伪造 window.parentRoof。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`canopy`、`railing`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。采光顶 → 透明 roof/primitive，屋面墙上的窗仍需真实 parentWall；幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型；自动扶梯 → stair/ramp 静态近似；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 超市营业厅

<!-- rag-meta
entity_type: building
entity_name: supermarket_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 超市营业厅
synonyms: []
applies_to:
  - 超市营业厅
-->

- 适用条件：用户或已批准方案明确采用超市营业厅；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：大空间少柱；货架区；收银阵列；冷库隔墙
- 条件关系：货架、收银区和通道按任务组织；选择冷库时表达分隔围护和入口，不默认密集隔墙。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`stair`、`canopy`、`light`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。placement 非当前正式业务类型 → 用 primitive 或省略；收银台 wall 半围合 + furniture；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 经济型酒店客房层

<!-- rag-meta
entity_type: building
entity_name: economy_hotel_guest_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 经济型酒店客房层
synonyms: []
applies_to:
  - 经济型酒店客房层
-->

- 适用条件：用户或已批准方案明确采用经济型酒店客房层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：客房单元重复；走廊中分；小卫生间
- 条件关系：重复客房与共享交通连通；走廊居中、单侧或其他组织由方案决定，不锁定客房尺度与数量。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`wall`、`roof`、`door`、`window`、`stair`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 商务酒店客房层

<!-- rag-meta
entity_type: building
entity_name: business_hotel_guest_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 商务酒店客房层
synonyms: []
applies_to:
  - 商务酒店客房层
-->

- 适用条件：用户或已批准方案明确采用商务酒店客房层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：核心筒；玻璃幕墙；落地窗客房；通高大堂
- 条件关系：客房、核心交通与公共大堂有明确联系；选择幕墙或落地窗时协调宿主与模数，通高大堂保留空域。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`roof`、`door`、`window`、`stair`、`canopy`、`railing`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 五星级酒店客房层

<!-- rag-meta
entity_type: building
entity_name: luxury_hotel_guest_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 五星级酒店客房层
synonyms: []
applies_to:
  - 五星级酒店客房层
-->

- 适用条件：用户或已批准方案明确采用五星级酒店客房层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：通高大堂；宴会厅大跨；屋顶泳池；豪华雨棚
- 条件关系：客房与大堂、宴会空间按任务联系；屋顶泳池与雨棚仅在已选方案出现时落实，星级不触发固定设施套餐。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`canopy`、`railing`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 度假酒店客房别墅

<!-- rag-meta
entity_type: building
entity_name: resort_hotel_villa
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 度假酒店客房别墅
synonyms: []
applies_to:
  - 度假酒店客房别墅
-->

- 适用条件：用户或已批准方案明确采用度假酒店客房别墅；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：木石客房别墅；景观落地窗；木露台；无边际泳池
- 条件关系：客房、景观开口与户外停留空间按方案连接；选择泳池或露台时区分水面、池岸与平台，不强制所有单元相同。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`canopy`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。terrain 无原生类型 → 场景处理；泳池 floor/primitive 加水面视觉材质；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 汽车客运站

<!-- rag-meta
entity_type: building
entity_name: coach_station
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 汽车客运站
synonyms: []
applies_to:
  - 汽车客运站
-->

- 适用条件：用户或已批准方案明确采用汽车客运站；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：大跨候车厅；发车位雨棚；售票窗口；站前广场
- 条件关系：候车、检票与发车区按本次动线连接；雨棚范围与上车区匹配，通高大厅不复制整层楼板。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`canopy`、`railing`、`furniture`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（屋盖）无原生类型 → beam 组合；幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 港口客运站

<!-- rag-meta
entity_type: building
entity_name: port_passenger_terminal
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 港口客运站
synonyms: []
applies_to:
  - 港口客运站
-->

- 适用条件：用户或已批准方案明确采用港口客运站；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：大跨候船厅；登船廊桥；联检通道；码头高栏
- 条件关系：候船、联检、登船通道与码头端部连贯；廊桥标高与两端平台对应，临水边界单独处理。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`canopy`、`railing`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（warren 屋盖）无原生类型 → beam 组合；幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 地铁站站台层

<!-- rag-meta
entity_type: building
entity_name: metro_platform_level
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 地铁站站台层
synonyms: []
applies_to:
  - 地铁站站台层
-->

- 适用条件：用户或已批准方案明确采用地铁站站台层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：站台屏蔽门；中柱列；扶梯组；通风竖井
- 条件关系：站台、屏蔽门与交通入口按本次站台轮廓对应；竖向交通连接实际平台，轨道和设备仅表达受支持几何。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`door`、`stair`、`ramp`、`canopy`、`railing`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。placement 非当前正式业务类型 → primitive 或省略；屏蔽门 leafCount 用分段 door；自动扶梯 → stair/ramp 静态近似；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 高铁站候车大厅

<!-- rag-meta
entity_type: building
entity_name: high_speed_rail_waiting_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 高铁站候车大厅
synonyms: []
applies_to:
  - 高铁站候车大厅
-->

- 适用条件：用户或已批准方案明确采用高铁站候车大厅；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：超大跨候车厅；CFT 巨柱；站台长雨棚；扶梯组。
- 条件关系：候车厅与站台交通连贯；大跨支撑保持所需净空，长雨棚按站台范围分段，不借用普通办公立面。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`canopy`、`railing`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。CFT、桁架、扶梯和幕墙分别用现有 `primitive/beam/stair/ramp/wall/window` 近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 航站楼办票大厅

<!-- rag-meta
entity_type: building
entity_name: airport_checkin_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 航站楼办票大厅
synonyms: []
applies_to:
  - 航站楼办票大厅
-->

- 适用条件：用户或已批准方案明确采用航站楼办票大厅；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：超少柱办票厅、超大跨屋盖、玻璃幕墙、登机廊桥、夹层和分离流线。
- 条件关系：办票、候机和所选到达/出发流线保持对应；夹层保留主厅通高，廊桥连接明确楼层与端点。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`railing`、`light`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。桁架、方柱、扶梯、天窗和幕墙均映射到现有 `beam/primitive/stair/ramp/roof/wall/window`。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 法院审判楼

<!-- rag-meta
entity_type: building
entity_name: courthouse_building
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 法院审判楼
synonyms: []
applies_to:
  - 法院审判楼
-->

- 适用条件：用户或已批准方案明确采用法院审判楼；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：门廊柱列；三线分离流线；法庭隔离栏；封闭羁押室
- 条件关系：法庭、公共入口与已指定专用流线保持联系；隔离栏和羁押空间按任务布局，不由庄严外观替代功能关系。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`stair`、`ramp`、`railing`、`light`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 监狱监舍单元

<!-- rag-meta
entity_type: building
entity_name: prison_cell_unit
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 监狱监舍单元
synonyms: []
applies_to:
  - 监狱监舍单元
-->

- 适用条件：用户或已批准方案明确采用监狱监舍单元；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：高厚围墙；四角岗楼；铁栅门窗；放风区
- 条件关系：监舍、管理交通及所选放风区按任务分区；边界与出入口对应，铁栅外观不等于安全性能。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`roof`、`door`、`window`、`stair`、`railing`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。placement 非当前正式业务类型 → primitive 或省略；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 养老院居室层

<!-- rag-meta
entity_type: building
entity_name: eldercare_residential_floor
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 养老院居室层
synonyms: []
applies_to:
  - 养老院居室层
-->

- 适用条件：用户或已批准方案明确采用养老院居室层；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：无高差地面；双层扶手；推拉宽门；低窗台；无障碍庭院
- 条件关系：居室、公共交通与户外空间按任务连接；已要求平缓通行时保持标高连续，扶手与路径对应。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`roof`、`door`、`window`、`stair`、`ramp`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 佛寺大雄宝殿

<!-- rag-meta
entity_type: building
entity_name: buddhist_temple_main_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 佛寺大雄宝殿
synonyms: []
applies_to:
  - 佛寺大雄宝殿
-->

- 适用条件：用户或已批准方案明确采用佛寺大雄宝殿；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：中轴殿宇；曲面重檐；斗拱额枋；须弥座；佛塔
- 条件关系：主殿、台基与柱列按选定轴线组织；采用重檐或斗拱语汇时保持上下支撑关系；附属佛塔按任务单独决定。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`railing`、`cornice`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（斗拱）无原生类型 → primitive 组合或省略；placement 非当前正式业务类型 → primitive；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 道观三清殿

<!-- rag-meta
entity_type: building
entity_name: taoist_temple_main_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 道观三清殿
synonyms: []
applies_to:
  - 道观三清殿
-->

- 适用条件：用户或已批准方案明确采用道观三清殿；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：青绿瓦曲面顶；棂星门；八卦棂花；垂带踏跺
- 条件关系：殿堂入口、台基和柱列形成联系；选用屋盖与棂花时分别处理支点和真实门窗宿主，避免强制固定配色。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`ramp`、`railing`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。未列额外未注册类型；专业设备仅用当前基础类型近似。；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 清真寺礼拜大殿

<!-- rag-meta
entity_type: building
entity_name: mosque_prayer_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 清真寺礼拜大殿
synonyms: []
applies_to:
  - 清真寺礼拜大殿
-->

- 适用条件：用户或已批准方案明确采用清真寺礼拜大殿；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：中央穹顶；光塔；尖拱门；几何纹饰；米哈拉布
- 条件关系：礼拜空间、入口和所选朝向要求保持一致；穹顶、光塔及纹饰由本次地域或流派决定，支撑避让主要活动区。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`wall`、`roof`、`door`、`window`、`railing`、`cornice`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。mullion（几何纹）无独立类型 → window 棂条/primitive；placement 非当前正式业务类型 → primitive 或省略；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 哥特式教堂中殿

<!-- rag-meta
entity_type: building
entity_name: gothic_church_nave
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 哥特式教堂中殿
synonyms: []
applies_to:
  - 哥特式教堂中殿
-->

- 适用条件：用户或已批准方案明确采用哥特式教堂中殿；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：尖塔；飞扶壁；玫瑰窗；柳叶窗彩色玻璃；肋拱顶
- 条件关系：中殿、侧廊和所选塔楼保持主次关系；拱顶、扶壁与墙柱支点协调，彩窗纹样不改变宿主规则。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`stair`、`railing`、`cornice`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（肋拱顶）无原生类型 → beam 组合；玫瑰窗棂 → window 棂条/primitive 近似；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 苏州园林水榭

<!-- rag-meta
entity_type: building
entity_name: suzhou_garden_waterside_pavilion
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 苏州园林水榭
synonyms: []
applies_to:
  - 苏州园林水榭
-->

- 适用条件：用户或已批准方案明确采用苏州园林水榭；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：曲廊美人靠；月洞空窗；漏窗框景；叠山理水
- 条件关系：曲廊连接台基与房屋，框景洞口保持空透；临水平台与驳岸相接，美人靠的座面与护栏需分别表达。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`ramp`、`railing`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。terrain 无原生类型 → primitive 组合；漏窗/月洞用 opening(无 window)；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 皇家园林大殿

<!-- rag-meta
entity_type: building
entity_name: imperial_garden_main_hall
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 皇家园林大殿
synonyms: []
applies_to:
  - 皇家园林大殿
-->

- 适用条件：用户或已批准方案明确采用皇家园林大殿；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：重檐大殿；汉白玉栏杆；琉璃影壁；须弥座；大型水体
- 条件关系：选择重檐时对应上下柱列；台基与前场通过交通相接；影壁按其独立位置生成，不强行搭接院墙。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`railing`、`cornice`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。truss（斗拱）无原生类型 → primitive 组合；placement 非当前正式业务类型 → primitive 或省略；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 岭南园林水榭

<!-- rag-meta
entity_type: building
entity_name: lingnan_garden_waterside_pavilion
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 岭南园林水榭
synonyms: []
applies_to:
  - 岭南园林水榭
-->

- 适用条件：用户或已批准方案明确采用岭南园林水榭；名称本身不决定全部构件。
- 类型特征：来源涉及以下空间或系统，可按任务选择并保留选中部分的辨识度：细柱卷棚顶；满洲窗；花格隔断；水庭；骑楼连廊
- 条件关系：水庭、骑楼连廊与房屋连接；柱列支撑所选屋盖，满洲窗或花格隔断依附真实围护；临水平台保持有效边界。 来源附属系统仅在本次方案选择时使用。
- WILD 映射与边界：按已选系统使用 `floor`、`column`、`beam`、`wall`、`roof`、`door`、`window`、`railing`、`cornice`、`primitive`；墙挂组件引用原生 wall，平台和屋盖按实际支撑边界定位。mullion（花格）无独立类型 → window 棂条/primitive；几何表达不承担结构或专业性能验证。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
