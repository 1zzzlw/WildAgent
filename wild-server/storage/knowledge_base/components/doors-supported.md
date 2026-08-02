---
doc_type: component
doc_scope: generation
knowledge_layer: wild_schema
entity_type: door
entity_name: static_door_component
topic: schema
wild_version: "1.1"
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
keywords:
  - 基础静态门
  - door component
  - geometry.components
  - parentWall
  - frameWidth
  - leafMaterial
---

# 基础静态门组合构件

## 当前支持的基础静态门

基础门必须写入 `geometry.components`。它可依附直线墙或单段曲线墙，编译为矩形 `opening` 和三段门框。可选 `interaction` 为覆盖面增加右键平开或推拉动画；当前不包含碰撞和独立厚门扇。

### 参数契约

| 字段 | 要求 |
|---|---|
| `type` | 固定为 `door` |
| `id` | 非空且与全部元素、组件 ID 唯一 |
| `parentWall` | 已存在的直线或单段曲线 `wall` ID |
| `from` | `[沿墙弧长距离, 底部世界Y, 法向偏移]` |
| `width`, `height` | 正数，且不能超出父墙 |
| `frameWidth`, `frameDepth` | 可选正数 |
| `frameMaterial`, `leafMaterial` | 可选，必须引用已有材质 |
| `interaction` | 可选；`mode` 为 `swing/slide`，可设方向、角度/距离和初始状态 |

### 有效 JSON 片段

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "door",
  "id": "entry_door",
  "parentWall": "front_wall",
  "from": [1.2, 0, 0],
  "width": 1,
  "height": 2.2,
  "frameWidth": 0.08,
  "frameMaterial": "wood",
  "leafMaterial": "wood",
  "interaction": {
    "mode": "swing",
    "hingeSide": "left",
    "openAngle": 90,
    "initiallyOpen": false
  }
}
```

### 当前边界

左键选择高亮，右键才执行开合。`leafCount`、多门扇独立行为、碰撞、声音和独立厚门扇仍未实现；`hingeSide` 只能放在 `interaction` 内。
