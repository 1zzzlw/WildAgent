# WILD 全局材质世界架构

> 文档分类：材质与表面系统。返回 [正式文档入口](../README.md)。

> 程序化材质、PBR 材质包、Shader 光影包、多蓝图隔离与去中心化共享的技术论证和实施规划

## 1. 文档目的

本文讨论一个面向长期世界构建的材质与光影架构：每份蓝图的几何和运行状态相互隔离，而材质定义、贴图资产、光影配置和 GPU 资源可以在整个世界中安全共享。

本文不是要求立即重写渲染引擎，而是先回答以下问题：

1. 程序化 Shader 能否作为世界的默认材质来源？
2. PBR 与 Shader 到底是什么关系，各自适合解决什么问题？
3. 是否应该为每种材质单独编写 Shader？
4. PBR 材质包和 Shader 光影包应该采用什么格式、怎样配合？
5. 同时渲染多份 `.wild` 蓝图时，如何做到几何隔离、材质全局共享？
6. 当前项目需要修改哪些边界，应该按什么顺序实施？

## 2. 结论先行

你的总体方向是成立的，但需要校正一个关键概念：**Shader 和 PBR 不是互斥的两套渲染引擎。**

- Shader 是 GPU 上执行渲染计算的程序。
- PBR 是一套基于物理规律近似光照和表面反射的材质模型，底层仍然由 Shader 实现。
- 真正应该区分的是“表面数据从哪里来”：常量参数、程序计算、贴图采样，或者三者混合。

因此，推荐把系统定义成一套统一的 PBR 材质管线，支持三种表面来源：

| 来源 | 适用场景 | 主要成本 |
| --- | --- | --- |
| 程序化材质 | 默认世界材质、大面积表面、可参数化变化 | GPU 算术、Shader 变体 |
| 贴图材质 | 写实细节、扫描资产、品牌或人工制作表面 | 下载、显存、纹理带宽 |
| 混合材质 | 贴图负责真实底色，程序负责风化、积尘、雨痕等变化 | 两类成本的受控组合 |

最终推荐方案是：

> **有限的程序化材质族作为默认世界材质；PBR 资产包提供高精度替换；混合材质负责环境变化；所有蓝图只引用全局材质，运行时通过内容哈希共享 GPU 资源。**

这里的“有限”非常重要。系统不应为每个红砖、旧红砖、深红砖分别编写代码，而应编写少量稳定的材质族，再用配方参数生成变化。

从用户和产品角度，可以采用类似《我的世界》的双包模型：

- **PBR 材质包（`.wildmat`）**：决定砖、木材、玻璃等表面“长什么样”。
- **Shader 光影包（暂定 `.wildlook`）**：决定整个世界“怎样被照亮和表现”，包括阴影、天气、天空、雾、曝光和后处理。

默认情况下不要求安装 PBR 材质包，而是使用“内置程序化材质库 + 内置默认光影包”。导入 PBR 材质包后，只替换表面数据来源，仍然接入当前光影包。切换光影包时，程序化材质和 PBR 材质都应同时响应。

这个双包模型是产品概念；引擎内部仍需拆成“表面材质系统、光影功能系统、世界环境状态”三层，避免把所有 GPU 代码塞进同一个模块。

## 3. 概念辨析

### 3.1 Shader 是执行方式，不是材质分类本身

Three.js 中的 `MeshStandardMaterial` 和 `MeshPhysicalMaterial` 本身也会生成并执行 Shader。当前程序化砖材质是在标准 PBR 光照基础上增加程序计算，不代表项目增加了一个完全独立的渲染引擎。

更准确的结构是：

```text
渲染器（Three.js / WebGL / 未来可迁移 WebGPU）
└─ 统一 PBR 光照模型
   ├─ 常量参数来源
   ├─ 程序化 Shader 表面来源
   ├─ PBR 贴图表面来源
   └─ 贴图 + 程序化遮罩的混合来源
```

### 3.2 程序化材质不一定比 PBR 贴图更吃性能

两者消耗的是不同资源：

- 程序化材质减少文件体积、下载量和纹理显存，但会增加 GPU 算术指令。
- PBR 贴图减少复杂程序计算，但会增加纹理采样、显存占用和网络传输。
- 移动设备可能更怕复杂 Shader；显存较小的设备也可能更怕大量高分辨率贴图。

所以不能简单定义为“简单场景用 Shader，复杂场景用 PBR”，而应根据目标平台、观察距离、表面面积和细节要求选择。

### 3.3 不应该为每个材质外观写一份 Shader

