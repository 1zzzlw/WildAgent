---
doc_type: recipe
knowledge_role: relation
doc_scope: generation
knowledge_layer: constraint
entity_type: relation
entity_name: door_window_depth_convention
topic: depth
wild_version: "1.1"
status: supported
authority: engine
primary_terms:
  - 门窗深度
  - frameDepth
  - leafDepth
  - glassDepth
  - parentWall
  - 实体交叠
synonyms: []
---

# 门窗组合构件的深度约定

`geometry.components` 中的 `door` 与 `window` 依附 `parentWall`。二者的 `from` 均为 `[沿墙距离, 底部世界 Y, 墙体法向偏移]`，深度沿父墙法向计算。

| 构件 | 框深度 | 面板深度 | 约束 |
|---|---|---|---|
| `door` | `frameDepth`，默认父墙 `thickness` | `leafDepth`，默认 `min(0.04, frameDepth)` | `leafDepth > 0` 且不大于 `frameDepth` |
| `window` | `frameDepth`，默认父墙 `thickness` | `glassDepth`，默认 `min(0.012, frameDepth)` | `glassDepth > 0` 且不大于 `frameDepth` |

门框、窗框、门扇和玻璃都必须与父墙厚度范围存在实体交叠。省略这些可选字段即可使用安全默认值；显式设置主要用于特殊构造。
