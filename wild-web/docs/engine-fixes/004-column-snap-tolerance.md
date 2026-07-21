# 004 — resolveColumnOffsets 容差过大导致门廊柱/装饰柱被吸入墙内

| 字段 | 内容 |
|---|---|
| **日期** | 2026-07-21 |
| **模块** | `src/wild-core/src/primitive/resolver.ts` → `resolveColumnOffsets` |
| **严重度** | 🔴 高 |
| **触发条件** | 蓝图中有意放置在墙体外侧附近的柱子（门廊柱、装饰柱、壁柱等） |

---

## 现象

门廊柱（portico columns）、外墙装饰柱等**被自动吸附到墙体中心线上**，失去原有的空间位置，表现为柱子"脱离"了预期位置、嵌入墙体内部。

具体案例 — `haoHuaBieshu.wild` 门廊柱：
```json
// 设计意图：柱子在墙外侧 0.35m 处
{"base": [-1.2, 0.0, -6.35], ...}  // 墙在 z=-6，柱子在 z=-6.35

// 实际渲染：柱子被 "修复" 到墙体中心线
// col.base 变为 [-1.2, 0.0, -6.0] — 柱子被吸入墙内！
```

## 根因

`resolveColumnOffsets` 的容差计算使用了 `wallHalfThick + colR`：

```typescript
// 修复前
const tolerance = wall.thickness / 2 + col.bottomRadius;
if (Math.abs(perpDist) > tolerance) continue;
// 柱子距墙中心线 ≤ 半墙厚 + 柱半径 → 判定为"在墙内"→ 吸附
```

对于 `haoHuaBieshu.wild` 的门廊柱：
- wallHalfThick = 0.35 / 2 = 0.175
- colR = 0.22
- tolerance = 0.175 + 0.22 = **0.395**
- perpDist = |−6.35 − (−6.0)| = **0.35**
- 0.35 < 0.395 → **判定为"在墙内"，吸附！**

问题本质：`+ colR` 使得容差范围扩展到墙外一个柱子半径的距离。对于粗柱子+薄墙的组合（如 φ44cm 柱子 + 35cm 墙体），柱子即使在墙外 0.22m 仍会被吸入。

设计意图：`resolveColumnOffsets` 应该只处理**嵌入墙体内的柱子**（如墙角结构柱），帮助对齐到墙中心线。不应该影响有意放置在墙外的装饰柱。

## 影响范围

| 蓝图 | 柱子 | 受影响？ |
|---|---|---|
| `haoHuaBieshu.wild` | 门廊柱 (x2) | ❌ 被吸入墙内 |
| `cabin_v1.wild` | 角柱 (x4) | ✅ 不受影响（perpDist ≈ 0，本来就在墙线上） |
| `bieshu.wild` | 无柱子 | — |
| `tiantan.wild` | 内外圈柱 (x16) | ✅ 不受影响（弧形墙 + 柱子距墙较远） |

## 修复方案

将容差从 `wallHalfThick + colR` 改为 `wallHalfThick + 0.02`（仅墙体厚度 + 微小 epsilon）：

```typescript
// 修复后
// 仅当柱子中心在墙体厚度范围内（嵌入墙内）时才对齐到中心线
if (Math.abs(perpDist) > wallHalfThick + 0.02) continue;
```

**设计考量**：
- `0.02`（2cm）epsilon 用于处理浮点精度和"柱子恰好放在墙边"的边界情况
- 不再使用 `colR` 作为容差因子 → 柱子半径不影响吸附判定
- 有意 offset 的柱子（perpDist > wallHalfThick + 0.02）保持原位

## 验证

`haoHuaBieshu.wild` 门廊柱：
- wallHalfThick = 0.175, tolerance = 0.175 + 0.02 = **0.195**
- perpDist = **0.35**
- 0.35 > 0.195 → **跳过吸附** ✅ 柱子保持在 z=-6.35 原位

`cabin_v1.wild` 角柱（perDist ≈ 0）：
- perpDist = **0**
- 0 < 0.195 → **吸附** ✅ 柱子正确对齐到墙中心线
