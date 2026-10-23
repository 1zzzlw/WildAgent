# WILD 蓝图设计语言 v3.0

面向 AI 的独立建筑创作规范。整理日期：2026-10-22，渲染与几何修订：2026-10-23。**本文版本为 3.0；输出文件的 `meta.version` 写 `"1.1"`，不能写 `"3.0"`。** 当前引擎将历史 1.1 归一到内部 1.0。本文在既有语言 1.3 和十二例审计基础上重新组织；本次新增前端/Core 的多边形楼板孔洞和扫掠端盖，保持既有文件兼容。

补充修订：2026-10-23，参考用户提供的v2.0，补入依赖联动、精度、重复立面、分段/圆形设计与装配检查；所有引擎语义仍以当前实现为依据，不继承外部文档的冲突规则。

## 0. 直接交给 AI 的指令

你是一名使用 WILD 表达空间的建筑设计者。根据用户需求重新设计建筑，再把设计计算为一份可直接导入的、完整 UTF-8 JSON `.wild` 文件。建筑的用途、空间和构造决定形态，不能只靠名称、风格词和重复装饰表达设计。

用户没有规定的普通参数由你合理选择；需要澄清的是相互矛盾的核心条件。缺少参考图不妨碍原创设计。只有参考图时，区分可见特征、尺寸推定和不可见部分的补全，不声称测得真实尺寸。

严格执行：

1. 固定用户明确的地块、层数、功能、风格、招牌文字和禁用项。设计可变化，硬条件不可偷偷改变。
2. 先确定空间和尺寸链，再写构件。根据本文计算标高、门窗、楼梯、开口、支承和材料分工。
3. 用途相同也允许不同设计；除非用户要求复刻，不默认复制示例或历史成品的平面、坐标、屋面和材料组合。
4. 默认只交付完整 JSON，不夹脚本、说明、Markdown 围栏、注释、占位符或省略号。用户要求过程时，将简明设计依据、脚本和验证另存，不能混进 WILD。
5. 数组全部展开，所有引用存在。脚本只是可选展开工具；生成脚本本身不是已经生成 WILD。
6. 不发明类型、字段、外部资产或自动设计能力。单独一份 WILD 默认自足，不依赖网络贴图或未附带模板。
7. 无工具只能文本自检。真正执行的 Schema、Core 重建、渲染和人工查看分别报告，不能以文本推演冒充测试通过。

项目以极小文件表达精细建筑为核心约束，不引入GLB/GLTF模型资产，也不在JSON中内嵌网格/base64替代模型。优先用当前支持的参数化构件、轮廓/路径、材料复用和有设计价值的细部；不靠重复低价值零件增加体积。未来紧凑装配/实例/运动需要实现完整契约后才可写入，不能为缩小文件自行省略当前必填字段或发明repeat/spin语法。

本文是自足的常用创作字段集，含完整例子；并不罗列工程 Schema 的所有实验/资产字段。只收到本文即可创作。拿到资料包的智能体可进一步读 Schema 和源码，扩展已实现的能力。

## 1. 建筑丰富度来自哪些设计决定

把“精致”落实为下面的层次。每层都服务本方案，不要求每栋具有同样设施。

| 层次 | 设计问题 | 在蓝图里的证据 |
| --- | --- | --- |
| 场地与到达 | 人从哪里来，如何入门，建筑与院子如何分配 | 入口、道路/铺地边、台阶或坡道、完整地块范围 |
| 体量与剖面 | 主次体量、高低、实虚和屋面如何组织 | 建筑外轮廓、退台、庭院、挑空、真实层高 |
| 使用空间 | 各层怎么用，公共/私密/服务如何相邻 | 隔墙、独立门、家具与通道；不能以名字充当房间 |
| 交通与构造 | 上下楼、洞边、屋面、悬挑如何相接 | 梯段/平台/拆板/护栏，梁柱和覆盖关系 |
| 立面与材料 | 开间、窗墙、深浅、材料边界如何表达 | 墙垛、窗台/套、遮阳、层间边带、压顶和收口 |
| 使用细节 | 什么细部能说明这是一栋什么建筑 | 咖啡吧台、图书架/阅览桌、货架/收银、办公室/会议等 |
| 场景与光 | 入口识别、夜间照明、绿化和水如何增强空间 | 可读招牌、真实光源、正确池体、适量植被 |

先使体量、平面、剖面成立，再完善主要可见节点，最后分配次要细节。构件数量、门窗数量、材质数量和随机种子都不是丰富度目标。一个细致的檐口节点比增加十扇相同窗更有意义。

## 2. 从提示词到独立方案

### 2.1 建立设计事实

写 JSON 前确定以下事实；纯文本直出时自行完成，有工具时可另存一页设计记录：

- **约束**：建筑用途、地块外缘、层数、主要功能、风格、朝向、特殊要求。
- **场地**：入口方向、建筑占地、室外可用区、外部高程。`32×32` 默认指完整地块，不自动当主体尺寸；有其他含义就说明。
- **体量**：每个体块的平面范围 `[x0,x1]×[z0,z1]`、跨越楼层、主次关系和相接方式。
- **标高**：各层完成面、板底、墙顶、梁底/顶、屋面上下皮、露台和池底。统一使用同一组数字派生。
- **空间**：房间邻接、内部通路、门位置、楼梯/平台/洞口、家具使用范围。
- **表达**：立面节奏、主材料/辅材料/框架/屋面、细部重点和预计输出规模。

设计摘要记录决定、理由和可核查尺寸即可，不要求逐字输出模型内部推理。

### 2.2 让同类建筑产生不同设计

在满足功能后，先选择一条主设计命题，例如“沿庭院展开的低层住宅”“围绕阅览内庭的图书馆”“依街角退台的咖啡馆”。再从下列轴中选取相互兼容的变化，不能独立随机拼装：

| 变化轴 | 可选方向举例 | 必须联动的部分 |
| --- | --- | --- |
| 平面拓扑 | 紧凑矩形、L 形、U 形、串联庭院、错接双体量 | 功能分区、连接口、外墙、屋面分块 |
| 剖面策略 | 等高、局部挑高、退台、错层、连廊 | 楼层标高、楼梯/坡道、上层洞口和防护 |
| 交通组织 | 中央核心、侧向核心、庭院回廊、外楼梯 | 到达平台、门、路径宽度、洞边 |
| 环境回应 | 内向院落、面向景观、深遮阳、入口雨廊 | 窗墙比例、开口位置、结构与场地 |
| 屋面逻辑 | 单一平顶、分段坡顶、绿化退台、轻亭盖 | 支承、封口、檐口、屋顶开口 |
| 围护与节奏 | 厚墙深窗、框架玻璃、竖片遮阳、柱廊 | 结构网格、开间、材料厚度和边缘收口 |
| 氛围 | 安静石木、轻盈金属玻璃、温暖砖木、地域木构 | 配色、粗糙度、构造方法、照明与景观 |

用户要求“再生成一栋不同的”时，默认至少改变平面/剖面/交通/屋面中的两项，并解释变化如何满足用途；这个“两项”是创作对比建议，不是 WILD Schema 字段或硬性配额。保持用户指定风格。只改颜色、名称、窗数量或植被随机种子不算新方案。

没有历史方案时，先形成两个可行方向的简短比较，再选择一项实现；用户只要文件时，不必把比较输出给用户。任何选择都应有场地/使用/构造理由。

### 2.3 类型与风格分别处理

类型决定功能组织，风格决定比例、屋面、构造和材料。二者不能互相代替。

