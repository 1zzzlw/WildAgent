---
building_category: public
entity_name: public_building_subtypes
topic: composition
status: experimental
authority: domain_reference
source: building_types/public/public-building-subtypes.md
primary_terms:
  - 公共建筑细分类型
  - 默认完整构成合同
  - 组件优先级
  - WILD降级表达
synonyms:
  - public building subtype
---

# 公共建筑 38 类默认完整构成与组装关系

> 来源：用户提供的《WILD蓝图AI提示词与构件规则_公共建筑_当前规范版》。本文保留 38 类建筑的身份、空间、构件链、搭接关系和降级映射；来源中的工程尺寸均按 domain_reference 处理，不能替代结构、防火、疏散、无障碍、医疗或交通专业校核。
>
> 来源 JSON 未直接入库：其中混有旧字段、缺失引用和未注册业务类型。无效实现声明被隔离，但其仍成立的建筑构成语义已进入下列合同。玻璃幕墙共性规则路由到 components/glass-curtain-walls.md 与 recipes/glass-curtain-wall-assembly.md。
>
> **注意**：本文档包含多种公共建筑子类型，其中商业类建筑（社区商业、购物中心）使用 `building_category: commercial` 的实体级 metadata。

## 园区独栋办公楼

<!-- rag-meta
entity_type: building
entity_name: park_detached_office
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 园区独栋办公
  - 独栋办公楼
  - 默认完整构成
  - composition
synonyms:
  - park office
  - office building
-->

默认完整构成合同：

- 识别特征：玻璃幕墙四立面；规整柱网；中庭玻璃栏板；入口玻璃雨棚。
- 空间与体量：`required` 低层独栋办公体量；`characteristic` 中庭与可上人平屋面。
- 主体骨架：`required` `column → beam → floor` 规则框架；8.4m 柱网为领域参考。
- 外围护：`required / characteristic` 幕墙宿主 `wall`、内隔墙和 `roof(flat)`。
- 开口组件：`required` 幕墙 `window` 与入口 `door`，均依附真实 `parentWall`。
- 交通组件：`required` `stair`；入口有高差时 `ramp` 为 `conditional`。
- 附属组件：`characteristic` 入口 `canopy` 与中庭 `railing`。
- 重复与模数：标准层高约 4.2m，柱网、窗格和栏板按同一开间节奏重复。
- 组装与依附：先柱梁板，再幕墙宿主和开口，最后雨棚、栏杆与坡道；详见下节。
- 降级映射：方柱用 `primitive.box` 视觉近似；幕墙用 `wall + window` 或 `primitive`，禁止新增幕墙专用类型。

### 园区独栋办公楼 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: park_detached_office
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 园区独栋办公楼
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- column ⊗ beam：梁端搁柱顶伸至柱心（搭接=1/2 柱宽 0.15m），梁底与柱顶平齐
- beam ⊗ floor：楼板现浇于梁上，板底与梁底平齐（板搁梁侧）
- 幕墙 ⊗ floor：幕墙立柱生根楼板外缘（预埋件），板边与幕墙留缝 0.02m 打胶
- window ⊗ 幕墙：窗组件挂幕墙墙，frameDepth=0.02 与墙厚相交
- railing ⊗ floor（中庭）：立柱锚入板内 0.05m，玻璃栏板嵌槽，扶手高 1.1m
- ramp ⊗ floor：坡道两端与地面/首层板面顺接（高差 0）

### 园区独栋办公楼 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: park_detached_office
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 园区独栋办公楼
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(square 0.3m, 柱距8.4m) → beam(0.25×0.5) → floor(0.15)；wall(幕墙0.02+内隔墙0.12)；玻璃幕墙四立面。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 商务写字楼标准层

<!-- rag-meta
entity_type: building
entity_name: business_office_standard_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 商务写字楼
  - 标准层
  - 核心筒
  - curtain wall
  - 默认完整构成
  - composition
synonyms:
  - office tower
-->

默认完整构成合同：

- 识别特征：核心筒集中交通；单元式玻璃幕墙；避难层；大堂通高入口雨棚。
- 空间与体量：`required` 高层标准层塔楼；`characteristic` 核心筒居中、立面模数化。
- 主体骨架：`required` 核心筒 `wall`、外框 `column/beam` 与标准层 `floor`。
- 外围护：`required / characteristic` 幕墙宿主 `wall` 与 `roof(flat)`。
- 开口组件：`required` 固定幕墙 `window` 和大堂 `door`，均依附真实 `parentWall`。
- 交通组件：`required` 核心筒 `stair`；入口 `ramp` 为 `conditional`。
- 附属组件：`characteristic` 大堂 `canopy`。
- 重复与模数：标准层高约 3.9m；标准层可用 `templates + instances` 复用，特殊层单独实例化。
- 组装与依附：楼板连核心筒与外框，幕墙挂于楼层外缘，门窗不承重；详见下节。
- 降级映射：方柱用 `primitive.box` 近似；幕墙用 `wall + window` 或 `primitive`，不写未注册类型。

### 商务写字楼标准层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: business_office_standard_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 商务写字楼标准层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 核心筒 wall ⊗ floor：板端搭入筒壁（搁置宽 ≥1/2 筒壁 0.15m），与筒壁整浇
- column ⊗ beam：梁端伸至柱心（搭接=1/2 柱宽 0.2~0.25m），节点现浇整体
- 幕墙 ⊗ floor：幕墙与楼板留缝 0.02m 打胶；立柱预埋件锚固板外缘
- stair ⊗ floor（核心筒）：梯梁端搭接各层板边，标高对齐（容差 0.2m）
- door ⊗ 大堂幕墙：门框嵌幕墙墙，玻璃门扇内凹 0.02m

### 商务写字楼标准层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: business_office_standard_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 商务写字楼标准层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(核心筒 0.30m) → column(外框 square 0.4~0.5) → beam(0.3×0.6)；wall(核心筒 0.30m)；核心筒集中交通。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 超高层写字楼加强层

<!-- rag-meta
entity_type: building
entity_name: supertall_office_outrigger_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 超高层写字楼
  - 加强层
  - 核心筒
  - 外伸臂
  - 默认完整构成
  - composition
synonyms:
  - supertall office
-->

默认完整构成合同：

- 识别特征：巨型 CFT 柱；伸臂桁架加强层；单元式幕墙；塔冠天线。
- 空间与体量：`required` 超高层收分塔楼；`characteristic` 加强层、设备层与塔冠层次。
- 主体骨架：`required` 核心筒 `wall`、巨柱近似、环带/伸臂 `beam` 组合与标准层 `floor`。
- 外围护：`required / characteristic` 单元式幕墙宿主 `wall` 和设备层 `roof(flat)`。
- 开口组件：`required` 固定幕墙 `window`，依附真实 `parentWall`。
- 交通组件：`required` 核心筒 `stair`。
- 附属组件：`characteristic / conditional` 入口 `canopy`、避难层/大堂 `light`。
- 重复与模数：标准层约 4.2m；加强层在标准层序列中独立插入并连接核心筒与外框。
- 组装与依附：先核心筒和巨柱，再加强层梁与楼板，最后幕墙和附属组件；详见下节。
- 降级映射：CFT、桁架和塔冠无专用类型，分别用 `column/primitive`、`beam/primitive` 近似；幕墙不新增类型。

### 超高层写字楼加强层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: supertall_office_outrigger_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 超高层写字楼加强层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 巨柱 ⊗ 核心筒（伸臂层）：伸臂 beam 两端分别伸入核心筒壁与外框柱心（搭接 ≥0.4m）
- 核心筒 ⊗ floor：板端搭入筒壁整浇，分段收进处筒壁变厚
- 巨柱 ⊗ beam：标准层梁端伸至柱心（搭接=1/2 柱宽 0.3~0.4m）
- 幕墙 ⊗ 巨柱：单元式幕墙挂于柱外侧，与柱外缘平齐
- stair ⊗ 避难层：疏散梯在避难层设转换平台，标高对齐

### 超高层写字楼加强层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: supertall_office_outrigger_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 超高层写字楼加强层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(核心筒 0.3~0.6 分段) → column(巨型 0.6~0.8) → beam(0.4×0.7 + 伸臂 beam 组合)；wall(核心筒 0.3~0.6 分段)；巨型 CFT 柱。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 幼儿园活动室单元

<!-- rag-meta
entity_type: building
entity_name: kindergarten_activity_unit
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 幼儿园
  - 活动室
  - 低窗台
  - 雨棚
  - 默认完整构成
  - composition
synonyms:
  - kindergarten
-->

默认完整构成合同：

- 识别特征：低矮体量；圆角墙；低窗台大窗；加高栏杆；屋顶活动平台
- 空间与体量：幼儿园，强制 ≤3 层。红砖外墙圆角处理，教室开间 6~9m、进深 6~7.2m、净高 3.3m， 外廊式走廊加高栏杆（1.2m），低窗台（0.6m），楼梯踏步高 ≤0.15m，屋顶可上人活动， 室外活动场地 + 游乐设施。整体亲切明快、尺度小巧、色彩温暖。
- 主体骨架：`required` — wall(外墙0.24 + 隔墙0.12) → floor(0.12)
- 外围护：`required / characteristic` — wall(外墙0.24 + 隔墙0.12) → roof(flat 可上人)
- 开口组件：`required / characteristic` — door(教室门 w=1.0 附观察窗) → window(滑窗 w 窗地比1:5, 台0.6)；依附真实 `parentWall`。
- 交通组件：`required` — stair(踏步≤0.15) → ramp(1:12)
- 附属组件：`characteristic / conditional` — railing(外廊1.2 + 屋顶1.2)
- 重复与模数：层高 3.3m：wall.to[1]=3.3；窗 from[1]=0.6（低台）；楼梯 stair 步高≤0.15 → 自动推算或显式 stepCount
- 组装与依附：wall(0.24 圆角) 围护；floor 每层 + 屋顶平台；door(带观察窗) + window(低台滑窗) 挂墙；详见下节。
- 降级映射：游乐设施 furniture(subtype=custom) 受限 → 用 primitive 组合表达；圆角/椭圆 → arc 墙段或 primitive 分段

### 幼儿园活动室单元 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: kindergarten_activity_unit
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 幼儿园活动室单元
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- wall ⊗ wall（角部）：两端延伸至对墙外表面（搭接=墙厚 0.24m）封口
- window ⊗ wall：窗组件挂外墙，窗台高 0.6（坐姿儿童视线），窗地比≥1:5
- railing ⊗ floor（外廊）：立柱锚入板内 0.05m，栏杆高 1.2m（儿童防护加高）
- stair ⊗ floor：梯梁端搭接板边，踏步高≤0.15（防跌落）
- roof ⊗ wall（屋顶平台）：上人屋面板搭墙顶，四周 railing 1.2m

### 幼儿园活动室单元 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: kindergarten_activity_unit
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 幼儿园活动室单元
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(外墙0.24 + 隔墙0.12) → floor(0.12)；wall(外墙0.24 + 隔墙0.12)；低矮体量。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 中小学教学楼标准层

<!-- rag-meta
entity_type: building
entity_name: school_teaching_standard_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 中小学教学楼
  - 标准教室
  - 外廊
  - 内廊
  - 默认完整构成
  - composition
synonyms:
  - school building
-->

默认完整构成合同：