建议只为具有不同结构规律的材料编写材质族，例如：

1. 砌体：砖、砌块、石材拼缝。
2. 无机连续面：混凝土、灰泥、砂浆、涂料。
3. 木材：木纹、年轮方向、清漆层。
4. 金属：拉丝、锈蚀、氧化、涂层。
5. 玻璃：透射、粗糙、厚度、污渍。
6. 地面：土、砂、碎石、草地混合。

“红砖”“暗红旧砖”“浅灰砂浆砖”都应属于同一个砌体族，只是参数、种子和质量等级不同。只有当一种材料具有现有材质族无法表达的结构规律时，才新增代码。

这与建筑修复的原则一致：新增的是有限的共性能力，而不是针对单个建筑或单个材质打补丁。

### 3.4 产品上是两种包，引擎内是两类 Shader

“Shader 光影包”这个名称适合用户理解，但引擎内部必须区分两类 Shader：

1. **表面生成 Shader**：生成砖缝、木纹、混凝土噪声等，属于程序化材质系统。
2. **全局光影 Shader**：处理灯光、阴影、湿润、积雪、雾、天空和后处理，属于光影功能系统。

两者都使用 GPU，但复用边界不同。表面生成实现按有限材质族组织；全局光影实现按可复用功能组织。PBR 贴图和程序化表面最终都进入同一套全局光影计算。

天气本身不是某个材质包、Shader 包或建筑 Blueprint 的私有数据，而是世界状态。例如 `rain`、`wetness`、`snow`、`dust`、`fog`、`timeOfDay`、`cloudCoverage` 和 `wind` 由世界统一提供，光影功能读取它们，材质只声明自己如何响应。

## 4. 方案辩论

### 4.1 观点 A：程序化 Shader 作为默认世界材质

支持理由：

- 蓝图可以只保存少量参数，不必重复携带贴图。
- 同一材质族可以通过颜色、尺度、风化程度和随机种子形成大量变化。
- 大面积墙体不会因为贴图重复而产生明显的平铺感。
- 去中心化分发时，默认世界不依赖大量外部素材文件。
- 在材质族和算法版本固定后，同一份参数可以确定性复现。

反对理由：

- 材质族仍需人工开发和持续维护，不可能自然覆盖所有现实材料。
- Shader 分支、特性组合和动态编译容易产生变体爆炸。
- 复杂噪声、多层风化和视差可能在移动端成本过高。
- 不同 GPU 和图形后端上可能存在精度与兼容差异。
- 艺术人员无法像制作贴图一样自由表达任意细节。

判断：

> 可以将程序化材质作为默认材质库，但不能把“默认”理解为所有表面都强制启用复杂程序。默认配方必须有质量等级、性能预算和基础 PBR 回退。

### 4.2 观点 B：PBR 资产包负责高精度世界替换

支持理由：

- 能忠实保存扫描、拍摄和人工制作的高频细节。
- 工具链成熟，常见 DCC 和渲染器都理解基础 PBR 通道。
- 渲染成本相对可预测，艺术控制直接。
- 同一套贴图可以供多个蓝图和多种几何复用。

反对理由：

- 高分辨率贴图会明显增加下载、缓存和显存压力。
- 来源、授权、色彩空间和通道约定容易混乱。
- 单纯贴图仍可能出现平铺重复和环境变化不足。
- 如果蓝图保存本地绝对路径，将无法跨设备和去中心化复现。

判断：

> PBR 应作为全局资产，不应成为某一蓝图的私有附件。蓝图只保存稳定引用，导入器负责校验、转换、缓存和回退。

### 4.3 综合方案：统一材质合同

不建立“Shader 引擎”和“PBR 引擎”两个互不兼容的系统，而是建立统一材质合同：

```ts
type SurfaceSource =
  | { kind: 'constant'; params: ConstantParams }
  | { kind: 'procedural'; family: string; version: number; params: object; seed: number }
  | { kind: 'texture-set'; assetRef: string; params: TextureParams }
  | { kind: 'hybrid'; baseRef: string; overlay: ProceduralOverlay }
```

所有来源最后都编译为 Three.js 能够渲染的 PBR 材质。这样灯光、阴影、环境反射、透明、资源释放和质量降级都走同一条管线。

## 5. 推荐总体架构

