# WILD Blueprint 当前版本规范

> 文档分类：WILD 规范与能力目录。返回 [正式文档入口](../README.md)。

最后核对：2026-08-10。  
当前写入版本：WILD `1.1`；兼容读取：`1.0`。

## 1. 文档定位与事实来源

`.wild` 文件是 WildAgent 场景的唯一事实来源，本质上是 UTF-8 编码的严格 JSON。Agent、编辑器和 ScenePatch 只修改 Blueprint；组合构件编译器与 `wild-core` 根据 Blueprint 确定性生成网格，运行时生成的 `_cutouts`、`_jointExtensions`、`_interaction` 等内部字段不得写回文件。

本规范描述当前代码实际支持的交付格式。发生冲突时按以下顺序判断：

1. `wild-web/src/wild-core/`、`wild-web/src/wild-compiler/` 的实际构建代码；
2. `wild-web/wild-lang/schema.json` 和 TypeScript 类型；
3. `wild-server/app/utils/blueprint_parser.py` 与 `spatial_tools.py`；
4. 当前自动化测试；
5. 本文档及知识库中的旧版说明。

## 2. 顶层结构

当前 Agent 可安全交付的标准骨架如下：

```json
{
  "meta": {
    "version": "1.1",
    "type": "building",
    "name": "建筑名称"
  },
  "geometry": {
    "elements": [],
    "components": []
  },
  "materials": {},
  "assets": {},
  "behaviors": {},
  "editor": {
    "revision": 0
  }
}
```

| 顶层字段 | 当前要求 | 说明 |
|---|---|---|
| `meta` | 必需 | 版本、场景类型和名称。 |
| `geometry` | 必需 | 基础元素、组合构件和高级复用定义。 |
| `materials` | 使用材质时必需 | 材质 ID 到材质定义的映射。 |
| `assets` | 可选 | URL 型 PBR 纹理资产清单。 |
| `behaviors` | 可选 | 通用物理、脚本和动画配置；建筑生成默认使用空对象。 |
| `editor` | 可选 | 编辑器私有元数据，不参与几何语义。 |

虽然 JSON Schema 允许省略 `geometry.elements`，后端最终校验流水线要求它存在。因此，Agent 输出必须始终包含 `geometry.elements`，即使它是空数组。根级别禁止写入 `elements`、`components`、`bounds` 等几何字段。

### 2.1 `meta`

| 字段 | 类型 | 必需 | 约束 |
|---|---|---|---|
| `version` | string | 是 | 新文件固定写 `"1.1"`；`"1.0"` 会在读取时迁移为 `1.1`。 |
| `type` | string | 是 | `building` / `avatar` / `asset` / `scene`。 |
| `name` | string | 是 | 非空场景名称。 |
| `author` | string | 否 | 作者。 |
| `createdAt` | number | 否 | 毫秒时间戳。 |
| `style` | string | 否 | 风格标签，不是几何枚举。 |
| `seed` | number | 否 | 程序化生成种子。 |

### 2.2 `geometry`

| 字段 | 类型 | 当前状态 |
|---|---|---|
| `elements` | 基础元素数组 | 正式支持，Agent 必须输出。 |
| `components` | 组合构件数组 | 正式支持；渲染前编译为基础元素。 |
| `templates` | 模板字典 | Core 支持，但当前不允许 Agent 最终交付，见第 8 节。 |
| `instances` | 模板实例数组 | Core 支持，但当前不允许 Agent 最终交付，见第 8 节。 |
| `placements` | 表面网格排布数组 | 能力有限，当前不允许 Agent 最终交付，见第 8 节。 |

`geometry.elements` 与 `geometry.components` 中的所有 `id` 共享同一个命名空间，必须非空且全局唯一。组件编译生成的内部 ID 使用 `<componentId>__...`，人工元素不得占用这一前缀下的名称。

## 3. 坐标、尺寸与引用通则