| 类型 | 优先组织 | 适合深化的对象 |
| --- | --- | --- |
| 别墅/住宅 | 到达—门厅—起居餐厨，卧室私密，服务与上下楼连通 | 入户节点、露台、遮阳、窗洞进深、收纳 |
| 凉亭/廊架 | 柱网、开敞方向、坐凳与入口、屋下净空 | 柱础、梁枋/檩条、坡面承托、檐口、茶席 |
| 写字楼 | 接待、办公、会议、服务、连续交通核心 | 层间模数、幕墙框架、遮阳、设备围屏、退台 |
| 图书馆 | 入口咨询、书架、阅览、安静区、服务与交通 | 采光内庭、书架端部、阅览家具、遮阳和指引 |
| 咖啡厅/餐饮 | 点单—出品—取餐，座位与通路，后场/卫生间 | 吧台层次、陈列、桌椅朝向、街道界面、招牌 |
| 超市/商店 | 入口、货架通道、分区、收银、后场 | 双面货架、冷柜、商品分组、价签/分区和店名 |
| 高层住宅/塔楼 | 先明确完整建模还是用户授权的示意表达，组织核心交通与重复层 | 标准层模数、分段轮廓、服务/设备层和顶部收束；不能只增外墙高度代替内部楼层 |
| 商业综合体 | 公共裙房、塔楼、到达与后场分别组织，交接标高连续 | 裙房—塔身接缝、转换处几何支承、分段幕墙和公共露台 |
| 其他类型 | 先推导真实使用顺序和空间邻接 | 从用途选择细节，不硬套上述家具组合 |

新中式可通过院落、檐下层次、木格栅、虚实与灰瓦表达；古典欧式可通过对称比例、柱式、窗套、檐口和坡顶表达；现代建筑可通过干净的主次体量、连续框架、凹进开口和材料交接表达。风格可以混合，但要有清晰主次和统一尺度，不把所有装饰叠到一栋上。

### 2.4 将类型知识转成可交付清单

先区分“决定这是什么建筑的形制/功能”和“本方案自行选择的表达”：亭的开敞休憩和屋下使用不能被装饰取代；图书馆要有阅读与藏书使用；具体柱数、是否内庭、屋顶形式则由用户要求和本方案决定。历史形制或具名建筑复建，要明确哪些来自可靠资料、哪些只是比例推定；模型自己的建筑常识不等于检索到的证据。

有工具时可把用户条件整理成“要求 → 设计位置/范围 → 对应构件组 → 核对办法”的短表。数量词逐项兑现：三层须有三层实际表达，四面开窗不能只在正面做窗，两处露台须各有真实边界与连接。统计时按用户所说的对象计数，不能把一个双开门的编译零件算成多个入口，也不能拿书本零件数代表书架数。

方案中的标志性节点需要保留，非必要的历史细节可以适当概括并说明。无能力准确表达的形态应记录近似方式及可见差异，不擅自换成另一种形制；例如不把攒尖顶直接换成穹顶来回避表达困难。已有实例可查构造技法，但不强制沿用它的布局和尺寸。

## 3. 文件骨架与坐标契约

WILD 是严格 JSON，推荐顶层只有 `meta`、`geometry`、`materials`。`geometry.elements` 存基础构件；`geometry.components` 存会被编译展开的组合构件。每个构件都用唯一、稳定的 ASCII `id`，如 `wall_l2_east`；招牌文字可使用中文。

```text
meta = {version:"1.1", type:"building", name:"建筑名称"}
geometry = {elements:[...基础构件...], components:[...组合构件...]}
materials = {材质名:材质定义, ...}
```

上面是结构说明，不是可直接保存的 JSON；第 12 节提供完整可保存的例子。

- 米制；Y 向上，X/Z 为水平面。本文约定 front 为较小 Z 一侧，back 为较大 Z 一侧；“前”不是相机屏幕方向。可按项目朝向重新映射，但同稿一致。
- 向量均 `[x,y,z]`。`rotation=[rx,ry,rz]` 是弧度 Euler XYZ；90°为 1.570796，180°为 3.141593。门扇 `openAngle`、灯锥 `angle`、圆弧 `sweep` 则用度。
- 建筑物理外缘包含半墙厚、檐口、台阶、栏杆和景观，不能只检查墙轴线。
- 不添加 `geometry.rooms`、`holes`、任意 `mesh`、`sun`、`camera`、`waterAnimation`、Agent 任务状态或 `_interaction` 等内部字段。房间靠真实围合/开口表达，显示设置由查看器控制。
- 不需要外部资产的作品优先使用本文基础构件，不要求模板、实例、行为脚本和 RAG。

### 3.1 最容易混淆的锚点

| 对象 | 位置含义 |
| --- | --- |
| wall.from/to | XZ 是墙中心轴端点；from.y 是墙底，to.y 是墙顶 |
| floor.from/to | XZ 是矩形对角；两点 Y 为板底；thickness 向上增加 |
| column.base | 柱底中心；顶=base.y+height |
| beam.from/to | 梁中心线；水平梁底=中心线Y−height/2 |
| primitive.box/sphere/cylinder.position | 几何中心；圆柱沿局部 Y 轴 |
| furniture.position | 家具底面中心；不是几何中心 |
| flat roof.position | XZ 中心、Y 板底；顶=Y+thickness |
| gable/hip roof.position | XZ 中心、Y 檐口外表面；坡面厚度向下 |
| door/window.from | `[沿宿主墙距离, 底边世界Y, 墙法向偏移]`；不是 XYZ |
| light.body 中的 position | 世界坐标；省略时继承灯组件 position，不是相对偏移 |

### 3.2 标高链

设该层完成面 `F`、下一层完成面 `Fnext`、上层板厚 `t`：

```text
本层墙底 = F
上层楼板底 = Fnext - t
本层墙顶 = 上层楼板底（没有另外设计梁/缝时）
上层楼板顶 = Fnext
窗底 = F + 窗台高
门底 = 相接通行面完成标高
```

层高不是净高。顶层另算屋面板底、屋面板顶、女儿墙与压顶。台阶、露台、地毯、铺装和池底都从实际完成面派生，不能沿用上一层家具坐标。

常见概念模型参考值：住宅层高约 3～3.8m、家具座面约 0.43～0.48m、桌面约 0.72～0.78m；楼梯步高约 0.15～0.18m、步深约 0.26～0.32m。它们是设计起点，不是代码限制或法规合规结论。用途、气候和任务不同应重新选择。

### 3.3 模数、数值精度与真实尺度

轴网/开间可选择0.3m或0.15m等便于推导的模数，也可按结构、功能和地块使用其他模数。框料、玻璃、斜杆、曲线采样、台阶和定制节点不必硬凑模数。模数帮助建立秩序，不能变成所有建筑的尺寸限制。

计算时保留足够精度，统一共享边界，再按实际误差预算序列化。普通正交米制尺寸常用3～5位小数即可；角度、长斜杆和曲面位置可能需要更多。**不能把全部数字统一截成三位小数再放宽检查容差**：把π/2取成1.571，50m杆端可能偏移约10mm。楼梯步高量化误差还会随级数累积。应在最终落盘值上重算端点、接触和尺寸链。

无论精度多少，都要拒绝NaN、Infinity、零/负尺寸和连续重合路径点。使用整数索引命名重复构件，别把长浮点尾数拼进ID。紧凑JSON或可读缩进都允许；文件预算由接收端和任务决定，没有通用100KB上限或“超过300件必须用某种脚本”的语法规定。

真实建筑默认按米建模，相机按范围适配，不因建筑高就自动缩成桌面模型。用户要求缩尺时，记录比例k与原始尺寸，所有位置、厚度和标高相对选定基准一致缩放；尺寸同比例、角度不变。放大过细构件属于单独的表现性调整，要列明。缩尺后重新核查门窗框料、楼梯、法向偏移、光源距离与显示效果；照明强度不机械按长度同比缩放。比例和简化清单可写在独立设计说明中，不能发明本文未定义的`meta.scale`字段。

## 4. 基础构件字段集

以下记法列出字段，不代表可以把公式或变量写进 JSON。所有尺寸必须输出计算后的有限数。每行都另有 `id` 和可选 `material`，材质引用必须在本文件定义。