```text
WorldDocument
├─ BlueprintInstance A ──> 独立几何根节点 / 变换 / 实体命名空间
├─ BlueprintInstance B ──> 独立几何根节点 / 变换 / 实体命名空间
├─ WorldMaterialTheme ───> 语义角色到全局材质的映射
├─ MaterialLibraryRefs ──> .wildmat / 内置程序化材质
├─ RenderProfileRef ─────> .wildlook / 内置默认光影包
└─ EnvironmentState ─────> 时间、天气、湿润、风、云量、雾
                         │
                         ▼
GlobalMaterialRegistry（不可变材质定义）
├─ ProceduralDefinition
├─ TextureSetDefinition
└─ HybridDefinition
                         │
                         ▼
MaterialCompiler（有限材质族 + 质量等级 + 回退）
                         │
                         ├──────────────┐
                         ▼              ▼
ShaderFeatureRegistry              RenderProfile
（湿润、雨痕、积雪等实现）           （功能组合与质量配置）
                         │
                         ▼
GpuResourceCache（纹理、程序、材质实例、引用计数）
```

### 5.1 蓝图层：只负责几何和语义

每份蓝图继续拥有自己的：

- 元素 ID 和引用关系。
- 层级、局部坐标和实例变换。
- 碰撞、交互与选择状态。
- 材质语义槽位，例如外墙主材、屋面、门框、玻璃。

蓝图不应拥有全局贴图的物理副本，也不应保存 `C:\...` 之类的机器路径。

### 5.2 世界层：负责组合多份蓝图

未来需要一个高于单份 `.wild` 的世界文档，建议采用独立扩展名或清晰的 `type: world`：

```json
{
  "meta": { "version": "1.0", "type": "world" },
  "blueprintInstances": [
    {
      "id": "tower-a",
      "blueprintRef": "wild:sha256:BLUEPRINT_HASH",
      "transform": { "position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1] }
    }
  ],
  "materialThemeRef": "theme:sha256:THEME_HASH"
}
```

同一蓝图可以被实例化多次。每个实例有独立变换和交互状态，但可共享几何缓存与材质资源。

### 5.3 全局材质注册表：共享定义，不共享可变状态

`GlobalMaterialRegistry` 的核心规则：

- 材质定义以内容哈希或全局 ID 唯一标识。
- 注册后的定义不可直接修改；编辑会产生新版本和新哈希。
- 蓝图引用材质定义，允许少量受控覆盖参数。
- 相同引用和相同覆盖参数得到相同运行时缓存键。
- 不同蓝图不能通过修改一个 Three.js 材质对象意外影响其他蓝图。

可采用“不可变基础定义 + 写时复制实例”：

```json
{
  "ref": "mat:sha256:MATERIAL_HASH",
  "overrides": {
    "tint": "#9f4434",
    "uvScale": [1.2, 1.2]
  }
}
```

覆盖参数必须进入缓存键；动画参数和临时高亮则属于实例状态，不应写回全局定义。

### 5.4 GPU 资源缓存：真正实现跨蓝图复用

仅在 JSON 中引用同一个材质 ID 并不等于已经节省显存。运行时还需要全局缓存：

```text
materialRuntimeKey = hash(materialDefinition + overrides + qualityTier + rendererBackend)
textureRuntimeKey  = hash(textureContent + colorSpace + sampler + mipPolicy)
```

缓存项至少保存：

- Three.js 材质或已编译程序。
- GPU 纹理和采样配置。
- 加载状态与错误状态。
- 引用计数。
- 最后使用时间和显存估算。

蓝图加载时增加引用，卸载时减少引用。引用为零后进入延迟回收队列，而不是立刻销毁，以避免玩家来回移动造成反复编译和上传。

### 5.5 语义材质主题：让世界可以整体换肤

蓝图直接引用某一种红砖会降低世界统一替换能力。建议增加语义槽位：

```json
{
  "materialBindings": {
    "facade.primary": "mat:sha256:RED_BRICK_HASH",
    "facade.secondary": "mat:sha256:PLASTER_HASH",
    "roof.main": "mat:sha256:ROOF_HASH",
    "opening.frame": "mat:sha256:FRAME_HASH",
    "opening.glass": "mat:sha256:GLASS_HASH"
  }
}
```

解析优先级建议为：

1. 构件实例显式覆盖。
2. 蓝图自己的材质绑定。
3. 世界主题绑定。
4. 构件类型默认材质。
5. 引擎安全回退材质。

这使同一蓝图可以在“现代社区”“荒废城市”“雪地世界”等世界主题中复用，而不需要修改几何。

## 6. 程序化材质系统设计

### 6.1 材质族是代码，配方是数据

建议使用如下边界：

