# WILD 程序化建筑材质扩展方案

## 1. 文档目的

本文用于指导 WILD 在不依赖外部图片贴图的情况下，扩展可复用的程序化建筑材质。第一阶段以红砖墙为最小可交付版本，支持砖块错缝、砖缝凹陷、自然色差、风化、盐碱和潮湿痕迹；后续再复用同一架构扩展混凝土、抹灰、石材、木材和金属。

这项扩展属于 `renderer_only` 能力：Blueprint 继续描述材质意图和参数，Wild Core 继续负责确定性几何与材质参数传递，Three.js renderer 负责把参数编译成 GPU Shader。不得为某栋建筑、某个墙体 ID 或固定坐标增加材质特判。

## 2. 结论与技术选择

### 2.1 推荐方案

第一版使用 `THREE.MeshStandardMaterial` 的 `onBeforeCompile` 扩展程序化 Shader，保留 Three.js 原有 PBR 光照、阴影、雾和色调映射，只替换或调制以下通道：

- 基础颜色 `baseColor`；
- 粗糙度 `roughness`；
- 表面法线 `normal`；
- 可选的环境遮蔽近似；
- 风化、盐碱和潮湿遮罩。

不建议第一版直接使用完整 `ShaderMaterial`，否则需要自行维护 Three.js 的灯光、阴影、透明度、雾、环境贴图和版本兼容。CanvasTexture 可作为不支持自定义 Shader 时的降级方案或编辑器预览方案，但不作为最终高质量实现。

### 2.2 “不用贴图”的准确含义

本方案不读取 PNG/JPEG/WebP 等外部纹理图片，但 GPU 仍会根据 UV、世界/局部坐标和数学函数计算表面图案。这称为程序化纹理或程序化材质，不等于没有纹理细节。

### 2.3 第一版不做的内容

- 不为每块砖创建独立 Mesh；
- 不修改墙体结构、碰撞或门窗洞口；
- 不做真正改变物体轮廓的顶点位移；
- 不在 Agent 中生成 GLSL 代码；
- 不同时实现全部材质族；
- 不将随机结果与帧时间绑定。

普通墙面在第一版使用程序化法线表现砖缝凹陷。只有未来需要近距离侧视轮廓或砖块缺角时，才评估视差遮蔽映射或局部真实几何。

## 3. 现状与扩展边界

当前项目已经具备以下基础：

- `wild-core` 为直墙和曲墙生成按米展开的语义 UV；
- `MaterialDef` 支持基础色、粗糙度、金属度、玻璃、法线强度、UV 比例和图片 PBR 通道；
- `wild-core/src/primitive/materials/apply.ts` 把 `MaterialDef` 转换为 renderer 使用的 `MaterialParams`；
- `renderer/materialAdapter.ts` 负责创建和缓存 `MeshStandardMaterial`/`MeshPhysicalMaterial`；
- `check-rendering-pipeline.mjs` 已覆盖物理材质和 UV 渲染回归。

本次扩展应沿现有数据流增加 `procedural` 字段：

```text
Blueprint MaterialDef
    -> 后端 Schema/validator
    -> Wild Core MaterialParams
    -> renderer MaterialCache
    -> procedural material compiler
    -> MeshStandardMaterial.onBeforeCompile
```

Blueprint 是事实源。AI 只能选择预定义材质族并填写受控参数，不能输出 Shader 源码。

## 4. Blueprint 协议草案

### 4.1 顶层结构

在 `MaterialDef` 和 `MaterialParams` 中增加可选的 `procedural` 字段。第一阶段只接受 `type: "brick"`：

```ts
interface ProceduralBrickMaterial {
  type: 'brick'
  seed?: number
  brickSize?: [number, number]
  mortarWidth?: number
  mortarDepth?: number
  bond?: 'running' | 'stack'
  secondaryColor?: [number, number, number]
  colorVariation?: number
  roughnessVariation?: number
  edgeWear?: number
  weathering?: {
    amount?: number
    scale?: number
    efflorescence?: number
    verticalStreaks?: number
    baseDampness?: number
  }
}
```

字段单位与范围：

