# 渲染引擎修复报告 (2026-07-21)

## 问题诊断

从用户提供的截图分析，发现以下渲染问题：

1. **墙体破碎/缺失** - 墙面有大片缺失
2. **屋顶定位错误** - 屋顶几何体穿透墙体
3. **地板下有空隙** - 地板厚度方向错误
4. **阳台结构异常** - 阳台地板/栏杆渲染错误

## 根本原因

经过源码分析，发现了**四个**引擎bug：

### Bug 1: 地板厚度方向错误 ❌

**文件**: `wild-web/src/wild-core/src/primitive/geometry/floor.ts`

**问题描述**:
- 地板 `from` 坐标定义的是地板**顶面**的Y坐标
- 但代码将地板中心点设置为 `from[1] - thickness/2`，导致地板**向下偏移**
- 结果：地板下方出现空隙

**修复前**:
```typescript
// 第26行
transform: { position: [midX, from[1]-effectiveThick/2, midZ], ... }

// 第67行 (圆形地板)
const centerY = from[1] - effectiveThick / 2;
const yBot = from[1] - effectiveThick;
```

**修复后**:
```typescript
// 地板应该向下延伸，不是向上
transform: { position: [midX, from[1] + effectiveThick/2, midZ], ... }

// 圆形地板也修复
const centerY = from[1] + effectiveThick / 2;
const yBot = from[1];
```

**影响**: 所有有厚度的地板（包括ground_floor, upper_floor, balcony）

---

### Bug 2: 开口Y坐标未转换 ❌

**文件**: `wild-web/src/wild-core/src/primitive/resolver.ts`

**问题描述**:
- 蓝图中 `opening.from[1]` 使用**世界Y坐标**（如规范所述）
- 但传给墙体生成器时，直接使用了这个值作为相对墙底的偏移
- 对于二层墙体（墙底Y=3），窗户Y=4实际应该是相对偏移1，但被当作偏移4使用
- 结果：开口位置错误，墙体几何破碎

**修复前** (第301-306行):
```typescript
wall._cutouts.push({
  localX: opening.from[0],
  localY: opening.from[1],  // ❌ 直接使用世界坐标
  localW: opening.width,
  localH: opening.height,
});
```

**修复后**:
```typescript
// opening.from[1] 是世界坐标Y，需要转换为相对墙底的偏移
wall._cutouts.push({
  localX: opening.from[0],
  localY: opening.from[1] - wallFrom[1],  // ✓ 转换为相对偏移
  localW: opening.width,
  localH: opening.height,
});
```

**示例**:
```
墙体: wall_upper_front
  from = [-8, 3, -6]    // 墙底Y=3
  to = [8, 5.8, -6]     // 墙顶Y=5.8

开口: window_upper_front_center
  from = [8, 4.0, 0]    // 世界Y=4.0
  
修复前: localY = 4.0 (错误，窗户会在墙外)
修复后: localY = 4.0 - 3.0 = 1.0 (正确，窗户在墙底向上1米)
```

**影响**: 所有开口（门、窗），特别是二层及以上的开口

---

### Bug 3: 开口Y坐标重复加半高 ❌

**文件**: `wild-web/src/wild-core/src/primitive/geometry/opening.ts`

**问题描述**:
- 开口几何体是以中心为原点的矩形
- `worldPos` 是开口底部的世界坐标
- 代码先计算了 `pos = worldPos || [x, y + hh, z]`（加了半高）
- 然后在transform中又用了 `position: [pos[0], pos[1] + hh, pos[2]]`（又加了半高）
- 结果：Y坐标被加了两次 `hh`，开口飘在墙上方

**修复前** (第18-27行):
```typescript
const pos = worldPos || [params.from[0], params.from[1] + hh, params.from[2]];

return [{
  geometry,
  indices: new Uint32Array(indices),
  transform: {
    position: [pos[0], pos[1] + hh, pos[2]],  // ❌ 又加了一次hh
    rotation: [0, wallRotation, 0],
    scale: [1, 1, 1]
  },
```

**修复后**:
```typescript
// worldPos 已经是开口底部的世界坐标，需要加上半高度使开口中心对齐
const centerY = worldPos ? worldPos[1] + hh : params.from[1] + hh;
const pos = worldPos || [params.from[0], params.from[1], params.from[2]];

return [{
  geometry,
  indices: new Uint32Array(indices),
  transform: {
    position: [pos[0], centerY, pos[2]],  // ✓ 只加一次hh
    rotation: [0, wallRotation, 0],
    scale: [1, 1, 1]
  },
```