- 识别特征：规整教室单元；防眩光窗布置；走廊栏板；观察窗教室门
- 空间与体量：中小学，小学 ≤4F、中学 ≤6F。砖混外墙 0.24m + 构造柱抗震，教室 9×6m（黑板 3.6~4.0m 宽）， 外廊/内廊，窗间墙≤1.2m、前端侧窗端墙≥1.0m（防眩光），墙裙小学 1.2m/中学 1.4m，楼梯 1.2m 宽。 外观规整、开窗规律、明快安全。
- 主体骨架：`required` — wall(外墙0.24 + 隔墙0.12 + 黑板墙) → column(构造柱0.24) → floor(0.12)
- 外围护：`required / characteristic` — wall(外墙0.24 + 隔墙0.12 + 黑板墙) → roof(flat/gable)
- 开口组件：`required / characteristic` — door(教室门附观察窗) → window(滑窗)；依附真实 `parentWall`。
- 交通组件：`required` — stair → ramp(1:12)
- 附属组件：`characteristic / conditional` — railing(走廊1.1)
- 重复与模数：层高 3.0m；窗 from[1]=0.9、窗间墙≤1.2m；黑板墙无窗
- 组装与依附：wall(0.24+构造柱) 承重；floor 每层；door(带观察窗) + window(防眩光布置) 挂墙；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 中小学教学楼标准层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: school_teaching_standard_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 中小学教学楼标准层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 构造柱 ⊗ wall：柱嵌于墙端/墙交点，柱边与墙面平齐（马牙槎咬合）
- window ⊗ wall：窗间墙≤1.2m、前端侧窗端墙≥1.0m（防眩光），同墙窗不重叠
- door ⊗ wall：教室门附观察窗（门扇内嵌），净宽≥1.0
- railing ⊗ floor（走廊）：立柱锚板 0.05m，高 1.1m
- stair ⊗ floor：疏散梯 2~4 部，梯梁端搭接板边

### 中小学教学楼标准层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: school_teaching_standard_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 中小学教学楼标准层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(外墙0.24 + 隔墙0.12 + 黑板墙) → column(构造柱0.24) → floor(0.12)；wall(外墙0.24 + 隔墙0.12 + 黑板墙)；规整教室单元。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 大学教学楼标准层

<!-- rag-meta
entity_type: building
entity_name: university_teaching_standard_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 大学教学楼
  - 合班教室
  - 教学楼
  - 默认完整构成
  - composition
synonyms:
  - university teaching building
-->

默认完整构成合同：

- 识别特征：规整柱网；报告厅大跨；成组教室单元
- 空间与体量：大学教学楼，框架结构，柱网 7.2~8.4m，层高 3.6m，外墙 AAC 砌块填充，报告厅大跨 无柱（12~18m），教室门 flush、窗 casement。外观现代规整，教学单元重复排列。
- 主体骨架：`required` — column(0.4) → beam(0.3×0.6) → floor(0.15) → wall(0.20 填充 + 0.12 内隔)
- 外围护：`required / characteristic` — wall(0.20 填充 + 0.12 内隔) → roof(flat)
- 开口组件：`required / characteristic` — door(教室门 flush) → window(casement)；依附真实 `parentWall`。
- 交通组件：`required` — stair(宽1.4)
- 附属组件：`characteristic / conditional` — canopy(入口 depth=2.5) → railing(走廊)
- 重复与模数：层高 3.6m；报告厅大跨：多根主梁并列（beam 组合，span 12~18m）
- 组装与依附：column(0.4) 承托 beam+floor；wall(0.20 AAC) 围护；door/window 挂墙；报告厅用 beam 组合大跨；详见下节。
- 降级映射：truss（报告厅）无原生类型 → beam 组合表达

### 大学教学楼标准层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: university_teaching_standard_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 大学教学楼标准层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- column ⊗ beam：梁端伸柱心（搭接=1/2 柱宽 0.2m）
- 填充墙 ⊗ beam/floor：AAC 砌块墙顶抵梁底、底落板面，端贴柱外缘
- 大跨 beam ⊗ 报告厅墙：主梁两端支承于报告厅两侧框架梁上（搭接≥0.3m）
- window ⊗ wall：窗组件挂墙，casement 外开

### 大学教学楼标准层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: university_teaching_standard_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 大学教学楼标准层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.4) → beam(0.3×0.6) → floor(0.15)；wall(0.20 填充 + 0.12 内隔)；规整柱网。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 实验室单元

<!-- rag-meta
entity_type: building
entity_name: laboratory_unit
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 实验室
  - 实验单元
  - 服务走廊
  - 设备带
  - 默认完整构成
  - composition
synonyms:
  - laboratory
-->

默认完整构成合同：

- 识别特征：厚重墙；隔振台基；通风竖井；实验台排布
- 空间与体量：实验室，强制低层（精密仪器振动敏感）。钢筋混凝土外墙 0.30m，独立隔振台基 0.30m + 防振沟，框架柱 0.5m 减振节点，梁 0.35×0.7m，楼板 0.20m 荷载加大，通风柜靠墙排风竖井， 实验台防酸碱。外观厚重封闭、科技感。
- 主体骨架：`required` — floor(隔振台基0.30) → column(0.5) → beam(0.35×0.7) → floor(0.20 防振) → wall(0.30 外墙 + 通风竖井)
- 外围护：`required / characteristic` — wall(0.30 外墙 + 通风竖井)
- 开口组件：`required / characteristic` — door(实验室门) → window(casement)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — furniture 元素(实验台/通风柜位)
- 重复与模数：层高 4.2~5.0m；台基独立于外墙基础（防振沟分隔）；通风柜靠墙留洞口
- 组装与依附：wall(0.30) 围护；floor(隔振台基 0.30) 独立；column+beam 框架；furniture(实验台) 布置；详见下节。
- 降级映射：placement 非当前正式业务类型 → primitive 组合表达

### 实验室单元 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: laboratory_unit
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 实验室单元
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 隔振台基 ⊗ 外墙基础：台基与外墙基础**脱开**（防振沟，碰撞警示：不得搭接）
- column ⊗ 台基：柱底落于台基面，减振节点隔振垫
- 通风竖井 ⊗ floor：井壁与各层板搭接，排风口上下对位
- furniture ⊗ floor：实验台置于楼板面，不嵌入

### 实验室单元 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: laboratory_unit
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 实验室单元
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(隔振台基0.30) → column(0.5) → beam(0.35×0.7)；wall(0.30 外墙 + 通风竖井)；厚重墙。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 博物馆展厅

<!-- rag-meta
entity_type: building
entity_name: museum_gallery
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 博物馆
  - 展厅
  - 大空间
  - 受控采光
  - 默认完整构成
  - composition
synonyms:
  - museum
-->

默认完整构成合同：

- 识别特征：少柱大跨展厅；顶部漫射天窗；通高入口大厅；可移动展墙。
- 空间与体量：`required` 高净空展陈体量；`characteristic` 大跨大厅与连续展墙。
- 主体骨架：`required` 大间距 `column`、大跨 `beam`、承托 `floor`。
- 外围护：`required` 厚重 `wall` 与 `roof(flat/dome)`。
- 开口组件：`required / characteristic` 入口 `door`、高侧 `window`；屋顶采光不使用 `window.parentRoof`。
- 交通组件：`conditional` 有跨层展厅时补 `stair/ramp`。
- 附属组件：`characteristic / conditional` 展厅 `light`、大厅/楼座 `railing`。
- 重复与模数：柱距与层高取来源范围；展墙按展陈单元重复，入口大厅保持通高。
- 组装与依附：柱梁承屋盖，围护控制开口，展墙与灯具后置；详见下节。
- 降级映射：天窗用透明 `roof/primitive`，展柜和导览设施用 `furniture/primitive` 近似。

### 博物馆展厅 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: museum_gallery
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 博物馆展厅
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- column ⊗ beam：大跨梁端伸柱心（搭接=1/2 柱宽 0.25m）
- 天窗 ⊗ 屋面墙：天窗洞口开于顶部围护，防 UV 玻璃内嵌，洞口四周泛水
- 可移动隔墙 ⊗ floor：轻质墙底落板面，**不锚固**（可灵活挪动，碰撞警示：不与结构柱碰撞）
- railing ⊗ floor（中庭）：通高洞口临边玻璃栏 1.1m
- door ⊗ 大厅墙：入口玻璃门 w=3.0 双扇

### 博物馆展厅 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: museum_gallery
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 博物馆展厅
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5, 间距12~18m) → beam(0.4×0.8 大跨) → floor(0.15 荷载≥5kN/㎡)；wall(0.24 + 可移动0.08)；少柱大跨展厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 剧院观众厅

<!-- rag-meta
entity_type: building
entity_name: theater_auditorium
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 剧院
  - 观众厅
  - 舞台塔
  - 楼座
  - 默认完整构成
  - composition
synonyms:
  - theater
-->

默认完整构成合同：

- 识别特征：弧形声学观众厅；超高舞台塔；下沉乐池；前厅柱廊
- 空间与体量：剧院/音乐厅，天然大跨单层（不做高层，舞台上部需 2.5 倍台口高度）。观众厅弧形声学墙 （避免平行墙面颤动回声），舞台塔超高（≥30m），屋盖桁架跨主台口，乐池下沉，声学吊顶 反射板阵列，前厅柱廊，四周疏散梯。外观庄重、声学造型突出。
- 主体骨架：`required` — wall(弧形声学墙0.3 + 舞台塔墙) → column(前厅柱廊 doric/modern) → beam(0.4×0.6 + 屋盖 beam 组合) → floor(乐池下沉 + 面光桥悬挑)
- 外围护：`required / characteristic` — wall(弧形声学墙0.3 + 舞台塔墙)
- 开口组件：`required / characteristic` — door(舞台大门 w=4.0 h=6.0)；依附真实 `parentWall`。
- 交通组件：`required` — stair(疏散)
- 附属组件：`characteristic / conditional` — railing(楼座/池座) → light(舞台灯) → furniture 元素(座椅 primitive)
- 重复与模数：观众厅弧形 wall 用 curve=arc；乐池 floor 下沉 1.5m；舞台塔墙高≥30m
- 组装与依附：wall(弧形) 围合观众厅；column 前厅柱廊；beam 组合屋盖桁架；floor(乐池下沉/声学吊顶)；详见下节。
- 降级映射：truss（屋盖）无原生类型 → beam 组合；座椅 furniture 用 primitive 阵列

### 剧院观众厅 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: theater_auditorium
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 剧院观众厅
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 弧形墙 ⊗ 弧形墙：弧墙两端与直墙相交，端部延伸封口；弧墙仅单段 arc（门窗宿主约束）
- 乐池 floor ⊗ 观众厅墙：下沉板边搭于弧形墙内侧，池边栏杆 1.1m
- 面光桥 floor ⊗ 屋盖梁：悬挑板端锚固于屋盖梁，挂于观众厅上方
- 舞台大门 door ⊗ 舞台塔墙：门洞 w=4.0 h=6.0 布景进出，门框嵌墙
- 柱廊 column ⊗ beam：前厅梁端伸柱心（搭接=1/2 柱径）

### 剧院观众厅 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: theater_auditorium
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 剧院观众厅
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(弧形声学墙0.3 + 舞台塔墙) → column(前厅柱廊 doric/modern) → beam(0.4×0.6 + 屋盖 beam 组合)；wall(弧形声学墙0.3 + 舞台塔墙)；弧形声学观众厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 图书馆标准层

<!-- rag-meta
entity_type: building
entity_name: library_standard_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 图书馆
  - 阅览区
  - 书库
  - 中庭
  - 默认完整构成
  - composition
synonyms:
  - library
-->

默认完整构成合同：

