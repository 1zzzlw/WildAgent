---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_skeleton
topic: structure
wild_version: "1.0"
status: supported
authority: maintainer
primary_terms:
  - 蓝图顶层结构
  - blueprint top level
  - meta
  - geometry
  - materials
  - assets
  - materialLibraries
  - renderProfile
  - presentation
  - behaviors
synonyms: []
---

# 蓝图骨架

原语蓝图使用 JSON 编码，文件扩展名 `.wild`。

## 顶层结构

必须包含 `meta` 和 `geometry`，可选 `materials`、`assets`、`materialLibraries`、`renderProfile`、`presentation` 和 `behaviors`。

```jsonc
{
  "meta": { ... },
  "geometry": { ... },
  "materials": { ... },
  "assets": { ... },
  "materialLibraries": [ ... ],
  "renderProfile": "builtin:default",
  "presentation": { ... },
  "behaviors": { ... }
}
```

| 字段 | 必需 | 说明 |
|------|------|------|
| `meta` | 是 | 版本、类型、名称等元数据 |
| `geometry` | 是 | 几何定义 |
| `materials` | 否 | 材质字典，键为材质名 |
| `assets` | 否 | PBR 纹理集资产清单，键为 `assetId` |
| `materialLibraries` | 否 | 全局材质库引用；蓝图只存引用，不复制全局资产 |
| `renderProfile` | 否 | 世界光影配置引用；省略时使用 `builtin:default` |
| `presentation` | 否 | 单蓝图的初始画面、环境、机位和入场意图；不修改几何或编辑器 UI |
| `behaviors` | 否 | 物理、脚本与动画 |

## 初始展示意图 (presentation)

2026-10-29 新增的可选字段；沿用当前版本和原有坐标语义，旧蓝图不需要迁移。以下为字段片段，不是独立蓝图：

```jsonc
{
  "presentation": {
    "style": "toon",
    "stage": "diorama",
    "environment": { "timeOfDay": 22, "rain": 0.65, "wetness": 0.85 },
    "camera": { "position": [-6.3, 7.6, 17.7], "target": [0, 1.6, 0] },
    "entrance": { "type": "assemble", "duration": 12 }
  }
}
```

| 字段 | 契约与当前实现 |
| --- | --- |
| `style` | `pbr` 或 `toon`；toon 对漫反射分级并叠加轮廓，保留原材质、发光、透射与水面。`meta.style` 仍是语义标签 |
| `stage` | `world` 或 `diorama`；后者收起外围地面、天空、天体与布景，雨雪范围按蓝图包围盒组织。不会自动生成正方形底座，底座仍须写入 geometry |
| `environment` | 复用世界环境字段。`timeOfDay` 为 0～24 小时；rain/wetness/snow/dust/wind/cloudCoverage/fog 为 0～1，均可省略。rain 控制雨丝，wetness 控制材质湿润响应 |
| `camera` | position 与 target 都必填，使用蓝图世界坐标和米制；两者不能重合。查看器居中偏移只在显示层应用一次，不改写这些坐标 |
| `entrance` | 当前仅支持 `type:"assemble"`，duration 为正数秒。按实际网格包围盒从低到高入场，兼容实例批处理，不按构件命名推断顺序 |

展示默认值在导入或切换蓝图时应用；切换到旧蓝图时恢复查看器原来的环境和风格。初始机位不会覆盖用户随后转动的视角。入场在首次加载时播放；开始交互、编辑重建或导出 GLB 前恢复最终变换，普通几何编辑不会重播。运行进度、临时矩阵、显示状态不进入蓝图或撤销历史。

该字段保存数据与受控预设，不接受自定义 Shader、JavaScript、回调、任意时间轴或 UI 隐藏代码。分辨率、画质预算与界面显隐由应用决定。材质、天气和光影配置继续由既有渲染运行时实现，不把表现设置混进墙、门窗或物理约束。

当前编辑器支持这套展示契约。多蓝图世界仍由 WorldDocument 的环境、主题和光影配置决定整体风格，不自动合并多个 Blueprint 的初始展示意图。后端 Schema 已添加同名字段，但自研 Agent 的设计规划、生成和 ScenePatch 尚未增加专门的展示编辑操作，不能据此声称全链自动生成已验收。

## 元数据 (meta)

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | 是 | 未上线阶段固定为 `"1.0"`；同样支持 `primitive` 和 PBR 纹理，历史 `"1.1"` 文件仍可读 |
| `type` | string | 是 | `"building"`、`"avatar"`、`"asset"` 或 `"scene"` |
| `name` | string | 是 | 实体名称 |
| `author` | string | 否 | 创建者地址 |
| `createdAt` | number | 否 | 创建时间戳 |
| `style` | string | 否 | 语义风格标识，如 "east-asian-tower" |
| `seed` | number | 否 | 随机种子，用于微调细节 |

## 几何条目公共字段

所有构件都具有：

- `id`：唯一标识符
- `material`：引用材质库中的材质名（可选）

## 材质与资产四字段分工

材质与纹理资产不参与几何成形，只决定表面的最终外观。

| 字段 | 类型 | 职责 |
|------|------|------|
| `materials` | object | 材质字典。键为材质名（如 `"wall_plaster"`），值为材质定义。构件的 `material` 字段引用这里的键 |
| `assets` | object | PBR 纹理集资产清单。键为不可变 `assetId`，值为 `pbr_texture_set`（含各通道的资源地址、`mimeType`、`contentHash`）。材质通过 `textureSet` 引用它 |
| `materialLibraries` | string[] | 引用全局材质库。蓝图只保存引用而不内联资产，避免同一贴图在多份蓝图里重复复制 |
| `renderProfile` | string | 引用世界光影配置（`wild.render-profile`）。省略时使用 `builtin:default` |

**引用方向**：`构件.material` → `materials[键]` → （可选）`materials[键].textureSet` → `assets[assetId]` → 资产地址。

**顺序要求**：`assets` 中的资产必须先存在，材质才能通过 `textureSet` 指向它。增量修改时先 `upsert_asset`，再 `upsert_material`。

**材质属于表现层**：纹理与效果层只影响表面着色，不改变构件的尺寸、位置或轮廓——即"画质增强，不改变几何语义"。


## 门扇附件 leafParts（Blueprint 1.1 可选扩展）

`door.leafParts` 表达随门移动的盒形附件，如把手、支座、护板和装饰条；不要把需要随动的部件另写成无依附的静态 primitive。

每项为 `{id,position:[x,y,z],dimensions:[w,h,d],material,leaf?:0|1}`。`x` 是相对所选门扇中心的沿墙偏移，`y` 是距门洞底部的高度（不是世界 Y），`z` 是相对门扇中面的法向偏移，单位为米。尺寸为正数；附件在门扇平面内不得越界。单扇门 leaf 只能为 0；双开门沿墙方向两扇依次为 0、1。id 在同一门的附件内唯一；material 引用蓝图材质。

附件随对应门扇平开、推拉或升降；门框保持固定。`interaction:false` 时附件和门扇一起保持静态。整个 door 移动或修改宿主时，附件由编译器重新定位，源文件不保存运行时矩阵、pivot 或 groupId。省略 leafParts 的旧门保持原有生成行为。当前附件只支持盒形；窗附件、任意模型依附不在本字段范围内。

示例：`"leafParts":[{"id":"handle","position":[0.4,1.1,0.04],"dimensions":[0.025,0.25,0.045],"material":"metal"}]`。需先核对所选门扇净宽能容纳 x 与附件半宽。