```json
{
  "kind": "procedural",
  "family": "masonry.brick",
  "familyVersion": 1,
  "recipeVersion": 3,
  "seed": 18427,
  "params": {
    "baseColor": "#9e3f30",
    "brickSize": [0.24, 0.065],
    "mortarWidth": 0.012,
    "mortarDepth": 0.006,
    "weathering": 0.18,
    "saltStain": 0.08,
    "rainStreak": 0.12
  }
}
```

- `family` 决定使用哪一套稳定实现。
- `familyVersion` 绑定算法版本，保证旧世界可复现。
- `recipeVersion` 绑定参数解释方式。
- `seed` 保证随机变化可复现。
- `params` 只允许白名单字段和安全范围。

不要允许资产包直接携带任意 GLSL/WGSL 源码。去中心化环境中执行外来 Shader 会带来安全、卡死、兼容和审查问题。外部包只能声明受支持的材质族和参数。

### 6.2 控制 Shader 变体

Shader 变体数量比材质数量更危险。推荐：

- 通过少量特性位生成固定变体，例如 `USE_PARALLAX`、`USE_WEATHERING`。
- 连续变化使用 uniform 参数，不把每个数值编译成新程序。
- 对昂贵特性设置平台能力和质量等级门槛。
- 在进入可见范围前异步预热常用变体。
- 对每个材质族规定最大纹理采样数和估算指令预算。

### 6.3 质量等级与回退

每个程序化材质应提供：

| 等级 | 行为 |
| --- | --- |
| low | 基础颜色、粗糙度和简单结构，无多层噪声 |
| medium | 基础结构、少量变化和法线扰动 |
| high | 风化、雨痕、盐碱、边缘等高级细节 |
| fallback | 普通 `MeshStandardMaterial` 或低分辨率 PBR 贴图 |

质量降级应由设备能力和性能预算决定，不应要求蓝图作者重新编辑文件。

### 6.4 Shader 光影包与功能注册表

光影包不只是一个片元 Shader 文件。它还可能包含阴影质量、天空、雾、曝光、色调映射和后处理配置，因此协议名称推荐使用 `RenderProfile`，用户界面仍可显示为“Shader 光影包”。

建议扩展名暂定为 `.wildlook`。第一阶段的光影包只允许组合引擎已经注册的安全功能和参数，不允许携带任意 GLSL/WGSL 源码：

```json
{
  "format": "wild.render-profile",
  "version": "1.0",
  "name": "Default Weather Look",
  "profileId": "look:sha256:PROFILE_HASH",
  "features": {
    "lighting": "lighting.pbr.v1",
    "wetness": "surface.wetness.v1",
    "rainStreak": "surface.rain-streak.v1",
    "snow": "surface.snow.v1",
    "fog": "environment.fog.v1"
  },
  "quality": {
    "shadowTier": "medium",
    "weatherTier": "medium",
    "postProcessingTier": "low"
  },
  "renderer": {
    "minVersion": "1.2",
    "fallbackProfile": "builtin:default"
  }
}
```

内部由 `ShaderFeatureRegistry` 管理有限的通用能力：

```text
World EnvironmentState
├─ rain = 0.8
├─ wetness = 0.6
├─ timeOfDay = 18.5
└─ cloudCoverage = 0.7
             │
             ▼
RenderProfile 选择并配置功能
             │
             ▼
ShaderFeatureRegistry 提供受支持实现
├─ surface.wetness.v1
├─ surface.rain-streak.v1
├─ surface.snow.v1
└─ environment.fog.v1
             │
             ▼
MaterialCompiler 把表面数据、材质响应和光影功能组合为有限变体
```

真正的 Three.js、GLSL 或未来的 WGSL 实现属于 renderer，不属于几何 core。core 只保存 `RenderProfile`、`EnvironmentState`、功能 ID、版本、能力要求和回退协议。

## 7. PBR 材质资产包设计

### 7.1 自定义格式可以有，但不要自创压缩算法

建议自定义容器扩展名 `.wildmat`，内部采用成熟标准：

- 容器：ZIP/ZIP64，未来有需要再评估 tar.zst。
- GPU 纹理：优先 KTX2 + Basis Universal。
- 预览图：WebP 或 PNG。
- 清单：UTF-8 JSON。

自定义的是目录结构、清单协议、哈希和扩展名，不是底层压缩算法。这样可以减少安全风险、兼容成本和维护成本。

### 7.2 建议目录结构

```text
example.wildmat
├─ manifest.json
├─ preview.webp
├─ textures/
│  ├─ basecolor.ktx2
│  ├─ normal.ktx2
│  ├─ roughness.ktx2
│  ├─ metallic.ktx2
│  ├─ ao.ktx2
│  └─ emissive.ktx2
└─ license.txt
```