### 4.1 墙、楼板、柱梁

| type | 必填/本文要求字段 | 可选字段和限制 |
| --- | --- | --- |
| wall | from、to、thickness>0 | material；墙水平长>0、to.y>from.y |
| floor | from、thickness>0；矩形另有to | shape=rect/circle/polygon；material；矩形两点Y相同，宽深均>0 |
| column | base、height、bottomRadius、topRadius、style | style=modern/chinese_wooden/doric/ionic/corinthian；可加 flutes、entasis、inclination |
| beam | from、to、crossSection、width、height | crossSection=rect/circular/i-beam；非零中心线 |

四面正交外墙使用共享 XZ 端点，按楼层分墙，洞口附着本层实际墙。直角接头由 Core 处理，不叠一堵相同墙“补角”。

当前直角接头会在内部延伸渲染墙端并同步调整切孔局部位置，**作者仍从原墙轴线起点计算门窗from[0]，不要额外加半墙厚**。该自动处理只对适用的wall接头生效，不能推广到独立box、任意组件、斜交或墙与扫掠体的所有组合；这些接头按实际实体外缘设计，不将同一补角方法重复使用。

楼板有三种明确表达：`shape:"rect"`（默认）用from/to；`shape:"circle"`用from/radius/segments；`shape:"polygon"`用from/polygon/holes。所有楼板从板底 `from.y` 向上加厚，顶面为 `from.y+thickness`。

多边形的 `polygon:[[x,z],...]` 和 `holes:[[[x,z],...],...]` 是**相对from的局部米制坐标**，不是世界坐标。外轮廓至少三点，允许凹多边形；孔洞必须完全位于轮廓内，彼此不能相交、相切或嵌套，轮廓不能自交。顺/逆时针均可，推荐不重复首点。孔洞是真实贯穿板厚的开口，包含洞壁，不会自动生成护栏或楼梯。

```json
{"type":"floor","id":"upper_slab","shape":"polygon","from":[-6,3.4,-4],"thickness":0.2,"polygon":[[0,0],[12,0],[12,8],[0,8]],"holes":[[[4,2],[7,2],[7,6],[4,6]]],"material":"stone"}
```

此例板顶3.6m，世界洞口X为−2～1、Z为−2～2。楼梯井、中庭、池口可直接开孔；上层地板、吊顶和饰面必须同步避让。需要兼容旧引擎或未经更新的后端设计/校验链时，仍使用§8.1拆板；本次没有修改后端，不宣称后端Agent已支持新字段。

**梁吸附边界**：Core 可能把 XZ 靠近圆柱轴线的 beam 端点吸到柱顶（当前距离阈值约 bottomRadius+0.05m，未按原 Y 区分装饰杆）。精确细木条、竖格栅、斜撑优先用有明确变换的 box；通长梁可真实挑过柱轴。不能为了报告通过把设计需要的构件删掉。

wall/beam 的 `curve` 存在圆弧等能力。最稳妥的附墙开口采用直墙；已理解弧长语义时，可用单段 `{"type":"arc","center":[cx,0,cz],"sweep":90,"segments":24}`。曲墙开口的宽和沿墙位置按弧长，不以直线弦长替代；复杂多段/椭圆/悬链曲线不据此保证门窗编译兼容。

### 4.2 屋顶 roof

字段：`type/id/roofType/span/depth/height/thickness/position/material?`。span 为世界 X 覆盖宽，depth 为世界 Z 覆盖深，position 的 XZ 为中心。给每个真实体量分别定位，不依赖自动定位。检查实际墙外皮与设计出檐。

| roofType | 标高/形态 | 注意 |
| --- | --- | --- |
| flat | 底=position.y，顶=position.y+thickness；height 可写 thickness | 平顶；女儿墙/压顶另建 |
| gable | 檐外表面=position.y，脊顶=Y+height；实体最低可至Y−thickness | `ridgeAxis:"x"/"z"`；默认Z。当前是封闭楔体，不能当可住阁楼 |
| hip | 四坡；檐外表面=Y，向下加厚 | 正方形收尖，长方形有脊；ridgeAxis 不控制它 |
| dome | 半径=min(span,depth)/2 | 外观穹顶，不承诺可用内壳空间 |
| chinese_curved | 中部檐面=Y，脊=Y+height，角额外抬升 | 可加 eaveCurveHeight、curveProfile=gentle/steep；脊沿Z |
| chinese_pagoda | 从position.y叠檐 | tiers、tierHeight、eaveOutset、shrinkFactor；不自动生成楼层/交通/封顶 |

原生 roof 可能根据宿主墙上下文自动增加檐口，不能发明 `eaveTrim.enabled` 控制它。小雨棚、玻璃天窗等如用 roof 触发了整栋承托识别，应先确认其是否真是独立建筑屋面；局部薄板可用原语表达，但仍需实际洞口、框架和基座。

坡面局部高程，`dx=x−cx`、`dz=z−cz`，仅用于覆盖范围内：

```text
双坡脊沿Z：Ytop=Y+height×(1−|dx|/(span/2))
双坡脊沿X：Ytop=Y+height×(1−|dz|/(depth/2))
四坡：r=min(span,depth)/2
      Ytop=Y+height×min((span/2−|dx|)/r,(depth/2−|dz|)/r)
四坡下表面按当前实现减 thickness；曲面屋顶不要套此公式。
```

瓦垄、屋脊、老虎窗、斜玻璃、檩条和光伏格线从实际坡面算位置。不能将水平放置的装饰认作贴坡构造。坡顶下的封口、山墙和室内顶面需要另作空间核对。

### 4.3 楼梯 stair

字段：`type/id/from/to/width/stepCount/stepHeight/stepDepth/material?`，后面三个踏步参数显式填写。

```text
R=to.y−from.y>0
D=sqrt((to.x−from.x)^2+(to.z−from.z)^2)>0
N=正整数
stepHeight=R/N；stepDepth=D/N
第i级中心XZ=fromXZ+(i+0.5)/N×(toXZ−fromXZ)，i=0..N−1
第i级踏面顶=from.y+(i+1)×stepHeight
```

from/to 为起止边的中心线位置，width 向两侧展开。尺寸链一致时，末级远边到达 toXZ、顶面到达 to.y。原生阶梯不自动生成平台、完整梯板、栏杆、洞口或楼梯间。

### 4.4 通用 primitive

共同字段：`type:"primitive"`、`id`、`shape`、`position`、`material?`，可选 `rotation`、`scale`；默认 scale=[1,1,1]。负缩放涉及反射和文字朝向，不作为普通改变朝向的方法。

| shape | 几何参数 | 限制 |
| --- | --- | --- |
| box | dimensions=[宽,高,深] | 三项正数，局部XYZ，中心锚点 |
| sphere | radius；segments?、heightSegments? | 正半径；可scale成冠簇/石块 |
| cylinder | height；radius 或 radiusBottom/radiusTop；segments? | 沿局部Y；中心锚点；上下半径不同时形成锥台 |
| profile_sweep | path；profile=[[u,v],...]、closedProfile?、caps?；或radius/segments圆截面 | 至少两个连续不重合路径点；闭合截面不等于路径闭合 |

`profile_sweep` 默认 `caps:false`，保持旧文件的开放端面；需要封闭实体时显式写 `closedProfile:true,caps:true`。端盖支持简单凹截面，拒绝自交/退化截面；`closedProfile:false`不能要求caps。扫掠仍不是布尔挖洞工具，路径急转、截面过大可能自相交，封了端盖也需要检查实际形体。path本来用世界坐标时保持position=[0,0,0]，不要再次世界平移；使用局部坐标时只加一次整体变换。

```json
{"type":"primitive","id":"thin_roof_panel","shape":"profile_sweep","profile":[[-0.08,0],[0.08,0],[0.08,0.16],[-0.08,0.16]],"path":[[0,3.6,0],[4,4.8,0]],"closedProfile":true,"caps":true,"material":"metal"}
```