- 单位统一为米，角度字段另有说明时使用度；`primitive.rotation` 使用弧度。
- 世界坐标为右手系：X 向右、Y 向上、Z 向后；建筑正立面通常位于较小的 Z。
- `Vec3` 必须是恰好三个有限数字组成的数组：`[x, y, z]`。字符串数字、对象坐标、`NaN` 和无穷值都不是正式格式。
- 几何尺寸必须为正有限数；不得用负尺寸表达方向，方向由坐标顺序或旋转表示。
- 元素引用材质时，对应 ID 必须存在于 `materials`。
- `parentWall`、`parentFloor`、`parentRoof` 必须引用正确类型的现有基础元素。
- 同层结构墙的相邻端点必须共享完全相同的 XZ 坐标。墙的 Y 分量分别表达墙底和墙顶，不要求两个墙角对象的完整三维数组相同。
- 蓝图保存的是结构中心线。直线墙在同层、端点相距小于 `0.01m` 且夹角在 90°±5°内时，渲染器才会按相邻墙半厚增加运行时墙角延伸；斜角墙和曲墙不会自动延伸。

## 4. `geometry.elements` 基础元素

当前注册 11 种基础元素。

| `type` | 引擎状态 | 必填字段（除 `type`、`id`） | 关键枚举或条件 |
|---|---|---|---|
| `wall` | stable | `from,to,thickness` | 可选 `curve`。 |
| `floor` | stable | `from,thickness` | `shape=rect` 还需 `to`；`shape=circle` 还需 `radius`。 |
| `column` | partial | `base,height,bottomRadius,topRadius,style` | `style` 见 4.3。 |
| `beam` | partial | `from,to,crossSection,width,height` | `rect/circular/i-beam`。 |
| `roof` | partial | `roofType,span,depth,height,thickness` | 6 种标准屋顶枚举。 |
| `opening` | partial | `parentWall,from,width,height,style` | 洞口和覆盖面；详细门窗优先使用组件。 |
| `stair` | stable | `from,to,width` | 当前为直跑参数化楼梯。 |
| `furniture` | partial | `subtype,position,dimensions` | 仅 6 种基础家具。 |
| `dense_brick` | experimental | `resolution,origin,data` | 当前不应由 Agent 生成。 |
| `body` | partial | `height,build,headShape,armLength,legLength,cloakLength,hoodUp` | 简化参数化人物。 |
| `primitive` | stable | `shape` 及形状对应参数 | `box/sphere/cylinder/profile_sweep`。 |

所有基础元素都可以使用可选的 `material`。未指定时渲染器使用默认材质，但正式建筑蓝图应显式声明主要材质。

### 4.1 `wall`

```json
{
  "type": "wall",
  "id": "wall_front_l1",
  "from": [0, 0, 0],
  "to": [8, 3, 0],
  "thickness": 0.24,
  "material": "wall_ext"
}
```

- 水平中心线从 `from.xz` 指向 `to.xz`，墙长只按 XZ 平面计算。
- `min(from[1], to[1])` 是墙底，`max(from[1], to[1])` 是墙顶。
- 不要写旧式 `height`；兼容解析器只会在 `from.y == to.y` 且 `height > 0` 时把它转换为标准 `to.y`。
- `curve` 可描述 `line`、`arc`、`ellipse`、`catenary`。带门窗洞口的曲墙当前只应使用单段 `arc`；复合曲线路径不得作为门窗宿主。

圆弧墙片段示例：

```json
{
  "curve": {
    "type": "arc",
    "center": [0, 0, 0],
    "sweep": 90,
    "segments": 24
  }
}
```

### 4.2 `floor`

矩形楼板：

```json
{
  "type": "floor",
  "id": "floor_l1",
  "from": [0, -0.2, 0],
  "to": [8, -0.2, 6],
  "thickness": 0.2,
  "shape": "rect",
  "material": "floor_concrete"
}
```

`from` 与 `to` 是矩形 XZ 对角点，正式矩形楼板应让二者 Y 相同。逻辑楼板底标高是 `from[1]`，顶标高是 `from[1] + thickness`。

圆形楼板使用 `from` 作为中心/底标高，并提供 `shape: "circle"`、`radius`，可选 `segments >= 3`；不再提供 `to`。

### 4.3 `column` 与 `beam`

`column.style` 只能是：

```text
doric | ionic | corinthian | modern | chinese_wooden
```

`beam.crossSection` 只能是：

```text
rect | circular | i-beam
```

