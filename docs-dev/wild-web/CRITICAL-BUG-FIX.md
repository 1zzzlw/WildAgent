# 🔴 关键Bug修复：屋顶position丢失

## Bug描述

**症状**：别墅（bieshu.wild）和天坛（tiantan.wild）渲染时出现模型错乱、构件交叉

**根本原因**：瓦片合并逻辑错误地将屋顶主体当作小瓦片处理，导致屋顶position信息丢失

## 问题分析

### 调试输出

```
屋顶position（resolver计算）: [0, 5.8, 1]   ✓ 正确
屋顶网格position（实际渲染）: [0, 0, 0]     ❌ 错误！
```

### 代码追踪

1. **resolver计算正确**：
   ```typescript
   // resolveRoofBoundary计算的position
   position = [(minX + maxX) / 2, maxY, (minZ + maxZ) / 2]
            = [0, 5.8, 1]  // ✓ 正确
   ```

2. **buildRoof生成网格**：
   ```typescript
   return [{
     geometry: geo,
     transform: { position: [0, 5.8, 1], ... },  // ✓ position传递正确
     materialRef: 'roof_tile',
     elementId: 'main_roof'
   }];
   ```

3. **瓦片合并逻辑**（**这里出错！**）：
   ```typescript
   // index.ts line 242-266
   for (const m of rawMeshes) {
     if (m.materialRef === 'roof_tile' && m.transform.position) {
       const [px, py, pz] = m.transform.position;
       
       // 检测已在世界坐标的大网格
       if (px === 0 && py === 0 && pz === 0 && m.geometry.length > 1000) {
         otherMeshes.push(m);  // 保留
         continue;
       }
       
       // ❌ BUG: 屋顶position是[0,5.8,1]，不满足上面的条件
       // 于是被当作小瓦片，转换到世界坐标并合并
       
       for (let i = 0; i < m.geometry.length; i += 3) {
         tileVerts.push(
           m.geometry[i] + px,      // 加上position
           m.geometry[i + 1] + py,
           m.geometry[i + 2] + pz
         );
       }
       // ... 合并
     }
   }
   
   // 合并后创建新网格
   otherMeshes.push({
     geometry: new Float32Array(tileVerts),
     transform: { position: [0, 0, 0], ... },  // ❌ position丢失！
     materialRef: 'roof_tile',
     elementId: undefined  // ❌ elementId也丢失！
   });
   ```

### 问题本质

**瓦片合并逻辑的设计意图**：
- 合并placement生成的大量小瓦片（每个瓦片4-12个顶点）
- 减少draw call，提升性能

**实际错误**：
- 没有区分"屋顶主体"和"小瓦片"
- 判断条件`px === 0 && py === 0 && pz === 0`过于严格
- 导致屋顶主体被错误合并

## 修复方案

### 修改前

```typescript
for (const m of rawMeshes) {
  if (m.materialRef === 'roof_tile' && m.transform.position) {
    const [px, py, pz] = m.transform.position;
    
    // 只检查position和geometry大小
    if (px === 0 && py === 0 && pz === 0 && m.geometry.length > 1000) {
      otherMeshes.push(m);
      continue;
    }
    
    // 否则合并（错误地包含了屋顶主体）
    // ...
  }
}
```

### 修改后

```typescript
for (const m of rawMeshes) {
  if (m.materialRef === 'roof_tile' && m.transform.position) {
    const [px, py, pz] = m.transform.position;
    
    // 若已经在世界坐标中（批处理合并的网格），直接保留
    if (px === 0 && py === 0 && pz === 0 && m.geometry.length > 1000) {
      otherMeshes.push(m);
      continue;
    }
    
    // ✅ 新增：屋顶主体判断
    // 有elementId且几何较大（> 20顶点）→ 这是屋顶主体，保留原样
    if (m.elementId && m.geometry.length / 3 > 20) {
      otherMeshes.push(m);
      continue;
    }
    
    // 小瓦片：合并到世界坐标
    // ...
  }
}
```

### 关键改进

1. **检查elementId**：屋顶主体有elementId（如'main_roof'），小瓦片没有
2. **检查几何大小**：屋顶主体顶点数较多（gable roof有8个三角形=24个顶点），小瓦片很少（4-12个顶点）
3. **阈值选择**：20个顶点足以区分屋顶主体和小瓦片

## 影响范围

### 受影响的蓝图

| 蓝图 | 屋顶材质 | 是否受影响 | 原因 |
|------|---------|-----------|------|
| cabin_v1.wild | roof_structure | ❌ 不受影响 | 材质不是roof_tile |
| bieshu.wild | roof_tile | ✅ **受影响** | 屋顶主体被错误合并 |
| tiantan.wild | roof_blue | ❌ 不受影响 | 材质不是roof_tile |

**注意**：tiantan虽然屋顶材质不是roof_tile，但如果其他蓝图使用roof_tile作为屋顶主体材质，也会受影响。

### cabin_v1为何正常？

查看cabin_v1的屋顶定义：
```json
{
  "type": "roof",
  "id": "main_roof",
  "roofType": "gable",
  "material": "roof_structure"  // ← 不是 roof_tile
}
```

因为材质是`roof_structure`而不是`roof_tile`，所以不会进入瓦片合并逻辑。

## 验证

### 修复前

```
屋顶网格:
  #0: undefined
    materialRef: roof_tile
    position: [0.00, 0.00, 0.00]  ❌ 错误
    elementId: undefined          ❌ 丢失
```

### 修复后（预期）

```
屋顶网格:
  #0: main_roof
    materialRef: roof_tile
    position: [0.00, 5.80, 1.00]  ✓ 正确
    elementId: main_roof          ✓ 保留
```

## 测试步骤

1. 保存修改后的代码
2. 刷新浏览器（Ctrl+R）
3. 重新加载 bieshu.wild
4. 查看控制台输出，确认：
   - 屋顶网格position为`[0, 5.8, 1]`
   - elementId为`main_roof`
5. 查看3D视图，确认屋顶位置正确

## 相关文件

- 修改：`src/wild-core/src/primitive/index.ts` (line 235-267)
- 蓝图：`lantu/bieshu.wild`
- 调试：`src/utils/debugRender.ts`

## 后续改进建议

1. **明确瓦片合并的触发条件**：
   - 只合并没有elementId的网格
   - 或者只合并geometry很小的网格（< 50顶点）

2. **添加材质命名约定**：
   - `roof_tile` 应该只用于placement的小瓦片
   - 屋顶主体应该使用其他材质名（如`roof_surface`）

3. **添加警告日志**：
   ```typescript
   if (m.elementId && m.geometry.length / 3 > 100) {
     console.warn(`Large roof mesh with roof_tile material: ${m.elementId}`);
   }
   ```

---

修复人：Kiro AI Assistant  
日期：2026-07-21  
文件：src/wild-core/src/primitive/index.ts