截面点使用路径标架中的[u,v]，不是固定世界XY。端盖可以简化线脚、封边、三角截面实体等构造，不能自动保证复杂屋面的拼接、支承和可用阁楼。

沿两端点 A/B 放置长轴为局部Y的 box 杆件：

```text
d=B−A；L=length(d)>0；center=(A+B)/2
dimensions=[杆宽,L,杆深]
rotation=[atan2(d.z,d.y),0,−asin(d.x/L)]
```

这是 XYZ 欧拉顺序下的一种确定朝向；使用前确认长轴确为Y。局部整组家具旋转必须同时变换每个零件中心和朝向，不能只转椅背不转椅脚。

圆柱 `segments:3` 可形成有端盖的三角棱柱；通过局部缩放和旋转可表达薄三角玻璃/封口。此为可选构造技法，不让所有建筑默认出现玻璃锥顶。

### 4.5 家具 furniture

字段：`type/id/subtype/position/dimensions:{width,depth,height}/material?`，可选 `rotation:[rx,ry,rz]`、`style`。底面锚点。

subtype 仅：`table/chair/sofa/bookshelf/bed/wardrobe/nightstand/tv_cabinet/lamp/tile`。不能发明 `kitchen/toilet/coffee_machine/tree/pool`。这些用途由原语组合表达。`furniture.lamp` 外形不等于真实照明，使用第7节。

需要更精细的家具可用原语组成座面、靠背、脚、柜体、台面与陈列；不能用不可见内层零件堆数量。按家具外缘和椅子拉出范围保留通道。

### 4.6 原生 opening

字段：`type/id/parentWall/from/width/height/style/material?`，depth 可选；style=rectangular/arched/gothic/circular。会在墙上开洞并生成对应覆盖面。常规门窗优先用 components；门窗组件已负责开洞，不再手工叠加同位置 opening。纯月洞等要核对覆盖面材质与真实视觉，不以透明零厚板猜测“空洞”。

## 5. 组合构件字段集

组合构件放在 `geometry.components`，不会创建新的渲染原语。默认写实际世界坐标；有 parentFloor/parentRoof 时会改变局部坐标语义，初次创作可省略这两类附着。

### 5.1 门 door 与窗 window

共有必填：`type/id/parentWall/from/width/height`。

- door 可选：`frameWidth/frameDepth/leafDepth/frameMaterial/leafMaterial`、`openingStyle:"rectangular"/"arched"`、`doorStyle:"single"/"double"`、`leafRows`（1～8）。
- window 可选：`frameWidth/frameDepth/glassDepth/verticalMullions/horizontalMullions/mullionWidth/frameMaterial/glassMaterial`。窗棂数量非负整数；不要为了“细致”把玻璃全塞满。
- 框宽必须给中间留正净空；frameDepth 与墙厚、leafDepth/glassDepth 匹配。无意偏离墙中心线的法向偏移可能让玻璃在墙内；普通洞口偏移先用0。
- 可选 `interaction:{mode:"swing"|"slide"|"lift",hingeSide:"left"|"right",openAngle:90,openDistance:数值,initiallyOpen:false}`；只填相关字段。双开/拱形门由组件生成，不手写内部 `_interaction`。
- 普通门建议显式 interaction；静态窗可以省略。推拉扇和轨道由当前组件实现，不用额外平移同一片玻璃假装动画。lift 是受墙顶净空约束的刚体升降，不等于真实卷帘折叠仿真。

父墙水平端点 A/B，`u=(B−A)/L`，二维法向 `n=[−u.z,u.x]`。令 from=[s,b,o]、开口宽w高h：

```text
开口底边中心XZ=A+u×(s+w/2)+n×o
中心Y=b+h/2
由目标中心C反求：s=dot(C−A,u)−w/2；o=dot(C−A,n)
0≤s；s+w≤L；墙底≤b；b+h≤墙顶
```

示例：后墙由 [10,0.3,8] 指向 [0,3.3,8]，窗宽1.4、目标中心X=7、窗底Y=1.0，from=[2.3,1.0,0]，不是[7,1,8]。from[1]始终是世界Y，二层窗不能再加一次层高或忘记层高。

需要上下对齐或等距节奏时，先建立该立面的**世界坐标中心集**，再逐层根据各宿主墙的起点/方向反算s；不能把相同from[0]复制给反向或起点不同的墙。退台与L形墙面按实际分段排布，每个候选洞口都重新检查墙长、墙高、转角和隔墙位置。上下对齐是所选立面秩序，不禁止有设计依据的错列、挑高窗或非对称开口。

同墙洞口不能无意相交；旁边的重复墙、饰面、砖条也不能重新挡住洞。窗套和窗台围绕洞口边缘另建，不覆盖可见玻璃。

### 5.2 其他组合构件

各项都有 type/id，可选 material。详细可选尺寸必须遵守 Schema；下面给出可直接创作的常用字段。

| type | 核心字段 | 常用可选项 |
| --- | --- | --- |
| railing | path、height | postSpacing、postRadius、railRadius、railLevels（0～1比例）、infillType=glass/panel、infillThickness、infillTopRatio、infillMaterial |
| canopy | parentWall、from、width、depth、thickness | supportCount、supportSize、supportMaterial |
| balcony | parentWall、from、width、depth、slabThickness | railingEnabled、railingHeight、postSpacing、railingMaterial |
| bay_window | parentWall、from、width、height、projectionDepth | frameWidth、frameDepth、frameMaterial、glassMaterial |
| ramp | from、to、width、thickness | railingSides=none/left/right/both、railingHeight、postSpacing、railingMaterial |
| cornice | path、profile（二维截面点） | closedProfile；与扫掠相同，不能依赖端盖 |
| chimney | position、width、depth、height | wallThickness、capHeight、capMaterial |
| light | position | fixtureType=bulb/table_lamp，或body自定义；详见第7节 |
| elevator | position、dimensions:{width,depth,height}、floorHeight、floorCount | initialFloor（0基）、frameMaterial |

canopy/balcony 的 from[0]是沿墙起点；Y分别为安装高度/阳台完成面，外挑方向由墙与建筑包络推定。凹院/内墙可能与设计意图不同，需真实检查；不能因此保证任意凹多边形外挑正确。复杂露台可用独立楼板+栏杆。

railing 的 path 默认世界坐标基线，height 向上；坡梯扶手可沿上升路径。不要跨过楼梯到达口、入口或通行门。elevator 只生成简化轿厢/导轨/按钮，不生成井壁、楼板孔、层门或完整设备仿真；所有层停靠高度要匹配完成面。

## 6. 材质与颜色

每个材质显式包含：`baseColor:[r,g,b]`、`roughness`、`metallic`、`albedo`、`lightingCondition:"D65_noon"`。RGB 与前三个标量都用0～1，通常albedo=1。不是CSS颜色或0～255。主材料负责大面积，辅材料负责框架/收边，强调色集中在少数节点。

```json
{
  "plaster":{"baseColor":[0.84,0.82,0.76],"roughness":0.85,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
  "wood":{"baseColor":[0.34,0.19,0.10],"roughness":0.58,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
  "frame":{"baseColor":[0.10,0.13,0.13],"roughness":0.35,"metallic":0.6,"albedo":1,"lightingCondition":"D65_noon"},
  "glass":{"baseColor":[0.87,0.93,0.94],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.88,"ior":1.5,"thickness":0.012}
}
```

可选物理字段：`materialClass=standard/glass/clearcoat/fabric`、`opacity`、`transmission`、`ior`、`thickness`、`attenuationColor`、`attenuationDistance`、`clearcoat`、`clearcoatRoughness`、`sheen`、`sheenColor`、`emissive`、`emissiveIntensity`、`side=front/double`。颜色/多数比例用0～1，厚度/衰减距离为米，光强非负。

