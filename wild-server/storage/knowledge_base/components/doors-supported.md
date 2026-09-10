---
entity_type: door
entity_name: static_door_component
topic: schema
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
primary_terms:
  - 门组件
  - door
  - geometry.components
  - parentWall
  - openingStyle
  - doorStyle
synonyms: []
---

# 门组合构件（当前引擎支持）

`type: "door"` 写入 `geometry.components`。编译器把单扇门展开为一个带门扇细节的 `opening` 和三段门框；`doorStyle: "double"` 使用一个完整门洞及双扇细节，不需要并排创建两个门组件。

## 参数契约

| 字段 | 要求 | 当前语义 |
|---|---|---|
| `type` | 必填 | 固定为 `door` |
| `id` | 必填 | 非空，并与全部元素和组件 ID 唯一 |
| `parentWall` | 必填 | 引用原生 `wall.id` |
| `from` | 必填 | `[沿墙距离, 底部世界Y, 法向偏移]` |
| `width`, `height` | 必填 | 正数，并完整落入父墙范围；具体尺寸由批准设计决定 |
| `frameWidth` | 可选 | 非负，默认 `0.08` |
| `frameDepth` | 可选 | 正数，默认父墙厚度 |
| `leafDepth` | 可选 | 正数且不大于框深，默认 `min(0.04, frameDepth)` |
| `frameMaterial`, `leafMaterial` | 可选 | 引用已存在的材质 ID |
| `openingStyle` | 可选 | `rectangular` 或 `arched`，默认 `rectangular` |
| `doorStyle` | 可选 | `single` 或 `double`，默认 `single` |
| `interaction` | 可选 | 平开或推拉交互；省略时仍生成静态门 |

门框和门扇以 `from[2]` 为中心沿父墙法向放置。常规墙洞使用 `from[2] = 0`；只有批准设计明确需要偏置时才改变。

## 交互字段

`interaction.mode` 为 `swing` 或 `slide`。平开可使用 `hingeSide` 与 `openAngle`，推拉可使用 `openDistance`；`initiallyOpen` 控制初始状态。`openAngle` 必须大于 0 且不超过 180，`openDistance` 必须为正数。

```json
{
  "type": "door",
  "id": "door_entry",
  "parentWall": "wall_front",
  "from": [2.0, 0.0, 0.0],
  "width": 1.8,
  "height": 2.4,
  "doorStyle": "double",
  "openingStyle": "rectangular",
  "frameMaterial": "entry_frame",
  "leafMaterial": "entry_leaf"
}
```

该片段只解释字段关系。沿墙位置、宽高和材质均须来自本次设计及父墙有效范围。

## 组合关系与能力边界

- 门上亮子使用独立 `window`，两者引用同一父墙并保持竖向范围不重叠。
- 门侧亮同样使用独立 `window`；不能把窗挂在门生成的临时 `opening` 上。
- 拱形门洞由 `openingStyle: "arched"` 直接表达。
- 自动感应、卷帘、防火、气密等专业性能没有对应字段；只能表达外观与已有开合交互，不能声称实现这些性能。
- 旋转门、折叠门和复杂雕花没有原生门型；只有用户接受几何近似时才使用显式 `primitive`。

## 禁止字段

- 不使用 `style`、`leafCount` 或 `parentOpening`。
- `hingeSide`、`openAngle` 和 `openDistance` 只能放在 `interaction` 中。
- 不把 `door` 写入 `geometry.elements`，也不创建不存在的 `mullion` 类型。
