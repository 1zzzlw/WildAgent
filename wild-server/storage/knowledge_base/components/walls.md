---
entity_type: wall
entity_name: wall_family
topic: parameters
status: supported
authority: maintainer
source: components/walls.md
primary_terms:
  - 墙体
  - wall
  - parentWall
synonyms: []
---

# 墙体参数与关系

## 墙体字段和坐标

wall 必填 id、from、to、thickness；material 与 curve 按规范选用。from/to 是世界坐标，from[1] 为墙底，to[1] 为墙顶；没有 wall.height 字段。墙长及墙高必须有效，厚度来自本次方案，不按建筑名称固定。直墙省略 curve，曲线墙使用受支持的路径定义。

## 宿主与边界

门窗、凸窗、雨棚和阳台通过 parentWall 引用原生 wall。墙挂组件 from 为沿墙距离、世界 Y、法向偏移；开口不得超出墙的有效水平和竖向范围。不同楼层分别匹配墙段，不能把上层窗挂到首层墙。转角、共享墙和分段围护避免重复或重叠。

## 功能角色与表示边界

承重、填充、隔断和幕墙是设计角色，wall 不会因厚度或材质自动获得相应工程性能。复合墙如需表现分层，要明确各层偏移与开口一致性，不叠放重复实体。没有 cavity 字段；幕墙使用真实宿主加 window 或显式框架和玻璃，不能仅把实墙改名为幕墙。
