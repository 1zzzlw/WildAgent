# WILD 默认世界材质与光影实施路线

> 从当前单蓝图渲染链路，逐步发展到全局材质、可替换光影包和去中心化多蓝图世界。每个 Phase 必须独立验收。

## 总体目标

默认情况下不依赖外部 PBR 材质包或光影包，世界仍具备自然、稳定、性能可控的程序化表面和 PBR 光照。

~~~text
.wild Blueprint
→ core 解析几何和材质语义
→ core 输出渲染中间表示
→ renderer 查找已注册的表面与光影实现
→ Three.js 编译材质并渲染
~~~

外部包以后只替换标准接口：

~~~text
内置程序化表面 ─┐
PBR 材质包 ─────┼─> 统一材质编译器 ─> 当前光影配置 ─> Three.js
混合表面 ───────┘
~~~

## 必须坚持的边界

- core 保存类型、语义、参数、版本、能力 ID 和回退，不导入 Three.js。
- renderer 保存 Three.js、GLSL/WGSL 和 GPU 资源生命周期实现。
- renderer/proceduralMaterials 当前是实际 Shader 实现，不能直接删除。
- Blueprint 和外部包不得携带任意可执行 Shader 源码。
- 新增能力必须解决一类表面，不为某栋建筑或某个外观打补丁。
- 每个蓝图拥有独立几何根节点；材质、纹理和程序通过全局运行时共享。

## Phase 1：冻结 core 与 renderer 合同

### 实现内容

1. 定义 renderer 无关的 RenderMaterialDescriptor。
2. 定义有限基础表面族：neutral、mineral、masonry、wood、metal、glass。
3. 定义表面来源：constant、procedural、texture-set、hybrid。
4. 定义 EnvironmentState、EnvironmentResponse 和 requiredFeatures。
5. 保持现有 procedural.type = brick 向后兼容。

### 结果

core 每个材质参数都携带稳定、可校验的渲染描述。未知值回退 neutral，不进入任意代码路径。

### 验收

- core 不依赖 Three.js。
- 同一个 Blueprint 多次解析得到相同描述。
- 现有 .wild 不修改即可重建。

## Phase 2：完成默认程序化表面 Shader

### 实现内容

1. 保留专用砖 Shader，注册为 masonry.brick.v1。
2. 增加一个低成本通用表面 Shader，通过 uniform 表达有限表面族：
   - neutral：极弱微表面变化。
   - mineral：混凝土、灰泥、石材的低频斑驳。
   - wood：方向性细微木纹。
   - metal：轻微拉丝和粗糙度变化。
   - glass：不增加颜色噪声，保持物理透射。
3. 仅在没有 PBR 颜色贴图、没有显式专用程序材质时启用。
4. 数值差异使用 uniform，避免每个外观产生新 GPU Program。
5. 保留 low、medium、high、fallback 质量入口，默认使用低成本等级。

### 结果

不开 AI Shader、不导入 PBR 时，普通墙面、木构件、金属和玻璃仍有克制的自然表面。

### 验收

- 默认效果不过度显眼。
- 同一功能只产生有限程序变体。
- PBR 贴图和专用砖 Shader 不被重复叠加。

## Phase 3：完成默认世界光影

### 实现内容

1. 将视口里的天空、太阳、半球光、阴影、雾、曝光和后处理整理为 DefaultWorldLook。
2. 定义 WorldLookProfile，包含光照比例、阴影质量、天空、雾、曝光和功能 ID。
3. 建立 ShaderFeatureRegistry，内置功能通过 ID 注册并延迟创建。
4. EnvironmentState 统一提供时间、雨量、湿润、积雪、风和云量。
5. 材质只声明吸水率、变暗程度、粗糙度变化和积雪附着力。

### 单一激活与资源释放

1. 任意时刻只允许一个主 WorldLookProfile 处于 active。
2. builtin:default 是回退，不与外部光影隐式叠加。
3. 新光影先校验、加载和预热，成功后原子切换。
4. 切换后释放旧配置持有的阴影贴图、RenderTarget、Pass 和材质引用。
5. 注册表只保留工厂和元数据；未激活功能不创建 GPU 资源。
6. 外部光影失败时继续使用 builtin:default，避免黑屏。
7. V1 只支持 replace；将来如需叠加，必须使用显式、受预算控制的 overlay。