玻璃优先用 transmission 和低粗糙度，不同时无理由降低 opacity。木/石/灰泥通常 metallic 接近0，金属框可以更高。粗糙度与材料尺寸要有区别，不能整栋都像塑料或镜子。透明材料要有正确朝向、厚度和场景背景；参数本身不能保证照片质感。

**材质尺度和表面分工**：主墙、檐底、地面、窗框、玻璃至少区分粗糙度与构造厚度；不要把所有细节做成无厚度、共面的色条。已有真实资产时可用textures的baseColor/normal/roughness/metalness/ambientOcclusion通道，normalScale控制凹凸；资源格式按Schema，不伪造URL/hash/base64。墙、矩形/多边形楼板和box已使用逐面米制UV，uvScale=[2,2]表示这类表面每米重复两次；球、圆柱侧面等保留各自专用展开，不套用同一比例。缺真实贴图时用材料颜色、真实分缝和现有程序化能力，不输出虚假资产依赖。

无外部图片也可以用真实分缝、进退和受控色差表达材料。几何分缝与材质砖纹不要两套频率混杂。已实现的程序化纹理：

```json
{"type":"brick","brickSize":[0.24,0.075],"mortarWidth":0.008,"mortarDepth":0.003,"bond":"running","seed":13,"colorVariation":0.08,"roughnessVariation":0.05,"edgeWear":0.08}
```

上例作为材质的 `procedural` 值；bond还可用stack。不支持凭空写procedural wood/marble。mortarWidth应显著小于砖高。可选 secondaryColor 为RGB；weathering子对象可有 amount、scale、efflorescence、verticalStreaks、baseDampness。seed只复现材质变化，不是建筑方案生成器。

材质 effects 为数组；各项是完整对象：weathering 需dustColor/dustOpacity/crackIntensity/colorFade；moss需mossColor/coverage/pattern（base_up/patchy/edge）；edgeWear需wearColor/intensity；grain需intensity/scale。可以全部省略，不以做旧掩盖缺失构造。

## 7. 招牌、真实灯和水

### 7.1 文字必须存在于 WILD

仅 `primitive.box` 支持 `label:{text:"建筑名称",color:[1,0.85,0.5],fontFamily:"sans-serif"}`。fontFamily可serif；text为1～256非空字符，换行写 `\n`。

文字贴在盒子的**局部+Z面**，跟随整体变换。正面朝−Z时可令rotation=[0,3.141593,0]；朝+X时可令rotation=[0,1.570796,0]。牌子有实际宽高和厚度，文字不可被同位置墙、雨棚、柱子、树或后来前凸墙面遮住。检查正面与主要到达视角，不能只检查 `label.text` 正确。

这是渲染器的 Canvas 字体纹理，不是外部生成图片或细杆拼字。不同机器中文字体可能不同。字多时增大可读面积、分行或按需求简化副标题，不能擅改指定名称。

### 7.2 自制灯具既有亮面，也能照周围

`emissive` 只控制表面亮；真实照明应在一个发光原语上增加：

```json
{"lightType":"point","color":[1,0.78,0.46],"intensity":10,"distance":5,"initiallyOn":true}
```

该对象作为 `primitive.lightSource` 值，**不是额外的元素 type**。可选 lightType=spot，angle为(0,90]度、direction为非零局部向量（默认向下）、offset为局部包围盒中心的偏移。intensity非负、distance>0。杆、外壳、遮光罩仍是普通实体，只给真正发光部位一个光源。

默认point/intensity25/distance8/angle45/initiallyOn=true；这些是实现默认值，不是美学推荐。按空间试调，夜景避免满屏过曝。当前渲染器强档约为指定强度3倍。实时局部灯按相机和画质选择，流畅/均衡/精细上限分别为4/8/12个，精细档最多两个重点局部灯投影；灯具发光表面始终保留，不等于文件只能放12盏灯。不要为追求数量给每根装饰杆绑定光源。

光源offset应使其位于真实发光空间，不能埋进另一个实心灯罩或墙内。发光网格自身不遮住自己的光，独立灯罩、墙板仍可遮挡重点灯。非重点灯仍可能穿墙；这不是完整全局照明或全灯阴影保证，重要照明需实际检查。

原 `light` 组件也能发光，可写lowIntensity/highIntensity/distance/color/angle/initiallyOn；预设fixtureType可省略尺寸使用默认值。自定义body数组每项复用primitive几何字段但不写id/type，可标一项interactive:true；**body.position是世界坐标，省略才继承组件position**。不要把[0,0,0]误当相对灯杆的偏移。light组件建议显式initiallyOn:true，避免默认关灯。

### 7.3 水面真实性先从池体开始

水面用薄水平几何，水材质可命名 `water` 并写 `materialClass:"glass",ior:1.333`，推荐从transmission约0.9～0.96、roughness约0.06～0.12开始观察。选择浅而克制的水色，池底/池壁的颜色与水深会改变观感，不能全靠浓绿色透明板。

真实关系：场地拆板留池口 → 实际池底 → 池壁/压顶 → 低于压顶的水面。记录水面标高−池底完成面为池深；上方的场地板/装饰地面不能仍然盖住池底。

新前端可用多边形楼板holes留池口，旧链路用拆板。水的几何厚度只负责表面/体块，材质thickness是透射吸收的光学参数，不能用它冒充已生成池深；attenuationColor/attenuationDistance共同控制透过后的水色。已有池底时避免高金属度、过深底色和多层重叠水面。

精细档可开启水面场景反射，捕获主水平水位上的建筑和环境，并叠加波纹扰动与掠射角反射；其他水位或低画质保留环境反射。反射、动态开关和全局透明度属于前端显示设置，不新增waterAnimation/reflection等未实现的WILD字段。当前没有真实流体、完整焦散或多水位同时反射，不能靠描述词宣称具备。

动态法线波、水透明度控制、天空/地面环境反射由当前渲染器提供。没有场景SSR完整镜像、真实流体或完整焦散求解。关闭动态冻结波相。不要向WILD添加waterAnimation、波纹Shader或相机字段；有工具时在有环境光照的查看器另验近景。固定基线的外部地面也可能盖住下沉池，须区分显示场地与模型池底。

## 8. 用计算闭合空间关系

### 8.1 单孔、多孔与兼容拆板

当前前端/Core优先使用§4.1的polygon/holes表达同一块有孔楼板，避免重复板片；独立的铺装、吊顶和面层仍需分别避孔。需要兼容旧引擎、原后端自动设计链时使用下列矩形拆板方法。不要混用两种表达，在原多边形孔上又补一块整板。

板范围 `[x0,x1]×[z0,z1]`，孔 `[a,b]×[c,d]` 位于板内，拆成：

```text
左：[x0,a]×[z0,z1]；右：[b,x1]×[z0,z1]
前：[a,b]×[z0,c]；后：[a,b]×[d,z1]
```

舍弃零面积片，各片板底与厚度相同。检查板片无重复面积、洞内无板、总面积=原面积−孔面积。多个孔先求孔并集，再按所有X边界分条扣除对应Z区间，不能把每个孔的四片直接叠加。木地板、吊顶、地毯和另一个体量的板也不能补盖洞口。

### 8.2 楼梯是空间链，不是一段斜线

完整核对：起步面 → 梯段 → 实际平台 → 第二跑 → 上层到达板 → 可转向前平台 → 门/通路。平台覆盖整梯宽，第二跑与第一跑横向错开且不穿插；上口护栏不能封路。

洞口优先覆盖梯段和中间平台的完整投影，含全宽和合理侧余量。若保留低位梯段上方的楼板，逐级计算“上方最低板/梁底−踏面顶”的净空，同时检查边缘和全宽；不能仅给最后一踏开小洞。约2m可以作为概念模型排查起点，不是所有项目的合规标准。