| 字段                         | 单位/范围         | 默认值          | 说明                          |
| ---------------------------- | ----------------- | --------------- | ----------------------------- |
| `seed`                       | 0–2147483647 整数 | `1`             | 保证同一 Blueprint 重建一致   |
| `brickSize`                  | 米，两个正数      | `[0.24, 0.065]` | 单块砖可见面宽和高            |
| `mortarWidth`                | 米，`0.002–0.03`  | `0.01`          | 砖缝宽度                      |
| `mortarDepth`                | 米，`0–0.02`      | `0.006`         | 仅用于法线/视差观感，不改结构 |
| `bond`                       | 枚举              | `running`       | 顺砌错缝或直缝                |
| `secondaryColor`             | 三个 0–1 数值     | 从基础色推导    | 砖块自然色差的另一端颜色      |
| `colorVariation`             | 0–1               | `0.12`          | 砖块间和砖面内颜色变化        |
| `roughnessVariation`         | 0–1               | `0.12`          | 粗糙度变化强度                |
| `edgeWear`                   | 0–1               | `0.05`          | 砖边轻微磨损，不改变轮廓      |
| `weathering.amount`          | 0–1               | `0`             | 总风化强度                    |
| `weathering.scale`           | 米尺度，正数      | `1.8`           | 风化斑块的大致尺寸            |
| `weathering.efflorescence`   | 0–1               | `0`             | 盐碱泛白强度                  |
| `weathering.verticalStreaks` | 0–1               | `0`             | 雨水竖向流痕                  |
| `weathering.baseDampness`    | 0–1               | `0`             | 靠近墙脚的潮湿强度            |

`brickSize` 使用真实米制尺寸，不应再受图片纹理式的 `uvScale` 控制。第一阶段若 `procedural` 与图片 `textures`/`textureSet` 同时存在，应由 validator 拒绝，避免不明确的叠加语义。未来若确实需要混合，再单独设计显式的组合规则。

### 4.2 红砖墙示例

```json
{
  "materials": {
    "aged_red_brick": {
      "baseColor": [0.52, 0.11, 0.055],
      "roughness": 0.84,
      "metallic": 0,
      "albedo": 1,
      "lightingCondition": "D65_noon",
      "side": "front",
      "procedural": {
        "type": "brick",
        "seed": 42,
        "brickSize": [0.24, 0.065],
        "mortarWidth": 0.01,
        "mortarDepth": 0.006,
        "bond": "running",
        "secondaryColor": [0.68, 0.19, 0.08],
        "colorVariation": 0.14,
        "roughnessVariation": 0.16,
        "edgeWear": 0.06,
        "weathering": {
          "amount": 0.28,
          "scale": 1.8,
          "efflorescence": 0.22,
          "verticalStreaks": 0.14,
          "baseDampness": 0.1
        }
      }
    }
  }
}
```

## 5. 红砖 Shader 算法

### 5.1 坐标输入

墙体正面应使用按米展开的 UV：`u` 表示沿墙长度，`v` 表示高度。砖块尺寸直接除以米制 UV，因此不同长度和高度的墙会保持同样的砖尺度。

需要注意：直墙带门窗洞口时仍应确认 `boxWithHoles` 输出的表面 UV 与普通直墙一致；曲墙已有按弧长展开的 UV。若墙体局部 UV 不能保证连续，应先修复通用 UV 契约，不能在 Shader 中按墙 ID 修正。

不要直接使用绝对世界坐标生成砖格，否则墙体旋转后砖方向可能改变，分层墙体也可能出现不可控跳变。风化的大尺度遮罩可以混入稳定的局部/世界高度，但砖块排列必须依赖墙面语义坐标。

### 5.2 错缝砖块

伪代码：

```glsl
vec2 brickUv = surfaceMeters / brickSize;
float row = floor(brickUv.y);
if (bond == RUNNING && mod(row, 2.0) > 0.5) {
  brickUv.x += 0.5;
}
vec2 cell = floor(brickUv);
vec2 withinBrick = fract(brickUv);
```

砖块随机值必须来自 `cell + seed` 的确定性哈希，而不是 `Math.random()` 或时间：

```glsl
float brickRandom = hash21(cell + float(seed));
```

这样相同参数每次重建结果一致，材质也能在缓存中安全复用。

### 5.3 砖缝遮罩与凹陷

按砖块内坐标计算到四边的距离：

