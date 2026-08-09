# 综合诊断报告

## 当前状态

从最新的渲染图片和调试输出看，存在以下问题：

### 1. 几何数据正确性 ✓
```
屋顶: position [0.00, 5.80, 1.00] ✓
      geometry Y: 0 to 3 ✓
      → 实际Y: 5.8 to 8.8 ✓

墙体: position Y: 1.50 (1层), 4.40 (2层) ✓
      → 墙顶: 3.0, 5.8 ✓

地板: ground Y: -0.45 (底面-0.6, 顶面-0.3) ✓
      upper Y: 2.70 (底面2.6, 顶面2.8) ✓
```

**结论：渲染引擎输出的数据完全正确！**

### 2. 视觉渲染错误 ❌

从图片看：
- 屋顶不在墙顶上方，而是悬空/错位
- 墙体分离
- 地板位置混乱
- 整体像"爆炸视图"

**这说明问题在Three.js渲染层！**

## 可能的原因

### 原因1: 材质/阴影问题
- 所有mesh都设置了`castShadow`和`receiveShadow`
- 如果阴影计算错误，可能导致视觉错乱

### 原因2: 相机/控制器问题
- OrbitControls的target可能不对
- 相机position计算可能有误

### 原因3: 场景组织问题
- 所有mesh都添加到同一个Group
- Group的transform可能有问题

### 原因4: 材质透明度
- 如果某些材质设置了opacity但没有设置transparent
- 可能导致渲染顺序错误

## 诊断步骤

### 步骤1: 检查相机位置

在CanvasViewport.vue中添加：
```typescript
console.log('Camera:', camera.position, camera.rotation);
console.log('Controls target:', controls.target);
```

### 步骤2: 禁用阴影测试

临时禁用阴影看效果：
```typescript
mesh.castShadow = false;
mesh.receiveShadow = false;
```

### 步骤3: 简化渲染

只渲染一种元素（如只渲染墙体）：
```typescript
if (!m.elementId?.includes('wall')) continue;
```

### 步骤4: 检查GridHelper

GridHelper应该在initThreeJS中创建：
```typescript
const gridHelper = new THREE.GridHelper(20, 20, 0x444444, 0x333333);
scene.add(gridHelper);
```

确认它是否被添加到scene。

## 建议修复顺序

### 优先级1: 修复GridHelper不显示

这是最基本的，如果GridHelper都不显示，说明scene或renderer有问题。

### 优先级2: 简化场景测试

创建一个最简单的测试场景：
```typescript
// 只渲染一个box
const geometry = new THREE.BoxGeometry(1, 1, 1);
const material = new THREE.MeshStandardMaterial({ color: 0xff0000 });
const cube = new THREE.Mesh(geometry, material);
cube.position.set(0, 0.5, 0);
scene.add(cube);
```

如果这个都显示不正确，问题在基础渲染设置。

### 优先级3: 逐个添加构件

按顺序添加：
1. 地板 → 检查
2. 墙体 → 检查
3. 屋顶 → 检查

确定是哪个构件导致混乱。

## 构件库问题

你提到的构件库bug：
- 墙面只显示一条线
- 放置地板不显示
- 放置地板后其他构件消失

这些是**编辑器逻辑问题**，不是渲染引擎问题。需要检查：
- `src/stores/` - 状态管理
- `src/components/` - UI组件
- `src/agent/` - Agent逻辑

## 下一步行动

我需要你：

1. **检查GridHelper**
   - 在浏览器控制台输入：`scene.children`
   - 看看scene里有哪些对象
   - GridHelper应该在列表中

2. **测试简单场景**
   - 临时注释掉加载蓝图的代码
   - 手动添加一个红色cube
   - 看看是否正常显示

3. **检查材质设置**
   - 在materialAdapter中添加日志
   - 看看材质参数是否正确

4. **提供更多信息**
   - 浏览器控制台有没有错误？
   - 网络请求有没有失败？
   - Three.js版本是多少？

请先做第1和第2步，把结果告诉我！
