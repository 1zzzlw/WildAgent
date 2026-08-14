# `.wildmat` 材质包与 `.wildlook` 光影包格式规范

本文对应 WildAgent 当前 `1.0` 包协议，说明两种文件如何编写、打包、导入和排错。

- `.wildmat`：世界材质包，提供 PBR 纹理、材质默认参数和天气响应。
- `.wildlook`：世界光影配置，组合渲染器已注册的光照、天空、雾、天气和后处理能力。

二者都不保存建筑几何，也不能携带任意 GLSL、WGSL 或 JavaScript。建筑 Blueprint 只引用已经注册的材质；光影和天气属于全局世界状态。

## 1. 文件容器

### 1.1 `.wildmat`

推荐使用标准 ZIP/ZIP64 容器，然后把扩展名改为 `.wildmat`：

```text
stone_wall.wildmat
├─ manifest.json
└─ textures/
   ├─ basecolor.webp
   ├─ normal.webp
   ├─ roughness.webp
   └─ ao.webp
```

解析器根据文件头识别 ZIP，不依赖伪造的 MIME 或扩展名。ZIP 内必须且只能有一个清单，推荐命名为根目录 `manifest.json`。

如果所有纹理都使用 HTTPS、IPFS、站内绝对路径或安全 Data URI，也可以把单个 JSON 清单直接保存为 `.wildmat`。但 JSON 单文件不能使用 `package:/` 包内路径。

### 1.2 `.wildlook`

当前 `.wildlook` 不包含可执行 Shader 或必需的图片资源，推荐直接把 JSON 清单保存为 `.wildlook`：

```text
cinematic_overcast.wildlook   # 文件内容就是 JSON
```

解析器也能读取 ZIP/ZIP64 形式的 `.wildlook`，但 v1 不会执行或加载其中的自定义 Shader 文件。光影包只能引用渲染器已经注册的功能 ID。

## 2. `.wildmat` 清单

### 2.1 最小可用示例

以下例子适用于 ZIP 容器。示例哈希必须替换为真实 SHA-256：

```json
{
  "format": "wild.material-package",
  "version": "1.0",
  "packageId": "material:stone-limestone-v1",
  "materialId": "stone_limestone",
  "name": "浅色石灰岩",
  "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "license": "CC0",
  "family": "mineral",
  "channels": {
    "baseColor": {
      "uri": "package:/textures/basecolor.webp",
      "mimeType": "image/webp",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "colorSpace": "srgb"
    }
  }
}
```

`baseColor` 是唯一必需的纹理通道。其余通道都是可选增强。

### 2.2 完整示例

```json
{
  "format": "wild.material-package",
  "version": "1.0",
  "packageId": "material:weathered-limestone-v1",
  "materialId": "weathered_limestone",
  "name": "轻度风化石灰岩",
  "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "license": "CC0",
  "publisher": "Example Studio",
  "family": "mineral",
  "channels": {
    "baseColor": {
      "uri": "package:/textures/basecolor.webp",
      "mimeType": "image/webp",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "colorSpace": "srgb",
      "byteSize": 245760,
      "variants": {
        "low": {
          "uri": "package:/textures/basecolor-low.webp",
          "mimeType": "image/webp",
          "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
          "colorSpace": "srgb",
          "byteSize": 98304
        }
      }
    },
    "normal": {
      "uri": "package:/textures/normal.webp",
      "mimeType": "image/webp",
      "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "colorSpace": "linear"
    },
    "roughness": {
      "uri": "package:/textures/roughness.webp",
      "mimeType": "image/webp",
      "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "colorSpace": "linear"
    },
    "ambientOcclusion": {
      "uri": "package:/textures/ao.webp",
      "mimeType": "image/webp",
      "sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      "colorSpace": "linear"
    }
  },
  "defaults": {
    "baseColorTint": [1, 0.98, 0.94],
    "roughness": 0.82,
    "metallic": 0,
    "normalScale": 1.15,
    "uvScale": [1, 1]
  },
  "environmentResponse": {
    "wetness": {
      "absorption": 0.48,
      "colorDarkening": 0.16,
      "roughnessReduction": 0.24,
      "normalFlattening": 0.2
    },
    "rainStreak": { "strength": 0.2 },
    "snow": { "adhesion": 0.42 },
    "dust": { "adhesion": 0.5 }
  },
  "requiredFeatures": [
    "surface.pbr.v1",
    "surface.wetness.v1",
    "surface.rain-streak.v1"
  ],
  "renderer": {
    "minVersion": "1.0",
    "fallbackColor": [0.62, 0.6, 0.56]
  }
}
```

### 2.3 字段说明

