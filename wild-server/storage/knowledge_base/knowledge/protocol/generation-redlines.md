---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: generation_redlines
topic: constraints
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 生成红线
  - always-on rules
  - 坐标红线
  - 材质格式铁律
  - 屋顶枚举
synonyms: []
---

# 生成红线（始终注入）

本文件**每轮完整注入提示词**，因此只放"模型不看到就一定会写错、且写错后无法靠常识补救"的条目。
其余字段细节走检索，不在这里重复。新增条目请保持一句话一条。

## 坐标与几何

- 两面墙在转角处相接时必须**共享完全相同的端点坐标**，不能使用近似值。
- 生成屋顶前先用 `get_wall_bounding_box` 取得墙体包围盒，不要猜测尺寸。
- 组合构件挂在墙上的水平定位是 **`from[0] = 沿墙距离`**（从 `parentWall.from` 沿墙方向量起，单位米）。
- `roof.span` / `roof.depth` 按其负责的**体量轮廓**取尺寸，出檐时两侧加余量；
  **不得**用整栋外包络当屋顶范围。多体量（L 形 / U 形 / 退台）各生成一块屋顶，或贴合墙体留出内院 / 天井。
- `roof.position` 位于墙体 XZ 中心与墙顶高度。

## 枚举陷阱

- `roof.roofType` 只有 **6 个合法值**：`gable` / `hip` / `dome` / `flat` / `chinese_curved` / `chinese_pagoda`。
- **严禁** `pitched`、`sloped`、`gabled`、`hipped`、`shed`、`mono-pitch` —— 它们是建筑学术语，不是 WILD 枚举值。
- 组合构件只能写入 `geometry.components`，不能写进 `geometry.elements`；严禁发明不存在的类型值。

## 材质

- baseColor 必须是 [R, G, B] 数组（各分量 0.0–1.0）；绝对禁止写成 `"#RRGGBB"` 字符串。
- 数值颜色（`baseColor`、`emissive`、效果层颜色、程序化顶点色）统一按 sRGB authored value 表达，
  由渲染器转换到线性工作空间。
- 墙、楼板、屋顶、门、玻璃按实际角色引用各自独立的材质名，不要全部指向同一个 `concrete`。
- 物理玻璃必须给出 `materialClass: "glass"`、`transmission > 0` 和 `ior`，`opacity` 必须为 `1` 或省略。
