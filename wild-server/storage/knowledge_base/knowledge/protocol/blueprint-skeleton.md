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
  - behaviors
synonyms: []
---

# 蓝图骨架

原语蓝图使用 JSON 编码，文件扩展名 `.wild`。

## 顶层结构

必须包含 `meta` 和 `geometry`，可选 `materials`、`assets`、`materialLibraries` 和 `behaviors`。

```jsonc
{
  "meta": { ... },
  "geometry": { ... },
  "materials": { ... },
  "assets": { ... },
  "materialLibraries": [ ... ],
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
| `behaviors` | 否 | 物理、脚本与动画 |

## 视口设置归属

蓝图只描述建筑、构件关系、材质和建筑交互。时间、天空背景、天气、世界光影、渲染风格、观察机位和组装播放由前端工作台设置，不写入 `.wild`。载入或切换蓝图不得覆盖工作台的环境设置。

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

## 材质与资产分工

材质与纹理资产不参与几何成形，只决定表面的最终外观。

| 字段 | 类型 | 职责 |
|------|------|------|
| `materials` | object | 材质字典。键为材质名（如 `"wall_plaster"`），值为材质定义。构件的 `material` 字段引用这里的键 |
| `assets` | object | PBR 纹理集资产清单。键为不可变 `assetId`，值为 `pbr_texture_set`（含各通道的资源地址、`mimeType`、`contentHash`）。材质通过 `textureSet` 引用它 |
| `materialLibraries` | string[] | 引用全局材质库。蓝图只保存引用而不内联资产，避免同一贴图在多份蓝图里重复复制 |

**引用方向**：`构件.material` → `materials[键]` → （可选）`materials[键].textureSet` → `assets[assetId]` → 资产地址。

**顺序要求**：`assets` 中的资产必须先存在，材质才能通过 `textureSet` 指向它。增量修改时先 `upsert_asset`，再 `upsert_material`。

**材质属于表现层**：纹理与效果层只影响表面着色，不改变构件的尺寸、位置或轮廓——即"画质增强，不改变几何语义"。


## 门扇附件 leafParts（Blueprint 1.1 可选扩展）

`door.leafParts` 表达随门移动的盒形附件，如把手、支座、护板和装饰条；不要把需要随动的部件另写成无依附的静态 primitive。

每项为 `{id,position:[x,y,z],dimensions:[w,h,d],material,leaf?:0|1}`。`x` 是相对所选门扇中心的沿墙偏移，`y` 是距门洞底部的高度（不是世界 Y），`z` 是相对门扇中面的法向偏移，单位为米。尺寸为正数；附件在门扇平面内不得越界。单扇门 leaf 只能为 0；双开门沿墙方向两扇依次为 0、1。id 在同一门的附件内唯一；material 引用蓝图材质。

附件随对应门扇平开、推拉或升降；门框保持固定。`interaction:false` 时附件和门扇一起保持静态。整个 door 移动或修改宿主时，附件由编译器重新定位，源文件不保存运行时矩阵、pivot 或 groupId。省略 leafParts 的旧门保持原有生成行为。当前附件只支持盒形；窗附件、任意模型依附不在本字段范围内。

示例：`"leafParts":[{"id":"handle","position":[0.4,1.1,0.04],"dimensions":[0.025,0.25,0.045],"material":"metal"}]`。需先核对所选门扇净宽能容纳 x 与附件半宽。
