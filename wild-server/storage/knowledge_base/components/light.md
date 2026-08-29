---
knowledge_layer: architecture
entity_type: light
entity_name: light_component
topic: parameters
status: supported
authority: engine
source: components/light.md
primary_terms:
  - 灯具
  - light
  - 台灯
  - 壁灯
  - 灯泡
  - 照明
  - 发光
  - 可开关灯具
synonyms:
  - lamp
  - 光源
---

# 灯具（light）组件参数契约

> 来源：引擎 light 组件实现与 `BLUEPRINT-SPEC-MINIMAL.md` 的 light 定义核对。
> 用途：定义可发光、可开关灯具 `light` 组件的参数与约束。用户要求台灯、亮灯、发光或可开关灯具时使用本组件；旧版 `furniture.subtype: "lamp"` 只是静态家具占位，不产生真实光照。

## 基本定义

`light` 是 `geometry.components` 中的组合组件：

```json
{
  "type": "light",
  "id": "desk_lamp",
  "fixtureType": "table_lamp",
  "position": [1.5, 0.75, 1.0],
  "lightType": "point",
  "color": [1.0, 0.78, 0.52],
  "lowIntensity": 18,
  "highIntensity": 65,
  "distance": 8,
  "initiallyOn": false
}
```

## 必填与可选字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | ✓ | `"light"` |
| `id` | ✓ | 稳定唯一 ID |
| `position` | ✓ | 世界坐标 `[x, y, z]`；`table_lamp` 是底座支承面锚点，`bulb` 是灯泡中心 |
| `fixtureType` | ✗ | 外观业务类型：`bulb` 或 `table_lamp` |
| `lightType` | ✗ | 发光算法：`point` 或 `spot` |
| `color` | ✗ | RGB，3 个 0~1 数值 |
| `lowIntensity` / `highIntensity` | ✗ | 弱光/强光强度 |
| `distance` | ✗ | 光照距离 |
| `angle` | ✗ | 光束角（`spot` 时） |
| `initiallyOn` | ✗ | 初始状态：默认 `true`（亮灯）；`false` 表示默认关灯。省略按亮灯处理 |

## 约束

- **`fixtureType` 与 `lightType` 不混用**：`fixtureType` 是外观（bulb/table_lamp），`lightType` 是发光算法（point/spot），二者独立。
- **`table_lamp` 编译产物**：灯泡、底座、灯杆和灯罩；`bulb` 只编译灯泡与灯座。
- **交互**：右键在关灯、弱光和强光之间循环；运行时亮度级别不写回 Blueprint，`initiallyOn` 只保存初始状态。
- **`draggable: true`** 允许用户手动拖动并把位置写回当前草稿，不表示已实现自动贴桌面或空间碰撞校验。
- **壁灯挂墙**：壁灯（`fixtureType: bulb`）的 `position` 应落在墙上安装高度（如离地 1.8m 左右），不要悬浮在半空。

## 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| 台灯悬浮半空 | `position[1]` 过高且 `fixtureType: table_lamp` | 把底座 Y 落到支承面（桌面/地面） |
| 无光照的静态灯 | 用了 `furniture.subtype: "lamp"` | 改用 `light` 组件 |
| `initiallyOn` 缺失被误判 | 省略即亮灯 | 需要默认关灯时显式写 `false` |
| `position` 高度为负 | 灯具埋入地下 | 修正 `position[1]` ≥ 0 |
