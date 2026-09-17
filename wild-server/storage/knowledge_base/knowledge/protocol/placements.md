---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_placements
topic: structure
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 布局放置
  - placements
  - onSurface
  - layout grid
  - cellMaterials
  - 屋顶瓦片铺排
synonyms: []
---

# 布局放置 (placements)

`placements` 数组提供了一种用数学规则批量生成构件实例的方式。与 `instances` 逐个指定位置不同，`placements` 通过父构件表面 + 网格布局参数自动计算每个实例的位置和朝向。

**适用场景**：屋顶瓦片铺排、墙面砖缝排列、地板铺装、密集装饰阵列等。

## 语法

```json
{
  "placements": [
    {
      "id": "roof_tiles_left",
      "template": "roof_tile",
      "onSurface": {
        "parent": "main_roof",
        "face": ["left", "right"]
      },
      "layout": {
        "type": "grid",
        "columns": 19,
        "rows": 23,
        "rowSpacing": 0.183,
        "colSpacing": 0.308,
        "overlap": 0.04,
        "gapWidth": 0.008
      }
    }
  ]
}
```

## 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 本 placement 的唯一标识，引擎用它构建实例 id 前缀 |
| `template` | string | 是 | 引用的模板名，须在顶层 `templates` 中定义 |
| `onSurface` | object | 是 | 指定放置目标表面 |
| `onSurface.parent` | string | 是 | 目标构件 ID |
| `onSurface.face` | string 或 string[] | 是 | 目标表面的名称。可以是单一面（如 `"left"`）或面名数组（如 `["left", "right"]`）。各面共用一个 layout 参数。可用面名取决于父构件的类型 |
| `layout` | object | 是 | 放置布局描述 |

## layout.type: "grid" 参数

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `columns` | number | 是 | 每行瓦/块数（沿表面 U 方向） |
| `rows` | number | 是 | 行数（沿表面 V 方向） |
| `colSpacing` | number | 是 | 列间距（米），含块宽和缝隙 |
| `rowSpacing` | number | 是 | 行间距（米），含块高和缝隙 |
| `overlap` | number | 否 | V 方向重叠量（米），用于叠瓦场景。为 0 时无重叠 |
| `gapWidth` | number | 否 | 同排行之间的缝隙宽度（米）。默认 0.008 |
| `cellMaterials` | object | 否 | 按格子覆盖材质。键为 `"{行}_{列}"`，值为材质名。例：`{"3_5": "broken_tile"}` 表示第 3 行第 5 列的格子使用 "broken_tile" 材质而非模板默认材质 |

## 展开规则

引擎按以下步骤将一条 placement 展开为若干独立构件：

1. 根据 `onSurface.parent` 查找父构件，根据 `onSurface.face` 确定目标表面。
2. 从父构件的几何定义中推导目标表面的四角坐标和法线方向。
3. 在表面上以 (U, V) 网格计算每个放置点的 3D 坐标：
   - U 方向第 col 列：`u = col * colSpacing`
   - V 方向第 row 行：`v = row * rowSpacing`
   - 网格原点位于表面的第一个角（底前）。
4. 每个放置点生成一个独立构件，构件定义为模板的深拷贝，并覆写：
   - `position`：根据表面四角插值计算的 3D 坐标
   - `rotation`：对齐表面法线的朝向（XYZ 欧拉角）
5. 构件的 `id` 自动生成为 `{placement_id}_{行}_{列}`（若 `face` 为数组则加上面索引，如 `roof_tiles_left_0_0`）。

## 与 instances 的关系

- `placements` 和 `instances` 在同一蓝图中共存，引擎先展开 placements，再追加 instances。
- 两者展开后的结果合并为一个元素列表，输入模板展开器后的同一处理管线。因此 placements 生成的实例同样可被 behaviors 中的事件引用。