柱的 `base` 是底部中心，`height` 向 Y+ 延伸。梁从 `from` 延伸到 `to`，可选 `curve`；`width`、`height` 是截面尺寸。

### 4.4 `roof`

```json
{
  "type": "roof",
  "id": "roof_main",
  "roofType": "gable",
  "span": 8.8,
  "depth": 6.8,
  "height": 2.2,
  "thickness": 0.18,
  "position": [4, 3, 3],
  "material": "roof_tile"
}
```

`roofType` 只能是：

```text
gable | hip | dome | flat | chinese_curved | chinese_pagoda
```

- `position` 是屋顶水平中心和檐口基准高度，不是屋脊中心。
- `span` 覆盖 X，`depth` 覆盖 Z，`height` 是檐口基准以上的屋顶高度。
- `span/depth` 应至少覆盖结构墙包围盒；需要出檐时在对应方向增加两侧余量。
- `chinese_pagoda` 可选 `tiers/tierHeight/eaveOutset/shrinkFactor`。
- `chinese_curved` 可选 `eaveCurveHeight/curveProfile`。
- 历史值 `pitched/sloped/gabled/shed/mono-pitch` 会兼容映射为 `gable`，`hipped` 会映射为 `hip`；新文件严禁继续使用这些别名。

### 4.5 `opening`

`opening` 表示墙洞及一个简单覆盖面。需要门框、窗框、玻璃厚度、窗棂或开合行为时，应使用 `geometry.components` 中的 `door/window`。

```json
{
  "type": "opening",
  "id": "opening_service",
  "parentWall": "wall_front_l1",
  "from": [1.2, 0, 0],
  "width": 1,
  "height": 2.1,
  "depth": 0.04,
  "style": "rectangular",
  "material": "door_leaf"
}
```

`from` 是墙体局部/世界混合坐标：

```text
[开口左边缘沿墙距离, 开口底部世界 Y, 墙体法向偏移]
```

- `from[0]` 从 `parentWall.from.xz` 沿父墙方向或弧长量起，表示左边缘，不是开口中心，也不是世界 X/Z。
- `from[1]` 是世界 Y，必须满足开口底部不低于墙底、顶部不高于墙顶。
- `from[2]` 通常为 `0`；后端将绝对值大于 `0.25m` 视为错误。
- 必须满足 `from[0] >= 0` 且 `from[0] + width <= wallLength`。
- `style` 只能是 `rectangular/arched/gothic/circular`。
- 同一父墙上的洞口二维区域不得重叠。

### 4.6 `stair`

`from` 是下端，`to` 是上端，必须有 `from[1] < to[1]`，并与楼板顶面或墙顶标高对齐。可选 `stepCount/stepDepth/stepHeight`；省略时引擎按约 `0.18m` 步高和 `0.30m` 步深自动求步数。当前只支持直跑楼梯，不表示已完成建筑规范或结构安全校核。

### 4.7 `furniture`

`subtype` 只能是：

```text
table | chair | bookshelf | bed | lamp | tile
```

`dimensions` 固定为对象：

```json
{ "width": 1.2, "depth": 0.6, "height": 0.75 }
```

`furniture.subtype: "lamp"` 只是静态家具，不发光。发光灯具必须使用 `components.light`。沙发、柜子等未注册家具应由 `primitive` 组合表达，不得发明新的 `subtype`。

### 4.8 `primitive`

| `shape` | 必需几何字段 | 说明 |
|---|---|---|
| `box` | `dimensions: [width,height,depth]` | 盒体、板件和简单构件。 |
| `sphere` | `radius` | 可选 `segments`、`heightSegments`。 |
| `cylinder` | `height`，以及 `radius` 或同时提供 `radiusTop/radiusBottom` | 圆柱、圆锥和锥台。 |
| `profile_sweep` | `path` | 可选二维 `profile`；无 profile 时可用 `radius` 生成圆截面。 |

所有形体可选 `position/rotation/scale/material`。`rotation` 是 XYZ 欧拉角，单位弧度。不要为篮球、花瓶、檐口等现实名词增加新的 element type。

### 4.9 `dense_brick` 与 `body`

- `dense_brick` 已注册但仍为 experimental，等值面能力未达到 Agent 安全交付标准，当前禁止自动生成。
- `body` 是简化人物能力，`build` 为 `lean/athletic/stout`，`headShape` 为 `round/oval/angular`；它不是建筑人物资产系统。