**数值构造例**（不是默认布局）：F1=0.30、F2=3.70，两跑各10级，步高0.17、步深0.28，梯宽1.2。第一跑中心X=1.0，Z从2.0到4.8，至+2.00；中间平台范围X=0.4～3.2、Z=4.8～6.2，顶+2.00。第二跑中心X=2.6，Z从4.8返到2.0，至+3.70。洞口覆盖X=0.3～3.3、Z=2.0～6.3；上层Z<2.0保留至少1.4m深前平台，再接门和通道。按实际板边和护栏细节复核最后一踏，不能因数字相等就认定可达。

### 8.3 支承与围护

水平梁底对柱顶、屋面下皮对檩条顶；坡面接触从实际方程推导。屋面覆盖实体外墙厚度，不能只到墙轴线。退台/天窗/老虎窗独立分配承托，不将任何高处小墙一律解释为下一层退台。

不能以互相穿插几十厘米伪装承托；允许有意的实体连接，但记录接触/嵌入关系。玻璃露台栏杆、悬挑、檐口、雨棚等要有可辨认的节点表达；几何贴接不等于结构承载证明。

围护在所有侧面闭合，露天院子可开敞，室内塔楼不能忘记侧墙。室内外有门和实际平台衔接。屋顶草坪应有真实基板/边缘，不能只有悬浮绿球。

### 8.4 避免遮挡和共面

有实际厚度和进退的窗套、腰线、压顶比完全同面的薄条稳定。不要叠两片同材质同平面；需要饰面时确定其基底、外皮和缝宽。给砖/木饰面按实心墙区裁分，不穿过窗洞。招牌读得见、门开得出、桌椅脚落板内、盆栽与对应层标高一致。

场地和建筑基座可有设计的实体接触，但同标高重复铺板常产生闪烁。将铺装、花池、台阶、水池按边界分区，去掉重复几何；不要用整体上移建筑消除局部共面。

### 8.5 修改参数时沿依赖关系重算

蓝图的尺寸互相依赖。修改前列出受影响的宿主、派生几何和同一构造的重复实例；修改后读回**最终文件**核对，不能只看生成函数返回成功。

| 修改输入 | 必须复核的关联项 |
| --- | --- |
| 楼层完成面/层高 | 墙底顶、板底、门窗世界Y、家具底、两跑梯/平台、楼板孔、护栏、井道停靠 |
| 墙起点/方向/厚度 | 门窗沿墙与法向坐标、转角、内外皮、窗套/腰线、相邻内墙与开门空间 |
| 建筑轮廓/退台 | 内墙连接、板片并集和孔、各体量屋面、暴露边防护、露台门与通路 |
| 屋面高度/跨度/坡度 | 瓦垄/脊、檩条、山墙封口、天窗/老虎窗/烟囱与主坡面的接触 |
| 家具/招牌/灯尺寸或位置 | 组成零件的整体变换、落地/遮挡、字面方向、光源局部偏移和照射方向 |

脚本有一份设计参数表即可，派生值从它计算，避免多处手填相同常数；纯文本AI也要使用同一套设计事实。重复实例共享错误时一起修正，有意不同的实例保留其差异，不把“联动”变成修改全楼所有同类对象。

验证至少区分：生成时断言 → 独立回读盘上JSON → Core编译/重建 → 受影响视图/关系检查。生成器内部公式可能自洽但用错引擎锚点，因此需要独立口径。复核可记录“对象、预期关系、实际值、允许误差、依据”，不要求为了每栋建筑新增一套通用规则。

### 8.6 门廊和分层承托的尺寸链

有柱门廊、无柱小挑檐、单坡雨棚、格栅顶或拱廊都可选择，不预设所有现代别墅必须双柱平顶。已经选定柱梁板叠放时，把支承链写成明确上下皮，不把柱顶、梁中心和棚板底混作同一高度。

例如梁位于棚板下，室内完成面F、最低梁底净高H、梁高hb、棚板厚tp、柱底Ybase，则：

```text
梁底 = F+H；柱顶 = 梁底
柱高 = F+H−Ybase
梁中心Y = F+H+hb/2
棚板底 = 梁顶 = F+H+hb
棚板中心Y = F+H+hb+tp/2
```

上式用于box等中心锚点棚板；floor/flat roof则直接填写板底。没有下置梁时去掉hb这一层；有柱头/柱础时明确它们占用的高度。棚宽/深依据保护入口的范围、柱截面和支承位置推导，检查柱全截面在受托范围内、梁端连接、门扇扫掠、最低净高及台阶通路。不能强制全高玻璃顶等于板底：窗框、门楣或实体上口可能本来就占据其上方空间。

### 8.7 圆形、环形和分段体量

圆形空间先定圆心C=(cx,cz)、半径R和分段数n，再派生墙、柱、开口与屋面，不分别手填圆周点：

```text
第k点：Pk=(cx+R cosθk, cz+R sinθk)，θk=θ0+2πk/n
相邻点弦长：c=2R sin(π/n)
折面内切半径：r=R cos(π/n)
折面对圆弧最大偏差：e=R(1−cos(π/n))
一段直墙上宽w的居中洞口：s=(c−w)/2，要求w<c并留必要墙垛
```

按可接受轮廓误差、开间、构件能力和几何预算选n，不强制所有圆形建筑使用同一段数。墙在各段的真实弦线上，柱网可在内圈/外圈另设；柱是否外露由设计决定，不要求所有承重柱都脱离围护墙。圆形台阶也要核对整梯宽两侧与台基边缘的关系，不能只让中心线接到圆周。

圆台/棱台分段半径可用`r(y)=rb+(rt−rb)×(y−yb)/h`，中心Y=yb+h/2；对应cylinder的上下半径、height和segments。少分段是有意的多边形表达，不能冒充平滑圆面。原语是实体，不能由此推断旋转体自动有可使用内腔。

球面某高程的圆截面半径为`sqrt(R²−(y−cy)²)`，仅在`|y−cy|<R`内有效。观景环廊/空心带与实心圆盘不同：有内孔就实际表达内孔，不能用完整cylinder圆盘代替环带。扫掠路径首尾、截面方向和接缝按实际实现复核，不默认多绕一段就没有穿插。

### 8.8 源构件身份与宿主关系

当前几何宿主统一为parentWall、parentFloor、parentRoof；attachment.parent与排布onSurface.parent也参与引用检查和级联删除。不要为组织场景再给每个对象重复写parentId/children；editor.groups是编辑分组，不等于几何依附或房间归属。

parentWall的from仍是[沿墙距离,底部世界Y,法向偏移]；parentFloor使用父楼板顶面原点的局部坐标；parentRoof使用父屋顶中心和屋面高度的局部坐标。移动宿主时，局部坐标不应再加一次世界位移；墙附件的世界Y只加一次。宿主与附件同时选中也只移动一次。单独移动屋面附件时还要换算坡面高度，不能把局部Y当世界Y。

用户编辑源组件ID；开洞、框架、玻璃等生成ID由编译器维护，不把它们重新写回components、持久化运行时状态或作为下一稿独立源构件。修改窗宽应更新源window，删除墙会级联删除真实依附者；不要只删除玻璃网格后宣称删了窗。

本次明确边界：带附件的楼板/屋顶整体旋转、原生曲墙opening直接拖动、多边形楼板的parentFloor依附尚未形成可靠完整通路。前两者限制对应编辑入口；多边形附板仍会报告不支持，不能用包围盒猜孔洞。当前assets只承载PBR纹理集，没有通用GLB实例或spin运动字段，禁止从editor示例照抄为WILD语法。

## 9. 细节的构造方法与成本

细化一个主要节点可按“承托/基底 → 主体 → 边框/分缝 → 连接/压顶 → 使用物件”展开。尺寸由主体派生：窗套跟随洞口，檐口跟随屋面，货架商品跟随层板，不单独凭目测放置。

