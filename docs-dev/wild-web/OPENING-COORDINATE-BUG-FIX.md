# 🔴 关键Bug修复：开口坐标转换错误导致墙体几何异常

## Bug描述

**症状**：
- 墙体边界盒异常巨大（X范围从-13.75到8.5，应该是-8到8）
- 墙体渲染错乱、相互交叉
- 开口（门窗）位置错误

**根本原因**：
`resolveOpenings` 函数错误地将开口的**世界坐标**直接当作**沿墙距离**使用，导致 `boxWithHoles` 生成错误的几何体。

## 问题分析

### 蓝图中的开口定义

```json
{
  "type": "opening",
  "id": "window_front_left",
  "parentWall": "wall_front",
  "from": [-5.0, 1.0, -6.0],  // ← 世界坐标
  "width": 1.5,
  "height": 1.2
}
```

开口的 `from` 字段是**世界坐标** `[-5.0, 1.0, -6.0]`。

### 墙体定义

```json
{
  "type": "wall",
  "id": "wall_front",
  "from": [-8.0, 0.0, -6.0],
  "to": [8.0, 3.0, -6.0],
  "thickness": 0.3
}
```

wall_front 是一面沿X轴的墙：
- 起点：X=-8.0, Z=-6.0
- 终点：X=8.0, Z=-6.0  
- 长度：16米

### 错误的坐标转换

**修复前的代码**（resolver.ts line 301）：

```typescript
wall._cutouts.push({
  localX: opening.from[0],  // ❌ 直接使用世界X坐标 -5.0
  localY: opening.from[1],  // ❌ 直接使用世界Y坐标 1.0
  localW: opening.width,
  localH: opening.height,
});
```

这导致：
- `localX = -5.0`（错误！应该是3.0）
- `localY = 1.0`（碰巧正确，因为墙底Y=0）

### boxWithHoles的坐标系统

`boxWithHoles` 接收的 cutout 参数使用**墙体局部坐标系**：
- `localX`：开口中心沿墙的距离（从墙起点算起，单位：米）
- `localY`：开口底部相对墙底的高度（单位：米）

然后转换为**盒体中心坐标系**：

```typescript
const holes = cutouts.map(c => ({
  x1: c.localX - c.localW / 2 - hl,  // ← hl = length/2
  x2: c.localX + c.localW / 2 - hl,
  y1: c.localY - hh,
  y2: c.localY + c.localH - hh,
}));
```

对于 wall_front（长度16米）：
- `hl = 8.0`
- 错误的localX=-5.0会导致：
  - `x1 = -5.0 - 0.75 - 8.0 = -13.75` ❌
  - `x2 = -5.0 + 0.75 - 8.0 = -12.25` ❌
- 正确的localX=3.0应该是：
  - `x1 = 3.0 - 0.75 - 8.0 = -5.75` ✓
  - `x2 = 3.0 + 0.75 - 8.0 = -4.25` ✓

### 实际影响

从调试输出（query #8）可以看到：

```
边界盒: {min: [-13.75, -0.3, -14.6], max: [8.5, 8.8, 16.6]}
```

X的最小值是**-13.75**，这正好对应错误计算的开口位置！

## 修复方案

### 正确的坐标转换逻辑

**修复后的代码**：

```typescript
// 计算开口沿墙的局部坐标
let localX: number, localY: number;

if (wallCurve && wallCurve.type === 'arc') {
  // 弧形墙：开口from[0]已经是弧长
  localX = opening.from[0];
  localY = opening.from[1];
} else {
  // 直线墙：需要从世界坐标转换到沿墙距离
  const wallDx = wallTo[0] - wallFrom[0];
  const wallDz = wallTo[2] - wallFrom[2];
  const wallLen = Math.sqrt(wallDx * wallDx + wallDz * wallDz);
  
  if (wallLen < 0.001) {
    localX = 0;
    localY = 0;
  } else {
    // 开口中心点到墙起点的向量
    const openingX = opening.from[0];
    const openingZ = opening.from[2];
    const toOpeningX = openingX - wallFrom[0];
    const toOpeningZ = openingZ - wallFrom[2];
    
    // 投影到墙方向上，得到沿墙距离
    const dirX = wallDx / wallLen;
    const dirZ = wallDz / wallLen;
    localX = toOpeningX * dirX + toOpeningZ * dirZ;
    
    // Y是相对墙底的高度
    localY = opening.from[1] - wallFrom[1];
  }
}

wall._cutouts.push({
  localX: localX,
  localY: localY,
  localW: opening.width,
  localH: opening.height,
});
```

