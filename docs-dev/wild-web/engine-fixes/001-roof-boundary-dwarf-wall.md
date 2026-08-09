# 001 — 屋顶包围盒计算被矮墙干扰导致屋顶偏移

| 字段 | 内容 |
|---|---|
| **日期** | 2026-07-21 |
| **模块** | `src/wild-core/src/primitive/resolver.ts` → `resolveRoofBoundary` |
| **严重度** | 🔴 高 |
| **触发条件** | 蓝图中存在延伸出主体建筑包围盒的矮墙（阳台栏杆、装饰墙等）且屋顶未显式指定 `position` |

---

## 现象

`bieshu.wild`（荒原别墅）和 `haoHuaBieshu.wild`（豪华别墅）渲染后，**屋顶相对主体建筑明显偏移**（偏离 ~1.25m），且尺寸被撑大。而 `cabin_v1.wild`（小木屋）渲染正常。

## 根因

`resolveRoofBoundary` 在计算屋顶位置和尺寸时，**无差别取场景中所有 `type: "wall"` 的包围盒**：

```typescript
// 修复前
const walls = elements.filter(e => e.type === 'wall') as any[];
for (const wall of walls) {
  minX = Math.min(minX, wall.from[0], wall.to[0]);
  maxX = Math.max(maxX, wall.from[0], wall.to[0]);
  minZ = Math.min(minZ, wall.from[2], wall.to[2]);
  maxZ = Math.max(maxZ, wall.from[2], wall.to[2]);
  maxY = Math.max(maxY, wall.from[1], wall.to[1]);
}
roof.position = [(minX + maxX) / 2, maxY, (minZ + maxZ) / 2];
```

以 `bieshu.wild` 为例：

| 墙组 | X 范围 | Z 范围 | 高度 |
|---|---|---|---|
| 主体结构墙（GF+1F） | [-8, 8] | [-6, 8] | 3.0m / 2.8m |
| 阳台栏杆（矮墙） | [-3, 3] | [8, **10.5**] | 0.8m |

- 主体建筑中心 Z = (−6 + 8) / 2 = **1.0**
- 全量包围盒中心 Z = (−6 + 10.5) / 2 = **2.25** → 偏移 **+1.25m**
- 屋顶 depth 被撑大：max(15, 10.5−(−6)+1) = **17.5m**（原设计 15m）

## 影响范围

| 蓝图 | 状态 | 偏移量 |
|---|---|---|
| `bieshu.wild` | ❌ 受影响 | Z 轴 +1.25m |
| `haoHuaBieshu.wild` | ❌ 受影响 | Z 轴 +1.25m |
| `tiantan.wild` | ✅ 不受影响 | 屋顶有显式 `position` |
| `cabin_v1.wild` | ✅ 不受影响 | 无阳台/栏杆等延伸墙 |

## 修复方案

在计算屋顶包围盒前，先过滤掉矮墙（栏杆、装饰墙等）：

```typescript
// 1. 计算所有墙的最大高度
let maxWallHeight = 0;
for (const wall of walls) {
  const h = Math.abs(wall.to[1] - wall.from[1]);
  if (h > maxWallHeight) maxWallHeight = h;
}

// 2. 只取高度 >= 最大高度 50% 的结构墙
const heightThreshold = maxWallHeight * 0.5;
const structuralWalls = walls.filter(w =>
  Math.abs(w.to[1] - w.from[1]) >= heightThreshold
);

// 3. 过滤后墙太少（如凉亭只有矮墙），退回全量
const effectiveWalls = structuralWalls.length >= 3 ? structuralWalls : walls;
```

**设计考量**：
- 阈值取 **最大高度的 50%** 而非绝对高度：适配不同规模的建筑（3m 层高 vs 6m 挑高大厅）
- 设置 **≥3 面墙** 的兜底条件：极端场景（如亭子可能全矮墙）退回全量逻辑
- 未引入新的蓝图字段，完全向后兼容

## 验证

修复后 `bieshu.wild`：
- 有效墙过滤掉 `balcony_railing_left`/`balcony_railing_right`（高 0.8m < 2.8m×0.5=1.4m）
- 主体结构墙包围盒 Z: [-6, 8]，中心 Z = 1.0 ✅
- 屋顶 position: [0, 5.8, 1.0] → 与主体建筑中心重合 ✅