### 表面 Shader 与光影 Shader 的关系

- 换光影包不会无条件删除砖、木材等表面实现。
- 表面实现继续为材质提供颜色、法线和粗糙度。
- 光影配置决定这些表面如何接受灯光、天气和后处理。
- 只有外部光影明确提供兼容替代功能时，才重新编译相应材质。

### 验收

- 没有外部包时始终使用 builtin:default。
- 切换后旧光影运行时资源引用为零。
- 程序化与 PBR 表面使用同一环境状态。
- 切换失败不改变当前可用场景。

## Phase 4：全局材质共享与蓝图隔离

### 实现内容

1. 全局材质键使用完整参数签名，不以材质名作为身份。
2. 全局纹理键包含内容、通道、色彩空间、采样和 UV 参数。
3. 材质和纹理使用引用计数。
4. 每个蓝图实例拥有唯一 instanceId、独立 THREE.Group 和材质作用域。
5. 蓝图更新只释放该作用域不再使用的资源。

### 结果

几何、选择和交互按蓝图隔离；相同材质和纹理在多个蓝图间只创建一份 GPU 资源。

### 验收

- 两个蓝图使用相同参数时获得同一材质对象。
- 释放一个蓝图不会破坏另一个蓝图。
- 同名但参数不同的 wall 不会互相覆盖。

## Phase 5：材质包与光影包解析接口

### 实现内容

1. 定义 .wildmat 和 .wildlook 清单。
2. 提供协议版本、数值、URI、哈希、色彩空间和功能依赖校验。
3. 暴露 registerMaterialPackage、registerWorldLookProfile 和 registerShaderFeature。
4. 提供可插拔 WorldPackageDecoder。
5. 初始只解析 JSON 清单，不伪装支持尚未实现的 ZIP/KTX2。
6. 拒绝 shaderSource、glsl、wgsl、script 等可执行字段。

### 结果

以后增加压缩包、服务端素材库或去中心化来源时，不修改 core 到 renderer 的主链路。

### 验收

- 合法清单可解析和注册。
- 任意 Shader 源码和不支持的大版本被拒绝。
- 未实现功能有诊断并安全回退。

## Phase 6：前端导入与管理

### 实现内容

1. 素材面板增加 .wildmat 导入。
2. 光影设置增加 .wildlook 导入。
3. 显示名称、版本、许可证、依赖和支持状态。
4. 材质包由用户明确应用到已选构件。
5. 光影包由用户明确启用，不在导入后自动覆盖。
6. 支持移除、回退默认包和内容去重。

### 验收

- 导入失败不改变场景。
- 删除正在使用的包时先回退默认资源。
- 刷新后能恢复全局包引用。

## Phase 7：正式压缩包与高质量资产

### 实现内容

1. .wildmat 使用标准 ZIP/ZIP64，不自创压缩算法。
2. 纹理优先 KTX2/Basis Universal。
3. 服务端内容寻址存储、文件哈希、缩略图和许可证。
4. 防止路径穿越、压缩炸弹、超大纹理和伪造类型。
5. 支持质量等级和观察距离流式加载。

### 验收

- 重复内容不产生副本。
- 同一纹理在多蓝图中只上传一次。
- 包损坏或网络失败时使用基础颜色回退。

## Phase 8：完整天气功能

按通用能力逐个增加，而不是按材质包增加：

1. surface.wetness.v1
2. surface.rain-streak.v1
3. surface.snow.v1
4. surface.dust.v1
5. environment.fog.v1
6. 后续体积云、积水和反射

每个功能必须有性能等级、能力检测和关闭路径。

### 验收

- 同一湿润算法作用于程序化和 PBR 材质。
- 材质通过响应参数表现差异，不携带天气代码。
- 低端设备可以关闭昂贵功能。

## Phase 9：世界文档与多蓝图运行时

### 实现内容

1. 增加 WorldDocument 和 BlueprintInstance。
2. 支持同一蓝图多次实例化。
3. 建立实体命名空间、区块加载和卸载。
4. 建立世界主题到蓝图语义材质槽位的映射。
5. 编辑器从单个 reconstructed 发展为实例集合。

### 验收

- 多份蓝图的几何和交互互不影响。
- 世界主题可替换材质而不修改几何。
- 区块卸载后引用计数和显存回到预期值。

## Phase 10：去中心化分发

