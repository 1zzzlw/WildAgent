---
doc_type: component
doc_scope: generation
knowledge_layer: wild_schema
entity_type: window
entity_name: static_window_component
topic: schema
wild_version: "1.1"
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
keywords:
  - 基础静态窗
  - window component
  - geometry.components
  - parentWall
  - verticalMullions
  - glassMaterial
---

# 基础静态窗组合构件

## 当前支持的基础静态窗

基础窗必须写入 `geometry.components`。它可依附直线墙或单段曲线墙，编译为矩形 `opening`、四边窗框和可选横竖窗棂；可选 `interaction` 为窗面增加右键平开或推拉动画。

### 参数契约

| 字段 | 要求 |
|---|---|
| `type` | 固定为 `window` |
| `id` | 非空且与全部元素、组件 ID 唯一 |
| `parentWall` | 已存在的直线或单段曲线 `wall` ID |
| `from` | `[沿墙弧长距离, 窗台世界Y, 法向偏移]` |
| `width`, `height` | 正数，且不能超出父墙 |
| `verticalMullions`, `horizontalMullions` | 可选，分别为 0–32 的整数 |
| `frameWidth`, `frameDepth` | 可选正数 |
| `frameMaterial`, `glassMaterial` | 可选，必须引用已有材质 |
| `interaction` | 可选；`mode` 为 `swing/slide`，可设方向、角度/距离和初始状态 |

### 有效 JSON 片段

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "window",
  "id": "living_window",
  "parentWall": "front_wall",
  "from": [3, 0.9, 0],
  "width": 1.8,
  "height": 1.2,
  "verticalMullions": 1,
  "horizontalMullions": 1,
  "frameMaterial": "metal",
  "glassMaterial": "glass"
}
```

### 当前边界

左键选择高亮，右键才执行开合。`sashType`、多窗扇独立状态、复杂 `muntinPattern`、碰撞和独立 `mullion` 类型仍未实现。