- 识别特征：少柱阅览大厅；通高中庭；密集书库；天窗漫射光
- 空间与体量：图书馆，密集书库楼板荷载 ≥12kN/㎡（厚 0.20m），阅览大厅少柱（柱距 9~12m）、大跨梁， 中庭 3~5 层通高 + 玻璃栏板，天窗漫射采光（避免直射），阅览窗玻璃 opacity 0.25，宽大 楼梯。外观文雅厚重、光环境安静。
- 主体骨架：`required` — column(0.5) → beam(0.4×0.8) → floor(书库0.20 / 标准0.15) → wall(0.24)
- 外围护：`required / characteristic` — wall(0.24) → roof(flat/dome)
- 开口组件：`required / characteristic` — window(阅览窗 fixed opacity0.25 / 天窗) → door(玻璃门)；依附真实 `parentWall`。
- 交通组件：`conditional` — 来源未单列；有跨层/高差时再补。
- 附属组件：`characteristic / conditional` — railing(中庭玻璃栏) → light(阅览灯)
- 重复与模数：层高 4.2m；中庭各层 floor 留洞（用开洞 floor 表达）；屋顶天窗没有原生 parentRoof 开洞，改用透明 roof 或 primitive 近似
- 组装与依附：column(9~12m) + beam 承重；floor(书库0.20) 各层；wall 围护；opening(天窗) + window；railing 沿中庭；详见下节。
- 降级映射：书架/桌椅 furniture → primitive 组合；原 autoRailing(中庭) → railing 组件；屋顶天窗 → 透明 roof/primitive；没有 window.parentRoof

### 图书馆标准层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: library_standard_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 图书馆标准层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 中庭 floor ⊗ 楼板：各层环廊板端搭入外墙，临中庭侧 railing 玻璃栏 1.1m（防坠）
- 书库 floor ⊗ 柱：板端搭于柱侧主梁，荷载≥12kN/㎡ 板厚 0.20
- 天窗 ⊗ 屋面：天窗框与屋面搭接，泛水卷材上翻 0.25m
- window ⊗ wall：阅览窗固定扇，玻璃 opacity 0.25 防直射

### 图书馆标准层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: library_standard_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 图书馆标准层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5) → beam(0.4×0.8) → floor(书库0.20 / 标准0.15)；wall(0.24)；少柱阅览大厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 中小型体育馆

<!-- rag-meta
entity_type: building
entity_name: small_medium_gymnasium
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 体育馆
  - 中小型体育馆
  - 大跨
  - 看台
  - 默认完整构成
  - composition
synonyms:
  - gymnasium
-->

默认完整构成合同：

- 识别特征：大跨屋盖；阶梯看台；运动木地板；疏散楼梯环绕
- 空间与体量：中小型体育馆，跨度 30~60m，可做篮球/羽毛球/体操多功能。框架柱 0.5×0.7m，屋盖 桁架跨 30~60m，金属屋面，看台踏步 28~34° 逐级抬高，场地木地板，四周疏散梯，入口 大门 + 雨棚。外观简洁、大跨屋面突出。
- 主体骨架：`required` — column(0.5×0.7) → beam(屋盖组合) → floor(看台踏步逐级 + 场地0.15) → wall(0.24 围护)
- 外围护：`required / characteristic` — wall(0.24 围护) → roof(flat/curved 金属)
- 开口组件：`required / characteristic` — door(入口玻璃门 w=3.0)；依附真实 `parentWall`。
- 交通组件：`required` — stair(疏散)
- 附属组件：`characteristic / conditional` — railing(看台前沿1.1) → canopy(入口 depth=4.0) → light(场地灯)
- 重复与模数：看台 floor 逐级抬高（每级 0.35m 高差）；屋盖梁底 ≥ 场地净高（≥9m）
- 组装与依附：column(0.5×0.7) + beam 组合屋盖；floor(看台逐级 + 场地木地板)；wall 围护；railing 沿看台前沿；详见下节。
- 降级映射：truss（屋盖）无原生类型 → beam 组合；原 furniture(座椅) → primitive 阵列；方/矩形柱 → primitive.box 视觉近似；原生 column 为圆/锥柱

### 中小型体育馆 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: small_medium_gymnasium
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 中小型体育馆
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 屋盖 beam ⊗ 柱：大跨主梁端伸柱心（搭接=1/2 柱宽），多榀并列
- 看台 floor ⊗ 框架：看台板逐级搭于斜梁/阶梁上，前端收边
- railing ⊗ 看台前沿：立柱锚入看台板 0.05m，高 1.1m
- 场地 floor ⊗ 看台：运动木地板与看台起始级顺接（高差 0）

### 中小型体育馆 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: small_medium_gymnasium
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 中小型体育馆
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5×0.7) → beam(屋盖组合) → floor(看台踏步逐级 + 场地0.15)；wall(0.24 围护)；大跨屋盖。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 大型体育场看台单元

<!-- rag-meta
entity_type: building
entity_name: stadium_stand_unit
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 体育场
  - 看台单元
  - 罩棚
  - 场地
  - 默认完整构成
  - composition
synonyms:
  - stadium
-->

默认完整构成合同：

- 识别特征：椭圆环墙；悬挑罩棚；阶梯看台；跑道足球场
- 空间与体量：大型体育场，看台坡度 28~34°（C 值法视线），罩棚悬挑 30~70m，膜/金属屋面，椭圆形 环墙，巨型柱 0.8×1.0m，400m 标准跑道 + 标准足球场（105×68m），疏散楼梯绕看台布置。 外观气势恢宏、罩棚悬挑飘逸。
- 主体骨架：`required` — wall(椭圆环墙 curve=ellipse 0.3m) → column(0.8×1.0 巨柱) → beam(罩棚悬挑组合) → floor(看台 20~40 级 + 草坪 + 跑道)
- 外围护：`required / characteristic` — wall(椭圆环墙 curve=ellipse 0.3m) → roof(膜结构 flat)
- 开口组件：`required / characteristic` — door(入口玻璃门)；依附真实 `parentWall`。
- 交通组件：`required` — stair(疏散)
- 附属组件：`characteristic / conditional` — railing(看台前沿1.1) → light(场地灯柱)
- 重复与模数：跑道 400m（半径 36.5m 两直道）；看台每级高差 0.35m；罩棚梁端锚固巨柱
- 组装与依附：wall(椭圆) 围合；column(巨柱) 支撑罩棚 beam 组合；floor(看台逐级 + 跑道/草坪)；railing 沿看台；详见下节。
- 降级映射：truss（罩棚）无原生类型 → beam 组合；膜屋面用 roof(flat) + 材质表达；方/矩形柱 → primitive.box 视觉近似；原生 column 为圆/锥柱；圆角/椭圆 → arc 墙段或 primitive 分段

### 大型体育场看台单元 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: stadium_stand_unit
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 大型体育场看台单元
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 罩棚 beam ⊗ 巨柱：悬挑梁端伸入柱心（搭接≥0.4m），环向多榀
- 看台 floor ⊗ 环墙：看台板逐级搭于环墙内侧斜梁，端部收边
- railing ⊗ 看台前沿：立柱锚板 0.05m，高 1.1m
- 草坪/跑道 ⊗ 场地：足球场草坪与跑道内缘顺接（高差 0）

### 大型体育场看台单元 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: stadium_stand_unit
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 大型体育场看台单元
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(椭圆环墙 curve=ellipse 0.3m) → column(0.8×1.0 巨柱) → beam(罩棚悬挑组合)；wall(椭圆环墙 curve=ellipse 0.3m)；椭圆环墙。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 室内游泳馆

<!-- rag-meta
entity_type: building
entity_name: indoor_natatorium
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 游泳馆
  - 泳池大厅
  - 大跨屋顶
  - 默认完整构成
  - composition
synonyms:
  - natatorium
-->

默认完整构成合同：

- 识别特征：下沉泳池；大跨防腐屋盖；池边玻璃栏；通风除湿竖井
- 空间与体量：室内游泳馆，大跨屋盖（40~60m）防腐金属，框架柱防腐处理，外墙防潮钢板，下沉泳池 池体（贴瓷砖防水），池边玻璃栏杆，看台逐级，除湿通风竖井，更衣室防潮隔墙。外观 通透湿润、防腐构造突出。
- 主体骨架：`required` — column(0.5×0.7 防腐) → beam(屋盖组合 40~60m) → floor(池体下沉 1.8m + 看台) → wall(0.24 防潮 + 通风竖井)
- 外围护：`required / characteristic` — wall(0.24 防潮 + 通风竖井) → roof(flat 防腐金属)
- 开口组件：`required / characteristic` — door(入口玻璃门)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — railing(池边玻璃栏1.1) → light(水下灯/场地灯)
- 重复与模数：池体 floor 下沉（from[1]=-1.8）；池边标高与地面顺接；屋盖梁底 ≥ 池区净高
- 组装与依附：column + beam(屋盖组合)；floor(池体下沉 + 看台)；wall(防潮围护 + 通风井)；railing 沿池边；详见下节。
- 降级映射：truss（warren）无原生类型 → beam 组合；方/矩形柱 → primitive.box 视觉近似；原生 column 为圆/锥柱

### 室内游泳馆 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: indoor_natatorium
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 室内游泳馆
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 池体 floor ⊗ 结构：池体为下沉独立结构，与看台/外墙留缝设变形缝
- railing ⊗ 池边：玻璃栏立柱锚入池边压顶，高 1.1m
- 通风竖井 ⊗ 屋盖：除湿风井穿屋面，泛水卷材上翻 0.25m
- 看台 floor ⊗ 池边：看台起始级与池边标高顺接

### 室内游泳馆 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: indoor_natatorium
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 室内游泳馆
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5×0.7 防腐) → beam(屋盖组合 40~60m) → floor(池体下沉 1.8m + 看台)；wall(0.24 防潮 + 通风竖井)；下沉泳池。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 社区医疗诊室单元

<!-- rag-meta
entity_type: building
entity_name: community_clinic_unit
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 社区医疗
  - 诊室
  - 候诊区
  - 默认完整构成
  - composition
synonyms:
  - community clinic
-->

默认完整构成合同：

- 识别特征：候诊大厅；诊室单元（观察窗门）；无障碍坡道
- 空间与体量：社区医院/门诊部，≤3 层。框架柱 0.4m（间距 6~9m），诊室隔墙开间≥3.0m、进深≥3.9m、 面积≥12㎡，诊室门附观察窗，候诊大厅 + 候诊座椅，无障碍坡道。外观简洁明快、功能导向。
- 主体骨架：`required` — column(0.4) → beam → floor(0.15) → wall(0.24 外墙 + 0.12 诊室隔墙)
- 外围护：`required / characteristic` — wall(0.24 外墙 + 0.12 诊室隔墙) → roof(flat)
- 开口组件：`required / characteristic` — door(诊室门附观察窗) → window(casement w=1.5)；依附真实 `parentWall`。
- 交通组件：`required` — stair → ramp(1:12)
- 附属组件：`optional` — 来源未单列。
- 重复与模数：层高 3.6m；诊室 3.0×3.9m；窗台 0.9
- 组装与依附：column+beam+floor 框架；wall 隔墙；door(观察窗) + window 挂墙；ramp 无障碍；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 社区医疗诊室单元 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: community_clinic_unit
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 社区医疗诊室单元
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 诊室隔墙 ⊗ 外墙：隔墙端贴外墙内缘，内表面平齐
- door ⊗ 隔墙：诊室门净宽≥1.0，附观察窗
- ramp ⊗ 地面：坡道与首层地面顺接（高差 0）

