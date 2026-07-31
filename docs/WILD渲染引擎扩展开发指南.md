# WILD 渲染引擎扩展开发指南

> 适用版本：WILD 1.1 / wild-core 1.1  
> 编写日期：2026-07-31  
> 目标：说明“新增一个物件”与“新增一种引擎能力”分别应该怎样做

## 1. 先判断：到底需不需要扩展 Core

WILD 1.1 以后，新增现实物件不等于新增构件类型。

| 需求 | 推荐方式 | 是否修改 Core |
|---|---|---|
| 篮球、花瓶、路灯、简单线脚 | 用 `primitive` 和已有构件组合 | 否 |
| 重复柱、瓦片、栏杆 | 模板、实例、placements | 通常否 |
| 中式曲面屋顶 | 使用已有 `roofType: "chinese_curved"` | 否 |
| 新的截面扫掠细节 | `primitive.shape: "profile_sweep"` | 否 |
| 现有 shape 无法表达的新数学造型 | 新增 builder | 是 |
| 高精雕刻、骨骼角色、复杂美术网格 | 未来外部资产能力 | 当前不实现 |

判断标准只有一个：如果现有数学形体能够组合出来，就不要增加 `type: "basketball"` 之类的业务类型。只有出现新的成形算法时，才扩展 Core。

## 2. 当前代码边界

渲染链路现在分为三层：

```text
.wild 数据
  -> parser / expander / resolver
  -> builder registry + geometry builder
  -> MeshData（position / index / normal / UV / transform）
  -> Three.js geometry + PBR material + scene lighting
```

主要文件：

| 职责 | 项目代码 |
|---|---|
| WILD 权威 Schema | `wild-web/wild-lang/schema.json` |
| Core 公共类型 | `wild-web/src/wild-core/types.ts` |
| Core 内部类型 | `wild-web/src/wild-core/src/primitive/types.ts` |
| Builder 注册表 | `wild-web/src/wild-core/src/primitive/registry.ts` |
| 几何构建器 | `wild-web/src/wild-core/src/primitive/geometry/` |
| Core 重建入口 | `wild-web/src/wild-core/src/primitive/index.ts` |
| Three.js 几何适配 | `wild-web/src/renderer/meshDataToGeometry.ts` |
| Three.js 材质适配 | `wild-web/src/renderer/materialAdapter.ts` |
| 能力清单适配 | `wild-web/src/renderer/wildCoreAdapter.ts` |
| 后端结构校验 | `wild-server/app/tools/spatial_tools.py` |
| Agent 精简规范 | `wild-server/storage/knowledge_base/BLUEPRINT-SPEC-MINIMAL.md` |

Core 不再通过一个大 `switch` 分发所有构件，而是从 registry 查找 builder。注册表当前是应用启动时静态注册：`.wild` 只能携带数据，不能携带或执行 JavaScript。

## 3. 第一种扩展：不改 Core，组合一个新物件

### 3.1 篮球

项目中的完整样例是：

`wild-web/lantu/basketball_v1_1.wild`

球体使用通用 sphere：

```json
{
  "type": "primitive",
  "id": "basketball_body",
  "shape": "sphere",
  "position": [0, 0.121, 0],
  "radius": 0.12,
  "segments": 40,
  "heightSegments": 24,
  "material": "basketball_orange"
}
```

接缝使用通用 profile sweep：

```json
{
  "type": "primitive",
  "id": "basketball_seam_horizontal",
  "shape": "profile_sweep",
  "radius": 0.0018,
  "segments": 6,
  "path": [
    [0.1215, 0.121, 0],
    [0.0859, 0.121, 0.0859],
    [0, 0.121, 0.1215],
    [-0.0859, 0.121, 0.0859],
    [-0.1215, 0.121, 0]
  ],
  "material": "basketball_seam"
}
```

表面颗粒使用正式的 `grain` 效果：

```json
{
  "baseColor": [0.86, 0.24, 0.035],
  "roughness": 0.78,
  "metallic": 0,
  "albedo": 1,
  "lightingCondition": "D65_noon",
  "effects": [
    { "type": "grain", "intensity": 0.09, "scale": 0.006 }
  ]
}
```

这里没有 basketball builder。篮球只是 sphere、两组 sweep 和两个材质的装配结果。

### 3.2 复杂屋檐

项目中的完整样例是：

`wild-web/lantu/eave_extension_v1_1.wild`

主体使用现有中式曲面屋顶，檐口和屋脊使用 sweep：