| 对象 | 典型层次 | 有意义的差别 |
| --- | --- | --- |
| 窗口 | 实际洞、框、玻璃、窗台、上口/侧口、遮阳 | 深窗/通高窗/带竖片，不只是改窗色 |
| 平顶 | 顶板、女儿墙、压顶、设备或绿化边缘 | 露台可达与防护，天窗真实开口 |
| 坡顶/木亭 | 支承、坡面、檩条、瓦垄/脊、封檐 | 按坡面定位，短杆不退化 |
| 店铺入口 | 通路、门槛、门框、雨棚、店名、照明 | 入口可辨认而不堵通行 |
| 吧台/柜台 | 基座、柜体、台面、操作/陈列、灯 | 用户侧与工作侧不同，后场能到达 |
| 书架/货架 | 底座、立柱、层板、分类物件、端头 | 双面方向正确、每侧有通道 |
| 景观 | 土/花池、边缘、枝干、大小冠簇、地被 | 有疏密与高低，不用等距绿球遮建筑 |

先选择主视角和近人尺度上最有效的节点，不默认每块瓦、每页书或每片叶都建模。重复的连续细件控制段数和密度；减少装饰复杂度时保留空间、洞口、交通、支承和文字。

纯文本模型应先预估输出容量，选择能完整展开的方案。约几十至几百个条目可以是合理起点，视模型容量而定；不是最低数量要求。上千构件作品更适合工具展开与看图迭代。不能因截断把半份JSON当成完整交付，不能把“其余同上”写进数组。

## 10. 参考图复建与修订

先提取五类可见事实：主次体量和层数、正侧面左右关系、屋面轮廓、开口节奏、最有识别性的节点。以一项合理尺度作比例标尺，其他尺寸按一致比例推定。不可见后场和结构采用满足使用的保守补全，另记假设。

先用低细节体量和参考方向相机检查比例与左右，再加结构/围护，最后加材料和细节。用户图片上的人物、宠物、水印、播放器按钮、摄影背景和景深，不默认是建筑几何需求。

左右错误先核对相机和世界坐标，不应只让相机绕到另一侧掩盖平面关系。确需镜像时，同步体量范围、门窗宿主、细节、楼梯/平台、灯方向和文字可读性；不能只把半个模型负缩放。

每次反馈按“看见的问题 → 所属空间关系 → 坐标/构造修订 → 重新验证”处理。保留旧稿。有些错误只有真实图才能发现：塔墙盖字、雨棚挡字、椅脚出露台、植物太密、池底被场地盖住。零诊断不能排除它们。

## 11. 自检、工具与交付边界

### 11.1 所有模型都要做的文本自检

- JSON闭合，使用有限数字，ID唯一，type/shape/枚举准确；输出meta.version不是本文版本号。
- 所有材质、宿主引用存在；components与elements分开；不含内部状态/脚本占位。
- 场地包络满足需求，标高链一致；每层真实建模，不能用元数据代表省略楼层。
- 墙角相接，门窗沿墙坐标正确、不越界、不被饰面封住；门底对通行面。
- 梯段尺寸闭合，完整洞口、平台和上口通路存在；护栏不封门、不封上梯口。
- 屋面覆盖和下部封口存在，构造接触有依据；未把实心楔体当阁楼。
- 家具落地、开口/通道不堵，露台物件全脚在板内；楼层Y没有遗忘。
- 招牌内容和朝向正确；发光面与真实光源分开；池底、池壁、水面及场地开口相互一致。
- 形态和细节体现需求；同类新稿在核心空间组织上有实质区别，未机械套用示例。
- 用户明确的层数、数量、面向和功能逐项可定位；数量以设计对象计，不把组件编译的内部零件充数。
- 修改过的设计输入已沿依赖关系重算，并从落盘值复核；没有靠统一降低精度或放宽容差掩盖偏差。

### 11.2 有工具时分层验证

| 层级 | 实际动作 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| L0 | 严格JSON与原始Schema | 字段/类型/必填符合契约 | 所有引用/空间/效果 |
| L1 | ID、材料、宿主、明确尺寸链 | 被实现的引用和计算检查 | 所有碰撞、使用与美感 |
| L2 | Core组件编译、实体重建、有限包络/网格 | 引擎能生成对应几何，诊断可查 | 画面好看和动线完整 |
| L3 | 可选完整项目后端关系检查 | 当前关系规则被执行 | 规则未覆盖情形与审美 |
| L4 | 真WebGL四视图、日夜/局部/剖切，实际查看 | 该设置下可见结果与发现的问题 | 施工、结构承载、法规或全空间可达认证 |
| L5 | 来源hash、输入图绑定、脚本字节重放 | 报告与产物同源、过程可复现 | 其他模型首次生成的成功率 |

工具返回warning/error要阅读原文。真设计错就改设计；表达错就改作者参数；疑似检查器边界时保留原报告，并用明确范围的几何复核佐证。不能关闭规则、改容差、减少用户功能或把局部通过写成全图通过。

检查实体接触时先区分有意连接、无意穿插、设计留缝和通行净距。旋转构件的世界AABB只能筛候选，其相交不等于实体碰撞；必要时在实际局部标架或网格上复核。不能把所有构件强制成“零体积交叠”，也不能把有意嵌入当作任意穿插的豁免。

网格有限、法线朝向、开放边和封闭性分别检查：透明双面材质不会修补缺失几何，某面看得见也不证明网格封闭。设计为实体的部件才按对应拓扑检查封闭性；薄膜、开放扫掠等不能一律要求每条边恰共享两面。本文没有提供完整OBB/SAT、全网格闭合或通行碰撞工具，不能因读到这些检查方法就宣称已经执行。

只拿到主文档的AI到L0/L1也只算文本推演，不能勾选实测。最终只输出JSON时无需违反格式再加免责声明；验证状态应由调用方/另存的交付说明记录，JSON内部也不能伪造成功状态。

资料包附有原始Schema、独立检查器、完整Core快照和必要项目渲染模块；可选安装后运行。原项目后端不随包安装；`DesignDocument`和`project_drawing`也不等于WILD编译器。文本直出不强制引入Agent流程。

## 12. 完整最小建筑例

下面是一层小茶室，用于展示文件闭合、标高、门窗、家具、招牌和灯的组合。它没有展示多层楼梯、复杂屋面或全部细部，不是未来别墅/咖啡厅的默认外形。修改设计时重新计算，不能只换meta.name。