### 社区医疗诊室单元 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: community_clinic_unit
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 社区医疗诊室单元
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.4) → beam → floor(0.15)；wall(0.24 外墙 + 0.12 诊室隔墙)；候诊大厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 综合医院住院标准层

<!-- rag-meta
entity_type: building
entity_name: general_hospital_ward_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 综合医院
  - 住院标准层
  - 病房
  - 护士站
  - 默认完整构成
  - composition
synonyms:
  - general hospital
-->

默认完整构成合同：

- 识别特征：洁污分流双通道；防辐射厚墙；手术室气密门；南向病房
- 空间与体量：综合医院，门诊/医技/住院分区，洁污分流（污物通道与洁物完全独立）。防辐射机房墙 厚≥0.5m（铅板/硫酸钡），手术室气密门净宽≥1.4m、净高≥2.7m、层流净化，洁净走廊 净宽≥2.5m，病房南向 3.6×7.5m，核心筒集中电梯/楼梯，护士站半围合，输液轨道。 外观理性高效、流线清晰。
- 主体骨架：`required` — wall(核心筒0.3 + 防辐射0.5 + 病房隔墙0.12 + 污物竖井) → column(0.5) → floor(0.15~0.20)
- 外围护：`required / characteristic` — wall(核心筒0.3 + 防辐射0.5 + 病房隔墙0.12 + 污物竖井) → roof(flat)
- 开口组件：`required / characteristic` — door(气密门 w=1.4 / 病房门 w=0.9) → window(病房 casement w=1.8)；依附真实 `parentWall`。
- 交通组件：`required` — stair(疏散) → ramp
- 附属组件：`characteristic / conditional` — railing(走道扶手)
- 重复与模数：病房 3.6×7.5m 南向；手术室净高≥2.7m；防辐射墙厚 0.5~0.6
- 组装与依附：wall(核心筒+防辐射墙0.5+病房隔墙) 围合；floor 各层；door(气密门/病房门) + window 挂墙；furniture 病床；详见下节。
- 降级映射：输液轨道原 placement → primitive 组合；病床 furniture(bed)

### 综合医院住院标准层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: general_hospital_ward_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 综合医院住院标准层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 防辐射墙 ⊗ 结构：机房墙与结构脱开或整浇，铅板衬里贴墙面（碰撞警示：不得开普通窗洞）
- 洁污通道 wall ⊗ wall：污物竖井独立围合，与洁物通道**不交叉**（流线碰撞规避）
- door ⊗ 病房隔墙：气密门框嵌墙，门扇与门框严密贴合（气密）
- 护士站 ⊗ 走道：半围合墙贴走道一侧，开敞面朝病房区

### 综合医院住院标准层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: general_hospital_ward_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 综合医院住院标准层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(核心筒0.3 + 防辐射0.5 + 病房隔墙0.12 + 污物竖井) → column(0.5) → floor(0.15~0.20)；wall(核心筒0.3 + 防辐射0.5 + 病房隔墙0.12 + 污物竖井)；洁污分流双通道。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 专科医院设备机房单元

<!-- rag-meta
entity_type: building
entity_name: specialist_hospital_plant_unit
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 专科医院
  - 设备机房
  - 医疗设备
  - 默认完整构成
  - composition
synonyms:
  - specialist hospital
-->

默认完整构成合同：

- 识别特征：专科差异化机房/病房；防护与隔离构造
- 空间与体量：专科医院，在综合医院基础上按专科调整：妇幼医院 LDR 家庭化产房（3.6×6.0m 温馨色彩）， 肿瘤医院加速器机房（墙厚≥1.0m 含铁板/混凝土迷路），口腔医院牙科治疗位排列，精神病院 防护窗（fixed 无把手内开、安全玻璃），传染病院负压隔离病房（负压梯度、气密门、独立通风）。
- 主体骨架：`required` — wall(1.0m 迷路)；传染病 → wall(负压隔离) ；精神病 → wall + window(fixed)
- 外围护：`required / characteristic` — wall(1.0m 迷路)；传染病 → wall(负压隔离) ；精神病 → wall + window(fixed)
- 开口组件：`required / characteristic` — door(气密门/铁栅门) → window(fixed 安全玻璃)；依附真实 `parentWall`。
- 交通组件：`required` — ramp(无障碍)
- 附属组件：`optional` — 来源未单列。
- 重复与模数：加速器机房墙厚≥1.0m；负压病房独立通风竖井；防护窗无把手内开
- 组装与依附：按专科换 wall(厚墙/隔离墙) + door(气密/铁栅) + window(fixed 防护)；其余同综合医院；详见下节。
- 降级映射：furniture(牙科椅等) → primitive 组合

### 专科医院设备机房单元 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: specialist_hospital_plant_unit
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 专科医院设备机房单元
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 迷路墙 ⊗ 机房：加速器迷路墙交错咬合（防射线直射），门洞错位布置
- 负压隔离墙 ⊗ 风井：隔离病房独立负压风井，与病房区正压区不串通
- 防护窗 ⊗ 病房墙：fixed 窗内嵌安全玻璃，无开启（防自伤）

### 专科医院设备机房单元 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: specialist_hospital_plant_unit
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 专科医院设备机房单元
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(1.0m 迷路)；传染病 → wall(负压隔离) ；精神病 → wall + window(fixed)；wall(1.0m 迷路)；传染病；专科差异化机房/病房。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 社区商业

<!-- rag-meta
entity_type: building
entity_name: community_commercial
building_category: commercial
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 社区商业
  - 沿街商铺
  - 店面
  - 默认完整构成
  - composition
synonyms:
  - neighborhood retail
-->

默认完整构成合同：

- 识别特征：大面积橱窗；沿街雨棚；首层高空间
- 空间与体量：社区商业/邻里中心，≤2 层。框架柱网 6~8m，首层层高 4.5~5.5m，大面积橱窗与玻璃门， 沿街雨棚连排，屋顶平屋面。外观亲切、商业氛围浓。
- 主体骨架：`required` — column(0.4) → floor(首层 4.5~5.5m) → wall(0.24 外墙 + 0.12 商铺隔墙)
- 外围护：`required / characteristic` — wall(0.24 外墙 + 0.12 商铺隔墙) → roof(flat)
- 开口组件：`required / characteristic` — door(商铺门 w=1.5 glass) → window(橱窗 fixed)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — canopy(沿街 depth=1.5 bracket) → railing(二层外廊)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column+beam+floor 框架；wall 围护；door(商铺玻璃门) + window(橱窗 fixed) 挂墙；canopy 沿街；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 社区商业 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: community_commercial
building_category: commercial
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 社区商业
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 橱窗 ⊗ 外墙：落地橱窗 fixed 玻璃，窗台 0.3m（陈列）
- canopy ⊗ 外墙：雨棚根部锚墙 0.15m，沿街面连续
- 商铺隔墙 ⊗ 楼板：隔墙底搭板、顶抵上层板底

### 社区商业 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: community_commercial
building_category: commercial
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 社区商业
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.4) → floor(首层 4.5~5.5m) → wall(0.24 外墙 + 0.12 商铺隔墙)；wall(0.24 外墙 + 0.12 商铺隔墙)；大面积橱窗。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 购物中心标准层

<!-- rag-meta
entity_type: building
entity_name: shopping_center_standard_floor
building_category: commercial
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 购物中心
  - 中庭
  - 商业标准层
  - 默认完整构成
  - composition
synonyms:
  - shopping mall
-->

默认完整构成合同：

- 识别特征：通高中庭 + 玻璃栏板；采光顶；自动扶梯；商铺阵列
- 空间与体量：购物中心/商场，极少超 7 层。中庭 3~7 层通高 + 玻璃栏板 + 顶部采光顶，商铺轻质隔墙 面宽 8~12m，首层 5.4~6.0m、标准层 4.5~5.4m，自动扶梯跨层，玻璃幕墙外立面，货梯井。 外观通透繁华、中庭为核心。
- 主体骨架：`required` — column(0.5) → beam(0.35×0.7) → floor(首层0.15/标准0.15, 中庭留洞) → wall(幕墙 + 商铺隔墙0.08)
- 外围护：`required / characteristic` — wall(幕墙 + 商铺隔墙0.08) → roof(flat)
- 开口组件：`required / characteristic` — window(采光顶 fixed) → door(入口自动门)；依附真实 `parentWall`。
- 交通组件：`required` — stair(扶梯)
- 附属组件：`characteristic / conditional` — railing(中庭玻璃栏) → canopy(入口 depth=3.0) → light(中庭灯)
- 重复与模数：中庭 floor 各层留洞（用开洞表达）；扶梯 stair 30° 跨 1~2 层
- 组装与依附：column(8.4×8.4) + beam 框架；floor 各层留洞(中庭)；wall(幕墙+轻质商铺隔墙)；railing 沿中庭；stair(扶梯)；详见下节。
- 降级映射：原 opening(采光顶)+window → window 组件挂屋面墙；幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型；自动扶梯 → stair/ramp 静态近似

### 购物中心标准层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: shopping_center_standard_floor
building_category: commercial
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 购物中心标准层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 中庭 railing ⊗ floor：各层留洞边玻璃栏 1.1m（防坠）
- 扶梯 stair ⊗ floor：扶梯两端搭接相邻层板边，30° 倾斜
- 商铺隔墙 ⊗ 环廊：轻质墙端贴环廊边，面宽 8~12m
- 采光顶 ⊗ 屋面：天窗框与屋面搭接，泛水上翻 0.25m

### 购物中心标准层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: shopping_center_standard_floor
building_category: commercial
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 购物中心标准层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5) → beam(0.35×0.7) → floor(首层0.15/标准0.15, 中庭留洞)；wall(幕墙 + 商铺隔墙0.08)；通高中庭 + 玻璃栏板。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 超市营业厅

<!-- rag-meta
entity_type: building
entity_name: supermarket_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 超市
  - 营业厅
  - 大开间
  - 货架
  - 默认完整构成
  - composition
synonyms:
  - supermarket
-->

默认完整构成合同：

- 识别特征：大空间少柱；货架区；收银阵列；冷库隔墙
- 空间与体量：超市，1~2 层。框架柱网 8.4m，层高 4.5~5.5m，大空间少隔墙，货架排列区，收银台阵列， 冷库保温隔墙，入口自动感应玻璃门 + 雨棚，屋顶平屋面。外观简洁、仓储感。
- 主体骨架：`required` — column(0.5) → beam(0.3×0.6) → floor(0.15) → wall(0.24 外墙 + 冷库保温墙)
- 外围护：`required / characteristic` — wall(0.24 外墙 + 冷库保温墙) → roof(flat)
- 开口组件：`required / characteristic` — door(入口自动门 w=3.0)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — canopy(depth=3.0) → light(仓储灯)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(8.4m) + beam 大跨；floor(4.5~5.5m)；wall(冷库保温隔墙)；door(自动门)；canopy 入口；详见下节。
- 降级映射：placement 非当前正式业务类型 → 用 primitive 或省略；收银台 wall 半围合 + furniture

### 超市营业厅 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: supermarket_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 超市营业厅
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 冷库墙 ⊗ 外墙：保温隔墙端贴外墙内缘，接缝密封
- 入口 door ⊗ 外墙：自动感应门框嵌墙，双扇
- 收银台 ⊗ floor：半围合台体落地，不锚固

### 超市营业厅 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: supermarket_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 超市营业厅
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5) → beam(0.3×0.6) → floor(0.15)；wall(0.24 外墙 + 冷库保温墙)；大空间少柱。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 经济型酒店客房层