```json
{
  "type": "roof",
  "id": "curved_roof",
  "roofType": "chinese_curved",
  "span": 8.2,
  "depth": 6.4,
  "height": 2.25,
  "thickness": 0.16,
  "eaveCurveHeight": 0.62,
  "curveProfile": "gentle",
  "position": [0, 3.72, 0],
  "material": "roof_tile"
}
```

```json
{
  "type": "primitive",
  "id": "front_eave_profile",
  "shape": "profile_sweep",
  "profile": [
    [-0.07, -0.09],
    [0.07, -0.09],
    [0.09, 0.02],
    [0, 0.08],
    [-0.09, 0.02]
  ],
  "path": [
    [-4.1, 3.72, 3.2],
    [0, 3.68, 3.2],
    [4.1, 3.72, 3.2]
  ],
  "material": "eave_gold"
}
```

更复杂的古建可以继续拆成屋面、檐口、屋脊、瓦片排布、柱梁和斗拱装配。只有当目标样例证明 `profile_sweep` 仍不能表达某段曲面时，才增加新的通用 shape。

## 4. 第二种扩展：增加一种新的 Builder

假设未来确实需要一种现有 shape 无法表达的 `lathe`（旋转体）。最小改动顺序如下。

### 4.1 在权威类型中增加参数

修改 `wild-web/src/wild-core/types.ts`，让新类型进入 `GeometryElement` 联合类型，并定义明确参数。字段必须是可验证的数据，不能放回调、Three.js 对象或任意脚本。

### 4.2 编写纯几何 Builder

在 `wild-web/src/wild-core/src/primitive/geometry/` 新增一个文件。builder 接收参数并返回 `MeshData[]`：

```ts
export interface ElementBuilderRegistration {
  type: string;
  status: EngineCapability['status'];
  description: string;
  build: (element: any) => MeshData[];
}
```

实现应满足：

- 同一参数始终产生相同网格；
- 顶点、索引不能出现 `NaN` 或越界；
- 尽量提供 normals 和 UV；
- transform 与材质引用放在 `MeshData`，不要直接创建 Three.js 对象；
- 无法实现时抛出明确错误，不能返回一个看似成功的空几何。

当前 `primitive` builder 的入口可以作为参考：

```ts
export function buildPrimitive(params: PrimitiveParams): MeshData[] {
  let buffers: GeometryBuffers;
  switch (params.shape) {
    case 'box':
      buffers = buildBox(params);
      break;
    case 'sphere':
      buffers = buildSphere(params);
      break;
    case 'cylinder':
      buffers = buildCylinder(params);
      break;
    case 'profile_sweep':
      buffers = buildProfileSweep(params);
      break;
    default:
      throw new Error(`Unsupported primitive shape: ${(params as any).shape}`);
  }

  return [{ ...buffers, transform, materialRef }];
}
```

### 4.3 从 geometry 目录导出

在 `wild-web/src/wild-core/src/primitive/geometry/index.ts` 导出新 builder。

### 4.4 注册能力

在 `wild-web/src/wild-core/src/primitive/registry.ts` 静态注册：

```ts
registerElementBuilder({
  type: 'lathe',
  status: 'experimental',
  description: '绕轴旋转二维轮廓',
  build: buildLathe,
});
```

状态含义：

- `stable`：结构与主要参数已稳定；
- `partial`：可用，但部分枚举或细节仍会降级；
- `experimental`：可以试验，不应由 Agent 默认生成。

`getEngineCapabilities()` 会自动从 registry 生成能力清单。未知类型会由重建入口返回 `UNSUPPORTED_ELEMENT_TYPE`，builder 抛错会返回 `ELEMENT_BUILD_FAILED`。

### 4.5 同步 Schema、前端类型和后端校验

至少同步以下位置：

1. `wild-web/wild-lang/schema.json`；
2. `wild-web/src/wild-core/types.ts`；
3. `wild-web/src/types/blueprint.ts`；
4. `wild-server/app/tools/spatial_tools.py`；
5. `wild-server/storage/knowledge_base/BLUEPRINT-SPEC-MINIMAL.md`；
6. `wild-web/wild-lang/PRIMITIVES.md`。

如果增加的是向后兼容的新 type 或字段，使用新的 WILD 小版本；已有 v1.0/v1.1 字段不能改义。

### 4.6 添加端到端样例

在 `wild-web/lantu/` 增加最小 `.wild`：