| 字段 | 必需 | 规则 |
|---|---:|---|
| `format` | 是 | 固定为 `wild.material-package` |
| `version` | 是 | 当前固定为 `1.0` |
| `packageId` | 是 | 全局包 ID；允许字母、数字、`.`、`_`、`:`、`/`、`-` |
| `materialId` | 是 | 写入 Blueprint 材质表时使用的稳定 ID |
| `name` | 是 | 用户可见名称 |
| `contentHash` | 是 | `sha256:` 加 64 位十六进制摘要；用于去重和稳定资产 ID |
| `license` | 是 | 例如 `CC0`、`CC BY 4.0`、`User supplied` |
| `family` | 否 | `neutral`、`mineral`、`masonry`、`wood`、`metal`、`glass` |
| `channels.baseColor` | 是 | 基础颜色纹理 |
| `channels.normal` | 否 | 法线纹理 |
| `channels.roughness` | 否 | 粗糙度纹理 |
| `channels.metalness` | 否 | 金属度纹理；字段名是 `metalness` |
| `channels.ambientOcclusion` | 否 | AO 纹理 |
| `defaults` | 否 | 材质导入后的默认渲染参数 |
| `environmentResponse` | 否 | 该材质对世界雨雪、湿润和积尘的响应强度 |
| `requiredFeatures` | 否 | 运行该材质所依赖的已注册功能 ID |
| `publisher` / `signature` | 否 | 发布者和 Ed25519 清单签名 |
| `renderer` | 否 | 最低渲染器版本和回退颜色 |

### 2.4 纹理通道规则

每个通道都使用相同的资源结构：

```json
{
  "uri": "package:/textures/normal.webp",
  "mimeType": "image/webp",
  "sha256": "64位真实文件摘要",
  "colorSpace": "linear",
  "byteSize": 123456,
  "variants": {
    "low": { "...": "同样的资源结构" },
    "medium": { "...": "同样的资源结构" },
    "high": { "...": "同样的资源结构" }
  }
}
```

允许的图片格式：

- `image/png`
- `image/jpeg`
- `image/webp`
- `image/ktx2`

颜色空间：

- `baseColor`：通常使用 `srgb`。
- `normal`、`roughness`、`metalness`、`ambientOcclusion`：必须使用 `linear`。

包内 URI 必须写成 `package:/相对路径`。禁止绝对磁盘路径、`..`、空目录段和重复路径。

### 2.5 参数范围

| 参数 | 范围 |
|---|---:|
| `baseColorTint` | 三个 `0~1` 数值 |
| `roughness` | `0~1` |
| `metallic` | `0~1` |
| `normalScale` | `0~4` |
| `uvScale` | 两个 `0.01~64` 数值 |
| 所有 `environmentResponse` 数值 | `0~1` |

`baseColorTint: [1,1,1]` 保持原图颜色；其他颜色会与 Base Color 相乘。

## 3. `.wildlook` 清单

### 3.1 最小可用示例

```json
{
  "format": "wild.render-profile",
  "version": "1.0",
  "profileId": "look:soft-overcast-v1",
  "name": "柔和阴天",
  "features": {
    "lighting": "lighting.pbr.v1",
    "sky": "environment.sky.v1",
    "fog": "environment.fog.v1",
    "toneMapping": "post.tonemap.v1"
  },
  "appearance": {
    "directLightScale": 0.62,
    "ambientLightScale": 1.08,
    "exposureScale": 0.92,
    "shadowOpacity": 0.52,
    "fogScale": 1.35
  }
}
```

把这段 JSON 保存为 `soft_overcast.wildlook`，即可从“光影”面板导入。导入不会自动启用，需要用户点击“启用”。

### 3.2 完整示例

```json
{
  "format": "wild.render-profile",
  "version": "1.0",
  "profileId": "look:cinematic-rain-v1",
  "name": "电影感雨天",
  "contentHash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  "license": "CC0",
  "publisher": "Example Studio",
  "features": {
    "lighting": "lighting.pbr.v1",
    "sky": "environment.sky.v1",
    "fog": "environment.fog.v1",
    "toneMapping": "post.tonemap.v1",
    "wetness": "surface.wetness.v1",
    "rainStreak": "surface.rain-streak.v1"
  },
  "appearance": {
    "directLightScale": 0.58,
    "ambientLightScale": 0.86,
    "exposureScale": 0.84,
    "shadowOpacity": 0.46,
    "fogScale": 1.55
  },
  "quality": {
    "shadowTier": "medium",
    "weatherTier": "high",
    "postProcessingTier": "medium"
  },
  "renderer": {
    "minVersion": "1.0",
    "fallbackProfile": "builtin:default"
  }
}
```

### 3.3 字段说明

| 字段 | 必需 | 规则 |
|---|---:|---|
| `format` | 是 | 固定为 `wild.render-profile` |
| `version` | 是 | 当前固定为 `1.0` |
| `profileId` | 是 | 全局光影配置 ID |
| `name` | 是 | 用户可见名称 |
| `features` | 是 | 至少一个“角色 → 已注册功能 ID”映射 |
| `appearance` | 否 | 光照、曝光、阴影和雾的安全倍率 |
| `quality` | 否 | 阴影、天气和后处理质量档位 |
| `contentHash` | 否 | 推荐使用完整 SHA-256 |
| `license` / `publisher` / `signature` | 否 | 发布与签名信息 |
| `renderer` | 否 | 最低版本和不兼容时的回退配置 |

`appearance` 范围：