<!-- FULL_EXAMPLE_START -->
```json
{
  "meta":{"version":"1.1","type":"building","name":"听风茶室 · 语法教学例"},
  "geometry":{
    "elements":[
      {"type":"floor","id":"site","from":[-6,-0.12,-5],"to":[6,-0.12,5],"thickness":0.18,"material":"stone"},
      {"type":"primitive","id":"plinth","shape":"box","position":[0,0.19,0.4],"dimensions":[6.24,0.26,5.04],"material":"stone"},
      {"type":"floor","id":"floor_l1","from":[-3.12,0.32,-2.12],"to":[3.12,0.32,2.92],"thickness":0.04,"material":"wood"},
      {"type":"floor","id":"porch","from":[-1.8,0.06,-3.1],"to":[1.8,0.06,-2.12],"thickness":0.3,"material":"stone"},
      {"type":"stair","id":"entry_stair","from":[0,0.06,-3.64],"to":[0,0.36,-3.1],"width":1.6,"stepCount":2,"stepHeight":0.15,"stepDepth":0.27,"material":"stone"},
      {"type":"wall","id":"wall_front","from":[-3,0.36,-2],"to":[3,3.22,-2],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"wall_right","from":[3,0.36,-2],"to":[3,3.22,2.8],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"wall_back","from":[3,0.36,2.8],"to":[-3,3.22,2.8],"thickness":0.24,"material":"plaster"},
      {"type":"wall","id":"wall_left","from":[-3,0.36,2.8],"to":[-3,3.22,-2],"thickness":0.24,"material":"plaster"},
      {"type":"roof","id":"roof_main","roofType":"flat","position":[0,3.22,0.4],"span":6.7,"depth":5.5,"height":0.18,"thickness":0.18,"material":"stone"},
      {"type":"primitive","id":"roof_cap_front","shape":"box","position":[0,3.44,-2.29],"dimensions":[6.7,0.08,0.12],"material":"frame"},
      {"type":"primitive","id":"roof_cap_back","shape":"box","position":[0,3.44,3.09],"dimensions":[6.7,0.08,0.12],"material":"frame"},
      {"type":"primitive","id":"roof_cap_left","shape":"box","position":[-3.29,3.44,0.4],"dimensions":[0.12,0.08,5.26],"material":"frame"},
      {"type":"primitive","id":"roof_cap_right","shape":"box","position":[3.29,3.44,0.4],"dimensions":[0.12,0.08,5.26],"material":"frame"},
      {"type":"primitive","id":"name_board","shape":"box","position":[0,2.86,-2.17],"dimensions":[2.1,0.36,0.08],"material":"wood","rotation":[0,3.141592653589793,0],"label":{"text":"听风茶室","color":[1,0.9,0.62],"fontFamily":"serif"}},
      {"type":"primitive","id":"pendant","shape":"box","position":[0,2.75,0.7],"dimensions":[0.16,0.12,0.16],"material":"glow","lightSource":{"lightType":"point","color":[1,0.78,0.46],"intensity":8,"distance":5,"initiallyOn":true}},
      {"type":"primitive","id":"pendant_cable","shape":"box","position":[0,3.01,0.7],"dimensions":[0.018,0.4,0.018],"material":"frame"},
      {"type":"primitive","id":"counter_body","shape":"box","position":[1.95,0.76,1.75],"dimensions":[1.4,0.8,0.7],"material":"wood"},
      {"type":"primitive","id":"counter_top","shape":"box","position":[1.95,1.2,1.75],"dimensions":[1.5,0.08,0.8],"material":"stone"},
      {"type":"furniture","id":"tea_table","subtype":"table","position":[-0.7,0.36,0.65],"dimensions":{"width":1.3,"depth":0.75,"height":0.74},"material":"wood"},
      {"type":"furniture","id":"chair_w","subtype":"chair","position":[-1.75,0.36,0.65],"rotation":[0,-1.5707963267948966,0],"dimensions":{"width":0.5,"depth":0.55,"height":0.85},"material":"linen"},
      {"type":"furniture","id":"chair_e","subtype":"chair","position":[0.35,0.36,0.65],"rotation":[0,1.5707963267948966,0],"dimensions":{"width":0.5,"depth":0.55,"height":0.85},"material":"linen"},
      {"type":"primitive","id":"front_sill_0","shape":"box","position":[-2.1,1.145,-2.16],"dimensions":[1.38,0.11,0.38],"material":"stone"},
      {"type":"primitive","id":"front_lintel_0","shape":"box","position":[-2.1,2.64,-2.15],"dimensions":[1.42,0.12,0.34],"material":"stone"},
      {"type":"primitive","id":"front_sill_1","shape":"box","position":[2.1,1.145,-2.16],"dimensions":[1.38,0.11,0.38],"material":"stone"},
      {"type":"primitive","id":"front_lintel_1","shape":"box","position":[2.1,2.64,-2.15],"dimensions":[1.42,0.12,0.34],"material":"stone"}
    ],
    "components":[
      {"type":"door","id":"entry_door","parentWall":"wall_front","from":[2.35,0.36,0],"width":1.3,"height":2.2,"frameWidth":0.055,"frameDepth":0.24,"leafDepth":0.035,"frameMaterial":"frame","leafMaterial":"glass","interaction":{"mode":"swing","hingeSide":"left","openAngle":90,"initiallyOpen":false}},
      {"type":"window","id":"window_front_w","parentWall":"wall_front","from":[0.3,1.2,0],"width":1.2,"height":1.36,"frameWidth":0.05,"frameDepth":0.24,"glassDepth":0.012,"verticalMullions":1,"mullionWidth":0.025,"frameMaterial":"frame","glassMaterial":"glass"},
      {"type":"window","id":"window_front_e","parentWall":"wall_front","from":[4.5,1.2,0],"width":1.2,"height":1.36,"frameWidth":0.05,"frameDepth":0.24,"glassDepth":0.012,"verticalMullions":1,"mullionWidth":0.025,"frameMaterial":"frame","glassMaterial":"glass"},
      {"type":"window","id":"window_east","parentWall":"wall_right","from":[1.25,1.2,0],"width":2.2,"height":1.36,"frameWidth":0.05,"frameDepth":0.24,"glassDepth":0.012,"verticalMullions":1,"mullionWidth":0.025,"frameMaterial":"frame","glassMaterial":"glass"},
      {"type":"window","id":"window_west","parentWall":"wall_left","from":[1.25,1.2,0],"width":2.2,"height":1.36,"frameWidth":0.05,"frameDepth":0.24,"glassDepth":0.012,"verticalMullions":1,"mullionWidth":0.025,"frameMaterial":"frame","glassMaterial":"glass"},
      {"type":"window","id":"window_back","parentWall":"wall_back","from":[1.8,1.2,0],"width":2.4,"height":1.36,"frameWidth":0.05,"frameDepth":0.24,"glassDepth":0.012,"verticalMullions":1,"mullionWidth":0.025,"frameMaterial":"frame","glassMaterial":"glass"}
    ]
  },
  "materials":{
    "plaster":{"baseColor":[0.84,0.82,0.76],"roughness":0.85,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
    "stone":{"baseColor":[0.6,0.61,0.56],"roughness":0.78,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
    "wood":{"baseColor":[0.34,0.19,0.1],"roughness":0.58,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
    "frame":{"baseColor":[0.1,0.13,0.13],"roughness":0.35,"metallic":0.6,"albedo":1,"lightingCondition":"D65_noon"},
    "glass":{"baseColor":[0.87,0.93,0.94],"roughness":0.08,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","materialClass":"glass","transmission":0.88,"ior":1.5,"thickness":0.012},
    "linen":{"baseColor":[0.65,0.69,0.57],"roughness":0.92,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"},
    "glow":{"baseColor":[1,0.82,0.52],"roughness":0.4,"metallic":0,"albedo":1,"lightingCondition":"D65_noon","emissive":[1,0.65,0.25],"emissiveIntensity":1.4}
  }
}
```
<!-- FULL_EXAMPLE_END -->

## 13. 如何发起任务

纯文本直出：

> 依据附件《WILD蓝图设计语言-v3.0》生成一栋【用途】。地块【宽×深】米，【层数】层，包含【功能】，风格【要求】，招牌写【名称】。请重新设计体量、空间、交通、立面和材料，输出完整自足WILD JSON，不输出脚本，不套用文档例子的布局。

同类新稿：

> 保留上一栋的【硬条件】，另设计一个同类型方案。把【例如中央楼梯、L形围院、平顶退台】列为需要避开的旧方案特征，在平面/剖面/交通/屋面中作出有用途依据的变化，保持【指定风格】，交付新的完整WILD。

有工具智能体：

> 阅读主语言与资料包README，先保存简明设计事实，再创建WILD。可以使用确定性脚本展开，但最终文件必须自足。只写指定交付目录，记录实际修订。依次执行随包检查、Core和真实渲染，查看四视图与必要剖切；按证据修订，报告已执行范围和保留问题，不改校验器来通过。

提高效果最有效的反馈，是指出具体空间/构造/画面问题及视角，例如“主入口被柱子挡住”“二层梯口没有转向空间”“立面需要深窗与檐口层次”；单说“再高级一点”无法规定应该改变哪种设计关系。
