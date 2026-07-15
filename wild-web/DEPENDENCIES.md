# 项目依赖说明

## 已安装的依赖

以下依赖已添加到 `package.json`，需要运行 `npm install` 安装：

```json
{
  "dependencies": {
    "pinia": "^2.1.7",
    "three": "^0.160.0"
  },
  "devDependencies": {
    "@types/three": "^0.160.0"
  }
}
```

## 安装命令

```bash
cd wild-web
npm install
```

## 依赖用途

- **pinia**: Vue 3 状态管理库，用于管理编辑器状态（场景、UI、历史记录等）
- **three**: Three.js 3D 渲染引擎，用于显示和渲染 3D 场景
- **@types/three**: Three.js 的 TypeScript 类型定义

## wild-core 集成状态

### ✅ 已完成

1. **类型系统修复**：`wild-core/src/primitive/types.ts` 已完全独立，内联了所有类型定义
   - 所有具体构件参数类型（WallParams, ColumnParams, FloorParams 等）已补全
   - 完整的材质系统类型（MaterialDef, EffectLayer, WeatheringEffect 等）
   - 完整的动态系统类型（PhysicsData, ConstraintData, ScriptData 等）
   - 不再依赖外部 `wild-lang/types`

2. **渲染适配层**：创建了完整的 wild-core 到 Three.js 的适配层
   - `renderer/wildCoreAdapter.ts`: 核心接口封装
   - `renderer/meshDataToGeometry.ts`: 网格数据转换
   - `renderer/materialAdapter.ts`: 材质转换和缓存
   - `renderer/renderEntity.ts`: 场景组装

3. **场景加载集成**：sceneStore 和 CanvasViewport 已连接到 wild-core
   - 支持加载 .wild 文件
   - 自动重建几何和材质
   - 实时 3D 渲染

4. **TypeScript 编译**：所有文件通过类型检查，无错误

### 📋 类型系统详情

`wild-core/src/primitive/types.ts` 现在包含：

**基础类型**:
- Vec3, Color

**元数据**:
- Meta, CurveSegment (LineCurve, ArcCurve, EllipseCurve, CatenaryCurve)

**几何构件参数**:
- WallParams, FloorParams, ColumnParams, BeamParams
- RoofParams, OpeningParams, StairParams, FurnitureParams
- DenseBrickParams, BodyParams
- GeometryElement (联合类型)

**材质系统**:
- MaterialDef, WeatheringEffect, MossEffect, EdgeWearEffect
- EffectLayer, EmbeddedImageData

**动态系统**:
- PhysicsData, ConstraintData, HingeConstraint, SliderConstraint
- AnimationParams, ScriptData, ScriptCondition, ActionData

**蓝图结构**:
- Blueprint, InstanceRef, Placement

**引擎内部类型**:
- MeshData, MaterialParams, AABB, ReconstructedEntity, SpatialIndex

### 🚀 下一步

- 测试加载 `lantu/bieshu.wild` 示例文件
- 实现 3D 拾取和选中高亮
- 添加 Transform Gizmo（移动/旋转/缩放）
- 实现局部重建优化
- 添加导出功能（GLB/IFC）

## 开发服务器

启动开发服务器：

```bash
cd wild-web
npm run dev
```

构建生产版本：

```bash
npm run build
```

## 相关文档

- `docs/FRONTEND_API.md`: 前后端 API 接口规范
- `docs/WILD_CORE_INTEGRATION.md`: wild-core 集成详细说明
- `rules/css.md`: CSS 样式规范
- `CLAUDE.md`: 项目快速了解文档（根目录）