<!-- rag-meta
entity_type: building
entity_name: economy_hotel_guest_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 经济型酒店
  - 客房层
  - 双廊客房
  - 默认完整构成
  - composition
synonyms:
  - economy hotel
-->

默认完整构成合同：

- 识别特征：客房单元重复；走廊中分；小卫生间
- 空间与体量：经济型酒店/旅馆，≤7 层。客房开间 3.2~3.8m、进深 6.0~6.2m、层高 3.0m，客房隔墙隔声， 门附观察窗，卫生间小门，走廊两侧排布，前台接待，屋顶平屋面。外观简洁经济。
- 主体骨架：`required` — wall(客房隔墙0.12 隔声 + 走廊墙) → floor(0.12)
- 外围护：`required / characteristic` — wall(客房隔墙0.12 隔声 + 走廊墙) → roof(flat)
- 开口组件：`required / characteristic` — door(客房门 w=0.9) → window(w=1.5 h=1.5)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — railing(走道扶手)
- 重复与模数：客房 3.6×6.0m；层高 3.0m；窗台 0.9
- 组装与依附：wall(隔声隔墙) 分隔；floor 每层；door(客房门附观察窗) + window(固定/滑窗) 挂墙；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 经济型酒店客房层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: economy_hotel_guest_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 经济型酒店客房层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 客房隔墙 ⊗ 外墙：隔墙端贴外墙内缘，隔声缝填实
- door ⊗ 隔墙：客房门附观察窗，净宽 0.9
- 走廊 ⊗ 客房：走廊板与客房板同标高整浇

### 经济型酒店客房层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: economy_hotel_guest_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 经济型酒店客房层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(客房隔墙0.12 隔声 + 走廊墙) → floor(0.12)；wall(客房隔墙0.12 隔声 + 走廊墙)；客房单元重复。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 商务酒店客房层

<!-- rag-meta
entity_type: building
entity_name: business_hotel_guest_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 商务酒店
  - 客房层
  - 电梯厅
  - 默认完整构成
  - composition
synonyms:
  - business hotel
-->

默认完整构成合同：

- 识别特征：核心筒；玻璃幕墙；落地窗客房；通高大堂
- 空间与体量：商务酒店，8~15 层。核心筒 + 外框架，客房开间 3.7~4.2m、进深 7.2~8.4m、层高 3.0~3.9m， 客房隔墙隔声，落地窗（w≥2.7m），玻璃幕墙立面，大堂通高 + 大堂柱，电梯分区。 外观现代商务、立面模数化。
- 主体骨架：`required` — wall(核心筒0.30) → column(0.4~0.5) → floor(0.15) → wall(幕墙 + 客房隔墙0.12)
- 外围护：`required / characteristic` — wall(核心筒0.30) → wall(幕墙 + 客房隔墙0.12) → roof(flat)
- 开口组件：`required / characteristic` — door(客房门) → window(落地 fixed)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — canopy(大堂雨棚 depth=3.0) → railing(大堂栏)
- 重复与模数：层高 3.2m；客房 4.0×8.0m；落地窗 from[1]=0.9（台）或 0（落地观景）
- 组装与依附：wall(核心筒) 围合电梯楼梯；column 外框；wall(幕墙) 围护；door(客房) + window(落地) 挂墙；详见下节。
- 降级映射：幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型

### 商务酒店客房层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: business_hotel_guest_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 商务酒店客房层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 核心筒 ⊗ floor：板端搭入筒壁整浇
- 落地窗 ⊗ 幕墙：窗组件挂幕墙墙，frameDepth 与幕墙相交
- 客房门 ⊗ 隔墙：门附观察窗，净宽 0.9

### 商务酒店客房层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: business_hotel_guest_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 商务酒店客房层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(核心筒0.30) → column(0.4~0.5) → floor(0.15)；wall(核心筒0.30)；核心筒。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 五星级酒店客房层

<!-- rag-meta
entity_type: building
entity_name: luxury_hotel_guest_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 五星级酒店
  - 客房层
  - 套房
  - 阳台
  - 默认完整构成
  - composition
synonyms:
  - luxury hotel
-->

默认完整构成合同：

- 识别特征：通高大堂；宴会厅大跨；屋顶泳池；豪华雨棚
- 空间与体量：五星级酒店，>24m。客房开间 4.5~4.8m、进深 9.0~9.8m、层高 3.9~4.2m，大堂 2~3 层 通高 + 豪华门头雨棚（挑 5m），宴会厅大跨无柱（i-beam），屋顶泳池玻璃栏，电梯分区 4~6 部，核心筒 + 玻璃幕墙。外观奢华大气、细部精致。
- 主体骨架：`required` — wall(核心筒0.3~0.4) → column(0.5~0.6) → beam(0.35×0.7 + 宴会厅 i-beam 大跨) → floor(0.15) → wall(幕墙+客房隔墙)
- 外围护：`required / characteristic` — wall(核心筒0.3~0.4) → wall(幕墙+客房隔墙) → roof(flat)
- 开口组件：`required / characteristic` — door(客房) → window(落地)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — canopy(豪华门头 depth=5.0) → railing(屋顶泳池玻璃栏) → light(大堂吊灯)
- 重复与模数：层高 4.0m；宴会厅无柱 i-beam 大跨；屋顶泳池 floor 上人 + 玻璃栏
- 组装与依附：wall(核心筒0.3~0.4) 围合；column 外框；beam(i-beam 宴会厅大跨)；floor 各层；door/window 客房；详见下节。
- 降级映射：幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型

### 五星级酒店客房层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: luxury_hotel_guest_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 五星级酒店客房层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 宴会厅 beam ⊗ 柱：i-beam 主梁端伸柱心（搭接≥0.3m），大跨无柱
- 屋顶泳池 ⊗ 屋面：泳池板搭屋面结构，玻璃栏沿边 1.1m
- 大堂通高 column ⊗ 楼板：通高柱从首层板底贯穿至 2~3 层板顶

### 五星级酒店客房层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: luxury_hotel_guest_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 五星级酒店客房层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(核心筒0.3~0.4) → column(0.5~0.6) → beam(0.35×0.7 + 宴会厅 i-beam 大跨)；wall(核心筒0.3~0.4)；通高大堂。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 度假酒店客房别墅

<!-- rag-meta
entity_type: building
entity_name: resort_hotel_villa
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 度假酒店
  - 客房别墅
  - terrace
  - villa
  - 默认完整构成
  - composition
synonyms:
  - resort hotel
-->

默认完整构成合同：

- 识别特征：木石客房别墅；景观落地窗；木露台；无边际泳池
- 空间与体量：度假酒店，结合自然，低层分散布局：客房别墅墙木/石，圆木柱，木/钢梁，景观落地窗 （w≥3.0m），木露台 + 玻璃栏，坡瓦/茅草顶，户外连廊，无边际泳池下沉，自然地形。 外观亲和自然、景观渗透。
- 主体骨架：`required` — column(圆木0.15~0.25) → beam(0.2×0.4) → floor(0.15 + 木露台) → wall(木/石)
- 外围护：`required / characteristic` — wall(木/石) → roof(gable/hip 木瓦/茅草)
- 开口组件：`required / characteristic` — window(落地 w≥3.0) → door(客房)；依附真实 `parentWall`。
- 交通组件：`conditional` — 来源未单列；有跨层/高差时再补。
- 附属组件：`characteristic / conditional` — railing(露台玻璃栏) → canopy(入口 depth=2.0)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(圆木) + beam(木/钢) 构架；wall(木/石) 围护；floor(露台) 悬挑；window(落地) 挂墙；roof(坡顶)；详见下节。
- 降级映射：terrain 无原生类型 → 场景处理；泳池 floor(custom) + 材质 water

### 度假酒店客房别墅 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: resort_hotel_villa
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 度假酒店客房别墅
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 木柱 ⊗ 露台：柱底落露台板面（或独立基础），柱心对齐梁交点
- 露台 floor ⊗ 客房墙：露台板外伸锚固，玻璃栏沿边 1.1m
- 屋顶 ⊗ 木梁：坡屋面搭于屋架梁，出檐 0.8m

### 度假酒店客房别墅 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: resort_hotel_villa
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 度假酒店客房别墅
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(圆木0.15~0.25) → beam(0.2×0.4) → floor(0.15 + 木露台)；wall(木/石)；木石客房别墅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 汽车客运站

<!-- rag-meta
entity_type: building
entity_name: coach_station
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 汽车客运站
  - 候车大厅
  - 发车雨棚
  - 默认完整构成
  - composition
synonyms:
  - coach station
-->

默认完整构成合同：

- 识别特征：大跨候车厅；发车位雨棚；售票窗口；站前广场
- 空间与体量：汽车客运站，候车大厅柱距 8~12m，屋盖桁架跨 20~40m，玻璃幕墙高 6~9m，发车位雨棚 外挑 6~10m，售票窗口阵列，进出站自动门，站台栏杆隔离，候车座椅，站前广场。外观 通透高效、流线清晰。
- 主体骨架：`required` — column(0.5, 8~12m) → beam(屋盖组合 20~40m) → wall(幕墙 6~9m) → floor(0.15)
- 外围护：`required / characteristic` — wall(幕墙 6~9m) → roof(flat 压型钢板)
- 开口组件：`required / characteristic` — door(进出站自动门 w=3.0)；依附真实 `parentWall`。
- 交通组件：`required` — stair → ramp(1:12)
- 附属组件：`characteristic / conditional` — canopy(发车位 depth=6~10 post) → railing(站台隔离) → furniture 元素(座椅)
- 重复与模数：候车厅净高≥6m；发车位雨棚外挑 6~10m
- 组装与依附：column(0.5) + beam(屋盖组合) 大跨；wall(幕墙) 围护；door(进出站自动门)；canopy(发车位大挑)；详见下节。
- 降级映射：truss（屋盖）无原生类型 → beam 组合；幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型

### 汽车客运站 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: coach_station
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 汽车客运站
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 屋盖 beam ⊗ 柱：主梁端伸柱心（搭接=1/2 柱宽）
- 发车位 canopy ⊗ 站房：雨棚根部锚站房墙/柱，外挑 6~10m post 立柱落地
- 站台 railing ⊗ 发车位：隔离栏沿发车位边缘，高 1.1m

### 汽车客运站 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: coach_station
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 汽车客运站
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.5, 8~12m) → beam(屋盖组合 20~40m) → wall(幕墙 6~9m)；wall(幕墙 6~9m)；大跨候车厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 港口客运站

<!-- rag-meta
entity_type: building
entity_name: port_passenger_terminal
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 港口客运站
  - 候船厅
  - 登船廊桥
  - 默认完整构成
  - composition
synonyms:
  - ferry terminal
-->

默认完整构成合同：

- 识别特征：大跨候船厅；登船廊桥；联检通道；码头高栏
- 空间与体量：港口客运站，候船大厅柱距 10~15m，跨桁架屋盖 30~50m，抗风玻璃幕墙（抗台风）， 可伸缩登船廊桥连码头，联检通道（海关/边检分隔），码头边缘加高栏杆 1.2m，抗风 雨棚。外观临海开阔、抗风构造突出。
- 主体骨架：`required` — column(0.6, 10~15m) → beam(屋盖组合 30~50m) → wall(抗风幕墙 + 联检隔墙0.12) → floor(0.15)
- 外围护：`required / characteristic` — wall(抗风幕墙 + 联检隔墙0.12) → roof(flat 抗风揭)
- 开口组件：`required / characteristic` — door(联检门)；依附真实 `parentWall`。
- 交通组件：`required` — stair → ramp(登船廊桥 width=2.0)
- 附属组件：`characteristic / conditional` — railing(码头1.2) → canopy(登船区 depth=8 抗风)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(0.6) + beam(屋盖组合)；wall(抗风幕墙 + 联检隔墙)；ramp(廊桥)；railing(码头1.2)；canopy(抗风)；详见下节。
- 降级映射：truss（warren 屋盖）无原生类型 → beam 组合；幕墙 → wall + window 或 primitive；禁用 curtain_wall/mullion/transom 类型

