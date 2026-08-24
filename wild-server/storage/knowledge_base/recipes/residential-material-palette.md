---
knowledge_layer: architecture
entity_type: material
entity_name: residential_material_palette
topic: parameters
status: experimental
authority: domain_reference
source: recipes/residential-material-palette.md
primary_terms:
  - 居住建筑材质
  - baseColor
  - roughness
  - metallic
  - opacity
synonyms:
  - residential material palette
---

# 居住建筑建议材质调色板

> 来源资料：用户提供的《WILD蓝图AI描述词与构件组合规则_居住建筑.md》附录。
> 用途：为居住建筑的不同材料角色提供一致的建议颜色和表面参数；材质名是自定义引用名，不是 WILD 构件类型。

## 居住建筑材质的当前 Schema 约束

<!-- rag-meta
entity_type: material
entity_name: residential_material_schema_rules
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

每个 `materials.<name>` 至少应提供 `baseColor`、`roughness`、`metallic`、`albedo` 和 `lightingCondition`。下表中的所有材质默认补充 `albedo: 1.0` 与 `lightingCondition: "D65_noon"`；只有玻璃类材质使用小于 1 的 `opacity`。`baseColor` 必须是三个 0～1 数值，材质名可以自由定义，但必须与元素的 `material` 引用完全一致。

## 现代结构、金属与玻璃材质

<!-- rag-meta
entity_type: material
entity_name: modern_residential_materials
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - white_concrete
  - reinforced_concrete
  - steel_sandwich
  - glass_curtain
  - steel_railing
synonyms: []
-->

以下数值适合现代别墅、公寓、高层住宅和临建的视觉初始化，不代表真实材料检测结果。玻璃幕墙仅是材质表现，当前引擎没有完整幕墙系统。

| 材质名 | `baseColor` | `roughness` | `metallic` | `opacity` | 建议用途 |
|---|---:|---:|---:|---:|---|
| `white_concrete` | `[0.85, 0.84, 0.82]` | 0.92 | 0.0 | 1.0 | 现代别墅、新中式、保障房墙面 |
| `reinforced_concrete` | `[0.55, 0.55, 0.53]` | 0.92 | 0.0 | 1.0 | 楼板、墙体与基础体量 |
| `steel_sandwich` | `[0.65, 0.68, 0.72]` | 0.40 | 0.60 | 1.0 | 工地临建围护视觉 |
| `glass_curtain` | `[0.60, 0.70, 0.75]` | 0.05 | 0.0 | 0.35 | 公寓玻璃立面近似 |
| `steel_railing` | `[0.60, 0.60, 0.62]` | 0.25 | 0.95 | 1.0 | 金属扶手或细构件近似 |

## 木材与木瓦材质

<!-- rag-meta
entity_type: material
entity_name: residential_wood_materials
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - wood_red
  - wood_plank
  - wood_oak
  - wood_shingle
  - 木材
  - 木瓦
synonyms: []
-->

木材组用于中式住宅、吊脚楼、木屋和民宿。不同结构角色应使用独立材质名，避免柱梁、楼板、门扇和木瓦全部共享一个表面参数而失去层次。

| 材质名 | `baseColor` | `roughness` | `metallic` | `opacity` | 建议用途 |
|---|---:|---:|---:|---:|---|
| `wood_red` | `[0.40, 0.15, 0.08]` | 0.70 | 0.0 | 1.0 | 中式柱梁、吊脚楼和前廊构件 |
| `wood_plank` | `[0.60, 0.40, 0.20]` | 0.75 | 0.0 | 1.0 | 木楼板、木墙面和栈道 |
| `wood_oak` | `[0.50, 0.30, 0.15]` | 0.65 | 0.0 | 1.0 | 入户门扇近似或室内木作 |
| `wood_shingle` | `[0.35, 0.20, 0.10]` | 0.85 | 0.0 | 1.0 | 木瓦屋顶 |

## 砖石、抹灰与土质材质

<!-- rag-meta
entity_type: material
entity_name: residential_masonry_earth_materials
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - grey_brick
  - red_brick
  - white_plaster
  - rammed_earth
  - stone_rubble
synonyms: []
-->

砖石与土质组适合中式住宅、农村自建房、民宿和窑洞近似。材质参数只影响渲染外观，不会让墙体自动获得承重、防水、保温或文物保护性能。

| 材质名 | `baseColor` | `roughness` | `metallic` | `opacity` | 建议用途 |
|---|---:|---:|---:|---:|---|
| `grey_brick` | `[0.50, 0.48, 0.45]` | 0.92 | 0.0 | 1.0 | 中式住宅、院墙和康养小院 |
| `red_brick` | `[0.55, 0.25, 0.15]` | 0.92 | 0.0 | 1.0 | 农村住宅和院墙 |
| `white_plaster` | `[0.85, 0.83, 0.78]` | 0.90 | 0.0 | 1.0 | 新中式、徽派或现代白墙 |
| `rammed_earth` | `[0.60, 0.45, 0.25]` | 0.95 | 0.0 | 1.0 | 窑洞和夯土民宿体量近似 |
| `stone_rubble` | `[0.55, 0.50, 0.45]` | 0.95 | 0.0 | 1.0 | 毛石墙面、院墙和基础体量 |

## 屋面与场地视觉材质

<!-- rag-meta
entity_type: material
entity_name: residential_roof_site_materials
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - grey_tile
  - clay_tile
  - grass_terrain
  - 屋面材质
  - 场地材质
synonyms: []
-->

屋面材质应引用当前支持的 `roof`，场地绿色只能作为 `floor` 或 `primitive` 的视觉材质。`grass_terrain` 这个名字不表示存在 `terrain` 元素，也不会生成草地起伏、植被或 heightmap。

| 材质名 | `baseColor` | `roughness` | `metallic` | `opacity` | 建议用途 |
|---|---:|---:|---:|---:|---|
| `grey_tile` | `[0.40, 0.38, 0.35]` | 0.88 | 0.0 | 1.0 | 中式曲面或灰瓦坡顶 |
| `clay_tile` | `[0.60, 0.25, 0.15]` | 0.85 | 0.0 | 1.0 | 联排别墅等暖色坡顶 |
| `grass_terrain` | `[0.30, 0.50, 0.20]` | 1.00 | 0.0 | 1.0 | 平面场地或背景体块的绿色近似 |