```glsl
vec2 edgeDistance = min(withinBrick, 1.0 - withinBrick) * brickSize;
float distanceToEdge = min(edgeDistance.x, edgeDistance.y);
float mortarMask = 1.0 - smoothstep(
  mortarWidth * 0.45,
  mortarWidth * 0.55,
  distanceToEdge
);
```

`mortarMask` 用于：

- 把基础色混合到砂浆颜色；
- 提高砂浆粗糙度；
- 形成砖缝高度函数；
- 轻微降低砂浆明度。

第一版不能依赖顶点位移，因为普通墙面没有足够顶点表现毫米级砖缝。应从高度函数的屏幕空间导数计算扰动法线，或者采用 Three.js 常见的 derivative normal perturbation 方法。`mortarDepth` 只调节法线强度，不修改墙体碰撞和包围盒。

### 5.4 自然砖色

自然感需要至少两层变化：

1. 每块砖稳定变化：由 `cell + seed` 决定整块砖略偏红、偏暗或偏黄；
2. 砖面内部细噪声：频率更高、强度更低，用于表现烧制颗粒。

不要把高强度白噪声直接加在最终颜色上，否则会出现电视雪花。建议使用 2–4 层 fBm 噪声，并限制颜色变化：

```glsl
float cellTone = hash21(cell + seedValue);
float surfaceNoise = fbm(surfaceMeters * 18.0 + seedValue);
float variation = (cellTone - 0.5) * colorVariation
                + (surfaceNoise - 0.5) * colorVariation * 0.35;
```

### 5.5 风化

风化使用低频连续噪声，作用于整面墙，不应让每块砖完全独立：

```glsl
float weatherNoise = fbm(surfaceMeters / weatheringScale + seedValue);
float weatherMask = smoothstep(0.42, 0.78, weatherNoise) * weatheringAmount;
```

风化遮罩可以：

- 将颜色轻微向灰白或褐灰偏移；
- 增加粗糙度；
- 减弱砖块饱和度；
- 与边缘磨损做有限叠加。

### 5.6 盐碱、流痕和墙脚潮湿

盐碱不能等同于随机白斑，应组合三个具有物理含义的遮罩：

```text
盐碱 = 低频噪声 × 墙脚高度衰减 × 潮湿来源
流痕 = 窄带横向噪声 × 纵向连续性
墙脚潮湿 = 1 - smoothstep(墙脚起点, 影响高度, 局部高度)
```

推荐效果：

- 盐碱区域颜色向低饱和暖白色混合；
- 盐碱区域粗糙度提高；
- 墙脚潮湿区域颜色略暗、粗糙度可适当下降；
- 竖向流痕沿高度连续，不要形成横向斑马纹；
- 三种效果均受 `weathering.amount` 总开关控制。

第一版可以使用墙体局部 `v` 作为墙脚高度。以后如果要让多层模板形成整栋楼连续流痕，需要为 Mesh 额外传入稳定的建筑表面坐标或世界高度，不能仅依赖每层从零开始的局部 UV。

## 6. 代码落点与职责

### 6.1 类型协议

同步修改以下类型，保持字段一致：

- `wild-web/src/wild-core/types.ts`：`MaterialDef`；
- `wild-web/src/wild-core/src/primitive/types.ts`：Core 内部 `MaterialDef/MaterialParams`；
- `wild-web/src/types/blueprint.ts`：前端 Blueprint 类型；
- `wild-web/src/types/scene.ts`：若存在独立的重建材质类型，也要同步增加；
- 后端 Blueprint Schema/校验逻辑。

建议把 `ProceduralMaterial` 定义为判别联合，后续按类型扩展：

```ts
type ProceduralMaterial = ProceduralBrickMaterial
  | ProceduralConcreteMaterial
  | ProceduralPlasterMaterial
```

第一版联合中只包含 `brick`，不要提前创建没有实现的空类型。

### 6.2 Core 参数传递

在 `wild-core/src/primitive/materials/apply.ts` 中把经过归一化的 `procedural` 原样、只读地传给 `MaterialParams`。Core 不生成噪声图片，也不执行 Shader；它只负责协议归一化和参数闭合。

必须深拷贝或以不可变方式使用参数，避免 renderer 修改 Blueprint 中的源对象。

### 6.3 Renderer

建议新增：

```text
wild-web/src/renderer/proceduralMaterials/
  index.ts
  brickMaterial.ts
  noise.glsl.ts
  types.ts
```

