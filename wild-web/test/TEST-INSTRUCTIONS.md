# 测试说明

## 已修复的Bug

### 1. 开口坐标转换Bug（Critical）

**文件**：`src/wild-core/src/primitive/resolver.ts`

**问题**：开口的世界坐标被错误地当作沿墙距离使用，导致墙体几何异常巨大

**影响**：所有带门窗的墙体都会生成错误的几何体

**修复**：正确计算开口沿墙的投影距离

### 2. 屋顶位置丢失Bug

**文件**：`src/wild-core/src/primitive/index.ts`

**问题**：瓦片合并逻辑错误地合并了屋顶主体，导致position丢失

**修复**：添加elementId和顶点数检查，避免屋顶主体被合并

## 启动开发服务器

由于PowerShell执行策略限制，请在Windows命令提示符(CMD)中运行：

```cmd
cd E:\AgentProject\WildAgent\wild-web
npm run dev
```

或者在PowerShell中临时允许脚本执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd E:\AgentProject\WildAgent\wild-web
npm run dev
```

## 测试步骤

### 1. 验证修复效果

1. 启动开发服务器后，在浏览器中打开应用
2. 加载 `bieshu.wild`
3. 打开浏览器控制台（F12）

### 2. 检查调试输出

应该看到以下日志：

```
🧱 buildWall wall_front
  from: [-8.00, 0.00, -6.00]
  to: [8.00, 3.00, -6.00]
  length: 16.00m, height: 3.00m
  cutouts: 3
    - localX=3.00, localW=1.50
    - localX=8.00, localW=1.20
    - localX=13.00, localW=1.50

📦 boxWithHoles: L=16.00, H=3.00, T=0.30
  hl=8.00, hh=1.50, ht=0.15
  cutouts: 3
  转换后的holes:
    [0] x1=-5.75, x2=-4.25, y1=-0.50, y2=0.70
    [1] x1=-0.60, x2=0.60, y1=-1.50, y2=0.90
    [2] x1=4.25, x2=5.75, y1=-0.50, y2=0.70
```

**关键检查点**：
- ✓ localX 值应该在 0-16 之间（不是负数）
- ✓ x1/x2 值应该在 -8 到 8 之间（盒体半长）
- ✓ 边界盒尺寸应该合理（~16m × 9m × 17m）

### 3. 检查渲染效果

```javascript
// 在浏览器控制台执行
console.log('边界盒:', debugScene.scene.children[3].children[0].geometry.boundingBox);
```

**预期结果**：
```
边界盒: {
  min: [-8.15, -0.3, -6.15],
  max: [8.15, 8.8, 10.65]
}
```

X范围应该是 -8到8（墙体范围），而不是 -13.75到8.5

### 4. 视觉检查

3D视图中应该看到：
- ✓ 墙体正确对齐，没有错位
- ✓ 门窗在正确位置
- ✓ 屋顶在墙顶上方（Y=5.8）
- ✓ 楼板在正确高度（ground Y=-0.15, upper Y=2.9）
- ✓ 整体建筑结构完整，不再错乱

## 运行单元测试

```bash
cd E:\AgentProject\WildAgent\wild-web\test
node validate-opening-fix.js
```

应该看到：
```
✓ PASS: wall_front 的 window_front_left
✓ PASS: wall_front 的 front_door
✓ PASS: wall_front 的 window_left
总结: 3 通过, 0 失败
```

## 测试其他蓝图

### cabin_v1.wild
- 应该保持正常（之前就是正常的）
- 无开口，所以不受此bug影响

### tiantan.wild
- 圆形墙体（弧形）
- 4个门应该均匀分布（已在之前修复蓝图文件）
- 检查门是否在正确的角度位置

## 如果问题仍然存在

### 清除缓存
```javascript
// 在浏览器控制台执行
localStorage.clear();
sessionStorage.clear();
location.reload(true);
```

### 检查TypeScript编译
```cmd
cd E:\AgentProject\WildAgent\wild-web
npm run build
```

查看是否有编译错误

### 检查Vite HMR
如果热更新没有生效，手动刷新浏览器（Ctrl+Shift+R 强制刷新）

## 已知问题（待修复）

1. **GridHelper消失**：初始加载时显示一瞬间后消失
   - 需要检查 CanvasViewport.vue 的场景更新逻辑

2. **构件库放置bug**：
   - 墙体显示为单线
   - 地板不显示
   - 需要检查 stores/ 和 agent/ 的状态管理

## 调试工具

项目中已添加调试工具，可在浏览器控制台使用：

```javascript
// 测试基础渲染
debugScene.testScene();

// 清除测试对象
debugScene.clearTest();

// 查看场景内容
console.log(debugScene.scene.children);

// 查看WildScene组
console.log(debugScene.scene.children[3].children);
```

## 文档

详细的修复说明请查看：
- `docs/OPENING-COORDINATE-BUG-FIX.md` - 开口坐标bug
- `docs/CRITICAL-BUG-FIX.md` - 屋顶位置bug
- `docs/FINAL-FIX-REPORT.md` - 蓝图文件修复
- `docs/COMPREHENSIVE-DIAGNOSIS.md` - 综合诊断

---

最后更新：2026-07-21