不要求所有通道都存在。非金属墙体通常不需要 metallic，缺失通道由清单中的常量回退。

### 7.3 清单草案

```json
{
  "format": "wild.material-package",
  "version": "1.0",
  "name": "Weathered Red Brick",
  "materialId": "mat:sha256:MATERIAL_HASH",
  "license": "CC0-1.0",
  "physicalSizeMeters": [2.0, 2.0],
  "channels": {
    "baseColor": { "path": "textures/basecolor.ktx2", "colorSpace": "srgb" },
    "normal": { "path": "textures/normal.ktx2", "colorSpace": "linear", "normalScale": 1.0 },
    "roughness": { "path": "textures/roughness.ktx2", "colorSpace": "linear", "fallback": 0.78 },
    "metallic": { "fallback": 0.0 },
    "ao": { "path": "textures/ao.ktx2", "colorSpace": "linear", "fallback": 1.0 }
  },
  "environmentResponse": {
    "wetness": {
      "absorption": 0.65,
      "colorDarkening": 0.18,
      "roughnessReduction": 0.42,
      "normalFlattening": 0.08
    },
    "rainStreak": { "strength": 0.25 },
    "snow": { "adhesion": 0.12 }
  },
  "requiredFeatures": [
    "surface.wetness.v1",
    "surface.rain-streak.v1"
  ],
  "renderer": {
    "minVersion": "1.1",
    "fallbackColor": "#9e3f30"
  },
  "files": {
    "textures/basecolor.ktx2": "sha256:FILE_HASH"
  }
}
```

颜色空间必须明确：baseColor 和 emissive 通常使用 sRGB；normal、roughness、metallic、AO 通常按线性数据读取。

### 7.4 导入流程

```text
选择 .wildmat
→ 校验容器、大小、文件数量和路径
→ 校验 manifest 版本和字段
→ 校验每个文件哈希、MIME、尺寸、色彩空间
→ 计算整个材质定义的内容哈希
→ 存入全局内容寻址资产库
→ 生成缩略图和质量信息
→ 注册 MaterialDefinition
→ 用户或 AI 通过 materialRef 复用
```

导入器必须防止路径穿越、压缩炸弹、超大纹理、重复文件和伪造扩展名。未知字段可以保留，但未知可执行代码必须拒绝。

### 7.5 PBR、程序化表面与光影包的混合

混合不是简单叠加两套完整材质，而应限定为少量有价值的组合：

- PBR 贴图提供基础颜色、法线和粗糙度。
- 程序化遮罩提供积尘、雨痕、湿润、盐碱和局部色差。
- 世界环境提供高度、朝向、遮挡和天气输入。
- 光影包提供湿润、积雪、雨痕等通用算法和质量配置。
- 材质定义只提供吸水率、变暗程度、积雪附着力等环境响应参数。
- 最终参数仍进入同一套 PBR 光照计算。

例如同一份砖墙 PBR 可以在建筑北侧生成更明显的潮湿，在檐口下减少雨痕，而不需要制作多套贴图。

PBR 材质包不应携带自己的任意 Shader 源码。否则每个材质包都会重复下雨和积雪逻辑，并产生安全风险、兼容问题和 Shader 变体膨胀。材质包可以通过 `requiredFeatures` 声明所需能力；运行时若当前光影包或设备不支持，应忽略高级响应并使用基础 PBR 回退，而不是阻止整个世界加载。

## 8. 多蓝图隔离与共享

### 8.1 必须隔离的状态

- 元素 ID、父子引用和局部坐标。
- 选择、高亮、编辑锁和撤销记录。
- 物理碰撞体与交互脚本实例。
- 蓝图实例变换和可见性。
- 临时动画和用户操作状态。

建议使用全局实体键：

```text
worldEntityId = blueprintInstanceId + ':' + localElementId
```

### 8.2 可以共享的状态

- 不可变的材质定义。
- 贴图内容和 GPU 纹理。
- 已编译的 Shader 程序变体。
- 不可变几何模板和组件模型。
- 资产元数据、缩略图和许可证信息。

### 8.3 不能直接共享的对象

同一 Three.js 材质如果会被修改颜色、透明度或高亮状态，就不能无条件由多个对象共用。推荐把对象状态拆开：

- 永久材质差异：生成写时复制材质实例并进入缓存。
- 选择高亮：使用后处理、单独描边或临时覆盖，不修改基础材质。
- 动态脏污：放入实例参数缓冲或受控 uniform，不写回全局定义。