职责划分：

- `index.ts`：根据 `procedural.type` 分派，不认识的类型安全回退到普通 PBR；
- `brickMaterial.ts`：注册 uniform、插入砖块/风化 Shader 片段；
- `noise.glsl.ts`：共享确定性 hash/fBm，实现保持短小；
- `types.ts`：renderer 内部经过默认值归一化后的参数。

`materialAdapter.ts` 仍是唯一材质创建入口。创建标准材质并设置基础 PBR 参数后，再调用类似函数：

```ts
applyProceduralMaterial(material, normalizedProcedural)
```

使用 `material.onBeforeCompile` 注入代码时，还必须设置 `material.customProgramCacheKey()`，其结果至少包含：

- 程序化材质类型；
- 会改变 Shader 分支结构的功能开关；
- Shader 实现版本。

数值参数应尽量使用 uniform，不要全部拼进 Shader 字符串，否则每组参数都会编译一套新 GPU Program。

### 6.4 材质缓存

当前 `MaterialCache` 使用 `materialSignature(params)` 区分材质实例。扩展时必须把完整、规范化后的 `procedural` 参数加入签名，否则修改砖尺寸或风化强度后可能继续复用旧材质。

材质缓存规则：

- 参数完全相同的程序化材质复用一个 Three.js Material；
- 不同参数可以复用 GPU Program，但使用不同 uniform/Material 实例；
- 场景卸载时继续由现有缓存统一 `dispose()`；
- 不在每帧创建材质、纹理或 uniform 对象。

### 6.5 后端校验

在 `wild-server/app/utils/blueprint_parser.py` 的材质校验处增加通用规则：

- `procedural` 必须是对象；
- `type` 第一版只能为 `brick`；
- 所有数值必须有限，拒绝布尔值、NaN 和无穷大；
- 0–1 参数必须在范围内；
- 米制尺寸必须为正并处于合理上限内；
- `mortarWidth < min(brickSize) / 2`；
- `mortarDepth` 不得大于合理的视觉深度；
- `seed` 必须为整数；
- `procedural` 与 `textureSet/textures/embeddedImage` 第一版互斥；
- 未知字段按现有 Schema 策略处理，不允许把任意 GLSL 字符串传入前端。

参数越界应产生明确的字段路径，例如：

```text
材质 'aged_red_brick'.procedural.mortarWidth 必须小于砖块最短边的一半
```

## 7. AI 与编辑器交互

Agent 只能输出受控参数。例如用户说“生成有轻微盐碱的旧红砖墙”，材质规划应选择 `procedural.type = brick`，再给出有限参数，不生成代码、不创建图片。

建议第一阶段提供三个内置预设，预设只是一组参数，不是三套 Shader：

| 预设         | 典型参数                           |
| ------------ | ---------------------------------- |
| 新红砖       | 低色差、无盐碱、轻微砖缝           |
| 自然旧红砖   | 中等风化、少量流痕和边缘磨损       |
| 潮湿盐碱红砖 | 墙脚潮湿与盐碱较明显，但受上限约束 |

编辑器参数建议分组：

- 砖规格：宽、高、砖缝宽、砖缝深、砌筑方式；
- 表面变化：辅助色、色差、粗糙度变化、边缘磨损；
- 环境老化：风化、尺度、盐碱、流痕、墙脚潮湿；
- 随机种子：默认隐藏在高级设置中。

所有调节应走现有材质 Patch/历史记录体系，支持撤销和重做。不要让面板直接修改 Three.js Material；事实源必须仍是 Blueprint。

## 8. 性能与质量分级

### 8.1 MVP 性能策略

- 每像素最多使用约 3–4 个 fBm octave；
- 砖格计算使用简单 `floor/fract/smoothstep`；
- 盐碱、风化和流痕共享基础噪声，避免重复计算；
- 禁止循环次数由 Blueprint 动态决定；
- 不新增每帧 CPU 工作；
- 不为每面墙创建独立 Shader 源码；
- 阴影通道继续使用 Three.js 标准实现。

### 8.2 质量档位

建议 renderer 根据全局质量档位设置一个统一 define/uniform，而不是写入每栋建筑：