## 5. `geometry.components` 组合构件

组合构件不是新的渲染原语。编译器在 Blueprint 副本上把它们展开为 `opening/primitive/beam` 等基础元素，源文件仍保留组件定义。某个组件编译失败会产生 `COMPONENT_COMPILE_FAILED`，并阻止该修改被当作成功交付。

当前支持 10 种组件：

| `type` | 必填字段（除 `type/id`） | 主要可选字段 |
|---|---|---|
| `door` | `parentWall,from,width,height` | `frameWidth,frameDepth,leafDepth,frameMaterial,leafMaterial,interaction,openingStyle,doorStyle,draggable` |
| `window` | `parentWall,from,width,height` | `frameWidth,frameDepth,glassDepth,verticalMullions,horizontalMullions,frameMaterial,glassMaterial,interaction,draggable` |
| `railing` | `path,height` | `postSpacing,postRadius,railRadius,railLevels,material,parentFloor,draggable` |
| `canopy` | `parentWall,from,width,depth,thickness` | `supportCount,supportSize,material,supportMaterial,draggable` |
| `balcony` | `parentWall,from,width,depth,slabThickness` | `railingHeight,postSpacing,material,railingMaterial,draggable` |
| `ramp` | `from,to,width,thickness` | `railingSides,railingHeight,postSpacing,material,railingMaterial,parentFloor,draggable` |
| `bay_window` | `parentWall,from,width,height,projectionDepth` | `frameWidth,frameDepth,frameMaterial,glassMaterial,draggable` |
| `cornice` | `path,profile` | `closedProfile,material,parentRoof,draggable` |
| `chimney` | `position,width,depth,height` | `wallThickness,capHeight,material,capMaterial,parentRoof,draggable` |
| `light` | `position` | `fixtureType,lightType,color,intensity/distance/angle,外观尺寸与材质,initiallyOn,draggable` |

组件对象执行严格字段白名单校验，不能写入未声明字段。`draggable` 只表示编辑器允许手动拖动，不代表吸附、碰撞或结构求解。

### 5.1 门窗组件

`door/window.from` 与 `opening.from` 完全相同：

```text
[左边缘沿父墙距离, 底部世界 Y, 法向偏移]
```

- 门默认 `frameWidth=0.08`；窗默认 `frameWidth=0.06`。
- `frameDepth` 默认等于父墙厚度。
- `leafDepth` 默认 `min(0.04, frameDepth)`；`glassDepth` 默认 `min(0.012, frameDepth)`。
- 面板深度不能大于框深；框深最多只能比父墙厚 `0.12m`。
- 法向偏移必须让框、门扇或玻璃与父墙厚度范围存在实体交叠。
- `verticalMullions/horizontalMullions` 必须是 `0–32` 的整数；`mullion` 不是独立类型。
- `door.openingStyle` 为 `rectangular/arched`，`doorStyle` 为 `single/double`。

`interaction` 是可选字段。省略时门窗为静态构件；提供后才具有运行时开合行为：

```json
{
  "mode": "swing",
  "hingeSide": "left",
  "openAngle": 90,
  "initiallyOpen": false
}
```

`mode` 为 `swing/slide`；`hingeSide` 为 `left/right`；`openAngle` 位于 `(0,180]`；滑动模式可设置正数 `openDistance`。动画进度只存在于运行时，不写回 Blueprint。

### 5.2 栏杆、坡道与依附坐标

- `railing.path` 至少两个不重合的三维点；`railLevels` 是 `(0,1]` 内不重复的相对高度，最多 8 层。
- 栏杆默认使用世界坐标。设置 `parentFloor` 后，路径以父楼板最小 X/Z 角和楼板顶面为局部原点。
- `ramp` 必须有水平延伸，不能是竖直构件；`railingSides` 为 `none/left/right/both`。
- 坡道指定 `parentFloor` 后允许延伸到楼板边界之外，其余楼板依附路径默认不得越界。

### 5.3 阳台、雨棚与凸窗