### 港口客运站 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: port_passenger_terminal
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 港口客运站
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 登船廊桥 ramp ⊗ 码头：廊桥一端铰接站房、一端搭码头（可伸缩，碰撞警示：留伸缩缝）
- 码头 railing ⊗ 廊桥：加高栏 1.2m 沿码头边缘，廊桥口留通行口
- 抗风幕墙 ⊗ 结构：幕墙与主体结构柔性连接（抗风揭）

### 港口客运站 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: port_passenger_terminal
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 港口客运站
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.6, 10~15m) → beam(屋盖组合 30~50m) → wall(抗风幕墙 + 联检隔墙0.12)；wall(抗风幕墙 + 联检隔墙0.12)；大跨候船厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 地铁站站台层

<!-- rag-meta
entity_type: building
entity_name: metro_platform_level
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 地铁站
  - 站台层
  - 屏蔽门
  - 地下空间
  - 默认完整构成
  - composition
synonyms:
  - metro station
-->

默认完整构成合同：

- 识别特征：站台屏蔽门；中柱列；扶梯组；通风竖井
- 空间与体量：地铁站，地下 1~3 层：站台层 + 站厅层。防水混凝土围护墙 0.30m，站台屏蔽门全高封闭， 中柱间距 6~9m，楼板 0.30m 防水，自动扶梯 + 疏散梯，出入口雨棚，通风井，导向标识。 岛式/侧式站台。外观地下机能导向、简洁明快。
- 主体骨架：`required` — wall(围护0.30 防水) → floor(站台层0.30) → column(0.5~0.8) → floor(站厅层0.30) → wall(隔断+通风井)
- 外围护：`required / characteristic` — wall(围护0.30 防水) → wall(隔断+通风井)
- 开口组件：`required / characteristic` — door(屏蔽门 glass 滑动)；依附真实 `parentWall`。
- 交通组件：`required` — stair(扶梯/疏散)
- 附属组件：`characteristic / conditional` — railing(站台安全栏) → canopy(出入口 depth=3.0) → light(站台灯)
- 重复与模数：站台层 Y=-6，站厅层 Y=0；屏蔽门 opening 宽=站台全长（用分段 door 表达）
- 组装与依附：wall(防水混凝土) 围合；column(中柱) 支撑；floor(站厅/站台0.30)；stair(扶梯)；door(屏蔽门玻璃)；详见下节。
- 降级映射：placement 非当前正式业务类型 → primitive 或省略；屏蔽门 leafCount 用分段 door；自动扶梯 → stair/ramp 静态近似

### 地铁站站台层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: metro_platform_level
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 地铁站站台层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 围护墙 ⊗ floor：底板/中板端搭入围护墙（防水贯通，碰撞警示：不得穿防水层开洞）
- 屏蔽门 door ⊗ 站台边缘：门框嵌站台边缘结构，与列车门对位
- 扶梯 stair ⊗ 中板：扶梯两端搭接站厅/站台板边，30° 倾斜
- 通风井 wall ⊗ 顶板：风井穿顶板，防水泛水上翻

### 地铁站站台层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: metro_platform_level
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 地铁站站台层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(围护0.30 防水) → floor(站台层0.30) → column(0.5~0.8)；wall(围护0.30 防水)；站台屏蔽门。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 高铁站候车大厅

<!-- rag-meta
entity_type: building
entity_name: high_speed_rail_waiting_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 高铁站
  - 候车大厅
  - 大跨屋盖
  - 默认完整构成
  - composition
synonyms:
  - high-speed rail station
-->

默认完整构成合同：

- 识别特征：超大跨候车厅；CFT 巨柱；站台长雨棚；扶梯组。
- 空间与体量：`required` 通高候车大厅与跨站台天桥/地道；`characteristic` 高架交通界面。
- 主体骨架：`required` 巨柱近似、屋盖 `beam` 组合、大厅/天桥 `floor`。
- 外围护：`required / characteristic` 幕墙宿主 `wall` 与弧形金属 `roof`。
- 开口组件：`required` 分段 `door` 近似检票口，依附真实墙体。
- 交通组件：`required` `stair/ramp` 静态近似扶梯和无障碍连接。
- 附属组件：`characteristic` 站台 `canopy` 与安全 `railing`。
- 重复与模数：巨柱、屋盖梁、幕墙分格和站台雨棚沿长向统一重复。
- 组装与依附：先大厅骨架和天桥，再围护屋盖，最后雨棚、闸机和交通组件；详见下节。
- 降级映射：CFT、桁架、扶梯和幕墙分别用现有 `primitive/beam/stair/ramp/wall/window` 近似。

### 高铁站候车大厅 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: high_speed_rail_waiting_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 高铁站候车大厅
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 屋盖 beam ⊗ 巨柱：主梁端伸柱心（搭接≥0.4m），多榀大跨并列
- 站台 canopy ⊗ 站台结构：雨棚外挑 15~30m，post 立柱落于站台，根部锚固
- 天桥 floor ⊗ 站台：天桥两端搭于候车厅与站台，跨站台留净空
- 检票 door ⊗ 隔断墙：闸机口分段 door 嵌隔断墙

### 高铁站候车大厅 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: high_speed_rail_waiting_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 高铁站候车大厅
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.8×1.0, 40~80m) → beam(屋盖组合) → wall(幕墙超大板块)；wall(幕墙超大板块)；超大跨候车厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 航站楼办票大厅

<!-- rag-meta
entity_type: building
entity_name: airport_checkin_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 航站楼
  - 办票大厅
  - curtain wall
  - 默认完整构成
  - composition
synonyms:
  - airport terminal
  - check-in hall
-->

默认完整构成合同：

- 识别特征：超少柱办票厅、超大跨屋盖、玻璃幕墙、登机廊桥、夹层和分离流线。
- 空间与体量：`required` 通高大厅与出发/到达分区；`characteristic` 放射指廊和行李夹层。
- 主体骨架：`required` 巨柱近似、屋盖 `beam` 组合、大厅/夹层 `floor`。
- 外围护：`required / characteristic` 幕墙宿主与流线分隔 `wall`、超大跨 `roof`。
- 开口组件：`required / characteristic` 安检 `door` 和采光近似；门窗依附真实墙体。
- 交通组件：`required` `stair/ramp` 近似扶梯和登机廊桥。
- 附属组件：`characteristic / conditional` 夹层 `railing`、大厅 `light`。
- 重复与模数：巨柱、屋盖、幕墙和办票岛按大厅长向统一节奏重复。
- 组装与依附：先大厅骨架和夹层，再分隔墙/幕墙与屋盖，最后廊桥和设备占位；详见下节。
- 降级映射：桁架、方柱、扶梯、天窗和幕墙均映射到现有 `beam/primitive/stair/ramp/roof/wall/window`。

### 航站楼办票大厅 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: airport_checkin_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 航站楼办票大厅
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 屋盖 beam ⊗ 巨柱：主梁端伸柱心（搭接≥0.5m）
- 登机廊桥 ramp ⊗ 航站楼/机位：一端铰接航站楼、一端连机位（伸缩缝）
- 行李夹层 ⊗ 结构：夹层板搭于主梁牛腿，净高 2.2m
- 分隔墙 ⊗ 楼板：到达/出发流线墙端贴楼板，流线互不交叉

### 航站楼办票大厅 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: airport_checkin_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 航站楼办票大厅
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：column(0.8×1.0) → beam(屋盖组合 50~100m) → wall(幕墙 + 分隔墙0.12)；wall(幕墙 + 分隔墙0.12)；超少柱办票厅。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 法院审判楼

<!-- rag-meta
entity_type: building
entity_name: courthouse_building
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 法院
  - 审判楼
  - 门廊
  - 纪念性入口
  - 默认完整构成
  - composition
synonyms:
  - courthouse
-->

默认完整构成合同：

- 识别特征：门廊柱列；三线分离流线；法庭隔离栏；封闭羁押室
- 空间与体量：法院，审判楼，法官/被告/旁听三线分离互不交叉。石/混凝土外墙庄严，门廊 doric 柱列 （高 8~12m），屋顶 flat/dome，大门拱形（w 2.4~3.6m），法庭隔声墙，庭审区隔离栏， 羁押室全封闭 0.30m 厚墙 + 防暴门，独立羁押通道，宽台阶仪式感。外观庄严肃穆。
- 主体骨架：`required` — wall(外墙0.24~0.30 + 法庭隔声墙 + 羁押室0.30) → column(门廊 doric 8~12m) → beam(门廊 0.4×0.6) → floor(0.15)
- 外围护：`required / characteristic` — wall(外墙0.24~0.30 + 法庭隔声墙 + 羁押室0.30) → roof(flat/dome)
- 开口组件：`required / characteristic` — door(大门 arched + 防暴门 steel)；依附真实 `parentWall`。
- 交通组件：`required` — stair(三线通道) → ramp(宽台阶)
- 附属组件：`characteristic / conditional` — railing(庭审隔离1.0) → light(法庭灯)
- 重复与模数：门廊柱高 8~12m；羁押室无窗或高窗；三线通道独立布置
- 组装与依附：column(doric 柱廊) + beam(门廊) 门面；wall(石墙 + 羁押厚墙) 围合；door(大门/防暴门)；railing(庭审隔离)；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 法院审判楼 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: courthouse_building
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 法院审判楼
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 门廊 column ⊗ beam：横梁端伸柱心（搭接=1/2 柱径）
- 庭审 railing ⊗ 法庭墙：隔离栏将旁听席与庭审区分隔，高 1.0m
- 羁押室 wall ⊗ 通道：防暴门框嵌 0.30m 厚墙，通道与公共区隔离（流线不交叉）
- ramp ⊗ 台基：宽台阶与台基面顺接，仪式感

### 法院审判楼 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: courthouse_building
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 法院审判楼
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(外墙0.24~0.30 + 法庭隔声墙 + 羁押室0.30) → column(门廊 doric 8~12m) → beam(门廊 0.4×0.6)；wall(外墙0.24~0.30 + 法庭隔声墙 + 羁押室0.30)；门廊柱列。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 监狱监舍单元

<!-- rag-meta
entity_type: building
entity_name: prison_cell_unit
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 监狱
  - 监舍单元
  - 围墙
  - 监控走廊
  - 默认完整构成
  - composition
synonyms:
  - prison
-->

默认完整构成合同：