### 8.4 加载与卸载时序

```text
加载世界区块
→ 解析蓝图引用
→ 建立蓝图实例命名空间
→ 收集所需 materialRef
→ Registry 去重并解析定义
→ GPU Cache 获取或创建资源、增加引用
→ 重建几何并绑定材质

卸载世界区块
→ 销毁该蓝图的交互和几何实例
→ 对材质、纹理、几何缓存减少引用
→ 零引用资源进入延迟回收
```

## 9. 去中心化世界的额外约束

去中心化不只是把文件放到 IPFS。材质和蓝图需要具备以下能力：

1. **内容寻址**：引用内容哈希，而不是服务器临时路径。
2. **不可变版本**：修改内容产生新哈希，旧世界仍能复现。
3. **签名与来源**：发布者可签名，客户端可以显示可信来源。
4. **许可证**：材质包必须携带可机器读取的授权信息。
5. **多解析器**：同一引用可从本地缓存、HTTP、对象存储或去中心化网络解析。
6. **离线回退**：资源不可用时仍显示基础颜色或低级材质。
7. **确定性**：程序材质固定算法版本、参数和种子。
8. **安全边界**：不执行包内任意 Shader、脚本或路径。

建议先定义统一的 `AssetResolver` 接口，再增加不同来源；不要让渲染器直接理解 HTTP、磁盘路径或 IPFS。

## 10. AI 如何参与材质生成

AI 不应直接写 Shader 源码，也不应随意生成任意字段。推荐流程：

```text
用户建筑描述
→ AI 识别建筑语义、风格、年代、气候和构件角色
→ 选择材质来源策略（程序 / PBR 库 / 混合）
→ 选择受支持的材质族或全局资产
→ 生成受约束的配方意图
→ 代码归一化、补默认值、限制范围和固定 seed
→ 预览 / 校验 / 应用
```

当用户只说“生成一个别墅”时，AI 可以根据风格和环境做适度丰富，但随机性必须受控：

- 同一个生成任务保持相同 seed，重试不应完全换材质。
- 优先选择世界主题已经存在的材质，避免每栋建筑都创造新材质。
- 若用户关闭“AI 自动生成 Shader”，只使用基础材质或素材库中的 PBR。
- AI 的丰富结果应保存在结构化计划中，便于用户理解和修改。

推荐输出中间意图，而不是直接输出底层数值：

```json
{
  "role": "facade.primary",
  "surface": "brick",
  "age": "lightly_weathered",
  "climate": "humid",
  "variation": "subtle",
  "preferredSource": "auto"
}
```

后端配方系统再把意图稳定映射为具体参数。这能防止提示词不断膨胀，也方便未来替换 Shader 实现。

## 11. 与当前项目的关系

当前项目已经完成从单蓝图材质到世界运行时的客户端基础链路：

- `.wild` 只保存建筑几何、构件和材质引用；世界环境字段保存在 `.wild.world` / `WorldDocument`，不会随单栋 Blueprint 切换而覆盖全局天气。
- core 输出 renderer 无关的 `RenderMaterialDescriptor`、有限表面族、环境响应和功能依赖。
- renderer 已有全局材质/纹理引用计数、默认表面 Shader、PBR 天气层、专用砖 Shader 和单一激活光影运行时。
- 素材面板已能导入、管理、应用 `.wildmat`，并导入、显式启用 `.wildlook`。
- 标准 ZIP/ZIP64、KTX2/Basis、IndexedDB 包恢复、内容哈希、Ed25519 声明签名和资源解析器已接入。
- `WorldDocument`、`BlueprintInstance`、`WorldRuntime`、区块卸载和世界主题接口已实现；当前编辑器蓝图作为第一个世界实例运行。
- 后端已有素材内容存储、材质计划以及受控程序化配方生成。

`MaterialCache` 现在是蓝图作用域句柄，底层资源注册表按完整材质签名和纹理内容共享；释放一个蓝图只减少自己的引用，不会销毁其他蓝图仍在使用的 GPU 资源。

当前 `CanvasViewport` 仍以 `sceneStore.reconstructed` 作为活动编辑对象，但实际几何已挂载到 `WorldRuntime → BlueprintRenderInstance`。以后增加世界编排 UI 时可以并列挂载更多实例，不需要合并多份 Blueprint JSON。

仍需由后续产品/部署工作补齐的不是另一套渲染引擎，而是外部基础设施：

