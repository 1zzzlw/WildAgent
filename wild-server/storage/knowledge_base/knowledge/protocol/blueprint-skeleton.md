---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_skeleton
topic: structure
wild_version: "1.1"
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
  - behaviors
synonyms: []
---

# 蓝图骨架

原语蓝图使用 JSON 编码，文件扩展名 `.wild`。

## 顶层结构

必须包含 `meta` 和 `geometry`，可选 `materials`、`assets`、`materialLibraries`、`renderProfile` 和 `behaviors`。

```jsonc
{
  "meta": { ... },
  "geometry": { ... },
  "materials": { ... },
  "assets": { ... },
  "materialLibraries": [ ... ],
  "renderProfile": "builtin:default",
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
| `behaviors` | 否 | 物理、脚本与动画 |

## 元数据 (meta)

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | 是 | `"1.0"` 或 `"1.1"`；使用 `primitive`/PBR 纹理时必须为 `"1.1"` |
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