| 档位     | 启用内容                       |
| -------- | ------------------------------ |
| `low`    | 砖格颜色、砂浆色、低频风化     |
| `medium` | 增加粗糙度变化与程序化法线     |
| `high`   | 增加更细噪声、流痕和更精确法线 |

第一版不必做自动距离 LOD；先记录 GPU 帧耗，再决定是否需要按屏幕占比关闭细节。若未来增加 LOD，切换应有滞后区间，避免相机移动时闪烁。

### 8.3 性能预算建议

以同一测试场景、同一相机和同一设备比较：

- 程序化红砖相对普通标准材质的 GPU 帧耗增幅目标不超过 20%；
- 材质参数变化不得触发场景几何重建；
- 相同参数的 100 面墙不得产生 100 套不同 GPU Program；
- 连续观察 60 秒不应持续增加材质和 WebGL Program 数量。

预算是验收目标，不是静默降质的理由；超过预算时应先使用性能分析工具确认瓶颈。

## 9. 测试计划

### 9.1 后端 Schema 测试

新增或扩展 Blueprint 材质测试，至少覆盖：

- 合法红砖参数通过；
- 缺省可选参数通过并由前端/Core 归一化；
- 非法 `type` 被拒绝；
- 负砖尺寸、过宽砖缝、非法颜色、NaN、布尔数值被拒绝；
- 图片纹理与程序化材质同时存在时被拒绝；
- 任意 Shader 字符串或未知可执行字段不能进入协议。

### 9.2 Core 测试

扩展 `check-wild-core.mjs`：

- `procedural` 从 Blueprint 完整传递到 `MaterialParams`；
- Core 不修改源 Blueprint；
- 直墙、带洞直墙和曲墙都具有稳定的米制 UV；
- 不同尺寸墙体的同一 UV 米坐标对应相同砖尺度。

### 9.3 Renderer 测试

扩展 `check-rendering-pipeline.mjs`：

- `type: brick` 创建标准 PBR 材质并安装程序化 Shader；
- `customProgramCacheKey` 区分普通材质与砖材质；
- 参数变化进入 `materialSignature`；
- 相同结构、不同数值参数不产生不同 Shader 源码；
- 不支持的类型安全回退并产生开发期诊断；
- 材质销毁路径仍然有效。

Shader 片段函数应尽可能拆出可在 JavaScript 中复算的纯函数，单测错缝行、砖缝遮罩和参数归一化。最终视觉仍需浏览器截图验收。

### 9.4 视觉回归场景

建立一个最小测试场景，而不是复制整栋建筑：

- 一面 6m × 3m 直墙；
- 一面带门窗洞口的墙；
- 一段曲墙；
- 同材质的两层模板墙；
- 斜向自然光和近/中/远三个固定相机位。

固定 `seed` 和灯光，保存基准截图。重点检查：

- 砖的物理尺寸一致；
- 奇偶行错缝正确；
- 门窗周围纹理没有拉伸或突然换向；
- 曲墙沿弧长连续；
- 风化不是均匀蒙灰；
- 盐碱集中但不过曝；
- 近景砖缝有光照凹陷，远景不闪烁；
- 相邻共面墙的接缝是否可接受。

## 10. 实施顺序

### 阶段 A：协议和门禁

1. 定义 `ProceduralBrickMaterial` 判别类型。
2. 同步前端、Core 和后端协议。
3. 增加参数默认值、范围校验和互斥规则。
4. 编写 Schema/Core 传递测试。

完成标准：合法示例可以保存、解析和重建，非法参数在进入 renderer 前被拒绝。

### 阶段 B：最小红砖 Shader

1. 新增程序化材质分派器。
2. 实现米制砖格、错缝和砂浆遮罩。
3. 调制基础颜色和粗糙度。
4. 接入 `MaterialCache`、签名和 Program cache key。
5. 完成渲染自动测试。

完成标准：不使用图片即可在不同尺寸墙体上看到比例一致的红砖和砂浆。

### 阶段 C：凹陷与自然老化

1. 从砖缝高度函数生成程序化法线。
2. 加入砖块色差和表面细噪声。
3. 加入低频风化、盐碱、流痕和墙脚潮湿。
4. 调整强度上限，避免迷彩和过曝。
5. 完成固定截图视觉验收。

完成标准：斜光下砖缝有稳定凹陷，风化与盐碱有区域逻辑，移动相机时不游动。

### 阶段 D：编辑与 AI

