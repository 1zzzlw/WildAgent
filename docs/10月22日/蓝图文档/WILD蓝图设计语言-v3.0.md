# WILD 蓝图设计语言 v3.0

面向 AI 的独立建筑创作规范。整理日期：2026-10-22。**本文版本为 3.0；输出文件的 `meta.version` 写 `"1.1"`，不能写 `"3.0"`。** 当前引擎将历史 1.1 归一到内部 1.0。本文在既有语言 1.3 和十二例审计基础上重新组织，不增加 WILD 语法。

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
| 其他类型 | 先推导真实使用顺序和空间邻接 | 从用途选择细节，不硬套上述家具组合 |

新中式可通过院落、檐下层次、木格栅、虚实与灰瓦表达；古典欧式可通过对称比例、柱式、窗套、檐口和坡顶表达；现代建筑可通过干净的主次体量、连续框架、凹进开口和材料交接表达。风格可以混合，但要有清晰主次和统一尺度，不把所有装饰叠到一栋上。

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

## 4. 基础构件字段集

以下记法列出字段，不代表可以把公式或变量写进 JSON。所有尺寸必须输出计算后的有限数。每行都另有 `id` 和可选 `material`，材质引用必须在本文件定义。

### 4.1 墙、楼板、柱梁

| type | 必填/本文要求字段 | 可选字段和限制 |
| --- | --- | --- |
| wall | from、to、thickness>0 | material；墙水平长>0、to.y>from.y |
| floor | from、to、thickness>0 | material；本文用矩形，两点Y相同，宽深均>0 |
| column | base、height、bottomRadius、topRadius、style | style=modern/chinese_wooden/doric/ionic/corinthian；可加 flutes、entasis、inclination |
| beam | from、to、crossSection、width、height | crossSection=rect/circular/i-beam；非零中心线 |

四面正交外墙使用共享 XZ 端点，按楼层分墙，洞口附着本层实际墙。直角接头由 Core 处理，不叠一堵相同墙“补角”。

`floor` 没有通用孔洞字段；楼梯井、中庭、电梯井和泳池必须拆成不重叠板片。圆形楼板可用 `shape:"circle"`、`radius` 和 `segments`，不填矩形 `to`，但不能因此获得任意多边形板。

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
| profile_sweep | path；profile=[[u,v],...]、closedProfile?；或radius/segments圆截面 | 至少两个连续不重合路径点；闭合截面不等于路径闭合 |

`profile_sweep` 不自动封两端端盖，不能冒充水密实体、布尔挖洞或万能三角墙。path 本来用世界坐标时保持 position=[0,0,0]，不要再次世界平移。确需局部坐标时，以局部path加一次整体变换。

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

默认point/intensity25/distance8/angle45/initiallyOn=true；这些是实现默认值，不是美学推荐。按空间试调，夜景避免满屏过曝。当前渲染器强档约为指定强度3倍，局部灯不投射阴影；不能保证穿墙光完全消除或宣称全局照明。

原 `light` 组件也能发光，可写lowIntensity/highIntensity/distance/color/angle/initiallyOn；预设fixtureType可省略尺寸使用默认值。自定义body数组每项复用primitive几何字段但不写id/type，可标一项interactive:true；**body.position是世界坐标，省略才继承组件position**。不要把[0,0,0]误当相对灯杆的偏移。light组件建议显式initiallyOn:true，避免默认关灯。

### 7.3 水面真实性先从池体开始

水面用薄水平几何，水材质可命名 `water` 并写 `materialClass:"glass",ior:1.333`，推荐从transmission约0.9～0.96、roughness约0.06～0.12开始观察。选择浅而克制的水色，池底/池壁的颜色与水深会改变观感，不能全靠浓绿色透明板。

真实关系：场地拆板留池口 → 实际池底 → 池壁/压顶 → 低于压顶的水面。记录水面标高−池底完成面为池深；上方的场地板/装饰地面不能仍然盖住池底。

动态法线波、水透明度控制、天空/地面环境反射由当前渲染器提供。没有场景SSR完整镜像、真实流体或完整焦散求解。关闭动态冻结波相。不要向WILD添加waterAnimation、波纹Shader或相机字段；有工具时在有环境光照的查看器另验近景。固定基线的外部地面也可能盖住下沉池，须区分显示场地与模型池底。

## 8. 用计算闭合空间关系

### 8.1 单孔和多孔拆板

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