- `balcony.from[1]` 是阳台楼板顶面世界 Y；`depth` 始终表示室外悬挑深度。
- 编译器根据宿主墙相对于全体墙水平包围盒中心的位置推断室外方向，不依赖墙的顺逆时针。
- 同一阳台只能由一个 `balcony` 表达；禁止额外生成重合的 `floor` 或 `railing`。
- `canopy.from[1]` 是安装高度；支柱数量 `supportCount` 为 `0–16`。
- `bay_window` 会生成父墙洞口和投影窗体，但不等同于完整室内凸窗结构。

### 5.4 檐口、烟囱与灯具

- `cornice.profile` 至少三个二维有限点，沿 `path` 扫掠。
- `cornice/chimney.parentRoof` 只支持 `flat/gable/hip` 的确定性屋面依附；局部 X/Z 不得超出屋顶平面范围。
- 烟囱仅生成薄壁筒体和压顶，不会对屋顶做布尔穿透。
- `light.fixtureType` 为 `bulb/table_lamp`，`lightType` 为 `point/spot`。
- `initiallyOn` 可选，默认 `false`；`highIntensity` 不能小于 `lowIntensity`，聚光灯 `angle <= 90`。

## 6. 材质与 PBR 资产

### 6.1 标准材质

```json
{
  "wall_ext": {
    "baseColor": [0.78, 0.75, 0.7],
    "roughness": 0.82,
    "metallic": 0,
    "albedo": 1,
    "opacity": 1,
    "lightingCondition": "D65_noon",
    "normalScale": 1,
    "uvScale": [1, 1]
  }
}
```

| 字段 | 要求 |
|---|---|
| `baseColor` | 必需；三个 `0–1` 的 sRGB authored value，禁止 `#RRGGBB`。 |
| `roughness` | 必需；`0–1`。 |
| `metallic` | 必需；`0–1`。 |
| `albedo` | 必需；`0–1`。 |
| `lightingCondition` | 必需；固定 `D65_noon`。 |
| `emissive` | 可选；三个 `0–1` 数值。 |
| `opacity` | 可选；`0–1`，默认 1。物理玻璃必须为 1 或省略。 |
| `materialClass` | 可选；`standard/glass/clearcoat/fabric`。物理玻璃使用 `glass`。 |
| `side` | 可选；`front/double`。薄玻璃通常使用 `double`。 |
| `transmission` | 可选；`0–1`。物理玻璃必须大于 0。 |
| `ior` | 可选；`1–2.333`，建筑玻璃通常为 1.5。 |
| `thickness` | 可选；非负光学厚度。 |
| `effects` | 可选；`grain/weathering/moss/edgeWear` 效果层。 |
| `normalScale` | 可选；非负数。 |
| `uvScale` | 可选；两个正数。 |
| `textureSet` | 可选；引用 `assets` 中存在的 PBR 资产 ID。 |

解析器可把旧式 `color: "#RRGGBB"` 归一化为 `baseColor` 并补齐基础 PBR 参数，但保存的新蓝图必须直接使用标准字段。

玻璃不得只靠 `opacity: 0.35` 模拟；新蓝图使用 `materialClass: "glass"`、正数 `transmission` 和有效 `ior`，同时省略 `opacity` 或保持为 1。

### 6.2 URL 型 PBR 资产

新资产只在 Blueprint 中保存不可变清单和 URL，不保存图片 Base64：

```json
{
  "assets": {
    "pbr_0123456789abcdef01234567": {
      "schemaVersion": "1.0",
      "assetId": "pbr_0123456789abcdef01234567",
      "kind": "pbr_texture_set",
      "name": "Stone",
      "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "source": { "type": "user_upload" },
      "license": "User supplied",
      "maps": {
        "baseColor": {
          "encoding": "url",
          "uri": "/api/assets/pbr_0123456789abcdef01234567/files/baseColor.png",
          "mimeType": "image/png",
          "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "colorSpace": "srgb"
        }
      },
      "createdAt": "2026-08-10T00:00:00Z"
    }
  }
}
```