| 参数 | 范围 | 含义 |
|---|---:|---|
| `directLightScale` | `0~4` | 太阳/月亮主方向光倍率 |
| `ambientLightScale` | `0~4` | 天空环境光倍率 |
| `exposureScale` | `0.1~4` | 色调映射曝光倍率 |
| `shadowOpacity` | `0~1` | 接触阴影与地面阴影倍率 |
| `fogScale` | `0.1~8` | 世界雾距离倍率 |

质量档位只能是 `low`、`medium`、`high`、`fallback`。

### 3.4 当前内置功能 ID

以下功能无需额外插件即可在 `.wildlook` 中引用：

```text
lighting.pbr.v1
environment.sky.v1
environment.fog.v1
post.tonemap.v1
surface.wetness.v1
surface.rain-streak.v1
surface.snow.v1
surface.dust.v1
```

材质系统另外注册了：

```text
surface.micro-variation.v1
surface.masonry.brick.v1
surface.pbr.v1
texture.ktx2.v1
asset.zip64.v1
```

`features` 的左侧角色名用于表达用途，右侧功能 ID 决定实际能力。未知功能可以被导入记录，但启用光影包时会被拒绝并保持原光影不变。

## 4. 安全限制

清单任意层级出现下列可执行字段都会被拒绝：

```text
shader / shaderSource / shaderCode
vertexShader / fragmentShader
glsl / wgsl
script / javascript / code
```

这是有意设计：外部包只能选择受控功能并提供参数，不能把任意 GPU 或脚本代码注入世界。

ZIP/ZIP64 限制：

- 压缩包最大 128 MB。
- 单个解压文件最大 64 MB。
- 解压后总大小最大 256 MB。
- 文件数量最多 512。
- 清单最大 2 MB。
- 不允许加密条目、重复路径和路径穿越。
- 包内图片会核验真实 MIME、SHA-256 和可选的 `byteSize`。

## 5. Windows 制作流程

### 5.1 计算纹理 SHA-256

```powershell
(Get-FileHash .\textures\basecolor.webp -Algorithm SHA256).Hash.ToLower()
```

把结果写入对应通道的 `sha256`。如果填写 `byteSize`：

```powershell
(Get-Item .\textures\basecolor.webp).Length
```

### 5.2 打包 `.wildmat`

目录准备完成后：

```powershell
Compress-Archive -Path .\manifest.json, .\textures -DestinationPath .\stone_wall.zip
Rename-Item .\stone_wall.zip stone_wall.wildmat
```

注意 ZIP 根目录必须直接看到 `manifest.json`，不要多包一层项目目录。

### 5.3 制作 `.wildlook`

把合法 JSON 保存为目标扩展名即可：

```powershell
Copy-Item .\manifest.json .\soft_overcast.wildlook
```

## 6. 导入后的行为

### `.wildmat`

1. 在右侧“素材”面板点击“导入 `.wildmat`”。
2. 包通过校验后进入全局材质包列表，并持久化保存。
3. 选择一个或多个构件，点击“应用到已选”。
4. 编辑器把稳定的材质包引用写入 Blueprint；纹理资源仍由全局材质系统共享。

### `.wildlook`

1. 在右侧“光影”面板点击“导入 `.wildlook`”。
2. 包通过校验后进入光影配置列表，但不会自动启用。
3. 点击“启用”，渲染器验证所有功能 ID 后切换配置。
4. 切换成功后释放上一套外部光影运行时资源；失败则继续使用原配置。

## 7. 常见错误

| 错误 | 原因与修复 |
|---|---|
| 素材面板提示清单类型不符 | `.wildmat` 内的 `format` 必须是 `wild.material-package` |
| 光影面板提示清单类型不符 | `.wildlook` 内的 `format` 必须是 `wild.render-profile` |
| `JSON 清单不能引用包内路径` | 使用了 `package:/`，但文件不是 ZIP 容器 |
| `包内资源不存在` | `uri` 与 ZIP 内实际相对路径不一致 |
| `包内资源哈希不匹配` | 重新计算文件 SHA-256，注意不要计算路径字符串 |
| `包内资源类型与清单不一致` | `mimeType` 与真实 PNG/JPEG/WebP/KTX2 文件不一致 |
| `contentHash 必须是完整 SHA-256` | `.wildmat` 应填写 `sha256:` 加 64 位十六进制值 |
| `Unsupported shader features` | `.wildlook` 引用了当前渲染器未注册的功能 ID |
| 包被判定不可信 | 未签名或 Ed25519 签名无效；本地包仍可标记为未签名导入，但不会获得“签名已验证”状态 |

## 8. 当前 v1 边界

- `.wildmat` 已支持包内 PBR 图片、画质变体、KTX2、天气响应、内容去重和复用。
- `.wildlook` 当前是“已注册光影功能的安全参数配置”，不是任意 Shader 源码容器。
- 天气的实时数值保存在世界环境状态中，不写入 `.wildlook`，也不写入建筑 Blueprint；`.wildlook` 只决定天气和光照怎样被渲染。
- `contentHash` 当前用于包身份和去重；纹理通道文件哈希会严格核验。制作工具应对稳定、规范化的材质定义计算内容哈希，避免把文件名或临时路径纳入身份。

