---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: column
entity_name: column_component
topic: parameters
status: supported
authority: engine
primary_terms:
  - 柱
  - column
  - 柱廊
  - 廊柱
  - 罗马柱
  - 柱网
  - 柱子
  - 石柱
  - peristyle
  - colonnade
synonyms:
  - 列柱
  - 门廊柱
  - 围廊柱
  - 景观柱
---

# 柱（column）组件参数契约

> 来源：引擎 column 原生元素实现 + `wild-core/schema.json` 的 column 定义核对。
> 用途：定义独立柱元素（门廊柱、围廊柱、景观柱、柱廊）的参数与约束。
> 用户要求柱廊 / 廊柱 / 罗马柱 / 柱子 / 石柱 / peristyle 时使用本组件。

## 基本定义

`column` 是 `geometry.elements` 中的**原生元素类型**（引擎直接渲染，含柱头柱身收分），
不是 `geometry.components`，**没有宿主构件**——不需要 `parentWall` / `parentFloor`。

```json
{
  "type": "column",
  "id": "column_front_01",
  "base": [2.0, 0.0, 0.4],
  "height": 3.6,
  "bottomRadius": 0.25,
  "topRadius": 0.2,
  "style": "ionic",
  "flutes": 24,
  "material": "stone"
}
```

## 必填与可选字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | ✓ | `"column"` |
| `id` | ✓ | 稳定唯一 ID（如 `column_front_01`） |
| `base` | ✓ | **柱底中心**世界坐标 `[x, y, z]`；`base[1]` 必须落在承托面上（地面 / 台基顶 / 楼板顶），不得悬空 |
| `height` | ✓ | 柱底到柱顶的高度（米），> 0 |
| `bottomRadius` | ✓ | 柱底半径（米），> 0 |
| `topRadius` | ✓ | 柱顶半径（米），> 0；古典柱收分通常 bottom 0.25 → top 0.2 |
| `style` | ✓ | 闭集五选一：`doric` / `ionic` / `corinthian` / `modern` / `chinese_wooden` |
| `flutes` | ✗ | 柱身凹槽数（整数 ≥ 0）；多立克式常见 20，爱奥尼/科林斯常见 24 |
| `entasis` | ✗ | 卷杀程度（柱身中段微凸，数值 ≥ 0） |
| `inclination` | ✗ | 柱身倾斜弧度（≥ 0；古典柱廊的微内倾） |
| `material` | ✗ | 材质名，必须引用骨架 `materials` 中已有的材质名 |

## 约束

- 关键：**`base[1]` 必须落在承托面上**：地面、台基顶或楼板顶。柱底悬空 = 校验报缺陷。
  需要垫高层时，用独立 `primitive`（台基/柱础）承托，不要让柱子飘在半空。
- 关键：**style 是闭集**：只允许 `doric / ionic / corinthian / modern / chinese_wooden` 五个值。
  自创 style 值会被 schema 拒绝。
- 关键：**柱头垫块（abacus）、柱础、柱间横梁等附件用独立 `primitive` 表达**：
  column 的字段装不下它们——不要发明 `abacus` / `capital` 之类 schema 里没有的字段。
- **柱身不得与墙体相交**：柱是独立承重/装饰元素，嵌进墙里既穿模又重复表达。
- **柱网沿承托面周边等距布置**：数量、位置服从 `component_quota` 与已批准设计；
  围廊（peristyle）沿台基/体量周边一圈等距，门廊柱只在入口开间。
- **直径与层高的比例**：古典柱总高（含柱头）约为柱径的 8~10 倍；多层柱廊逐层收分
  或换 style 时，每根柱仍是独立 column 元素，不要用一根超长柱贯穿多层。
- **材质必须引用骨架 materials 中已有的材质名**，不得凭空造材质。

## 编译产物与交互

- 编译后产出：column 元素本身（引擎原生渲染，含柱头柱身收分）。
- 柱本身没有开合/交互语义；柱廊围合的门廊入口由 `door` + `canopy` 表达。

## 典型用法

- **门廊柱**：入口开间两侧各一根，`style` 跟随建筑风格（欧式 → doric/ionic/corinthian，
  中式 → chinese_wooden，现代 → modern）。
- **围廊（peristyle）**：沿台基周边等距一圈，古典殿宇常配 `flutes` + `entasis`。
- **景观柱**：庭院/轴线端头的独立柱，可配基座 `primitive`。

## 能力边界

- 没有 `abacus`（柱头垫块）字段——垫块用独立 `primitive` 补。
- 没有柱间横梁/额枋字段——用 `beam` 元素或 `primitive` 表达。
- 不做墙体一体化柱（壁柱/扶壁）——那是墙体几何的事，用墙的凸出体量表达。
