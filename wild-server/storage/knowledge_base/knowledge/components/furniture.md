---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: furniture
entity_name: furniture_component
topic: parameters
status: supported
authority: engine
primary_terms:
  - 家具
  - 桌子
  - 椅子
  - 书柜
  - 书架
  - 衣柜
  - 床头柜
  - 电视柜
  - 床
  - 茶几
  - 书桌
  - 餐桌
synonyms:
  - furniture
  - table
  - chair
applies_to:
  - 家具
  - 桌子
  - 椅子
  - 书柜
  - 衣柜
  - 床头柜
  - 电视柜
  - 床
  - 茶几
---

# 家具（furniture）参数契约

> 来源：`wild-core/src/primitive/geometry/furniture.ts` 各 `build*` 函数的真实几何，**不是按函数名推断**。
> 用途：定义 `furniture` 元素的字段、坐标语义与十个子类型的尺寸含义。

`furniture` 是 `geometry.elements` 的**原生元素类型**，不是 `geometry.components` 组合构件：
它**没有宿主**（不写 `parentWall` / `parentFloor`），也不产生 `opening`。
它同时服务两条链——建筑里当室内陈设，也可以单独成为整个场景的唯一交付物（"生成一个桌子"）。

## 一、三个字段的语义（写错就悬空或占地错位）

| 字段 | 语义 | 易错点 |
|---|---|---|
| `position` | **底面锚点**，不是几何中心。局部原点是底面中心：X/Z 以占地中心为 0，Y 以底面为 0 | 落地摆放时 `position[1]` 给行走面标高；写成"几何中心高度"会让家具一半埋进地板 |
| `rotation` | 绕**底面中心**的欧拉角（弧度，`[rx, ry, rz]`，XYZ 序），缺省 `[0,0,0]` | 只改朝向时用 `rotation[1]`；因为绕底面中心转，转完家具不会离开落点 |
| `dimensions` | `{ width, depth, height }`，三项都必须 > 0 | `height` 的含义**逐子类型不同**（见第二节）；`width`/`depth` 是占地外廓 |

`material` 必须引用骨架 `materials` 里已存在的材质名。

### 朝向约定：所有子类型的正面统一朝 +Z

这不是约定俗成，是从几何硬编码读出来的：躯干/靠背/床头类零件的 z 偏移都是**负**的，
门板/抽屉面类零件都是**正**的 —— 两类合起来是同一个事实：**正面 = +Z**。

| 子类型 | 判定依据（源码中的 z 偏移） | 正面 |
|---|---|---|
| `chair` | 靠背在 `z = -d/2 + thickness/2` | +Z |
| `sofa` | 靠背在 `z = -d/2 + backDepth/2` | +Z |
| `bed` | 床头板在 `z = -d/2` | +Z |
| `bookshelf` | 背板在 `z = -d/2 + board/2` | +Z |
| `wardrobe` | 两扇柜门在 `z = +d/2 + doorDepth/2` | +Z |
| `nightstand` | 抽屉分缝在 `z = +bodyDepth/2` | +Z |
| `tv_cabinet` / `lamp` / `tile` | 左右对称或无朝向语义 | 无 |

⇒ 要让一把椅子面向 −Z，写 `rotation: [0, 3.1416, 0]`。**不要靠改 `position` 去凑朝向。**

## 二、十个子类型与 `dimensions` 含义（均为引擎原生，无需降级）

| subtype | `height` 是什么 | 常用取值 | 几何构成 |
|---|---|---|---|
| `table` | 台面**顶**高 | 0.72~0.78 | 台面 + 4 条桌腿 |
| `chair` | **含靠背**的总高 | 餐椅 0.85~0.95 | 座面（0.45×height）+ 4 条腿 + 靠背 |
| `sofa` | **含靠背**的总高 | 0.75~0.90 | 底座 + 靠背 + 双扶手 + 3 块坐垫 |
| `bed` | 床头板高 | 0.90~1.10 | 床架 + 床垫 + 床头板 |
| `wardrobe` | 柜体总高 | 2.00~2.40 | 踢脚 + 柜体 + 两扇柜门 |
| `bookshelf` | 总高 | 1.80~2.20 | 双侧板 + 顶底板 + 背板 + 2 块层板 |
| `nightstand` | 台面顶高 | 0.50~0.60 | 台面 + 柜体 + 抽屉分缝 + 4 条腿 |
| `tv_cabinet` | 台面顶高 | 0.45~0.60 | 台面 + 踢脚 + 左右柜体 + 中置设备格 |
| `lamp` | 总高 | 0.40~0.75 | 底座 + 灯杆 + 锥形灯罩（`width`/`depth` 是灯罩直径） |
| `tile` | 板厚 | 0.02 量级 | 单块薄板 |

**零件数量硬编码、不随尺寸变**，写方案时不要承诺能改：sofa 坐垫恒 3 块
（每块宽 = 内宽/3×0.94）、bookshelf 层板恒 2 块（0.33 / 0.66 高度处）、
chair 座面恒在 0.45×height。其余零件由固定比例推出，改 `dimensions` 整体联动。

## 三、落地与不悬空

家具没有宿主，"有没有摆稳"只能靠高度比对：

- 有楼板时，`position[1]` 对齐楼板**顶面**（`floor.from[1] + thickness`）；
- **没有楼板的独立物件场景**，以地面 `Y = 0` 为行走面；
- 校验口径（`app/tools/spatial_tools.py`）：底部与最近行走面相差 > 0.31m 判"可能悬空"，
  低于超过 0.1m 判"穿入地板"。两者都是 ⚠️ 警告级，不阻断交付。

## 四、能力边界

- ✅ 十个原生子类型，直接写 `subtype` 即可，不需要 primitive 降级。
- ✅ `rotation` 任意朝向（绕底面中心），可以围桌、靠墙、面向视线。
- ✅ 精细造型仍可用 `primitive` 盒体组合：L 型沙发、贵妃位、逐块坐垫单独控制尺寸与材质。
- ❌ 圆角、软包、绗缝、织物褶皱：引擎只有盒体/圆柱/球体几何；抱枕可用小 `primitive` 盒近似。
- ❌ 抽屉/柜门可开：家具是静态几何，没有 `interaction`；要开合行为得用 `door` 组件。
- ❌ `subtype: "lamp"` **不发光**：它只是静态灯形家具；需要真实光照与开关行为请用 `light` 组件。
- ❌ 不与墙做布尔穿透：贴墙摆放靠 `position` 控制，超出会按"与墙穿插"给警告。

## 五、相关文档的分工（避免读成互相竞争的两份权威）

- 本文档是**总契约**：字段语义、坐标与朝向约定、十个子类型的 `height` 含义、落地口径。
- 《沙发表达》（`components/sofa.md`）是**沙发专用**的展开：原生 subtype 与 primitive 组合两种写法、
  固定四件与坐垫分块的拼装细节。两者在重叠处（坐垫恒 3 块、靠背朝 −Z、`position` 为底面锚点）
  结论一致；若将来出现分歧，以本文档的字段语义为准，并同步修那一份。