- 识别特征：高厚围墙；四角岗楼；铁栅门窗；放风区
- 空间与体量：监狱/看守所，外围高墙 0.5~0.8m 厚、高 5~7m，四角岗楼，监舍隔墙 0.20m 钢筋混凝土， 铁栅门 + 铁栅栏窗（fixed 小窗 0.6×0.8），放风区高墙 + 2.0m 钢栏，墙顶巡逻通道， 电网围栏贴附，双开大门。外观封闭森严、安防突出。
- 主体骨架：`required` — wall(高墙0.5~0.8 h=5~7 + 监舍隔墙0.20 + 放风区墙0.30) → column(岗楼0.4) → floor(岗楼平台 + 巡逻通道)
- 外围护：`required / characteristic` — wall(高墙0.5~0.8 h=5~7 + 监舍隔墙0.20 + 放风区墙0.30) → roof(岗楼小顶 gable)
- 开口组件：`required / characteristic` — door(监舍铁栅门 w=0.9 + 大门 w=4.0) → window(fixed 铁栅 0.6×0.8)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — railing(放风区2.0 + 巡逻1.1)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：wall(高墙0.5~0.8 + 监舍墙0.20) 围合；column+floor(岗楼)；door(铁栅门/大门)；window(fixed 铁栅)；railing(2.0m 高栏)；详见下节。
- 降级映射：placement 非当前正式业务类型 → primitive 或省略

### 监狱监舍单元 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: prison_cell_unit
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 监狱监舍单元
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 高墙 ⊗ 高墙（角部）：转角延伸封口，整体围合（周圈闭合）
- 岗楼 ⊗ 高墙：岗楼平台搭于墙顶，四角布置
- 铁栅窗 ⊗ 监舍墙：fixed 窗内嵌铁栅，窗洞 0.6×0.8 小窗
- 放风区 railing ⊗ 高墙：2.0m 钢栏沿放风区周圈，高墙内侧

### 监狱监舍单元 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: prison_cell_unit
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 监狱监舍单元
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(高墙0.5~0.8 h=5~7 + 监舍隔墙0.20 + 放风区墙0.30) → column(岗楼0.4) → floor(岗楼平台 + 巡逻通道)；wall(高墙0.5~0.8 h=5~7 + 监舍隔墙0.20 + 放风区墙0.30)；高厚围墙。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 养老院居室层

<!-- rag-meta
entity_type: building
entity_name: eldercare_residential_floor
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 养老院
  - 居室层
  - 护理单元
  - 阳台
  - 默认完整构成
  - composition
synonyms:
  - eldercare
-->

默认完整构成合同：

- 识别特征：无高差地面；双层扶手；推拉宽门；低窗台；无障碍庭院
- 空间与体量：养老院/福利院，≤3 层，全楼无障碍：所有地面无高差，走廊宽≥1.5m + 双层扶手（0.65+0.85m）， 居室门净宽≥1.1m 推拉式，低窗台 0.6m，楼梯踏步高≤0.15m 宽≥0.30m，卫生间扶手，无障碍 坡道 + 庭院。外观温馨宜老。
- 主体骨架：`required` — wall(外墙0.24 + 居室隔墙0.12) → column(0.4) → floor(0.15 无高差)
- 外围护：`required / characteristic` — wall(外墙0.24 + 居室隔墙0.12) → roof(flat/gable)
- 开口组件：`required / characteristic` — door(推拉 w≥1.1) → window(casement 低台0.6)；依附真实 `parentWall`。
- 交通组件：`required` — stair(踏步≤0.15) → ramp(1:12 双侧扶手)
- 附属组件：`characteristic / conditional` — railing(双层扶手0.65+0.85)
- 重复与模数：层高 3.0m；窗台 0.6；门净宽≥1.1；走廊宽≥1.5
- 组装与依附：wall(0.24 保温 + 居室隔墙0.12) 围合；floor(无高差) 各层；door(推拉宽1.1) + window(低台0.6) 挂墙；railing(双层扶手)；ramp；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 养老院居室层 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: eldercare_residential_floor
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 养老院居室层
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- railing ⊗ 走廊墙：双层扶手（0.65+0.85）连续锚固于走廊两侧墙
- door ⊗ 居室墙：推拉门框嵌墙，门下无槛（高差 0）
- ramp ⊗ 地面：坡道与各入口地面顺接，双侧扶手连续
- window ⊗ 外墙：低窗台 0.6m（坐姿/轮椅观景）

### 养老院居室层 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: eldercare_residential_floor
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 养老院居室层
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：wall(外墙0.24 + 居室隔墙0.12) → column(0.4) → floor(0.15 无高差)；wall(外墙0.24 + 居室隔墙0.12)；无高差地面。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 佛寺大雄宝殿

<!-- rag-meta
entity_type: building
entity_name: buddhist_temple_main_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 佛寺
  - 大雄宝殿
  - 台基
  - 中式屋顶
  - 默认完整构成
  - composition
synonyms:
  - Buddhist temple
-->

默认完整构成合同：

- 识别特征：中轴殿宇；曲面重檐；斗拱额枋；须弥座；佛塔
- 空间与体量：汉传佛寺，中轴线布局：山门殿 → 天王殿 → 大雄宝殿 → 法堂 → 藏经楼，东西钟鼓楼。 檐柱 chinese_wooden，额枋 + 斗拱，大雄宝殿重檐歇山曲面顶（青/黄瓦，出檐 1.5~2.0m）， 佛塔 chinese_pagoda 3~7 层，须弥座台基 + 石栏杆，山门三门，隔扇门格心棂花，漏窗， 香炉/经幢陈设。…
- 主体骨架：`required` — floor(须弥座台基0.5~1.5) → column(檐柱 chinese_wooden r0.22~0.30) → beam(额枋0.18×0.30) → wall(院墙0.24) → floor(楼板)
- 外围护：`required / characteristic` — roof(chinese_curved eaveOutset=1.5~2.0) → wall(院墙0.24)
- 开口组件：`required / characteristic` — door(山门/隔扇门) → window(槛窗)；依附真实 `parentWall`。
- 交通组件：`required` — stair
- 附属组件：`characteristic / conditional` — railing(石寻杖栏) → cornice(飞檐)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：floor(台基) + column(檐柱) + beam(额枋) 构架；roof(chinese_curved/pagoda)；wall(院墙)；door(山门/隔扇)；railing(石栏杆)；详见下节。
- 降级映射：truss（斗拱）无原生类型 → primitive 组合或省略；placement 非当前正式业务类型 → primitive

### 佛寺大雄宝殿 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: buddhist_temple_main_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 佛寺大雄宝殿
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 檐柱 ⊗ 额枋：梁端伸柱心（搭接=1/2 柱径），榫卯固定
- roof ⊗ 檐柱：曲面屋顶檐口基准=檐柱顶+斗拱高度，出檐 1.5~2.0m
- 山门 door ⊗ 院墙：三门洞开于院墙，门框嵌墙
- 台基 railing ⊗ 台基面：石寻杖栏沿台基边缘，柱间距 2m

### 佛寺大雄宝殿 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: buddhist_temple_main_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 佛寺大雄宝殿
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(须弥座台基0.5~1.5) → column(檐柱 chinese_wooden r0.22~0.30) → beam(额枋0.18×0.30)；roof(chinese_curved eaveOutset=1.5~2.0)；中轴殿宇。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 道观三清殿

<!-- rag-meta
entity_type: building
entity_name: taoist_temple_main_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 道观
  - 三清殿
  - 山门
  - 中式木构
  - 默认完整构成
  - composition
synonyms:
  - Taoist temple
-->

默认完整构成合同：

- 识别特征：青绿瓦曲面顶；棂星门；八卦棂花；垂带踏跺
- 空间与体量：道教宫观，中轴线：山门 → 灵官殿 → 三清殿/玉皇殿 → 后殿，不建塔和经幢。檐柱 chinese_wooden，额枋，歇山/悬山曲面顶（青绿瓦），棂星门式山门，隔扇门八卦棂花， 窗太极/八卦纹，台基 + 石栏杆，垂带踏跺坡道，庭院铜香炉。外观清静朴素、青绿黛瓦。
- 主体骨架：`required` — floor(台基0.3~1.0) → column(檐柱 r0.20~0.28) → beam(额枋0.15×0.25) → wall(院墙0.24) → floor(楼板)
- 外围护：`required / characteristic` — roof(chinese_curved eaveOutset=1.0~1.5) → wall(院墙0.24)
- 开口组件：`required / characteristic` — door(山门/隔扇) → window(槛窗 八卦纹)；依附真实 `parentWall`。
- 交通组件：`required` — ramp(垂带踏跺)
- 附属组件：`characteristic / conditional` — railing(石栏杆)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：floor(台基) + column(檐柱) + beam(额枋)；roof(chinese_curved 青绿瓦)；wall(院墙)；door(山门/隔扇)；ramp(踏跺)；详见下节。
- 降级映射：未列额外未注册类型；专业设备仅用当前基础类型近似。

### 道观三清殿 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: taoist_temple_main_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 道观三清殿
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 檐柱 ⊗ 额枋：梁端伸柱心（搭接=1/2 柱径）
- roof ⊗ 檐柱：曲面顶檐口基准=柱顶，出檐 1.0~1.5m
- 踏跺 ramp ⊗ 台基：垂带踏跺与台基面顺接，两端高差 0.3~1.0m

### 道观三清殿 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: taoist_temple_main_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 道观三清殿
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(台基0.3~1.0) → column(檐柱 r0.20~0.28) → beam(额枋0.15×0.25)；roof(chinese_curved eaveOutset=1.0~1.5)；青绿瓦曲面顶。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 清真寺礼拜大殿

<!-- rag-meta
entity_type: building
entity_name: mosque_prayer_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 清真寺
  - 礼拜大殿
  - 穹顶
  - 宣礼塔
  - 默认完整构成
  - composition
synonyms:
  - mosque
-->

默认完整构成合同：

- 识别特征：中央穹顶；光塔；尖拱门；几何纹饰；米哈拉布
- 空间与体量：清真寺，礼拜大殿（面东朝麦加）+ 邦克楼/光塔（高 15~30m）+ 庭院 + 净身室。殿内柱林 （间距 4~6m），中央穹顶 dome，厚石墙拱形装饰，尖拱/马蹄拱门，彩色玻璃几何纹窗棂， 回廊拱柱连续拱廊，净身水池下沉，院墙围合，阿拉伯几何纹/经文贴附，米哈拉布壁龛。 外观庄重、穹顶光塔突出。
- 主体骨架：`required` — floor(庭院) → column(大殿柱 r 间距4~6m + 光塔 h=15~30m) → wall(厚石墙0.3~0.5 + 院墙) → floor(净身水池下沉)
- 外围护：`required / characteristic` — wall(厚石墙0.3~0.5 + 院墙) → roof(dome span=10~20)
- 开口组件：`required / characteristic` — door(尖拱门) → window(彩色玻璃 fixed)；依附真实 `parentWall`。
- 交通组件：`conditional` — 来源未单列；有跨层/高差时再补。
- 附属组件：`characteristic / conditional` — railing(回廊) → cornice(拱券装饰)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(殿内柱林 + 光塔柱) 构架；roof(dome + 光塔小穹顶)；wall(厚石墙 + 院墙)；door(尖拱门)；window(彩色玻璃)；详见下节。
- 降级映射：mullion（几何纹）无独立类型 → window 棂条/primitive；placement 非当前正式业务类型 → primitive 或省略

### 清真寺礼拜大殿 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: mosque_prayer_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 清真寺礼拜大殿
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 大殿柱 ⊗ 穹顶：穹顶环梁落于殿内柱列上（柱顶标高=穹顶底）
- 光塔 column ⊗ 小穹顶：塔身柱列承托顶部小穹顶，塔高 15~30m
- 尖拱门 door ⊗ 大殿墙：门洞嵌厚墙，拱券顶与墙顶平齐
- 净身池 floor ⊗ 庭院：水池下沉 0.3m，池边防滑