1. 世界编排和多实例选择的产品界面。
2. 生产发布者证书、密钥轮换和信任目录。
3. 对象存储/CDN/IPFS 网关部署与运行监控。
4. 更大世界的按相机距离网络流式调度和显存预算面板。
5. 更多受控表面族及真实设备上的 GPU 基准数据。

### 11.1 预计涉及的代码位置

以下是实施时应评审的边界，不代表需要一次性全部修改：

| 位置 | 可能职责变化 |
| --- | --- |
| `wild-web/src/wild-core/types.ts` | 增加全局引用、统一表面来源、`RenderProfile`、`EnvironmentState` 和世界实例协议 |
| `wild-web/src/renderer/materialAdapter.ts` | 从“直接创建材质”转为通过 Registry/Compiler 获取材质 |
| `wild-web/src/renderer/proceduralMaterials/` | 扩展有限材质族、版本、质量等级和回退 |
| 建议新增 `wild-web/src/renderer/shaderFeatures/` | 保存湿润、雨痕、积雪等可复用 Three.js/GLSL 实现 |
| 建议新增 `wild-web/src/renderer/shaderPacks/` | 解析 `.wildlook`，组合功能、质量等级和回退配置 |
| `wild-web/src/wild-core/src/primitive/materials/apply.ts` | 统一绑定材质引用与受控实例覆盖 |
| `wild-web/src/wild/materialBindings.ts` | 增加语义槽位、世界主题和优先级解析 |
| 场景与重建相关模块 | 引入蓝图实例根节点、命名空间和卸载生命周期 |
| `wild-web/src/components/panels/PBRAssetPanel.vue` | 支持 `.wildmat` 导入、预览、版本和许可证信息 |
| `wild-server/app/services/asset_storage.py` | 内容寻址、去重、清单校验和包文件存储 |
| `wild-server/app/agent/nodes/material_plan_node.py` | 输出材质意图、复用全局资产、选择来源策略 |
| 蓝图解析与校验模块 | 校验 `materialRef`、依赖、回退和协议版本 |

实际实施前应再次以当前代码为准确认文件职责，避免为了架构图进行无关重构。

## 12. 分阶段实施路线

### 阶段 0：冻结概念和协议

目标：避免现有 Shader 与 PBR 功能继续沿两条路径扩张。

- 确定 `SurfaceSource`、`MaterialDefinition` 和 `MaterialRef`。
- 确定 `RenderProfile`、`EnvironmentState`、`EnvironmentResponse` 和 Shader 功能 ID。
- 明确颜色空间、单位、种子和版本规则。
- 为现有材质定义向新协议设计无损映射。
- 确定 `.wildmat` 1.0 与 `.wildlook` 1.0 清单。

验收：现有 `.wild` 不改即可继续渲染，新旧协议转换有测试。

### 阶段 1：全局材质注册表

目标：先解决材质定义复用，不急于多蓝图。

- 引入 `GlobalMaterialRegistry`。
- 材质适配器通过注册表获取不可变定义。
- 建立运行时缓存键和引用计数。
- 选中高亮不再修改共享基础材质。

验收：同一场景中 100 个对象引用一个材质时，只建立一份可共享基础资源。

### 阶段 2：PBR 资产包

目标：让导入、复用、迁移和分发成为一个完整闭环。

- 实现 `.wildmat` 解析和安全校验。
- 资产存储改为内容寻址和自动去重。
- 支持 KTX2 质量级别及普通图片回退。
- 素材库显示来源、许可证、尺寸和依赖状态。

验收：同一包重复导入不产生重复资产；换设备后可通过引用恢复。

### 阶段 3：程序化材质族、光影包和混合层

目标：让 Shader 真正成为可控的默认世界材质。

- 从砖扩展到少量高价值材质族。
- 建立版本化配方、范围限制和确定性测试。
- 增加 low/medium/high/fallback。
- 建立 `ShaderFeatureRegistry` 和内置默认 `RenderProfile`。
- 先实现湿润、雨痕、积雪等少量通用功能。
- 只实现受控的 PBR + 程序化遮罩 + 环境响应混合。

验收：同一版本、参数和 seed 生成一致结果；同一光影包可同时作用于程序化与 PBR 材质；低端质量可自动降级。

### 阶段 4：多蓝图世界容器

目标：同时渲染多个独立蓝图并共享资源。

- 增加 WorldDocument 和 BlueprintInstance。
- 建立实体命名空间和实例生命周期。
- 引入区块加载、卸载和资源引用回收。
- 支持世界主题替换蓝图语义材质。

验收：加载 10 份使用同一材质的蓝图时，贴图和基础材质只上传一次；卸载其中 9 份不会破坏剩余蓝图。