- 资产 key 和 `assetId` 必须匹配 `pbr_[0-9a-f]{24}`。
- `contentHash` 使用 `sha256:` 加 64 位小写十六进制摘要。
- `maps.baseColor` 必需；其余通道为 `normal/roughness/metalness/ambientOcclusion`。
- `uri` 必须是站内绝对路径或 HTTP(S) URL；MIME 只允许 PNG、JPEG、WebP。
- `baseColor.colorSpace` 固定 `srgb`，其余通道固定 `linear`。
- 旧版 `embeddedImage` 和 Base64 `textures` 仍可兼容读取，但新入库和 Agent 修改不得继续生成 Base64。

### 6.3 无图片程序化红砖

当墙面需要真实砖块比例、砖缝凹陷或连续风化，而项目不使用图片贴图时，材质可声明受控的 `procedural` 参数：

```json
{
  "brick_aged": {
    "baseColor": [0.52, 0.11, 0.055],
    "roughness": 0.84,
    "metallic": 0,
    "albedo": 1,
    "lightingCondition": "D65_noon",
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
        "efflorescence": 0.1,
        "verticalStreaks": 0.14,
        "baseDampness": 0.08
      }
    }
  }
}
```

- 第一阶段 `procedural.type` 只允许 `brick`；不允许携带 GLSL 或其他可执行代码。
- `brickSize`、`mortarWidth`、`mortarDepth` 使用米制墙面 UV；`bond` 只允许 `running/stack`。
- `seed` 为 `0–2147483647` 的整数；颜色是三个 `0–1` 数值；变化和老化强度均为 `0–1`。
- `brickSize` 范围为宽 `0.04–2m`、高 `0.02–1m`；`mortarWidth` 为 `0.002–0.03m` 且小于短边一半；`mortarDepth` 为 `0–0.02m`。
- `weathering.scale` 范围为 `0.1–100`；其余 weathering 字段均为 `0–1`。
- 第一阶段 `procedural` 与 `textureSet`、`textures`、`embeddedImage` 互斥。
- 相同 Blueprint 与 seed 必须得到确定结果；程序化材质只改变表面颜色、粗糙度和法线，不改变结构、洞口、碰撞或轮廓。

## 7. `behaviors` 与 `editor`

`behaviors` 的 Schema 包含：

- `physics.mass/collisionShape/constraints`；
- `scripts` 的 `on_click/on_enter/on_leave`；
- `animation` 的人物动画参数。

这些属于高级兼容能力，当前建筑 Agent 默认不生成。门窗和灯具交互应使用组件自身的 `interaction/initiallyOn`，不要同时再写一套通用脚本。

`editor` 只保存编辑器状态，例如 `revision`、分组、相机视角和 Agent 元数据。几何编译和空间校验不得依赖 `editor`。

## 8. 模板、实例与排布的当前边界

Core 的正式字段是：

```json
{
  "templates": {
    "column_proto": {
      "type": "column",
      "id": "template_column",
      "base": [0, 0, 0],
      "height": 3,
      "bottomRadius": 0.12,
      "topRadius": 0.12,
      "style": "modern"
    }
  },
  "instances": [
    { "id": "column_1", "ref": "column_proto", "position": [0, 0, 0] }
  ]
}
```

但是当前后端 `validate_reference_integrity` 仍按历史字段 `templateId` 检查实例，而 Core/Schema 使用 `ref`；`placements` 也只实现了 `gable` 屋顶的 `left/right` 表面。为了保证 Agent 最终校验、保存和前端重建一致：

- 当前 Agent 禁止生成 `templates/instances/placements`；
- 人工蓝图使用这些字段时视为实验能力；
- 在后端引用协议统一为 `ref` 并补齐跨端测试前，不得把它们写入正式生成配方。

## 9. 输入归一化与兼容策略

兼容层只处理能够确定意图的旧写法，不能把它们当作新规范：

| 输入问题 | 当前兼容处理 |
|---|---|
| `meta.version/type/name` 为空 | 后端生成链补为 `1.1/building/AI生成建筑`。 |
| `wall.height` 且 from/to 同高 | 转为 `to.y = from.y + height`，删除 `height`。 |
| `opening.style=door/window/double/lattice` | 收敛为 `rectangular`，必要时补常用高度。 |
| `column.style=round` | 转为 `modern`。 |
| 非标准屋顶别名 | 按 4.4 的映射转为 `gable/hip`。 |
| `furniture.subtype=sofa/counter` | 分别转为 `chair/table`。 |
| `primitive.box.dimensions` 为尺寸对象 | 三个正值完整时转为数组 `[width,height,depth]`。 |
| 材质 `color=#RRGGBB` | 转为 `baseColor` 并补基础 PBR 字段。 |
| 矩形楼板坐标对象或缺坐标 | 只有墙体包围盒和标高可无歧义推断时才恢复。 |
| 二层墙附组件把 `from[1]` 写成局部高度 | 明显低于父墙底超过 `0.5m` 时，加上父墙底 Y。 |

