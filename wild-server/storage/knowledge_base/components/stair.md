---
knowledge_layer: architecture
entity_type: stair
entity_name: stair_component
topic: parameters
status: supported
authority: engine
source: components/stair.md
primary_terms:
  - 楼梯
  - stair
  - 直跑楼梯
  - 折跑楼梯
  - 台阶
  - 多层竖向交通
synonyms:
  - staircase
  - stairs
---

# 楼梯（stair）参数契约

> 来源：引擎 resolver 与 `BLUEPRINT-SPEC-MINIMAL.md` 的 stair 定义核对。
> 用途：定义楼梯 `stair` 元素的参数、约束与常见布局，供生成多层建筑时正确配楼梯。

## 基本定义

`stair` 是 `geometry.elements` 中的结构元素，连接两个不同标高的楼板：

```json
{
  "type": "stair", "id": "main_stair",
  "from": [2, 0, 1], "to": [2, 3, 4],
  "width": 1.2,
  "material": "concrete"
}
```

## 必填字段与语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `"stair"` | 固定 |
| `id` | string | 稳定唯一 ID |
| `from` | [number, number, number] | 楼梯下端世界坐标：`from[1]` 是下层地板 Y |
| `to` | [number, number, number] | 楼梯上端世界坐标：`to[1]` 是上层地板 Y |
| `width` | number | 楼梯宽度（米） |
| `material` | string | 材质引用（可选） |

## 硬约束（引擎强制）

- **`from[1] < to[1]`**：楼梯必须连接两个递增标高；`to[1] <= from[1]` 是无效楼梯（`invalid_stair_levels`）。
- **`from` / `to` 的 XZ 平面投影**：直跑楼梯的两端在水平面上应基本对齐；若 XZ 差异过大（折跑/旋转），引擎当前只支持直跑，需要用**多段直跑 stair 拼接**表达折跑。
- **宽度范围**：建议 0.8m ~ 3.0m（住宅 0.9~1.2m，公建 1.5~1.8m）。
- **两端落地**：楼梯下端应落在下层楼板顶面、上端落在上层楼板顶面；`collect_stair_placement_issues` 会检查踏步是否与两侧楼板衔接，悬空或穿入楼板会被标记。

## 踏步推算（引擎 resolver）

引擎按 `from`→`to` 的高差和水平跨度自动推算踏步（`resolveStairSteps`）：

- **踏步高（rise）**：推荐 0.14~0.20m（住宅常用 ~0.16m，公建 ~0.15m）。过高过矮都会让引擎以警告方式提示。
- **踏步宽（run）**：由水平跨度与步数自动分配；水平跨度不足时优先保证踏步高合理。
- **一段直跑建议最多 12~14 步**，超过后应插入休息平台（用多段 stair 表达）。

## 多段折跑/带平台楼梯

引擎只支持**直跑 stair**；折跑（L/U 形）楼梯用多段直跑拼接：

1. 第一段：下层楼板 → 平台标高（`to[1]` = 平台顶 Y，水平投影到平台一端）。
2. 平台：用 `floor` 元素铺在平台标高（或由楼板单元表达）。
3. 第二段：平台 → 上层楼板（`from[1]` = 平台顶 Y，水平投影与第一段方向垂直）。

```json
[
  {"type": "stair", "id": "stair_l1", "from": [2, 0, 1], "to": [2, 1.6, 1], "width": 1.2},
  {"type": "floor", "id": "landing_1", "from": [2, 1.6, 1], "to": [4, 1.6, 1], "thickness": 0.15},
  {"type": "stair", "id": "stair_l2", "from": [4, 1.6, 1], "to": [4, 3.2, 3], "width": 1.2}
]
```

## 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| `from[1] == to[1]` | 没有高差 | 让 `to[1]` = 上一层楼板标高 |
| 楼梯悬空 | 下端 Y 低于下层楼板顶 | 下端 Y 对齐楼板顶面 |
| 一段过长 | 步数 > 14 无平台 | 插入平台并拆成多段 |
| 宽度过窄 | < 0.8m | 加宽到 0.9m 以上 |
| 旋转楼梯 | 引擎不支持 | 改用多段直跑 + 平台近似 |