### 实现内容

1. 内容哈希作为稳定身份。
2. 支持本地、HTTP、对象存储和去中心化 AssetResolver。
3. 发布者签名、许可证和信任等级。
4. 离线缓存和多来源恢复。
5. 材质族和光影功能严格版本化，保证确定性。

### 最终验收

- 同一世界在不同设备上得到一致资源和可接受视觉结果。
- 不可信包不能执行任意 GPU 或脚本代码。
- 外部资源不可用时，默认材质和默认光影仍能完整显示世界。
- 建筑数量增加时，材质代码不按建筑数量线性增长。

## 当前执行顺序

~~~text
Phase 1 core 合同
→ Phase 2 默认表面 Shader
→ Phase 3 默认世界光影接口
→ Phase 4 全局共享与蓝图隔离
→ Phase 5 包解析与注册扩展点
→ 全部现有检查与前端构建
~~~

Phase 6–10 已在前五阶段合同稳定后接通；生产部署仍需为真实发布者配置签名密钥、对象存储和可用的去中心化网关。

## 当前实施状态（2026-08-14）

| Phase | 状态 | 本轮结果 |
| --- | --- | --- |
| Phase 1 | 已完成 | core 已输出有限表面族、来源、实现 ID、质量等级和环境响应 |
| Phase 2 | 已完成 | 默认表面 Shader 已覆盖有限表面族，画质档位和 A/B 开关通过共享 uniform 实时生效，并兼容专用砖 Shader |
| Phase 3 | 已完成 | 默认光影已重新调校太阳、环境光、曝光和阴影层次；支持单一激活、原子切换、失败回退和资源释放 |
| Phase 4 | 已完成 | 材质和纹理全局引用计数；编辑器当前蓝图也已通过独立 BlueprintRenderInstance/WorldRuntime 运行 |
| Phase 5 | 已完成 | 已提供安全 JSON 清单解析器和材质、光影、功能、解码器注册接口 |
| Phase 6 | 已完成 | 素材面板可导入、列出、应用、启用和移除 `.wildmat/.wildlook`；包文件保存到 IndexedDB，光影选择和天气参数可恢复 |
| Phase 7 | 已完成客户端闭环 | 使用标准 ZIP/ZIP64 解码；限制路径、文件数和解压体积，校验 SHA-256/图片魔数；部署 KTX2/Basis 转码器并支持质量变体与 mipmap 距离 LOD |
| Phase 8 | 已完成首批能力 | wetness、rain-streak、snow、dust 已统一作用于默认表面、专用砖和 PBR；有质量等级与关闭路径，云量联动世界光照 |
| Phase 9 | 已完成运行时 | 已定义 WorldDocument、BlueprintInstance、世界主题和区块；WorldRuntime 支持同蓝图多实例、独立根节点、区块卸载和资源回收，编辑器保存活动世界文档 |
| Phase 10 | 已完成客户端协议 | 资源以内容哈希校验；支持可插拔 AssetResolver、HTTP/站内资源、IPFS 多网关恢复、Cache Storage 离线缓存和 Ed25519 声明签名验证 |

### Phase 6–10 实施说明

- `.wildmat/.wildlook` 可以是安全 JSON 清单或标准 ZIP/ZIP64 包；JSON 清单不能伪装引用包内文件。
- ZIP 导入先读取中央目录元数据，限制 512 个文件、单文件 64 MB、解压总量 256 MB、包体 128 MB；拒绝路径穿越、重复路径、加密条目、哈希错误和伪造图片类型。
- Blueprint 对材质包只保存 `wildpkg://包ID/通道` 稳定引用；当前会话 Blob URL 和 KTX2 转码资源由全局运行时管理，移除包时释放。
- 删除正在使用的材质包前，相关材质会回退基础颜色；删除正在使用的光影包前，先原子切回 `builtin:default`。
- IndexedDB 保存原始包文件，刷新后重新执行相同校验并注册；激活光影、天气和渲染开关保存在本地世界状态。
- `WorldRuntime` 已能承载多个实例和区块，但现有编辑器 UI 仍只暴露一个活动 Blueprint 的编辑入口；新增世界编排界面不需要修改材质/光影核心。
- Phase 10 的客户端协议和安全门禁已完成；真实发布者证书、对象存储地址和 IPFS 网关可用性属于部署配置，不在仓库内伪造。
