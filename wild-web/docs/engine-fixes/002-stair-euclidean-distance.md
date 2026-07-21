# 002 — 楼梯水平距离使用 Manhattan 距离导致对角线楼梯步深计算错误

| 字段 | 内容 |
|---|---|
| **日期** | 2026-07-21 |
| **模块** | `src/wild-core/src/primitive/resolver.ts` → `resolveStairSteps` |
| **严重度** | 🟡 中 |
| **触发条件** | 楼梯的 X 和 Z 方向同时有位移（对角线楼梯）且未显式指定 `stepCount`/`stepDepth` |

---

## 现象

当楼梯在 XZ 平面呈对角线走向（`from` 和 `to` 的 X、Z 均不同），自动计算的 `stepDepth`（每级踏步深度）会偏大：

| 楼梯走向 | dx | dz | Manhattan 距离 | 实际水平距离 | 误差 |
|---|---|---|---|---|---|
| 纯纵向 | 0 | 4.0 | 4.0m | 4.0m | 0% |
| 45° 对角线 | 3.0 | 3.0 | 6.0m | 4.24m | **+41%** |
| 30° 斜向 | 2.0 | 3.46 | 5.46m | 4.0m | **+36%** |

## 根因

`resolveStairSteps` 中水平距离的计算使用了 Manhattan 距离（各轴差绝对值之和）而非欧几里得距离：

```typescript
// 修复前
const totalDepth = Math.abs(stair.to[0] - stair.from[0])
                 + Math.abs(stair.to[2] - stair.from[2]);
```

这是错误的——楼梯沿 XZ 平面的实际走向是一个斜线段，其长度应该是两个端点之间的直线距离，即 `sqrt(dx² + dz²)`。

步深计算公式 `stepDepth = totalDepth / bestCount`，当 `totalDepth` 被高估 41%，步深也被高估 41%，导致踏步过深、步数过少。

## 影响范围

| 蓝图 | 楼梯走向 | 受影响？ |
|---|---|---|
| `bieshu.wild` | `from=[2,0,1] to=[2,3,4]` dx=0, dz=3 | ✅ 不受影响（纯纵向） |
| `haoHuaBieshu.wild` | `from=[2.5,0,0.2] to=[2.5,3.2,3.8]` dx=0, dz=3.6 | ✅ 不受影响（纯纵向） |
| `cabin_v1.wild` | `from=[2.4,0,-1.2] to=[2.4,0.5,-0.15]` dx=0, dz=1.05 | ✅ 不受影响（纯纵向） |

所有现有蓝图均未触发此 Bug，但**对角线楼梯是常见的建筑设计需求**（如旋转楼梯、斜向直梯），应提前修复。

## 修复方案

改为欧几里得距离：

```typescript
// 修复后
const totalDepth = Math.sqrt(
  Math.pow(stair.to[0] - stair.from[0], 2) +
  Math.pow(stair.to[2] - stair.from[2], 2)
);
```

**注意**：楼梯的 `from`/`to` 定义是 `[x, y, z]`，其中 y 是高程，不影响水平距离。

## 验证

对角线楼梯（dx=3, dz=3, rise=3）：
- 修复前：totalDepth=6, 最佳步数=17, stepDepth=0.35（偏大）
- 修复后：totalDepth=4.24, 最佳步数=17, stepDepth=0.25 ✅（合理范围）
