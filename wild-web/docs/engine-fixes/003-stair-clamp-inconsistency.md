# 003 — 楼梯踏步尺寸 clamp 破坏一致性导致踏步重叠/缝隙

| 字段 | 内容 |
|---|---|
| **日期** | 2026-07-21 |
| **模块** | `src/wild-core/src/primitive/resolver.ts` → `resolveStairSteps` |
| **严重度** | 🟡 中 |
| **触发条件** | 楼梯的 `totalRise` 或 `totalDepth` 使得单步值超出 clamp 范围时触发 |

---

## 现象

楼梯渲染后出现**踏步之间重叠**（z-fighting 闪烁）或**踏步之间出现缝隙**，表现为"乱码"状的视觉异常。

## 根因

`resolveStairSteps` 在最后对 `stepHeight` 和 `stepDepth` 做了独立的 clamp：

```typescript
// 修复前
stepHeight = Math.max(minStepHeight, Math.min(maxStepHeight, stepHeight));
stepDepth = Math.max(minStepDepth, Math.min(maxStepDepth, stepDepth));
```

但 `stairBuilder` 中踏步的**位置**和踏步 box 的**尺寸**使用不同的数据源：
- **位置间距** = `(to - from) / count`（始终均匀分布，不受 clamp 影响）
- **box 尺寸** = `stepDepth × stepHeight`（来自 resolver，被 clamp 改变）

clamp 破坏了恒等式 `stepHeight * count == totalRise` 和 `stepDepth * count == totalDepth`，导致：

| 场景 | 后果 |
|---|---|
| stepDepth 被 clamp 到 minStepDepth（0.26），但实际间距仅 0.22 | 踏步 box 比间距宽，相邻踏步**重叠** |
| stepHeight 被 clamp 到 maxStepHeight（0.20），但实际间距为 0.22 | 踏步 box 比间距矮，相邻踏步**有缝隙** |

### 具体案例

楼梯 totalRise=0.5, totalDepth=1.05（cabin_v1.wild 入口台阶）：
- bestCount = round(0.5/0.18) = 3
- stepHeight = 0.5/3 = 0.167, stepDepth = 1.05/3 = 0.35
- clamp: stepHeight 在 [0.15, 0.20] 内 ✓，stepDepth = clamp(0.35, 0.26, 0.35) = **0.35** ✓
- 实际水平间距 = 1.05/3 = **0.35** = stepDepth ✓（恰好一致）

但 totalDepth=1.5, totalRise=3.0：
- bestCount = round(3.0/0.18) = 17
- stepHeight = 3.0/17 = 0.176, stepDepth = 1.5/17 = 0.088
- clamp: stepDepth = max(0.088, 0.26) = **0.26**（被强制拉大！）
- 实际水平间距 = 1.5/17 = **0.088** ≠ 0.26 → 踏步 box 深 0.26 但间距只有 0.088 → **严重重叠**

## 影响范围

所有楼梯（含现有蓝图）在特定尺寸组合下均会受影响。cabin_v1.wild 的入口楼梯尺寸恰好避开了 clamp 边界，因此未表现出问题。

## 修复方案

**移除独立 clamp**，改为从步高和步深两个维度分别估算步数后取平均，保证 `stepHeight = totalRise / count` 和 `stepDepth = totalDepth / count` 始终成立：

```typescript
// 修复后
const countByRise = Math.max(1, Math.round(totalRise / targetStepHeight));
const countByDepth = Math.max(1, Math.round(totalDepth / targetStepDepth));
let bestCount = Math.round((countByRise + countByDepth) / 2);

// 恒等式保证：踏步 box 尺寸 == 踏步间距，永不重叠/有缝
stair.stepHeight = totalRise / bestCount;
stair.stepDepth = totalDepth / bestCount;
```

**设计考量**：
- 不再 clamp 单值 → `stepHeight * count == totalRise` 始终成立
- 从步高和步深两个维度估算步数后取平均 → 平衡舒适度和空间利用
- 小楼梯（单步 < 0.25m）直接设 count=1 → 避免除零

## 验证

楼梯 totalRise=3.0, totalDepth=1.5：
- 修复前：count=17, stepHeight=0.176, stepDepth=**0.26**(clamp) vs 实际间距 0.088 → 重叠
- 修复后：countByRise=17, countByDepth=5, bestCount=11, stepHeight=0.273, stepDepth=**0.136** = 实际间距 → 无重叠 ✅
