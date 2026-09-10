---
entity_type: assembly
entity_name: component_selection_conditions
topic: constraints
status: supported
authority: maintainer
source: recipes/component-selection-relations.md
primary_terms:
  - 构件选择
  - 条件系统
synonyms: []
---

# 按功能选择构件

## 构件选择的触发条件

先从用户要求和已批准方案确定功能，再选择构件；建筑名称不触发一套固定构件清单。

| 已选择的功能 | WILD 表达 | 必须保持的关系 |
|---|---|---|
| 墙体开口 | door/window/opening | 真实 parentWall；沿墙局部坐标及垂直范围有效 |
| 小型墙挂阳台 | balcony | 自带板和 U 形栏杆，同位置不重复生成 floor/railing |
| 大露台或外廊 | floor 与 railing | 楼板覆盖实际轮廓；栏杆仅沿所选临空边 |
| 入口遮蔽 | canopy 或独立柱梁屋盖 | canopy 需要墙宿主；独立雨棚显式表达支撑 |
| 跨层交通 | stair | 起终点连接本次楼层；多跑用多段与平台 |
| 高差通行 | ramp | 起终标高与路径匹配，不由类型名自动添加 |
| 屋面附属 | cornice/chimney | 按实际屋面定位；烟囱不自动穿孔 |

## 数量与尺度的决定方式

数量来自功能单元、立面轴网、层数和本次预算；尺寸来自宿主有效范围、任务尺寸与已选比例。不按“现代/中式/公共建筑”固定门窗、阳台、灯具数量。没有选择的附属功能不为了凑细节而生成。
