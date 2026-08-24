---
knowledge_layer: architecture
entity_type: material
entity_name: public_building_material_palette
topic: parameters
status: experimental
authority: domain_reference
source: recipes/public-building-material-palette.md
primary_terms:
  - 公共建筑材质
  - concrete
  - metal
  - glass
  - roughness
synonyms:
  - public building materials
---

# 公共建筑视觉材质调色板

> 来源：用户提供的《WILD蓝图AI提示词与构件规则_公共建筑_当前规范版》材质附录。下列值只用于生成初始视觉层次，不证明真实材料性能；它们是 `MaterialDef` 标量参数，不是带贴图通道的 PBR 素材包。

## 公共建筑材质字段边界

<!-- rag-meta
entity_type: material
entity_name: public_material_schema_boundary
topic: constraints
status: supported
authority: schema
primary_terms:
  - MaterialDef
  - baseColor
  - roughness
  - metallic
  - albedo
  - lightingCondition
synonyms: []
-->

每个蓝图内材质至少提供 `baseColor`、`roughness`、`metallic`、`albedo` 和 `lightingCondition: D65_noon`。`baseColor` 使用 0～1 的三分量数组；材质名称只是可自定义引用 ID，元素和组件引用必须与其完全一致。

## 公共建筑实体与金属材质

<!-- rag-meta
entity_type: material
entity_name: public_solid_metal_materials
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - reinforced_concrete
  - floor_concrete
  - wall_ext
  - metal
  - steel_railing
synonyms: []
-->

| 材质 ID | `baseColor` | `roughness` | `metallic` | 建议角色 |
|---|---:|---:|---:|---|
| `reinforced_concrete` | `[0.52, 0.52, 0.50]` | 0.92 | 0.00 | 核心筒、巨柱、地下体量 |
| `floor_concrete` | `[0.55, 0.55, 0.53]` | 0.90 | 0.00 | 楼板、看台、铺装 |
| `wall_ext` | `[0.78, 0.75, 0.70]` | 0.82 | 0.00 | 普通外墙涂层 |
| `white_plaster` | `[0.90, 0.89, 0.87]` | 0.70 | 0.00 | 白色抹面 |
| `metal` | `[0.70, 0.70, 0.70]` | 0.30 | 0.90 | 钢构、屋盖、雨棚 |
| `steel_railing` | `[0.60, 0.60, 0.62]` | 0.25 | 0.95 | 栏杆和细金属构件 |
| `window_frame` | `[0.12, 0.12, 0.13]` | 0.32 | 0.72 | 门窗和幕墙框 |

## 公共建筑木、砖石与屋面材质

<!-- rag-meta
entity_type: material
entity_name: public_masonry_wood_roof_materials
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - wood_red
  - wood_plank
  - stone_rubble
  - grey_brick
  - red_brick
  - grey_tile
synonyms: []
-->

| 材质 ID | `baseColor` | `roughness` | `metallic` | 建议角色 |
|---|---:|---:|---:|---|
| `wood_red` | `[0.40, 0.15, 0.08]` | 0.70 | 0.00 | 中式柱梁与木构 |
| `wood_plank` | `[0.60, 0.40, 0.20]` | 0.75 | 0.00 | 运动地板、露台、木饰面 |
| `stone_rubble` | `[0.60, 0.58, 0.55]` | 0.95 | 0.00 | 石墙、台基和园林体量 |
| `grey_brick` | `[0.45, 0.42, 0.40]` | 0.92 | 0.00 | 灰砖墙 |
| `red_brick` | `[0.65, 0.30, 0.25]` | 0.92 | 0.00 | 红砖墙 |
| `grey_tile` | `[0.40, 0.38, 0.35]` | 0.88 | 0.00 | 中式屋面 |
| `concrete_ramp` | `[0.55, 0.53, 0.50]` | 0.85 | 0.00 | 坡道和室外混凝土面 |
| `grass_terrain` | `[0.30, 0.50, 0.20]` | 1.00 | 0.00 | 平面场地的绿色近似，不代表存在 terrain 类型 |

## 公共建筑玻璃材质

<!-- rag-meta
entity_type: material
entity_name: public_glass_material
topic: parameters
status: experimental
authority: engine
primary_terms:
  - facade_glass
  - materialClass glass
  - transmission
  - ior
  - opacity
synonyms: []
-->

来源采用单一 `opacity` 值表达玻璃；当前渲染器已支持更专业的玻璃字段，因此玻璃应规范化为 `materialClass: glass`、`transmission`、`ior`、`thickness` 与低 `roughness` 的组合。幕墙玻璃使用 `recipes/glass-curtain-wall-assembly.md` 的 `facade_glass` 示例，避免同时召回两套互相冲突的透明度参数。

普通门窗玻璃与幕墙玻璃应使用不同材质 ID，以便分别调整色调、透射和粗糙度。材质参数不会自动产生玻璃厚度分层、Low-E 镀膜、隔热、防火或天气响应。
