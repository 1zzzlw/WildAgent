# 农业建筑：温室、养殖场、粮仓、农机站

> 来源：`docs/建筑类型分类体系_构件清单版1.2.md`。
> 用途：整理设施温室、畜禽饲养场、粮仓、农机站等农业建筑构件配方。
> RAG 关键词：农业建筑、温室、设施温室、养殖场、粮仓、农机站、轻钢、采光顶、通风

---
## 四、农业建筑

---

### 4.1 设施温室

> 图示：温室结构示意图（原始资源：`docs/建筑类型分类体系_images/05_温室.png`）

**构件清单**

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 主立柱 | `column` | crossSection=square, side=0.12m(热镀锌矩形管120×120×3mm), height=3~6m, 间距4m, style=modern |
| 拱形桁架 | `truss` | trussType=warren(轻型), span=8~12m, height=1.5~2.5m, memberProfile=rect 0.04×0.06m |
| 透明覆盖墙 | `wall` | thickness=0.004~0.016m(玻璃/PC板/薄膜), material=glass, opacity=0.3 |
| 采光屋顶 | `roof` | roofType=flat(连栋) / gable(单栋), material=glass |
| 外遮阳骨架 | `beam` | 上部网格, 高于屋面 |
| 天沟排水 | `beam` | U形截面, 2.5‰坡度 |
| 湿帘开口 | `opening` | 侧墙, style=rectangular, 强制降温 |
| 风机开口 | `opening` | 对侧山墙, 负压通风 |
| 内保温幕 | `roof`(内层) | 轻质, 冬季保温 |
| 苗床 | `furniture` | subtype=table, 可移动 |

**温室 WILD JSON 示例**

```json
{
  "type": "column", "id": "gh_post_01",
  "base": [0, 0, 0], "height": 4.0,
  "crossSection": "square",
  "bottomSide": 0.12, "topSide": 0.12,
  "style": "modern",
  "material": "galvanized_steel"
}
```

**典型案例**：内蒙古赤峰松山区智慧农业园、荷兰 Venlo 型温室群

---

### 4.2 畜禽饲养场

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 外围护墙 | `wall` | 保温夹芯板, thickness=0.08m, 隔温防腐蚀 |
| 轻钢门式刚架 | `column`+`beam` | column: square 0.15m; beam: rect 0.2×0.4m(弧形) |
| 屋面 | `roof` | roofType=gable, 彩钢板+保温棉, 通风屋脊 |
| 漏缝地板 | `floor` | 带缝隙, 粪尿自动分离, surfaces=custom |
| 通风风机 | `opening` | 山墙, 负压通风 |
| 湿帘 | `opening` | 对侧山墙 |
| 栏位隔断 | `wall` | 低矮0.8~1.2m, 金属管, thickness=0.05m |
| 喂料线 | `furniture` | (设备构件) |

**典型案例**：牧原股份楼房养猪（≤4F）、浙江婺城湖羊智慧养殖基地（双层）

---

### 4.3 粮仓

| 类型 | 构件 | WILD type | 精确参数 |
|:---:|:---|:---:|:---|
| 筒仓 | 仓壁 | `wall` | curve=arc, sweep=360°, height=10~30m, 直径6~15m |
| | 仓顶 | `roof` | roofType=dome/flat, 密封防水 |
| | 输送栈桥 | `beam`+`floor` | 高架通道 |
| 平房仓 | 墙体 | `wall` | thickness=0.30m+, 保温, 跨度18~30m |
| | 屋盖 | `truss`+`roof` | trussType=pratt, roofType=gable |
| 烘干塔 | 塔身 | `column`+`wall` | 围合竖塔, height=15~25m |

**典型案例**：四川德阳旌耘粮仓（2022 NDA 金奖）

---

### 4.4 农机站

| 构件 | WILD type | 精确参数 |
|:---:|:---:|:---|
| 大开间钢架 | `column`+`truss` | column: square 0.2m; truss: warren, span=12~18m |
| 大型推拉门 | `opening`+`door` | w=4~6m, h=4m, door:flush, leafCount=4 |
| 混凝土地坪 | `floor` | thickness=0.20m, 耐磨 |
| 维修地沟 | `floor`(下沉) | 车底检修 |

---