1. 增加红砖材质预设和参数面板。
2. 通过 ScenePatch 修改并支持撤销/重做。
3. 限制 Agent 只能输出协议字段和合法范围。
4. 增加自然语言到预设/参数的测试。

完成标准：用户可复用程序化材质，AI 可选择和调参，但不能注入代码。

### 阶段 E：性能验收

1. 比较普通材质与程序化材质 GPU 帧耗。
2. 检查 Material、Program 数量和销毁。
3. 根据数据决定是否加入质量档位或距离 LOD。
4. 运行完整前后端回归。

## 11. 实施记录（2026-08-13）

- [x] 创建前端、Core 和 renderer 共享的判别协议类型；
- [x] 后端 validator 拒绝越界值、图片混用和 Shader 字符串；
- [x] Core 不修改源 Blueprint，并传递规范化 `procedural`；
- [x] renderer 使用独立的 `proceduralMaterials` 分派目录；
- [x] `materialSignature` 包含完整程序化参数；
- [x] `customProgramCacheKey` 只包含 Shader 类型和实现版本，不包含数值 uniform；
- [x] 完成米制砖格、错缝、砂浆颜色与粗糙度；
- [x] 完成砖缝程序化法线；
- [x] 完成连续风化、盐碱、竖向流痕和墙脚潮湿；
- [x] 增加三套内置预设、自定义参数面板、本机复用和多选对象 Patch 应用；
- [x] 材质规划 Agent 可选择受控红砖参数，服务端再次白名单化；
- [x] 运行 `npm run check:core`、`npm run check:compiler`、`npm run check:rendering` 和 `npm run build`；
- [x] 后端运行材质定向测试与完整测试；
- [x] 把协议补充进 `WILD_BLUEPRINT_SPEC.md`，把测试说明补充进 `TESTING.md`；
- [ ] 用直墙、带洞墙、曲墙和多层模板完成固定相机视觉基准；
- [ ] 在目标部署显卡上记录 GPU 帧耗、Material 和 Program 数量，决定是否需要距离 LOD。

当前完成范围是阶段 A–D 的 MVP 与自动化门禁。最后两项属于需要真实浏览器/WebGL 环境和目标硬件的视觉、性能验收，不应以静态检查结果代替。

## 12. 验收标准

功能验收：

- 红砖墙不依赖任何图片资产；
- 砖宽、高和砖缝按米设置，在不同墙体上比例一致；
- 支持错缝、颜色变化、粗糙度变化、砖缝法线、风化、盐碱、流痕和墙脚潮湿；
- 固定 seed 后重载结果一致；
- 用户可以保存、复用和调节材质；
- 用户显式参数不会被默认值覆盖。

架构验收：

- 没有建筑 ID、墙 ID 或固定坐标特判；
- AI 不生成 GLSL，只生成受控参数；
- Blueprint 结构和碰撞不因视觉材质改变；
- 新材质族通过统一分派器扩展；
- 非法参数在渲染前被拒绝；
- 程序化材质参数参与缓存签名并可正确释放。

视觉验收：

- 砖块不是纯色网格，也不是高频随机噪点；
- 砖缝在斜光下有凹陷感，但轮廓和碰撞保持不变；
- 风化是连续的大尺度变化；
- 盐碱和潮湿具有墙脚/流痕逻辑；
- 门窗洞口和曲墙上不存在明显拉伸、跳变或游动；
- 远距离没有摩尔纹、闪烁或明显性能下降。

## 13. 后续材质族

红砖完成后，只在出现明确需求和回归样本时增加新的有限材质族：

| 类型   | 可复用核心函数        | 新增专属逻辑         |
| ------ | --------------------- | -------------------- |
| 混凝土 | fBm、流痕、粗糙度变化 | 气孔、模板拼缝、色斑 |
| 抹灰   | fBm、风化、墙脚潮湿   | 刮抹方向、细颗粒     |
| 石材   | hash、粗糙度和法线    | 板块分缝、矿脉       |
| 木材   | hash、颜色变化        | 年轮/木纹方向        |
| 金属   | 粗糙度变化、流痕      | 拉丝、氧化、锈蚀     |

共享噪声、缓存、验证和 Shader 注入基础设施只能保留一套。新类型增加的是有限的图案函数与参数协议，而不是复制完整材质系统。