### 清真寺礼拜大殿 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: mosque_prayer_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 清真寺礼拜大殿
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(庭院) → column(大殿柱 r 间距4~6m + 光塔 h=15~30m) → wall(厚石墙0.3~0.5 + 院墙)；wall(厚石墙0.3~0.5 + 院墙)；中央穹顶。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 哥特式教堂中殿

<!-- rag-meta
entity_type: building
entity_name: gothic_church_nave
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 哥特式教堂
  - 中殿
  - 尖拱
  - 飞扶壁
  - 默认完整构成
  - composition
synonyms:
  - Gothic church
-->

默认完整构成合同：

- 识别特征：尖塔；飞扶壁；玫瑰窗；柳叶窗彩色玻璃；肋拱顶
- 空间与体量：哥特教堂：尖塔钟楼高耸（40~120m），中殿厚重石墙 + 飞扶壁，交叉肋拱顶（高 15~30m）， 西立面玫瑰窗（直径 3~13m）+ 柳叶窗（彩色玻璃），三大门尖拱，拱顶石装饰，祭坛台基 + 石栏杆，钟楼螺旋楼梯。外观高耸挺拔、尖拱肋拱交织。
- 主体骨架：`required` — floor(祭坛台基) → wall(中殿石墙0.5~1.0 + 钟楼) → column(钟楼 2~4m) → beam(飞扶壁斜撑0.3×0.5) → floor(楼板0.20)
- 外围护：`required / characteristic` — wall(中殿石墙0.5~1.0 + 钟楼) → roof(尖顶 custom)
- 开口组件：`required / characteristic` — window(玫瑰/柳叶窗 stained) → door(三大门 gothic)；依附真实 `parentWall`。
- 交通组件：`required` — stair(螺旋)
- 附属组件：`characteristic / conditional` — railing(祭坛石栏) → cornice(拱顶石)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：wall(厚石墙0.5~1.0) 围合；column(钟楼) + beam(飞扶壁) + roof(尖顶)；opening(玫瑰/柳叶窗) + window(彩色玻璃)；stair(螺旋梯)；详见下节。
- 降级映射：truss（肋拱顶）无原生类型 → beam 组合；玫瑰窗棂 → window 棂条/primitive 近似

### 哥特式教堂中殿 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: gothic_church_nave
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 哥特式教堂中殿
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 飞扶壁 beam ⊗ 中殿墙：斜撑梁一端顶外墙高侧、一端落扶壁墩（搭接≥0.3m）
- 玫瑰窗 ⊗ 西立面墙：圆洞开于厚墙，棂条放射分格，彩色玻璃内嵌
- 尖顶 roof ⊗ 钟楼：尖锥顶落于钟楼柱列顶，塔高 40~120m
- 螺旋 stair ⊗ 钟楼：石质螺旋梯贴钟楼内壁，逐级上升

### 哥特式教堂中殿 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: gothic_church_nave
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 哥特式教堂中殿
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(祭坛台基) → wall(中殿石墙0.5~1.0 + 钟楼) → column(钟楼 2~4m)；wall(中殿石墙0.5~1.0 + 钟楼)；尖塔。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 苏州园林水榭

<!-- rag-meta
entity_type: building
entity_name: suzhou_garden_waterside_pavilion
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 苏州园林
  - 水榭
  - 白墙灰瓦
  - 漏窗
  - 默认完整构成
  - composition
synonyms:
  - Suzhou garden
-->

默认完整构成合同：

- 识别特征：曲廊美人靠；月洞空窗；漏窗框景；叠山理水
- 空间与体量：苏州园林，私家文人园林：小中见大、叠山理水、曲折蜿蜒。木柱檐廊，曲面屋顶 （卷棚歇山/悬山，出檐 0.8~1.5m），廊道 + 美人靠，隔扇门格心棂花，槛窗，漏窗/空窗 （月洞纯框景），台基，叠山理水，花街铺地，石桌石凳。外观精致雅致、步移景异。
- 主体骨架：`required` — floor(台基0.3~0.6 + 庭院铺地) → column(木柱 r0.18~0.22) → beam(额枋0.15×0.25 + 廊梁0.10×0.15) → wall(院墙) → floor(水池下沉)
- 外围护：`required / characteristic` — roof(chinese_curved) → wall(院墙)
- 开口组件：`required / characteristic` — door(隔扇门) → window(槛窗)；依附真实 `parentWall`。
- 交通组件：`required` — ramp(垂带踏跺)
- 附属组件：`characteristic / conditional` — railing(美人靠0.5)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(木柱) + beam(廊梁) 构架；roof(chinese_curved)；wall(院墙含漏窗)；opening(月洞/漏窗)；railing(美人靠)；详见下节。
- 降级映射：terrain 无原生类型 → primitive 组合；漏窗/月洞用 opening(无 window)

### 苏州园林水榭 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: suzhou_garden_waterside_pavilion
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 苏州园林水榭
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 曲廊 column ⊗ 廊梁：梁端伸柱心（搭接=1/2 柱径），廊柱列沿曲径
- 美人靠 ⊗ 廊柱：坐凳栏嵌于柱间，高 0.5m
- 月洞 opening ⊗ 院墙：圆形洞口开于墙（纯框景，无扇无棂）
- 水池 floor ⊗ 台基：水体下沉 0.3~0.6m，驳岸与台基顺接

### 苏州园林水榭 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: suzhou_garden_waterside_pavilion
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 苏州园林水榭
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(台基0.3~0.6 + 庭院铺地) → column(木柱 r0.18~0.22) → beam(额枋0.15×0.25 + 廊梁0.10×0.15)；roof(chinese_curved)；曲廊美人靠。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 皇家园林大殿

<!-- rag-meta
entity_type: building
entity_name: imperial_garden_main_hall
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 皇家园林
  - 大殿
  - 轴线
  - 琉璃瓦
  - 默认完整构成
  - composition
synonyms:
  - imperial garden
-->

默认完整构成合同：

- 识别特征：重檐大殿；汉白玉栏杆；琉璃影壁；须弥座；大型水体
- 空间与体量：皇家园林，规模宏大、轴线对称：殿堂粗柱（r0.30~0.50 红漆），大额枋，重檐庑殿/歇山 曲面顶，汉白玉栏杆（寻杖，柱距 2m），隔扇门三交六椀棂花，菱花窗，琉璃影壁，高须弥座 台基（1~3m），殿前广场，大型水体叠山，铜缸/铜兽陈设。外观恢宏华丽、金碧辉煌。
- 主体骨架：`required` — floor(须弥座1~3m) → column(粗柱 r0.30~0.50) → beam(大额枋0.25×0.40) → wall(影壁0.40 + 院墙) → floor(广场/水体)
- 外围护：`required / characteristic` — roof(chinese_pagoda tiers=2) → wall(影壁0.40 + 院墙)
- 开口组件：`required / characteristic` — door(隔扇门 leafCount=6~8) → window(菱花窗)；依附真实 `parentWall`。
- 交通组件：`conditional` — 来源未单列；有跨层/高差时再补。
- 附属组件：`characteristic / conditional` — railing(汉白玉寻杖1.0) → cornice(重檐檐口)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(粗柱 r0.3~0.5) + beam(大额枋) 构架；roof(chinese_pagoda 重檐)；wall(影壁)；railing(汉白玉)；placement(铜兽)；详见下节。
- 降级映射：truss（斗拱）无原生类型 → primitive 组合；placement 非当前正式业务类型 → primitive 或省略

### 皇家园林大殿 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: imperial_garden_main_hall
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 皇家园林大殿
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 重檐 roof ⊗ 柱列：重檐下层檐口落于下檐柱，上层落于内柱（柱列两级）
- 汉白玉 railing ⊗ 须弥座：寻杖栏沿台基边缘，柱距 2m，栏板嵌柱间
- 影壁 wall ⊗ 院门：琉璃影壁立于院门内外，与院墙脱开（碰撞警示：不搭接）
- 须弥座 ⊗ 广场：台基面与广场铺地高差 1~3m，台阶/坡道连接

### 皇家园林大殿 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: imperial_garden_main_hall
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 皇家园林大殿
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(须弥座1~3m) → column(粗柱 r0.30~0.50) → beam(大额枋0.25×0.40)；roof(chinese_pagoda tiers=2)；重檐大殿。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。

## 岭南园林水榭

<!-- rag-meta
entity_type: building
entity_name: lingnan_garden_waterside_pavilion
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 岭南园林
  - 水榭
  - 满洲窗
  - 灰塑
  - 默认完整构成
  - composition
synonyms:
  - Lingnan garden
-->

默认完整构成合同：

- 识别特征：细柱卷棚顶；满洲窗；花格隔断；水庭；骑楼连廊
- 空间与体量：岭南园林，结合亚热带气候，轻巧通透：细木柱（r0.12~0.16），卷棚顶（无正脊，出檐 0.6~1.0m），满洲窗彩色玻璃，花格隔断通风，水庭为核心，美人靠矮栏（0.6~0.8m）， 骑楼连廊遮阳避雨（柱距 3~4m），花砖铺地。外观轻盈通透、湿热适应。
- 主体骨架：`required` — floor(水庭下沉 + 铺地) → column(细木柱) → beam(连廊梁0.10×0.18) → wall(院墙) → floor(骑楼连廊板)
- 外围护：`required / characteristic` — roof(chinese_curved 卷棚) → wall(院墙)
- 开口组件：`required / characteristic` — window(满洲窗 casement) → door(隔扇)；依附真实 `parentWall`。
- 交通组件：`conditional` — 来源未单列；有跨层/高差时再补。
- 附属组件：`characteristic / conditional` — railing(美人靠0.6~0.8) → cornice(卷棚檐口)
- 重复与模数：来源未单列；保持轴线、单元或开窗节奏。
- 组装与依附：column(细木柱 r0.12~0.16) + beam(连廊梁)；roof(chinese_curved 卷棚)；floor(水庭下沉)；window(满洲窗)；railing(矮栏)；详见下节。
- 降级映射：mullion（花格）无独立类型 → window 棂条/primitive

### 岭南园林水榭 关键组装关系

<!-- rag-meta
entity_type: building
entity_name: lingnan_garden_waterside_pavilion
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - 岭南园林水榭
  - 构件搭接
  - 宿主
  - 对齐
  - 碰撞
synonyms: []
-->

保留来源的空间与搭接意图；锚固、结构、防火、疏散和工艺数值不属于 WILD 自动验证能力。

- 水庭 floor ⊗ 连廊：水体下沉，连廊柱立于驳岸，栏板临水 0.6m
- 卷棚 roof ⊗ 细柱：檐口基准=柱顶，出檐 0.6~1.0m
- 满洲窗 ⊗ 隔断墙：彩色玻璃窗嵌花格隔断，通风可开启

### 岭南园林水榭 最少可行回退

<!-- rag-meta
entity_type: building
entity_name: lingnan_garden_waterside_pavilion
topic: fallback
status: experimental
authority: domain_reference
primary_terms:
  - 岭南园林水榭
  - fallback
  - 最少可行回退
synonyms: []
-->

- 触发条件：仅限快速/低复杂度模式、性能预算不足或详细构成确定性失败。
- 必须保留：floor(水庭下沉 + 铺地) → column(细木柱) → beam(连廊梁0.10×0.18)；roof(chinese_curved 卷棚)；细柱卷棚顶。
- 可简化项：减少重复单元、次要灯具和装饰细部；不得删除主要空间、交通宿主或全部身份组件。
- 恢复路径：普通/精密模式按完整构成合同补回开口、交通、附属系统和关键关系。