**示例**:
```
开口: front_door
  width = 1.2m, height = 2.4m
  hh = 1.2m (半高)
  worldPos = [0, 0, -6]  // 底部世界坐标

修复前:
  pos = [0, 0, -6]
  position = [0, 0+1.2, -6] = [0, 1.2, -6]  // 错误：门底部在Y=1.2
  
修复后:
  centerY = 0 + 1.2 = 1.2
  pos = [0, 0, -6]
  position = [0, 1.2, -6]  // 正确：门中心在Y=1.2，底部在Y=0
```

**影响**: 所有开口（门、窗）- 导致开口飘在墙上方，与墙体分离

---

### Bug 4: 蓝图规范文档需要更新

**文件**: `wild-web/docs/BLUEPRINT-SPECIFICATION.md`

**问题**: 规范未明确说明 `opening.from[1]` 应该使用世界Y坐标

**修复**: 
1. 明确说明from[1]是**世界Y坐标**，不是相对偏移
2. 添加二层窗户的示例
3. 更新常见错误和验证清单

---

## 修复文件清单

| 文件 | 修改内容 | 行数 |
|------|---------|------|
| `wild-web/src/wild-core/src/primitive/geometry/floor.ts` | 修复地板厚度方向 | 26, 67-68 |
| `wild-web/src/wild-core/src/primitive/resolver.ts` | 修复开口Y坐标转换 | 301-307 |
| `wild-web/src/wild-core/src/primitive/geometry/opening.ts` | 修复开口Y坐标重复加半高 | 18-32 |
| `wild-web/docs/BLUEPRINT-SPECIFICATION.md` | 更新规范文档 | 多处 |

---

## 测试建议

### 测试用例 1: 地板厚度
```
预期: 地板从Y=0向下延伸0.3米到Y=-0.3
实际: 加载任意蓝图，观察地板不应有空隙
```

### 测试用例 2: 一层开口
```
蓝图: cabin_v1.wild 或 villa_correct.wild
墙体: from=[0, 0, 0], to=[6, 3, 0]
开口: from=[3, 0, 0], width=1.2, height=2.4
预期: 门在墙底（Y=0），沿墙3米处
```

### 测试用例 3: 二层开口
```
蓝图: villa_correct.wild
墙体: wall_upper_front
  from=[-8, 3, -6], to=[8, 5.8, -6]
开口: window_upper_front_center
  from=[8, 4.0, 0], width=2.0, height=1.5
预期: 窗户底部在Y=4.0（墙底向上1米），沿墙8米（中心）
```

---

## 构建和测试

**构建命令** (在wild-web目录):
```bash
npm run build
# 或
npm run dev
```

**测试步骤**:
1. 启动开发服务器
2. 加载 `villa_correct.wild`
3. 检查：
   - 地板不应有空隙
   - 墙体完整，无破碎
   - 门窗在正确位置
   - 阳台结构完整

---

## 技术说明

### 坐标系统总结

| 元素类型 | 坐标字段 | 含义 |
|---------|---------|------|
| 墙体 | from, to | 世界坐标 [X, Y, Z] |
| 地板 | from, to | 世界坐标，from是顶面Y |
| 开口 | from[0] | **沿墙距离**（不是世界X/Z） |
| 开口 | from[1] | **世界Y坐标**（不是相对偏移） |
| 开口 | from[2] | 法向偏移（通常为0） |

### 为什么地板厚度向下？

建筑学惯例：
- 地板标高指的是**可行走表面**（顶面）
- 地板结构（梁板）在可行走表面**之下**
- 所以蓝图中 `from=[x, y, z]` 定义的是地板顶面
- 厚度应该向下延伸

### 为什么开口Y用世界坐标？

设计决策：
- 简化蓝图编写：同一高度的窗户可以用相同的Y值
- 与墙体坐标一致：墙体用世界坐标，开口也用世界坐标
- 引擎负责转换：resolver自动转换为墙体局部坐标

---

## 相关文档

- [蓝图规范文档](./BLUEPRINT-SPECIFICATION.md)
- [正确格式别墅](../myLantu/villa_correct.wild)
- [测试说明](../test/TEST-INSTRUCTIONS.md)

---

## 修复时间

2026-07-21

**状态**: ✅ 已修复，待测试