- 至少有一个正常参数样例；
- 参数变化能够产生可观察的几何变化；
- 重建后 mesh 数量大于 0；
- 包围盒有限；
- 索引不越界；
- experimental/错误能力必须产生预期 diagnostics。

完成后在 `wild-web` 目录执行：

```bash
npm run check:core
```

该脚本位于 `wild-web/scripts/check-wild-core.mjs`，会验证全部 `lantu/*.wild` 的完整 Schema、重建错误、有限包围盒、顶点/法线/UV 长度和索引范围。

## 5. 扩展材质，而不是扩展几何

如果物体轮廓已经正确，只是“看起来不真实”，优先扩展材质：

```json
{
  "baseColor": [1, 1, 1],
  "roughness": 0.7,
  "metallic": 0,
  "albedo": 1,
  "lightingCondition": "D65_noon",
  "textures": {
    "baseColor": {
      "encoding": "base64",
      "mimeType": "image/png",
      "data": "<base64>"
    },
    "normal": {
      "encoding": "base64",
      "mimeType": "image/png",
      "data": "<base64>"
    }
  },
  "normalScale": 0.8,
  "uvScale": [2, 2]
}
```

Core 会传递 UV 和纹理参数，`materialAdapter.ts` 将其映射到 Three.js 的 base color、normal、roughness、metalness 和 AO 通道。基础色纹理和顶点色存在时，适配层不会再次乘一遍 `baseColor`，避免画面整体偏暗。

## 6. Diagnostics 是扩展协议的一部分

`reconstructEntity()` 现在返回：

```ts
interface EngineDiagnostic {
  level: 'info' | 'warning' | 'error';
  code: string;
  message: string;
  elementId?: string;
  elementType?: string;
}
```

扩展时不要只写 `console.warn`。可恢复的降级用 warning，构件无法生成用 error。编辑器会显示诊断数量，适配层会记录错误级诊断。

当前常见 code：

| code | 含义 |
|---|---|
| `UNSUPPORTED_ELEMENT_TYPE` | registry 中没有该 type |
| `PARTIAL_CAPABILITY` | 构件可用，但能力尚未完全实现 |
| `ELEMENT_BUILD_FAILED` | builder 抛错 |
| `EMPTY_GEOMETRY` | builder 没有产生网格 |
| `TEMPLATE_NOT_FOUND` | instance 引用不存在的模板 |
| `PLACEMENT_TEMPLATE_NOT_FOUND` | placement 模板不存在 |
| `PLACEMENT_PARENT_NOT_FOUND` | placement 父构件不存在 |
| `PLACEMENT_SURFACE_UNSUPPORTED` | 当前 resolver 不支持该表面 |

## 7. 性能扩展注意事项

当前 Three.js 适配层会把三个及以上、几何与材质签名一致的非交互网格合并为 `InstancedMesh`。因此重复柱、瓦片和装饰应复用同一参数与材质，不要人为制造细微但无意义的几何差异。

后续若做局部重建、LOD 或 Worker，应继续保持以下边界：

- Core 输出与 Three.js 无关的 `MeshData`；
- 缓存键必须包含会改变几何或材质的参数；
- 局部重建不能绕开空间关系解析；
- 交互构件需要保留 element ID 与 instance ID 的映射；
- 优化前先记录构建耗时、顶点数和 draw call，避免凭感觉改。

## 8. GLB 导出预留边界

本轮没有实现 GLB 导出，也没有增加 GLB 引用字段。

未来导出器建议作为 `ReconstructedEntity -> GLB` 的独立适配层：

```text
.wild
  -> reconstructEntity()
  -> ReconstructedEntity
  -> GLB exporter
```

这样 GLB 只是确定性重建结果的一种发布格式，不会反向污染 WILD builder。导出时需要处理坐标、材质纹理、实例展开或保留、资源嵌入和 element ID 元数据；这些应在真正开始 GLB 功能时单独设计和测试。

## 9. 提交前检查清单

- [ ] 这是“新物件”还是“新数学能力”？
- [ ] 能否先用 primitive、模板和现有构件组合？
- [ ] 类型、Schema、后端校验、Agent 规范是否同步？
- [ ] builder 是否输出有效 indices、normals、UV 和 transform？
- [ ] 不支持或失败时是否返回 diagnostics？
- [ ] capability 状态是否诚实标为 stable / partial / experimental？
- [ ] 是否有一个最小 `.wild` 端到端样例？
- [ ] v1.0 与已有 v1.1 样例是否仍能重建？
- [ ] 是否避免把 Three.js、动态代码或 GLB 导出逻辑放进 Core builder？