归一化无法确定意图时必须保留错误并交给校验器，不能猜测宿主、尺寸、楼层或材质。

## 10. 校验、修复与保存门禁

完整生成的确定性流水线顺序为：

1. 顶层结构和全局 ID；
2. 基础元素/组件必填字段与枚举；
3. `parentWall`、材质、模板和行为引用；
4. 门窗局部坐标；
5. 门窗是否完整位于父墙内、同墙是否重叠；
6. 墙体端点连接；
7. 楼梯标高；
8. 屋顶覆盖；
9. 构件尺寸范围；
10. 对可确定问题执行修复并立即重检；
11. AABB 碰撞、穿插和悬空检查；
12. 组合编译与前端重建诊断；
13. 设计方案中的立面槽位和数量约束。

当前关键阈值：

- 门窗法向偏移绝对值不得超过 `0.25m`，且仍要与墙厚实体相交。
- 门窗水平/竖向越界容差约 `0.05m`；重叠宽高同时超过 `0.05m` 时判为错误。
- 墙端点连接检查使用 `0.15m` 提示容差，但 Core 墙角延伸只接受 `<0.01m`；因此生成规范仍要求精确一致。
- 楼梯标高对齐容差为 `0.2m`。
- 屋顶小于墙体跨度一半是错误；正式蓝图应让屋顶完整覆盖墙体包围盒，而不是依赖宽松警告阈值。
- 碰撞使用 AABB 近似，警告不等同于精确几何碰撞结论。

自动修复执行成功不代表蓝图通过。每次修复后必须由同一校验器重检；完整生成只有最终错误数为 0、组件编译无错误且重建成功时才能保存并加载。

## 11. 最小完整建筑示例

下面是当前格式的完整 `.wild` 示例，可作为新蓝图骨架：