### 转换示例

#### 示例1：wall_front 的 window_front_left

```
墙体：from=[-8, 0, -6], to=[8, 3, -6]
开口世界坐标：[-5, 1, -6]

计算过程：
1. wallDx = 8 - (-8) = 16
   wallDz = -6 - (-6) = 0
   wallLen = 16

2. toOpeningX = -5 - (-8) = 3
   toOpeningZ = -6 - (-6) = 0

3. dirX = 16/16 = 1
   dirZ = 0/16 = 0

4. localX = 3*1 + 0*0 = 3.0 ✓
   localY = 1 - 0 = 1.0 ✓
```

#### 示例2：wall_left 的 window_left

```
墙体：from=[-8, 0, -6], to=[-8, 3, 8]
开口世界坐标：[-8, 1, -2]

计算过程：
1. wallDx = -8 - (-8) = 0
   wallDz = 8 - (-6) = 14
   wallLen = 14

2. toOpeningX = -8 - (-8) = 0
   toOpeningZ = -2 - (-6) = 4

3. dirX = 0/14 = 0
   dirZ = 14/14 = 1

4. localX = 0*0 + 4*1 = 4.0 ✓
   localY = 1 - 0 = 1.0 ✓
```

## 测试验证

创建了 `test/validate-opening-fix.js` 测试文件，验证坐标转换逻辑：

```bash
node test/validate-opening-fix.js
```

结果：
```
✓ PASS: wall_front 的 window_front_left
✓ PASS: wall_front 的 front_door
✓ PASS: wall_left 的 window_left

总结: 3 通过, 0 失败
✓ 所有测试通过！坐标转换逻辑正确。
```

## 预期效果

修复后，墙体边界盒应该恢复正常：

**修复前**：
```
边界盒: {min: [-13.75, -0.3, -14.6], max: [8.5, 8.8, 16.6]}
尺寸: 22.25m × 9.1m × 31.2m ❌
```

**修复后（预期）**：
```
边界盒: {min: [-8.15, -0.3, -6.15], max: [8.15, 8.8, 10.65]}
尺寸: ~16.3m × 9.1m × ~16.8m ✓
```

（考虑墙厚和阳台，略大于墙体坐标范围是正常的）

## 弧形墙的特殊处理

对于弧形墙（如tiantan.wild的圆形墙），开口的 `from[0]` **已经是弧长**，不需要转换：

```typescript
if (wallCurve && wallCurve.type === 'arc') {
  localX = opening.from[0];  // 直接使用，已经是弧长
  localY = opening.from[1];  // 相对墙底高度
}
```

这是因为弧形墙的开口定义不同：
```json
{
  "type": "opening",
  "id": "door_N",
  "parentWall": "circular_wall",
  "from": [0, 0, 0],  // [弧长, 高度, 径向偏移]
  "width": 1.2,
  "height": 2.4
}
```

## 相关文件

- 修改：`wild-web/src/wild-core/src/primitive/resolver.ts` (line 289-334)
- 调试：`wild-web/src/wild-core/src/primitive/geometry/box-with-holes.ts` (添加调试日志)
- 调试：`wild-web/src/wild-core/src/primitive/geometry/wall.ts` (添加调试日志)
- 测试：`wild-web/test/validate-opening-fix.js`
- 文档：`wild-web/docs/OPENING-COORDINATE-BUG-FIX.md`

## 浏览器测试步骤

1. 如果开发服务器在运行，它会自动热更新
2. 刷新浏览器（Ctrl+R）
3. 重新加载 bieshu.wild
4. 查看控制台输出：
   - 应该看到 `🧱 buildWall` 和 `📦 boxWithHoles` 的调试日志
   - 检查 cutout 的 localX 值是否合理（应该在0-16之间）
   - 检查边界盒尺寸是否恢复正常

5. 查看3D视图：
   - 墙体应该正确对齐
   - 门窗应该在正确的位置
   - 整体建筑应该不再错乱

## 后续任务

此修复完成后，还需要解决：

1. **GridHelper不显示**：初始页面加载时网格消失的问题
2. **构件库放置bug**：
   - 墙体显示为单线
   - 地板不显示且清除其他构件

---

修复人：Kiro AI Assistant  
日期：2026-07-21  
Bug类型：坐标系统转换错误  
严重程度：Critical（导致所有带开口的墙体几何错误）