### 阶段 5：去中心化解析

目标：在不改变渲染层的情况下增加资源来源。

- 抽象 `AssetResolver`。
- 支持本地、HTTP、对象存储和去中心化来源。
- 加入签名、信任级别、离线缓存和失败回退。

验收：同一内容哈希从不同来源解析得到相同验证结果，网络失败仍可显示回退材质。

## 13. 性能预测与观测指标

必须通过数据选择 Shader 或 PBR，不能靠主观判断。建议至少记录：

- 首次可见时间和资源下载字节数。
- 纹理 GPU 内存估算。
- Shader 编译次数和编译耗时。
- 每帧材质切换、draw call 和纹理采样数量。
- 每个材质族在 low/medium/high 下的 GPU 时间。
- 全局缓存命中率、重复资源节省量和零引用资源数量。
- 蓝图加载、卸载后的 GPU 资源是否回到预期值。

预计收益：

- 多蓝图共享相同贴图时，下载、解码和 GPU 上传可显著减少。
- 默认程序化材质可降低基础世界包体，但会增加首次 Shader 编译成本。
- 语义主题能减少 AI 重复创造近似材质，提升世界一致性。
- 内容寻址可以天然去重，也能为去中心化分发提供校验基础。

主要风险：

| 风险 | 控制方式 |
| --- | --- |
| Shader 变体爆炸 | 有限特性位、uniform 参数、预热、质量等级 |
| 共享材质被意外修改 | 不可变定义、写时复制、独立高亮管线 |
| PBR 包体过大 | KTX2、质量层级、流式加载、显存预算 |
| 外部包不安全 | 禁止任意代码、哈希校验、限额和路径检查 |
| 旧世界无法复现 | 材质族版本、迁移器、基础材质回退 |
| AI 随机性破坏一致性 | 世界主题优先、固定 seed、结构化意图 |
| 一次重构范围过大 | 按 Registry → 包格式 → 多蓝图的顺序渐进实施 |

## 14. 必须坚持的设计原则

1. **一种光照管线，多种表面来源。** 不维护两套互不兼容的渲染体系。
2. **材质族有限，配方变化无限。** 新增代码必须解决一类材料，而不是一个外观。
3. **蓝图引用资产，不复制资产。** 材质和贴图属于世界级资源。
4. **共享不可变数据，隔离可变状态。** 防止一个蓝图影响另一个蓝图。
5. **内容哈希是真正身份，名称只是别名。** 便于去重、迁移和去中心化校验。
6. **自定义容器，不自创压缩算法。** 把创新放在协议和体验上。
7. **产品上区分材质包与光影包，内部统一编译。** 清晰体验不能演变成重复渲染管线。
8. **天气属于世界，算法属于光影功能，响应参数属于材质。** 三者不能互相侵入。
9. **外部包只传受约束数据，不传任意 GPU 代码。** 安全和兼容优先。
10. **所有高级效果都必须有回退。** 世界不能因为一个材质或光影功能加载失败而不可用。
11. **AI 生成意图，确定性代码生成参数。** 减少幻觉和不可复现结果。
12. **先测共享与生命周期，再扩展材质数量。** 否则类型越多，资源泄漏和变体问题越难收敛。

## 15. 最终建议

你的思路不是“再增加一个渲染引擎”，而是在建立一套世界级材质平台。最适合 WILD 的长期形态是：

- 用程序化材质族提供轻量、统一、可变化的默认世界。
- 用 `.wildmat` PBR 资产包提供可复用的高精度表面。
- 用 `.wildlook` 光影包组合阴影、天气、天空、曝光和后处理能力。
- 用受控混合层和材质环境响应参数，让同一资产响应气候、朝向和年代。
- 用世界文档组合多份几何隔离的蓝图。
- 用全局注册表和 GPU 缓存让所有蓝图共享同一份材质资源。
- 用内容哈希、版本和安全回退为去中心化分发打基础。

默认世界应由“内置程序化材质库 + 内置默认光影包”组成，不依赖外部 PBR。导入 PBR 材质包后替换表面数据，导入光影包后改变所有材质的世界表现，两者通过统一材质编译器配合，而不是彼此携带和复制实现代码。

最先应该实现的不是更多材质类型，也不是自定义压缩算法，而是 **统一材质合同 + 全局注册表 + Shader 功能注册表 + 稳定引用**。这些基础正确之后，程序化材质、PBR、光影包、AI 自动配方和多蓝图世界才能继续扩展而不让代码规模失控。