```json
{
  "meta": {
    "version": "1.1",
    "type": "building",
    "name": "八乘六米双坡小屋"
  },
  "geometry": {
    "elements": [
      {
        "type": "floor",
        "id": "floor_l1",
        "from": [0, -0.2, 0],
        "to": [8, -0.2, 6],
        "thickness": 0.2,
        "material": "floor_concrete"
      },
      {
        "type": "wall",
        "id": "wall_front_l1",
        "from": [0, 0, 0],
        "to": [8, 3, 0],
        "thickness": 0.24,
        "material": "wall_ext"
      },
      {
        "type": "wall",
        "id": "wall_right_l1",
        "from": [8, 0, 0],
        "to": [8, 3, 6],
        "thickness": 0.24,
        "material": "wall_ext"
      },
      {
        "type": "wall",
        "id": "wall_back_l1",
        "from": [8, 0, 6],
        "to": [0, 3, 6],
        "thickness": 0.24,
        "material": "wall_ext"
      },
      {
        "type": "wall",
        "id": "wall_left_l1",
        "from": [0, 0, 6],
        "to": [0, 3, 0],
        "thickness": 0.24,
        "material": "wall_ext"
      },
      {
        "type": "roof",
        "id": "roof_main",
        "roofType": "gable",
        "span": 8.8,
        "depth": 6.8,
        "height": 2.2,
        "thickness": 0.18,
        "position": [4, 3, 3],
        "material": "roof_tile"
      }
    ],
    "components": [
      {
        "type": "door",
        "id": "door_front",
        "parentWall": "wall_front_l1",
        "from": [1.2, 0, 0],
        "width": 1.2,
        "height": 2.2,
        "frameDepth": 0.24,
        "leafDepth": 0.04,
        "frameMaterial": "door_frame",
        "leafMaterial": "door_leaf",
        "interaction": {
          "mode": "swing",
          "hingeSide": "left",
          "openAngle": 90,
          "initiallyOpen": false
        }
      },
      {
        "type": "window",
        "id": "window_front",
        "parentWall": "wall_front_l1",
        "from": [4.4, 0.9, 0],
        "width": 1.6,
        "height": 1.2,
        "frameDepth": 0.24,
        "glassDepth": 0.012,
        "verticalMullions": 1,
        "horizontalMullions": 1,
        "frameMaterial": "window_frame",
        "glassMaterial": "glass"
      }
    ]
  },
  "materials": {
    "floor_concrete": {
      "baseColor": [0.55, 0.55, 0.53],
      "roughness": 0.9,
      "metallic": 0,
      "albedo": 1,
      "lightingCondition": "D65_noon"
    },
    "wall_ext": {
      "baseColor": [0.78, 0.75, 0.7],
      "roughness": 0.82,
      "metallic": 0,
      "albedo": 1,
      "lightingCondition": "D65_noon"
    },
    "roof_tile": {
      "baseColor": [0.48, 0.18, 0.1],
      "roughness": 0.78,
      "metallic": 0,
      "albedo": 1,
      "lightingCondition": "D65_noon"
    },
    "door_frame": {
      "baseColor": [0.2, 0.09, 0.04],
      "roughness": 0.68,
      "metallic": 0,
      "albedo": 1,
      "lightingCondition": "D65_noon"
    },
    "door_leaf": {
      "baseColor": [0.32, 0.12, 0.04],
      "roughness": 0.65,
      "metallic": 0,
      "albedo": 1,
      "lightingCondition": "D65_noon"
    },
    "window_frame": {
      "baseColor": [0.12, 0.12, 0.13],
      "roughness": 0.32,
      "metallic": 0.72,
      "albedo": 1,
      "lightingCondition": "D65_noon"
    },
    "glass": {
      "baseColor": [0.62, 0.78, 0.86],
      "roughness": 0.08,
      "metallic": 0,
      "albedo": 1,
      "opacity": 0.32,
      "lightingCondition": "D65_noon"
    }
  },
  "behaviors": {}
}
```

## 12. 生成与验收清单

- [ ] 输出是严格 JSON，没有注释、尾随逗号或 Markdown 包装残片。
- [ ] `meta.version/type/name` 完整，版本写 `1.1`。
- [ ] `geometry.elements` 存在；基础元素和组件 ID 全局唯一。
- [ ] 所有 Vec3 都是三个有限数字，所有尺寸为正数。
- [ ] 相邻结构墙的 XZ 端点精确一致，楼层 Y 连续。
- [ ] 门窗 `from[0]` 是左边缘沿墙距离，`from[1]` 是世界 Y，`from[2]` 通常为 0。
- [ ] 门窗完整落在父墙范围内，同墙门窗不重叠。
- [ ] 门框、门扇、窗框和玻璃深度与父墙相交。
- [ ] 阳台只使用一个 `balcony` 组件，没有重复楼板或栏杆。
- [ ] 屋顶枚举合法，中心和尺寸来自真实墙体包围盒。
- [ ] 每个材质引用都存在，材质必填字段和颜色范围正确。
- [ ] 新 PBR 只使用 URL 资产清单，材质 `textureSet` 引用闭合。
- [ ] 未生成 `dense_brick` 和当前受限的模板/实例/排布能力。
- [ ] 自动修复后执行同一校验器重检，最终错误数为 0。
- [ ] 前端组合编译和 `wild-core` 重建没有 error 级诊断。

## 13. 已知协议差异与维护要求

当前存在三处需要维护者知晓的实现差异：

1. `wild-lang/schema.json` 顶层尚未显式声明 `assets`，但 Schema 默认允许未知根字段，前后端应用层会对 `assets` 做专门校验，PBR 流程已有回归测试。
2. Core/Schema 的实例引用字段是 `ref`，后端空间引用校验仍读取旧字段 `templateId`，因此 Agent 暂停使用模板实例。
3. Schema 把 `geometry.elements` 视为可选，后端完整交付流水线把它视为必需；本文按更严格的最终交付要求执行。

上述差异被修复时，必须同步更新 Schema、TypeScript 类型、Python 校验器、自动化测试、知识库最小铁律以及本文档，不能只修改其中一处。
